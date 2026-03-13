"""
Integration tests for the User Dashboards API (/api/v1/dashboards).

Test scenarios:
  1. Dashboard CRUD lifecycle — create, list, get, update, delete
  2. Block CRUD lifecycle — add, update, delete, with ownership guards
  3. Bulk layout update — drag-and-drop rearrangement
  4. Authorization — ownership checks, unauthenticated requests
  5. Validation limits — max 10 dashboards, max 20 blocks per dashboard
  6. Agent access validation — agent must be owned by user
  7. Webapp view_type validation — agent must have webapp_enabled
  8. Invalid view_type rejection
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api, update_agent
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.dashboard import (
    add_block,
    create_dashboard,
    delete_block,
    delete_dashboard,
    get_dashboard,
    list_dashboards,
    update_block,
    update_block_layout,
    update_dashboard,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/dashboards"


# ── Scenario 1: Dashboard CRUD lifecycle ────────────────────────────────────

def test_dashboard_full_lifecycle(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Full dashboard CRUD lifecycle:
      1. Create dashboard
      2. List dashboards — verify it appears
      3. Get dashboard by ID
      4. Update dashboard (rename + description)
      5. Verify update persisted
      6. Delete dashboard
      7. Verify it's gone
    """
    # ── Phase 1: Create ──────────────────────────────────────────────────────
    dashboard = create_dashboard(
        client, superuser_token_headers, name="My Test Dashboard", description="Test desc"
    )
    dashboard_id = dashboard["id"]
    assert dashboard["name"] == "My Test Dashboard"
    assert dashboard["description"] == "Test desc"
    assert dashboard["blocks"] == []
    assert "sort_order" in dashboard

    # ── Phase 2: List → dashboard is present ────────────────────────────────
    dashboards = list_dashboards(client, superuser_token_headers)
    assert any(d["id"] == dashboard_id for d in dashboards)

    # ── Phase 3: Get by ID ───────────────────────────────────────────────────
    fetched = get_dashboard(client, superuser_token_headers, dashboard_id)
    assert fetched["id"] == dashboard_id
    assert fetched["name"] == "My Test Dashboard"
    assert fetched["blocks"] == []

    # ── Phase 4: Update ──────────────────────────────────────────────────────
    updated = update_dashboard(
        client, superuser_token_headers, dashboard_id, name="Renamed", description="Updated desc"
    )
    assert updated["name"] == "Renamed"
    assert updated["description"] == "Updated desc"

    # ── Phase 5: Verify update persisted ────────────────────────────────────
    refetched = get_dashboard(client, superuser_token_headers, dashboard_id)
    assert refetched["name"] == "Renamed"

    # ── Phase 6: Auth and ownership guards ──────────────────────────────────
    # Unauthenticated
    assert client.get(f"{_BASE}/").status_code in (401, 403)
    assert client.get(f"{_BASE}/{dashboard_id}").status_code in (401, 403)

    # Other user cannot access
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client, email=other_user["email"], password=other_user["_password"]
    )
    assert client.get(f"{_BASE}/{dashboard_id}", headers=other_headers).status_code in (403, 404)
    assert client.put(f"{_BASE}/{dashboard_id}", headers=other_headers, json={"name": "X"}).status_code in (403, 404)
    assert client.delete(f"{_BASE}/{dashboard_id}", headers=other_headers).status_code in (403, 404)

    # Non-existent ID returns 404
    ghost = str(uuid.uuid4())
    assert client.get(f"{_BASE}/{ghost}", headers=superuser_token_headers).status_code == 404

    # ── Phase 7: Delete ──────────────────────────────────────────────────────
    delete_dashboard(client, superuser_token_headers, dashboard_id)

    # ── Phase 8: Verify gone ─────────────────────────────────────────────────
    r = client.get(f"{_BASE}/{dashboard_id}", headers=superuser_token_headers)
    assert r.status_code == 404


# ── Scenario 2: Block CRUD lifecycle ────────────────────────────────────────

