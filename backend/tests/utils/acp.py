"""ACP test setup through the authenticated management API."""

from fastapi.testclient import TestClient

from app.core.config import settings


def acp_connector_url(agent_id: str, connector_id: str | None = None) -> str:
    base = f"{settings.API_V1_STR}/agents/{agent_id}/acp-connectors"
    return f"{base}/{connector_id}" if connector_id else base


def create_acp_connector(
    client: TestClient, headers: dict[str, str], agent_id: str, **fields: object
) -> dict:
    response = client.post(
        acp_connector_url(agent_id),
        headers=headers,
        json={"name": "ACP client", **fields},
    )
    assert response.status_code == 200, response.text
    return response.json()


def create_acp_token(
    client: TestClient,
    headers: dict[str, str],
    agent_id: str,
    connector_id: str,
    **fields: object,
) -> dict:
    response = client.post(
        f"{acp_connector_url(agent_id, connector_id)}/tokens",
        headers=headers,
        json={"label": "Test client", **fields},
    )
    assert response.status_code == 200, response.text
    return response.json()
