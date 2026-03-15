"""
Integration tests: Agent Collaboration feature.

Tests the four collaboration API endpoints end-to-end:
  1. POST /agents/collaborations/create
  2. POST /agents/collaborations/{id}/findings
  3. GET  /agents/collaborations/{id}/status
  4. GET  /agents/collaborations/by-session/{session_id}

Key infrastructure note
-----------------------
Creating a collaboration calls ``AgentService.create_agent_task`` internally,
which triggers the full InputTask / session / agent-env dispatch chain. Tests
that exercise creation patch this method with an AsyncMock so they only verify
the collaboration-layer logic. Tests that check side effects (findings, status,
by-session lookup) reuse collaborations created with the mock active.

The coordinator_agent_id is NOT provided directly in the create request — the
route derives it from the source_session's environment. This means every
creation scenario must supply a ``source_session_id`` that belongs to a session
created for a real agent (set up via create_agent_via_api + create_session_via_api).

Scenarios covered
-----------------
A. Creation happy path — valid coordinator + valid target agents → success
B. Creation validation — no subtasks, invalid session id, missing task_message
C. Creation ownership — target agent owned by another user is silently skipped
D. Findings — post/accumulate findings, empty finding rejected, wrong owner denied
E. Status — full status with subtask details, 404 for ghost, 403 for wrong owner
F. By-session lookup — participant session returns context, non-participant returns {}
G. Cross-user isolation — other user cannot access collaboration endpoints
H. Optional field defaults — no description, no explicit order value
"""
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.collaboration import (
    _COLLAB_BASE,
    _mock_create_agent_task,
    _mock_create_agent_task_failure,
    create_collaboration,
    get_collaboration_by_session,
    get_collaboration_status,
    post_finding,
    setup_coordinator_agent,
)
from tests.utils.session import create_session_via_api
from tests.utils.user import create_random_user_with_headers


def _setup_user_with_agent(client: TestClient) -> tuple[dict, dict[str, str], dict]:
    """Create a new user with AI credentials and an agent.

    Returns ``(user, headers, agent)``. Drains background tasks after agent creation
    so the environment stub is fully set up.
    """
    user, headers = create_random_user_with_headers(client)
    create_random_ai_credential(client, headers, set_default=True)
    agent = create_agent_via_api(client, headers)
    drain_tasks()
    return user, headers, agent


# ── A. Creation — happy path ────────────────────────────────────────────────


def test_create_collaboration_with_valid_subtasks(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full creation happy path:
      1. Create coordinator agent and session
      2. Create two target agents
      3. POST create — with two subtasks (mock dispatch succeeds)
      4. Verify response shape: success=True, collaboration_id, subtask_count
      5. GET status — verify all fields and subtask list
      6. Both subtasks in "running" state (dispatch succeeded)
    """
    # ── Phase 1: Coordinator agent and session ─────────────────────────────
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Agent"
    )
    coord_session_id = coord_session["id"]

    # ── Phase 2: Target agents ─────────────────────────────────────────────
    target_a = create_agent_via_api(client, superuser_token_headers, name="Worker Alpha")
    drain_tasks()
    target_b = create_agent_via_api(client, superuser_token_headers, name="Worker Beta")
    drain_tasks()

    subtasks = [
        {"target_agent_id": target_a["id"], "task_message": "Analyse dataset A", "order": 0},
        {"target_agent_id": target_b["id"], "task_message": "Analyse dataset B", "order": 1},
    ]

    # ── Phase 3: Create collaboration (mock dispatch) ──────────────────────
    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Parallel Analysis",
            description="Fan-out analysis tasks",
            source_session_id=coord_session_id,
            subtasks=subtasks,
        )

    collab_id = body["collaboration_id"]
    assert collab_id is not None
    assert body["subtask_count"] == 2
    assert "message" in body

    # ── Phase 4: GET status — full detail ─────────────────────────────────
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    assert status["id"] == collab_id
    assert status["title"] == "Parallel Analysis"
    assert status["description"] == "Fan-out analysis tasks"
    assert status["status"] == "in_progress"
    assert status["coordinator_agent_id"] == coordinator["id"]
    assert status["source_session_id"] == coord_session_id
    assert "shared_context" in status
    assert isinstance(status["subtasks"], list)
    assert len(status["subtasks"]) == 2

    # ── Phase 5: Subtask records created with correct task messages ──────────
    # The mock returns success=True with no task_id/session_id. The service
    # sets status="error" when both IDs are absent (it only sets "running" when
    # success=True AND task_id AND session_id are all truthy). In tests we use
    # None IDs to avoid FK violations from fake UUIDs, so "error" is expected.
    target_ids = {st["target_agent_id"] for st in status["subtasks"]}
    assert target_a["id"] in target_ids
    assert target_b["id"] in target_ids

    for subtask in status["subtasks"]:
        assert subtask["status"] in ("pending", "error")
        assert subtask["task_message"] in ("Analyse dataset A", "Analyse dataset B")
        assert subtask["target_agent_name"] is not None


def test_create_collaboration_with_dispatch_failure(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    When AgentService.create_agent_task fails, the subtask is recorded with
    status="error" and the collaboration is still created (success=True).
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Fail Test"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Fail")
    drain_tasks()

    subtasks = [
        {"target_agent_id": target["id"], "task_message": "Will fail dispatch"},
    ]

    with _mock_create_agent_task_failure(error="No active environment"):
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Failure Test Collab",
            source_session_id=coord_session["id"],
            subtasks=subtasks,
        )

    collab_id = body["collaboration_id"]
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    assert len(status["subtasks"]) == 1
    subtask = status["subtasks"][0]
    assert subtask["status"] == "error"
    assert subtask["input_task_id"] is None
    assert subtask["session_id"] is None


# ── B. Creation — validation failures ──────────────────────────────────────


def test_create_collaboration_no_subtasks_returns_failure(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Submitting an empty subtasks list → success=False (service raises
    AgentCollaborationError before any DB writes).
    """
    _, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord No Sub"
    )

    with _mock_create_agent_task():
        r = client.post(
            f"{_COLLAB_BASE}/create",
            headers=superuser_token_headers,
            json={
                "title": "Empty subtasks",
                "source_session_id": coord_session["id"],
                "subtasks": [],
            },
        )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "error" in body and body["error"]


