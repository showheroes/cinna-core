"""
AI Credentials test fixtures.

Provides adapter-level environment stubbing so agent creation runs real service
logic without Docker. Follows the same pattern as tests/api/agents/conftest.py.
"""
import asyncio
import pytest
from unittest.mock import patch, AsyncMock

from app.core.config import settings
from app.services.environment_service import EnvironmentService
from app.services.environment_lifecycle import EnvironmentLifecycleManager
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.stubs.socketio_stub import StubSocketIOConnector
from tests.utils.background_tasks import set_collector
from tests.utils.ai_credential import create_random_ai_credential


class _NonClosingSessionProxy:
    """
    Wraps test DB session so `with create_session() as db:` doesn't close it.
    """

    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *args):
        pass

    def __getattr__(self, name):
        return getattr(self._session, name)


class _BackgroundTaskCollector:
    """Collects fire-and-forget asyncio tasks for deferred execution."""

    def __init__(self):
        self.pending: list[tuple] = []

    def __call__(self, coro, task_name="background_task"):
        self.pending.append((coro, task_name))

    def run_all(self, max_rounds: int = 10):
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
        for coro, _name in self.pending:
            coro.close()
        self.pending.clear()


@pytest.fixture(autouse=True)
def patch_create_session(db):
    """All internal service session creation returns the test session."""
    factory = lambda: _NonClosingSessionProxy(db)
    with (
        patch("app.core.db.create_session", factory),
        patch("app.services.environment_service.create_session", factory),
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
def patch_environment_adapter(tmp_path_factory):
    """Patch lifecycle manager to use EnvironmentTestAdapter instead of Docker.

    Uses a single persistent adapter instance so tests can track calls
    (start, rebuild, set_credentials, etc.) across lifecycle operations.
    """
    tmp = tmp_path_factory.mktemp("env")
    templates_dir = tmp / "templates"
    instances_dir = tmp / "instances"
    templates_dir.mkdir()
    instances_dir.mkdir()

    # Create minimal template with docker-compose.template.yml
    template_dir = templates_dir / settings.DEFAULT_AGENT_ENV_NAME
    template_dir.mkdir(parents=True)
    (template_dir / "docker-compose.template.yml").write_text(
        "version: '3'\nservices:\n  agent:\n    image: test\n    ports:\n      - '${AGENT_PORT}:8000'\n"
    )
    # Create app/core directory (required by rebuild_environment validation)
    (template_dir / "app" / "core").mkdir(parents=True)

    # Build lifecycle manager with tmp dirs
    lm = EnvironmentLifecycleManager()
    lm.templates_dir = templates_dir
    lm.instances_dir = instances_dir

    # Use a single persistent adapter so tests can inspect call history
    adapter = EnvironmentTestAdapter()

    def _test_get_adapter(environment):
        return adapter
    lm.get_adapter = _test_get_adapter
    lm._test_adapter = adapter

    # Install as singleton
    EnvironmentService._lifecycle_manager = lm
    yield lm
    EnvironmentService._lifecycle_manager = None


@pytest.fixture(autouse=True)
def background_tasks():
    """Collect background tasks for deferred execution."""
    collector = _BackgroundTaskCollector()
    set_collector(collector)
    with (
        patch(
            "app.services.environment_service.create_task_with_error_logging",
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


@pytest.fixture(autouse=True)
def setup_default_credentials(client, superuser_token_headers):
    """Create a default anthropic AI credential so create_environment validation passes."""
    cred = create_random_ai_credential(
        client, superuser_token_headers,
        credential_type="anthropic",
        api_key="sk-ant-api03-test-default-key",
        name="test-default-credential",
        set_default=True,
    )
    yield cred
