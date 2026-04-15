"""
Integration tests for the prompt_examples field on AppAgentRoute and IdentityAgentBinding.

Covers:
  1. AppAgentRoute prompt_examples lifecycle — create with value, update, null default
  2. AppAgentRoute prompt_examples validation — >2000 chars, >10 non-empty lines → 422
  3. IdentityAgentBinding prompt_examples lifecycle — create with value, update
  4. IdentityAgentBinding prompt_examples validation — >2000 chars, >10 lines → 422
"""

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.background_tasks import drain_tasks
from tests.utils.identity import create_identity_binding, update_identity_binding
from tests.utils.utils import random_lower_string

_BINDINGS = f"{settings.API_V1_STR}/identity/bindings"


def _agent_routes_base(agent_id: str) -> str:
    return f"{settings.API_V1_STR}/agents/{agent_id}/app-mcp-routes"


def _create_agent_route(
    client: TestClient,
    headers: dict,
    agent_id: str,
    *,
    prompt_examples: str | None = None,
) -> "requests.Response":  # type: ignore[name-defined]
    payload: dict = {
        "name": f"route-{random_lower_string()[:8]}",
        "agent_id": agent_id,
        "trigger_prompt": f"Handle {random_lower_string()[:8]} tasks",
        "session_mode": "conversation",
        "auto_enable_for_users": False,
        "assigned_user_ids": [],
    }
    if prompt_examples is not None:
        payload["prompt_examples"] = prompt_examples
    return client.post(_agent_routes_base(agent_id) + "/", headers=headers, json=payload)


# ---------------------------------------------------------------------------
# Scenario 1: AppAgentRoute — prompt_examples lifecycle
# ---------------------------------------------------------------------------


def test_app_agent_route_prompt_examples_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    prompt_examples lifecycle for AppAgentRoute:
      1. Create agent
      2. Create route without prompt_examples — field is null in response
      3. Create route with prompt_examples — field is saved and returned
      4. Update route to set prompt_examples — update persists
      5. Update route to clear prompt_examples (set to null) — cleared
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Route PE Agent")
    drain_tasks()
    agent_id = agent["id"]
    base = _agent_routes_base(agent_id)

    # ── Phase 2: Create without prompt_examples — null ────────────────────
    r = _create_agent_route(client, superuser_token_headers, agent_id)
    assert r.status_code == 200, r.text
    route_no_pe = r.json()
    assert route_no_pe["prompt_examples"] is None

    # ── Phase 3: Create with prompt_examples ──────────────────────────────
    examples = "Schedule a meeting\nSummarize my emails\nFind a contact"
    r = _create_agent_route(
        client, superuser_token_headers, agent_id, prompt_examples=examples
    )
    assert r.status_code == 200, r.text
    route_with_pe = r.json()
    route_id = route_with_pe["id"]
    assert route_with_pe["prompt_examples"] == examples

    # ── Phase 4: Update to change prompt_examples ─────────────────────────
    updated_examples = "Check my calendar\nBook a flight"
    r_update = client.put(
        f"{base}/{route_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": updated_examples},
    )
    assert r_update.status_code == 200, r_update.text
    assert r_update.json()["prompt_examples"] == updated_examples

    # ── Phase 5: Clear prompt_examples by setting to null ────────────────
    r_clear = client.put(
        f"{base}/{route_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": None},
    )
    assert r_clear.status_code == 200, r_clear.text
    assert r_clear.json()["prompt_examples"] is None


# ---------------------------------------------------------------------------
# Scenario 2: AppAgentRoute — prompt_examples validation
# ---------------------------------------------------------------------------


def test_app_agent_route_prompt_examples_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Validation rules for AppAgentRoute.prompt_examples:
      1. Create agent
      2. prompt_examples > 2000 characters on POST → 422
      3. prompt_examples > 10 non-empty lines on POST → 422
      4. Exactly 10 non-empty lines → 200 (boundary: allowed)
      5. prompt_examples > 2000 characters on PUT → 422
      6. prompt_examples > 10 non-empty lines on PUT → 422
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Route PE Validation Agent")
    drain_tasks()
    agent_id = agent["id"]
    base = _agent_routes_base(agent_id)

    # ── Phase 2: > 2000 chars on POST → 422 ──────────────────────────────
    too_long = "a" * 2001
    r = _create_agent_route(
        client, superuser_token_headers, agent_id, prompt_examples=too_long
    )
    assert r.status_code == 422, f"Expected 422 for >2000 chars, got {r.status_code}: {r.text}"
    assert "2000" in r.json()["detail"] or "characters" in r.json()["detail"].lower()

    # ── Phase 3: > 10 non-empty lines on POST → 422 ───────────────────────
    eleven_lines = "\n".join(f"Example {i}" for i in range(11))
    r = _create_agent_route(
        client, superuser_token_headers, agent_id, prompt_examples=eleven_lines
    )
    assert r.status_code == 422, f"Expected 422 for >10 lines, got {r.status_code}: {r.text}"
    assert "10" in r.json()["detail"] or "example" in r.json()["detail"].lower()

    # ── Phase 4: Exactly 10 non-empty lines → 200 (boundary) ─────────────
    ten_lines = "\n".join(f"Example {i}" for i in range(10))
    r = _create_agent_route(
        client, superuser_token_headers, agent_id, prompt_examples=ten_lines
    )
    assert r.status_code == 200, f"Expected 200 for exactly 10 lines, got {r.status_code}: {r.text}"
    route_id = r.json()["id"]
    assert r.json()["prompt_examples"] == ten_lines

    # ── Phase 5: PUT with > 2000 chars → 422 ─────────────────────────────
    r = client.put(
        f"{base}/{route_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": "b" * 2001},
    )
    assert r.status_code == 422, f"Expected 422 for >2000 chars on PUT, got {r.status_code}: {r.text}"

    # ── Phase 6: PUT with > 10 non-empty lines → 422 ─────────────────────
    r = client.put(
        f"{base}/{route_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": eleven_lines},
    )
    assert r.status_code == 422, f"Expected 422 for >10 lines on PUT, got {r.status_code}: {r.text}"


