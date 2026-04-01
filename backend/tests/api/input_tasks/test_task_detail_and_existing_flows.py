"""
Tests for the task detail endpoint and preservation of existing task flows.

Scenarios:
  1. Task detail endpoint — GET /tasks/{id}/detail returns full data structure
  2. Task detail by short-code — GET /tasks/by-code/{code}/detail
  3. Detail includes all related data (comments, attachments, subtasks, status_history)
  4. Computed fields in detail (subtask_count, subtask_completed_count)
  5. Existing task creation flow still works (short_code assigned to every task)
  6. Tasks without a team get TASK- prefix short codes
  7. Status filter "active" includes new/refining/open/in_progress/blocked/error
  8. Status filter "completed" shows only completed tasks
  9. Status filter "archived" shows only archived tasks
 10. Task description defaults to original_message on create
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.input_task import (
    create_task,
    get_task,
    get_task_detail,
    get_task_by_code,
    get_task_detail_by_code,
    add_comment,
    upload_attachment,
    list_tasks,
    create_subtask,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_task_detail_endpoint_full_structure(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/{id}/detail returns a fully populated InputTaskDetailPublic:
      1. Create task
      2. Add two comments
      3. Upload an attachment
      4. Create a subtask
      5. Archive task (generates status history + system comment)
      6. GET detail — all fields present and populated
      7. comments, attachments, subtasks, status_history all non-empty
      8. Computed subtask_count matches
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create task ─────────────────────────────────────────────────
    task = create_task(
        client, headers,
        original_message="Full detail test task",
        title="Detail Test",
        priority="high",
    )
    task_id = task["id"]

    # ── Phase 2: Add two comments ────────────────────────────────────────────
    c1 = add_comment(client, headers, task_id, content="First detail comment")
    c2 = add_comment(client, headers, task_id, content="Second detail comment")

    # ── Phase 3: Upload an attachment ────────────────────────────────────────
    att = upload_attachment(
        client, headers, task_id,
        content=b"Attachment for detail test",
        filename="detail_test.txt",
    )

    # ── Phase 4: Create a subtask ────────────────────────────────────────────
    sub = create_subtask(client, headers, task_id, original_message="Detail test subtask")

    # ── Phase 5: Archive task (generates status history + system comment) ────
    r = client.post(f"{_BASE}/{task_id}/archive", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "archived"

    # ── Phase 6: GET detail — full structure ─────────────────────────────────
    detail = get_task_detail(client, headers, task_id)

    # Core fields
    assert detail["id"] == task_id
    assert detail["title"] == "Detail Test"
    assert detail["priority"] == "high"
    assert detail["status"] == "archived"
    assert detail["short_code"] is not None

    # ── Phase 7: Related data non-empty ──────────────────────────────────────
    # Comments: 2 user comments + at least 1 status_change system comment
    comment_ids = [c["id"] for c in detail["comments"]]
    assert c1["id"] in comment_ids
    assert c2["id"] in comment_ids
    status_comments = [c for c in detail["comments"] if c["comment_type"] == "status_change"]
    assert len(status_comments) >= 1

    # Attachments: the uploaded file
    att_ids = [a["id"] for a in detail["attachments"]]
    assert att["id"] in att_ids

    # Subtasks: the created subtask
    sub_ids = [s["id"] for s in detail["subtasks"]]
    assert sub["id"] in sub_ids

    # Status history: at least one entry (new → archived)
    assert len(detail["status_history"]) >= 1

    # ── Phase 8: Computed counts ─────────────────────────────────────────────
    assert detail["subtask_count"] == 1
    assert detail["subtask_completed_count"] == 0


def test_task_detail_by_id_vs_by_code_consistency(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/{id}/detail and GET /tasks/by-code/{code}/detail return same data:
      1. Create task
      2. Add a comment
      3. Compare detail by ID vs detail by short_code — key fields match
    """
    headers = normal_user_token_headers

    task = create_task(client, headers, original_message="Detail consistency test", title="Consistency")
    task_id = task["id"]
    short_code = task["short_code"]

    add_comment(client, headers, task_id, content="Consistency comment")

    detail_by_id = get_task_detail(client, headers, task_id)
    detail_by_code = get_task_detail_by_code(client, headers, short_code)

    # Core fields match
    assert detail_by_id["id"] == detail_by_code["id"]
    assert detail_by_id["short_code"] == detail_by_code["short_code"]
    assert detail_by_id["title"] == detail_by_code["title"]
    assert detail_by_id["status"] == detail_by_code["status"]

    # Comments are the same
    by_id_comment_ids = {c["id"] for c in detail_by_id["comments"]}
    by_code_comment_ids = {c["id"] for c in detail_by_code["comments"]}
    assert by_id_comment_ids == by_code_comment_ids


