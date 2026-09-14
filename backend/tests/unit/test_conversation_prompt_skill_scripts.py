"""Unit tests: the conversation prompt lets a loaded skill run its own scripts.

A skill's credential is only checked when its script runs, so an agent that
loads the skill and improvises the answer instead leaves a broken credential
invisible. Two pieces of platform-built prompt text decide whether a small
model runs the script:

* the untouched ``scripts/README.md`` template ("No scripts created yet") must
  not appear under "Available Scripts" in conversation mode — models quoted it
  as the reason not to run a skill's script;
* a ``## Skill Scripts`` block names the skills that ship scripts (the agent's
  own and those of plugins active in conversation mode), says running them is
  part of using the skill, and says the script's own error message is relayed.

Engine enablement of skills is covered in
``tests/unit/test_skills_engine_enablement.py``.

Run:
    docker compose exec backend python -m pytest \
        tests/unit/test_conversation_prompt_skill_scripts.py -v
"""

from __future__ import annotations

from pathlib import Path

from core.server.prompt_generator import PromptGenerator

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_README_TEMPLATE = (
    BACKEND_ROOT
    / "app"
    / "env-templates"
    / "python-env-advanced"
    / "app"
    / "workspace"
    / "scripts"
    / "README.md"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "skills").mkdir()
    (workspace / "docs").mkdir()
    (workspace / "credentials").mkdir()
    (workspace / "scripts" / "README.md").write_text(
        SCRIPTS_README_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    (workspace / "scripts" / ".gitkeep").write_text("", encoding="utf-8")
    (workspace / "docs" / "WORKFLOW_PROMPT.md").write_text(
        "You tell jokes. Do not perform any task that is not about jokes.\n",
        encoding="utf-8",
    )
    (workspace / "credentials" / "README.md").write_text(
        "# Credentials\n\nNone yet.\n", encoding="utf-8"
    )
    return workspace


def _write_skill(
    skills_root: Path,
    name: str,
    *,
    scripts: tuple[str, ...] = (),
    skill_name: str | None = None,
    extra_frontmatter: str = "",
) -> Path:
    skill_dir = skills_root / name
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {skill_name or name}\ndescription: Tell a joke.\n"
        f"{extra_frontmatter}---\n\nBody.\n",
        encoding="utf-8",
    )
    for relative in scripts:
        path = skill_dir / "scripts" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("print('joke')\n", encoding="utf-8")
    return skill_dir


def _generator(workspace: Path, plugins: list[dict] | None = None) -> PromptGenerator:
    if plugins is None:
        return PromptGenerator(str(workspace))
    return PromptGenerator(
        str(workspace), active_plugins_for_mode=lambda mode: plugins if mode == "conversation" else []
    )


def _conversation_prompt(workspace: Path, plugins: list[dict] | None = None) -> str:
    return _generator(workspace, plugins).generate_conversation_mode_prompt()


# ===========================================================================
# 1. The scripts catalog is only shown when scripts exist
# ===========================================================================


