"""ACP journeys through the real mounted WebSocket and owner REST APIs."""

import asyncio
import json
import time
from unittest.mock import AsyncMock, patch

import pytest
from acp import connect_to_agent
from acp.exceptions import RequestError
from acp.schema import TextContentBlock
from starlette.websockets import WebSocketDisconnect

from app.acp.agent import CinnaACPAgent
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.acp import acp_connector_url, create_acp_connector, create_acp_token
from tests.utils.acp_runtime import acp_prompt_slots, acp_runtime_counts
from tests.utils.agent import create_agent_via_api
from tests.utils.background_tasks import drain_tasks
from tests.utils.message import list_messages
from tests.utils.session import get_session


def setup_acp_client(client, headers, **fields):
    agent = create_agent_via_api(client, headers)
    drain_tasks()
    connector = create_acp_connector(client, headers, agent["id"], **fields)
    token = create_acp_token(client, headers, agent["id"], connector["id"])
    return agent, connector, token


def socket(client, connector, token):
    return client.websocket_connect(
        f"/acp/{connector['id']}", headers={"Authorization": f"Bearer {token['token']}"}
    )


def rpc(ws, method, params, request_id=1):
    ws.send_json(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    )
    updates = []
    while True:
        result = ws.receive_json()
        if result.get("id") == request_id:
            return result, updates
        assert result["method"] == "session/update"
        updates.append(result["params"]["update"])


def initialize(ws):
    result, _ = rpc(ws, "initialize", {"protocolVersion": 1, "clientCapabilities": {}})
    assert result["result"]["protocolVersion"] == 1
    assert result["result"]["agentCapabilities"]["loadSession"] is True
    return result


def new_session(ws):
    result, _ = rpc(ws, "session/new", {"cwd": "/app/workspace", "mcpServers": []})
    assert "result" in result, result
    return result["result"]["sessionId"]


def test_remote_prompt_persists_and_reconnect_replays_history(
    client, superuser_token_headers
):
    agent, connector, token = setup_acp_client(client, superuser_token_headers)
    stub = StubAgentEnvConnector(response_text="Hello ACP")
    with patch("app.services.sessions.message_service.agent_env_connector", stub):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)
            result, updates = rpc(
                ws,
                "session/prompt",
                {"sessionId": sid, "prompt": [{"type": "text", "text": "Hello Cinna"}]},
                request_id="turn",
            )
            assert result["result"]["stopReason"] == "end_turn", result
            assert "Hello ACP" == "".join(
                u["content"]["text"]
                for u in updates
                if u["sessionUpdate"] == "agent_message_chunk"
            )
        with socket(client, connector, token) as ws:
            initialize(ws)
            result, history = rpc(
                ws,
                "session/load",
                {"sessionId": sid, "cwd": "/app/workspace", "mcpServers": []},
            )
            assert "result" in result, result
            assert [(u["sessionUpdate"], u["content"]["text"]) for u in history] == [
                ("user_message_chunk", "Hello Cinna"),
                ("agent_message_chunk", "Hello ACP"),
            ]
    session = get_session(client, superuser_token_headers, sid)
    assert session["integration_type"] == "acp"
    assert session["agent_id"] == agent["id"]
    assert session["interaction_status"] == ""
    messages = list_messages(client, superuser_token_headers, sid)
    assert any(m["content"] == "Hello Cinna" for m in messages)


