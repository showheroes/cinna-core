"""
MCP send_message tool handler integration tests.

Verifies that the MCP tool handler correctly:
  - Creates platform sessions with all required fields
  - Stores user messages and agent responses as SessionMessage records
  - Links sessions to MCP connectors
  - Preserves MCP transport session IDs (mcp_session_id)
  - Preserves external session IDs for multi-turn continuity
  - Reuses existing sessions for subsequent messages
  - Handles MCP session ID changes (client reconnection)

These tests call handle_send_message() directly (not through MCP protocol)
with the agent environment stubbed to return predefined responses.

Uses the same service pipeline as email and A2A integrations:
  - MessageService.create_message for user messages
  - MessageService.stream_message_with_events for agent streaming + storage
  - create_session() (patchable) for all DB access
"""
import asyncio
from unittest.mock import patch

from fastapi.testclient import TestClient

from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.mcp import create_mcp_connector, update_mcp_connector
from tests.utils.message import list_messages, get_messages_by_role
from tests.utils.session import list_sessions


# ── Helpers ──────────────────────────────────────────────────────────────────


def _setup_agent_with_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_name: str = "MCP Send Agent",
    connector_name: str = "Send Connector",
    mode: str = "conversation",
) -> tuple[dict, dict]:
    """Create agent + connector. Returns (agent, connector)."""
    agent = create_agent_via_api(client, token_headers, name=agent_name)
    drain_tasks()
    agent = get_agent(client, token_headers, agent["id"])
    connector = create_mcp_connector(
        client, token_headers, agent["id"],
        name=connector_name, mode=mode,
    )
    return agent, connector


def _find_mcp_sessions(
    client: TestClient,
    token_headers: dict[str, str],
    connector_id: str,
) -> list[dict]:
    """Find sessions linked to a specific MCP connector."""
    sessions = list_sessions(client, token_headers)
    return [s for s in sessions if s.get("mcp_connector_id") == connector_id]


def _run_send_message(
    connector_id: str,
    message: str,
    agent_env_stub: StubAgentEnvConnector,
    mcp_session_id: str | None = None,
) -> str:
    """Call handle_send_message with the standard service pipeline.

    Patches agent_env_connector at the MessageService level (same as A2A tests)
    so that streaming goes through the full MessageService.stream_message_with_events
    pipeline, which stores both user and agent messages in the database.

    Args:
        connector_id: MCP connector UUID string
        message: User message to send
        agent_env_stub: Stub for the agent environment
        mcp_session_id: Optional MCP transport session ID (simulates the
            mcp-session-id header that Claude Desktop sends)
    """
    from app.mcp.tools import handle_send_message
    from app.mcp.server import mcp_connector_id_var, mcp_session_id_var

    async def _run():
        token_conn = mcp_connector_id_var.set(connector_id)
        token_sess = mcp_session_id_var.set(mcp_session_id)
        try:
            return await handle_send_message(message)
        finally:
            mcp_connector_id_var.reset(token_conn)
            mcp_session_id_var.reset(token_sess)

    with patch("app.services.message_service.agent_env_connector", agent_env_stub):
        result = asyncio.run(_run())
    drain_tasks()
    return result


# ── Tests ────────────────────────────────────────────────────────────────────


def test_send_message_creates_session_with_correct_fields(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    First send_message call creates a platform session with correct fields:
      1. Create agent + connector
      2. Call send_message tool with an MCP session ID
      3. Verify session created via API
      4. Check: mcp_connector_id, mcp_session_id, integration_type, mode, status
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Session Fields Agent",
        connector_name="Fields Connector",
        mode="conversation",
    )
    connector_id = connector["id"]

    stub = StubAgentEnvConnector(response_text="Hello from the agent!")
    test_mcp_session_id = "abc123-mcp-session-from-claude-desktop"
    result = _run_send_message(
        connector_id, "Hi there", stub,
        mcp_session_id=test_mcp_session_id,
    )

    # ── Verify tool returned the agent response ──────────────────────────
    assert "Hello from the agent!" in result

    # ── Verify session created via API ───────────────────────────────────
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1, f"Expected 1 MCP session, got {len(mcp_sessions)}"

    session = mcp_sessions[0]
    assert session["mcp_connector_id"] == connector_id
    assert session["integration_type"] == "mcp"
    assert session["mode"] == "conversation"
    assert session["status"] == "active"
    assert session["agent_id"] == agent["id"]
    assert session["user_id"] is not None
    # MCP transport session ID should be stored
    assert session["mcp_session_id"] == test_mcp_session_id, (
        f"mcp_session_id not stored: got {session.get('mcp_session_id')!r}"
    )