# ---------------------------------------------------------------------------
# Scenario 3: IdentityAgentBinding — prompt_examples lifecycle
# ---------------------------------------------------------------------------


def test_identity_binding_prompt_examples_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    prompt_examples lifecycle for IdentityAgentBinding:
      1. Create agent
      2. Create binding without prompt_examples — field is null in response
      3. Create binding with prompt_examples — field is saved and returned
      4. Update binding to change prompt_examples — change persists
      5. Update binding to clear prompt_examples — cleared
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Binding PE Agent")
    agent_id = agent["id"]

    # ── Phase 2: Create binding without prompt_examples — null ───────────
    binding_no_pe = create_identity_binding(
        client,
        superuser_token_headers,
        agent_id=agent_id,
        trigger_prompt="Route me to this agent.",
    )
    assert binding_no_pe.get("prompt_examples") is None

    # Need a second agent to avoid duplicate-binding constraint
    agent2 = create_agent_via_api(client, superuser_token_headers, name="Binding PE Agent 2")
    agent2_id = agent2["id"]

    # ── Phase 3: Create binding with prompt_examples ──────────────────────
    examples = "What's my schedule?\nSend a message to Alice\nSet a reminder"
    binding_with_pe = create_identity_binding(
        client,
        superuser_token_headers,
        agent_id=agent2_id,
        trigger_prompt="Route me to this agent with examples.",
        prompt_examples=examples,
    )
    binding_id = binding_with_pe["id"]
    assert binding_with_pe["prompt_examples"] == examples

    # ── Phase 4: Update to change prompt_examples ────────────────────────
    updated_examples = "Book a meeting\nCancel my appointment"
    updated = update_identity_binding(
        client,
        superuser_token_headers,
        binding_id,
        prompt_examples=updated_examples,
    )
    assert updated["prompt_examples"] == updated_examples

    # ── Phase 5: Clear prompt_examples by setting to null ────────────────
    cleared = update_identity_binding(
        client,
        superuser_token_headers,
        binding_id,
        prompt_examples=None,
    )
    assert cleared["prompt_examples"] is None


# ---------------------------------------------------------------------------
# Scenario 4: IdentityAgentBinding — prompt_examples validation
# ---------------------------------------------------------------------------


def test_identity_binding_prompt_examples_validation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Validation rules for IdentityAgentBinding.prompt_examples:
      1. Create agent
      2. prompt_examples > 2000 characters on POST → 422
      3. prompt_examples > 10 non-empty lines on POST → 422
      4. Exactly 10 non-empty lines → 200 (boundary: allowed)
      5. prompt_examples > 2000 characters on PUT → 422
      6. prompt_examples > 10 non-empty lines on PUT → 422
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Binding PE Validation Agent")
    agent_id = agent["id"]

    # ── Phase 2: > 2000 chars on POST → 422 ──────────────────────────────
    too_long = "a" * 2001
    r = client.post(
        f"{_BINDINGS}/",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "trigger_prompt": "Test trigger.",
            "assigned_user_ids": [],
            "prompt_examples": too_long,
        },
    )
    assert r.status_code == 422, f"Expected 422 for >2000 chars, got {r.status_code}: {r.text}"
    assert "2000" in r.json()["detail"] or "characters" in r.json()["detail"].lower()

    # ── Phase 3: > 10 non-empty lines on POST → 422 ───────────────────────
    eleven_lines = "\n".join(f"Example {i}" for i in range(11))
    r = client.post(
        f"{_BINDINGS}/",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "trigger_prompt": "Test trigger.",
            "assigned_user_ids": [],
            "prompt_examples": eleven_lines,
        },
    )
    assert r.status_code == 422, f"Expected 422 for >10 lines, got {r.status_code}: {r.text}"
    assert "10" in r.json()["detail"] or "example" in r.json()["detail"].lower()

    # ── Phase 4: Exactly 10 non-empty lines → 200 (boundary) ─────────────
    ten_lines = "\n".join(f"Example {i}" for i in range(10))
    r = client.post(
        f"{_BINDINGS}/",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "trigger_prompt": "Test trigger.",
            "assigned_user_ids": [],
            "prompt_examples": ten_lines,
        },
    )
    assert r.status_code == 200, f"Expected 200 for exactly 10 lines, got {r.status_code}: {r.text}"
    binding_id = r.json()["id"]
    assert r.json()["prompt_examples"] == ten_lines

    # ── Phase 5: PUT with > 2000 chars → 422 ─────────────────────────────
    r = client.put(
        f"{_BINDINGS}/{binding_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": "b" * 2001},
    )
    assert r.status_code == 422, f"Expected 422 for >2000 chars on PUT, got {r.status_code}: {r.text}"

    # ── Phase 6: PUT with > 10 non-empty lines → 422 ─────────────────────
    r = client.put(
        f"{_BINDINGS}/{binding_id}",
        headers=superuser_token_headers,
        json={"prompt_examples": eleven_lines},
    )
    assert r.status_code == 422, f"Expected 422 for >10 lines on PUT, got {r.status_code}: {r.text}"
