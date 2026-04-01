"""Helpers for InputTask API tests — tasks, comments, attachments, subtasks."""
import io
from uuid import UUID

from fastapi.testclient import TestClient

from app.core.config import settings

_BASE = f"{settings.API_V1_STR}/tasks"


# ---------------------------------------------------------------------------
# Task helpers
# ---------------------------------------------------------------------------

def create_task(
    client: TestClient,
    headers: dict,
    original_message: str = "Test task description",
    title: str | None = None,
    priority: str = "normal",
    selected_agent_id: str | None = None,
    team_id: str | None = None,
    assigned_node_id: str | None = None,
    parent_task_id: str | None = None,
) -> dict:
    """POST /tasks/ — asserts 200 and returns body."""
    payload: dict = {"original_message": original_message, "priority": priority}
    if title is not None:
        payload["title"] = title
    if selected_agent_id is not None:
        payload["selected_agent_id"] = selected_agent_id
    if team_id is not None:
        payload["team_id"] = team_id
    if assigned_node_id is not None:
        payload["assigned_node_id"] = assigned_node_id
    if parent_task_id is not None:
        payload["parent_task_id"] = parent_task_id
    r = client.post(_BASE + "/", headers=headers, json=payload)
    assert r.status_code == 200, f"Task creation failed: {r.text}"
    return r.json()


def get_task(client: TestClient, headers: dict, task_id: str) -> dict:
    """GET /tasks/{task_id} — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{task_id}", headers=headers)
    assert r.status_code == 200, f"Get task failed: {r.text}"
    return r.json()


def get_task_detail(client: TestClient, headers: dict, task_id: str) -> dict:
    """GET /tasks/{task_id}/detail — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{task_id}/detail", headers=headers)
    assert r.status_code == 200, f"Get task detail failed: {r.text}"
    return r.json()


def get_task_by_code(client: TestClient, headers: dict, short_code: str) -> dict:
    """GET /tasks/by-code/{short_code} — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/by-code/{short_code}", headers=headers)
    assert r.status_code == 200, f"Get task by code failed: {r.text}"
    return r.json()


def get_task_detail_by_code(client: TestClient, headers: dict, short_code: str) -> dict:
    """GET /tasks/by-code/{short_code}/detail — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/by-code/{short_code}/detail", headers=headers)
    assert r.status_code == 200, f"Get task detail by code failed: {r.text}"
    return r.json()


def get_task_tree_by_code(client: TestClient, headers: dict, short_code: str) -> dict:
    """GET /tasks/by-code/{short_code}/tree — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/by-code/{short_code}/tree", headers=headers)
    assert r.status_code == 200, f"Get task tree by code failed: {r.text}"
    return r.json()


def list_tasks(
    client: TestClient,
    headers: dict,
    status: str | None = None,
    root_only: bool = False,
    team_id: str | None = None,
    priority: str | None = None,
) -> dict:
    """GET /tasks/ — asserts 200 and returns full body (data + count)."""
    params: dict = {}
    if status is not None:
        params["status"] = status
    if root_only:
        params["root_only"] = "true"
    if team_id is not None:
        params["team_id"] = team_id
    if priority is not None:
        params["priority"] = priority
    r = client.get(_BASE + "/", headers=headers, params=params)
    assert r.status_code == 200, f"List tasks failed: {r.text}"
    return r.json()


def update_task(
    client: TestClient,
    headers: dict,
    task_id: str,
    **fields,
) -> dict:
    """PATCH /tasks/{task_id} — asserts 200 and returns body."""
    r = client.patch(f"{_BASE}/{task_id}", headers=headers, json=fields)
    assert r.status_code == 200, f"Update task failed: {r.text}"
    return r.json()


def delete_task(client: TestClient, headers: dict, task_id: str) -> dict:
    """DELETE /tasks/{task_id} — asserts 200 and returns body."""
    r = client.delete(f"{_BASE}/{task_id}", headers=headers)
    assert r.status_code == 200, f"Delete task failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Comment helpers
# ---------------------------------------------------------------------------

def add_comment(
    client: TestClient,
    headers: dict,
    task_id: str,
    content: str = "Test comment",
    comment_type: str = "message",
) -> dict:
    """POST /tasks/{task_id}/comments/ — asserts 200 and returns body."""
    payload = {"content": content, "comment_type": comment_type}
    r = client.post(f"{_BASE}/{task_id}/comments/", headers=headers, json=payload)
    assert r.status_code == 200, f"Add comment failed: {r.text}"
    return r.json()


def list_comments(client: TestClient, headers: dict, task_id: str) -> dict:
    """GET /tasks/{task_id}/comments/ — asserts 200 and returns full body."""
    r = client.get(f"{_BASE}/{task_id}/comments/", headers=headers)
    assert r.status_code == 200, f"List comments failed: {r.text}"
    return r.json()


def delete_comment(client: TestClient, headers: dict, task_id: str, comment_id: str) -> dict:
    """DELETE /tasks/{task_id}/comments/{comment_id} — asserts 200 and returns body."""
    r = client.delete(f"{_BASE}/{task_id}/comments/{comment_id}", headers=headers)
    assert r.status_code == 200, f"Delete comment failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Attachment helpers
# ---------------------------------------------------------------------------

def upload_attachment(
    client: TestClient,
    headers: dict,
    task_id: str,
    content: bytes = b"Hello attachment content",
    filename: str = "test_file.txt",
    content_type: str = "text/plain",
) -> dict:
    """POST /tasks/{task_id}/attachments/ — asserts 200 and returns body."""
    r = client.post(
        f"{_BASE}/{task_id}/attachments/",
        headers=headers,
        files={"file": (filename, io.BytesIO(content), content_type)},
    )
    assert r.status_code == 200, f"Upload attachment failed: {r.text}"
    return r.json()


def list_attachments(client: TestClient, headers: dict, task_id: str) -> dict:
    """GET /tasks/{task_id}/attachments/ — asserts 200 and returns full body."""
    r = client.get(f"{_BASE}/{task_id}/attachments/", headers=headers)
    assert r.status_code == 200, f"List attachments failed: {r.text}"
    return r.json()


def delete_attachment(
    client: TestClient, headers: dict, task_id: str, attachment_id: str
) -> dict:
    """DELETE /tasks/{task_id}/attachments/{attachment_id} — asserts 200 and returns body."""
    r = client.delete(f"{_BASE}/{task_id}/attachments/{attachment_id}", headers=headers)
    assert r.status_code == 200, f"Delete attachment failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# Subtask helpers
# ---------------------------------------------------------------------------

def create_subtask(
    client: TestClient,
    headers: dict,
    parent_task_id: str,
    original_message: str = "Subtask description",
    title: str | None = None,
    priority: str = "normal",
) -> dict:
    """POST /tasks/{parent_task_id}/subtasks/ — asserts 200 and returns body."""
    payload: dict = {"original_message": original_message, "priority": priority}
    if title is not None:
        payload["title"] = title
    r = client.post(f"{_BASE}/{parent_task_id}/subtasks/", headers=headers, json=payload)
    assert r.status_code == 200, f"Create subtask failed: {r.text}"
    return r.json()


def list_subtasks(client: TestClient, headers: dict, task_id: str) -> dict:
    """GET /tasks/{task_id}/subtasks/ — asserts 200 and returns full body."""
    r = client.get(f"{_BASE}/{task_id}/subtasks/", headers=headers)
    assert r.status_code == 200, f"List subtasks failed: {r.text}"
    return r.json()
