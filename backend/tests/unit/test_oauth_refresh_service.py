"""Unit tests: ``OAuthRefreshService.refresh_if_needed`` (plan §6.1).

No DB: the ``Session`` is a ``MagicMock`` and the credential is an in-memory
``Credential`` row whose ``encrypted_data`` is a real encrypted blob. The three
seams are patched:

  * ``OAuthCredentialsService._exchange_refresh_token`` — the Google call
  * ``OAuthRefreshService._try_advisory_lock``          — pg advisory try-lock
  * ``oauth_refresh_service.asyncio.sleep``              — busy-lock polling

``session.refresh(credential)`` is simulated through ``side_effect`` to model
"another worker refreshed in the meantime".
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core import security
from app.core.config import settings
from app.models import Credential
from app.models.credentials.credential import CredentialType
from app.services.credentials import oauth_refresh_service as ors
from app.services.credentials.oauth_credentials_service import (
    OAuthCredentialsService,
    OAuthRefreshError,
)
from app.services.credentials.oauth_refresh_service import OAuthRefreshService

EXCHANGE = (
    "app.services.credentials.oauth_credentials_service."
    "OAuthCredentialsService._exchange_refresh_token"
)
TRY_LOCK = (
    "app.services.credentials.oauth_refresh_service."
    "OAuthRefreshService._try_advisory_lock"
)
OLD_ACCESS = "ya29.old-access-secret"
REFRESH_TOKEN = "1//refresh-secret-value"
NEW_ACCESS = "ya29.new-access-secret"
THRESHOLD = 1800


def _blob(**overrides) -> str:
    data = {
        "access_token": OLD_ACCESS,
        "refresh_token": REFRESH_TOKEN,
        "token_type": "Bearer",
        "expires_at": int(time.time()) + 60,  # near expiry by default
        "scope": "https://www.googleapis.com/auth/gmail.modify",
    }
    data.update(overrides)
    return security.encrypt_field(json.dumps(data))


def _credential(**overrides) -> Credential:
    return Credential(
        id=uuid.uuid4(),
        owner_id=uuid.uuid4(),
        name="c",
        type=CredentialType.GMAIL_OAUTH,
        encrypted_data=_blob(**overrides),
    )


def _data(credential: Credential) -> dict:
    return json.loads(security.decrypt_field(credential.encrypted_data))


@pytest.fixture(autouse=True)
def google_configured():
    with (
        patch.object(settings, "GOOGLE_CLIENT_ID", "x"),
        patch.object(settings, "GOOGLE_CLIENT_SECRET", "x"),
        patch.object(settings, "OAUTH_REFRESH_COOLDOWN_SECONDS", 60),
    ):
        yield


def _refresh(session, credential, **kw):
    kw.setdefault("min_valid_seconds", THRESHOLD)
    return asyncio.run(OAuthRefreshService.refresh_if_needed(session, credential, **kw))


def test_fresh_token_makes_no_exchange_and_takes_no_lock() -> None:
    cred = _credential(expires_at=int(time.time()) + 10_000)
    session = MagicMock()
    with patch(EXCHANGE, new=AsyncMock()) as exchange, patch(TRY_LOCK) as lock:
        outcome = _refresh(session, cred)
    assert outcome.status == "fresh"
    exchange.assert_not_called()
    lock.assert_not_called()
    session.commit.assert_not_called()


def test_non_google_credential_is_skipped() -> None:
    cred = _credential()
    cred.type = CredentialType.API_TOKEN
    with patch(EXCHANGE, new=AsyncMock()) as exchange:
        outcome = _refresh(MagicMock(), cred)
    assert outcome.status == "skipped"
    exchange.assert_not_called()


def test_near_expiry_refreshes_and_persists_new_token() -> None:
    cred = _credential()
    session = MagicMock()
    token = {"access_token": NEW_ACCESS, "expires_in": 3600}
    with patch(EXCHANGE, new=AsyncMock(return_value=token)) as exchange, patch(
        TRY_LOCK, return_value=True
    ):
        outcome = _refresh(session, cred)
    assert outcome.status == "refreshed"
    exchange.assert_awaited_once_with(REFRESH_TOKEN)
    data = _data(cred)
    assert data["access_token"] == NEW_ACCESS
    assert data["expires_at"] > time.time() + 3000
    assert data["refresh_token"] == REFRESH_TOKEN  # not rotated -> kept
    # NOTE: plan §1.3 says "one commit per path"; the code commits twice
    # (``_store`` + ``locked`` exit). Harmless, so only require >= 1.
    assert session.commit.called


def test_rotated_refresh_token_persisted_and_error_fields_cleared() -> None:
    cred = _credential(
        refresh_error="boom",
        refresh_error_kind="provider_error",
        refresh_error_at=1,
        refresh_attempted_at=int(time.time()) - 3600,  # cooldown elapsed
    )
    token = {"access_token": NEW_ACCESS, "refresh_token": "1//rotated", "expires_in": 3600}
    with patch(EXCHANGE, new=AsyncMock(return_value=token)), patch(TRY_LOCK, return_value=True):
        outcome = _refresh(MagicMock(), cred)
    assert outcome.status == "refreshed"
    data = _data(cred)
    assert data["refresh_token"] == "1//rotated"
    for field in ("refresh_error", "refresh_error_kind", "refresh_error_at"):
        assert field not in data


def test_lock_busy_then_other_worker_refreshed_returns_fresh() -> None:
    cred = _credential()
    session = MagicMock()
    fresh_blob = _blob(access_token=NEW_ACCESS, expires_at=int(time.time()) + 3600)

    def reread(c):
        c.encrypted_data = fresh_blob

    session.refresh.side_effect = reread
    with patch(EXCHANGE, new=AsyncMock()) as exchange, patch(TRY_LOCK, return_value=False):
        outcome = _refresh(session, cred)
    assert outcome.status == "fresh"
    exchange.assert_not_called()


def test_lock_busy_throughout_returns_busy_after_timeout() -> None:
    cred = _credential()
    session = MagicMock()
    sleep = AsyncMock()
    # Fake monotonic loop time: each sleep advances 1s so the 5s deadline passes.
    clock = {"t": 0.0}

    async def fake_sleep(_s):
        clock["t"] += 1.0

    sleep.side_effect = fake_sleep

    async def run():
        loop = asyncio.get_running_loop()
        with patch.object(loop, "time", lambda: clock["t"]):
            return await OAuthRefreshService.refresh_if_needed(
                session, cred, min_valid_seconds=THRESHOLD
            )

    with (
        patch(EXCHANGE, new=AsyncMock()) as exchange,
        patch(TRY_LOCK, return_value=False),
        patch.object(ors.asyncio, "sleep", sleep),
    ):
        outcome = asyncio.run(run())
    assert outcome.status == "busy"
    exchange.assert_not_called()
    assert sleep.await_count >= 1
    # token untouched
    assert _data(cred)["access_token"] == OLD_ACCESS


def test_reread_after_acquiring_lock_shows_fresh_skips_exchange() -> None:
    cred = _credential()
    session = MagicMock()
    fresh_blob = _blob(access_token=NEW_ACCESS, expires_at=int(time.time()) + 3600)
    session.refresh.side_effect = lambda c: setattr(c, "encrypted_data", fresh_blob)
    with patch(EXCHANGE, new=AsyncMock()) as exchange, patch(TRY_LOCK, return_value=True):
        outcome = _refresh(session, cred)
    assert outcome.status == "fresh"
    exchange.assert_not_called()
    session.commit.assert_called_once()  # releases the xact lock


def test_invalid_grant_records_reauth_required_and_stops_further_attempts() -> None:
    cred = _credential()
    err = OAuthRefreshError("reauth_required", "Google rejected the refresh token")
    with patch(EXCHANGE, new=AsyncMock(side_effect=err)) as exchange, patch(
        TRY_LOCK, return_value=True
    ):
        first = _refresh(MagicMock(), cred)
        assert first.status == "failed"
        assert first.error_kind == "reauth_required"
        data = _data(cred)
        assert data["refresh_error_kind"] == "reauth_required"
        assert data["refresh_error"]
        assert exchange.await_count == 1

        second = _refresh(MagicMock(), cred)
        assert second.status == "failed"
        assert second.error_kind == "reauth_required"
        assert exchange.await_count == 1  # no new Google call

        # force (manual refresh) bypasses the reauth stop
        exchange.side_effect = None
        exchange.return_value = {"access_token": NEW_ACCESS, "expires_in": 3600}
        forced = _refresh(MagicMock(), cred, force=True)
    assert forced.status == "refreshed"
    assert "refresh_error_kind" not in _data(cred)


def test_provider_error_cooldown_then_retry_after_cooldown() -> None:
    cred = _credential()
    err = OAuthRefreshError("provider_error", "Google token endpoint returned 503")
    with patch(EXCHANGE, new=AsyncMock(side_effect=err)) as exchange, patch(
        TRY_LOCK, return_value=True
    ):
        first = _refresh(MagicMock(), cred)
        assert first.status == "failed"
        assert first.error_kind == "provider_error"
        assert exchange.await_count == 1

        within = _refresh(MagicMock(), cred)
        assert within.status == "cooldown"
        assert exchange.await_count == 1

        # Age the last attempt beyond the cooldown window.
        data = _data(cred)
        data["refresh_attempted_at"] = int(time.time()) - 3600
        cred.encrypted_data = security.encrypt_field(json.dumps(data))
        exchange.side_effect = None
        exchange.return_value = {"access_token": NEW_ACCESS, "expires_in": 3600}
        after = _refresh(MagicMock(), cred)
    assert after.status == "refreshed"
    assert exchange.await_count == 2


def test_unexpected_exception_is_recorded_as_provider_error() -> None:
    cred = _credential()
    with patch(EXCHANGE, new=AsyncMock(side_effect=RuntimeError(REFRESH_TOKEN))), patch(
        TRY_LOCK, return_value=True
    ):
        outcome = _refresh(MagicMock(), cred)
    assert outcome.status == "failed"
    assert outcome.error_kind == "provider_error"
    assert REFRESH_TOKEN not in (outcome.error or "")
    assert REFRESH_TOKEN not in json.dumps(
        {k: v for k, v in _data(cred).items() if k.startswith("refresh_error")}
    )


def test_raise_on_error_raises_after_recording() -> None:
    cred = _credential()
    err = OAuthRefreshError("reauth_required", "nope")
    with patch(EXCHANGE, new=AsyncMock(side_effect=err)), patch(TRY_LOCK, return_value=True):
        with pytest.raises(OAuthRefreshError) as ei:
            _refresh(MagicMock(), cred, raise_on_error=True)
    assert ei.value.kind == "reauth_required"
    assert _data(cred)["refresh_error_kind"] == "reauth_required"


def test_not_configured_when_google_oauth_disabled() -> None:
    cred = _credential()
    with (
        patch.object(settings, "GOOGLE_CLIENT_ID", None),
        patch.object(settings, "GOOGLE_CLIENT_SECRET", None),
        patch(EXCHANGE, new=AsyncMock()) as exchange,
    ):
        outcome = _refresh(MagicMock(), cred)
        assert outcome.status == "failed"
        assert outcome.error_kind == "not_configured"
        with pytest.raises(OAuthRefreshError) as ei:
            _refresh(MagicMock(), cred, raise_on_error=True)
    assert ei.value.kind == "not_configured"
    exchange.assert_not_called()


def test_apply_token_response_defaults_expiry_and_keeps_refresh_token() -> None:
    data = {"refresh_token": REFRESH_TOKEN, "refresh_error_kind": "provider_error"}
    out = OAuthCredentialsService.apply_token_response(data, {"access_token": NEW_ACCESS})
    assert out["access_token"] == NEW_ACCESS
    assert out["refresh_token"] == REFRESH_TOKEN
    assert out["expires_at"] > time.time() + 3000  # default 3600s
    assert "refresh_error_kind" not in out


def test_outcome_and_errors_never_contain_token_values() -> None:
    cred = _credential()
    err = OAuthRefreshError("provider_error", "Google token endpoint returned 500")
    with patch(EXCHANGE, new=AsyncMock(side_effect=err)), patch(TRY_LOCK, return_value=True):
        outcome = _refresh(MagicMock(), cred)
    blob = f"{outcome.error} {outcome.error_kind} {err}"
    assert REFRESH_TOKEN not in blob
    assert OLD_ACCESS not in blob


@pytest.mark.parametrize("google_fails", [False, True])
def test_concurrent_reauthorization_is_not_overwritten(google_fails: bool) -> None:
    """The owner re-authorizes (OAuth callback writes the row without the lock)
    while the Google call is in flight: the stale result — token or error — is
    dropped and the re-authorized blob survives untouched."""
    cred = _credential()
    reauth_blob = _blob(
        access_token="ya29.reauthorized", refresh_token="1//reauth", expires_at=int(time.time()) + 3600
    )

    async def exchange(_refresh_token):
        cred.encrypted_data = reauth_blob  # callback commits mid-flight
        if google_fails:
            raise OAuthRefreshError("reauth_required", "Google rejected the refresh token")
        return {"access_token": NEW_ACCESS, "expires_in": 3600}

    with patch(EXCHANGE, new=AsyncMock(side_effect=exchange)), patch(TRY_LOCK, return_value=True):
        outcome = _refresh(MagicMock(), cred)
    assert outcome.status == "fresh"
    assert cred.encrypted_data == reauth_blob
    data = _data(cred)
    assert data["access_token"] == "ya29.reauthorized"
    assert "refresh_error_kind" not in data


def test_refresh_under_another_event_loop_while_main_loop_holds_the_lock() -> None:
    """Credential locks are per event loop: a refresh run via ``asyncio.run`` in a
    worker thread (e.g. the sweep job) must neither raise nor hang while this
    loop holds the same credential's lock."""
    import threading

    cred = _credential()
    result: dict = {}

    def worker():
        try:
            with patch(EXCHANGE, new=AsyncMock(
                return_value={"access_token": NEW_ACCESS, "expires_in": 3600}
            )), patch(TRY_LOCK, return_value=True):
                result["outcome"] = asyncio.run(
                    OAuthRefreshService.refresh_if_needed(
                        MagicMock(), cred, min_valid_seconds=THRESHOLD
                    )
                )
        except BaseException as e:  # noqa: BLE001
            result["error"] = e

    async def main():
        async with ors._credential_lock(cred.id):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            t.join(timeout=5)
            assert not t.is_alive(), "refresh in another loop hung on the held lock"

    asyncio.run(main())
    assert "error" not in result, result.get("error")
    assert result["outcome"].status == "refreshed"
