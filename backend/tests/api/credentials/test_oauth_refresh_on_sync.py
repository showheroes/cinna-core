"""OAuth credential refresh on env sync / env start / stream start (Phase 1).

Plan: docs/plans/oauth_credential_refresh_plan.md §1, §6.2.

Google is never contacted: ``OAuthCredentialsService._exchange_refresh_token``
is replaced with an ``AsyncMock``. ``tests/utils/fixtures.py`` globally no-ops
``CredentialsService.refresh_expiring_credentials_for_agent`` (D6) through the
credentials ``patch_external_services`` autouse fixture, which would make every
test here vacuous — so this module overrides that fixture and patches only the
Socket.IO connector.

Near-expiry credentials are created via API with ``expires_at = now + 60``.
Env pushes are asserted on ``EnvironmentTestAdapter.credentials_set``.

Covers:
  a) Linking a near-expiry Google credential refreshes it before the push; the
     pushed payload has the new access_token and neither refresh_token nor the
     refresh-error bookkeeping fields. A later sync with a fresh token does not
     call Google again.
  b) Env restart (``_sync_dynamic_data``) refreshes before ``set_credentials``.
  c) Refresh failure during sync: old token still pushed, env not critical,
     metadata reports the error.
  d) Manual ``POST /oauth/refresh`` succeeds and calls Google exactly once.
  e) Stream start (single choke point) refreshes an expiring token and pushes
     it to the env before streaming.
  f) ``invalid_grant`` → metadata ``needs_reauthorization``; automatic paths
     stop calling Google; the re-authorization callback clears the flag.
"""
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.credentials.oauth_credentials_service import OAuthRefreshError
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.stubs.socketio_stub import StubSocketIOConnector
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.credential import (
    create_random_credential,
    link_credential_to_agent,
    real_credentials_json,
    update_credential,
)
from tests.utils.environment import get_environment
from tests.utils.message import send_message
from tests.utils.session import create_session_via_api

EXCHANGE = (
    "app.services.credentials.oauth_credentials_service."
    "OAuthCredentialsService._exchange_refresh_token"
)
OLD_ACCESS = "ya29.old-access-secret"
NEW_ACCESS = "ya29.new-access-secret"
REFRESH_TOKEN = "1//refresh-secret-value"
_BASE = f"{settings.API_V1_STR}"


@pytest.fixture(autouse=True)
def patch_external_services():
    """Override the conftest fixture: keep the REAL credential refresh."""
    # Google is also forced OFF by default (the container may have real client
    # credentials configured, which would let a sync reach the real token
    # endpoint); tests opt in with ``google_enabled()`` around a mocked exchange.
    with (
        patch(
            "app.services.events.event_service.socketio_connector", StubSocketIOConnector()
        ),
        patch.object(settings, "GOOGLE_CLIENT_ID", None),
        patch.object(settings, "GOOGLE_CLIENT_SECRET", None),
    ):
        yield


@contextmanager
def google_enabled():
    with (
        patch.object(settings, "GOOGLE_CLIENT_ID", "x"),
        patch.object(settings, "GOOGLE_CLIENT_SECRET", "x"),
    ):
        yield


@pytest.fixture
def exchange():
    """Mocked Google token exchange returning a fresh token by default."""
    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with patch(EXCHANGE, new=mock), google_enabled():
        yield mock


def _near_expiry_credential(client: TestClient, headers: dict[str, str]) -> dict:
    return create_random_credential(
        client,
        headers,
        credential_type="gmail_oauth",
        credential_data={
            "access_token": OLD_ACCESS,
            "refresh_token": REFRESH_TOKEN,
            "token_type": "Bearer",
            "expires_at": int(time.time()) + 60,
            "scope": "https://www.googleapis.com/auth/gmail.modify",
        },
    )


def _agent_with_shared_adapter(
    client: TestClient, headers: dict[str, str], patch_environment_adapter
) -> tuple[dict, EnvironmentTestAdapter]:
    agent = create_agent_via_api(client, headers)
    drain_tasks()
    agent = get_agent(client, headers, agent["id"])
    assert agent["active_environment_id"] is not None
    adapter = EnvironmentTestAdapter()
    patch_environment_adapter.get_adapter = lambda env: adapter
    return agent, adapter


def _entry(adapter: EnvironmentTestAdapter, credential_id: str) -> dict:
    entries = {e["id"]: e for e in real_credentials_json(adapter.credentials_set)}
    assert credential_id in entries, "credential was not pushed to the env"
    return entries[credential_id]


