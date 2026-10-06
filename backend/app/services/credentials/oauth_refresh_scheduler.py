"""Periodic refresh sweep for OAuth credentials used by running environments.

Refresh-on-sync and refresh-on-stream only fire when something happens. A
script running in an idle environment (no new turn, no credential edit) would
otherwise see its synced Google access token expire after an hour. Every
``OAUTH_REFRESH_SWEEP_INTERVAL_MINUTES`` this sweep refreshes OAuth tokens of
credentials linked to an agent with a running environment once they fall
within ``OAUTH_REFRESH_THRESHOLD_SECONDS`` of expiry, and pushes the refreshed
payload to the affected agents' running environments.

Covered types: Google OAuth credentials (through
``OAuthRefreshService.refresh_if_needed``) and ``mcp_provider`` ``oauth_dcr``
credentials (through ``CredentialsService._refresh_expiring_mcp_provider``).
Both share the per-credential lock, so the sweep never double-refreshes with
a concurrent sync, stream or env endpoint call.

Single-leader across workers via :func:`app.core.db.leader_session` (pinned
connection; per-credential commits are safe on it). Never started under
``settings.TESTING``.

The APScheduler thread hands each sweep to the **main event loop**
(``run_coroutine_threadsafe``, same idiom as the key-provisioning and
status-repair sweeps) instead of ``asyncio.run``: the refresh path shares
in-process locks and adapter calls with request handlers on that loop, and a
throwaway loop in a worker thread must not touch them.
"""
import asyncio
import logging
import time
import uuid

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from app.core.config import settings
from app.core.db import leader_session
from app.models import AgentCredentialLink, AgentEnvironment, Credential, CredentialType
from app.services.credentials.credentials_service import CredentialsService
from app.services.credentials.oauth_refresh_service import (
    GOOGLE_OAUTH_TYPES,
    OAuthRefreshService,
)

logger = logging.getLogger(__name__)

OAUTH_REFRESH_SWEEP_LOCK_KEY = 0x4F415554485246  # "OAUTHRF"

scheduler = BackgroundScheduler()


# How long the APScheduler thread waits for a sweep handed to the main loop.
# A constant: shutdown waits on this thread.
SWEEP_WAIT_TIMEOUT_SECONDS = 300

_main_loop: asyncio.AbstractEventLoop | None = None


def _candidate_credential_ids(
    session: Session, limit: int, after: uuid.UUID | None = None
) -> list[uuid.UUID]:
    """One keyset page of ids of OAuth credentials linked to an agent with a
    running environment, ordered by id, strictly after ``after``."""
    google_types = [CredentialType(t) for t in GOOGLE_OAUTH_TYPES]
    statement = (
        select(Credential.id)
        .join(AgentCredentialLink, AgentCredentialLink.credential_id == Credential.id)
        .join(AgentEnvironment, AgentEnvironment.agent_id == AgentCredentialLink.agent_id)
        .where(
            AgentEnvironment.status == "running",
            Credential.is_placeholder == False,  # noqa: E712
            (
                Credential.type.in_(google_types)
                | (
                    (Credential.type == CredentialType.MCP_PROVIDER)
                    & (Credential.mcp_auth_mode == "oauth_dcr")
                )
            ),
        )
        .distinct()
        .order_by(Credential.id)
        .limit(limit)
    )
    if after is not None:
        statement = statement.where(Credential.id > after)
    return list(session.exec(statement).all())


async def _refresh_one(session: Session, credential: Credential, threshold_seconds: int) -> str:
    """Refresh one credential; returns ``refreshed``, ``failed`` or ``unchanged``."""
    if credential.type == CredentialType.MCP_PROVIDER:
        refreshed = await CredentialsService._refresh_expiring_mcp_provider(
            session=session,
            credential=credential,
            threshold=time.time() + threshold_seconds,
        )
        return "refreshed" if refreshed else "unchanged"

    outcome = await OAuthRefreshService.refresh_if_needed(
        session, credential, min_valid_seconds=threshold_seconds
    )
    if outcome.status == "refreshed":
        return "refreshed"
    # Only a failure of a Google call made now counts; a pre-check "failed"
    # (reauth_required, not configured) is a standing state, not news.
    if outcome.status == "failed" and outcome.attempted:
        return "failed"
    return "unchanged"