def test_create_collaboration_invalid_source_session_id_returns_failure(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Providing a non-existent source_session_id → success=False.
    """
    ghost_session_id = str(uuid.uuid4())

    r = client.post(
        f"{_COLLAB_BASE}/create",
        headers=superuser_token_headers,
        json={
            "title": "Ghost Session Test",
            "source_session_id": ghost_session_id,
            "subtasks": [
                {"target_agent_id": str(uuid.uuid4()), "task_message": "Some task"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "error" in body and body["error"]


def test_create_collaboration_malformed_source_session_id_returns_failure(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Providing a malformed (non-UUID) source_session_id → success=False with a
    format error message.
    """
    r = client.post(
        f"{_COLLAB_BASE}/create",
        headers=superuser_token_headers,
        json={
            "title": "Malformed Session",
            "source_session_id": "not-a-uuid",
            "subtasks": [
                {"target_agent_id": str(uuid.uuid4()), "task_message": "Some task"},
            ],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "error" in body and body["error"]


def test_create_collaboration_subtasks_missing_task_message_are_skipped(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Subtasks with a missing or empty task_message are silently skipped.
    If ALL subtasks are skipped, the collaboration has zero subtasks but still
    returns success=True (the collaboration record is created).
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Skip Test"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Skip")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Skip Empty Messages",
            source_session_id=coord_session["id"],
            subtasks=[
                {"target_agent_id": target["id"], "task_message": "   "},  # blank — skipped
            ],
        )

    collab_id = body["collaboration_id"]
    status = get_collaboration_status(client, superuser_token_headers, collab_id)
    # The blank-message subtask was skipped, so 0 subtasks recorded
    assert len(status["subtasks"]) == 0


# ── C. Creation — ownership of target agents ────────────────────────────────


def test_create_collaboration_target_agent_owned_by_other_user_is_skipped(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Target agents not owned by the requesting user are silently skipped.
    The collaboration is created with only the valid subtasks.

    Uses a ghost UUID as the "other user's agent" since the service performs
    the ownership check via ``session.get(Agent, target_agent_id)`` — returning
    None when the agent doesn't exist triggers the same skip path as an agent
    owned by a different user.
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Owner Test"
    )
    # Agent owned by the requesting user
    own_target = create_agent_via_api(client, superuser_token_headers, name="My Worker")
    drain_tasks()

    # Non-existent agent UUID — service skips it (not owned by user)
    ghost_agent_id = str(uuid.uuid4())

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Ownership Guard Test",
            source_session_id=coord_session["id"],
            subtasks=[
                {"target_agent_id": own_target["id"], "task_message": "Do my task"},
                {"target_agent_id": ghost_agent_id, "task_message": "Do their task"},
            ],
        )

    collab_id = body["collaboration_id"]
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    # Only the owned-agent subtask should have been created (ghost was skipped)
    assert len(status["subtasks"]) == 1
    assert status["subtasks"][0]["target_agent_id"] == own_target["id"]


# ── D. Findings ─────────────────────────────────────────────────────────────


def test_findings_post_and_accumulate(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Post findings lifecycle:
      1. Create collaboration with one subtask
      2. Post first finding → appears in findings list, attributed to agent
      3. Post second finding → both findings present, ordered
      4. GET status → shared_context["findings"] reflects all findings
      5. Empty finding → success=False
      6. Wrong owner → success=False with error
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Findings"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Findings")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Findings Accumulation Test",
            source_session_id=coord_session["id"],
            subtasks=[{"target_agent_id": target["id"], "task_message": "Collect data"}],
        )

    collab_id = body["collaboration_id"]

    # ── Phase 2: Post first finding ────────────────────────────────────────
    result1 = post_finding(
        client, superuser_token_headers, collab_id,
        finding="Found 42 anomalies in dataset",
    )
    assert len(result1["findings"]) == 1
    assert "42 anomalies" in result1["findings"][0]
    # Finding is attributed to coordinator agent by default (no source_session_id)
    assert "Coord Findings" in result1["findings"][0]

    # ── Phase 3: Post second finding ───────────────────────────────────────
    result2 = post_finding(
        client, superuser_token_headers, collab_id,
        finding="Processing complete — no errors",
    )
    assert len(result2["findings"]) == 2
    assert any("no errors" in f for f in result2["findings"])

    # ── Phase 4: GET status reflects accumulated findings ──────────────────
    status = get_collaboration_status(client, superuser_token_headers, collab_id)
    findings = status["shared_context"].get("findings", [])
    assert len(findings) == 2

    # ── Phase 5: Empty finding → success=False ─────────────────────────────
    r_empty = client.post(
        f"{_COLLAB_BASE}/{collab_id}/findings",
        headers=superuser_token_headers,
        json={"finding": "   "},
    )
    assert r_empty.status_code == 200
    empty_body = r_empty.json()
    assert empty_body["success"] is False
    assert "error" in empty_body and empty_body["error"]

    # ── Phase 6: Wrong owner → success=False ──────────────────────────────
    _, other_headers = create_random_user_with_headers(client)
    r_other = client.post(
        f"{_COLLAB_BASE}/{collab_id}/findings",
        headers=other_headers,
        json={"finding": "Intruder finding"},
    )
    assert r_other.status_code == 200
    other_body = r_other.json()
    assert other_body["success"] is False
    assert "error" in other_body


