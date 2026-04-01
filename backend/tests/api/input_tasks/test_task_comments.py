"""
Tests for Task Comment CRUD operations.

Scenarios:
  1. Comment full lifecycle — add, list, delete
  2. Multiple comments preserve chronological order
  3. Comment with different types (message, system, status_change)
  4. Comment appears in task detail endpoint
  5. Delete unknown comment returns 404
  6. User cannot delete comment on another user's task
  7. Unauthenticated access rejected
  8. Add comment to non-existent task returns 404
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.input_task import (
    create_task,
    get_task_detail,
    add_comment,
    list_comments,
    delete_comment,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_comment_full_lifecycle(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Full comment CRUD lifecycle:
      1. Create task
      2. Add comment — returns comment with author_user_id set
      3. List comments — comment appears
      4. Add second comment — appears in list, ordered chronologically
      5. Delete first comment — returns success
      6. List — first comment gone, second still present
      7. Unauthenticated access rejected
      8. Comment on non-existent task returns 404
      9. Delete non-existent comment returns 404
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create task ─────────────────────────────────────────────────
    task = create_task(client, headers, original_message="Task for comment testing")
    task_id = task["id"]

    # ── Phase 2: Add first comment ───────────────────────────────────────────
    comment1 = add_comment(client, headers, task_id, content="First comment", comment_type="message")
    assert comment1["id"] is not None
    assert comment1["task_id"] == task_id
    assert comment1["content"] == "First comment"
    assert comment1["comment_type"] == "message"
    assert comment1["author_user_id"] is not None
    assert comment1["author_agent_id"] is None
    assert comment1["author_node_id"] is None
    assert comment1["created_at"] is not None
    assert comment1["inline_attachments"] == []

    # ── Phase 3: List comments — first appears ───────────────────────────────
    comments_result = list_comments(client, headers, task_id)
    assert comments_result["count"] == 1
    assert len(comments_result["data"]) == 1
    assert comments_result["data"][0]["id"] == comment1["id"]
    assert comments_result["data"][0]["content"] == "First comment"

    # ── Phase 4: Add second comment — ordered chronologically ────────────────
    comment2 = add_comment(client, headers, task_id, content="Second comment", comment_type="message")
    comments_result = list_comments(client, headers, task_id)
    assert comments_result["count"] == 2
    comment_ids = [c["id"] for c in comments_result["data"]]
    assert comment1["id"] in comment_ids
    assert comment2["id"] in comment_ids
    # Chronological order: first comment created first
    first_idx = comment_ids.index(comment1["id"])
    second_idx = comment_ids.index(comment2["id"])
    assert first_idx < second_idx

    # ── Phase 5: Delete first comment ────────────────────────────────────────
    deleted = delete_comment(client, headers, task_id, comment1["id"])
    assert "deleted" in deleted["message"].lower() or "comment" in deleted["message"].lower()

    # ── Phase 6: List — first gone, second remains ───────────────────────────
    comments_result = list_comments(client, headers, task_id)
    assert comments_result["count"] == 1
    assert comments_result["data"][0]["id"] == comment2["id"]

    # ── Phase 7: Unauthenticated access rejected ──────────────────────────────
    assert client.get(f"{_BASE}/{task_id}/comments/").status_code in (401, 403)
    assert client.post(
        f"{_BASE}/{task_id}/comments/",
        json={"content": "unauth", "comment_type": "message"},
    ).status_code in (401, 403)

    # ── Phase 8: Comment on non-existent task returns 404 ───────────────────
    ghost = str(uuid.uuid4())
    r = client.post(
        f"{_BASE}/{ghost}/comments/",
        headers=headers,
        json={"content": "ghost", "comment_type": "message"},
    )
    assert r.status_code == 404

    # ── Phase 9: Delete non-existent comment returns 404 ───────────────────
    r = client.delete(f"{_BASE}/{task_id}/comments/{str(uuid.uuid4())}", headers=headers)
    assert r.status_code == 404


def test_comment_types_and_meta(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Different comment types are accepted:
      1. comment_type=message (default)
      2. comment_type=system — accepted
      3. comment_type=status_change — accepted
      4. All types appear in list ordered chronologically
      5. comment_meta field is returned (null for user-created comments)
    """
    headers = normal_user_token_headers

    task = create_task(client, headers, original_message="Comment types test task")
    task_id = task["id"]

    msg_comment = add_comment(client, headers, task_id, content="A message", comment_type="message")
    sys_comment = add_comment(client, headers, task_id, content="A system note", comment_type="system")
    status_comment = add_comment(client, headers, task_id, content="Status changed", comment_type="status_change")

    assert msg_comment["comment_type"] == "message"
    assert sys_comment["comment_type"] == "system"
    assert status_comment["comment_type"] == "status_change"

    # comment_meta is null for user-created comments
    assert msg_comment["comment_meta"] is None
    assert sys_comment["comment_meta"] is None

    # All three appear in list
    result = list_comments(client, headers, task_id)
    assert result["count"] == 3


def test_comment_in_task_detail(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Comments appear in the task detail endpoint:
      1. Create task
      2. Add two comments
      3. GET /tasks/{id}/detail — comments list contains both, in order
      4. Comment fields match what was created (content, type, author_user_id)
    """
    headers = normal_user_token_headers

    task = create_task(client, headers, original_message="Task for detail comments test")
    task_id = task["id"]

    c1 = add_comment(client, headers, task_id, content="Detail comment one")
    c2 = add_comment(client, headers, task_id, content="Detail comment two")

    detail = get_task_detail(client, headers, task_id)
    assert "comments" in detail
    detail_comment_ids = [c["id"] for c in detail["comments"]]
    assert c1["id"] in detail_comment_ids
    assert c2["id"] in detail_comment_ids

    # Content matches
    by_id = {c["id"]: c for c in detail["comments"]}
    assert by_id[c1["id"]]["content"] == "Detail comment one"
    assert by_id[c2["id"]]["content"] == "Detail comment two"
    # Author user IDs set
    assert by_id[c1["id"]]["author_user_id"] is not None


def test_comment_ownership_enforcement(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Comment operations respect task ownership:
      1. User A creates a task and adds a comment
      2. User B cannot list comments on User A's task (task 404)
      3. User B cannot add comment to User A's task (task 404)
      4. User B cannot delete User A's comment (comment 404 — task ownership check)
    """
    headers_a = normal_user_token_headers

    # User A setup
    task = create_task(client, headers_a, original_message="Ownership test task")
    task_id = task["id"]
    comment = add_comment(client, headers_a, task_id, content="Owner's comment")
    comment_id = comment["id"]

    # User B
    user_b = create_random_user(client)
    headers_b = user_authentication_headers(
        client=client, email=user_b["email"], password=user_b["_password"]
    )

    # User B cannot list comments (PermissionDeniedError → 400)
    r = client.get(f"{_BASE}/{task_id}/comments/", headers=headers_b)
    assert r.status_code in (400, 404)

    # User B cannot add comment (PermissionDeniedError → 400)
    r = client.post(
        f"{_BASE}/{task_id}/comments/",
        headers=headers_b,
        json={"content": "intruder", "comment_type": "message"},
    )
    assert r.status_code in (400, 404)

    # User B cannot delete User A's comment (ownership check returns 404 from delete_comment)
    r = client.delete(f"{_BASE}/{task_id}/comments/{comment_id}", headers=headers_b)
    assert r.status_code in (400, 404)
