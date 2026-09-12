"""The shared engine's pool sizing and the ACP prompt budget derived from it.

Covers the wiring half of F1 (`docs/plans/acp_connector_review_fixes_plan.md`):
the pool is configured explicitly from `settings` rather than inheriting
SQLAlchemy's 5 + 10 default, and `app/acp/agent.py` slices its admission budget
out of that pool instead of carrying a free-floating constant.

Nothing here opens a connection — `engine.pool` reports its configuration
without one, and `Settings(...)` is pure validation. The *behaviour* these
numbers exist to protect (one lease pins one connection; a small pool starves)
is covered in `tests/infra/db_leader_session_test.py`, which drives
`leader_session` for real against a scratch database.
"""

import importlib.util
import sys
from unittest.mock import patch

import pytest
from pydantic import ValidationError
from sqlalchemy.pool import QueuePool

import app.acp.agent as acp_agent
from app.core.config import Settings, settings
from app.core.db import engine

# The pinned numbers below are written for this default. If the default moves,
# they must move with it — that is the point of asserting it separately.
DEFAULT_POOL_SIZE = 20


def test_shared_engine_pool_is_configured_from_settings() -> None:
    """Every pool knob on the shared engine tracks its setting.

    Asserted against `settings.*`, never against literals, so raising
    `DB_POOL_SIZE` in the environment keeps this green while *dropping* the
    explicit `create_engine(...)` arguments (the pre-F1 state) turns it red:
    the SQLAlchemy defaults are 5 / 10 / 30 / -1 / False, and `DB_POOL_SIZE`
    can never be 5 because config floors it at 8.
    """
    pool = engine.pool
    assert isinstance(pool, QueuePool)

    assert pool.size() == settings.DB_POOL_SIZE
    assert pool._max_overflow == settings.DB_MAX_OVERFLOW
    assert pool._timeout == settings.DB_POOL_TIMEOUT
    assert pool._recycle == settings.DB_POOL_RECYCLE
    # Not merely truthy: `pool_pre_ping` is stored verbatim, and it is what
    # keeps a connection the server closed while idle from surfacing as an
    # OperationalError mid-request (F3's trigger).
    assert pool._pre_ping is True

    # The engine is the one the app actually uses, not a test-local rebuild.
    assert sys.modules["app.core.db"].engine is engine


def test_db_pool_size_floor_is_enforced_by_config() -> None:
    """`DB_POOL_SIZE` below 8 is rejected at settings construction, 8 accepted.

    The floor is what makes the derived ACP budget meaningful (a third of a
    smaller pool rounds down to nothing usable), so it is a config invariant
    rather than a comment. 7 and 8 are asserted as a pair: rejecting 7 alone
    would also pass if the floor had drifted upward to 12.
    """
    with pytest.raises(ValidationError) as excinfo:
        Settings(DB_POOL_SIZE=7)
    assert "DB_POOL_SIZE must be at least 8" in str(excinfo.value)

    assert Settings(DB_POOL_SIZE=8).DB_POOL_SIZE == 8


def test_acp_prompt_budget_is_a_slice_of_the_pool() -> None:
    """The live ACP constants, pinned at the default pool size.

    `MAX_ACTIVE_PROMPTS` used to be a bare `8` — larger than the whole 5-slot
    default pool. Both numbers are pinned to literals (not restated as the
    formula, which would make the assertion tautological) plus the ordering
    invariant that has to hold at *any* pool size.
    """
    assert settings.DB_POOL_SIZE == DEFAULT_POOL_SIZE, (
        "default pool size changed — update the pinned budget numbers below"
    )
    assert acp_agent.MAX_ACTIVE_PROMPTS == 6
    assert acp_agent.MAX_ACTIVE_PROMPTS_PER_CONNECTOR == 2

    # The invariant the module-level assert in agent.py states, restated here
    # so it is checked even when Python runs with -O (which drops that assert).
    assert (
        0
        < acp_agent.MAX_ACTIVE_PROMPTS_PER_CONNECTOR
        < acp_agent.MAX_ACTIVE_PROMPTS
        < settings.DB_POOL_SIZE
    )


def _load_isolated_agent_module(name: str = "app.acp._agent_budget_probe"):
    """Execute `app/acp/agent.py` again as a throwaway module object.

    Deliberately NOT `importlib.reload`: reload rebinds `_active_prompts` and
    `_prompt_tickets` in place, while `app.acp.server` keeps the pre-reload
    `CinnaACPAgent` (so `admit_prompt` would write to the old dict) and
    `tests/utils/acp_runtime.py` re-imports the name fresh on every call (so it
    would read the new one). The ACP runtime tests would then observe an empty
    admission table and pass vacuously. `spec_from_file_location` +
    `exec_module` never touches `sys.modules`, so the live module and its
    mutable state are left exactly as they were — asserted by the caller.
    """
    spec = importlib.util.spec_from_file_location(name, acp_agent.__file__)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prompt_budget_at_the_pool_floor_is_two_and_one() -> None:
    """At the `DB_POOL_SIZE = 8` floor the budget is 2 global / 1 per connector.

    A review report claimed the floor yielded "4/1". It does not: `8 // 3` is
    2 and `max(1, 2 // 3)` is 1. This pins the real arithmetic at the only
    other pool size the config actually admits as an edge, and incidentally
    exercises agent.py's module-level ordering assert at that size — it is the
    case most likely to trip it.
    """
    live_module = sys.modules["app.acp.agent"]
    live_admissions = acp_agent._active_prompts

    with patch.object(settings, "DB_POOL_SIZE", 8):
        floor = _load_isolated_agent_module()

    assert floor.MAX_ACTIVE_PROMPTS == 2
    assert floor.MAX_ACTIVE_PROMPTS_PER_CONNECTOR == 1
    assert 0 < floor.MAX_ACTIVE_PROMPTS_PER_CONNECTOR < floor.MAX_ACTIVE_PROMPTS

    # The probe must be inert: the module every other test reaches into is the
    # same object, with the same admission dict, and the probe is not
    # importable by anyone else.
    assert sys.modules["app.acp.agent"] is live_module
    assert acp_agent._active_prompts is live_admissions
    assert floor._active_prompts is not live_admissions
    assert "app.acp._agent_budget_probe" not in sys.modules
    assert acp_agent.MAX_ACTIVE_PROMPTS == 6
