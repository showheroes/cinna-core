"""
Agent-specific test fixtures.

Provides:
- Session proxy so service code uses the test DB session
- Environment stub so agent creation skips Docker
- Background task collector so fire-and-forget tasks can be drained by test utils
- External service mocks to prevent real calls
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from tests.stubs.environment_stub import stub_create_environment
from tests.stubs.socketio_stub import StubSocketIOConnector
from tests.utils.background_tasks import set_collector


class _NonClosingSessionProxy:
    """
    Wraps test DB session so `with create_session() as db:` doesn't close it.

    Service code does:
        with create_session() as fresh_db:
            ...
    The context manager __exit__ would normally close the session.
    We suppress that so everything stays on the test transaction.
    """

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *args):
        pass  # Don't close — the test fixture handles rollback

    def __getattr__(self, name):
        return getattr(self._session, name)


class _BackgroundTaskCollector:
    """Collects fire-and-forget asyncio tasks for deferred execution.

    Replaces create_task_with_error_logging so that background coroutines
    (e.g. process_pending_messages) are captured instead of scheduled on the
    event loop.  Test utilities call run_all() to drain them synchronously
    from the test thread (outside the ASGI event loop).
    """

    def __init__(self):
        self.pending: list[tuple] = []

    def __call__(self, coro, task_name="background_task"):
        self.pending.append((coro, task_name))

    def run_all(self, max_rounds: int = 10):
        """Run all collected tasks synchronously, draining cascading tasks."""
        for _ in range(max_rounds):
            if not self.pending:
                return
            batch = list(self.pending)
            self.pending.clear()
            for coro, _name in batch:
                asyncio.run(coro)
        if self.pending:
            names = [name for _, name in self.pending]
            raise RuntimeError(
                f"run_all: still pending after {max_rounds} rounds: {names}"
            )

    def _cleanup(self):
        """Close any unrun coroutines to prevent RuntimeWarning."""
        for coro, _name in self.pending:
            coro.close()
        self.pending.clear()


@pytest.fixture(autouse=True)
def patch_create_session(db):
    """All internal service session creation returns the test session.

    Must patch at every import site because `from app.core.db import create_session`
    binds a local reference that isn't updated by patching the source module alone.
    """
    factory = lambda: _NonClosingSessionProxy(db)
    with (
        patch("app.core.db.create_session", factory),
        patch("app.services.email.processing_service.create_session", factory),
        patch("app.services.session_service.create_session", factory),
    ):
        yield


@pytest.fixture(autouse=True)
def patch_asyncio_to_thread():
    """Run asyncio.to_thread synchronously to avoid cross-thread session issues."""
    async def _run_sync(func, /, *args, **kwargs):
        return func(*args, **kwargs)

    with patch("asyncio.to_thread", _run_sync):
        yield


@pytest.fixture(autouse=True)
def patch_environment_creation():
    """Agent creation via API skips Docker, creates running environment directly."""
    with patch(
        "app.services.agent_service.EnvironmentService.create_environment",
        stub_create_environment,
    ):
        yield


@pytest.fixture(autouse=True)
def background_tasks():
    """Collect background tasks for deferred execution.

    Replaces create_task_with_error_logging at every import site so that
    fire-and-forget coroutines are captured instead of scheduled.
    Test utilities (e.g. process_emails_with_stub) drain them automatically
    via drain_tasks().
    """
    collector = _BackgroundTaskCollector()
    set_collector(collector)
    with (
        patch(
            "app.services.session_service.create_task_with_error_logging",
            collector,
        ),
        patch(
            "app.services.event_service.create_task_with_error_logging",
            collector,
        ),
    ):
        yield
        collector._cleanup()
    set_collector(None)


@pytest.fixture(autouse=True)
def patch_external_services():
    """Mock external service calls (OAuth refresh, Socket.IO)."""
    with (
        patch(
            "app.services.credentials_service.CredentialsService.refresh_expiring_credentials_for_agent",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "app.services.event_service.socketio_connector",
            StubSocketIOConnector(),
        ),
    ):
        yield
