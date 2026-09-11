"""Desktop-owned tasks stay mirrors until the owner releases external work.

Late session-creation defense: tests/unit/test_session_external_executor_guard.py.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.agent import create_agent_via_api
from tests.utils.background_tasks import drain_tasks
from tests.utils.input_task import (
    create_task,
    execute_task,
    get_task,
    get_task_by_code,
    get_task_detail,
    get_task_sessions,
    list_tasks,
    set_task_status,
    update_task,
)
from tests.utils.session import create_session_via_api
from tests.utils.user import create_random_user_with_headers

_BASE = f"{settings.API_V1_STR}/tasks"
_AGENT_ENV_PATCH = "app.services.sessions.message_service.agent_env_connector"


def test_external_executor_blocks_execution_until_finished_and_released(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """A marked create never starts cinna, persists through sync, then releases.

    1. Create with an agent, auto-execute, and a padded Desktop marker.
    2. Every read projection exposes the marker and no session is created.
    3. Retrying without a marker cannot undo ownership or start execution.
    4. Execute/refine are refused; ordinary edits and status reports still work.
    5. Active work cannot be released or reassigned, including by another user.
    6. Complete externally, release explicitly, then cinna can execute once.
    """
    headers = superuser_token_headers
    agent = create_agent_via_api(client, headers, name="External ownership agent")
    drain_tasks()
    source = create_session_via_api(client, headers, agent["id"])
    stub = StubAgentEnvConnector(response_text="Executed after explicit release.")

    # ── Phase 1: Auto-execute is neutralized before any background work ───
    with patch(_AGENT_ENV_PATCH, stub):
        task = create_task(
            client, headers, selected_agent_id=agent["id"],
            auto_execute=True, external_executor="  Desktop  ",
            external_ref="external-execution-lifecycle", source_session_id=source["id"],
        )
        drain_tasks()
    task_id = task["id"]
    assert task["external_executor"] == "Desktop"
    assert task["auto_execute"] is False
    assert task["status"] == "new"
    assert get_task_sessions(client, headers, task_id) == []

    # ── Phase 2: Explicitly built projections retain the marker ───────────
    projections = [
        get_task(client, headers, task_id),
        get_task_detail(client, headers, task_id),
        get_task_by_code(client, headers, task["short_code"]),
    ]
    listed = list_tasks(client, headers, status="all")
    projections.append(next(row for row in listed["data"] if row["id"] == task_id))
    by_source = client.get(f"{_BASE}/by-source-session/{source['id']}", headers=headers)
    assert by_source.status_code == 200, by_source.text
    projections.append(next(row for row in by_source.json()["data"] if row["id"] == task_id))
    assert all(row["external_executor"] == "Desktop" for row in projections)

    # ── Phase 3: Retry payload does not replace persisted ownership ───────
    with patch(_AGENT_ENV_PATCH, stub):
        retry = create_task(
            client, headers, selected_agent_id=agent["id"], auto_execute=True,
            external_ref="external-execution-lifecycle",
        )
        drain_tasks()
    assert retry["id"] == task_id
    assert retry["external_executor"] == "Desktop"
    assert retry["auto_execute"] is False
    assert get_task_sessions(client, headers, task_id) == []

    # ── Phase 4: All cinna execution entry points refuse marked work ──────
    refused = execute_task(client, headers, task_id)
    assert refused["success"] is False
    assert "Desktop" in refused["error"]
    refinement = client.post(
        f"{_BASE}/{task_id}/refine", headers=headers,
        json={"user_comment": "Refine the task"},
    )
    assert refinement.status_code == 400, refinement.text
    assert "external" in refinement.json()["detail"].lower()
    assert get_task(client, headers, task_id)["status"] == "new"
    assert get_task_sessions(client, headers, task_id) == []

    before_edit = get_task(client, headers, task_id)["updated_at"]
    edited = update_task(client, headers, task_id, title="Desktop task renamed", priority="high")
    assert edited["external_executor"] == "Desktop"
    assert edited["title"] == "Desktop task renamed"
    assert edited["priority"] == "high"
    delta = list_tasks(client, headers, status="all", updated_since=before_edit)
    assert any(row["id"] == task_id and row["external_executor"] == "Desktop" for row in delta["data"])

    # ── Phase 5: Active ownership survives edits and forbidden takeovers ──
    for status in ("in_progress", "blocked"):
        current = set_task_status(client, headers, task_id, status)
        assert current["executed_at"] is None, "External execution must not stamp a cinna execution"
        unchanged = update_task(client, headers, task_id, external_executor=" Desktop ")
        assert unchanged["external_executor"] == "Desktop"
        for replacement in (None, "Other computer", "  "):
            response = client.patch(
                f"{_BASE}/{task_id}", headers=headers,
                json={"external_executor": replacement},
            )
            assert response.status_code == 400, response.text
        assert get_task(client, headers, task_id)["external_executor"] == "Desktop"
    _, other_headers = create_random_user_with_headers(client)
    foreign = client.patch(f"{_BASE}/{task_id}", headers=other_headers, json={"external_executor": None})
    assert foreign.status_code in (400, 404)
    assert client.patch(f"{_BASE}/{task_id}", json={"external_executor": None}).status_code in (401, 403)
    assert get_task_sessions(client, headers, task_id) == []

    # ── Phase 6: External completion does not clear ownership implicitly ──
    set_task_status(client, headers, task_id, "in_progress")
    completed = set_task_status(client, headers, task_id, "completed")
    assert completed["external_executor"] == "Desktop"
    assert completed["executed_at"] is None
    assert execute_task(client, headers, task_id)["success"] is False
    released = update_task(client, headers, task_id, external_executor=None)
    assert released["external_executor"] is None
    with patch(_AGENT_ENV_PATCH, stub):
        executed = execute_task(client, headers, task_id)
        assert executed["success"] is True, executed
        drain_tasks()
    assert len(get_task_sessions(client, headers, task_id)) == 1
    assert get_task(client, headers, task_id)["executed_at"] is not None


def test_marker_acquisition_preserves_sessionless_work_but_refuses_cinna_sessions(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Acquire legacy mirrors; prevent takeover of both live and completed runs.

    1. A sessionless legacy task can acquire a marker after reporting progress.
    2. Acquisition clears the legacy cinna executed_at, and emits a sync delta.
    3. A task with a live session refuses a marker and preserves ordinary edits.
    4. It still refuses after completion: historical cinna sessions count too.
    """
    headers = superuser_token_headers
    mirror = create_task(client, headers)
    reported = set_task_status(client, headers, mirror["id"], "in_progress")
    assert reported["executed_at"] is not None, "Setup pins the legacy reporting behavior"
    acquired = update_task(client, headers, mirror["id"], external_executor="Desktop")
    assert acquired["external_executor"] == "Desktop"
    assert acquired["executed_at"] is None
    delta = list_tasks(client, headers, status="all", updated_since=reported["updated_at"])
    assert any(row["id"] == mirror["id"] and row["external_executor"] == "Desktop" for row in delta["data"])

    agent = create_agent_via_api(client, headers, name="Cinna ownership agent")
    drain_tasks()
    task = create_task(client, headers, selected_agent_id=agent["id"])
    with patch(_AGENT_ENV_PATCH, StubAgentEnvConnector(response_text="Cinna execution finished.")):
        executed = execute_task(client, headers, task["id"])
        assert executed["success"] is True, executed
        assert len(get_task_sessions(client, headers, task["id"])) == 1
        response = client.patch(f"{_BASE}/{task['id']}", headers=headers, json={"external_executor": "Desktop"})
        assert response.status_code == 400, response.text
        assert "session" in response.json()["detail"].lower()
        edited = update_task(client, headers, task["id"], title="Still cinna-owned")
        assert edited["external_executor"] is None
        drain_tasks()
    assert get_task(client, headers, task["id"])["status"] == "completed"
    response = client.patch(f"{_BASE}/{task['id']}", headers=headers, json={"external_executor": "Desktop"})
    assert response.status_code == 400, response.text
    assert "session" in response.json()["detail"].lower()
    assert get_task(client, headers, task["id"])["external_executor"] is None