def test_token_scope_and_live_revocation(client, superuser_token_headers):
    agent, connector, token = setup_acp_client(client, superuser_token_headers)
    second = create_acp_token(
        client, superuser_token_headers, agent["id"], connector["id"]
    )
    with socket(client, connector, token) as ws:
        initialize(ws)
        sid = new_session(ws)
        for alias in (sid.upper(), sid.replace("-", "")):
            result, _ = rpc(
                ws,
                "session/load",
                {"sessionId": alias, "cwd": "/app/workspace", "mcpServers": []},
            )
            assert result["error"]["code"] == -32002
        with socket(client, connector, second) as other:
            initialize(other)
            result, _ = rpc(
                other,
                "session/load",
                {"sessionId": sid, "cwd": "/app/workspace", "mcpServers": []},
            )
            assert result["error"]["code"] == -32002
        revoked = client.delete(
            f"{acp_connector_url(agent['id'], connector['id'])}/tokens/{token['id']}",
            headers=superuser_token_headers,
        )
        assert revoked.status_code == 200, revoked.text
        result, _ = rpc(ws, "session/new", {"cwd": "/app/workspace", "mcpServers": []})
        assert result["error"]["code"] == -32000
    with pytest.raises(WebSocketDisconnect):
        with socket(client, connector, token):
            pass


@pytest.mark.parametrize(
    "params",
    [
        {"cwd": "/tmp/client", "mcpServers": []},
        {
            "cwd": "/app/workspace",
            "mcpServers": [
                {"name": "injected", "command": "sh", "args": [], "env": []}
            ],
        },
        {"cwd": "/app/workspace", "mcpServers": [], "additionalDirectories": ["/tmp"]},
    ],
)
def test_restricted_remote_context_is_explicit(client, superuser_token_headers, params):
    _, connector, token = setup_acp_client(client, superuser_token_headers)
    with socket(client, connector, token) as ws:
        result, _ = rpc(ws, "session/new", {"cwd": "/app/workspace", "mcpServers": []})
        assert result["error"]["code"] == -32003
        initialize(ws)
        result, _ = rpc(ws, "session/new", params)
        assert result["error"]["code"] == -32602
        sid = new_session(ws)
        result, _ = rpc(
            ws,
            "session/prompt",
            {
                "sessionId": sid,
                "prompt": [{"type": "image", "data": "AA==", "mimeType": "image/png"}],
            },
        )
        assert result["error"]["code"] == -32602
        result, _ = rpc(
            ws, "session/set_mode", {"sessionId": sid, "modeId": "building"}
        )
        assert result["error"]["code"] == -32601


def test_bad_frames_origin_and_connection_capacity(client, superuser_token_headers):
    _, connector, token = setup_acp_client(
        client, superuser_token_headers, max_connections=1
    )
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            f"/acp/{connector['id']}",
            headers={
                "Authorization": f"Bearer {token['token']}",
                "Origin": "https://evil.example",
            },
        ):
            pass
    with socket(client, connector, token) as ws:
        with pytest.raises(WebSocketDisconnect):
            with socket(client, connector, token):
                pass
        ws.send_text("{")
        assert ws.receive_json()["error"]["code"] == -32700
        ws.send_json([])
        assert ws.receive_json()["error"]["code"] == -32600
        initialize(ws)
        ws.send_text("x" * (256 * 1024 + 1))
        with pytest.raises(WebSocketDisconnect) as closed:
            ws.receive_json()
        assert closed.value.code == 1009


class SlowAgent(StubAgentEnvConnector):
    async def stream_chat(self, base_url, auth_headers, payload):
        self.stream_calls.append({"payload": payload})
        yield {
            "type": "session_created",
            "session_id": "remote-session",
            "content": "",
            "metadata": {},
        }
        yield {"type": "assistant", "content": "Working", "metadata": {}}
        await asyncio.sleep(3600)


