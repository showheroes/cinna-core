"""Pure bridge URL validation and async pipe backpressure; no database or HTTP."""

import asyncio
import importlib.util
from pathlib import Path

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "clients" / "acp" / "stdio_bridge.py"
)
_spec = importlib.util.spec_from_file_location("cinna_acp_stdio_bridge", _MODULE_PATH)
assert _spec and _spec.loader
bridge = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bridge)


@pytest.mark.parametrize(
    "url",
    [
        "wss://cinna.example/acp/id",
        "ws://localhost:8000/acp/id",
        "ws://127.0.0.1/acp/id",
        "ws://[::1]/acp/id",
    ],
)
def test_bridge_accepts_tls_or_loopback(url):
    bridge.validate_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ws://cinna.example/acp/id",
        "https://cinna.example/acp/id",
        "wss://user:secret@cinna.example/acp/id",
        "wss://cinna.example/acp/id?token=secret",
        "wss://cinna.example/acp/id#token",
        "wss:///acp/id",
    ],
)
def test_bridge_rejects_insecure_or_credential_bearing_urls(url):
    with pytest.raises(ValueError):
        bridge.validate_url(url)


def test_stdout_backpressure_yields_and_resumes_without_blocking_event_loop():
    async def run():
        output = bridge.OutputProtocol()
        output.pause_writing()
        waiter = asyncio.create_task(output.drain())
        await asyncio.sleep(0)
        assert not waiter.done()
        output.resume_writing()
        await asyncio.wait_for(waiter, timeout=1)
        output.connection_lost(None)
        with pytest.raises(BrokenPipeError):
            await output.drain()

    asyncio.run(run())