class TestScriptsCatalogInConversationMode:
    def test_the_untouched_template_is_left_out(self, tmp_path: Path):
        workspace = _workspace(tmp_path)

        prompt = _conversation_prompt(workspace)

        assert "No scripts created yet" in SCRIPTS_README_TEMPLATE.read_text(encoding="utf-8")
        assert "## Available Scripts" not in prompt
        assert "No scripts created yet" not in prompt

    def test_caches_and_hidden_files_are_not_scripts(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        (workspace / "scripts" / "__pycache__").mkdir()
        (workspace / "scripts" / "__pycache__" / "old.cpython-312.pyc").write_bytes(b"\0")
        (workspace / "scripts" / ".venv" / "lib").mkdir(parents=True)
        (workspace / "scripts" / ".venv" / "lib" / "site.py").write_text("", encoding="utf-8")
        (workspace / "scripts" / ".DS_Store").write_bytes(b"\0")

        assert "## Available Scripts" not in _conversation_prompt(workspace)

    def test_a_missing_scripts_folder_is_not_an_error(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        for child in (workspace / "scripts").iterdir():
            child.unlink()
        (workspace / "scripts").rmdir()

        assert "## Available Scripts" not in _conversation_prompt(workspace)

    def test_a_workspace_with_a_script_keeps_its_catalog(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        (workspace / "scripts" / "reports").mkdir()
        (workspace / "scripts" / "reports" / "weekly.py").write_text("", encoding="utf-8")
        (workspace / "scripts" / "README.md").write_text(
            "# Scripts Catalog\n\n## reports/weekly.py\n**Purpose**: Weekly report.\n",
            encoding="utf-8",
        )

        prompt = _conversation_prompt(workspace)

        assert "## Available Scripts" in prompt
        assert "Weekly report." in prompt

    def test_building_mode_still_carries_the_template(self, tmp_path: Path):
        # The building agent maintains the catalog, so it must keep seeing it.
        workspace = _workspace(tmp_path)
        generator = PromptGenerator(str(workspace))
        generator.building_agent_prompt = "BUILDING BASE"

        building = generator.generate_building_mode_prompt()

        assert "No scripts created yet" in building["append"]
        assert "## Skill Scripts" not in building["append"]


# ===========================================================================
# 2. Skills that ship scripts are named, with the run + relay rules
# ===========================================================================


class TestSkillScriptsBlock:
    def test_a_skill_with_scripts_gets_the_block(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(workspace / "skills", "dad-jokes", scripts=("jokes.py",))

        prompt = _conversation_prompt(workspace)

        assert "## Skill Scripts" in prompt
        assert "`dad-jokes`" in prompt
        assert "part of using that skill, not a separate task" in prompt
        assert "verbatim" in prompt
        # Relaying is scoped to the script's own message, never raw internals.
        assert "Never paste a traceback or a credential value" in prompt
        # Placed after the owner's workflow prompt, before the credentials docs.
        assert prompt.index("You tell jokes.") < prompt.index("## Skill Scripts")
        assert prompt.index("## Skill Scripts") < prompt.index("## Available Credentials")

    def test_only_skills_with_scripts_are_named(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(workspace / "skills", "dad-jokes", scripts=("jokes.py",))
        _write_skill(workspace / "skills", "dirty-jokes")

        section = _generator(workspace)._get_skill_scripts_section()

        assert section is not None
        assert "`dad-jokes`" in section
        assert "dirty-jokes" not in section
        # A file the script wrote for the user is delivered, not pasted inline.
        assert "`<cinna_attach>`" in section

    def test_a_scripts_folder_with_only_scaffolding_does_not_count(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(
            workspace / "skills",
            "dad-jokes",
            scripts=(".gitkeep", "README.md", "__pycache__/jokes.cpython-312.pyc"),
        )

        assert _generator(workspace)._get_skill_scripts_section() is None

    def test_a_skill_the_model_may_not_invoke_is_not_named(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(
            workspace / "skills",
            "release",
            scripts=("ship.py",),
            extra_frontmatter="disable-model-invocation: true\n",
        )

        assert _generator(workspace)._get_skill_scripts_section() is None

    def test_skills_without_scripts_get_no_block(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(workspace / "skills", "dirty-jokes")

        assert "## Skill Scripts" not in _conversation_prompt(workspace)

    def test_an_invalid_skill_is_not_advertised(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        # Folder name and frontmatter name disagree → invalid, never projected.
        _write_skill(
            workspace / "skills", "broken", scripts=("run.py",), skill_name="not-broken"
        )

        assert _generator(workspace)._get_skill_scripts_section() is None

    def test_an_agent_with_no_skills_folder_gets_no_block(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        (workspace / "skills").rmdir()

        assert _generator(workspace)._get_skill_scripts_section() is None


# ===========================================================================
# 3. Catalog and marketplace skills live under active plugins
# ===========================================================================


class TestPluginSkillScripts:
    def _plugin(self, workspace: Path, name: str) -> Path:
        plugin_dir = workspace / "plugins" / "cinna-skills" / name
        (plugin_dir / "skills").mkdir(parents=True)
        return plugin_dir

    def test_an_active_plugin_skill_with_scripts_is_named(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        plugin_dir = self._plugin(workspace, "weather-report")
        _write_skill(plugin_dir / "skills", "weather-report", scripts=("forecast.py",))

        section = _generator(
            workspace, plugins=[{"path": str(plugin_dir), "conversation_mode": True}]
        )._get_skill_scripts_section()

        assert section is not None
        assert "`weather-report`" in section

    def test_without_the_plugin_source_plugin_skills_are_not_seen(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        plugin_dir = self._plugin(workspace, "weather-report")
        _write_skill(plugin_dir / "skills", "weather-report", scripts=("forecast.py",))

        assert _generator(workspace)._get_skill_scripts_section() is None

    def test_a_name_in_both_places_is_named_once(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(workspace / "skills", "dad-jokes", scripts=("jokes.py",))
        plugin_dir = self._plugin(workspace, "dad-jokes")
        _write_skill(plugin_dir / "skills", "dad-jokes", scripts=("jokes.py",))

        section = _generator(
            workspace, plugins=[{"path": str(plugin_dir)}, {"path": str(plugin_dir)}]
        )._get_skill_scripts_section()

        assert section is not None
        assert section.count("`dad-jokes`") == 1

    def test_a_failing_plugin_source_keeps_local_skills(self, tmp_path: Path):
        workspace = _workspace(tmp_path)
        _write_skill(workspace / "skills", "dad-jokes", scripts=("jokes.py",))

        def broken(_mode: str) -> list[dict]:
            raise RuntimeError("settings.json unreadable")

        section = PromptGenerator(
            str(workspace), active_plugins_for_mode=broken
        )._get_skill_scripts_section()

        assert section is not None
        assert "`dad-jokes`" in section
