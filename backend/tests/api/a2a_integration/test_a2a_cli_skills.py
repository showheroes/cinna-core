"""
Integration tests: CLI commands appear as AgentSkill entries in the A2A agent card.

Covers:
  1. Happy path — agent with CLI_COMMANDS.yaml populated: extended card contains
     cinna.run.* skills with correct id, name, examples.
  2. No CLI_COMMANDS.yaml — extended card has no cinna.run.* skills (graceful empty).
  3. Public card — never contains CLI skills regardless of environment state.
  4. User-defined skills + CLI skills coexist — both present, user skills first.
"""
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.utils.a2a import (
    create_access_token,
    get_a2a_agent_card,
)
from tests.utils.agent import create_agent_via_api, enable_a2a, get_agent, update_agent
from tests.utils.background_tasks import drain_tasks


_CLI_COMMANDS_YAML = b"""
commands:
  - name: check
    command: uv run /app/workspace/scripts/check.py
    description: Run health check
  - name: build
    command: docker build -t myapp .
    description: Build Docker image
  - name: test
    command: uv run pytest tests/
"""


def _setup_agent_with_cli_commands(
    client: TestClient,
    token_headers: dict[str, str],
    cli_yaml: bytes | None = _CLI_COMMANDS_YAML,
    name: str = "CLI Skills A2A Agent",
) -> tuple[dict, dict]:
    """Create agent, populate CLI commands cache, enable A2A, create access token.

    If cli_yaml is None, no CLI_COMMANDS.yaml is set in the stub workspace.
    Returns (agent_dict, token_data_dict).
    """
    if cli_yaml is not None:
        EnvironmentTestAdapter.workspace_files["docs/CLI_COMMANDS.yaml"] = cli_yaml

    try:
        agent = create_agent_via_api(client, token_headers, name=name)
        drain_tasks()  # fires ENVIRONMENT_ACTIVATED → CLICommandsService.fetch_commands

        agent = get_agent(client, token_headers, agent["id"])
        assert agent["active_environment_id"] is not None

        enable_a2a(client, token_headers, agent["id"])
        token_data = create_access_token(client, token_headers, agent["id"])
    finally:
        # Always clean up workspace_files to avoid leaking state between tests
        EnvironmentTestAdapter.workspace_files.pop("docs/CLI_COMMANDS.yaml", None)

    return agent, token_data


# ---------------------------------------------------------------------------
# Scenario 1: Extended card contains CLI skills when CLI_COMMANDS.yaml is set
# ---------------------------------------------------------------------------

