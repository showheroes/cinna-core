"""
AI Credentials test fixtures.

Provides adapter-level environment stubbing so agent creation runs real service
logic without Docker. Uses a persistent adapter so tests can inspect call history.
"""
import pytest
from tests.utils.fixtures import (
    patch_asyncio_to_thread,
    setup_default_credentials,
    patched_create_sessions,
    patched_background_tasks,
    patched_external_services,
    setup_environment_adapter,
    teardown_environment_adapter,
)


@pytest.fixture(autouse=True)
def patch_create_session(db):
    """Patch create_session at all service import sites."""
    with patched_create_sessions(db):
        yield


@pytest.fixture(autouse=True)
def patch_environment_adapter(tmp_path_factory):
    """Use persistent adapter so tests can inspect call history."""
    lm = setup_environment_adapter(
        tmp_path_factory, persistent_adapter=True, extra_template_dirs=["app/core"],
    )
    yield lm
    teardown_environment_adapter()


@pytest.fixture(autouse=True)
def background_tasks():
    """Collect background tasks for deferred execution."""
    with patched_background_tasks():
        yield


@pytest.fixture(autouse=True)
def patch_external_services():
    """Mock external service calls (OAuth refresh, Socket.IO)."""
    with patched_external_services():
        yield