def _metadata(client: TestClient, headers: dict[str, str], credential_id: str) -> dict:
    r = client.get(f"{_BASE}/credentials/{credential_id}/oauth/metadata", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_link_refreshes_near_expiry_token_before_push(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
    exchange: AsyncMock,
) -> None:
    """
    1. Link a near-expiry Google credential → Google called once, env gets new token.
    2. Pushed payload has no refresh_token / refresh-error fields.
    3. A follow-up sync (credential update) finds the token fresh → no new Google call.
    """
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)

    link_credential_to_agent(client, headers, agent["id"], cred["id"])

    exchange.assert_awaited_once_with(REFRESH_TOKEN)
    entry = _entry(adapter, cred["id"])
    data = entry["credential_data"]
    assert data["access_token"] == NEW_ACCESS
    assert "refresh_token" not in data
    assert not any(k.startswith("refresh_") for k in data)
    assert data["expires_at"] > time.time() + 1800

    update_credential(client, headers, cred["id"], notes="touch")
    assert exchange.await_count == 1
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == NEW_ACCESS

    meta = _metadata(client, headers, cred["id"])
    assert meta["needs_reauthorization"] is False
    assert meta["refresh_error"] is None


def test_env_restart_refreshes_before_set_credentials(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    Link while Google is not configured (token stays old), then enable Google and
    restart the env: the env-start sync refreshes first, so ``set_credentials``
    receives the new token.
    """
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    link_credential_to_agent(client, headers, agent["id"], cred["id"])
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == OLD_ACCESS

    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with patch(EXCHANGE, new=mock), google_enabled():
        env_id = agent["active_environment_id"]
        r = client.post(f"{_BASE}/environments/{env_id}/restart", headers=headers)
        assert r.status_code == 200, r.text
        drain_tasks()

    mock.assert_awaited_once_with(REFRESH_TOKEN)
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == NEW_ACCESS


def test_refresh_failure_still_pushes_old_token_and_env_not_critical(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """Google 5xx during sync: old token pushed, env healthy, error visible in metadata."""
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    boom = AsyncMock(
        side_effect=OAuthRefreshError("provider_error", "Google token endpoint returned 503")
    )

    with patch(EXCHANGE, new=boom), google_enabled():
        link_credential_to_agent(client, headers, agent["id"], cred["id"])
        env_id = agent["active_environment_id"]
        r = client.post(f"{_BASE}/environments/{env_id}/restart", headers=headers)
        assert r.status_code == 200, r.text
        drain_tasks()

    assert boom.await_count >= 1
    data = _entry(adapter, cred["id"])["credential_data"]
    assert data["access_token"] == OLD_ACCESS
    assert "refresh_token" not in data
    assert not any(k.startswith("refresh_") for k in data)

    env = get_environment(client, headers, env_id)
    assert env["critical_state"] is False
    assert env["status"] == "running"

    meta = _metadata(client, headers, cred["id"])
    assert meta["refresh_error"]
    assert meta["needs_reauthorization"] is False
    assert REFRESH_TOKEN not in str(meta)


def test_manual_refresh_succeeds_with_single_google_call(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
    exchange: AsyncMock,
) -> None:
    """Manual refresh → 200, Google called exactly once (the follow-up sync finds it fresh)."""
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    with google_enabled(), patch(EXCHANGE, new=AsyncMock(side_effect=OAuthRefreshError(
        "provider_error", "down"
    ))):
        link_credential_to_agent(client, headers, agent["id"], cred["id"])
    exchange.reset_mock()

    r = client.post(f"{_BASE}/credentials/{cred['id']}/oauth/refresh", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Token refresh successful"
    assert r.json()["expires_at"] > time.time() + 1800
    assert exchange.await_count == 1
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == NEW_ACCESS
    assert _metadata(client, headers, cred["id"])["refresh_error"] is None


def test_stream_start_refreshes_expiring_token_and_pushes_to_env(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    The stream processor is the single choke point: sending a message refreshes
    the agent's near-expiry credential and syncs it to the env before streaming.
    """
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    link_credential_to_agent(client, headers, agent["id"], cred["id"])  # Google off: stays old
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == OLD_ACCESS

    session = create_session_via_api(client, headers, agent["id"])
    stub = StubAgentEnvConnector(response_text="ok")
    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with (
        patch(EXCHANGE, new=mock),
        google_enabled(),
        patch("app.services.sessions.message_service.agent_env_connector", stub),
    ):
        send_message(client, headers, session["id"], "hello")
        drain_tasks()

    assert len(stub.stream_calls) == 1
    assert mock.await_count == 1
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == NEW_ACCESS


def test_invalid_grant_flags_reauthorization_stops_retries_and_callback_clears(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    1. invalid_grant on sync → metadata needs_reauthorization=true.
    2. A further sync does not call Google again.
    3. The re-authorization callback stores a fresh grant → flag cleared.
    """
    headers = superuser_token_headers
    cred = _near_expiry_credential(client, headers)
    agent, adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    revoked = AsyncMock(
        side_effect=OAuthRefreshError("reauth_required", "Google rejected the refresh token")
    )

    with patch(EXCHANGE, new=revoked), google_enabled():
        link_credential_to_agent(client, headers, agent["id"], cred["id"])
        assert revoked.await_count == 1
        meta = _metadata(client, headers, cred["id"])
        assert meta["needs_reauthorization"] is True
        assert meta["refresh_error"]

        update_credential(client, headers, cred["id"], notes="again")
        assert revoked.await_count == 1  # reauth_required stops automatic attempts
        assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == OLD_ACCESS

        # ── Re-authorization: authorize → callback with a mocked token endpoint ──
        r = client.post(f"{_BASE}/credentials/{cred['id']}/oauth/authorize", headers=headers)
        assert r.status_code == 200, r.text
        state = r.json()["state"]

        token_resp = MagicMock(status_code=200, text="")
        token_resp.json.return_value = {
            "access_token": NEW_ACCESS,
            "refresh_token": "1//new-refresh",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "x",
        }
        userinfo_resp = MagicMock(status_code=404)
        fake_client = MagicMock()
        fake_client.post = AsyncMock(return_value=token_resp)
        fake_client.get = AsyncMock(return_value=userinfo_resp)
        fake_client.__aenter__ = AsyncMock(return_value=fake_client)
        fake_client.__aexit__ = AsyncMock(return_value=False)
        with patch(
            "app.services.credentials.oauth_credentials_service.httpx.AsyncClient",
            return_value=fake_client,
        ):
            r = client.post(
                f"{_BASE}/credentials/oauth/callback",
                json={"code": "auth-code", "state": state},
            )
        assert r.status_code == 200, r.text

    meta = _metadata(client, headers, cred["id"])
    assert meta["needs_reauthorization"] is False
    assert meta["refresh_error"] is None
    assert _entry(adapter, cred["id"])["credential_data"]["access_token"] == NEW_ACCESS


def test_mcp_provider_oauth_dcr_near_expiry_is_refreshed_on_sync(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """An authorized oauth_dcr mcp_provider whose token expires within the
    threshold is refreshed through its own token request when linking syncs it
    (and is not refreshed again once fresh)."""
    import uuid

    from app.services.mcp_providers.mcp_provider_oauth_service import MCPProviderOAuthService

    headers = superuser_token_headers
    base = "app.services.mcp_providers.mcp_provider_oauth_service.MCPProviderOAuthService"
    fake_meta = {
        "issuer": "https://external.example.com",
        "authorization_endpoint": "https://external.example.com/oauth/authorize",
        "token_endpoint": "https://external.example.com/oauth/token",
        "registration_endpoint": "https://external.example.com/oauth/register",
    }
    with (
        patch(f"{base}.discover_authorization_server", new=AsyncMock(return_value=fake_meta)),
        patch(f"{base}.register_client", new=AsyncMock(
            return_value={"client_id": "c", "client_secret": "s"})),
    ):
        r = client.post(
            f"{_BASE}/mcp-providers/connect/external",
            headers=headers,
            json={
                "endpoint_url": "https://external.example.com/mcp",
                "auth_mode": "oauth_dcr",
                "transport": "streamable-http",
                "label": "dcr",
                "mcp_mode_conversation": True,
                "mcp_mode_building": True,
            },
        )
    assert r.status_code == 200, r.text
    credential_id = r.json()["credential_id"]

    # Authorize through the real callback route; the token expires in 60 s.
    me = client.get(f"{_BASE}/users/me", headers=headers).json()
    state = MCPProviderOAuthService._put_state(
        uuid.UUID(str(credential_id)), uuid.UUID(me["id"]), "verifier"
    )
    seed = {"access_token": "initial-access", "refresh_token": "initial-refresh", "expires_in": 60}
    with patch(f"{base}._token_request", new=AsyncMock(return_value=seed)):
        cb = client.post(
            f"{_BASE}/mcp-providers/oauth/callback",
            headers=headers,
            json={"code": "seed-code", "state": state},
        )
    assert cb.status_code == 200, cb.text

    agent, _adapter = _agent_with_shared_adapter(client, headers, patch_environment_adapter)
    refreshed = {"access_token": "refreshed-access", "refresh_token": "new-refresh", "expires_in": 3600}
    token_request = AsyncMock(return_value=refreshed)
    with patch(f"{base}._token_request", new=token_request):
        link_credential_to_agent(client, headers, agent["id"], str(credential_id))
        assert token_request.await_count == 1
        update_credential(client, headers, str(credential_id), notes="touch")
        assert token_request.await_count == 1  # now fresh