def test_cancel_forwards_interrupt_and_releases_session(
    client, superuser_token_headers
):
    _, connector, token = setup_acp_client(client, superuser_token_headers)
    with (
        patch("app.services.sessions.message_service.agent_env_connector", SlowAgent()),
        patch(
            "app.services.sessions.message_service.MessageService.forward_interrupt_to_environment",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as interrupt,
    ):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid,
                        "prompt": [{"type": "text", "text": "Work"}],
                    },
                }
            )
            assert ws.receive_json()["params"]["update"]["content"]["text"] == "Working"
            with socket(client, connector, token) as other:
                initialize(other)
                result, _ = rpc(
                    other,
                    "session/load",
                    {"cwd": "/app/workspace", "sessionId": sid, "mcpServers": []},
                )
                assert result["error"]["code"] == -32006
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "method": "session/cancel",
                    "params": {"sessionId": sid},
                }
            )
            result = ws.receive_json()
            assert result["id"] == "prompt"
            assert result["result"]["stopReason"] == "cancelled"
            interrupt.assert_awaited_once()
            assert (
                interrupt.await_args.kwargs["external_session_id"] == "remote-session"
            )
    session = get_session(client, superuser_token_headers, sid)
    assert session["interaction_status"] == ""
    messages = list_messages(client, superuser_token_headers, sid)
    partial = next(m for m in messages if m["role"] == "agent")
    assert partial["content"] == "Working"
    assert partial["message_metadata"]["streaming_in_progress"] is False
    assert partial["status"] == "user_interrupted"


def test_official_sdk_client_interoperates_with_remote_transport(
    client, superuser_token_headers
):
    _, connector, token = setup_acp_client(client, superuser_token_headers)
    updates = []

    class Client:
        async def session_update(self, session_id, update, **kwargs):
            updates.append(update)

    class Transport:
        def __init__(self, ws):
            self.ws = ws

        async def send(self, message):
            self.ws.send_json(message)

        async def receive(self):
            try:
                future = self.ws.portal.start_task_soon(self.ws._send_rx.receive)
                message = await asyncio.wait_for(
                    asyncio.wrap_future(future), timeout=10
                )
                if message["type"] == "websocket.close":
                    return None
                return json.loads(message["text"])
            except WebSocketDisconnect:
                return None

        async def close(self):
            self.ws.close()

    async def drive(ws):
        connection = connect_to_agent(Client(), Transport(ws))
        try:
            initialized = await connection.initialize(protocol_version=1)
            assert initialized.agent_capabilities.load_session is True
            session = await connection.new_session(cwd="/app/workspace", mcp_servers=[])
            response = await connection.prompt(
                session_id=session.session_id,
                prompt=[TextContentBlock(type="text", text="SDK client")],
            )
            assert response.stop_reason == "end_turn"
        finally:
            await connection.close()

    with patch(
        "app.services.sessions.message_service.agent_env_connector",
        StubAgentEnvConnector(response_text="SDK works"),
    ):
        with socket(client, connector, token) as ws:
            asyncio.run(asyncio.wait_for(drive(ws), timeout=20))
    assert any(
        getattr(getattr(u, "content", None), "text", "") == "SDK works" for u in updates
    )


def test_silent_running_prompt_is_interrupted_after_revocation(
    client, superuser_token_headers
):
    agent, connector, token = setup_acp_client(client, superuser_token_headers)
    with (
        patch("app.services.sessions.message_service.agent_env_connector", SlowAgent()),
        patch(
            "app.services.sessions.message_service.MessageService.forward_interrupt_to_environment",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as interrupt,
        patch("app.acp.agent.AUTH_CHECK_INTERVAL", 0.02),
    ):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid,
                        "prompt": [{"type": "text", "text": "Work"}],
                    },
                }
            )
            assert ws.receive_json()["params"]["update"]["content"]["text"] == "Working"
            response = client.post(
                f"{acp_connector_url(agent['id'], connector['id'])}/tokens/{token['id']}/revoke",
                headers=superuser_token_headers,
            )
            assert response.status_code == 200
            result = ws.receive_json()
            assert result["id"] == "prompt"
            assert result["error"]["code"] == -32000
            interrupt.assert_awaited_once()


def test_disconnect_interrupts_remote_execution(client, superuser_token_headers):
    _, connector, token = setup_acp_client(client, superuser_token_headers)
    with (
        patch("app.services.sessions.message_service.agent_env_connector", SlowAgent()),
        patch(
            "app.services.sessions.message_service.MessageService.forward_interrupt_to_environment",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ) as interrupt,
    ):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid,
                        "prompt": [{"type": "text", "text": "Work"}],
                    },
                }
            )
            assert ws.receive_json()["params"]["update"]["content"]["text"] == "Working"
        interrupt.assert_awaited_once()
    assert get_session(client, superuser_token_headers, sid)["interaction_status"] == ""
    assert acp_runtime_counts() == {
        "connections": 0,
        "tasks": 0,
        "admitted": 0,
        "prompts": 0,
    }


