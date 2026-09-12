# ACP connectors — review fix plan

Scope: the five findings from the review of `93b2b92a..029fb77b` (ACP connectors for
agents). All findings are about **resource behaviour under load** plus one copy fix.
The feature's auth seam, framing bounds and durable finalizer were reviewed and are
correct — do not redesign them.

Baseline: tree clean at `029fb77b`. **Do not commit and do not create branches.**
Leave every change in the working tree for the user to review.

Baseline verification (all green before these changes, must stay green after):

- `docker compose exec backend python -m pytest tests/api/acp_integration/ tests/unit/test_acp_stdio_bridge.py tests/migrations/acp_connectors_test.py -q` → 33 passed
- `docker compose exec backend python -m pytest tests/architecture/ -q` → 88 passed
- `python3 .cinna-core-kit/scripts/docs_index.py check` → all checks pass
- `cd frontend && npx tsc --noEmit` clean for ACP components; `npm run test:acp:ui` → 4/4

---

## F1 — Prompts pin a pooled DB connection for up to 30 minutes, 8 at a time, from a 15-connection pool

**Where:** `backend/app/acp/agent.py:61-72` (`session_lease`), `backend/app/acp/agent.py:52`
(`MAX_ACTIVE_PROMPTS = 8`), `backend/app/core/db.py:11` (`engine`).

`session_lease` wraps the whole prompt in `leader_session`, which by design pins a
*physical* connection for the life of its `with` block. That block is
`await self._run_prompt(...)`, bounded only by `PROMPT_TIMEOUT = 1800`.

The engine is `create_engine(str(settings.SQLALCHEMY_DATABASE_URI))` with no pool
arguments → `pool_size=5, max_overflow=10, pool_timeout=30`. Compose runs **one**
worker (`docker-compose.yml:9`), so those 15 connections serve the whole deployment.
`MAX_ACTIVE_PROMPTS = 8` therefore permits 8 long-lived checkouts — more than
`pool_size` itself — leaving 7 for all REST traffic, Socket.IO, the schedulers and
ACP's own `create_session()` calls.

Failure shape: 8 concurrent ACP prompts on slow agents → the rest of the app raises
`QueuePool limit of size 5 overflow 10 reached, connection timed out`.

**Fix:**
1. Configure the shared engine pool explicitly in `app/core/db.py`, with the sizes
   driven by `app/core/config.py` settings (new settings, sensible defaults, documented
   in `.env.example` if other DB settings are there). Include `pool_pre_ping=True` —
   it also removes the stale-connection trigger behind F3.
   Keep total possible connections comfortably under Postgres `max_connections` (100).
2. Tie the ACP prompt budget to the pool instead of leaving it a free-floating
   constant: `MAX_ACTIVE_PROMPTS` must be meaningfully **below** `pool_size`, with a
   comment stating the relationship and why (each admitted prompt pins one connection
   for up to `PROMPT_TIMEOUT`). If the relationship can be asserted cheaply at import
   or validated in config, do that rather than relying on the comment.

**Acceptance:** a reader of `agent.py` can see why the number is what it is; the pool
has headroom for the ACP budget plus normal traffic; no scheduler or existing
`leader_session` caller regresses (`tests/architecture/` covers some of this).

---

## F2 — Every streamed chunk costs two synchronous queries on the single event loop

**Where:** `backend/app/acp/agent.py:307-333` (`update()`), called from
`ACPStreamEventHandler.on_event` and from `_replay_session`.