def test_block_full_lifecycle(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Block CRUD lifecycle on a dashboard:
      1. Create dashboard
      2. Create agent
      3. Add block to dashboard
      4. Verify block appears in dashboard
      5. Update block settings
      6. Verify update persisted
      7. Delete block
      8. Verify block is gone
      9. Ownership guards for block operations
    """
    # ── Phase 1 & 2: Create dashboard and agent ──────────────────────────────
    dashboard = create_dashboard(client, superuser_token_headers, name="Block Test Dashboard")
    dashboard_id = dashboard["id"]
    agent = create_agent_via_api(client, superuser_token_headers)
    agent_id = agent["id"]

    # ── Phase 3: Add block ───────────────────────────────────────────────────
    block = add_block(
        client, superuser_token_headers, dashboard_id, agent_id,
        view_type="latest_session", grid_x=0, grid_y=0, grid_w=3, grid_h=2
    )
    block_id = block["id"]
    assert block["agent_id"] == agent_id
    assert block["view_type"] == "latest_session"
    assert block["grid_w"] == 3
    assert block["grid_h"] == 2
    assert block["show_border"] is True
    assert block["show_header"] is False  # default

    # ── Phase 4: Verify block appears in dashboard ───────────────────────────
    fetched = get_dashboard(client, superuser_token_headers, dashboard_id)
    assert len(fetched["blocks"]) == 1
    assert fetched["blocks"][0]["id"] == block_id

    # ── Phase 5: Update block ────────────────────────────────────────────────
    updated_block = update_block(
        client, superuser_token_headers, dashboard_id, block_id,
        view_type="latest_tasks", title="Custom Title", show_border=False, show_header=True
    )
    assert updated_block["view_type"] == "latest_tasks"
    assert updated_block["title"] == "Custom Title"
    assert updated_block["show_border"] is False
    assert updated_block["show_header"] is True

    # ── Phase 6: Verify block update persisted ───────────────────────────────
    refetched = get_dashboard(client, superuser_token_headers, dashboard_id)
    saved_block = refetched["blocks"][0]
    assert saved_block["view_type"] == "latest_tasks"
    assert saved_block["title"] == "Custom Title"
    assert saved_block["show_header"] is True

    # ── Phase 7: Block ownership guards ─────────────────────────────────────
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client, email=other_user["email"], password=other_user["_password"]
    )
    # Other user cannot modify blocks on this dashboard
    r = client.put(
        f"{_BASE}/{dashboard_id}/blocks/{block_id}",
        headers=other_headers,
        json={"title": "Hijack"},
    )
    assert r.status_code in (403, 404)

    r = client.delete(
        f"{_BASE}/{dashboard_id}/blocks/{block_id}", headers=other_headers
    )
    assert r.status_code in (403, 404)

    # ── Phase 8: Delete block ────────────────────────────────────────────────
    delete_block(client, superuser_token_headers, dashboard_id, block_id)

    # ── Phase 9: Verify block gone ───────────────────────────────────────────
    refetched2 = get_dashboard(client, superuser_token_headers, dashboard_id)
    assert len(refetched2["blocks"]) == 0

    r = client.delete(
        f"{_BASE}/{dashboard_id}/blocks/{block_id}", headers=superuser_token_headers
    )
    assert r.status_code == 404


# ── Scenario 3: Bulk layout update ──────────────────────────────────────────

def test_bulk_layout_update(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Bulk layout update (drag-and-drop):
      1. Create dashboard with 2 blocks
      2. Call layout update endpoint with new grid positions
      3. Verify positions persisted in dashboard response
    """
    dashboard = create_dashboard(client, superuser_token_headers, name="Layout Test")
    dashboard_id = dashboard["id"]

    agent = create_agent_via_api(client, superuser_token_headers)
    agent_id = agent["id"]

    block1 = add_block(
        client, superuser_token_headers, dashboard_id, agent_id,
        grid_x=0, grid_y=0, grid_w=2, grid_h=2
    )
    block2 = add_block(
        client, superuser_token_headers, dashboard_id, agent_id,
        grid_x=2, grid_y=0, grid_w=2, grid_h=2
    )

    # Move block1 to (4,2) and resize block2
    new_layouts = [
        {"block_id": block1["id"], "grid_x": 4, "grid_y": 2, "grid_w": 3, "grid_h": 3},
        {"block_id": block2["id"], "grid_x": 0, "grid_y": 0, "grid_w": 4, "grid_h": 4},
    ]
    updated_blocks = update_block_layout(
        client, superuser_token_headers, dashboard_id, new_layouts
    )
    assert len(updated_blocks) == 2

    # Verify positions persisted
    fetched = get_dashboard(client, superuser_token_headers, dashboard_id)
    blocks_by_id = {b["id"]: b for b in fetched["blocks"]}

    b1 = blocks_by_id[block1["id"]]
    assert b1["grid_x"] == 4
    assert b1["grid_y"] == 2
    assert b1["grid_w"] == 3
    assert b1["grid_h"] == 3

    b2 = blocks_by_id[block2["id"]]
    assert b2["grid_x"] == 0
    assert b2["grid_w"] == 4

    # Layout update with unknown block_id returns 404
    r = client.put(
        f"{_BASE}/{dashboard_id}/blocks/layout",
        headers=superuser_token_headers,
        json=[{"block_id": str(uuid.uuid4()), "grid_x": 0, "grid_y": 0, "grid_w": 2, "grid_h": 2}],
    )
    assert r.status_code == 404


# ── Scenario 4: Max dashboard limit ─────────────────────────────────────────

def test_max_dashboards_limit(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Max 10 dashboards per user:
      1. Create 10 dashboards (should succeed)
      2. Attempt to create 11th — should get 409
    """
    dashboard_ids = []
    for i in range(10):
        d = create_dashboard(client, superuser_token_headers, name=f"Dashboard {i}")
        dashboard_ids.append(d["id"])

    # 11th should fail
    r = client.post(
        f"{_BASE}/", headers=superuser_token_headers, json={"name": "Over Limit"}
    )
    assert r.status_code == 409

    # Clean up
    for did in dashboard_ids:
        delete_dashboard(client, superuser_token_headers, did)


# ── Scenario 5: Max blocks limit ────────────────────────────────────────────

def test_max_blocks_limit(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Max 20 blocks per dashboard:
      1. Create dashboard and agent
      2. Add 20 blocks (should succeed)
      3. Attempt 21st — should get 409
    """
    dashboard = create_dashboard(client, superuser_token_headers, name="Block Limit Test")
    dashboard_id = dashboard["id"]
    agent = create_agent_via_api(client, superuser_token_headers)
    agent_id = agent["id"]

    for _ in range(20):
        add_block(client, superuser_token_headers, dashboard_id, agent_id)

    # 21st should fail
    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "view_type": "latest_session",
            "title": None,
            "show_border": True,
            "grid_x": 0,
            "grid_y": 0,
            "grid_w": 2,
            "grid_h": 2,
        },
    )
    assert r.status_code == 409


