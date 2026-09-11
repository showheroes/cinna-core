"""Authenticated, bounded ACP JSON-RPC WebSocket transport (experimental remote profile)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections import Counter
from uuid import UUID

import anyio
from acp.connection import Connection
from acp.exceptions import RequestError
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.acp.agent import CinnaACPAgent
from app.core.config import settings
from app.core.db import create_session
from app.services.acp.connector_service import ACPConnectorService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["acp"])
MAX_FRAME_BYTES = 256 * 1024
MAX_CONNECTIONS = 64
MAX_INFLIGHT = 8
SEND_TIMEOUT = 15
IDLE_TIMEOUT = 600


class WebSocketTransport:
    """Official SDK Transport seam with strict framing, rate and concurrency bounds."""

    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self.closed = False
        self.pending: set[str | int] = set()
        self.send_lock = asyncio.Lock()
        self.tokens = 60.0
        self.last_message = time.monotonic()

    async def send(self, message: dict) -> None:
        if self.closed:
            raise ConnectionError("ACP connection closed")
        body = json.dumps(message, separators=(",", ":"), ensure_ascii=False)
        async with self.send_lock:
            try:
                await asyncio.wait_for(self.websocket.send_text(body), SEND_TIMEOUT)
            except Exception:
                await self.close()
                raise
        if "id" in message and "method" not in message:
            self.pending.discard(message["id"])

    async def fail(self, error: RequestError, request_id=None) -> None:
        await self.send(
            {"jsonrpc": "2.0", "id": request_id, "error": error.to_error_obj()}
        )

    async def receive(self) -> dict | None:
        while not self.closed:
            try:
                frame = await asyncio.wait_for(self.websocket.receive(), IDLE_TIMEOUT)
            except TimeoutError:
                if self.pending:
                    continue
                await self.close()
                return None
            except (WebSocketDisconnect, RuntimeError):
                await self.close()
                return None
            if frame["type"] == "websocket.disconnect":
                self.closed = True
                return None
            text = frame.get("text")
            if text is None:
                await self.close(1003)
                return None
            if len(text.encode("utf-8")) > MAX_FRAME_BYTES:
                await self.close(1009)
                return None
            now = time.monotonic()
            self.tokens = min(60.0, self.tokens + (now - self.last_message) * 10)
            self.last_message = now
            self.tokens -= 1
            if self.tokens < 0:
                await self.close(1008)
                return None
            try:
                message = json.loads(text)
            except (ValueError, RecursionError):
                await self.fail(RequestError.parse_error())
                continue
            if (
                not isinstance(message, dict)
                or message.get("jsonrpc") != "2.0"
                or not isinstance(message.get("method"), str)
            ):
                await self.fail(RequestError.invalid_request())
                continue
            request_id = message.get("id")
            if "id" in message:
                if (
                    isinstance(request_id, bool)
                    or not isinstance(request_id, (str, int))
                    or (isinstance(request_id, str) and len(request_id) > 128)
                ):
                    await self.fail(RequestError.invalid_request())
                    continue
                if request_id in self.pending:
                    # Duplicate IDs cannot be correlated unambiguously; close the peer.
                    await self.close(1008)
                    return None
                if len(self.pending) >= MAX_INFLIGHT:
                    await self.fail(
                        RequestError(-32004, "Too many in-flight requests"), request_id
                    )
                    continue
                self.pending.add(request_id)
            return message
        return None

    async def close(self, code: int = 1000) -> None:
        if self.closed:
            return
        self.closed = True
        if self.websocket.application_state == WebSocketState.CONNECTED:
            with contextlib.suppress(Exception):
                await self.websocket.close(code=code)


class ACPRuntime:
    def __init__(self) -> None:
        self.connections: dict[WebSocketTransport, CinnaACPAgent] = {}
        self.counts: Counter[str] = Counter()
        self.tasks: set[asyncio.Task] = set()

    async def shutdown(self) -> None:
        await asyncio.gather(
            *(agent.close() for agent in list(self.connections.values())),
            return_exceptions=True,
        )
        await asyncio.gather(
            *(transport.close(1001) for transport in list(self.connections)),
            return_exceptions=True,
        )
        tasks = list(self.tasks)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=5)
            for task in pending:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


acp_runtime = ACPRuntime()


def allowed_origin(origin: str | None) -> bool:
    # Native/stdio clients omit Origin. Browser callers must use the trusted UI
    # origins; bearer tokens never go in URLs, cookies or WebSocket subprotocols.
    if origin is None:
        return True
    allowed = {str(value).rstrip("/") for value in settings.all_cors_origins}
    allowed.add(str(settings.FRONTEND_HOST).rstrip("/"))
    return origin.rstrip("/") in allowed


@router.websocket("/acp/{connector_id}")
async def acp_websocket(websocket: WebSocket, connector_id: UUID) -> None:
    if not allowed_origin(websocket.headers.get("origin")) or websocket.query_params:
        await websocket.close(code=1008)
        return
    auth_header = websocket.headers.get("authorization", "")
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 256:
        await websocket.close(code=1008)
        return
    with create_session() as db:
        auth = ACPConnectorService.authenticate(connector_id, token, db)
        if auth is None:
            await websocket.close(code=1008)
            return
        limit = auth.connector.max_connections
        key = str(connector_id)
        if (
            len(acp_runtime.connections) >= MAX_CONNECTIONS
            or acp_runtime.counts[key] >= limit
        ):
            await websocket.close(code=1013)
            return
        ACPConnectorService.mark_used(db, auth.token)
    # No await between admission and reserving the count.
    acp_runtime.counts[key] += 1
    transport = WebSocketTransport(websocket)
    agent = CinnaACPAgent(connector_id, token)
    acp_runtime.connections[transport] = agent
    connection = Connection(agent.dispatch, transport, listening=False)
    agent.connection = connection
    task = asyncio.current_task()
    assert task is not None
    acp_runtime.tasks.add(task)
    try:
        await websocket.accept()
        await connection.main_loop()
    except Exception:
        logger.debug("ACP connection ended", exc_info=True)
    finally:
        with anyio.CancelScope(shield=True):
            # Forward cancellation while the agent still owns its prompt tasks, then
            # cancel the SDK dispatcher. No prompt is detached from its connection.
            await agent.close()
            await connection.close()
            acp_runtime.tasks.discard(task)
            acp_runtime.connections.pop(transport, None)
            acp_runtime.counts[key] -= 1
            if not acp_runtime.counts[key]:
                del acp_runtime.counts[key]
