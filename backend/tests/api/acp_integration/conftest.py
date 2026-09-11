"""ACP API fixtures share the agent environment and background-task stubs."""

from unittest.mock import patch

import pytest

from tests.utils.fixtures import (
    BACKGROUND_TASK_TARGETS_FULL,
    CREATE_SESSION_TARGETS_AGENT,
    patched_background_tasks,
    patched_create_sessions,
    patched_external_services,
    patched_storage_dirs,
    setup_environment_adapter,
    teardown_environment_adapter,
)
from tests.utils.fixtures import patch_asyncio_to_thread as patch_asyncio_to_thread
from tests.utils.fixtures import setup_default_credentials as setup_default_credentials


@pytest.fixture(autouse=True)
def patch_acp_base_url():
    with patch(
        "app.core.config.settings.ACP_SERVER_BASE_URL", "https://api.example.com/acp"
    ):
        yield


@pytest.fixture(autouse=True)
def patch_create_session(db):
    with patched_create_sessions(db, CREATE_SESSION_TARGETS_AGENT):
        yield


@pytest.fixture(autouse=True)
def patch_environment_adapter(tmp_path_factory):
    adapter = setup_environment_adapter(tmp_path_factory)
    yield adapter
    teardown_environment_adapter()


@pytest.fixture(autouse=True)
def background_tasks():
    with patched_background_tasks(BACKGROUND_TASK_TARGETS_FULL):
        yield


@pytest.fixture(autouse=True)
def patch_external_services():
    with patched_external_services(mock_ai_functions=True, mock_a2a_skills=True):
        yield


@pytest.fixture(autouse=True)
def patch_storage_dirs(tmp_path_factory):
    with patched_storage_dirs(tmp_path_factory):
        yield
