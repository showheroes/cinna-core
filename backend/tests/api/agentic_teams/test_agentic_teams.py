"""
Tests for the AgenticTeams feature.

Scenario-based integration tests covering all 17 endpoints and the key
business rules in the service layer:

  1. AgenticTeam CRUD lifecycle (create, list, get, update, delete)
  2. Auth and ownership guards — other user AND superuser both get 404
  3. Input validation — empty name, name/icon too long
  4. Ghost / non-existent IDs return 404
  5. AgenticTeamNode lifecycle — name auto-populated, is_lead toggle, positions
  6. Duplicate agent in same team → 409
  7. is_lead auto-unmark on CREATE (not just update)
  8. Agent deletion cascades node removal
  9. Node ownership and cross-team access guards
 10. AgenticTeamConnection lifecycle — resolved node names, prompt/enabled update
 11. Self-connection guard → 400
 12. Duplicate connection guard → 409
 13. Cross-team node IDs in connection → 404
 14. Connection ownership guards
 15. Node deletion cascades its connections
 16. Team deletion cascades all nodes and connections
 17. GET /chart — combined payload, resolved names, ownership guard
 18. PUT /nodes/positions — bulk update, persistence, foreign node → 400, ownership guard
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.agentic_team import (
    create_team,
    get_team,
    list_teams,
    update_team,
    delete_team,
    create_node,
    get_node,
    list_nodes,
    delete_node,
    create_connection,
    get_connection,
    list_connections,
    delete_connection,
    get_chart,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/agentic-teams"


# ---------------------------------------------------------------------------
# Test 1 — AgenticTeam CRUD lifecycle + auth + ownership guards
# ---------------------------------------------------------------------------

def test_agentic_team_full_lifecycle(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full team CRUD lifecycle and ownership/auth enforcement:
      1. Create team — name and icon in response, owner_id set
      2. List → team appears
      3. Get single → correct fields
      4. Update name and icon → persisted
      5. Partial update (icon only) → name unchanged
      6. Delete → 200 message
      7. Verify gone → 404
      8. Unauthenticated requests rejected
      9. Other user cannot read or mutate a different user's team
     10. Superuser cannot bypass ownership
    """
    headers = normal_user_token_headers

    # ── Phase 1: Create ──────────────────────────────────────────────────────
    team = create_team(client, headers, name="My Team", icon="users")
    team_id = team["id"]
    assert team["name"] == "My Team"
    assert team["icon"] == "users"
    assert "owner_id" in team
    assert "created_at" in team
    assert "updated_at" in team

    # ── Phase 2: List → team is present ─────────────────────────────────────
    teams = list_teams(client, headers)
    assert any(t["id"] == team_id for t in teams)

    # ── Phase 3: Get single ──────────────────────────────────────────────────
    fetched = get_team(client, headers, team_id)
    assert fetched["id"] == team_id
    assert fetched["name"] == "My Team"
    assert fetched["icon"] == "users"

    # ── Phase 4: Update name and icon ────────────────────────────────────────
    updated = update_team(client, headers, team_id, name="Renamed Team", icon="rocket")
    assert updated["name"] == "Renamed Team"
    assert updated["icon"] == "rocket"

    # Verify persisted
    refetched = get_team(client, headers, team_id)
    assert refetched["name"] == "Renamed Team"
    assert refetched["icon"] == "rocket"

    # ── Phase 5: Partial update (icon only) ──────────────────────────────────
    partial = update_team(client, headers, team_id, icon="star")
    assert partial["icon"] == "star"
    assert partial["name"] == "Renamed Team"  # name unchanged

    # ── Phase 6 & 7: Delete → verify gone ────────────────────────────────────
    r = client.delete(f"{_BASE}/{team_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Agentic team deleted"

    r = client.get(f"{_BASE}/{team_id}", headers=headers)
    assert r.status_code == 404

    # ── Phase 8: Unauthenticated requests rejected ────────────────────────────
    assert client.get(f"{_BASE}/").status_code in (401, 403)
    assert client.post(f"{_BASE}/", json={"name": "x"}).status_code in (401, 403)

    # ── Phase 9: Other user cannot read or mutate ─────────────────────────────
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client,
        email=other_user["email"],
        password=other_user["_password"],
    )
    team2 = create_team(client, headers, name="Owner Team")
    team2_id = team2["id"]

    assert client.get(f"{_BASE}/{team2_id}", headers=other_headers).status_code == 404
    assert (
        client.put(f"{_BASE}/{team2_id}", headers=other_headers, json={"name": "x"}).status_code
        == 404
    )
    assert client.delete(f"{_BASE}/{team2_id}", headers=other_headers).status_code == 404

    # ── Phase 10: Superuser cannot bypass ownership ───────────────────────────
    assert client.get(f"{_BASE}/{team2_id}", headers=superuser_token_headers).status_code == 404
    assert (
        client.put(f"{_BASE}/{team2_id}", headers=superuser_token_headers, json={"name": "x"}).status_code
        == 404
    )
    assert (
        client.delete(f"{_BASE}/{team2_id}", headers=superuser_token_headers).status_code == 404
    )

    # Cleanup
    delete_team(client, headers, team2_id)


