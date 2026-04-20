"""
Integration tests: CLI Commands Sync and Discovery feature.

Tests:
  1. GET /sessions/{id}/commands returns no dynamic entries when cli_commands_parsed is null
  2. GET /sessions/{id}/commands returns dynamic /run:<name> entries when cache is populated
  3. Dynamic entries have resolved_command populated; static entries have it null
  4. Dynamic entries are is_available=False when environment is not "running"
  5. Dynamic entries are is_available=True when environment is "running"
  6. CLICommandsService.parse_commands_file — canonical scenario via API: fetch + verify endpoint

Notes:
  - These tests use the environment adapter stub (auto-patched by agents/conftest.py).
  - The parse_commands_file unit tests are in tests/unit/test_cli_commands_service.py.
  - This file covers the API-observable behaviors.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.session import create_session_via_api


def _list_session_commands(
    client: TestClient,
    token_headers: dict[str, str],
    session_id: str,
) -> tuple[int, dict]:
    """Call GET /api/v1/sessions/{session_id}/commands. Returns (status_code, json)."""
    r = client.get(
        f"{settings.API_V1_STR}/sessions/{session_id}/commands",
        headers=token_headers,
    )
    return r.status_code, r.json()


def test_commands_no_dynamic_entries_when_cache_empty(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    When cli_commands_parsed is null (no cache), the endpoint returns only static
    commands. No /run:<name> entries appear.
    """
    agent = create_agent_via_api(client, superuser_token_headers)
    drain_tasks()
    agent = get_agent(client, superuser_token_headers, agent["id"])
    session_data = create_session_via_api(client, superuser_token_headers, agent["id"])
    session_id = session_data["id"]

    status, data = _list_session_commands(client, superuser_token_headers, session_id)

    assert status == 200
    commands = data["commands"]
    dynamic_names = [cmd["name"] for cmd in commands if cmd["name"].startswith("/run:")]
    assert dynamic_names == [], f"Expected no dynamic /run: commands, got: {dynamic_names}"