def test_stream_tool_ids_thoughts_and_runtime_interrupt_map_to_acp(
    client, superuser_token_headers
):
    _, connector, token = setup_acp_client(client, superuser_token_headers)
    stub = StubAgentEnvConnector(
        events=[
            {
                "type": "session_created",
                "session_id": "tool-session",
                "content": "",
                "metadata": {},
            },
            {"type": "thinking", "content": "Considering", "metadata": {}},
            {
                "type": "tool",
                "tool_name": "read_file",
                "content": "Reading",
                "metadata": {
                    "tool_id": "tool-actual",
                    "tool_input": {"path": "/app/workspace/README.md"},
                },
            },
            {
                "type": "tool_result",
                "content": "Denied",
                "metadata": {"tool_id": "tool-actual", "is_error": True},
            },
            {"type": "assistant", "content": "Stopping", "metadata": {}},
            {"type": "interrupted", "content": "Interrupted", "metadata": {}},
        ]
    )
    with patch("app.services.sessions.message_service.agent_env_connector", stub):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)
            result, updates = rpc(
                ws,
                "session/prompt",
                {"sessionId": sid, "prompt": [{"type": "text", "text": "Inspect"}]},
            )
    assert result["result"]["stopReason"] == "cancelled", result
    assert any(u["sessionUpdate"] == "agent_thought_chunk" for u in updates)
    tool = next(u for u in updates if u["sessionUpdate"] == "tool_call")
    assert tool["toolCallId"] == "tool-actual"
    assert tool["title"] == "read_file"
    assert any(
        u["sessionUpdate"] == "tool_call_update" and u["status"] == "failed"
        for u in updates
    )


def test_watchdog_tolerates_transient_failure_but_stops_real_auth_failure(
    client, superuser_token_headers
):
    """
    F3: ``watch_prompt`` must tell a transient infrastructure blip apart from a
    real authorization failure.

      1. A single unexpected (non-``RequestError``) exception from the
         watchdog's authorization check must not kill a live prompt — the
         turn is still alive afterwards and resolves normally on a
         client-initiated cancel.
      2. A real ``RequestError`` (revoked/expired/deactivated token) must
         still stop the turn on its very first occurrence — the security
         property ``029fb77b`` introduced must not regress.
    """
    real_session = CinnaACPAgent.session
    inject: dict[str, str | None] = {"kind": None}

    def flaky_session(self, db, session_id):
        kind = inject["kind"]
        if kind is not None:
            inject["kind"] = None
            if kind == "transient":
                raise RuntimeError("simulated transient DB blip")
            raise RequestError.auth_required()
        return real_session(self, db, session_id)

    agent, connector, token = setup_acp_client(client, superuser_token_headers)
    with (
        patch("app.services.sessions.message_service.agent_env_connector", SlowAgent()),
        patch(
            "app.services.sessions.message_service.MessageService.forward_interrupt_to_environment",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.acp.agent.AUTH_CHECK_INTERVAL", 0.02),
        patch.object(CinnaACPAgent, "session", flaky_session),
    ):
        with socket(client, connector, token) as ws:
            initialize(ws)
            sid = new_session(ws)

            # ── Phase 1: one transient exception does not kill the turn ────
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt1",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid,
                        "prompt": [{"type": "text", "text": "Work"}],
                    },
                }
            )
            assert ws.receive_json()["params"]["update"]["content"]["text"] == "Working"
            inject["kind"] = "transient"
            # >> the patched AUTH_CHECK_INTERVAL: gives the watchdog several
            # cycles to pick the failure up and tolerate it.
            time.sleep(0.2)
            assert inject["kind"] is None, (
                "watchdog never consumed the injected failure — this test "
                "would pass vacuously without AUTH_CHECK_INTERVAL actually firing"
            )
            # The turn is still alive: a client-initiated cancel resolves it
            # normally instead of racing an unsolicited watchdog error that
            # would already be sitting on the socket if the blip had killed it.
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "method": "session/cancel",
                    "params": {"sessionId": sid},
                }
            )
            result = ws.receive_json()
            assert result["id"] == "prompt1"
            assert "result" in result, result
            assert result["result"]["stopReason"] == "cancelled"

            # ── Phase 2: a real auth failure stops the turn immediately ────
            sid2 = new_session(ws)
            ws.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt2",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid2,
                        "prompt": [{"type": "text", "text": "Work"}],
                    },
                }
            )
            assert ws.receive_json()["params"]["update"]["content"]["text"] == "Working"
            inject["kind"] = "auth"
            result = ws.receive_json()
            assert result["id"] == "prompt2"
            assert result["error"]["code"] == -32000, result


