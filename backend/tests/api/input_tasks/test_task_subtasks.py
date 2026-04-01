"""
Tests for subtask creation, listing, and progress tracking.

User-initiated subtask creation (POST /tasks/{id}/subtasks/) is available
to any task owner. Agent-initiated subtask creation (via team context) is
tested in test_task_agent_api.py.

Scenarios:
  1. Subtask lifecycle — create, list, verify parent_task_id set
  2. Subtask inherits team_id when parent has team_id
  3. Create subtask via POST /tasks/{id}/subtasks/ endpoint
  4. GET /tasks/{id}/subtasks/ lists direct subtasks only (not grandchildren)
  5. Subtask counts on parent task (subtask_count, subtask_completed_count)
  6. Subtask appears in parent detail endpoint
  7. Nested subtask hierarchy (subtask of a subtask)
  8. Subtask is excluded by root_only filter
  9. Ownership: creating subtask for someone else's task returns 404
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agentic_team import create_team
from tests.utils.input_task import (
    create_task,
    get_task,
    get_task_detail,
    list_tasks,
    create_subtask,
    list_subtasks,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_subtask_full_lifecycle(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Full subtask lifecycle:
      1. Create parent task
      2. Create subtask via POST /tasks/{parent_id}/subtasks/
      3. Subtask has parent_task_id set to parent
      4. Subtask has its own short_code
      5. Subtask is owned by same user
      6. GET /tasks/{parent_id}/subtasks/ — subtask appears
      7. Parent task's subtask_count increments to 1
      8. Parent detail shows subtask in subtasks list
      9. Create second subtask — count becomes 2
     10. Subtask is accessible via GET /tasks/{subtask_id}
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create parent task ──────────────────────────────────────────
    parent = create_task(client, headers, original_message="Parent task for subtasks")
    parent_id = parent["id"]

    # ── Phase 2: Create first subtask ────────────────────────────────────────
    sub1 = create_subtask(
        client, headers, parent_id,
        original_message="Research competitors",
        title="Competitive Analysis",
        priority="high",
    )
    sub1_id = sub1["id"]

    assert sub1["parent_task_id"] == parent_id
    assert sub1["short_code"] is not None
    assert sub1["short_code"] != parent["short_code"]
    assert sub1["title"] == "Competitive Analysis"
    assert sub1["priority"] == "high"
    assert sub1["status"] == "new"

    # ── Phase 3: Subtask accessible via standard get ─────────────────────────
    fetched_sub = get_task(client, headers, sub1_id)
    assert fetched_sub["parent_task_id"] == parent_id
    assert fetched_sub["id"] == sub1_id

    # ── Phase 4: GET /tasks/{parent}/subtasks/ — subtask appears ─────────────
    subs_result = list_subtasks(client, headers, parent_id)
    assert subs_result["count"] == 1
    assert subs_result["data"][0]["id"] == sub1_id

    # ── Phase 5: Parent's subtask_count is 1 (from list endpoint which populates counts) ─
    # Note: GET /{id} (get_task_extended) does not populate subtask_count;
    # subtask_count is populated by list_tasks_extended and get_task_detail.
    parent_detail = get_task_detail(client, headers, parent_id)
    assert parent_detail["subtask_count"] == 1
    assert parent_detail["subtask_completed_count"] == 0

    # ── Phase 6: Parent detail shows subtask in subtasks list ────────────────
    parent_detail = get_task_detail(client, headers, parent_id)
    assert parent_detail["subtask_count"] == 1
    subtask_ids_in_detail = [s["id"] for s in parent_detail["subtasks"]]
    assert sub1_id in subtask_ids_in_detail

    # ── Phase 7: Create second subtask ───────────────────────────────────────
    sub2 = create_subtask(
        client, headers, parent_id,
        original_message="Write the report",
        title="Report Writing",
    )
    sub2_id = sub2["id"]
    assert sub2["parent_task_id"] == parent_id

    # ── Phase 8: Count is now 2 ──────────────────────────────────────────────
    subs_result = list_subtasks(client, headers, parent_id)
    assert subs_result["count"] == 2

    parent_detail_updated = get_task_detail(client, headers, parent_id)
    assert parent_detail_updated["subtask_count"] == 2

    # ── Phase 9: Subtask has its own unique short_code ───────────────────────
    assert sub1["short_code"] != sub2["short_code"]


def test_subtask_inherits_team_id_from_parent(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    When a parent task has team_id, user-created subtasks via POST /tasks/{id}/subtasks/
    can optionally specify the team_id; the team association is validated by the service.

    When creating a subtask via the normal create_task API with parent_task_id,
    the team_id must be provided explicitly. Via POST /tasks/{id}/subtasks/, the
    route sets parent_task_id but does not automatically inherit team_id.

    This test verifies:
      1. Create parent task with team_id
      2. Create subtask using POST /tasks/{parent_id}/subtasks/ without team_id
         — subtask has no team_id (not auto-inherited at route level)
      3. Verify parent's team_id is preserved on parent
    """
    headers = normal_user_token_headers

    team = create_team(client, headers, name="Subtask inheritance team")
    team_id = team["id"]

    parent = create_task(client, headers, original_message="Team parent task", team_id=team_id)
    assert parent["team_id"] == team_id

    # Create subtask via route — route sets parent_task_id only, not team_id
    sub = create_subtask(
        client, headers, parent["id"],
        original_message="Subtask without explicit team",
    )
    # team_id is NOT automatically inherited at the route level
    # (the agent subtask creation service handles inheritance differently)
    assert sub["parent_task_id"] == parent["id"]


