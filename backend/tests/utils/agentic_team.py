"""Helpers for AgenticTeam, AgenticTeamNode, and AgenticTeamConnection API tests."""
from fastapi.testclient import TestClient

from app.core.config import settings

_BASE = f"{settings.API_V1_STR}/agentic-teams"


# ---------------------------------------------------------------------------
# AgenticTeam helpers
# ---------------------------------------------------------------------------

def create_team(
    client: TestClient,
    headers: dict,
    name: str = "Test Team",
    icon: str | None = "users",
) -> dict:
    """POST /agentic-teams/ — asserts 200 and returns body."""
    payload: dict = {"name": name}
    if icon is not None:
        payload["icon"] = icon
    r = client.post(_BASE + "/", headers=headers, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def get_team(client: TestClient, headers: dict, team_id: str) -> dict:
    """GET /agentic-teams/{team_id} — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{team_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def list_teams(client: TestClient, headers: dict) -> list[dict]:
    """GET /agentic-teams/ — asserts 200 and returns data list."""
    r = client.get(_BASE + "/", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def update_team(
    client: TestClient,
    headers: dict,
    team_id: str,
    **fields,
) -> dict:
    """PUT /agentic-teams/{team_id} — asserts 200 and returns body."""
    r = client.put(f"{_BASE}/{team_id}", headers=headers, json=fields)
    assert r.status_code == 200, r.text
    return r.json()


def delete_team(client: TestClient, headers: dict, team_id: str) -> dict:
    """DELETE /agentic-teams/{team_id} — asserts 200 and returns body."""
    r = client.delete(f"{_BASE}/{team_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# AgenticTeamNode helpers
# ---------------------------------------------------------------------------

def create_node(
    client: TestClient,
    headers: dict,
    team_id: str,
    agent_id: str,
    is_lead: bool = False,
    pos_x: float = 0.0,
    pos_y: float = 0.0,
) -> dict:
    """POST /agentic-teams/{team_id}/nodes/ — asserts 200 and returns body."""
    r = client.post(
        f"{_BASE}/{team_id}/nodes/",
        headers=headers,
        json={"agent_id": agent_id, "is_lead": is_lead, "pos_x": pos_x, "pos_y": pos_y},
    )
    assert r.status_code == 200, r.text
    return r.json()


def get_node(client: TestClient, headers: dict, team_id: str, node_id: str) -> dict:
    """GET /agentic-teams/{team_id}/nodes/{node_id} — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{team_id}/nodes/{node_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def list_nodes(client: TestClient, headers: dict, team_id: str) -> list[dict]:
    """GET /agentic-teams/{team_id}/nodes/ — asserts 200 and returns data list."""
    r = client.get(f"{_BASE}/{team_id}/nodes/", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def delete_node(client: TestClient, headers: dict, team_id: str, node_id: str) -> dict:
    """DELETE /agentic-teams/{team_id}/nodes/{node_id} — asserts 200 and returns body."""
    r = client.delete(f"{_BASE}/{team_id}/nodes/{node_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# AgenticTeamConnection helpers
# ---------------------------------------------------------------------------

def create_connection(
    client: TestClient,
    headers: dict,
    team_id: str,
    source_node_id: str,
    target_node_id: str,
    connection_prompt: str = "",
    enabled: bool = True,
) -> dict:
    """POST /agentic-teams/{team_id}/connections/ — asserts 200 and returns body."""
    r = client.post(
        f"{_BASE}/{team_id}/connections/",
        headers=headers,
        json={
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "connection_prompt": connection_prompt,
            "enabled": enabled,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def get_connection(
    client: TestClient, headers: dict, team_id: str, conn_id: str
) -> dict:
    """GET /agentic-teams/{team_id}/connections/{conn_id} — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{team_id}/connections/{conn_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def list_connections(client: TestClient, headers: dict, team_id: str) -> list[dict]:
    """GET /agentic-teams/{team_id}/connections/ — asserts 200 and returns data list."""
    r = client.get(f"{_BASE}/{team_id}/connections/", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def delete_connection(
    client: TestClient, headers: dict, team_id: str, conn_id: str
) -> dict:
    """DELETE /agentic-teams/{team_id}/connections/{conn_id} — asserts 200."""
    r = client.delete(f"{_BASE}/{team_id}/connections/{conn_id}", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def get_chart(client: TestClient, headers: dict, team_id: str) -> dict:
    """GET /agentic-teams/{team_id}/chart — asserts 200 and returns body."""
    r = client.get(f"{_BASE}/{team_id}/chart", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()
