"""
MCP Connector CRUD integration tests.

Tests the full CRUD lifecycle for MCP connectors:
  - Create, list, get, update, delete
  - Ownership enforcement (non-owners get 403)
  - Edge cases: nonexistent agent, nonexistent connector, empty list
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.mcp import (
    create_mcp_connector,
    delete_mcp_connector,
    get_mcp_connector,
    list_mcp_connectors,
    update_mcp_connector,
)
from tests.utils.user import create_random_user_with_headers


def test_mcp_connector_full_crud_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full CRUD lifecycle:
      1. Create agent
      2. Create MCP connector
      3. List connectors → verify it appears
      4. Get connector by ID → verify fields
      5. Update connector (name, mode, allowed_emails, is_active)
      6. Verify update persisted via GET
      7. Delete connector
      8. Verify it's gone (404)
    """
    # ── Phase 1: Create agent ─────────────────────────────────────────────
    agent = create_agent_via_api(client, superuser_token_headers, name="MCP CRUD Agent")
    drain_tasks()
    agent = get_agent(client, superuser_token_headers, agent["id"])
    agent_id = agent["id"]

    # ── Phase 2: Create MCP connector ─────────────────────────────────────
    connector = create_mcp_connector(
        client, superuser_token_headers, agent_id,
        name="My MCP Connector",
        mode="conversation",
        allowed_emails=["alice@example.com"],
        max_clients=5,
    )
    connector_id = connector["id"]
    assert connector["name"] == "My MCP Connector"
    assert connector["mode"] == "conversation"
    assert connector["is_active"] is True
    assert connector["allowed_emails"] == ["alice@example.com"]
    assert connector["max_clients"] == 5
    assert connector["agent_id"] == agent_id

    # ── Phase 3: List connectors → present ────────────────────────────────
    listing = list_mcp_connectors(client, superuser_token_headers, agent_id)
    assert listing["count"] == 1
    assert listing["data"][0]["id"] == connector_id

    # ── Phase 4: Get connector by ID ──────────────────────────────────────
    fetched = get_mcp_connector(client, superuser_token_headers, agent_id, connector_id)
    assert fetched["name"] == "My MCP Connector"
    assert fetched["mode"] == "conversation"
    assert fetched["max_clients"] == 5

    # ── Phase 5: Update connector ─────────────────────────────────────────
    updated = update_mcp_connector(
        client, superuser_token_headers, agent_id, connector_id,
        name="Renamed Connector",
        mode="building",
        allowed_emails=["bob@example.com", "carol@example.com"],
        is_active=False,
    )
    assert updated["name"] == "Renamed Connector"
    assert updated["mode"] == "building"
    assert updated["is_active"] is False
    assert set(updated["allowed_emails"]) == {"bob@example.com", "carol@example.com"}

    # ── Phase 6: Verify update persisted ──────────────────────────────────
    fetched2 = get_mcp_connector(client, superuser_token_headers, agent_id, connector_id)
    assert fetched2["name"] == "Renamed Connector"
    assert fetched2["mode"] == "building"
    assert fetched2["is_active"] is False

    # ── Phase 7: Delete connector ─────────────────────────────────────────
    delete_mcp_connector(client, superuser_token_headers, agent_id, connector_id)

    # ── Phase 8: Verify deleted (404) ─────────────────────────────────────
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


