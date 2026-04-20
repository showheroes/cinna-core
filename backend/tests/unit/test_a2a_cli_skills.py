"""
Unit tests for A2AService CLI skill helpers — pure Python, no HTTP, no database.

Covers:
  1. _build_cli_command_skills: no environment → empty list
  2. _build_cli_command_skills: empty cli_commands_parsed → empty list
  3. _build_cli_command_skills: three commands with descriptions → three skills
     with correct id, name, description, tags, examples
  4. _build_cli_command_skills: command without description → name falls back to
     "Run: <name>"
  5. _build_cli_command_skills: malformed command dict (missing name) → warning
     logged, entry skipped gracefully
  6. _build_single_cli_skill: full command dict → correct AgentSkill fields
  7. _build_single_cli_skill: description-less command → correct fallback name
  8. _build_single_cli_skill: description with newline → only first line used as name
  9. build_agent_card: user-defined skills come first, CLI skills appended after,
     no id collision
 10. build_agent_card: no environment → card has only user-defined skills
 11. build_agent_card: environment with empty cli_commands_parsed → same as above
 12. build_public_agent_card: always returns skills=[] regardless of environment
"""
from unittest.mock import MagicMock, patch
import logging

import pytest

from app.services.a2a.a2a_service import A2AService


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_environment(cli_commands_parsed):
    """Build a minimal mock AgentEnvironment with the given cli_commands_parsed."""
    env = MagicMock()
    env.cli_commands_parsed = cli_commands_parsed
    env.agent_sdk_conversation = "claude-code"
    env.agent_sdk_building = None
    return env


def _make_agent(a2a_config=None, description="Test agent"):
    """Build a minimal mock Agent."""
    agent = MagicMock()
    agent.name = "Test Agent"
    agent.description = description
    agent.a2a_config = a2a_config or {}
    agent.id = "00000000-0000-0000-0000-000000000001"
    return agent


# ---------------------------------------------------------------------------
# 1–5: _build_cli_command_skills
# ---------------------------------------------------------------------------

class TestBuildCliCommandSkills:

    def test_no_environment_returns_empty(self):
        result = A2AService._build_cli_command_skills(None)
        assert result == []

    def test_empty_cli_commands_parsed_returns_empty(self):
        env = _make_environment([])
        result = A2AService._build_cli_command_skills(env)
        assert result == []

    def test_none_cli_commands_parsed_returns_empty(self):
        env = _make_environment(None)
        result = A2AService._build_cli_command_skills(env)
        assert result == []

    def test_three_commands_with_descriptions(self):
        env = _make_environment([
            {"name": "check", "command": "uv run /app/workspace/scripts/check.py", "description": "Monthly data check"},
            {"name": "build", "command": "docker build -t myapp .", "description": "Build Docker image"},
            {"name": "test", "command": "uv run pytest tests/", "description": "Run test suite"},
        ])
        result = A2AService._build_cli_command_skills(env)
        assert len(result) == 3

        ids = [s.id for s in result]
        assert "cinna.run.check" in ids
        assert "cinna.run.build" in ids
        assert "cinna.run.test" in ids

        check_skill = next(s for s in result if s.id == "cinna.run.check")
        assert check_skill.name == "Monthly data check"
        assert "/run:check" in check_skill.description
        assert "uv run /app/workspace/scripts/check.py" in check_skill.description
        assert check_skill.tags == ["cinna-run", "command"]
        assert check_skill.examples == ["/run:check"]

    def test_command_without_description_fallback_name(self):
        env = _make_environment([
            {"name": "deploy", "command": "./scripts/deploy.sh"},
        ])
        result = A2AService._build_cli_command_skills(env)
        assert len(result) == 1
        skill = result[0]
        assert skill.id == "cinna.run.deploy"
        assert skill.name == "Run: deploy"
        assert "/run:deploy" in skill.description

    def test_malformed_command_dict_skipped_with_warning(self):
        """A dict that causes _build_single_cli_skill to raise must be skipped."""
        from unittest.mock import patch

        env = _make_environment([
            {"name": "good", "command": "echo hi", "description": "Good command"},
            # Deliberately pass a non-dict value to trigger AttributeError in .get()
            "not-a-dict",
        ])

        with patch("app.services.a2a.a2a_service.logger") as mock_logger:
            result = A2AService._build_cli_command_skills(env)

        # The good command still produces a skill
        assert len(result) == 1
        assert result[0].id == "cinna.run.good"
        # A warning was logged for the malformed entry
        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "Failed to build CLI skill" in str(call)
        ]
        assert warning_calls, f"Expected warning log for malformed entry, got: {mock_logger.warning.call_args_list}"


# ---------------------------------------------------------------------------
# 6–8: _build_single_cli_skill
# ---------------------------------------------------------------------------

