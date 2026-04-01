"""
Tests for Task Attachment upload, list, download, and delete operations.

Scenarios:
  1. Attachment full lifecycle — upload, list, download, delete
  2. Multiple attachments on a task — all returned in list
  3. Attachment fields in response (file_name, content_type, upload_by, download_url)
  4. Attachments appear in task detail endpoint
  5. Delete non-existent attachment returns 404
  6. Download non-existent attachment returns 404
  7. Other user cannot access attachments
"""
import io
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.input_task import (
    create_task,
    get_task_detail,
    upload_attachment,
    list_attachments,
    delete_attachment,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_attachment_full_lifecycle(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Full attachment lifecycle:
      1. Create task
      2. Upload attachment — returns attachment record with correct fields
      3. List attachments — attachment appears
      4. Download attachment — returns file content
      5. Delete attachment — returns success
      6. List — attachment gone
      7. Download after delete — 404
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create task ─────────────────────────────────────────────────
    task = create_task(client, headers, original_message="Task for attachment testing")
    task_id = task["id"]

    # ── Phase 2: Upload attachment ───────────────────────────────────────────
    file_content = b"Hello, this is a test file attachment."
    attachment = upload_attachment(
        client, headers, task_id,
        content=file_content,
        filename="report.txt",
        content_type="text/plain",
    )

    assert attachment["id"] is not None
    assert attachment["task_id"] == task_id
    assert attachment["file_name"] == "report.txt"
    assert attachment["content_type"] == "text/plain"
    assert attachment["file_size"] == len(file_content)
    assert attachment["uploaded_by_user_id"] is not None
    assert attachment["uploaded_by_agent_id"] is None
    assert attachment["comment_id"] is None
    assert attachment["source_agent_id"] is None
    assert attachment["source_workspace_path"] is None
    assert attachment["created_at"] is not None
    # download_url should be populated
    assert attachment["download_url"] is not None
    assert attachment["id"] in attachment["download_url"]

    attachment_id = attachment["id"]

    # ── Phase 3: List attachments — appears ──────────────────────────────────
    att_list = list_attachments(client, headers, task_id)
    assert att_list["count"] == 1
    assert len(att_list["data"]) == 1
    assert att_list["data"][0]["id"] == attachment_id

    # ── Phase 4: Download attachment ─────────────────────────────────────────
    r = client.get(
        f"{_BASE}/{task_id}/attachments/{attachment_id}/download",
        headers=headers,
    )
    assert r.status_code == 200
    assert r.content == file_content

    # ── Phase 5: Delete attachment ────────────────────────────────────────────
    deleted = delete_attachment(client, headers, task_id, attachment_id)
    assert "deleted" in deleted["message"].lower() or "attachment" in deleted["message"].lower()

    # ── Phase 6: List — gone ─────────────────────────────────────────────────
    att_list = list_attachments(client, headers, task_id)
    assert att_list["count"] == 0

    # ── Phase 7: Download after delete — 404 ────────────────────────────────
    r = client.get(
        f"{_BASE}/{task_id}/attachments/{attachment_id}/download",
        headers=headers,
    )
    assert r.status_code == 404


def test_multiple_attachments(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Multiple attachments on a task are all returned in list:
      1. Create task
      2. Upload three different attachments
      3. List — all three appear with correct file names
      4. Each attachment has its own unique ID
    """
    headers = normal_user_token_headers

    task = create_task(client, headers, original_message="Multi-attachment task")
    task_id = task["id"]

    files = [
        (b"data for csv", "data.csv", "text/csv"),
        (b"image content", "chart.png", "image/png"),
        (b"# Report\n\nContent", "report.md", "text/markdown"),
    ]

    attachment_ids = set()
    for content, filename, ct in files:
        att = upload_attachment(client, headers, task_id, content=content, filename=filename, content_type=ct)
        assert att["file_name"] == filename
        attachment_ids.add(att["id"])

    att_list = list_attachments(client, headers, task_id)
    assert att_list["count"] == 3
    listed_ids = {a["id"] for a in att_list["data"]}
    assert attachment_ids == listed_ids


def test_attachment_in_task_detail(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Attachments appear in GET /tasks/{id}/detail:
      1. Create task
      2. Upload attachment
      3. GET detail — attachments list contains the uploaded file
      4. Attachment fields match what was returned by upload
    """
    headers = normal_user_token_headers

    task = create_task(client, headers, original_message="Task for detail attachments test")
    task_id = task["id"]

    att = upload_attachment(client, headers, task_id, content=b"detail test", filename="detail.txt")
    att_id = att["id"]

    detail = get_task_detail(client, headers, task_id)
    assert "attachments" in detail
    att_ids_in_detail = [a["id"] for a in detail["attachments"]]
    assert att_id in att_ids_in_detail

    by_id = {a["id"]: a for a in detail["attachments"]}
    assert by_id[att_id]["file_name"] == "detail.txt"


def test_attachment_ownership_enforcement(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Attachment operations respect task ownership:
      1. User A creates task and uploads attachment
      2. User B cannot list attachments (task 404)
      3. User B cannot upload to User A's task (task 404)
      4. User B cannot delete User A's attachment (403)
      5. User B cannot download User A's attachment (403)
      6. Delete non-existent attachment returns 404
    """
    headers_a = normal_user_token_headers

    task = create_task(client, headers_a, original_message="Attachment ownership task")
    task_id = task["id"]
    att = upload_attachment(client, headers_a, task_id, content=b"owner content", filename="owner.txt")
    att_id = att["id"]

    user_b = create_random_user(client)
    headers_b = user_authentication_headers(
        client=client, email=user_b["email"], password=user_b["_password"]
    )

    # Cannot list (PermissionDeniedError → 400)
    r = client.get(f"{_BASE}/{task_id}/attachments/", headers=headers_b)
    assert r.status_code in (400, 404)

    # Cannot upload (PermissionDeniedError → 400)
    r = client.post(
        f"{_BASE}/{task_id}/attachments/",
        headers=headers_b,
        files={"file": ("intruder.txt", io.BytesIO(b"intruder"), "text/plain")},
    )
    assert r.status_code in (400, 404)

    # Cannot download (403 — task ownership enforced in service)
    r = client.get(
        f"{_BASE}/{task_id}/attachments/{att_id}/download",
        headers=headers_b,
    )
    assert r.status_code in (403, 404)

    # Cannot delete (403)
    r = client.delete(f"{_BASE}/{task_id}/attachments/{att_id}", headers=headers_b)
    assert r.status_code in (403, 404)

    # Delete non-existent attachment returns 404 (for owner)
    ghost_id = str(uuid.uuid4())
    r = client.delete(f"{_BASE}/{task_id}/attachments/{ghost_id}", headers=headers_a)
    assert r.status_code == 404
