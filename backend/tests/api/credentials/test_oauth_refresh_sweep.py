"""Background OAuth refresh sweep (Phase 4).

Plan: docs/plans/oauth_credential_refresh_plan.md §4, §6.5. The sweep core is
driven directly through ``tests/utils/oauth_refresh.py`` (the scheduler job is
never started under TESTING). Google is mocked at the exchange seam; the
container's real Google client credentials are forced OFF except inside
``google_enabled()`` (see test_oauth_refresh_on_sync.py).

Covers: refresh + push for a running env; stopped env untouched;
``reauth_required`` rows never retried; one failing credential does not stop the
batch; a credential linked to two agents syncs each agent once.
"""
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.services.credentials.oauth_credentials_service import OAuthRefreshError
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.stubs.socketio_stub import StubSocketIOConnector
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.credential import (
    create_random_credential,
    link_credential_to_agent,
    real_credentials_json,
)
from tests.utils.environment import stop_environment
from tests.utils.oauth_refresh import run_oauth_refresh_sweep

EXCHANGE = (
    "app.services.credentials.oauth_credentials_service."
    "OAuthCredentialsService._exchange_refresh_token"
)
NEW_ACCESS = "ya29.new-access-secret"


@pytest.fixture(autouse=True)
def patch_external_services():
    with (
        patch("app.services.events.event_service.socketio_connector", StubSocketIOConnector()),
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


def _cred(client, headers, refresh_token: str, *, expires_in: int = 60) -> dict:
    return create_random_credential(
        client,
        headers,
        credential_type="gmail_oauth",
        credential_data={
            "access_token": f"ya29.old-{refresh_token}",
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_at": int(time.time()) + expires_in,
            "scope": "https://www.googleapis.com/auth/gmail.modify",
        },
    )


class Fleet:
    """Per-agent shared env adapters, so pushes can be inspected."""

    def __init__(self, lm):
        self.lm = lm
        self.adapters: dict[str, EnvironmentTestAdapter] = {}
        self.set_calls: dict[str, int] = {}
        lm.get_adapter = self._get

    def _get(self, env):
        key = str(env.agent_id)
        if key not in self.adapters:
            adapter = EnvironmentTestAdapter()
            orig = adapter.set_credentials
            self.set_calls[key] = 0

            async def counted(creds, _orig=orig, _key=key):
                self.set_calls[_key] += 1
                return await _orig(creds)

            adapter.set_credentials = counted
            self.adapters[key] = adapter
        return self.adapters[key]

    def new_agent(self, client, headers) -> dict:
        agent = create_agent_via_api(client, headers)
        drain_tasks()
        agent = get_agent(client, headers, agent["id"])
        self._get(type("E", (), {"agent_id": agent["id"]})())
        return agent

    def pushed_token(self, agent_id: str, credential_id: str) -> str | None:
        for e in real_credentials_json(self.adapters[agent_id].credentials_set):
            if e["id"] == credential_id:
                return e["credential_data"]["access_token"]
        return None


@pytest.fixture
def fleet(patch_environment_adapter) -> Fleet:
    return Fleet(patch_environment_adapter)


def test_sweep_refreshes_near_expiry_credential_and_pushes_to_running_env(
    client: TestClient, superuser_token_headers, fleet: Fleet, db: Session
) -> None:
    agent = fleet.new_agent(client, superuser_token_headers)
    cred = _cred(client, superuser_token_headers, "1//rt-a")
    link_credential_to_agent(client, superuser_token_headers, agent["id"], cred["id"])
    assert fleet.pushed_token(agent["id"], cred["id"]) == "ya29.old-1//rt-a"

    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with patch(EXCHANGE, new=mock), google_enabled():
        stats = run_oauth_refresh_sweep(db)
        again = run_oauth_refresh_sweep(db)

    assert stats["refreshed"] == 1 and stats["agents_synced"] == 1
    assert stats["checked"] >= 1
    mock.assert_awaited_once_with("1//rt-a")
    assert fleet.pushed_token(agent["id"], cred["id"]) == NEW_ACCESS
    assert again["refreshed"] == 0  # now fresh


def test_sweep_ignores_agents_with_only_stopped_envs(
    client: TestClient, superuser_token_headers, fleet: Fleet, db: Session
) -> None:
    agent = fleet.new_agent(client, superuser_token_headers)
    cred = _cred(client, superuser_token_headers, "1//rt-stopped")
    link_credential_to_agent(client, superuser_token_headers, agent["id"], cred["id"])
    stop_environment(client, superuser_token_headers, agent["active_environment_id"])

    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with patch(EXCHANGE, new=mock), google_enabled():
        stats = run_oauth_refresh_sweep(db)
    mock.assert_not_called()
    assert stats["refreshed"] == 0 and stats["agents_synced"] == 0


def test_sweep_does_not_retry_reauth_required_credentials(
    client: TestClient, superuser_token_headers, fleet: Fleet, db: Session
) -> None:
    agent = fleet.new_agent(client, superuser_token_headers)
    cred = _cred(client, superuser_token_headers, "1//rt-revoked")
    revoked = AsyncMock(side_effect=OAuthRefreshError("reauth_required", "rejected"))
    with patch(EXCHANGE, new=revoked), google_enabled():
        link_credential_to_agent(client, superuser_token_headers, agent["id"], cred["id"])
        assert revoked.await_count == 1  # recorded by the link-time sync
        stats = run_oauth_refresh_sweep(db)
    assert revoked.await_count == 1  # the sweep did not call Google again
    assert stats["refreshed"] == 0


def test_one_failing_credential_does_not_stop_the_next(
    client: TestClient, superuser_token_headers, fleet: Fleet, db: Session
) -> None:
    agent = fleet.new_agent(client, superuser_token_headers)
    bad = _cred(client, superuser_token_headers, "1//rt-bad")
    good = _cred(client, superuser_token_headers, "1//rt-good")
    link_credential_to_agent(client, superuser_token_headers, agent["id"], bad["id"])
    link_credential_to_agent(client, superuser_token_headers, agent["id"], good["id"])

    async def exchange(refresh_token):
        if refresh_token == "1//rt-bad":
            raise OAuthRefreshError("provider_error", "Google returned 503")
        return {"access_token": NEW_ACCESS, "expires_in": 3600}

    with patch(EXCHANGE, new=AsyncMock(side_effect=exchange)), google_enabled():
        stats = run_oauth_refresh_sweep(db)

    assert stats["refreshed"] == 1
    assert stats["failed"] == 1
    assert fleet.pushed_token(agent["id"], good["id"]) == NEW_ACCESS
    assert fleet.pushed_token(agent["id"], bad["id"]) == "ya29.old-1//rt-bad"


def test_credential_linked_to_two_agents_syncs_each_agent_once(
    client: TestClient, superuser_token_headers, fleet: Fleet, db: Session
) -> None:
    a1 = fleet.new_agent(client, superuser_token_headers)
    a2 = fleet.new_agent(client, superuser_token_headers)
    cred = _cred(client, superuser_token_headers, "1//rt-shared")
    link_credential_to_agent(client, superuser_token_headers, a1["id"], cred["id"])
    link_credential_to_agent(client, superuser_token_headers, a2["id"], cred["id"])
    before = dict(fleet.set_calls)

    mock = AsyncMock(return_value={"access_token": NEW_ACCESS, "expires_in": 3600})
    with patch(EXCHANGE, new=mock), google_enabled():
        stats = run_oauth_refresh_sweep(db)

    assert mock.await_count == 1  # one Google call for the shared credential
    assert stats["refreshed"] == 1 and stats["agents_synced"] == 2
    for a in (a1, a2):
        assert fleet.set_calls[a["id"]] - before[a["id"]] == 1
        assert fleet.pushed_token(a["id"], cred["id"]) == NEW_ACCESS
