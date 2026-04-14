"""
Integration tests for the App Agent Routes API.

Three scenario-based tests covering the full surface:
  1. Admin Route Lifecycle    — CRUD, assignment management, auth guards
  2. User Personal Routes     — personal CRUD, ownership guard, admin-route listing
  3. Admin-Assignment Toggle  — user enables/disables admin-assigned routes
"""

import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.app_agent_route import (
    assign_users_to_route,
    create_admin_route,
    create_user_route,
    delete_admin_route,
    delete_user_route,
    get_admin_route,
    list_admin_routes,
    list_user_routes,
    remove_user_assignment,
    toggle_admin_assignment,
    update_admin_route,
    update_user_route,
)
from tests.utils.background_tasks import drain_tasks
from tests.utils.user import create_random_user_with_headers, user_authentication_headers
from tests.utils.utils import random_lower_string

_ADMIN_BASE = f"{settings.API_V1_STR}/admin/app-agent-routes"
_USER_BASE = f"{settings.API_V1_STR}/users/me/app-agent-routes"


# ---------------------------------------------------------------------------
# Scenario 1: Admin Route Lifecycle
# ---------------------------------------------------------------------------


def test_admin_route_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full admin route management lifecycle:
      1.  Unauthenticated requests are rejected
      2.  Non-admin users get 403 on all admin endpoints
      3.  Create admin route — verify initial fields
      4.  Route appears in list
      5.  GET by ID — fields match
      6.  Update route — changes persist
      7.  Non-existent ID returns 404
      8.  Assign users to route — assignment appears in response
      9.  Duplicate assignment is skipped (idempotent)
      10. Remove user assignment
      11. Delete route — gone (404)
    """
    # ── Phase 1: No auth ───────────────────────────────────────────────────
    assert client.get(f"{_ADMIN_BASE}/").status_code in (401, 403)
    assert client.post(f"{_ADMIN_BASE}/", json={}).status_code in (401, 403)

    # ── Phase 2: Non-admin gets 403 ────────────────────────────────────────
    other_user, other_headers = create_random_user_with_headers(client)

    assert client.get(f"{_ADMIN_BASE}/", headers=other_headers).status_code == 403
    assert client.post(
        f"{_ADMIN_BASE}/", headers=other_headers,
        json={"name": "x", "agent_id": str(uuid.uuid4()), "trigger_prompt": "test"},
    ).status_code == 403

    # ── Phase 3: Create admin route ────────────────────────────────────────
    # Agent creation requires a running environment stub (active via conftest fixtures).
    agent = create_agent_via_api(client, superuser_token_headers, name="Route Test Agent")
    drain_tasks()
    agent_id = agent["id"]

    route_name = f"test-route-{random_lower_string()[:8]}"
    trigger = "Handle all document signing requests"
    patterns = "sign *\nsign this *"

    route = create_admin_route(
        client,
        superuser_token_headers,
        agent_id=agent_id,
        name=route_name,
        trigger_prompt=trigger,
        message_patterns=patterns,
        session_mode="conversation",
        channel_app_mcp=True,
        is_active=True,
    )
    route_id = route["id"]

    assert route["name"] == route_name
    assert route["agent_id"] == agent_id
    assert route["trigger_prompt"] == trigger
    assert route["message_patterns"] == patterns
    assert route["session_mode"] == "conversation"
    assert route["channel_app_mcp"] is True
    assert route["is_active"] is True
    assert route["assignments"] == []
    assert "created_at" in route
    assert "updated_at" in route
    assert "created_by" in route

    # ── Phase 4: List → route is present ──────────────────────────────────
    routes = list_admin_routes(client, superuser_token_headers)
    assert any(r["id"] == route_id for r in routes)

    # ── Phase 5: GET by ID ─────────────────────────────────────────────────
    fetched = get_admin_route(client, superuser_token_headers, route_id)
    assert fetched["id"] == route_id
    assert fetched["name"] == route_name
    assert fetched["agent_id"] == agent_id

    # Non-admin cannot GET by ID either
    assert client.get(
        f"{_ADMIN_BASE}/{route_id}", headers=other_headers
    ).status_code == 403

    # ── Phase 6: Update route ──────────────────────────────────────────────
    new_name = f"renamed-{random_lower_string()[:8]}"
    updated = update_admin_route(
        client, superuser_token_headers, route_id,
        name=new_name,
        trigger_prompt="Handle contract signing requests",
        is_active=False,
    )
    assert updated["name"] == new_name
    assert updated["trigger_prompt"] == "Handle contract signing requests"
    assert updated["is_active"] is False

    # Verify update persisted via GET
    re_fetched = get_admin_route(client, superuser_token_headers, route_id)
    assert re_fetched["name"] == new_name
    assert re_fetched["is_active"] is False

    # Non-admin cannot update
    assert client.put(
        f"{_ADMIN_BASE}/{route_id}", headers=other_headers, json={"name": "hacked"}
    ).status_code == 403

    # ── Phase 7: Non-existent ID returns 404 ─────────────────────────────
    ghost = str(uuid.uuid4())
    assert client.get(
        f"{_ADMIN_BASE}/{ghost}", headers=superuser_token_headers
    ).status_code == 404
    assert client.put(
        f"{_ADMIN_BASE}/{ghost}", headers=superuser_token_headers, json={"name": "x"}
    ).status_code == 404
    assert client.delete(
        f"{_ADMIN_BASE}/{ghost}", headers=superuser_token_headers
    ).status_code == 404

    # ── Phase 8: Assign users to route ────────────────────────────────────
    user_a, _ = create_random_user_with_headers(client)
    user_b, _ = create_random_user_with_headers(client)

    # Enable auto_enable_for_users on the route first so assignments are is_enabled=True
    update_admin_route(
        client, superuser_token_headers, route_id,
        auto_enable_for_users=True,
        is_active=False,  # keep is_active=False from Phase 6 update
    )

    assignments = assign_users_to_route(
        client, superuser_token_headers, route_id,
        user_ids=[user_a["id"], user_b["id"]],
    )
    assert len(assignments) == 2
    assigned_user_ids = {a["user_id"] for a in assignments}
    assert user_a["id"] in assigned_user_ids
    assert user_b["id"] in assigned_user_ids
    # Assignments are enabled because auto_enable_for_users=True on the route
    assert all(a["is_enabled"] is True for a in assignments)
    assert all(a["route_id"] == route_id for a in assignments)

    # Verify assignments appear in GET response
    route_with_assignments = get_admin_route(client, superuser_token_headers, route_id)
    assert len(route_with_assignments["assignments"]) == 2

    # Non-admin cannot assign users
    assert client.post(
        f"{_ADMIN_BASE}/{route_id}/assignments",
        headers=other_headers,
        json=[str(uuid.uuid4())],
    ).status_code == 403

    # ── Phase 9: Duplicate assignment is skipped (idempotent) ─────────────
    assignments_after_dup = assign_users_to_route(
        client, superuser_token_headers, route_id,
        user_ids=[user_a["id"]],  # already assigned
    )
    # Still only 2 total assignments — no duplicate created
    assert len(assignments_after_dup) == 2

    # ── Phase 10: Remove assignment ────────────────────────────────────────
    remove_user_assignment(
        client, superuser_token_headers, route_id, user_id=user_a["id"]
    )

    route_after_remove = get_admin_route(client, superuser_token_headers, route_id)
    remaining_user_ids = {a["user_id"] for a in route_after_remove["assignments"]}
    assert user_a["id"] not in remaining_user_ids
    assert user_b["id"] in remaining_user_ids

    # Removing non-existent assignment returns 404
    assert client.delete(
        f"{_ADMIN_BASE}/{route_id}/assignments/{user_a['id']}",
        headers=superuser_token_headers,
    ).status_code == 404

    # Non-admin cannot remove assignments
    assert client.delete(
        f"{_ADMIN_BASE}/{route_id}/assignments/{user_b['id']}",
        headers=other_headers,
    ).status_code == 403

    # ── Phase 11: Delete route → gone ─────────────────────────────────────
    deleted = delete_admin_route(client, superuser_token_headers, route_id)
    assert "message" in deleted

    assert client.get(
        f"{_ADMIN_BASE}/{route_id}", headers=superuser_token_headers
    ).status_code == 404

    # Route no longer in list
    remaining_routes = list_admin_routes(client, superuser_token_headers)
    assert not any(r["id"] == route_id for r in remaining_routes)

    # Non-admin cannot delete
    assert client.delete(
        f"{_ADMIN_BASE}/{route_id}", headers=other_headers
    ).status_code == 403


# ---------------------------------------------------------------------------
# Scenario 2: Admin route created with initial user assignments
# ---------------------------------------------------------------------------


def test_admin_route_create_with_assignments(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Admin can create a route with initial user assignments in a single call:
      1. Create two users
      2. Create route with both users in assigned_user_ids
      3. Verify both assignments appear immediately in the response
      4. Verify both assignments appear in GET by ID
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Batch Assign Agent")
    drain_tasks()
    agent_id = agent["id"]

    user_a, _ = create_random_user_with_headers(client)
    user_b, _ = create_random_user_with_headers(client)

    # ── Phase 1: Create with assignments ──────────────────────────────────
    r = client.post(
        f"{_ADMIN_BASE}/",
        headers=superuser_token_headers,
        json={
            "name": f"batch-route-{random_lower_string()[:8]}",
            "agent_id": agent_id,
            "trigger_prompt": "Handle batch test requests",
            "assigned_user_ids": [user_a["id"], user_b["id"]],
        },
    )
    assert r.status_code == 200
    route = r.json()
    route_id = route["id"]

    # ── Phase 2: Assignments present in creation response ─────────────────
    assert len(route["assignments"]) == 2
    assigned_ids = {a["user_id"] for a in route["assignments"]}
    assert user_a["id"] in assigned_ids
    assert user_b["id"] in assigned_ids

    # ── Phase 3: Verify via GET ────────────────────────────────────────────
    fetched = get_admin_route(client, superuser_token_headers, route_id)
    assert len(fetched["assignments"]) == 2


# ---------------------------------------------------------------------------
# Scenario 3: User personal routes lifecycle
# ---------------------------------------------------------------------------


def test_user_personal_route_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    User personal route management lifecycle:
      1. Unauthenticated requests are rejected
      2. Create personal route for own agent — verify fields
      3. Route appears in personal_routes list
      4. Update personal route — changes persist
      5. Cannot create route for agent not owned by user
      6. Other user cannot update or delete the route
      7. Delete route — gone from list
    """
    # ── Phase 1: No auth ───────────────────────────────────────────────────
    assert client.get(f"{_USER_BASE}/").status_code in (401, 403)
    assert client.post(f"{_USER_BASE}/", json={}).status_code in (401, 403)

    # ── Phase 2: Create personal route for own agent ───────────────────────
    # Regular user signs up and creates an agent
    user, user_headers = create_random_user_with_headers(client)

    # Superuser creates an agent for the test user
    # (agent creation requires superuser because agents API may restrict it — use superuser)
    agent = create_agent_via_api(client, superuser_token_headers, name="User Personal Agent")
    drain_tasks()
    agent_id = agent["id"]

    # The superuser owns this agent. Create a personal route from superuser's perspective
    # to validate the ownership check in a positive case.
    trigger = "Handle all expense reports"
    patterns = "expense *\nsubmit expense *"

    route = create_user_route(
        client,
        superuser_token_headers,
        agent_id=agent_id,
        trigger_prompt=trigger,
        message_patterns=patterns,
        session_mode="conversation",
        channel_app_mcp=True,
        is_active=True,
    )
    route_id = route["id"]

    assert route["agent_id"] == agent_id
    assert route["trigger_prompt"] == trigger
    assert route["message_patterns"] == patterns
    assert route["session_mode"] == "conversation"
    assert route["channel_app_mcp"] is True
    assert route["is_active"] is True
    assert "created_at" in route
    assert "updated_at" in route
    assert "user_id" in route

    # ── Phase 3: Route appears in personal_routes list ─────────────────────
    routes_response = list_user_routes(client, superuser_token_headers)
    assert "personal_routes" in routes_response
    assert "shared_routes" in routes_response
    personal = routes_response["personal_routes"]
    assert any(r["id"] == route_id for r in personal)

    # ── Phase 4: Update personal route ────────────────────────────────────
    updated = update_user_route(
        client, superuser_token_headers, route_id,
        trigger_prompt="Handle all reimbursement requests",
        is_active=False,
        message_patterns="reimburse *",
    )
    assert updated["trigger_prompt"] == "Handle all reimbursement requests"
    assert updated["is_active"] is False
    assert updated["message_patterns"] == "reimburse *"

    # Verify update persisted in list
    routes_after_update = list_user_routes(client, superuser_token_headers)
    updated_in_list = next(
        r for r in routes_after_update["personal_routes"] if r["id"] == route_id
    )
    assert updated_in_list["is_active"] is False

    # ── Phase 5: Cannot create route for agent not owned by user ──────────
    # user_a (a different user) should not be able to create a route for superuser's agent
    r = client.post(
        f"{_USER_BASE}/",
        headers=user_headers,
        json={
            "agent_id": agent_id,
            "trigger_prompt": "Should fail",
        },
    )
    assert r.status_code == 400
    assert "not owned" in r.json()["detail"].lower() or "not found" in r.json()["detail"].lower()

    # ── Phase 6: Other user cannot update or delete the route ─────────────
    assert client.put(
        f"{_USER_BASE}/{route_id}", headers=user_headers,
        json={"trigger_prompt": "hacked"},
    ).status_code == 404  # returns 404 when route doesn't belong to user

    assert client.delete(
        f"{_USER_BASE}/{route_id}", headers=user_headers,
    ).status_code == 404

    # Non-existent route returns 404
    ghost = str(uuid.uuid4())
    assert client.put(
        f"{_USER_BASE}/{ghost}", headers=superuser_token_headers,
        json={"trigger_prompt": "x"},
    ).status_code == 404
    assert client.delete(
        f"{_USER_BASE}/{ghost}", headers=superuser_token_headers,
    ).status_code == 404

    # ── Phase 7: Delete route → gone ──────────────────────────────────────
    deleted = delete_user_route(client, superuser_token_headers, route_id)
    assert "message" in deleted

    routes_after_delete = list_user_routes(client, superuser_token_headers)
    assert not any(
        r["id"] == route_id for r in routes_after_delete["personal_routes"]
    )


