"""
Shared MCP message streaming utilities.

Provides the common streaming pipeline used by both the per-connector
MCPRequestHandler and the App MCP AppMCPRequestHandler:
- Per-session locking (prevents concurrent message processing)
- MCP progress / log notifications
- Stream-collect-return loop (environment readiness → stream → JSON result)

Each handler is responsible for its own session resolution and message
creation; this module picks up from "session + message exist, now stream."
"""

import asyncio
import json
import logging
import time
from typing import Callable
from uuid import UUID

from sqlmodel import Session as DbSession

from app.models import Session
from app.services.sessions.session_service import SessionService
from app.services.sessions.message_service import MessageService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-session locks — shared singleton across all MCP handler types
# ---------------------------------------------------------------------------
_session_locks: dict[str, asyncio.Lock] = {}
_MAX_SESSION_LOCKS = 1000


def get_session_lock(session_id: str) -> asyncio.Lock:
    """Return (or create) a per-session asyncio.Lock.

    Bounded: evicts unlocked entries when the dict exceeds
    ``_MAX_SESSION_LOCKS`` to prevent unbounded memory growth.
    """
    if session_id not in _session_locks:
        if len(_session_locks) >= _MAX_SESSION_LOCKS:
            to_remove = [
                sid for sid, lock in _session_locks.items()
                if not lock.locked()
            ]
            for sid in to_remove:
                del _session_locks[sid]
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


# ---------------------------------------------------------------------------
# MCP progress / log notifications
# ---------------------------------------------------------------------------

async def send_mcp_progress(
    mcp_ctx,
    event: dict,
    progress: int,
    last_info_time: float,
) -> tuple[int, float]:
    """Send MCP progress and log notifications for a streaming event.

    Returns updated ``(progress, last_info_time)`` tuple.
    Failures are silently caught — notifications must never crash the tool.
    """
    if mcp_ctx is None:
        return progress, last_info_time

    event_type = event.get("type", "")
    now = time.monotonic()

    try:
        if event_type == "assistant" and progress < 100:
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, "Processing...")
        elif event_type == "tool" and progress < 100:
            tool_name = event.get("name", "tool")
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, f"Using tool: {tool_name}")
        elif event_type == "thinking" and progress < 100:
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, "Thinking...")
    except Exception:
        logger.debug("[MCP] Failed to send progress notification (non-fatal)", exc_info=True)

    try:
        if event_type == "assistant":
            content = event.get("content", "")
            if content and (now - last_info_time) >= 0.5:
                await mcp_ctx.info(content)
                last_info_time = now
    except Exception:
        logger.debug("[MCP] Failed to send log notification (non-fatal)", exc_info=True)

    return progress, last_info_time


# ---------------------------------------------------------------------------
# Core streaming pipeline
# ---------------------------------------------------------------------------

async def stream_and_collect_response(
    *,
    session_id: UUID,
    get_fresh_db_session: Callable[[], DbSession],
    mcp_ctx=None,
    timeout_seconds: int = 120,
    log_prefix: str = "[MCP]",
) -> str:
    """Ensure environment is ready, stream response, and return JSON result.

    This encapsulates Phases 2–3 of the MCP message pipeline, following
    the same message lifecycle as ``process_pending_messages``:

    - Phase 2: ensure environment is ready for streaming (wakes suspended envs)
    - Phase 3: collect pending messages, mark as sent, stream, collect response

    The caller must have already created the user message in the DB
    (with default ``sent_to_agent_status="pending"``) before calling this.

    Args:
        session_id: Platform session UUID.
        get_fresh_db_session: Factory for new DB sessions.
        mcp_ctx: Optional MCP context for progress notifications.
        timeout_seconds: Max wait for environment readiness.
        log_prefix: Logging prefix ("[MCP]" or "[AppMCP]").

    Returns:
        The agent's response text (empty string if no response),
        or a JSON error string with ``error`` and ``context_id`` keys.
    """
    result_context_id = str(session_id)

    # Phase 2: Ensure environment is ready
    if mcp_ctx is not None:
        try:
            await mcp_ctx.report_progress(0, 100, "Preparing agent environment...")
        except Exception:
            logger.debug("%s Failed to send initial progress notification (non-fatal)", log_prefix, exc_info=True)

    try:
        environment, _agent = await SessionService.ensure_environment_ready_for_streaming(
            session_id=session_id,
            get_fresh_db_session=get_fresh_db_session,
            timeout_seconds=timeout_seconds,
        )
    except (ValueError, RuntimeError) as e:
        logger.error("%s Environment not ready for streaming: %s", log_prefix, e)
        return json.dumps({"error": f"Environment not ready: {e}", "context_id": result_context_id})

    # Phase 3: Stream response with per-session locking
    session_id_str = str(session_id)
    lock = get_session_lock(session_id_str)
    if lock.locked():
        return json.dumps({
            "error": "Another message is being processed. Please wait.",
            "context_id": result_context_id,
        })

    async with lock:
        # Collect all pending messages and mark as sent — same lifecycle as
        # process_pending_messages.  This correctly handles the case where
        # multiple messages queued up while the environment was waking.
        with get_fresh_db_session() as db:
            concatenated_content, pending_messages = MessageService.collect_pending_messages(db, session_id)
            if not concatenated_content or not pending_messages:
                logger.info("%s No pending messages for session %s", log_prefix, session_id)
                return ""

            session_obj = db.get(Session, session_id)
            session_mode = (session_obj.mode or "conversation") if session_obj else "conversation"
            external_session_id = (
                (session_obj.session_metadata or {}).get("external_session_id")
                if session_obj else None
            )

            message_ids = [msg.id for msg in pending_messages]

        # Mark messages as sent — they are about to be delivered to the agent.
        # Done outside the read transaction, same pattern as process_pending_messages.
        with get_fresh_db_session() as db:
            MessageService.mark_messages_as_sent(db, message_ids)

        logger.info(
            "%s Streaming %d pending message(s) for session %s",
            log_prefix, len(pending_messages), session_id,
        )

        response_parts: list[str] = []
        mcp_progress = 0
        mcp_last_info_time = 0.0

        try:
            async for event in MessageService.stream_message_with_events(
                session_id=session_id,
                environment_id=environment.id,
                user_message_content=concatenated_content,
                session_mode=session_mode,
                external_session_id=external_session_id,
                get_fresh_db_session=get_fresh_db_session,
            ):
                event_type = event.get("type", "")

                mcp_progress, mcp_last_info_time = await send_mcp_progress(
                    mcp_ctx, event, mcp_progress, mcp_last_info_time,
                )

                if event_type == "assistant":
                    content = event.get("content", "")
                    if content:
                        response_parts.append(content)
                elif event_type == "error":
                    error_content = event.get("content", "Unknown error")
                    logger.error("%s Error event from agent: %s", log_prefix, error_content)
                    return json.dumps({
                        "error": f"Error from agent: {error_content}",
                        "context_id": result_context_id,
                    })

        except Exception as e:
            logger.error("%s Error streaming from agent environment: %s", log_prefix, e)
            return json.dumps({
                "error": f"Failed to communicate with agent environment: {e}",
                "context_id": result_context_id,
            })

    full_response = "\n\n".join(response_parts)
    logger.info(
        "%s Response complete | session=%s | response_parts=%d | length=%d",
        log_prefix, session_id, len(response_parts), len(full_response),
    )
    return full_response if full_response else ""