def test_external_executor_normalization_and_validation(
    client: TestClient,
) -> None:
    """Blank markers mean unclaimed, omission preserves, explicit blank clears.

    Verify the same length/type checks on create and update, and prove an
    idempotent retry cannot attach a new marker to an existing unmarked task.
    """
    _, headers = create_random_user_with_headers(client)
    task = create_task(client, headers, external_executor=" \t ", external_ref="blank-executor")
    assert task["external_executor"] is None
    retry = create_task(client, headers, external_executor="Desktop", external_ref="blank-executor")
    assert retry["id"] == task["id"]
    assert retry["external_executor"] is None
    marked = update_task(client, headers, task["id"], external_executor="  Laptop  ")
    assert marked["external_executor"] == "Laptop"
    omitted = update_task(client, headers, task["id"], title="Keep ownership")
    assert omitted["external_executor"] == "Laptop"
    cleared = update_task(client, headers, task["id"], external_executor=" \t ")
    assert cleared["external_executor"] is None
    for invalid in ("x" * 101, 42):
        created = client.post(_BASE + "/", headers=headers, json={"original_message": "Invalid marker", "external_executor": invalid})
        assert created.status_code == 422, created.text
        updated = client.patch(f"{_BASE}/{task['id']}", headers=headers, json={"external_executor": invalid})
        assert updated.status_code == 422, updated.text
    assert get_task(client, headers, task["id"])["external_executor"] is None