# ---------------------------------------------------------------------------
# Scenario 4: Admin-assigned routes visible to users + toggle
# ---------------------------------------------------------------------------


def test_admin_assigned_routes_and_toggle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Admin-assigned routes appear in user listing and can be toggled by the user:
      1. Superuser creates agent + admin route
      2. Superuser assigns a regular user to the route
      3. User lists their routes — admin route appears in admin_routes
      4. User disables the assignment (is_enabled=False)
      5. User re-enables the assignment (is_enabled=True)
      6. Another user cannot toggle someone else's assignment
      7. Toggling a non-existent assignment returns 404
    """
    # ── Phase 1: Create agent and admin route ──────────────────────────────
    agent = create_agent_via_api(client, superuser_token_headers, name="Toggle Test Agent")
    drain_tasks()
    agent_id = agent["id"]

    route = create_admin_route(
        client, superuser_token_headers,
        agent_id=agent_id,
        name=f"toggle-route-{random_lower_string()[:6]}",
        trigger_prompt="Handle toggle test requests",
        # auto_enable_for_users=True so assignments default to is_enabled=True
        auto_enable_for_users=True,
    )
    route_id = route["id"]

    # ── Phase 2: Assign regular user ──────────────────────────────────────
    user, user_headers = create_random_user_with_headers(client)

    assignments = assign_users_to_route(
        client, superuser_token_headers, route_id, user_ids=[user["id"]]
    )
    assert len(assignments) == 1
    assignment_id = assignments[0]["id"]
    # auto_enable_for_users=True → assignment is_enabled=True
    assert assignments[0]["is_enabled"] is True

    # ── Phase 3: User's shared_routes list includes the assignment ────────
    user_routes = list_user_routes(client, user_headers)
    shared_routes = user_routes["shared_routes"]
    assert any(r["assignment_id"] == assignment_id for r in shared_routes)

    assigned_route = next(r for r in shared_routes if r["assignment_id"] == assignment_id)
    assert assigned_route["is_enabled"] is True
    assert assigned_route["route_id"] == route_id
    assert assigned_route["is_active"] is True  # route-level toggle

    # ── Phase 4: User disables the assignment ─────────────────────────────
    toggled_off = toggle_admin_assignment(
        client, user_headers, assignment_id=assignment_id, is_enabled=False
    )
    assert toggled_off["is_enabled"] is False
    assert toggled_off["id"] == assignment_id

    # Verify persisted in list
    user_routes_after_disable = list_user_routes(client, user_headers)
    assignment_in_list = next(
        r for r in user_routes_after_disable["shared_routes"]
        if r["assignment_id"] == assignment_id
    )
    assert assignment_in_list["is_enabled"] is False

    # ── Phase 5: User re-enables the assignment ────────────────────────────
    toggled_on = toggle_admin_assignment(
        client, user_headers, assignment_id=assignment_id, is_enabled=True
    )
    assert toggled_on["is_enabled"] is True

    # ── Phase 6: Another user cannot toggle someone else's assignment ──────
    other_user, other_headers = create_random_user_with_headers(client)

    r = client.patch(
        f"{_USER_BASE}/admin-assignments/{assignment_id}",
        headers=other_headers,
        params={"is_enabled": "false"},
    )
    assert r.status_code == 404  # returns 404 when assignment doesn't belong to user

    # ── Phase 7: Non-existent assignment returns 404 ──────────────────────
    ghost_assignment = str(uuid.uuid4())
    r = client.patch(
        f"{_USER_BASE}/admin-assignments/{ghost_assignment}",
        headers=user_headers,
        params={"is_enabled": "false"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Scenario 5: Personal route unique constraint
# ---------------------------------------------------------------------------


def test_user_route_unique_constraint_per_agent(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A user cannot create two personal routes for the same agent
    (unique constraint on user_id + agent_id):
      1. Create a personal route for an agent
      2. Attempt to create a second route for the same agent
      3. Expect 400 or 409 error (DB unique constraint violation)
    """
    agent = create_agent_via_api(
        client, superuser_token_headers, name="Unique Constraint Agent"
    )
    drain_tasks()
    agent_id = agent["id"]

    # ── Phase 1: Create first route ────────────────────────────────────────
    create_user_route(
        client, superuser_token_headers,
        agent_id=agent_id,
        trigger_prompt="First trigger prompt",
    )

    # ── Phase 2: Attempt duplicate — expect 400 ────────────────────────────
    r = client.post(
        f"{_USER_BASE}/",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "trigger_prompt": "Second trigger prompt — should fail",
        },
    )
    # Service catches IntegrityError and raises ValueError → route returns 400
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"].lower()
