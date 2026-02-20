from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.utils import random_lower_string


def create_random_ai_credential(
    client: TestClient,
    token_headers: dict[str, str],
    credential_type: str = "anthropic",
    api_key: str | None = None,
    name: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    set_default: bool = False,
) -> dict:
    """Create a random AI credential via the API and return the response data.

    If *set_default* is True, also calls set-default so the credential becomes
    the active default for its type.
    """
    name = name or f"test-ai-cred-{random_lower_string()[:12]}"
    api_key = api_key or f"sk-ant-api03-{random_lower_string()}"

    data: dict = {
        "name": name,
        "type": credential_type,
        "api_key": api_key,
    }
    if base_url is not None:
        data["base_url"] = base_url
    if model is not None:
        data["model"] = model

    r = client.post(
        f"{settings.API_V1_STR}/ai-credentials/",
        headers=token_headers,
        json=data,
    )
    assert r.status_code == 200
    cred = r.json()

    if set_default:
        set_ai_credential_default(client, token_headers, cred["id"])

    return cred


def set_ai_credential_default(
    client: TestClient,
    token_headers: dict[str, str],
    credential_id: str,
) -> dict:
    """Set an AI credential as the default for its type."""
    r = client.post(
        f"{settings.API_V1_STR}/ai-credentials/{credential_id}/set-default",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()


def get_ai_credential(
    client: TestClient,
    token_headers: dict[str, str],
    credential_id: str,
) -> dict:
    """GET /ai-credentials/{id} — returns a single AI credential."""
    r = client.get(
        f"{settings.API_V1_STR}/ai-credentials/{credential_id}",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()


def list_ai_credentials(
    client: TestClient,
    token_headers: dict[str, str],
) -> dict:
    """GET /ai-credentials/ — returns {data: [...], count: N}."""
    r = client.get(
        f"{settings.API_V1_STR}/ai-credentials/",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()


def update_ai_credential(
    client: TestClient,
    token_headers: dict[str, str],
    credential_id: str,
    **fields,
) -> dict:
    """Update an AI credential via PATCH and return updated data."""
    r = client.patch(
        f"{settings.API_V1_STR}/ai-credentials/{credential_id}",
        headers=token_headers,
        json=fields,
    )
    assert r.status_code == 200
    return r.json()


def delete_ai_credential(
    client: TestClient,
    token_headers: dict[str, str],
    credential_id: str,
) -> None:
    """Delete an AI credential."""
    r = client.delete(
        f"{settings.API_V1_STR}/ai-credentials/{credential_id}",
        headers=token_headers,
    )
    assert r.status_code == 200


def get_ai_credentials_profile(
    client: TestClient,
    token_headers: dict[str, str],
) -> dict:
    """GET /users/me/ai-credentials — returns the user's AI credentials profile."""
    r = client.get(
        f"{settings.API_V1_STR}/users/me/ai-credentials",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()


def get_ai_credentials_status(
    client: TestClient,
    token_headers: dict[str, str],
) -> dict:
    """GET /users/me/ai-credentials/status — returns has_*_api_key flags."""
    r = client.get(
        f"{settings.API_V1_STR}/users/me/ai-credentials/status",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()


def get_affected_environments(
    client: TestClient,
    token_headers: dict[str, str],
    credential_id: str,
) -> dict:
    """GET /ai-credentials/{id}/affected-environments."""
    r = client.get(
        f"{settings.API_V1_STR}/ai-credentials/{credential_id}/affected-environments",
        headers=token_headers,
    )
    assert r.status_code == 200
    return r.json()
