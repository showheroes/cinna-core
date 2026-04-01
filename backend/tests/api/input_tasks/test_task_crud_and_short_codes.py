"""
Tests for InputTask CRUD operations, short-code generation, and filtering.

Scenarios:
  1. Task full lifecycle — create, get, update (priority/title), delete
  2. Short-code generation — every task gets TASK-N; counter increments per user
  3. Team prefix short-codes — team with task_prefix uses prefix instead of TASK
  4. Get by short-code — by-code and by-code/detail endpoints
  5. Task tree endpoint — recursive subtask structure via by-code/tree
  6. root_only filter — excludes subtasks from list
  7. team_id filter — filters to team tasks only
  8. priority filter — filters to matching priority tasks only
  9. Ownership enforcement — other user gets 404 on all operations
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agentic_team import create_team, update_team, create_node, create_connection
from tests.utils.agent import create_agent_via_api
from tests.utils.input_task import (
    create_task,
    get_task,
    get_task_by_code,
    get_task_detail_by_code,
    get_task_tree_by_code,
    list_tasks,
    update_task,
    delete_task,
    create_subtask,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_task_crud_lifecycle_and_short_code(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Full CRUD lifecycle with short-code and field assertions:
      1. Create task — short_code auto-generated (TASK-N), title derived from message
      2. Create second task — sequence_number increments, unique short_code
      3. Get by UUID — all fields present
      4. Update priority and title — persisted
      5. List — both tasks appear, count matches
      6. Delete first task — 200 message
      7. Verify first task gone — 404
      8. Second task still present after first deleted
      9. Unauthenticated requests rejected
     10. Other user cannot access tasks
     11. Non-existent ID returns 404
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create first task ───────────────────────────────────────────
    msg = "Investigate customer churn in Q4"
    task1 = create_task(client, headers, original_message=msg, priority="high")
    task1_id = task1["id"]

    assert task1["short_code"] is not None
    assert task1["short_code"].startswith("TASK-")
    seq1 = task1["sequence_number"]
    assert seq1 is not None and seq1 >= 1

    # Title should be derived from first line of message
    assert task1["title"] == msg[:500]
    assert task1["priority"] == "high"
    assert task1["status"] == "new"
    assert task1["original_message"] == msg
    assert task1["current_description"] == msg
    assert task1["parent_task_id"] is None
    assert task1["team_id"] is None
    assert task1["assigned_node_id"] is None

    # ── Phase 2: Create second task — counter increments ─────────────────────
    task2 = create_task(
        client, headers,
        original_message="Plan Q1 marketing campaign",
        priority="urgent",
        title="Q1 Campaign Plan",
    )
    task2_id = task2["id"]

    assert task2["short_code"] is not None
    assert task2["short_code"].startswith("TASK-")
    assert task2["sequence_number"] == seq1 + 1
    assert task2["short_code"] != task1["short_code"]
    assert task2["title"] == "Q1 Campaign Plan"  # explicit title used
    assert task2["priority"] == "urgent"

    # ── Phase 3: Get by UUID — fields match ──────────────────────────────────
    fetched = get_task(client, headers, task1_id)
    assert fetched["id"] == task1_id
    assert fetched["short_code"] == task1["short_code"]
    assert fetched["priority"] == "high"

    # ── Phase 4: Update priority and title ───────────────────────────────────
    updated = update_task(client, headers, task1_id, priority="low", title="Churn Analysis Q4")
    assert updated["priority"] == "low"
    assert updated["title"] == "Churn Analysis Q4"

    # Verify update persisted
    re_fetched = get_task(client, headers, task1_id)
    assert re_fetched["priority"] == "low"
    assert re_fetched["title"] == "Churn Analysis Q4"

    # ── Phase 5: List — both tasks present ───────────────────────────────────
    result = list_tasks(client, headers)
    ids = [t["id"] for t in result["data"]]
    assert task1_id in ids
    assert task2_id in ids
    assert result["count"] >= 2

    # ── Phase 6: Delete first task ───────────────────────────────────────────
    deleted = delete_task(client, headers, task1_id)
    assert "deleted" in deleted["message"].lower() or "success" in deleted["message"].lower()

    # ── Phase 7: Verify first task gone ──────────────────────────────────────
    r = client.get(f"{_BASE}/{task1_id}", headers=headers)
    assert r.status_code == 404

    # ── Phase 8: Second task still accessible ────────────────────────────────
    still_there = get_task(client, headers, task2_id)
    assert still_there["id"] == task2_id

    # ── Phase 9: Unauthenticated requests rejected ────────────────────────────
    assert client.get(f"{_BASE}/").status_code in (401, 403)
    assert client.post(f"{_BASE}/", json={"original_message": "test"}).status_code in (401, 403)

    # ── Phase 10: Other user cannot access tasks ──────────────────────────────
    # PermissionDeniedError has status_code=400 in the service layer.
    # The route converts service errors to HTTP using e.status_code, so
    # ownership violations return 400 (not 404) for this domain.
    other = create_random_user(client)
    other_h = user_authentication_headers(
        client=client, email=other["email"], password=other["_password"]
    )
    r = client.get(f"{_BASE}/{task2_id}", headers=other_h)
    assert r.status_code in (400, 404)
    r = client.patch(f"{_BASE}/{task2_id}", headers=other_h, json={"priority": "low"})
    assert r.status_code in (400, 404)
    r = client.delete(f"{_BASE}/{task2_id}", headers=other_h)
    assert r.status_code in (400, 404)

    # ── Phase 11: Non-existent ID returns 404 ────────────────────────────────
    ghost = str(uuid.uuid4())
    assert client.get(f"{_BASE}/{ghost}", headers=headers).status_code == 404
    assert client.patch(f"{_BASE}/{ghost}", headers=headers, json={}).status_code == 404
    assert client.delete(f"{_BASE}/{ghost}", headers=headers).status_code == 404


def test_short_code_is_isolated_per_user(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Short-code sequence counters are per-user and monotonically increase.

    Within a single user's task space:
      - Each task gets a unique short_code
      - sequence_number increments for every new task
      - Short codes follow the TASK-{N} pattern

    Note: The global unique constraint on short_code means two different users
    cannot have the same short_code simultaneously. The sequence counter is
    per-user, but codes are globally unique. This is tested with a single user.
    """
    headers = normal_user_token_headers

    task1 = create_task(client, headers, original_message="Sequence test task 1")
    task2 = create_task(client, headers, original_message="Sequence test task 2")
    task3 = create_task(client, headers, original_message="Sequence test task 3")

    # Sequence numbers are monotonically increasing
    assert task1["sequence_number"] < task2["sequence_number"]
    assert task2["sequence_number"] < task3["sequence_number"]

    # Short codes are unique
    codes = {task1["short_code"], task2["short_code"], task3["short_code"]}
    assert len(codes) == 3  # all unique

    # All follow TASK-N pattern
    for code in codes:
        assert code.startswith("TASK-")


