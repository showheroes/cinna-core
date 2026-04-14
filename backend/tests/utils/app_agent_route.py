"""Helper utilities for App Agent Route API calls in tests."""
import uuid
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.utils import random_lower_string

_ADMIN_BASE = f"{settings.API_V1_STR}/admin/app-agent-routes"
_USER_BASE = f"{settings.API_V1_STR}/users/me/app-agent-routes"


# ---------------------------------------------------------------------------
# Admin route helpers
# ---------------------------------------------------------------------------


def create_admin_route(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    *,
    name: str | None = None,
    session_mode: str = "conversation",
    trigger_prompt: str | None = None,
    message_patterns: str | None = None,
    channel_app_mcp: bool = True,
    is_active: bool = True,
    auto_enable_for_users: bool = False,
    assigned_user_ids: list[str] | None = None,
) -> dict:
    """Create an admin app agent route via POST /admin/app-agent-routes/."""
    payload: dict = {
        "name": name or f"route-{random_lower_string()[:8]}",
        "agent_id": agent_id,
        "session_mode": session_mode,
        "trigger_prompt": trigger_prompt or f"Handle {random_lower_string()[:8]} requests",
        "channel_app_mcp": channel_app_mcp,
        "is_active": is_active,
        "auto_enable_for_users": auto_enable_for_users,
        "assigned_user_ids": assigned_user_ids or [],
    }
    if message_patterns is not None:
        payload["message_patterns"] = message_patterns
    r = client.post(_ADMIN_BASE + "/", headers=token_headers, json=payload)
    assert r.status_code == 200, f"Admin route creation failed: {r.text}"
    return r.json()


def get_admin_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
) -> dict:
    """Get a single admin app agent route via GET /admin/app-agent-routes/{id}."""
    r = client.get(f"{_ADMIN_BASE}/{route_id}", headers=token_headers)
    assert r.status_code == 200, f"Get admin route failed: {r.text}"
    return r.json()


def list_admin_routes(
    client: TestClient,
    token_headers: dict[str, str],
) -> list[dict]:
    """List all admin app agent routes via GET /admin/app-agent-routes/."""
    r = client.get(_ADMIN_BASE + "/", headers=token_headers)
    assert r.status_code == 200, f"List admin routes failed: {r.text}"
    return r.json()


def update_admin_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
    **fields,
) -> dict:
    """Update an admin app agent route via PUT /admin/app-agent-routes/{id}."""
    r = client.put(f"{_ADMIN_BASE}/{route_id}", headers=token_headers, json=fields)
    assert r.status_code == 200, f"Update admin route failed: {r.text}"
    return r.json()


def delete_admin_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
) -> dict:
    """Delete an admin app agent route via DELETE /admin/app-agent-routes/{id}."""
    r = client.delete(f"{_ADMIN_BASE}/{route_id}", headers=token_headers)
    assert r.status_code == 200, f"Delete admin route failed: {r.text}"
    return r.json()


def assign_users_to_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
    user_ids: list[str],
) -> list[dict]:
    """Assign users to an admin route via POST /admin/app-agent-routes/{id}/assignments."""
    r = client.post(
        f"{_ADMIN_BASE}/{route_id}/assignments",
        headers=token_headers,
        json=[str(uid) for uid in user_ids],
    )
    assert r.status_code == 200, f"Assign users failed: {r.text}"
    return r.json()


def remove_user_assignment(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
    user_id: str,
) -> dict:
    """Remove a user from an admin route via DELETE /admin/app-agent-routes/{id}/assignments/{user_id}."""
    r = client.delete(
        f"{_ADMIN_BASE}/{route_id}/assignments/{user_id}",
        headers=token_headers,
    )
    assert r.status_code == 200, f"Remove assignment failed: {r.text}"
    return r.json()


# ---------------------------------------------------------------------------
# User personal route helpers
# ---------------------------------------------------------------------------


def create_user_route(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    *,
    session_mode: str = "conversation",
    trigger_prompt: str | None = None,
    message_patterns: str | None = None,
    channel_app_mcp: bool = True,
    is_active: bool = True,
) -> dict:
    """Create a personal app agent route via POST /users/me/app-agent-routes/."""
    payload: dict = {
        "agent_id": agent_id,
        "session_mode": session_mode,
        "trigger_prompt": trigger_prompt or f"Handle {random_lower_string()[:8]} tasks",
        "channel_app_mcp": channel_app_mcp,
        "is_active": is_active,
    }
    if message_patterns is not None:
        payload["message_patterns"] = message_patterns
    r = client.post(_USER_BASE + "/", headers=token_headers, json=payload)
    assert r.status_code == 200, f"User route creation failed: {r.text}"
    return r.json()


def list_user_routes(
    client: TestClient,
    token_headers: dict[str, str],
) -> dict:
    """List user's personal + admin-assigned routes via GET /users/me/app-agent-routes/."""
    r = client.get(_USER_BASE + "/", headers=token_headers)
    assert r.status_code == 200, f"List user routes failed: {r.text}"
    return r.json()


def update_user_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
    **fields,
) -> dict:
    """Update a personal app agent route via PUT /users/me/app-agent-routes/{id}."""
    r = client.put(f"{_USER_BASE}/{route_id}", headers=token_headers, json=fields)
    assert r.status_code == 200, f"Update user route failed: {r.text}"
    return r.json()


def delete_user_route(
    client: TestClient,
    token_headers: dict[str, str],
    route_id: str,
) -> dict:
    """Delete a personal app agent route via DELETE /users/me/app-agent-routes/{id}."""
    r = client.delete(f"{_USER_BASE}/{route_id}", headers=token_headers)
    assert r.status_code == 200, f"Delete user route failed: {r.text}"
    return r.json()


def toggle_admin_assignment(
    client: TestClient,
    token_headers: dict[str, str],
    assignment_id: str,
    is_enabled: bool,
) -> dict:
    """Toggle an admin-assigned route on/off via PATCH /users/me/app-agent-routes/admin-assignments/{id}."""
    r = client.patch(
        f"{_USER_BASE}/admin-assignments/{assignment_id}",
        headers=token_headers,
        params={"is_enabled": str(is_enabled).lower()},
    )
    assert r.status_code == 200, f"Toggle assignment failed: {r.text}"
    return r.json()