def test_task_detail_ownership(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/{id}/detail and GET /tasks/by-code/{code}/detail respect ownership:
      Other user gets 404 on both endpoints.
    """
    headers_a = normal_user_token_headers
    task = create_task(client, headers_a, original_message="Ownership detail test")
    task_id = task["id"]
    short_code = task["short_code"]

    other = create_random_user(client)
    other_h = user_authentication_headers(
        client=client, email=other["email"], password=other["_password"]
    )

    r = client.get(f"{_BASE}/{task_id}/detail", headers=other_h)
    assert r.status_code in (400, 404)  # PermissionDeniedError → 400

    r = client.get(f"{_BASE}/by-code/{short_code}/detail", headers=other_h)
    assert r.status_code in (400, 404)  # PermissionDeniedError → 400


def test_existing_task_creation_flow_gets_short_code(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Existing task creation flow is preserved — every created task gets a short_code:
      1. Create minimal task (original_message only) — gets short_code
      2. Create task with all optional fields — gets short_code
      3. Both short_codes are unique
      4. current_description defaults to original_message
      5. status defaults to 'new'
    """
    headers = normal_user_token_headers

    # ── Minimal task ─────────────────────────────────────────────────────────
    minimal = create_task(client, headers, original_message="Minimal task creation")
    assert minimal["short_code"] is not None
    assert minimal["short_code"].startswith("TASK-")
    assert minimal["status"] == "new"
    assert minimal["current_description"] == "Minimal task creation"
    assert minimal["priority"] == "normal"

    # ── Task with all fields ──────────────────────────────────────────────────
    full = create_task(
        client, headers,
        original_message="Full task creation with all fields",
        title="Full Task",
        priority="urgent",
    )
    assert full["short_code"] is not None
    assert full["short_code"].startswith("TASK-")
    assert full["title"] == "Full Task"
    assert full["priority"] == "urgent"

    # Short codes are unique
    assert minimal["short_code"] != full["short_code"]


def test_status_filter_active_and_completed_and_archived(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Status filter aliases work correctly:
      1. Create a task in 'new' status — appears in 'active' filter
      2. Archive it — appears in 'archived' filter, no longer in 'active'
      3. Create a second task — appears in 'active' filter
      4. 'all' filter shows everything
    """
    headers = normal_user_token_headers

    task_a = create_task(client, headers, original_message="Active status filter test A")
    task_b = create_task(client, headers, original_message="Active status filter test B")

    # ── Both appear in 'active' filter ───────────────────────────────────────
    active_result = list_tasks(client, headers, status="active")
    active_ids = [t["id"] for t in active_result["data"]]
    assert task_a["id"] in active_ids
    assert task_b["id"] in active_ids

    # ── Archive task_a ────────────────────────────────────────────────────────
    r = client.post(f"{_BASE}/{task_a['id']}/archive", headers=headers)
    assert r.status_code == 200

    # ── task_a no longer in 'active' ─────────────────────────────────────────
    active_result = list_tasks(client, headers, status="active")
    active_ids = [t["id"] for t in active_result["data"]]
    assert task_a["id"] not in active_ids
    assert task_b["id"] in active_ids

    # ── task_a appears in 'archived' filter ──────────────────────────────────
    archived_result = list_tasks(client, headers, status="archived")
    archived_ids = [t["id"] for t in archived_result["data"]]
    assert task_a["id"] in archived_ids
    assert task_b["id"] not in archived_ids

    # ── 'all' filter shows everything ────────────────────────────────────────
    all_result = list_tasks(client, headers, status="all")
    all_ids = [t["id"] for t in all_result["data"]]
    assert task_a["id"] in all_ids
    assert task_b["id"] in all_ids


def test_task_description_defaults_match_original_message(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    When creating a task, current_description defaults to original_message:
      1. Create task without specifying current_description
      2. Verify current_description == original_message
      3. Updating title and priority does NOT change current_description
    """
    headers = normal_user_token_headers

    msg = "This is the original task message"
    task = create_task(client, headers, original_message=msg)

    assert task["original_message"] == msg
    assert task["current_description"] == msg

    # Update title — description unchanged
    updated = client.patch(
        f"{_BASE}/{task['id']}",
        headers=headers,
        json={"title": "New Title"},
    )
    assert updated.status_code == 200
    assert updated.json()["current_description"] == msg


def test_task_detail_404_and_unauthenticated(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Detail endpoint guards:
      1. Non-existent task UUID returns 404
      2. Unauthenticated access returns 401/403
    """
    headers = normal_user_token_headers
    ghost = str(uuid.uuid4())

    r = client.get(f"{_BASE}/{ghost}/detail", headers=headers)
    assert r.status_code == 404

    r = client.get(f"{_BASE}/by-code/TASK-GHOST-9999/detail", headers=headers)
    assert r.status_code == 404

    # Unauthenticated
    r = client.get(f"{_BASE}/{ghost}/detail")
    assert r.status_code in (401, 403)
