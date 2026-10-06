"""Run the OAuth refresh sweep directly from a test.

The sweep core ``sweep_expiring_oauth_credentials`` is an ``async`` function over
a ``Session``; the scheduler job (leader election, ``asyncio.run``) is never
started under ``settings.TESTING``. This helper drives the core on the test
``db`` session — a documented app-internals import in ``tests/utils`` (cf.
``tests/utils/bundle.py``), not allowed in ``tests/api`` files.
"""
import asyncio

from sqlmodel import Session

from app.services.credentials.oauth_refresh_scheduler import (
    sweep_expiring_oauth_credentials,
)


def run_oauth_refresh_sweep(db: Session, *, limit: int = 200) -> dict:
    """Await one sweep pass and return its stats dict
    (``checked`` / ``refreshed`` / ``failed`` / ``agents_synced``)."""
    return asyncio.run(sweep_expiring_oauth_credentials(db, limit=limit))