# ---------------------------------------------------------------------------
# Test 2 — Input validation
# ---------------------------------------------------------------------------

def test_agentic_team_validation(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Pydantic validation errors on create and update:
      1. Empty name → 422
      2. Name exceeding 255 chars → 422
      3. Icon exceeding 50 chars → 422
      4. Name-only update (no icon field) works fine
    """
    headers = normal_user_token_headers

    # ── Phase 1: Empty name ───────────────────────────────────────────────────
    r = client.post(_BASE + "/", headers=headers, json={"name": ""})
    assert r.status_code == 422

    # ── Phase 2: Name too long ────────────────────────────────────────────────
    r = client.post(_BASE + "/", headers=headers, json={"name": "x" * 256})
    assert r.status_code == 422

    # ── Phase 3: Icon too long ────────────────────────────────────────────────
    r = client.post(_BASE + "/", headers=headers, json={"name": "Valid", "icon": "x" * 51})
    assert r.status_code == 422

    # ── Phase 4: Name-only create (no icon) works ─────────────────────────────
    team = create_team(client, headers, name="No Icon Team", icon=None)
    assert team["icon"] is None
    delete_team(client, headers, team["id"])


# ---------------------------------------------------------------------------
# Test 3 — Ghost IDs return 404
# ---------------------------------------------------------------------------

def test_agentic_team_ghost_ids(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
) -> None:
    """
    Non-existent IDs return 404 for team, node, and connection endpoints.
    """
    headers = normal_user_token_headers
    ghost = str(uuid.uuid4())

    assert client.get(f"{_BASE}/{ghost}", headers=headers).status_code == 404
    assert client.put(f"{_BASE}/{ghost}", headers=headers, json={"name": "x"}).status_code == 404
    assert client.delete(f"{_BASE}/{ghost}", headers=headers).status_code == 404

    # Node and connection endpoints also return 404 for ghost team
    assert client.get(f"{_BASE}/{ghost}/nodes/", headers=headers).status_code == 404
    assert (
        client.post(f"{_BASE}/{ghost}/nodes/", headers=headers, json={"agent_id": ghost}).status_code
        == 404
    )
    assert client.get(f"{_BASE}/{ghost}/connections/", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{ghost}/chart", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Test 4 — AgenticTeamNode full lifecycle
# ---------------------------------------------------------------------------

def test_agentic_team_node_full_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full node lifecycle using superuser (avoids needing separate env stubs):
      1. Create team
      2. Create node1 (not lead) — name auto-populated from agent
      3. Create node2 as lead
      4. List nodes → both present, count=2
      5. Get single node → all fields present including agent_ui_color_preset
      6. is_lead toggle via CREATE: node1 was not lead; set node3 as lead on
         create with is_lead=True → node2 auto-unmarked
      7. is_lead toggle via UPDATE: update node1 is_lead=True → node3 auto-unmarked
      8. Update pos_x / pos_y persists
      9. Delete node → gone from list
     10. Ghost node ID → 404
     11. Node from another team → 404
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Node Lifecycle Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Node Agent Alpha")
    agent2 = create_agent_via_api(client, headers, name="Node Agent Beta")
    agent3 = create_agent_via_api(client, headers, name="Node Agent Gamma")

    # ── Phase 1: Create node1 (not lead) ─────────────────────────────────────
    node1 = create_node(client, headers, team_id, agent1["id"], is_lead=False, pos_x=10.0, pos_y=20.0)
    node1_id = node1["id"]
    assert node1["name"] == agent1["name"]  # auto-populated
    assert node1["agent_id"] == agent1["id"]
    assert node1["team_id"] == team_id
    assert node1["is_lead"] is False
    assert node1["pos_x"] == 10.0
    assert node1["pos_y"] == 20.0
    assert node1["node_type"] == "agent"
    assert "agent_ui_color_preset" in node1

    # ── Phase 2: Create node2 as lead ────────────────────────────────────────
    node2 = create_node(client, headers, team_id, agent2["id"], is_lead=True)
    node2_id = node2["id"]
    assert node2["is_lead"] is True
    assert node2["name"] == agent2["name"]

    # ── Phase 3: List → both present ─────────────────────────────────────────
    nodes = list_nodes(client, headers, team_id)
    node_ids = [n["id"] for n in nodes]
    assert node1_id in node_ids
    assert node2_id in node_ids
    r = client.get(f"{_BASE}/{team_id}/nodes/", headers=headers)
    assert r.json()["count"] == 2

    # ── Phase 4: Get single node ──────────────────────────────────────────────
    fetched = get_node(client, headers, team_id, node1_id)
    assert fetched["id"] == node1_id
    assert fetched["name"] == agent1["name"]

    # ── Phase 5: is_lead auto-unmark on CREATE ────────────────────────────────
    # node2 is currently lead; creating node3 as lead should unmark node2
    node3 = create_node(client, headers, team_id, agent3["id"], is_lead=True)
    node3_id = node3["id"]
    assert node3["is_lead"] is True

    node2_refetch = get_node(client, headers, team_id, node2_id)
    assert node2_refetch["is_lead"] is False  # auto-unmarked

    # ── Phase 6: is_lead auto-unmark on UPDATE ────────────────────────────────
    # node3 is currently lead; update node1 to is_lead=True → node3 should be unmarked
    r = client.put(
        f"{_BASE}/{team_id}/nodes/{node1_id}",
        headers=headers,
        json={"is_lead": True},
    )
    assert r.status_code == 200
    assert r.json()["is_lead"] is True

    node3_refetch = get_node(client, headers, team_id, node3_id)
    assert node3_refetch["is_lead"] is False

    # ── Phase 7: Update position ──────────────────────────────────────────────
    r = client.put(
        f"{_BASE}/{team_id}/nodes/{node1_id}",
        headers=headers,
        json={"pos_x": 99.9, "pos_y": 88.8},
    )
    assert r.status_code == 200
    assert abs(r.json()["pos_x"] - 99.9) < 0.01
    assert abs(r.json()["pos_y"] - 88.8) < 0.01
    # Verify persisted
    assert abs(get_node(client, headers, team_id, node1_id)["pos_x"] - 99.9) < 0.01

    # ── Phase 8: Delete node → gone ──────────────────────────────────────────
    delete_node(client, headers, team_id, node1_id)
    assert client.get(f"{_BASE}/{team_id}/nodes/{node1_id}", headers=headers).status_code == 404

    # ── Phase 9: Ghost node ID → 404 ─────────────────────────────────────────
    ghost_node = str(uuid.uuid4())
    assert client.get(f"{_BASE}/{team_id}/nodes/{ghost_node}", headers=headers).status_code == 404
    assert (
        client.put(f"{_BASE}/{team_id}/nodes/{ghost_node}", headers=headers, json={"pos_x": 1.0}).status_code
        == 404
    )
    assert client.delete(f"{_BASE}/{team_id}/nodes/{ghost_node}", headers=headers).status_code == 404

    # ── Phase 10: Node from another team returns 404 ──────────────────────────
    other_team = create_team(client, headers, name="Other Team")
    other_team_id = other_team["id"]
    # node2 belongs to team_id, not other_team_id
    assert (
        client.get(f"{_BASE}/{other_team_id}/nodes/{node2_id}", headers=headers).status_code == 404
    )

    # Cleanup
    delete_team(client, headers, other_team_id)
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 5 — Duplicate agent in same team → 409
# ---------------------------------------------------------------------------

def test_duplicate_agent_in_team(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Adding the same agent twice to the same team returns 409.
    Adding the same agent to a different team is allowed.
    """
    headers = superuser_token_headers

    team1 = create_team(client, headers, name="Dup Test Team 1")
    team2 = create_team(client, headers, name="Dup Test Team 2")
    agent = create_agent_via_api(client, headers, name="Dup Agent")
    agent_id = agent["id"]

    # First add is fine
    create_node(client, headers, team1["id"], agent_id)

    # Second add to same team → 409
    r = client.post(
        f"{_BASE}/{team1['id']}/nodes/",
        headers=headers,
        json={"agent_id": agent_id, "is_lead": False},
    )
    assert r.status_code == 409
    assert "already in the team" in r.json()["detail"]

    # Adding same agent to a different team is fine
    create_node(client, headers, team2["id"], agent_id)

    # Cleanup
    delete_team(client, headers, team1["id"])
    delete_team(client, headers, team2["id"])


# ---------------------------------------------------------------------------
# Test 6 — Node ownership guards
# ---------------------------------------------------------------------------

def test_node_ownership_guards(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Another user cannot read or mutate nodes of a team they don't own.
    Superuser also cannot bypass ownership.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Ownership Guard Team")
    team_id = team["id"]
    agent = create_agent_via_api(client, headers, name="Guard Agent")
    node = create_node(client, headers, team_id, agent["id"])
    node_id = node["id"]

    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client,
        email=other_user["email"],
        password=other_user["_password"],
    )

    assert client.get(f"{_BASE}/{team_id}/nodes/", headers=other_headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/nodes/{node_id}", headers=other_headers).status_code == 404
    assert (
        client.put(f"{_BASE}/{team_id}/nodes/{node_id}", headers=other_headers, json={"pos_x": 1.0}).status_code
        == 404
    )
    assert client.delete(f"{_BASE}/{team_id}/nodes/{node_id}", headers=other_headers).status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 7 — Agent deletion cascades node removal
# ---------------------------------------------------------------------------

def test_agent_deletion_cascades_node(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deleting an agent (via DELETE /agents/{id}) removes its node from the team
    due to the CASCADE FK on agentic_team_node.agent_id.

    Verification: after agent deletion, GET /nodes/ no longer contains the node.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Cascade Agent Team")
    team_id = team["id"]

    agent = create_agent_via_api(client, headers, name="Deletable Agent")
    agent_id = agent["id"]

    node = create_node(client, headers, team_id, agent_id)
    node_id = node["id"]

    # Confirm node exists
    assert get_node(client, headers, team_id, node_id)["id"] == node_id

    # Delete the agent
    r = client.delete(f"{settings.API_V1_STR}/agents/{agent_id}", headers=headers)
    assert r.status_code == 200

    # Node should now be gone (FK cascade)
    r = client.get(f"{_BASE}/{team_id}/nodes/{node_id}", headers=headers)
    assert r.status_code == 404

    # Also verify via list
    remaining = list_nodes(client, headers, team_id)
    assert not any(n["id"] == node_id for n in remaining)

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 8 — AgenticTeamConnection full lifecycle
# ---------------------------------------------------------------------------

def test_agentic_team_connection_full_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full connection lifecycle:
      1. Create team + two nodes
      2. Create connection — resolved node names in response
      3. List connections → present; count=1
      4. Get single connection → all fields correct
      5. Update prompt and enabled → persisted
      6. Partial update (enabled only) → prompt unchanged
      7. Self-connection → 400
      8. Duplicate connection → 409
      9. Connection from wrong team → 404
     10. Delete connection → 200 message
     11. Verify gone → 404
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Conn Lifecycle Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Conn Agent 1")
    agent2 = create_agent_via_api(client, headers, name="Conn Agent 2")

    node1 = create_node(client, headers, team_id, agent1["id"])
    node2 = create_node(client, headers, team_id, agent2["id"])
    node1_id = node1["id"]
    node2_id = node2["id"]

    # ── Phase 1: Create connection ────────────────────────────────────────────
    conn = create_connection(
        client, headers, team_id, node1_id, node2_id,
        connection_prompt="Hand off task when done.",
        enabled=True,
    )
    conn_id = conn["id"]
    assert conn["team_id"] == team_id
    assert conn["source_node_id"] == node1_id
    assert conn["target_node_id"] == node2_id
    assert conn["connection_prompt"] == "Hand off task when done."
    assert conn["enabled"] is True
    # Resolved names
    assert conn["source_node_name"] == agent1["name"]
    assert conn["target_node_name"] == agent2["name"]

    # ── Phase 2: List → connection present ───────────────────────────────────
    conns = list_connections(client, headers, team_id)
    assert any(c["id"] == conn_id for c in conns)
    r = client.get(f"{_BASE}/{team_id}/connections/", headers=headers)
    assert r.json()["count"] == 1

    # ── Phase 3: Get single ───────────────────────────────────────────────────
    fetched = get_connection(client, headers, team_id, conn_id)
    assert fetched["id"] == conn_id
    assert fetched["source_node_name"] == agent1["name"]
    assert fetched["target_node_name"] == agent2["name"]

    # ── Phase 4: Update prompt and enabled ────────────────────────────────────
    r = client.put(
        f"{_BASE}/{team_id}/connections/{conn_id}",
        headers=headers,
        json={"connection_prompt": "Updated prompt.", "enabled": False},
    )
    assert r.status_code == 200
    updated = r.json()
    assert updated["connection_prompt"] == "Updated prompt."
    assert updated["enabled"] is False

    # Verify persisted
    refetched = get_connection(client, headers, team_id, conn_id)
    assert refetched["connection_prompt"] == "Updated prompt."
    assert refetched["enabled"] is False

    # ── Phase 5: Partial update (enabled only) → prompt unchanged ─────────────
    r = client.put(
        f"{_BASE}/{team_id}/connections/{conn_id}",
        headers=headers,
        json={"enabled": True},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    assert r.json()["connection_prompt"] == "Updated prompt."  # unchanged

    # ── Phase 6: Self-connection → 400 ───────────────────────────────────────
    r = client.post(
        f"{_BASE}/{team_id}/connections/",
        headers=headers,
        json={
            "source_node_id": node1_id,
            "target_node_id": node1_id,
            "connection_prompt": "",
        },
    )
    assert r.status_code == 400
    assert "must be different" in r.json()["detail"]

    # ── Phase 7: Duplicate connection → 409 ──────────────────────────────────
    r = client.post(
        f"{_BASE}/{team_id}/connections/",
        headers=headers,
        json={
            "source_node_id": node1_id,
            "target_node_id": node2_id,
            "connection_prompt": "",
        },
    )
    assert r.status_code == 409
    assert "already exists" in r.json()["detail"]

    # ── Phase 8: Ghost connection ID → 404 ───────────────────────────────────
    ghost_conn = str(uuid.uuid4())
    assert client.get(f"{_BASE}/{team_id}/connections/{ghost_conn}", headers=headers).status_code == 404
    assert (
        client.put(f"{_BASE}/{team_id}/connections/{ghost_conn}", headers=headers, json={"enabled": True}).status_code
        == 404
    )
    assert client.delete(f"{_BASE}/{team_id}/connections/{ghost_conn}", headers=headers).status_code == 404

    # ── Phase 9: Delete → 200 message ────────────────────────────────────────
    r = client.delete(f"{_BASE}/{team_id}/connections/{conn_id}", headers=headers)
    assert r.status_code == 200
    assert r.json()["message"] == "Connection deleted"

    # ── Phase 10: Verify gone → 404 ──────────────────────────────────────────
    assert client.get(f"{_BASE}/{team_id}/connections/{conn_id}", headers=headers).status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 9 — Cross-team node IDs rejected for connection creation
# ---------------------------------------------------------------------------

def test_connection_cross_team_node_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A node belonging to a different team cannot be used as source or target.
    The service verifies each node belongs to the given team_id.
    """
    headers = superuser_token_headers

    team1 = create_team(client, headers, name="Cross Team 1")
    team2 = create_team(client, headers, name="Cross Team 2")

    agent1 = create_agent_via_api(client, headers, name="Cross Agent 1")
    agent2 = create_agent_via_api(client, headers, name="Cross Agent 2")
    agent3 = create_agent_via_api(client, headers, name="Cross Agent 3")

    node_t1_a = create_node(client, headers, team1["id"], agent1["id"])
    node_t1_b = create_node(client, headers, team1["id"], agent2["id"])
    node_t2 = create_node(client, headers, team2["id"], agent3["id"])

    # source in team1, target in team2 → 404 (target node not found in team1)
    r = client.post(
        f"{_BASE}/{team1['id']}/connections/",
        headers=headers,
        json={
            "source_node_id": node_t1_a["id"],
            "target_node_id": node_t2["id"],
            "connection_prompt": "",
        },
    )
    assert r.status_code == 404

    # source in team2, target in team1 → 404 (source node not found in team1)
    r = client.post(
        f"{_BASE}/{team1['id']}/connections/",
        headers=headers,
        json={
            "source_node_id": node_t2["id"],
            "target_node_id": node_t1_b["id"],
            "connection_prompt": "",
        },
    )
    assert r.status_code == 404

    # Cleanup
    delete_team(client, headers, team1["id"])
    delete_team(client, headers, team2["id"])


# ---------------------------------------------------------------------------
# Test 10 — Connection ownership guards
# ---------------------------------------------------------------------------

def test_connection_ownership_guards(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Other user cannot read or mutate connections in a team they don't own.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Conn Ownership Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Conn Own Agent 1")
    agent2 = create_agent_via_api(client, headers, name="Conn Own Agent 2")

    node1 = create_node(client, headers, team_id, agent1["id"])
    node2 = create_node(client, headers, team_id, agent2["id"])
    conn = create_connection(client, headers, team_id, node1["id"], node2["id"])
    conn_id = conn["id"]

    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client,
        email=other_user["email"],
        password=other_user["_password"],
    )

    assert client.get(f"{_BASE}/{team_id}/connections/", headers=other_headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/connections/{conn_id}", headers=other_headers).status_code == 404
    assert (
        client.put(
            f"{_BASE}/{team_id}/connections/{conn_id}",
            headers=other_headers,
            json={"enabled": False},
        ).status_code
        == 404
    )
    assert client.delete(f"{_BASE}/{team_id}/connections/{conn_id}", headers=other_headers).status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 11 — Node deletion cascades its connections
# ---------------------------------------------------------------------------

def test_node_deletion_cascades_connections(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deleting a node (source or target) removes all its connections via CASCADE FK.

    Scenario:
      - node1 → node2 (conn1)
      - node2 → node3 (conn2)
      Delete node2 → both conn1 and conn2 disappear.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Node Cascade Team")
    team_id = team["id"]

    agents = [create_agent_via_api(client, headers, name=f"Casc Agent {i}") for i in range(3)]
    node1 = create_node(client, headers, team_id, agents[0]["id"])
    node2 = create_node(client, headers, team_id, agents[1]["id"])
    node3 = create_node(client, headers, team_id, agents[2]["id"])

    conn1 = create_connection(client, headers, team_id, node1["id"], node2["id"])
    conn2 = create_connection(client, headers, team_id, node2["id"], node3["id"])

    # Sanity: both connections exist
    assert get_connection(client, headers, team_id, conn1["id"])["id"] == conn1["id"]
    assert get_connection(client, headers, team_id, conn2["id"])["id"] == conn2["id"]

    # Delete middle node
    delete_node(client, headers, team_id, node2["id"])

    # Both connections cascade-deleted
    assert client.get(f"{_BASE}/{team_id}/connections/{conn1['id']}", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/connections/{conn2['id']}", headers=headers).status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 12 — Team deletion cascades all nodes and connections
# ---------------------------------------------------------------------------

def test_team_deletion_cascades_nodes_and_connections(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deleting the team removes all nodes and connections (FK CASCADE).
    After deletion all child resource endpoints return 404.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Full Cascade Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Casc Full A1")
    agent2 = create_agent_via_api(client, headers, name="Casc Full A2")

    node1 = create_node(client, headers, team_id, agent1["id"])
    node2 = create_node(client, headers, team_id, agent2["id"])
    conn = create_connection(client, headers, team_id, node1["id"], node2["id"])

    # Delete the team
    delete_team(client, headers, team_id)

    # Team gone
    assert client.get(f"{_BASE}/{team_id}", headers=headers).status_code == 404

    # All child endpoints now return 404 (team not found)
    assert client.get(f"{_BASE}/{team_id}/nodes/", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/nodes/{node1['id']}", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/connections/", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/connections/{conn['id']}", headers=headers).status_code == 404
    assert client.get(f"{_BASE}/{team_id}/chart", headers=headers).status_code == 404


# ---------------------------------------------------------------------------
# Test 13 — GET /chart bulk endpoint
# ---------------------------------------------------------------------------

def test_chart_bulk_endpoint(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    GET /agentic-teams/{id}/chart returns team, nodes, and connections in one
    request with resolved source/target node names. Also verifies ownership.
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Chart Test Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Chart Agent 1")
    agent2 = create_agent_via_api(client, headers, name="Chart Agent 2")

    node1 = create_node(client, headers, team_id, agent1["id"])
    node2 = create_node(client, headers, team_id, agent2["id"])
    conn = create_connection(client, headers, team_id, node1["id"], node2["id"], "Transfer task.")

    # ── Phase 1: Chart response structure ─────────────────────────────────────
    chart = get_chart(client, headers, team_id)

    assert chart["team"]["id"] == team_id
    assert chart["team"]["name"] == "Chart Test Team"
    assert len(chart["nodes"]) == 2
    assert len(chart["connections"]) == 1

    chart_node_ids = {n["id"] for n in chart["nodes"]}
    assert node1["id"] in chart_node_ids
    assert node2["id"] in chart_node_ids

    chart_conn = chart["connections"][0]
    assert chart_conn["id"] == conn["id"]
    assert chart_conn["source_node_name"] == agent1["name"]
    assert chart_conn["target_node_name"] == agent2["name"]
    assert chart_conn["connection_prompt"] == "Transfer task."

    # ── Phase 2: Empty team chart ──────────────────────────────────────────────
    empty_team = create_team(client, headers, name="Empty Chart Team")
    empty_chart = get_chart(client, headers, empty_team["id"])
    assert empty_chart["nodes"] == []
    assert empty_chart["connections"] == []

    # ── Phase 3: Ownership guard ──────────────────────────────────────────────
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client,
        email=other_user["email"],
        password=other_user["_password"],
    )
    assert client.get(f"{_BASE}/{team_id}/chart", headers=other_headers).status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)
    delete_team(client, headers, empty_team["id"])


# ---------------------------------------------------------------------------
# Test 14 — PUT /nodes/positions bulk update
# ---------------------------------------------------------------------------

def test_bulk_position_update(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Bulk position update:
      1. Create team + two nodes with default positions
      2. PUT /nodes/positions → new positions returned immediately
      3. Verify positions persisted via GET single node
      4. Empty list → 200 with empty array
      5. Node ID not in team → 400
      6. Other user cannot bulk-update → 404
    """
    headers = superuser_token_headers

    team = create_team(client, headers, name="Bulk Pos Team")
    team_id = team["id"]

    agent1 = create_agent_via_api(client, headers, name="Bulk Pos A1")
    agent2 = create_agent_via_api(client, headers, name="Bulk Pos A2")

    node1 = create_node(client, headers, team_id, agent1["id"])
    node2 = create_node(client, headers, team_id, agent2["id"])
    node1_id = node1["id"]
    node2_id = node2["id"]

    # ── Phase 1: Bulk update both nodes ──────────────────────────────────────
    r = client.put(
        f"{_BASE}/{team_id}/nodes/positions",
        headers=headers,
        json=[
            {"id": node1_id, "pos_x": 111.1, "pos_y": 222.2},
            {"id": node2_id, "pos_x": 333.3, "pos_y": 444.4},
        ],
    )
    assert r.status_code == 200
    result = r.json()
    assert isinstance(result, list)
    assert len(result) == 2

    pos_map = {n["id"]: n for n in result}
    assert abs(pos_map[node1_id]["pos_x"] - 111.1) < 0.01
    assert abs(pos_map[node1_id]["pos_y"] - 222.2) < 0.01
    assert abs(pos_map[node2_id]["pos_x"] - 333.3) < 0.01
    assert abs(pos_map[node2_id]["pos_y"] - 444.4) < 0.01

    # ── Phase 2: Verify persisted ─────────────────────────────────────────────
    assert abs(get_node(client, headers, team_id, node1_id)["pos_x"] - 111.1) < 0.01
    assert abs(get_node(client, headers, team_id, node2_id)["pos_y"] - 444.4) < 0.01

    # ── Phase 3: Empty list → 200 with empty array ────────────────────────────
    r = client.put(f"{_BASE}/{team_id}/nodes/positions", headers=headers, json=[])
    assert r.status_code == 200
    assert r.json() == []

    # ── Phase 4: Foreign / non-existent node ID → 400 ────────────────────────
    r = client.put(
        f"{_BASE}/{team_id}/nodes/positions",
        headers=headers,
        json=[{"id": str(uuid.uuid4()), "pos_x": 0.0, "pos_y": 0.0}],
    )
    assert r.status_code == 400
    assert "do not belong" in r.json()["detail"]

    # ── Phase 5: Other user cannot bulk-update ────────────────────────────────
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client,
        email=other_user["email"],
        password=other_user["_password"],
    )
    r = client.put(
        f"{_BASE}/{team_id}/nodes/positions",
        headers=other_headers,
        json=[{"id": node1_id, "pos_x": 0.0, "pos_y": 0.0}],
    )
    assert r.status_code == 404

    # Cleanup
    delete_team(client, headers, team_id)


# ---------------------------------------------------------------------------
# Test 15 — Node creation with non-owned agent rejected
# ---------------------------------------------------------------------------

def test_node_creation_with_foreign_agent_rejected(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A user cannot add an agent they don't own as a node in their team.
    The service checks agent.owner_id == current_user.id.
    """
    # Superuser creates an agent
    su_agent = create_agent_via_api(client, superuser_token_headers, name="SU Foreign Agent")
    su_agent_id = su_agent["id"]

    # Normal user creates a team and tries to add the superuser's agent
    normal_headers = normal_user_token_headers
    team = create_team(client, normal_headers, name="Foreign Agent Team")
    team_id = team["id"]

    r = client.post(
        f"{_BASE}/{team_id}/nodes/",
        headers=normal_headers,
        json={"agent_id": su_agent_id, "is_lead": False},
    )
    # Agent not found from normal user's perspective (ownership check fails as 404)
    assert r.status_code == 404

    # Cleanup
    delete_team(client, normal_headers, team_id)


# ---------------------------------------------------------------------------
# Test 16 — list_teams returns only owner's teams
# ---------------------------------------------------------------------------

def test_list_teams_isolation(
    client: TestClient,
    normal_user_token_headers: dict[str, str],
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Each user's GET /agentic-teams/ returns only their own teams.
    Teams owned by another user do not appear in the listing.
    """
    normal_headers = normal_user_token_headers
    su_headers = superuser_token_headers

    normal_team = create_team(client, normal_headers, name="Normal User Team")
    su_team = create_team(client, su_headers, name="Superuser Team")

    # Normal user sees their own team but not superuser's
    normal_teams = list_teams(client, normal_headers)
    normal_ids = [t["id"] for t in normal_teams]
    assert normal_team["id"] in normal_ids
    assert su_team["id"] not in normal_ids

    # Superuser sees their own team but not normal user's
    su_teams = list_teams(client, su_headers)
    su_ids = [t["id"] for t in su_teams]
    assert su_team["id"] in su_ids
    assert normal_team["id"] not in su_ids

    # Cleanup
    delete_team(client, normal_headers, normal_team["id"])
    delete_team(client, su_headers, su_team["id"])
