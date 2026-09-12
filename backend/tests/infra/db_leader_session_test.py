"""`leader_session` against a real pool, on a scratch database of its own.

`app/core/db.py::leader_session` short-circuits under `settings.TESTING`, so its
production branch — the `engine.connect()` checkout, the advisory lock, and the
`pg_advisory_unlock` in the `finally` whose docstring records a leak that once
shipped as a live bug — executes nowhere in the rest of the suite. This module
is the one place that runs it.

Why not `tests/api/`: there is no endpoint behind any of this. What is being
asserted is connection-pool accounting and Postgres lock state, neither of which
an HTTP response reveals.

**Isolation.** `leader_session` reads the module-global `app.core.db.engine`, so
these tests patch that global to an engine on a scratch database they create and
drop themselves, and flip `settings.TESTING` to False for the duration. Both are
done by `leader_engine()`, which refuses to run unless the engine really is
pointed at the scratch database — the root `tests/conftest.py` sets
`settings.TESTING = True` precisely to stop test code writing to the live
database, and this module is the one that turns that guard off.

The sizing half of F1 (the pool is configured from settings; the ACP prompt
budget is a slice of it) is covered in
`tests/unit/test_db_pool_and_acp_budget.py`.
"""

import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

import app.core.db as db
from app.core.config import settings
from app.core.db import leader_session

SCRATCH_PREFIX = "app_leader_session_"
FORBIDDEN = {"app", "app_test", "postgres"}


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> None:
    """Override root setup: this module neither migrates nor seeds app_test.

    `leader_session` needs a database and the `pg_advisory_lock` functions, not
    a schema — nothing here reads an application table.
    """


@pytest.fixture
def scratch_engines() -> Iterator[Callable[..., Engine]]:
    """Factory for engines on a fresh database, dropped even on failure.

    Yields a callable so a single test can build several engines with different
    pool arguments against the same database. Every engine handed out is
    disposed in teardown before the drop, so `WITH (FORCE)` has nothing to kill.
    """
    base = make_url(str(settings.TEST_SQLALCHEMY_DATABASE_URI))
    name = f"{SCRATCH_PREFIX}{uuid.uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    url = base.set(database=name).render_as_string(hide_password=False)
    engines: list[Engine] = []
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True

        def make(**pool_kwargs: object) -> Engine:
            engine = create_engine(url, **pool_kwargs)
            engines.append(engine)
            return engine

        yield make
    finally:
        for engine in engines:
            engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


@contextmanager
def leader_engine(engine: Engine) -> Iterator[None]:
    """Point `leader_session` at `engine` with the TESTING short-circuit off.

    The two assertions are the safety interlock, not decoration: without them a
    future edit that forgot to build a scratch engine would run the advisory
    lock and a real connection checkout against the dev database instead.
    """
    database = engine.url.database
    assert database is not None
    assert database.startswith(SCRATCH_PREFIX), f"refusing to run against {database}"
    assert database not in FORBIDDEN

    with patch.object(db, "engine", engine), patch.object(settings, "TESTING", False):
        assert db.engine is engine
        assert db.engine.url.database == database
        assert settings.TESTING is False
        yield


def _lock_holder_pids(engine: Engine, key: int) -> list[int]:
    """Backend pids currently holding advisory lock `key` in this database."""
    sql = text(
        """
        SELECT pid FROM pg_locks
        WHERE locktype = 'advisory'
          AND granted
          AND database = (SELECT oid FROM pg_database WHERE datname = current_database())
          AND ((classid::bigint << 32) | objid::bigint) = :key
        ORDER BY pid
        """
    )
    with engine.connect() as connection:
        return [row[0] for row in connection.execute(sql, {"key": key})]


def _key() -> int:
    """A positive 31-bit lock key, unique per call."""
    return uuid.uuid4().int % 2_000_000_000 + 1


def test_lease_pins_one_connection_and_frees_lock_and_connection(
    scratch_engines: Callable[..., Engine],
) -> None:
    """
    The production branch of `leader_session`, end to end:
      1. Entering a lease checks out exactly one connection
      2. The lock lives on that same physical connection...
      3. ...and survives a `commit()` on the session (the leak that shipped)
      4. A second holder of the same key is told to skip, not made to wait
      5. Leaving the lease returns the connection and releases the lock
      6. The key is genuinely free afterwards — it can be taken again
    """
    engine = scratch_engines(pool_size=5, max_overflow=0, pool_timeout=5)
    pool = engine.pool
    key = _key()

    with leader_engine(engine):
        assert pool.checkedout() == 0
        assert _lock_holder_pids(engine, key) == []

        with leader_session(key) as session:
            # ── Phase 1: exactly one connection, for the life of the block ──
            assert session is not None
            assert pool.checkedout() == 1

            # ── Phase 2: lock and session share one physical connection ─────
            backend_pid = (
                session.connection().execute(text("SELECT pg_backend_pid()")).scalar_one()
            )
            assert _lock_holder_pids(engine, key) == [backend_pid]

            # ── Phase 3: a commit must not strand the lock ──────────────────
            # A Session bound to the *engine* hands its connection back here;
            # binding to an explicit connection is what keeps the unlock on the
            # same backend. Same pid, same single checkout, lock still held.
            session.commit()
            assert pool.checkedout() == 1
            assert (
                session.connection().execute(text("SELECT pg_backend_pid()")).scalar_one()
                == backend_pid
            )
            assert _lock_holder_pids(engine, key) == [backend_pid]

            # ── Phase 4: second holder of the same key skips, does not block ─
            started = time.monotonic()
            with leader_session(key) as second:
                assert second is None
            assert time.monotonic() - started < 2, "non-leader waited on the lock"

        # ── Phase 5: connection returned, lock released ─────────────────────
        assert pool.checkedout() == 0
        assert _lock_holder_pids(engine, key) == []

        # ── Phase 6: the key is reusable — the unlock really ran ────────────
        with leader_session(key) as again:
            assert again is not None
            assert _lock_holder_pids(engine, key) != []
        assert pool.checkedout() == 0
        assert _lock_holder_pids(engine, key) == []


def test_concurrent_leases_exhaust_the_pool_and_the_next_caller_raises(
    scratch_engines: Callable[..., Engine],
) -> None:
    """The starvation F1 exists to prevent, reproduced at miniature scale.

    Each lease pins one connection for the whole life of its block (an ACP
    prompt holds that block for up to `PROMPT_TIMEOUT = 1800`s). With `pool_size`
    leases outstanding and no overflow, the next caller — any caller, a REST
    request just as much as another lease — waits `pool_timeout` and then fails.
    That is why `MAX_ACTIVE_PROMPTS` is a third of `DB_POOL_SIZE` and not the
    bare `8` it used to be on a 5-connection pool.
    """
    size = 2
    timeout = 1
    engine = scratch_engines(pool_size=size, max_overflow=0, pool_timeout=timeout)
    pool = engine.pool

    with leader_engine(engine):
        with ExitStack() as leases:
            for _ in range(size):
                session = leases.enter_context(leader_session(_key()))
                assert session is not None
            assert pool.checkedout() == size

            started = time.monotonic()
            with pytest.raises(PoolTimeoutError) as excinfo:
                with leader_session(_key()):
                    pytest.fail("pool was exhausted; this lease must not open")
            waited = time.monotonic() - started

        assert f"QueuePool limit of size {size} overflow 0 reached" in str(excinfo.value)
        # It waited for a connection rather than failing fast — the shape a
        # starved deployment sees.
        assert waited >= timeout * 0.9

        # The failed checkout leaked nothing: unwinding the held leases returns
        # every connection.
        assert pool.checkedout() == 0