# ── Scenario 6: Agent access validation ─────────────────────────────────────

def test_block_agent_access_validation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Cannot add a block for an agent owned by another user.
    """
    dashboard = create_dashboard(client, superuser_token_headers, name="Agent Access Test")
    dashboard_id = dashboard["id"]

    # Create agent under a different user (need AI credentials for that user too)
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client, email=other_user["email"], password=other_user["_password"]
    )
    # Set up default AI credential for other user so agent creation works
    create_random_ai_credential(client, other_headers, set_default=True)
    other_agent = create_agent_via_api(client, other_headers)
    other_agent_id = other_agent["id"]

    # Superuser tries to add other user's agent — should fail
    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks",
        headers=superuser_token_headers,
        json={
            "agent_id": other_agent_id,
            "view_type": "latest_session",
            "title": None,
            "show_border": True,
            "grid_x": 0,
            "grid_y": 0,
            "grid_w": 2,
            "grid_h": 2,
        },
    )
    assert r.status_code == 400

    # Non-existent agent_id also returns 400
    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks",
        headers=superuser_token_headers,
        json={
            "agent_id": str(uuid.uuid4()),
            "view_type": "latest_session",
            "title": None,
            "show_border": True,
            "grid_x": 0,
            "grid_y": 0,
            "grid_w": 2,
            "grid_h": 2,
        },
    )
    assert r.status_code == 400


# ── Scenario 7: Webapp view_type validation ──────────────────────────────────

def test_webapp_view_type_validation(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Cannot add webapp block if agent has webapp_enabled=False.
    When webapp_enabled=True, block creation succeeds.
    """
    dashboard = create_dashboard(client, superuser_token_headers, name="Webapp Test")
    dashboard_id = dashboard["id"]
    agent = create_agent_via_api(client, superuser_token_headers)
    agent_id = agent["id"]

    # Agent defaults to webapp_enabled=False — should fail
    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "view_type": "webapp",
            "title": None,
            "show_border": True,
            "grid_x": 0,
            "grid_y": 0,
            "grid_w": 2,
            "grid_h": 2,
        },
    )
    assert r.status_code == 400

    # Enable webapp on agent
    update_agent(client, superuser_token_headers, agent_id, webapp_enabled=True)

    # Now it should succeed
    block = add_block(
        client, superuser_token_headers, dashboard_id, agent_id, view_type="webapp"
    )
    assert block["view_type"] == "webapp"


# ── Scenario 8: Invalid view_type ────────────────────────────────────────────

def test_invalid_view_type_rejected(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Invalid view_type values are rejected with 422.
    """
    dashboard = create_dashboard(client, superuser_token_headers, name="View Type Test")
    dashboard_id = dashboard["id"]
    agent = create_agent_via_api(client, superuser_token_headers)
    agent_id = agent["id"]

    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks",
        headers=superuser_token_headers,
        json={
            "agent_id": agent_id,
            "view_type": "invalid_type_xyz",
            "title": None,
            "show_border": True,
            "grid_x": 0,
            "grid_y": 0,
            "grid_w": 2,
            "grid_h": 2,
        },
    )
    assert r.status_code == 422