class TestBuildSingleCliSkill:

    def test_full_command_dict(self):
        cmd = {
            "name": "check",
            "command": "uv run /app/workspace/scripts/check.py --month",
            "description": "Monthly data check",
        }
        skill = A2AService._build_single_cli_skill(cmd)

        assert skill.id == "cinna.run.check"
        assert skill.name == "Monthly data check"
        assert "Monthly data check" in skill.description
        assert "Invoke by sending message: `/run:check`" in skill.description
        assert "uv run /app/workspace/scripts/check.py --month" in skill.description
        assert skill.tags == ["cinna-run", "command"]
        assert skill.examples == ["/run:check"]

    def test_no_description_fallback_name(self):
        cmd = {
            "name": "report",
            "command": "./scripts/report.sh",
        }
        skill = A2AService._build_single_cli_skill(cmd)

        assert skill.id == "cinna.run.report"
        assert skill.name == "Run: report"
        assert "Invoke by sending message: `/run:report`" in skill.description
        assert "./scripts/report.sh" in skill.description

    def test_multiline_description_first_line_only_as_name(self):
        cmd = {
            "name": "analyse",
            "command": "uv run analyse.py",
            "description": "Analyse data\nRuns the monthly analysis script.\nSee docs for details.",
        }
        skill = A2AService._build_single_cli_skill(cmd)

        # Only first line used as name
        assert skill.name == "Analyse data"
        # Full description still in skill description field
        assert "Analyse data" in skill.description
        assert "Runs the monthly analysis script." in skill.description

    def test_no_command_string_omits_resolved_block(self):
        cmd = {
            "name": "ping",
            "command": "",
            "description": "Ping the server",
        }
        skill = A2AService._build_single_cli_skill(cmd)
        # No "Resolved command:" block when command is empty string
        assert "Resolved command:" not in skill.description

    def test_id_namespaced(self):
        cmd = {"name": "foo", "command": "echo foo"}
        skill = A2AService._build_single_cli_skill(cmd)
        assert skill.id.startswith("cinna.run.")


# ---------------------------------------------------------------------------
# 9–11: build_agent_card integration
# ---------------------------------------------------------------------------

class TestBuildAgentCardWithCliSkills:

    def test_user_defined_skills_first_cli_skills_appended(self):
        agent = _make_agent(a2a_config={
            "enabled": True,
            "skills": [
                {
                    "id": "summarize",
                    "name": "Summarize text",
                    "description": "Summarises a document",
                    "tags": [],
                    "examples": ["Summarise this."],
                }
            ],
        })
        env = _make_environment([
            {"name": "check", "command": "echo check", "description": "Health check"},
            {"name": "build", "command": "echo build", "description": "Build project"},
        ])

        card = A2AService.build_agent_card(agent, env, "https://example.com")
        skill_ids = [s.id for s in card.skills]

        # User-defined skill comes first
        assert skill_ids[0] == "summarize"
        # CLI skills appended after
        assert "cinna.run.check" in skill_ids
        assert "cinna.run.build" in skill_ids
        # Total: 1 user + 2 CLI
        assert len(card.skills) == 3

    def test_no_id_collision(self):
        agent = _make_agent(a2a_config={
            "enabled": True,
            "skills": [
                {"id": "cinna.run.other", "name": "Other", "description": "", "tags": [], "examples": []},
            ],
        })
        env = _make_environment([
            {"name": "check", "command": "echo check", "description": "Check"},
        ])
        card = A2AService.build_agent_card(agent, env, "https://example.com")
        ids = [s.id for s in card.skills]
        # Both are present — different ids, no collision
        assert "cinna.run.other" in ids
        assert "cinna.run.check" in ids

    def test_no_environment_only_user_skills(self):
        agent = _make_agent(a2a_config={
            "enabled": True,
            "skills": [
                {"id": "ask", "name": "Ask", "description": "", "tags": [], "examples": []},
            ],
        })
        card = A2AService.build_agent_card(agent, None, "https://example.com")
        assert len(card.skills) == 1
        assert card.skills[0].id == "ask"

    def test_empty_cli_commands_parsed_no_extra_skills(self):
        agent = _make_agent(a2a_config={"enabled": True, "skills": []})
        env = _make_environment([])
        card = A2AService.build_agent_card(agent, env, "https://example.com")
        assert card.skills == []


# ---------------------------------------------------------------------------
# 12: build_public_agent_card always returns skills=[]
# ---------------------------------------------------------------------------

class TestBuildPublicAgentCard:

    def test_public_card_always_empty_skills(self):
        agent = _make_agent(a2a_config={
            "enabled": True,
            "skills": [{"id": "s1", "name": "Skill 1", "description": "", "tags": [], "examples": []}],
        })
        card = A2AService.build_public_agent_card(agent, "https://example.com")
        assert card.skills == []
