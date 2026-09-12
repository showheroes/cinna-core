# Infrastructure tests

Tests for the process-wide database plumbing in `app/core/db.py` — the shared
engine and `leader_session` — driven against a **scratch database of their own**,
created and dropped by the module that uses it.

## Why this group is not `tests/api`

`tests/README.md` requires integration tests to go through HTTP, and that rule is
right for everything with an API behind it. The connection pool has none. What
these tests assert is pool accounting (`pool.checkedout()`) and Postgres lock
state (`pg_locks`), neither of which any status code or response body reveals.

They also have to run code the rest of the suite is deliberately shielded from:
`leader_session` short-circuits under `settings.TESTING`, so its production
branch — the physical connection checkout, the advisory lock, and the
`pg_advisory_unlock` in the `finally` — executes in no other test.

## Rules for this directory

- **Never touch `app`, `app_test` or `postgres`.** Create a scratch database,
  name it after what is under test, drop it in the fixture teardown with
  `WITH (FORCE)` after disposing every engine you handed out.
- **Patch `app.core.db.engine`, and assert the patch took.** `leader_session`
  resolves that module global at call time. A test that forgets to patch it
  silently runs the advisory lock against the dev database. Use a helper that
  refuses to proceed unless the engine's database name matches the scratch
  prefix — see `leader_engine()` in `db_leader_session_test.py`.
- **`settings.TESTING` goes back to True.** Flip it with `patch.object` and
  nothing else, so it is restored even when the test fails.
- **Override `setup_db` to a no-op.** These tests need a database and the
  `pg_advisory_*` functions, not a schema.
- **Assert on observed state, not on "it did not raise".** A lease that never
  took the lock also does not raise; `pg_locks` is what tells the difference.

## Running

```bash
docker compose exec backend python -m pytest tests/infra -v
```