`update()` re-authorizes before each notification (`self.session(db, session_id)` →
`authenticate()`'s four-table join, plus `db.get(Session, ...)`). It is called per
assistant/thought/tool event, and **again per 8192-character sub-chunk** of the split
at `agent.py:308-321`. These are blocking calls inside `async def` on the worker's only
event loop, each also taking a pool connection.

Worst case is `_replay_session`: up to `MAX_REPLAY_MESSAGES = 2000` messages, each
possibly split, so one `session/load` can issue ~4000+ blocking queries while holding
the F1 lease connection — stalling the loop for every other user of the process.

**Fix:** memoize the authorization check on `CinnaACPAgent` with a short TTL (~1s),
and use the cached path **only** in `update()`. Per-request checks stay uncached:
`_dispatch` entry, `new_session`, `load_session`, `prompt`, `session/cancel`, and
`watch_prompt` must keep calling the real thing — they are once-per-operation and
cheap. The hard revocation guarantee remains `watch_prompt` (every
`AUTH_CHECK_INTERVAL = 5s`), which already interrupts the turn; the per-chunk check
only narrows the disclosure window, so a 1s TTL preserves the property that matters.

**Watch out:** `tests/api/acp_integration/test_acp_runtime.py::test_token_scope_and_live_revocation`
and `::test_silent_running_prompt_is_interrupted_after_revocation` assert live
revocation behaviour. Read them before changing anything. If a test asserts that the
*very next* chunk after revocation is blocked, decide deliberately whether to (a) keep
that guarantee by invalidating the memo on a cheap signal, or (b) adjust the test to
assert the documented guarantee (the turn is interrupted) rather than chunk-level
immediacy. Do not weaken a test just to make the change pass — say which you chose and
why in the summary.

---

## F3 — The watchdog fix in `029fb77b` lets a transient DB blip kill a live prompt

**Where:** `backend/app/acp/agent.py:483-485`.

```python
except Exception:
    logger.exception("ACP authorization watchdog failed for %s", session_id)
    error = RequestError.internal_error()
```

Any exception from `create_session()` or the auth query stops the turn. Without
`pool_pre_ping` one stale pooled connection surfaces as `OperationalError`, and a pool
checkout timeout from F1 surfaces the same way. A 25-minute prompt then dies with a
generic internal error over something unrelated to authorization.

**Fix:** count *consecutive* unexpected failures and stop only after N (2–3); log each
one; reset the counter on a successful check. `RequestError` (a real authorization
failure) must still stop the prompt on the first occurrence — that is the security
property the commit was protecting and it must not regress. Combined with `pool_pre_ping`
from F1 the trigger becomes rare.

**Acceptance:** a test covers (a) real revocation still stops the turn immediately,
(b) a single transient exception does not.

---

## F4 — `MAX_ACTIVE_PROMPTS` is one unshared global; one tenant can lock out all others

**Where:** `backend/app/acp/agent.py:57` (`_active_prompts`), checked at
`agent.py:255` (`load_session`) and `agent.py:348` (`prompt`).

`_active_prompts` is a module-level set covering every connector, owner and agent in
the process. `max_connections` caps *connections* per connector but nothing caps prompt
admissions, so one owner with two connectors at the default limit of 10 can hold every
slot and every other tenant gets `-32004 Server prompt capacity reached` until they
finish.

**Fix:** keep the global cap and add a per-connector sub-quota beneath it (a new
constant, e.g. `MAX_ACTIVE_PROMPTS_PER_CONNECTOR`, strictly less than the global). The
admission structure needs to track both; whatever replaces the bare set must keep the
existing invariants intact — admission and reservation still happen with no `await`
between the check and the reservation, and the `finally` release must not drop another
holder's entry. `tests/utils/acp_runtime.py::acp_runtime_counts` reads
`len(_active_prompts)` for the `sessions` key — update it and its callers together.

**Acceptance:** a test shows connector A saturating its own sub-quota while connector B
can still start a prompt.

---

## F5 — Revocation copy understates what is lost

`session()` binds each session to the creating `token_id` (`agent.py:94-97`), so a
replacement token cannot load the old token's conversations. `docs/application/acp_integration/acp_integration.md`
states this correctly. The two places an owner actually reads do not:

- `backend/app/api/routes/acp_connectors.py:181` — docstring
  `"Permanently revoke a token. Create a replacement to restore access."`
- `frontend/src/components/Agents/Acp/AcpTokensDialog.tsx:341-344` — the confirm
  dialog mentions only that the app loses access.

**Fix:** add one clause in both places — conversations started with this token cannot
be reopened. Keep the dialog copy short and in the existing voice; follow
`docs/development/frontend/ui_ux_guidelines.md`. This is a copy change only: no layout,
component or flow changes in `AcpTokensDialog.tsx`.

---

## Docs

After the code changes, run `python3 .cinna-core-kit/scripts/docs_index.py impact` and
update what it names. At minimum:

- `docs/application/acp_integration/acp_integration_tech.md` — the limits table
  (prompt budget, new per-connector sub-quota, pool relationship), the authorization
  section (per-chunk memo vs. the 5s watchdog guarantee, watchdog failure tolerance),
  and the configuration section if new settings were added. Add a changelog line.
- `docs/application/acp_integration/acp_integration.md` — only if user-visible
  behaviour changed (capacity errors, revocation copy).
- Mirror into `backend/app/workspace/knowledge/platform/...` the same way the feature
  commits did — both trees carry these docs.

## Definition of done

- All five findings addressed, or explicitly declined with a reason in the summary.
- Backend: `tests/api/acp_integration/`, `tests/unit/test_acp_stdio_bridge.py`,
  `tests/migrations/acp_connectors_test.py`, `tests/architecture/` all pass.
- Frontend: `npx tsc --noEmit` clean for ACP components; `npm run test:acp:ui` passes.
- `python3 .cinna-core-kit/scripts/docs_index.py check` passes.
- New tests cover F3 (transient vs. real auth failure) and F4 (per-connector quota).
- **Nothing committed. No branches. No stashes. No `git restore`/`checkout`/`reset`.**
  `git log -1` must still read `029fb77b` when you finish, with all work unstaged in
  the working tree.