def test_mcp_connector_multiple_connectors_per_agent(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Multiple connectors on one agent:
      1. Create agent
      2. Create two connectors with different modes
      3. List → verify both appear with correct count
      4. Delete one → list shows only the other
    """
    # ── Setup ─────────────────────────────────────────────────────────────
    agent = create_agent_via_api(client, superuser_token_headers, name="Multi Connector Agent")
    drain_tasks()
    agent_id = agent["id"]

    # ── Create two connectors ─────────────────────────────────────────────
    c1 = create_mcp_connector(
        client, superuser_token_headers, agent_id,
        name="Conversation Connector", mode="conversation",
    )
    c2 = create_mcp_connector(
        client, superuser_token_headers, agent_id,
        name="Building Connector", mode="building",
    )

    # ── List → both present ───────────────────────────────────────────────
    listing = list_mcp_connectors(client, superuser_token_headers, agent_id)
    assert listing["count"] == 2
    ids = {c["id"] for c in listing["data"]}
    assert c1["id"] in ids
    assert c2["id"] in ids

    # ── Delete first → only second remains ────────────────────────────────
    delete_mcp_connector(client, superuser_token_headers, agent_id, c1["id"])
    listing2 = list_mcp_connectors(client, superuser_token_headers, agent_id)
    assert listing2["count"] == 1
    assert listing2["data"][0]["id"] == c2["id"]


def test_mcp_connector_ownership_enforcement(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Ownership enforcement:
      1. Superuser creates agent + connector
      2. Random user cannot list/get/update/delete that connector (403)
    """
    # ── Setup: superuser creates agent + connector ────────────────────────
    agent = create_agent_via_api(client, superuser_token_headers, name="Ownership Agent")
    drain_tasks()
    agent_id = agent["id"]

    connector = create_mcp_connector(
        client, superuser_token_headers, agent_id,
        name="Owner's Connector",
    )
    connector_id = connector["id"]

    # ── Create a different user ───────────────────────────────────────────
    _, other_headers = create_random_user_with_headers(client)

    # ── Other user: list → 403 (agent ownership check) ────────────────────
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors",
        headers=other_headers,
    )
    assert r.status_code == 403

    # ── Other user: get → 403 ─────────────────────────────────────────────
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=other_headers,
    )
    assert r.status_code == 403

    # ── Other user: update → 403 ──────────────────────────────────────────
    r = client.put(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=other_headers,
        json={"name": "Hacked Connector"},
    )
    assert r.status_code == 403

    # ── Other user: delete → 403 ──────────────────────────────────────────
    r = client.delete(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=other_headers,
    )
    assert r.status_code == 403

    # ── Original owner can still access ───────────────────────────────────
    fetched = get_mcp_connector(client, superuser_token_headers, agent_id, connector_id)
    assert fetched["name"] == "Owner's Connector"


def test_mcp_connector_nonexistent_agent(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Creating a connector on a nonexistent agent returns 404."""
    fake_agent_id = str(uuid.uuid4())
    r = client.post(
        f"{settings.API_V1_STR}/agents/{fake_agent_id}/mcp-connectors",
        headers=superuser_token_headers,
        json={"name": "Ghost Connector", "mode": "conversation"},
    )
    assert r.status_code == 404


def test_mcp_connector_nonexistent_connector(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Getting a nonexistent connector returns 404."""
    agent = create_agent_via_api(client, superuser_token_headers, name="404 Agent")
    drain_tasks()
    agent_id = agent["id"]

    fake_connector_id = str(uuid.uuid4())
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{fake_connector_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


def test_mcp_connector_empty_list(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Listing connectors on an agent with none returns empty list with count 0."""
    agent = create_agent_via_api(client, superuser_token_headers, name="Empty Agent")
    drain_tasks()
    agent_id = agent["id"]

    listing = list_mcp_connectors(client, superuser_token_headers, agent_id)
    assert listing["count"] == 0
    assert listing["data"] == []


def test_mcp_connector_partial_update(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Partial update: only update name, verify other fields unchanged.
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Partial Update Agent")
    drain_tasks()
    agent_id = agent["id"]

    connector = create_mcp_connector(
        client, superuser_token_headers, agent_id,
        name="Original Name",
        mode="conversation",
        allowed_emails=["alice@example.com"],
        max_clients=5,
    )
    connector_id = connector["id"]

    # Update only name
    updated = update_mcp_connector(
        client, superuser_token_headers, agent_id, connector_id,
        name="New Name",
    )
    assert updated["name"] == "New Name"
    assert updated["mode"] == "conversation"  # unchanged
    assert updated["allowed_emails"] == ["alice@example.com"]  # unchanged
    assert updated["max_clients"] == 5  # unchanged
    assert updated["is_active"] is True  # unchanged


def test_mcp_connector_unauthenticated_access(
    client: TestClient,
) -> None:
    """All connector endpoints reject unauthenticated requests (401)."""
    fake_agent_id = str(uuid.uuid4())

    r = client.get(f"{settings.API_V1_STR}/agents/{fake_agent_id}/mcp-connectors")
    assert r.status_code == 401

    r = client.post(
        f"{settings.API_V1_STR}/agents/{fake_agent_id}/mcp-connectors",
        json={"name": "Test", "mode": "conversation"},
    )
    assert r.status_code == 401