def test_commands_includes_dynamic_entries_when_cache_populated(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    When the environment has cli_commands_parsed populated, dynamic /run:<name>
    entries appear in the commands list.

    Scenario:
      1. Create agent and session
      2. Populate the environment's cli_commands cache via the stub adapter
      3. Fetch commands → verify dynamic entries are present
      4. Verify resolved_command is populated on dynamic entries
      5. Verify static entries have resolved_command=None
    """
    # ── Phase 1: Create agent and session ─────────────────────────────────
    yaml_content = (
        b"commands:\n"
        b"  - name: check\n"
        b"    command: uv run /app/workspace/scripts/check.py\n"
        b"    description: Monthly data quality check\n"
        b"  - name: report\n"
        b"    command: uv run /app/workspace/scripts/report.py\n"
    )
    EnvironmentTestAdapter.workspace_files["docs/CLI_COMMANDS.yaml"] = yaml_content

    try:
        agent = create_agent_via_api(client, superuser_token_headers)
        drain_tasks()
        agent = get_agent(client, superuser_token_headers, agent["id"])
        session_data = create_session_via_api(client, superuser_token_headers, agent["id"])
        session_id = session_data["id"]

        # ── Phase 2: Trigger CLI commands fetch via force-refresh of the env ─
        # The environment is already activated by create_session_via_api (via
        # drain_tasks). We trigger a manual fetch by calling the status endpoint
        # with force_refresh — but that only fetches STATUS.md. Instead, we
        # directly patch the environment's cli_commands_parsed via the API by
        # using a dedicated internal test helper.
        #
        # Since tests can only interact via HTTP, we trigger the fetch via an
        # ENVIRONMENT_ACTIVATED event indirectly: the agent was created and
        # drain_tasks() was called, but if the environment was in "stopped" state
        # during the handler registration it won't have fetched. We rely on
        # the fact that EnvironmentTestAdapter.workspace_files is populated BEFORE
        # drain_tasks(), so the ENVIRONMENT_ACTIVATED handler should have run.
        #
        # Re-drain tasks to let the CLI_COMMANDS.yaml fetch fire via the
        # ENVIRONMENT_ACTIVATED event handler that was registered at app startup.
        drain_tasks()

        # ── Phase 3: Fetch commands and verify dynamic entries ─────────────
        status, data = _list_session_commands(client, superuser_token_headers, session_id)
        assert status == 200

        commands_by_name = {cmd["name"]: cmd for cmd in data["commands"]}

        # Dynamic entries should appear
        assert "/run:check" in commands_by_name, (
            f"Expected /run:check in commands. Got: {list(commands_by_name.keys())}"
        )
        assert "/run:report" in commands_by_name

        # ── Phase 4: resolved_command is set on dynamic entries ────────────
        check_cmd = commands_by_name["/run:check"]
        assert check_cmd["resolved_command"] == "uv run /app/workspace/scripts/check.py"
        assert check_cmd["description"] == "Monthly data quality check"

        report_cmd = commands_by_name["/run:report"]
        assert report_cmd["resolved_command"] == "uv run /app/workspace/scripts/report.py"
        # No description → falls back to truncated command (first 80 chars)
        assert report_cmd["description"] is not None

        # ── Phase 5: Static entries have resolved_command=None ─────────────
        static_cmd = commands_by_name.get("/files")
        if static_cmd:
            assert static_cmd.get("resolved_command") is None

    finally:
        EnvironmentTestAdapter.workspace_files.pop("docs/CLI_COMMANDS.yaml", None)


def test_commands_static_entries_have_null_resolved_command(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Static slash commands (/files, /rebuild-env, etc.) always have
    resolved_command=None in the response.
    """
    agent = create_agent_via_api(client, superuser_token_headers)
    drain_tasks()
    agent = get_agent(client, superuser_token_headers, agent["id"])
    session_data = create_session_via_api(client, superuser_token_headers, agent["id"])
    session_id = session_data["id"]

    status, data = _list_session_commands(client, superuser_token_headers, session_id)

    assert status == 200
    for cmd in data["commands"]:
        if not cmd["name"].startswith("/run:"):
            assert cmd.get("resolved_command") is None, (
                f"Static command {cmd['name']} should have resolved_command=None, "
                f"got: {cmd.get('resolved_command')}"
            )


def test_commands_dynamic_entries_always_available(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Dynamic /run:<name> entries are always is_available=True regardless of the
    environment status. When the user invokes one, the execution path (plan #2)
    activates a stopped environment the same way a regular message does.
    """
    yaml_content = (
        b"commands:\n"
        b"  - name: check\n"
        b"    command: uv run /app/workspace/check.py\n"
    )
    EnvironmentTestAdapter.workspace_files["docs/CLI_COMMANDS.yaml"] = yaml_content

    try:
        agent = create_agent_via_api(client, superuser_token_headers)
        drain_tasks()
        agent = get_agent(client, superuser_token_headers, agent["id"])
        session_data = create_session_via_api(client, superuser_token_headers, agent["id"])
        session_id = session_data["id"]
        drain_tasks()

        from app.services.agents.cli_commands_service import CLICommandsService, ParsedCLICommand

        # Force a cached command via the service so the route sees it even if
        # the fetch path didn't populate during drain_tasks.
        mock_commands = [ParsedCLICommand(
            name="check",
            command="uv run /app/workspace/check.py",
            description="Check script",
        )]

        with patch.object(
            CLICommandsService, "get_cached_commands", return_value=mock_commands
        ):
            status, data = _list_session_commands(client, superuser_token_headers, session_id)

        assert status == 200
        dynamic_cmds = [c for c in data["commands"] if c["name"].startswith("/run:")]
        assert dynamic_cmds, "Expected at least one dynamic /run:* command"
        for cmd in dynamic_cmds:
            assert cmd["is_available"] is True, (
                f"Dynamic command {cmd['name']} should always be available; "
                f"execution-time activation is plan #2's responsibility"
            )

    finally:
        EnvironmentTestAdapter.workspace_files.pop("docs/CLI_COMMANDS.yaml", None)
