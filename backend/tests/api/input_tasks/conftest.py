"""
Input tasks test fixtures.

Provides the environment adapter stub, session patching, and external service
mocks needed for tests that create agents (via create_agent_via_api).

Task-only tests that do not create agents run fine without these patches,
but having them active for all tests in this directory keeps the setup uniform
and prevents accidental Docker dependency.
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
    CREATE_SESSION_TARGETS_AGENT,
    BACKGROUND_TASK_TARGETS_FULL,
)

# Re-export importable autouse fixtures
patch_asyncio_to_thread = patch_asyncio_to_thread
setup_default_credentials = setup_default_credentials


@pytest.fixture(autouse=True)
def patch_create_session(db):
    """Patch create_session at all service import sites."""
    with patched_create_sessions(db, CREATE_SESSION_TARGETS_AGENT):
        yield


@pytest.fixture(autouse=True)
def patch_environment_adapter(tmp_path_factory):
    """Patch lifecycle manager to use EnvironmentTestAdapter instead of Docker."""
    lm = setup_environment_adapter(tmp_path_factory)
    yield lm
    teardown_environment_adapter()


@pytest.fixture(autouse=True)
def background_tasks():
    """Collect background tasks for deferred execution."""
    with patched_background_tasks(BACKGROUND_TASK_TARGETS_FULL):
        yield


@pytest.fixture(autouse=True)
def patch_external_services():
    """Mock external service calls (OAuth refresh, Socket.IO, LLM providers)."""
    with patched_external_services(mock_ai_functions=True, mock_a2a_skills=True):
        yield