def test_send_message_stores_user_and_agent_messages(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    send_message should store both the user message and the agent response
    as SessionMessage records (same as email/web-UI integrations):
      1. Create agent + connector
      2. Call send_message tool with a user message
      3. Verify user message stored (role="user")
      4. Verify agent response stored (role="agent")
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Message Storage Agent",
    )
    connector_id = connector["id"]

    stub = StubAgentEnvConnector(response_text="I can help with that!")
    result = _run_send_message(connector_id, "Please help me", stub)
    assert "I can help with that!" in result

    # ── Find the session ─────────────────────────────────────────────────
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1
    session_id = mcp_sessions[0]["id"]

    # ── Verify messages stored ───────────────────────────────────────────
    messages = list_messages(client, superuser_token_headers, session_id)
    assert len(messages) >= 2, (
        f"Expected at least 2 messages (user + agent), got {len(messages)}: {messages}"
    )

    user_msgs = get_messages_by_role(client, superuser_token_headers, session_id, "user")
    assert len(user_msgs) >= 1, "No user message stored"
    assert user_msgs[0]["content"] == "Please help me"

    agent_msgs = get_messages_by_role(client, superuser_token_headers, session_id, "agent")
    assert len(agent_msgs) >= 1, "No agent message stored"
    assert "I can help with that!" in agent_msgs[0]["content"]


def test_send_message_reuses_existing_session(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    Subsequent send_message calls reuse the existing session:
      1. Call send_message twice on the same connector with the same MCP session ID
      2. Verify only one session exists
      3. Verify both message exchanges are in the same session
      4. Verify mcp_session_id is preserved
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Session Reuse Agent",
    )
    connector_id = connector["id"]
    mcp_sid = "reuse-test-mcp-session-id"

    # First message
    stub1 = StubAgentEnvConnector(response_text="First response")
    _run_send_message(connector_id, "First message", stub1, mcp_session_id=mcp_sid)

    # Second message (same MCP session)
    stub2 = StubAgentEnvConnector(response_text="Second response")
    _run_send_message(connector_id, "Second message", stub2, mcp_session_id=mcp_sid)

    # ── Verify single session ────────────────────────────────────────────
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1, (
        f"Expected 1 session (reused), got {len(mcp_sessions)}"
    )

    session = mcp_sessions[0]
    session_id = session["id"]
    assert session["mcp_session_id"] == mcp_sid

    # ── Verify all messages in same session ──────────────────────────────
    messages = list_messages(client, superuser_token_headers, session_id)
    # Should have messages from both exchanges
    user_msgs = [m for m in messages if m["role"] == "user"]
    agent_msgs = [m for m in messages if m["role"] == "agent"]
    assert len(user_msgs) >= 2, f"Expected 2 user messages, got {len(user_msgs)}"
    assert len(agent_msgs) >= 2, f"Expected 2 agent messages, got {len(agent_msgs)}"