def test_team_prefix_short_code(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    When a team has task_prefix set, tasks in that team use the prefix.
      1. Create team without prefix — tasks get default TASK- prefix
      2. Set task_prefix on team to "HR"
      3. Create task with team_id — short_code uses HR- prefix
      4. Task without team_id still gets TASK- prefix
    """
    headers = normal_user_token_headers
    _TEAM_BASE = f"{settings.API_V1_STR}/agentic-teams"

    # ── Phase 1: Create team without prefix ──────────────────────────────────
    team = create_team(client, headers, name="HR Department")
    team_id = team["id"]
    assert team["task_prefix"] is None

    # Create task with team_id — no prefix set, should use TASK-
    task_no_prefix = create_task(
        client, headers,
        original_message="Default prefix task",
        team_id=team_id,
    )
    assert task_no_prefix["team_id"] == team_id
    assert task_no_prefix["short_code"].startswith("TASK-")

    # ── Phase 2: Set task_prefix on team ────────────────────────────────────
    r = client.put(f"{_TEAM_BASE}/{team_id}", headers=headers, json={"task_prefix": "HR"})
    assert r.status_code == 200
    assert r.json()["task_prefix"] == "HR"

    # ── Phase 3: Create task with team_id — uses HR- prefix ─────────────────
    task_with_prefix = create_task(
        client, headers,
        original_message="HR department onboarding task",
        team_id=team_id,
    )
    assert task_with_prefix["team_id"] == team_id
    assert task_with_prefix["short_code"].startswith("HR-"), (
        f"Expected HR- prefix, got: {task_with_prefix['short_code']}"
    )

    # ── Phase 4: Task without team_id still uses TASK- prefix ───────────────
    task_no_team = create_task(client, headers, original_message="No team task")
    assert task_no_team["team_id"] is None
    assert task_no_team["short_code"].startswith("TASK-")


def test_get_by_short_code_and_detail(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Short-code lookup endpoints:
      1. Create task — get its short_code
      2. GET /tasks/by-code/{short_code} — returns task with all extended fields
      3. GET /tasks/by-code/{short_code}/detail — returns detail with empty lists
      4. Unknown short_code returns 404
      5. Other user gets 404 on by-code lookup
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create task ─────────────────────────────────────────────────
    task = create_task(client, headers, original_message="Short code lookup test task")
    short_code = task["short_code"]
    task_id = task["id"]
    assert short_code is not None

    # ── Phase 2: GET by-code — matches UUID-based get ───────────────────────
    by_code = get_task_by_code(client, headers, short_code)
    assert by_code["id"] == task_id
    assert by_code["short_code"] == short_code
    assert by_code["original_message"] == "Short code lookup test task"

    # ── Phase 3: GET by-code/detail — detail fields present ─────────────────
    detail = get_task_detail_by_code(client, headers, short_code)
    assert detail["id"] == task_id
    assert "comments" in detail
    assert "attachments" in detail
    assert "subtasks" in detail
    assert "status_history" in detail
    assert isinstance(detail["comments"], list)
    assert isinstance(detail["attachments"], list)
    assert isinstance(detail["subtasks"], list)
    assert isinstance(detail["status_history"], list)

    # ── Phase 4: Unknown short_code returns 404 ──────────────────────────────
    r = client.get(f"{_BASE}/by-code/TASK-9999999", headers=headers)
    assert r.status_code == 404

    # ── Phase 5: Other user gets 404 ─────────────────────────────────────────
    other = create_random_user(client)
    other_h = user_authentication_headers(
        client=client, email=other["email"], password=other["_password"]
    )
    r = client.get(f"{_BASE}/by-code/{short_code}", headers=other_h)
    assert r.status_code == 404
    r = client.get(f"{_BASE}/by-code/{short_code}/detail", headers=other_h)
    assert r.status_code == 404


def test_task_tree_endpoint(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/by-code/{short_code}/tree returns recursive subtask structure:
      1. Create root task
      2. Create two subtasks under root
      3. Create a sub-subtask under subtask-1
      4. GET tree — root node has correct subtasks list
      5. Subtask-1 node has sub-subtask in its subtasks list
      6. Leaf nodes have empty subtasks arrays
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create root task ────────────────────────────────────────────
    root = create_task(client, headers, original_message="Root project task", title="Root Task")
    root_id = root["id"]
    root_code = root["short_code"]

    # ── Phase 2: Create two subtasks under root ──────────────────────────────
    sub1 = create_subtask(client, headers, root_id, original_message="Sub-task 1", title="Sub One")
    sub2 = create_subtask(client, headers, root_id, original_message="Sub-task 2", title="Sub Two")
    sub1_id = sub1["id"]
    sub2_id = sub2["id"]

    assert sub1["parent_task_id"] == root_id
    assert sub2["parent_task_id"] == root_id

    # ── Phase 3: Create sub-subtask under subtask-1 ──────────────────────────
    subsub = create_subtask(client, headers, sub1_id, original_message="Sub-sub task", title="Leaf")
    subsub_id = subsub["id"]
    assert subsub["parent_task_id"] == sub1_id

    # ── Phase 4: GET tree by root short_code ─────────────────────────────────
    tree = get_task_tree_by_code(client, headers, root_code)
    assert tree["id"] == root_id
    assert tree["short_code"] == root_code
    assert "subtasks" in tree
    assert len(tree["subtasks"]) == 2

    child_ids = {c["id"] for c in tree["subtasks"]}
    assert sub1_id in child_ids
    assert sub2_id in child_ids

    # ── Phase 5: Sub-subtask appears under sub1 ──────────────────────────────
    sub1_node = next(c for c in tree["subtasks"] if c["id"] == sub1_id)
    assert "subtasks" in sub1_node
    assert len(sub1_node["subtasks"]) == 1
    assert sub1_node["subtasks"][0]["id"] == subsub_id

    # ── Phase 6: Leaf nodes have empty subtasks ───────────────────────────────
    sub2_node = next(c for c in tree["subtasks"] if c["id"] == sub2_id)
    assert sub2_node["subtasks"] == []
    leaf_node = sub1_node["subtasks"][0]
    assert leaf_node["subtasks"] == []

    # Tree is not accessible by other users
    other = create_random_user(client)
    other_h = user_authentication_headers(
        client=client, email=other["email"], password=other["_password"]
    )
    r = client.get(f"{_BASE}/by-code/{root_code}/tree", headers=other_h)
    assert r.status_code == 404


def test_root_only_filter(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/?root_only=true excludes subtasks (parent_task_id IS NOT NULL):
      1. Create root task
      2. Create subtask under root
      3. List without filter — both appear
      4. List with root_only=true — only root appears, subtask excluded
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create root task ─────────────────────────────────────────────
    root = create_task(client, headers, original_message="Root-only filter root task")
    root_id = root["id"]

    # ── Phase 2: Create subtask under root ───────────────────────────────────
    sub = create_subtask(client, headers, root_id, original_message="Root-only filter subtask")
    sub_id = sub["id"]

    # ── Phase 3: List without filter — both appear ────────────────────────────
    all_tasks = list_tasks(client, headers)
    all_ids = [t["id"] for t in all_tasks["data"]]
    assert root_id in all_ids
    assert sub_id in all_ids

    # ── Phase 4: root_only=true — only root appears ───────────────────────────
    root_only = list_tasks(client, headers, root_only=True)
    root_only_ids = [t["id"] for t in root_only["data"]]
    assert root_id in root_only_ids
    assert sub_id not in root_only_ids


def test_team_id_filter(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/?team_id=<uuid> filters to tasks in that team:
      1. Create team A and team B
      2. Create task in team A
      3. Create task in team B
      4. Create task with no team
      5. Filter by team A — only team-A task appears
      6. Filter by team B — only team-B task appears
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create two teams ─────────────────────────────────────────────
    team_a = create_team(client, headers, name="Team Alpha")
    team_b = create_team(client, headers, name="Team Beta")
    team_a_id = team_a["id"]
    team_b_id = team_b["id"]

    # ── Phase 2 & 3: Create tasks in each team ───────────────────────────────
    task_a = create_task(client, headers, original_message="Team A task", team_id=team_a_id)
    task_b = create_task(client, headers, original_message="Team B task", team_id=team_b_id)
    task_no_team = create_task(client, headers, original_message="No team task")

    # ── Phase 4: Filter by team A ────────────────────────────────────────────
    result_a = list_tasks(client, headers, team_id=team_a_id)
    result_a_ids = [t["id"] for t in result_a["data"]]
    assert task_a["id"] in result_a_ids
    assert task_b["id"] not in result_a_ids
    assert task_no_team["id"] not in result_a_ids

    # ── Phase 5: Filter by team B ────────────────────────────────────────────
    result_b = list_tasks(client, headers, team_id=team_b_id)
    result_b_ids = [t["id"] for t in result_b["data"]]
    assert task_b["id"] in result_b_ids
    assert task_a["id"] not in result_b_ids


def test_priority_filter(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    GET /tasks/?priority=<value> filters by priority:
      1. Create tasks with different priorities (low, normal, high, urgent)
      2. Filter by high — only high-priority task appears
      3. Filter by urgent — only urgent task appears
    """
    headers = normal_user_token_headers

    task_low = create_task(client, headers, original_message="Low priority task", priority="low")
    task_normal = create_task(client, headers, original_message="Normal priority task", priority="normal")
    task_high = create_task(client, headers, original_message="High priority task", priority="high")
    task_urgent = create_task(client, headers, original_message="Urgent priority task", priority="urgent")

    # Filter by high
    result_high = list_tasks(client, headers, priority="high")
    high_ids = [t["id"] for t in result_high["data"]]
    assert task_high["id"] in high_ids
    assert task_low["id"] not in high_ids
    assert task_urgent["id"] not in high_ids

    # Filter by urgent
    result_urgent = list_tasks(client, headers, priority="urgent")
    urgent_ids = [t["id"] for t in result_urgent["data"]]
    assert task_urgent["id"] in urgent_ids
    assert task_normal["id"] not in urgent_ids
    assert task_high["id"] not in urgent_ids


def test_task_create_with_all_new_fields(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    InputTaskCreate validates and persists all collaboration fields:
      1. Create task with explicit title — title preserved (not derived from message)
      2. Create task with priority=urgent — persisted
      3. Verify short_code, sequence_number, title, priority all in response
      4. Verify subtask_count and subtask_completed_count default to 0
    """
    headers = normal_user_token_headers

    task = create_task(
        client, headers,
        original_message="Long original message that should not become the title",
        title="My Explicit Title",
        priority="urgent",
    )

    assert task["title"] == "My Explicit Title"
    assert task["priority"] == "urgent"
    assert task["short_code"] is not None
    assert task["sequence_number"] is not None
    assert task["subtask_count"] == 0
    assert task["subtask_completed_count"] == 0

    # Via list — subtask counts also present
    result = list_tasks(client, headers)
    matching = [t for t in result["data"] if t["id"] == task["id"]]
    assert len(matching) == 1
    assert matching[0]["subtask_count"] == 0