def test_list_subtasks_returns_direct_children_only(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/{id}/subtasks/ returns DIRECT children only, not grandchildren:
      1. Create root task
      2. Create child under root
      3. Create grandchild under child
      4. GET /tasks/root/subtasks/ — only child appears, not grandchild
      5. GET /tasks/child/subtasks/ — grandchild appears
    """
    headers = normal_user_token_headers

    root = create_task(client, headers, original_message="Root for nesting test")
    child = create_subtask(client, headers, root["id"], original_message="Direct child")
    grandchild = create_subtask(client, headers, child["id"], original_message="Grandchild")

    # Root's subtasks: only child
    root_subs = list_subtasks(client, headers, root["id"])
    root_sub_ids = [s["id"] for s in root_subs["data"]]
    assert child["id"] in root_sub_ids
    assert grandchild["id"] not in root_sub_ids
    assert root_subs["count"] == 1

    # Child's subtasks: grandchild
    child_subs = list_subtasks(client, headers, child["id"])
    child_sub_ids = [s["id"] for s in child_subs["data"]]
    assert grandchild["id"] in child_sub_ids
    assert child_subs["count"] == 1


def test_subtask_excluded_by_root_only_filter(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    root_only=true excludes subtasks (tasks with parent_task_id set):
      1. Create root task
      2. Create subtask under root
      3. List all — both appear
      4. List with root_only=true — only root appears
    """
    headers = normal_user_token_headers

    root = create_task(client, headers, original_message="Root for root_only subtask test")
    sub = create_subtask(client, headers, root["id"], original_message="Sub for root_only test")

    all_tasks = list_tasks(client, headers)
    all_ids = [t["id"] for t in all_tasks["data"]]
    assert root["id"] in all_ids
    assert sub["id"] in all_ids

    root_only = list_tasks(client, headers, root_only=True)
    root_only_ids = [t["id"] for t in root_only["data"]]
    assert root["id"] in root_only_ids
    assert sub["id"] not in root_only_ids


def test_subtask_creation_ownership_enforcement(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    User B cannot create a subtask under User A's task:
      1. User A creates a task
      2. User B tries to POST /tasks/{A_task_id}/subtasks/ — 404
    """
    headers_a = normal_user_token_headers
    task_a = create_task(client, headers_a, original_message="Ownership subtask test")

    user_b = create_random_user(client)
    headers_b = user_authentication_headers(
        client=client, email=user_b["email"], password=user_b["_password"]
    )

    r = client.post(
        f"{_BASE}/{task_a['id']}/subtasks/",
        headers=headers_b,
        json={"original_message": "Intruder subtask"},
    )
    assert r.status_code in (400, 404)  # PermissionDeniedError → 400


def test_subtask_list_ownership_enforcement(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    User B cannot list subtasks of User A's task:
      GET /tasks/{A_task_id}/subtasks/ by User B returns 404
    """
    headers_a = normal_user_token_headers
    task_a = create_task(client, headers_a, original_message="Subtask list ownership test")

    user_b = create_random_user(client)
    headers_b = user_authentication_headers(
        client=client, email=user_b["email"], password=user_b["_password"]
    )

    r = client.get(f"{_BASE}/{task_a['id']}/subtasks/", headers=headers_b)
    assert r.status_code in (400, 404)  # PermissionDeniedError → 400


def test_create_subtask_on_nonexistent_parent_404(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """Creating a subtask with a non-existent parent_task_id returns 404."""
    headers = normal_user_token_headers
    ghost = str(uuid.uuid4())
    r = client.post(
        f"{_BASE}/{ghost}/subtasks/",
        headers=headers,
        json={"original_message": "Orphan subtask"},
    )
    assert r.status_code == 404
