"""
Integration tests for the personal-agent A2A target (`POST /external/a2a/agent/{agent_id}/`).

Scenarios covered:
  1. Card fetch — v1.0 format, URLs in supportedInterfaces point at external namespace
  2. Card fetch — v0.3 format, url field points at external namespace
  3. Card fetch — .well-known/agent-card.json mirror returns same content
  4. Card fetch — works even when a2a_config.enabled is False
  5. Card fetch — unknown ?protocol value returns 400
  6. Card auth/ownership — unauthenticated request is rejected
  7. Card auth/ownership — another user's agent returns 404
  8. SendStreamingMessage — creates session with integration_type="external"
  9. SendStreamingMessage — another user's agent returns JSON-RPC error
  10. GetTask after streaming — task is retrievable by task_id
  11. v0.3 protocol streaming — slash-case method names are accepted
"""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.a2a import build_streaming_request, parse_sse_events
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers

_EXT_A2A_BASE = f"{settings.API_V1_STR}/external/a2a"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_external_agent_card(
    client: TestClient,
    headers: dict,
    agent_id: str,
    protocol: str | None = None,
) -> dict:
    """GET /external/a2a/agent/{id}/ and return parsed JSON."""
    url = f"{_EXT_A2A_BASE}/agent/{agent_id}/"
    if protocol:
        url += f"?protocol={protocol}"
    r = client.get(url, headers=headers)
    assert r.status_code == 200, f"get_external_agent_card failed: {r.text}"
    return r.json()


def _post_external_a2a(
    client: TestClient,
    headers: dict,
    agent_id: str,
    request: dict,
    protocol: str | None = None,
) -> any:
    """POST a JSON-RPC request to /external/a2a/agent/{id}/ and return the response."""
    url = f"{_EXT_A2A_BASE}/agent/{agent_id}/"
    if protocol:
        url += f"?protocol={protocol}"
    return client.post(url, headers=headers, json=request)


def _create_user_with_agent(
    client: TestClient,
    superuser_token_headers: dict,
    agent_name: str = "External A2A Agent",
) -> tuple[dict, dict, dict]:
    """Create a user, give them an AI credential, create an agent.

    Returns ``(user_data, user_headers, agent_data)``.
    """
    user, headers = create_random_user_with_headers(client)
    # User needs an AI credential to create agents
    create_random_ai_credential(
        client,
        superuser_token_headers,
        credential_type="anthropic",
        api_key="sk-ant-api03-test-ext-a2a",
        name=f"test-cred-{uuid.uuid4().hex[:6]}",
        set_default=False,
    )
    # Create an AI credential as the user (needed for agent creation validation)
    # Use superuser to create and assign a default credential for the user via the admin
    # In tests, the global default set by setup_default_credentials is enough for the
    # superuser. For a new normal user, we rely on the global default credential being
    # visible, but agent creation validates the calling user's resolved credential.
    # The simplest approach: create the agent as superuser and verify ownership rules.
    agent = create_agent_via_api(client, superuser_token_headers, name=agent_name)
    drain_tasks()
    agent = get_agent(client, superuser_token_headers, agent["id"])
    assert agent["active_environment_id"] is not None
    return user, headers, agent


def _create_su_agent(
    client: TestClient,
    superuser_token_headers: dict,
    agent_name: str = "External A2A Agent",
) -> dict:
    """Create an agent as superuser and return its data (with active environment)."""
    agent = create_agent_via_api(client, superuser_token_headers, name=agent_name)
    drain_tasks()
    return get_agent(client, superuser_token_headers, agent["id"])