def _iter_candidate_ids(session: Session, page_size: int):
    """Yield every candidate id, one keyset page at a time."""
    after: uuid.UUID | None = None
    while True:
        page = _candidate_credential_ids(session, page_size, after)
        yield from page
        if len(page) < page_size:
            return
        after = page[-1]


async def sweep_expiring_oauth_credentials(session: Session, *, limit: int) -> dict:
    """Refresh expiring OAuth credentials of running environments and push them.

    Walks every candidate in keyset pages of ``limit`` ids (ordered by id), so
    a large fleet is fully covered on each run.

    One bad credential never stops the batch. Each agent whose credential was
    refreshed is synced once, after the loop (the sync's own refresh step is
    then a no-op).

    Returns:
        ``{"checked", "refreshed", "failed", "agents_synced"}`` counts.
    """
    threshold_seconds = settings.OAUTH_REFRESH_THRESHOLD_SECONDS
    stats = {"checked": 0, "refreshed": 0, "failed": 0, "agents_synced": 0}
    agents_to_sync: set[uuid.UUID] = set()

    for credential_id in _iter_candidate_ids(session, limit):
        stats["checked"] += 1
        try:
            credential = session.get(Credential, credential_id)
            if credential is None:
                continue
            result = await _refresh_one(session, credential, threshold_seconds)
            if result == "refreshed":
                stats["refreshed"] += 1
                agents_to_sync.update(
                    CredentialsService.get_affected_agents(
                        session=session, credential_id=credential_id
                    )
                )
            elif result == "failed":
                stats["failed"] += 1
        except Exception as e:
            stats["failed"] += 1
            session.rollback()
            logger.error(
                "OAuth refresh sweep failed for credential %s: %s: %s",
                credential_id, type(e).__name__, e,
            )

    for agent_id in agents_to_sync:
        try:
            await CredentialsService.sync_credentials_to_agent_environments(
                session=session, agent_id=agent_id
            )
            stats["agents_synced"] += 1
        except Exception as e:
            session.rollback()
            logger.error(
                "OAuth refresh sweep could not sync agent %s: %s: %s",
                agent_id, type(e).__name__, e,
            )

    if stats["refreshed"] or stats["failed"]:
        logger.info("OAuth refresh sweep: %s", stats)
    else:
        logger.debug("OAuth refresh sweep: %s", stats)
    return stats


def run_oauth_refresh_sweep() -> None:
    """APScheduler entry point — submit one sweep to the main event loop."""
    if _main_loop is None or _main_loop.is_closed():
        logger.error("Main event loop not available — skipping OAuth refresh sweep")
        return
    try:
        future = asyncio.run_coroutine_threadsafe(_sweep(), _main_loop)
        future.result(timeout=SWEEP_WAIT_TIMEOUT_SECONDS)
    except TimeoutError:
        logger.info(
            "OAuth refresh sweep still running on the main loop after %ds and "
            "holding the leader lock; later ticks skip until it finishes",
            SWEEP_WAIT_TIMEOUT_SECONDS,
        )
    except Exception as e:
        logger.error(f"OAuth refresh sweep job failed: {e}", exc_info=True)


async def _sweep() -> None:
    """Run the sweep on the leader worker only; the others skip."""
    with leader_session(OAUTH_REFRESH_SWEEP_LOCK_KEY) as session:
        if session is None:
            logger.debug("OAuth refresh sweep skipped: another worker holds the leader lock")
            return
        await sweep_expiring_oauth_credentials(
            session, limit=settings.OAUTH_REFRESH_SWEEP_BATCH_LIMIT
        )


def start_scheduler() -> None:
    """Start the OAuth refresh sweep scheduler (call on app startup, on the main loop)."""
    global _main_loop

    if not settings.OAUTH_REFRESH_SWEEP_ENABLED:
        logger.info("OAuth refresh sweep disabled (OAUTH_REFRESH_SWEEP_ENABLED=False)")
        return

    _main_loop = asyncio.get_running_loop()
    interval_minutes = settings.OAUTH_REFRESH_SWEEP_INTERVAL_MINUTES
    scheduler.add_job(
        run_oauth_refresh_sweep,
        "interval",
        minutes=interval_minutes,
        id="oauth_refresh_sweep",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(f"OAuth refresh sweep scheduler started (runs every {interval_minutes} minutes)")


def shutdown_scheduler() -> None:
    """Stop the OAuth refresh sweep scheduler (call on app shutdown)."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("OAuth refresh sweep scheduler stopped")