def test_send_message_reuses_session_after_stream_completed(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    Reproduce the production bug: STREAM_COMPLETED event sets session status
    to "completed", causing the next send_message to create a new session
    instead of reusing the existing one.

    Simulates what handle_stream_completed does in production:
      1. Send first message → session created with status "active"
      2. Simulate STREAM_COMPLETED: set session status to "completed"
         (this is what the event handler does for non-integration sessions)
      3. Call handle_stream_completed with integration_type check
      4. Verify MCP session stays "active"
      5. Send second message → should reuse the same session
    """
    from uuid import UUID
    from app.models import Session

    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Stream Completed Agent",
    )
    connector_id = connector["id"]
    mcp_sid = "stream-completed-test"

    # ── Phase 1: First message ───────────────────────────────────────────
    stub1 = StubAgentEnvConnector(response_text="First response")
    _run_send_message(connector_id, "Hello", stub1, mcp_session_id=mcp_sid)

    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1
    session_id = mcp_sessions[0]["id"]
    assert mcp_sessions[0]["status"] == "active"

    # ── Phase 2: Simulate what STREAM_COMPLETED does in production ───────
    # In production, handle_stream_completed sets status = "completed" for
    # non-integration sessions. With our fix, MCP sessions should stay
    # "active". We test the fix by calling handle_stream_completed directly.
    from app.services.session_service import SessionService
    event_data = {
        "meta": {
            "session_id": session_id,
            "was_interrupted": False,
        }
    }
    # Patch create_session() to use the test DB session
    with patch("app.services.session_service.create_session", return_value=db):
        with patch.object(db, "close", lambda: None):
            asyncio.run(SessionService.handle_stream_completed(event_data))
    drain_tasks()

    # ── Phase 3: Verify MCP session stayed "active" ──────────────────────
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1
    assert mcp_sessions[0]["status"] == "active", (
        f"MCP session should stay 'active' after STREAM_COMPLETED, "
        f"got '{mcp_sessions[0]['status']}'"
    )

    # ── Phase 4: Second message should reuse the same session ────────────
    stub2 = StubAgentEnvConnector(response_text="Second response")
    _run_send_message(connector_id, "Still here", stub2, mcp_session_id=mcp_sid)

    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1, (
        f"Expected 1 session (reused after STREAM_COMPLETED), got {len(mcp_sessions)}"
    )
    messages = list_messages(client, superuser_token_headers, session_id)
    user_msgs = [m for m in messages if m["role"] == "user"]
    assert len(user_msgs) >= 2, f"Expected 2 user messages in same session, got {len(user_msgs)}"


def test_send_message_session_reuse_after_mcp_session_change(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    When the MCP transport session ID changes (client reconnected), a new
    platform session is created — there is no connector-based fallback.
      1. Send first message with mcp_session_id "session-A"
      2. Send second message with mcp_session_id "session-B" (client reconnected)
      3. Verify 2 separate platform sessions exist
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Reconnect Agent",
    )
    connector_id = connector["id"]

    # First message with session-A
    stub1 = StubAgentEnvConnector(response_text="First response")
    _run_send_message(connector_id, "Hello", stub1, mcp_session_id="session-A")

    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1
    assert mcp_sessions[0]["mcp_session_id"] == "session-A"

    # Second message with session-B (simulates Claude Desktop reconnecting)
    stub2 = StubAgentEnvConnector(response_text="Second response")
    _run_send_message(connector_id, "Still here", stub2, mcp_session_id="session-B")

    # ── Different mcp_session_id → different platform session ────────────
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 2, (
        f"Expected 2 sessions after reconnect with new mcp_session_id, got {len(mcp_sessions)}"
    )
    session_ids_by_mcp = {s["mcp_session_id"]: s["id"] for s in mcp_sessions}
    assert "session-A" in session_ids_by_mcp
    assert "session-B" in session_ids_by_mcp


def test_send_message_without_mcp_session_id(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    When no MCP session ID is provided, each message creates a new
    platform session — there is no connector-based fallback.
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="No Session ID Agent",
    )
    connector_id = connector["id"]

    # First message without MCP session ID
    stub1 = StubAgentEnvConnector(response_text="First")
    _run_send_message(connector_id, "Hello", stub1, mcp_session_id=None)

    # Second message also without MCP session ID
    stub2 = StubAgentEnvConnector(response_text="Second")
    _run_send_message(connector_id, "Again", stub2, mcp_session_id=None)

    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 2, (
        f"Expected 2 sessions without mcp_session_id, got {len(mcp_sessions)}"
    )
    # mcp_session_id should be null on both since none was provided
    for s in mcp_sessions:
        assert s["mcp_session_id"] is None


def test_send_message_preserves_external_session_id(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    External session ID from agent environment is stored in session metadata:
      1. Call send_message with stub that returns session_created event
      2. Verify external_session_id appears in session metadata
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="External Session Agent",
    )
    connector_id = connector["id"]

    stub = StubAgentEnvConnector(response_text="Hello!")
    _run_send_message(connector_id, "Hello", stub)

    # The stub's build_simple_response_events includes a session_created event
    # with a UUID as session_id. Verify it was stored.
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1

    session = mcp_sessions[0]
    # external_session_id should be populated from the session_created event
    assert session.get("external_session_id") is not None, (
        "external_session_id not set — session_created event from agent env not captured"
    )


def test_send_message_inactive_connector_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """send_message on an inactive connector returns error."""
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Inactive Send Agent",
    )
    connector_id = connector["id"]
    agent_id = agent["id"]

    # Deactivate
    update_mcp_connector(
        client, superuser_token_headers, agent_id, connector_id,
        is_active=False,
    )

    stub = StubAgentEnvConnector(response_text="Should not reach")
    result = _run_send_message(connector_id, "Hello", stub)

    assert "error" in result.lower()
    assert "inactive" in result.lower() or "not found" in result.lower()

    # No session should have been created
    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 0


def test_send_message_agent_response_metadata(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    Agent response message should include streaming metadata:
      1. Call send_message
      2. Verify agent message has metadata with external_session_id and
         streaming_events
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Metadata Agent",
    )
    connector_id = connector["id"]

    stub = StubAgentEnvConnector(response_text="Response with metadata")
    _run_send_message(connector_id, "Check metadata", stub)

    mcp_sessions = _find_mcp_sessions(client, superuser_token_headers, connector_id)
    assert len(mcp_sessions) == 1
    session_id = mcp_sessions[0]["id"]

    agent_msgs = get_messages_by_role(
        client, superuser_token_headers, session_id, "agent",
    )
    assert len(agent_msgs) >= 1

    meta = agent_msgs[0].get("message_metadata") or {}
    assert "external_session_id" in meta, (
        f"Expected external_session_id in metadata, got keys: {list(meta.keys())}"
    )
    assert "streaming_events" in meta, (
        f"Expected streaming_events in metadata, got keys: {list(meta.keys())}"
    )
    assert meta.get("streaming_in_progress") is False, (
        "streaming_in_progress should be False after stream completes"
    )