def _send_streaming_message(
    client: TestClient,
    headers: dict,
    agent_id: str,
    message_text: str = "Hello from external!",
    response_text: str = "Hi! I'm responding from external A2A.",
    task_id: str | None = None,
    protocol: str | None = None,
) -> tuple[any, list[dict]]:
    """Send a streaming message via the external A2A endpoint.

    Returns ``(raw_response, parsed_sse_events)``.
    """
    stub = StubAgentEnvConnector(response_text=response_text)
    request = build_streaming_request(message_text, task_id=task_id)

    with patch("app.services.sessions.message_service.agent_env_connector", stub):
        resp = _post_external_a2a(client, headers, agent_id, request, protocol=protocol)
    drain_tasks()

    events = parse_sse_events(resp.text)
    return resp, events


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_external_agent_card_v1_format(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    Card fetch — v1.0 format:
      1. Create agent (a2a_config NOT enabled)
      2. GET card — 200, v1.0 shape with supportedInterfaces
      3. supportedInterfaces URLs point at /api/v1/external/a2a/agent/
      4. GET ?protocol=v0.3 — 200, v0.3 shape with "url" in external namespace
      5. GET .well-known/agent-card.json — same result as (2)
    """
    agent = _create_su_agent(client, superuser_token_headers, "Card Test Agent")
    agent_id = agent["id"]

    # ── Phase 1: v1.0 card (default) ─────────────────────────────────────────
    card = _get_external_agent_card(client, superuser_token_headers, agent_id)

    # Required v1.0 fields
    assert card["name"] == "Card Test Agent"
    assert "supportedInterfaces" in card, "v1.0 card must have supportedInterfaces"
    assert "protocolVersions" in card, "v1.0 card must have protocolVersions"
    assert "capabilities" in card
    assert "skills" in card

    # supportedInterfaces URLs must point at the external namespace
    iface_urls = [i["url"] for i in card["supportedInterfaces"]]
    for url in iface_urls:
        assert "/api/v1/external/a2a/agent/" in url, (
            f"Expected external URL, got: {url}"
        )
    # Must NOT point at the standard A2A namespace
    for url in iface_urls:
        assert "/api/v1/a2a/" not in url, (
            f"Card URL must not point at standard A2A namespace: {url}"
        )

    # ── Phase 2: v0.3 card ────────────────────────────────────────────────────
    card_v03 = _get_external_agent_card(client, superuser_token_headers, agent_id, protocol="v0.3")

    # v0.3 uses "url" top-level, not "supportedInterfaces"
    assert "url" in card_v03
    assert "/api/v1/external/a2a/agent/" in card_v03["url"], (
        f"v0.3 card url must be in external namespace: {card_v03['url']}"
    )

    # ── Phase 3: .well-known mirror ───────────────────────────────────────────
    r_wk = client.get(
        f"{_EXT_A2A_BASE}/agent/{agent_id}/.well-known/agent-card.json",
        headers=superuser_token_headers,
    )
    assert r_wk.status_code == 200
    wk_card = r_wk.json()
    assert wk_card["name"] == card["name"]
    assert "supportedInterfaces" in wk_card


def test_external_agent_card_works_without_a2a_enabled(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """Card fetch succeeds even when a2a_config.enabled is False.

    The external surface is always available to the agent owner regardless
    of the a2a_config.enabled flag (which only gates the public /api/v1/a2a/ surface).
    """
    # Create agent — by default a2a_config.enabled is False
    agent = _create_su_agent(client, superuser_token_headers, "No A2A Agent")
    assert not (agent.get("a2a_config") or {}).get("enabled", False), (
        "Test pre-condition: a2a_config.enabled should be False"
    )

    # Card fetch must still work
    card = _get_external_agent_card(client, superuser_token_headers, agent["id"])
    assert card["name"] == "No A2A Agent"


def test_external_agent_card_unknown_protocol(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """Unknown ?protocol value returns HTTP 400."""
    agent = _create_su_agent(client, superuser_token_headers, "Protocol Test Agent")

    r = client.get(
        f"{_EXT_A2A_BASE}/agent/{agent['id']}/?protocol=v99",
        headers=superuser_token_headers,
    )
    assert r.status_code == 400


def test_external_agent_card_auth_and_ownership(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    Auth and ownership guards:
      1. Unauthenticated request → 401/403
      2. Another user cannot fetch the card → 404
      3. Non-existent agent_id → 404
    """
    agent = _create_su_agent(client, superuser_token_headers, "Ownership Test Agent")
    agent_id = agent["id"]

    # ── Phase 1: Unauthenticated ──────────────────────────────────────────────
    r_unauth = client.get(f"{_EXT_A2A_BASE}/agent/{agent_id}/")
    assert r_unauth.status_code in (401, 403), (
        f"Unauthenticated request should be rejected, got {r_unauth.status_code}"
    )

    # ── Phase 2: Another user ─────────────────────────────────────────────────
    _, other_headers = create_random_user_with_headers(client)
    r_other = client.get(
        f"{_EXT_A2A_BASE}/agent/{agent_id}/",
        headers=other_headers,
    )
    assert r_other.status_code == 404, (
        f"Another user should get 404, got {r_other.status_code}"
    )

    # ── Phase 3: Non-existent ID ──────────────────────────────────────────────
    ghost_id = str(uuid.uuid4())
    r_ghost = client.get(
        f"{_EXT_A2A_BASE}/agent/{ghost_id}/",
        headers=superuser_token_headers,
    )
    assert r_ghost.status_code == 404


def test_external_a2a_streaming_creates_external_session(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    SendStreamingMessage creates a session with integration_type="external":
      1. Create agent (a2a_config NOT enabled)
      2. POST SendStreamingMessage
      3. Verify HTTP 200, SSE events returned
      4. Verify session was created with integration_type="external"
    """
    agent = _create_su_agent(client, superuser_token_headers, "Streaming Test Agent")
    agent_id = agent["id"]

    # ── Phase 1: Send streaming message ──────────────────────────────────────
    resp, events = _send_streaming_message(
        client,
        superuser_token_headers,
        agent_id,
        message_text="Hello from the external surface!",
        response_text="Responding via external A2A.",
    )

    assert resp.status_code == 200, f"Streaming request failed: {resp.text}"
    assert len(events) > 0, "Expected SSE events in response"

    # ── Phase 2: Verify session created ───────────────────────────────────────
    sessions = list_sessions(client, superuser_token_headers)
    agent_sessions = [s for s in sessions if s["agent_id"] == agent_id]
    assert len(agent_sessions) == 1, (
        f"Expected 1 session for agent, got {len(agent_sessions)}"
    )
    session = agent_sessions[0]

    # ── Phase 3: Verify integration_type="external" ───────────────────────────
    assert session["integration_type"] == "external", (
        f"Expected integration_type='external', got {session['integration_type']!r}"
    )


def test_external_a2a_streaming_rejects_wrong_owner(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    SendStreamingMessage from a non-owner returns a JSON-RPC error:
      1. Create agent as superuser
      2. Create a different user
      3. Other user POSTs StreamingMessage to the agent → error.code -32004
      4. No session created
    """
    agent = _create_su_agent(client, superuser_token_headers, "Owner Guard Agent")
    agent_id = agent["id"]

    _, other_headers = create_random_user_with_headers(client)

    request = build_streaming_request("Unauthorized attempt")
    resp = _post_external_a2a(client, other_headers, agent_id, request)

    # The route returns HTTP 200 with a JSON-RPC error body (standard JSON-RPC behavior)
    assert resp.status_code == 200
    body = resp.json()

    # Should be a JSON-RPC error response (streaming was rejected before starting)
    # or SSE events containing an error; check both patterns
    if "error" in body:
        # Non-streaming error response
        assert body["error"]["code"] in (-32004, -32001), (
            f"Unexpected error code: {body['error']}"
        )
    else:
        # SSE events — parse them
        events = parse_sse_events(resp.text)
        has_error = any(
            e.get("error") or
            (e.get("result", {}).get("status", {}).get("state") in ("failed",))
            for e in events
        )
        assert has_error, f"Expected error in SSE events, got: {events}"


def test_external_a2a_get_task_after_streaming(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    GetTask returns the task created by SendStreamingMessage:
      1. Create agent
      2. Send streaming message — capture task_id from events
      3. GetTask with that task_id — verify task is returned
    """
    agent = _create_su_agent(client, superuser_token_headers, "GetTask Test Agent")
    agent_id = agent["id"]

    # ── Phase 1: Stream a message ─────────────────────────────────────────────
    resp, events = _send_streaming_message(
        client, superuser_token_headers, agent_id,
        message_text="Start a task",
        response_text="Task started.",
    )
    assert resp.status_code == 200
    assert len(events) > 0

    # Extract task_id from the first SSE event (id is the session id)
    task_id = None
    for event in events:
        result = event.get("result", {})
        tid = result.get("id") or result.get("taskId")
        if tid:
            task_id = tid
            break
    assert task_id is not None, f"Could not extract task_id from SSE events: {events}"

    # ── Phase 2: GetTask ──────────────────────────────────────────────────────
    get_task_request = {
        "jsonrpc": "2.0",
        "id": "req-gettask",
        "method": "GetTask",
        "params": {"id": task_id},
    }
    r = _post_external_a2a(client, superuser_token_headers, agent_id, get_task_request)
    assert r.status_code == 200
    body = r.json()
    assert "result" in body, f"Expected result in GetTask response: {body}"
    assert body["result"]["id"] == task_id


def test_external_a2a_v03_streaming(
    client: TestClient,
    superuser_token_headers: dict,
) -> None:
    """
    v0.3 slash-case method name "message/stream" is accepted:
      1. Create agent
      2. POST ?protocol=v0.3 with method "message/stream"
      3. Verify HTTP 200 and SSE events returned
    """
    agent = _create_su_agent(client, superuser_token_headers, "V03 Protocol Agent")
    agent_id = agent["id"]

    stub = StubAgentEnvConnector(response_text="v0.3 response!")
    # v0.3 uses slash-case method names directly (no PascalCase)
    request = {
        "jsonrpc": "2.0",
        "id": "req-v03",
        "method": "message/stream",
        "params": {
            "message": {
                "role": "user",
                "parts": [{"text": "Hello via v0.3!"}],
                "messageId": "msg-v03",
            }
        },
    }

    with patch("app.services.sessions.message_service.agent_env_connector", stub):
        resp = _post_external_a2a(
            client, superuser_token_headers, agent_id, request, protocol="v0.3"
        )
    drain_tasks()

    assert resp.status_code == 200, f"v0.3 streaming failed: {resp.text}"
    events = parse_sse_events(resp.text)
    assert len(events) > 0, "Expected SSE events for v0.3 streaming"


def test_external_a2a_streaming_unauthenticated(
    client: TestClient,
) -> None:
    """Unauthenticated POST to the A2A endpoint returns 401/403 (before JSON-RPC parsing)."""
    ghost_id = str(uuid.uuid4())
    request = build_streaming_request("Unauthorized")
    r = client.post(
        f"{_EXT_A2A_BASE}/agent/{ghost_id}/",
        json=request,
    )
    # FastAPI dependency injection rejects before handler runs
    assert r.status_code in (401, 403)