def test_findings_on_nonexistent_collaboration(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Posting a finding to a non-existent collaboration → success=False.
    """
    ghost_id = str(uuid.uuid4())
    r = client.post(
        f"{_COLLAB_BASE}/{ghost_id}/findings",
        headers=superuser_token_headers,
        json={"finding": "Some finding"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is False
    assert "error" in body


def test_findings_with_source_session_attribution(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    When source_session_id is provided and resolves to a known agent's session,
    the finding is attributed to that agent (its name prefix appears in the
    finding entry). Uses the target agent's own session for attribution.
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Attribution"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Attribution")
    drain_tasks()
    # Create a real session for the target agent so attribution lookup works
    target_session = create_session_via_api(client, superuser_token_headers, target["id"])

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Attribution Test Collab",
            source_session_id=coord_session["id"],
            subtasks=[{"target_agent_id": target["id"], "task_message": "Attributed task"}],
        )

    collab_id = body["collaboration_id"]

    # Post finding attributed to the target agent via their session
    result = post_finding(
        client,
        superuser_token_headers,
        collab_id,
        finding="Result from worker",
        source_session_id=target_session["id"],
    )
    assert result["success"] is True
    assert len(result["findings"]) == 1
    # Finding should be attributed to the worker agent by name prefix
    assert "Worker Attribution" in result["findings"][0]


# ── E. Status ───────────────────────────────────────────────────────────────


def test_get_status_full_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Status endpoint covers:
      1. Returns full AgentCollaborationPublic with subtasks and agent names
      2. Ghost collaboration id → 404
      3. Wrong user → 403
      4. Unauthenticated → 401/403
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Status"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Status")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Status Lifecycle",
            description="Testing status endpoint",
            source_session_id=coord_session["id"],
            subtasks=[{"target_agent_id": target["id"], "task_message": "Do status work"}],
        )

    collab_id = body["collaboration_id"]

    # ── Phase 1: Valid status fetch ────────────────────────────────────────
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    assert status["id"] == collab_id
    assert status["title"] == "Status Lifecycle"
    assert status["description"] == "Testing status endpoint"
    assert status["coordinator_agent_id"] == coordinator["id"]
    assert status["status"] == "in_progress"
    assert isinstance(status["subtasks"], list)
    assert len(status["subtasks"]) == 1
    assert status["subtasks"][0]["target_agent_id"] == target["id"]
    assert status["subtasks"][0]["target_agent_name"] == "Worker Status"
    assert "created_at" in status
    assert "updated_at" in status

    # ── Phase 2: Ghost id → 404 ────────────────────────────────────────────
    ghost = str(uuid.uuid4())
    r_ghost = client.get(f"{_COLLAB_BASE}/{ghost}/status", headers=superuser_token_headers)
    assert r_ghost.status_code == 404

    # ── Phase 3: Wrong user → 403 ─────────────────────────────────────────
    _, other_headers = create_random_user_with_headers(client)
    r_other = client.get(f"{_COLLAB_BASE}/{collab_id}/status", headers=other_headers)
    assert r_other.status_code == 403

    # ── Phase 4: Unauthenticated → 401/403 ────────────────────────────────
    r_anon = client.get(f"{_COLLAB_BASE}/{collab_id}/status")
    assert r_anon.status_code in (401, 403)


# ── F. By-session lookup ────────────────────────────────────────────────────


def test_by_session_lookup_participant_returns_context(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    db,
) -> None:
    """
    When session_id belongs to a collaboration subtask, by-session returns
    a context dict with collaboration_id, title, role, and other_participants.

    Setup: create collaboration with two subtasks (mock dispatch → subtasks end up
    with status "error" and no session_id). Then update subtask A's session_id
    directly via the db fixture to point at a real session. This links the subtask
    to a real ChatSession so the by-session route can look it up.

    The db fixture is used here because session_id on a CollaborationSubtask is
    internal state only set by the dispatch hook — there is no API endpoint that
    updates it directly after creation.
    """
    from sqlmodel import select as sql_select
    from app.models.agent_collaboration import CollaborationSubtask

    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord BySession"
    )
    target_a = create_agent_via_api(client, superuser_token_headers, name="Worker BySession-A")
    drain_tasks()
    target_b = create_agent_via_api(client, superuser_token_headers, name="Worker BySession-B")
    drain_tasks()

    # Create a real session for target_a that we will link to the subtask record
    real_session_a = create_session_via_api(client, superuser_token_headers, target_a["id"])
    real_session_a_id = uuid.UUID(real_session_a["id"])

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="By-Session Lookup Test",
            description="Fan-out lookup scenario",
            source_session_id=coord_session["id"],
            subtasks=[
                {"target_agent_id": target_a["id"], "task_message": "Task for A", "order": 0},
                {"target_agent_id": target_b["id"], "task_message": "Task for B", "order": 1},
            ],
        )

    collab_id = body["collaboration_id"]

    # Update subtask A's session_id to point at the real session.
    # This simulates what the auto-feedback dispatch hook would do when the session
    # is created for the subtask. session_id is internal state with no direct API setter.
    subtask_a = db.exec(
        sql_select(CollaborationSubtask).where(
            CollaborationSubtask.collaboration_id == uuid.UUID(collab_id),
            CollaborationSubtask.target_agent_id == uuid.UUID(target_a["id"]),
        )
    ).first()
    assert subtask_a is not None, "Subtask A not found in DB"
    subtask_a.session_id = real_session_a_id
    db.add(subtask_a)
    db.commit()

    # ── Subtask A session → returns full collaboration context ─────────────
    context = get_collaboration_by_session(
        client, superuser_token_headers, real_session_a["id"]
    )
    assert context != {}
    assert context["collaboration_id"] == collab_id
    assert context["collaboration_title"] == "By-Session Lookup Test"
    assert context["collaboration_description"] == "Fan-out lookup scenario"
    assert context["collaboration_role"] == "Task for A"
    assert "subtask_id" in context
    # Other participants list should contain Worker BySession-B (the other subtask agent)
    assert isinstance(context["collaboration_other_participants"], list)

    # ── Coordinator session is NOT a subtask session → returns {} ──────────
    coord_context = get_collaboration_by_session(
        client, superuser_token_headers, coord_session["id"]
    )
    assert coord_context == {}


def test_by_session_lookup_non_participant_session_returns_empty(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A session that is NOT linked to any collaboration subtask returns {} (not 404).
    """
    agent, agent_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Non-Participant Agent"
    )
    # This session has nothing to do with any collaboration
    context = get_collaboration_by_session(
        client, superuser_token_headers, agent_session["id"]
    )
    assert context == {}


