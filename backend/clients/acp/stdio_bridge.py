# /// script
# requires-python = ">=3.10"
# dependencies = ["websockets>=15,<17"]
# ///
"""Expose a remote Cinna ACP connector as a standard ACP stdio subprocess.

Configure CINNA_ACP_URL=wss://host/acp/<connector UUID> and CINNA_ACP_TOKEN.
Only JSON-RPC messages are written to stdout; errors go to stderr.
The bridge maps the editor's local cwd to the fixed remote /app/workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import json
import os
import sys
from urllib.parse import urlsplit

from websockets.asyncio.client import connect

MAX_FRAME_BYTES = 256 * 1024


def validate_url(url: str) -> None:
    parsed = urlsplit(url)
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not parsed.hostname
    ):
        raise ValueError(
            "CINNA_ACP_URL must be a WebSocket endpoint without credentials or query parameters"
        )
    loopback = parsed.hostname == "localhost"
    with contextlib.suppress(ValueError):
        loopback = ipaddress.ip_address(parsed.hostname).is_loopback
    if parsed.scheme != "wss" and not (parsed.scheme == "ws" and loopback):
        raise ValueError(
            "Use wss:// for remote hosts (ws:// is permitted only on loopback)"
        )


class OutputProtocol(asyncio.Protocol):
    """Async stdout backpressure keeps cancellation and EOF processing responsive."""

    def __init__(self):
        self.writable = asyncio.Event()
        self.writable.set()
        self.closed = False

    def pause_writing(self):
        self.writable.clear()

    def resume_writing(self):
        self.writable.set()

    def connection_lost(self, exc):
        self.closed = True
        self.writable.set()

    async def drain(self):
        await asyncio.wait_for(self.writable.wait(), timeout=15)
        if self.closed:
            raise BrokenPipeError("Editor closed stdout")


async def bridge(url: str, token: str) -> None:
    validate_url(url)
    reader = asyncio.StreamReader(limit=MAX_FRAME_BYTES + 1)
    protocol = asyncio.StreamReaderProtocol(reader)
    input_transport, _ = await asyncio.get_running_loop().connect_read_pipe(
        lambda: protocol, sys.stdin.buffer
    )
    output_protocol = OutputProtocol()
    output_transport, _ = await asyncio.get_running_loop().connect_write_pipe(
        lambda: output_protocol, sys.stdout.buffer
    )
    try:
        async with connect(
            url,
            additional_headers={"Authorization": f"Bearer {token}"},
            max_size=MAX_FRAME_BYTES,
            max_queue=8,
        ) as websocket:

            async def upload() -> None:
                while line := await reader.readline():
                    if len(line) > MAX_FRAME_BYTES:
                        raise ValueError("ACP input exceeds 256 KiB")
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("ACP requires individual JSON-RPC objects")
                    if message.get("method") in {
                        "session/new",
                        "session/load",
                    } and isinstance(message.get("params"), dict):
                        # Hosted profile: no filesystem paths or tools execute on
                        # this computer. The server rejects injected MCP servers.
                        message["params"]["cwd"] = "/app/workspace"
                    await websocket.send(json.dumps(message, separators=(",", ":")))

            async def download() -> None:
                async for frame in websocket:
                    if not isinstance(frame, str):
                        raise ValueError("Expected an ACP text frame")
                    message = json.loads(frame)
                    output = json.dumps(message, separators=(",", ":")) + "\n"
                    output_transport.write(output.encode("utf-8"))
                    await output_protocol.drain()

            tasks = [asyncio.create_task(upload()), asyncio.create_task(download())]
            try:
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        input_transport.close()
        output_transport.close()


def main() -> None:
    url = os.environ.get("CINNA_ACP_URL", "")
    token = os.environ.get("CINNA_ACP_TOKEN", "")
    if not url or not token:
        sys.stderr.write(
            "Set CINNA_ACP_URL and CINNA_ACP_TOKEN before starting the Cinna ACP bridge.\n"
        )
        raise SystemExit(2)
    try:
        asyncio.run(bridge(url, token))
    except KeyboardInterrupt:
        pass
    except Exception as error:
        # Exception details may contain the handshake URL. Neither token nor
        # arbitrary server response headers are printed.
        sys.stderr.write(
            f"Cinna ACP connection failed ({type(error).__name__}). Check the endpoint, token and server.\n"
        )
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