def test_extended_card_contains_cli_skills(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Happy path — agent with CLI_COMMANDS.yaml populated in workspace:
      1. Create agent with CLI_COMMANDS.yaml in workspace stub
      2. Drain tasks so ENVIRONMENT_ACTIVATED fires and CLI commands are cached
      3. Enable A2A and create access token
      4. GET extended card (authenticated)
      5. Assert cinna.run.check, cinna.run.build, cinna.run.test skills are present
      6. Assert skill fields: id, examples contain /run:<name>
    """
    # ── Phase 1–3: Setup ──────────────────────────────────────────────────
    agent, token_data = _setup_agent_with_cli_commands(client, superuser_token_headers)
    agent_id = agent["id"]
    a2a_token = token_data["token"]

    # ── Phase 4: GET extended card ────────────────────────────────────────
    card = get_a2a_agent_card(client, agent_id, a2a_token)

    # ── Phase 5: Assert CLI skills present ────────────────────────────────
    skills = card.get("skills", [])
    skill_ids = [s["id"] for s in skills]

    assert "cinna.run.check" in skill_ids, (
        f"Expected cinna.run.check in card skills, got: {skill_ids}"
    )
    assert "cinna.run.build" in skill_ids, (
        f"Expected cinna.run.build in card skills, got: {skill_ids}"
    )
    assert "cinna.run.test" in skill_ids, (
        f"Expected cinna.run.test in card skills, got: {skill_ids}"
    )

    # ── Phase 6: Assert examples field contains /run:<name> ───────────────
    for skill in skills:
        if skill["id"].startswith("cinna.run."):
            name = skill["id"].replace("cinna.run.", "")
            examples = skill.get("examples", [])
            assert f"/run:{name}" in examples, (
                f"Expected /run:{name} in examples for skill {skill['id']}, got: {examples}"
            )


# ---------------------------------------------------------------------------
# Scenario 2: No CLI_COMMANDS.yaml — extended card has no cinna.run.* skills
# ---------------------------------------------------------------------------

def test_extended_card_no_cli_skills_when_no_yaml(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    No CLI_COMMANDS.yaml set: card is returned without cinna.run.* skills.
    Graceful fallback — no error, no 500.
    """
    agent, token_data = _setup_agent_with_cli_commands(
        client, superuser_token_headers, cli_yaml=None,
        name="No CLI Commands A2A Agent",
    )
    agent_id = agent["id"]
    a2a_token = token_data["token"]

    card = get_a2a_agent_card(client, agent_id, a2a_token)
    skills = card.get("skills", [])
    cli_skill_ids = [s["id"] for s in skills if s["id"].startswith("cinna.run.")]

    assert cli_skill_ids == [], (
        f"Expected no cinna.run.* skills when no CLI_COMMANDS.yaml, got: {cli_skill_ids}"
    )


# ---------------------------------------------------------------------------
# Scenario 3: Public card never contains CLI skills
# ---------------------------------------------------------------------------

def test_public_card_never_contains_cli_skills(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Public (unauthenticated) card must not expose CLI skills even when
    CLI_COMMANDS.yaml is populated.
    """
    agent, _token_data = _setup_agent_with_cli_commands(
        client, superuser_token_headers,
        name="Public Card CLI Test Agent",
    )
    agent_id = agent["id"]

    # Unauthenticated GET of the well-known card endpoint
    resp = client.get(
        f"{settings.API_V1_STR}/a2a/{agent_id}/.well-known/agent-card.json",
    )
    assert resp.status_code == 200, f"Expected 200 for public card, got: {resp.status_code}"
    card = resp.json()

    skills = card.get("skills", [])
    cli_skill_ids = [s.get("id", "") for s in skills if s.get("id", "").startswith("cinna.run.")]

    assert cli_skill_ids == [], (
        f"Public card must not expose cinna.run.* skills, got: {cli_skill_ids}"
    )


# ---------------------------------------------------------------------------
# Scenario 4: User-defined skills + CLI skills coexist
# ---------------------------------------------------------------------------

def test_extended_card_user_and_cli_skills_coexist(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Agent with both user-defined skills (in a2a_config) and CLI_COMMANDS.yaml:
      1. Create agent, set a2a_config with a user skill and A2A enabled
      2. Populate CLI commands
      3. Fetch extended card
      4. User-defined skill is present
      5. CLI skills are present
      6. Total count = 1 user skill + N CLI skills
    """
    # ── Phase 1: Create agent with a2a_config user skill ──────────────────
    EnvironmentTestAdapter.workspace_files["docs/CLI_COMMANDS.yaml"] = b"""
commands:
  - name: report
    command: uv run report.py
    description: Generate report
"""
    try:
        agent = create_agent_via_api(client, superuser_token_headers, name="Combo Skills A2A Agent")
        drain_tasks()
        agent = get_agent(client, superuser_token_headers, agent["id"])
    finally:
        EnvironmentTestAdapter.workspace_files.pop("docs/CLI_COMMANDS.yaml", None)

    agent_id = agent["id"]

    # ── Phase 2: Set a2a_config with a user-defined skill ─────────────────
    update_agent(client, superuser_token_headers, agent_id, a2a_config={
        "enabled": True,
        "skills": [
            {
                "id": "summarize",
                "name": "Summarize text",
                "description": "Summarises a document",
                "tags": [],
                "examples": ["Summarise this"],
            }
        ],
    })

    token_data = create_access_token(client, superuser_token_headers, agent_id)
    a2a_token = token_data["token"]

    # ── Phase 3: Fetch extended card ──────────────────────────────────────
    card = get_a2a_agent_card(client, agent_id, a2a_token)
    skills = card.get("skills", [])
    skill_ids = [s["id"] for s in skills]

    # ── Phase 4–5: Both user and CLI skills present ────────────────────────
    assert "summarize" in skill_ids, f"User-defined skill missing: {skill_ids}"
    assert "cinna.run.report" in skill_ids, f"CLI skill missing: {skill_ids}"

    # ── Phase 6: Count matches ─────────────────────────────────────────────
    # 1 user skill + 1 CLI skill = 2 total
    assert len(skills) == 2, (
        f"Expected 2 total skills (1 user + 1 CLI), got {len(skills)}: {skill_ids}"
    )