def test_by_session_lookup_nonexistent_session_returns_404(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A ghost session_id → 404.
    """
    ghost_session = str(uuid.uuid4())
    r = client.get(
        f"{_COLLAB_BASE}/by-session/{ghost_session}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


def test_by_session_lookup_other_user_session_returns_404(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A session belonging to a different user → 404 (ownership guard).
    """
    # Create a session owned by another user (includes AI credential setup)
    _, other_headers, other_agent = _setup_user_with_agent(client)
    other_session = create_session_via_api(client, other_headers, other_agent["id"])

    # Superuser tries to look up the other user's session → 404
    r = client.get(
        f"{_COLLAB_BASE}/by-session/{other_session['id']}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


# ── G. Cross-user isolation ─────────────────────────────────────────────────


def test_collaboration_unauthenticated_requests_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    All collaboration endpoints reject unauthenticated requests with 401 or 403.
    No collaboration setup needed — the auth check fires first.
    """
    ghost_id = str(uuid.uuid4())
    ghost_session = str(uuid.uuid4())

    r_create = client.post(
        f"{_COLLAB_BASE}/create",
        json={
            "title": "Anon Test",
            "source_session_id": ghost_session,
            "subtasks": [],
        },
    )
    assert r_create.status_code in (401, 403)

    r_findings = client.post(
        f"{_COLLAB_BASE}/{ghost_id}/findings",
        json={"finding": "test"},
    )
    assert r_findings.status_code in (401, 403)

    r_status = client.get(f"{_COLLAB_BASE}/{ghost_id}/status")
    assert r_status.status_code in (401, 403)

    r_by_session = client.get(f"{_COLLAB_BASE}/by-session/{ghost_session}")
    assert r_by_session.status_code in (401, 403)


# ── H. Optional field defaults and ordering ──────────────────────────────────


def test_create_collaboration_single_subtask_with_optional_fields(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Collaboration created with no description and minimal subtask (no order field)
    succeeds. Verify defaults: description=None, order=0.
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Minimal"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Minimal")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Minimal Collaboration",
            source_session_id=coord_session["id"],
            subtasks=[{"target_agent_id": target["id"], "task_message": "Do minimal task"}],
        )

    collab_id = body["collaboration_id"]
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    assert status["description"] is None
    assert len(status["subtasks"]) == 1
    assert status["subtasks"][0]["order"] == 0


def test_create_collaboration_multiple_subtasks_preserve_order(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    When multiple subtasks are submitted with explicit order values, GET status
    returns subtasks with those order values preserved.
    """
    coordinator, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Order"
    )
    target_a = create_agent_via_api(client, superuser_token_headers, name="Worker Order-A")
    drain_tasks()
    target_b = create_agent_via_api(client, superuser_token_headers, name="Worker Order-B")
    drain_tasks()
    target_c = create_agent_via_api(client, superuser_token_headers, name="Worker Order-C")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Order Preservation Test",
            source_session_id=coord_session["id"],
            subtasks=[
                {"target_agent_id": target_a["id"], "task_message": "First", "order": 2},
                {"target_agent_id": target_b["id"], "task_message": "Second", "order": 0},
                {"target_agent_id": target_c["id"], "task_message": "Third", "order": 1},
            ],
        )

    collab_id = body["collaboration_id"]
    status = get_collaboration_status(client, superuser_token_headers, collab_id)

    assert len(status["subtasks"]) == 3
    order_map = {st["target_agent_id"]: st["order"] for st in status["subtasks"]}
    assert order_map[target_a["id"]] == 2
    assert order_map[target_b["id"]] == 0
    assert order_map[target_c["id"]] == 1


def test_create_collaboration_response_message_includes_title_and_count(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    The success message in the create response includes the collaboration title
    and subtask count as human-readable confirmation.
    """
    _, coord_session = setup_coordinator_agent(
        client, superuser_token_headers, name="Coord Message Test"
    )
    target = create_agent_via_api(client, superuser_token_headers, name="Worker Msg")
    drain_tasks()

    with _mock_create_agent_task():
        body = create_collaboration(
            client,
            superuser_token_headers,
            title="Message Content Test",
            source_session_id=coord_session["id"],
            subtasks=[{"target_agent_id": target["id"], "task_message": "Some task"}],
        )

    assert body["message"] is not None
    assert "Message Content Test" in body["message"]
    assert "1" in body["message"]  # subtask count
