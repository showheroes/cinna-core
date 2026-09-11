"""Owner connector lifecycle, scoped secrets and input/role guards via HTTP."""

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.acp import acp_connector_url, create_acp_connector, create_acp_token
from tests.utils.agent import create_agent_via_api
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.user import create_random_user_with_headers, promote_to_developer


def test_connector_lifecycle_preserves_owner_and_agent_boundaries(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Create/list/update, deny other users and agents, then delete the connector."""
    headers = superuser_token_headers
    agent = create_agent_via_api(client, headers)
    connector = create_acp_connector(
        client, headers, agent["id"], name=" External editor "
    )
    url = acp_connector_url(agent["id"], connector["id"])
    assert connector["name"] == "External editor"
    assert connector["mode"] == "conversation"
    assert connector["max_connections"] == 10
    assert connector["is_active"] is True
    assert connector["acp_server_url"] == f"wss://api.example.com/acp/{connector['id']}"
    listing = client.get(acp_connector_url(agent["id"]), headers=headers)
    assert listing.status_code == 200
    assert listing.json()["data"] == [connector]
    assert listing.json()["count"] == 1

    # Ownership is enforced on every method, with no superuser override.
    _, other_headers = create_random_user_with_headers(client)
    for method, payload in (
        ("get", None),
        ("put", {"name": "Stolen"}),
        ("delete", None),
    ):
        kwargs = {"json": payload} if payload is not None else {}
        assert (
            getattr(client, method)(url, headers=other_headers, **kwargs).status_code
            == 404
        )
    assert (
        client.get(acp_connector_url(agent["id"]), headers=other_headers).status_code
        == 404
    )
    assert (
        client.post(
            acp_connector_url(agent["id"]),
            headers=other_headers,
            json={"name": "Stolen"},
        ).status_code
        == 404
    )
    assert client.get(url).status_code == 401
    second_agent = create_agent_via_api(client, headers)
    wrong_agent_url = acp_connector_url(second_agent["id"], connector["id"])
    for method in ("get", "delete"):
        assert (
            getattr(client, method)(wrong_agent_url, headers=headers).status_code == 404
        )
    assert (
        client.put(
            wrong_agent_url, headers=headers, json={"is_active": False}
        ).status_code
        == 404
    )
    assert (
        client.get(
            acp_connector_url(agent["id"], str(uuid.uuid4())), headers=headers
        ).status_code
        == 404
    )

    updated = client.put(
        url,
        headers=headers,
        json={
            "name": "Renamed",
            "mode": "building",
            "is_active": False,
            "max_connections": 3,
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Renamed"
    assert updated.json()["mode"] == "building"
    assert updated.json()["max_connections"] == 3
    assert updated.json()["is_active"] is False
    assert client.get(url, headers=headers).json() == updated.json()
    assert client.delete(url, headers=headers).status_code == 200
    assert client.get(url, headers=headers).status_code == 404
    assert (
        client.get(acp_connector_url(agent["id"]), headers=headers).json()["count"] == 0
    )


def test_token_lifecycle_reveals_secret_once_and_scopes_mutations(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Mint/list tokens, deny foreign users/connectors, revoke and delete independently."""
    headers = superuser_token_headers
    agent = create_agent_via_api(client, headers)
    connector = create_acp_connector(client, headers, agent["id"])
    url = acp_connector_url(agent["id"], connector["id"])
    response = client.post(
        f"{url}/tokens",
        headers=headers,
        json={"label": " Editor ", "expires_in_days": 7},
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    first = response.json()
    assert first["label"] == "Editor"
    assert first["token"].startswith("acp_")
    assert len(first["token"]) >= 64
    assert first["prefix"] == first["token"][:12]
    assert "token_hash" not in first
    duration = datetime.fromisoformat(
        first["expires_at"].replace("Z", "+00:00")
    ) - datetime.fromisoformat(first["created_at"].replace("Z", "+00:00"))
    assert abs(duration - timedelta(days=7)) < timedelta(seconds=2)
    second = create_acp_token(
        client, headers, agent["id"], connector["id"], label="Automation"
    )
    assert second["token"] != first["token"]
    listing = client.get(f"{url}/tokens", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["count"] == 2
    assert first["token"] not in listing.text
    assert second["token"] not in listing.text
    assert all(
        "token_hash" not in t and "token" not in t for t in listing.json()["data"]
    )
    # An ACP token cannot authenticate to the management API.
    assert (
        client.get(
            f"{url}/tokens", headers={"Authorization": f"Bearer {first['token']}"}
        ).status_code
        == 403
    )

    _, other_headers = create_random_user_with_headers(client)
    assert client.get(f"{url}/tokens", headers=other_headers).status_code == 404
    assert (
        client.post(
            f"{url}/tokens", headers=other_headers, json={"label": "Stolen"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"{url}/tokens/{first['id']}/revoke", headers=other_headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{url}/tokens/{first['id']}", headers=other_headers).status_code
        == 404
    )
    another = create_acp_connector(client, headers, agent["id"])
    other_url = acp_connector_url(agent["id"], another["id"])
    assert (
        client.post(
            f"{other_url}/tokens/{first['id']}/revoke", headers=headers
        ).status_code
        == 404
    )
    assert (
        client.delete(f"{other_url}/tokens/{first['id']}", headers=headers).status_code
        == 404
    )
    assert (
        client.delete(f"{url}/tokens/{uuid.uuid4()}", headers=headers).status_code
        == 404
    )

    revoked = client.post(f"{url}/tokens/{first['id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True
    assert "token" not in revoked.json()
    assert (
        client.post(f"{url}/tokens/{first['id']}/revoke", headers=headers).status_code
        == 200
    )
    listed = client.get(f"{url}/tokens", headers=headers).json()["data"]
    assert {t["id"]: t["revoked"] for t in listed} == {
        first["id"]: True,
        second["id"]: False,
    }
    assert (
        client.delete(f"{url}/tokens/{first['id']}", headers=headers).status_code == 200
    )
    assert client.get(f"{url}/tokens", headers=headers).json()["count"] == 1
    assert client.delete(url, headers=headers).status_code == 200
    assert client.get(f"{url}/tokens", headers=headers).status_code == 404


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "  "},
        {"name": "x" * 256},
        {"mode": "shell"},
        {"max_connections": 0},
        {"max_connections": 101},
    ],
)
def test_connector_rejects_invalid_creation_and_updates(
    client: TestClient, superuser_token_headers: dict[str, str], fields: dict
) -> None:
    agent = create_agent_via_api(client, superuser_token_headers)
    base = acp_connector_url(agent["id"])
    assert (
        client.post(
            base, headers=superuser_token_headers, json={"name": "Valid", **fields}
        ).status_code
        == 422
    )
    connector = create_acp_connector(client, superuser_token_headers, agent["id"])
    assert (
        client.put(
            f"{base}/{connector['id']}", headers=superuser_token_headers, json=fields
        ).status_code
        == 422
    )


def test_token_input_validation_and_null_updates(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    agent = create_agent_via_api(client, superuser_token_headers)
    connector = create_acp_connector(client, superuser_token_headers, agent["id"])
    url = acp_connector_url(agent["id"], connector["id"])
    for fields in (
        {"label": ""},
        {"label": " "},
        {"expires_in_days": 0},
        {"expires_in_days": 366},
    ):
        assert (
            client.post(
                f"{url}/tokens",
                headers=superuser_token_headers,
                json={"label": "Valid", **fields},
            ).status_code
            == 422
        )
    for field in ("name", "mode", "is_active", "max_connections"):
        assert (
            client.put(
                url, headers=superuser_token_headers, json={field: None}
            ).status_code
            == 422
        )
    assert client.get(url, headers=superuser_token_headers).json() == connector


def test_building_connector_requires_current_developer_role(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """An owner demoted to agent-user can still use conversation but cannot enable building."""
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_token_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    agent = create_agent_via_api(client, headers)
    connector = create_acp_connector(client, headers, agent["id"])
    response = client.patch(
        f"{settings.API_V1_STR}/users/{user['id']}/role",
        headers=superuser_token_headers,
        json={"role": "agent-user"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            acp_connector_url(agent["id"]),
            headers=headers,
            json={"name": "Builder", "mode": "building"},
        ).status_code
        == 403
    )
    url = acp_connector_url(agent["id"], connector["id"])
    assert (
        client.put(url, headers=headers, json={"mode": "building"}).status_code == 403
    )
    assert (
        client.put(url, headers=headers, json={"name": "Conversation"}).status_code
        == 200
    )
    # Administrators cannot mint access to another owner's connector either.
    assert (
        client.post(
            f"{url}/tokens", headers=superuser_token_headers, json={"label": "Admin"}
        ).status_code
        == 404
    )