def test_per_connector_prompt_quota_isolates_tenants(client, superuser_token_headers):
    """
    F4: ``MAX_ACTIVE_PROMPTS_PER_CONNECTOR`` bounds each connector's admitted
    prompts independently of the global cap, so one connector saturating its
    own sub-quota must not lock out a different connector.
    """
    agent, connector_a, token_a = setup_acp_client(client, superuser_token_headers)
    connector_b = create_acp_connector(client, superuser_token_headers, agent["id"])
    token_b = create_acp_token(
        client, superuser_token_headers, agent["id"], connector_b["id"]
    )
    with (
        patch("app.services.sessions.message_service.agent_env_connector", SlowAgent()),
        patch(
            "app.services.sessions.message_service.MessageService.forward_interrupt_to_environment",
            new_callable=AsyncMock,
            return_value={"status": "ok"},
        ),
        patch("app.acp.agent.MAX_ACTIVE_PROMPTS_PER_CONNECTOR", 1),
    ):
        with socket(client, connector_a, token_a) as ws_a1:
            initialize(ws_a1)
            sid_a1 = new_session(ws_a1)
            ws_a1.send_json(
                {
                    "jsonrpc": "2.0",
                    "id": "prompt_a1",
                    "method": "session/prompt",
                    "params": {
                        "sessionId": sid_a1,
                        "prompt": [{"type": "text", "text": "Work A1"}],
                    },
                }
            )
            assert (
                ws_a1.receive_json()["params"]["update"]["content"]["text"]
                == "Working"
            )

            # ── A second prompt on the SAME connector is rejected: its own
            #    sub-quota (patched to 1) is already saturated. ─────────────
            with socket(client, connector_a, token_a) as ws_a2:
                initialize(ws_a2)
                sid_a2 = new_session(ws_a2)
                result, _ = rpc(
                    ws_a2,
                    "session/prompt",
                    {
                        "sessionId": sid_a2,
                        "prompt": [{"type": "text", "text": "Work A2"}],
                    },
                )
                assert result["error"]["code"] == -32004, result
                assert "Connector" in result["error"]["message"], result

            # ── A different connector is unaffected: it can still admit. ────
            with socket(client, connector_b, token_b) as ws_b:
                initialize(ws_b)
                sid_b = new_session(ws_b)
                ws_b.send_json(
                    {
                        "jsonrpc": "2.0",
                        "id": "prompt_b",
                        "method": "session/prompt",
                        "params": {
                            "sessionId": sid_b,
                            "prompt": [{"type": "text", "text": "Work B"}],
                        },
                    }
                )
                assert (
                    ws_b.receive_json()["params"]["update"]["content"]["text"]
                    == "Working"
                )

                # Both connectors' admissions are visible at once — asserted
                # as a whole dict (not a single key) so a typo'd connector id
                # or an unrelated key can't pass vacuously against the
                # ``Counter``'s zero-default.
                assert acp_prompt_slots() == {
                    str(connector_a["id"]): 1,
                    str(connector_b["id"]): 1,
                }
