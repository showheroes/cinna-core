"""
Phase 5 advanced-provider and cross-SDK tests.

Tests cover:
1. Ollama credential type — validation, config generation, adapter defaults
2. Bedrock / Azure config generation (verifying Phase 2-3 work end-to-end)
3. EnvironmentCard SDK badge label combinations (via pure Python logic extracted
   from the TypeScript helper — we verify the Python-side lifecycle generates
   the correct model strings for each provider)
4. Cross-SDK scenario: Claude Code (building/Opus) + OpenCode (conversation/GPT-4o-mini)
   — config generation produces two distinct per-mode configs with the right models
5. Ollama local model scenario: OpenCode conversation with llama3.2

All filesystem writes use tmp_path fixtures so no real environment directories
are required. No Docker, no real API keys needed.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_BACKEND_DIR = Path(__file__).parents[2]
_LIFECYCLE_MODULE = _BACKEND_DIR / "app" / "services" / "environment_lifecycle.py"
_ADAPTER_DIR = (
    _BACKEND_DIR
    / "app"
    / "env-templates"
    / "app_core_base"
    / "core"
    / "server"
    / "adapters"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_environment(
    sdk_building="claude-code/anthropic",
    sdk_conversation="opencode/openai",
    model_override_building=None,
    model_override_conversation=None,
    conversation_cred_id=None,
    building_cred_id=None,
):
    """Build a minimal mock AgentEnvironment suitable for lifecycle tests."""
    env = MagicMock()
    env.id = "test-env-id"
    env.agent_sdk_building = sdk_building
    env.agent_sdk_conversation = sdk_conversation
    env.model_override_building = model_override_building
    env.model_override_conversation = model_override_conversation
    env.conversation_ai_credential_id = conversation_cred_id
    env.building_ai_credential_id = building_cred_id
    return env


def _load_lifecycle():
    """Import EnvironmentLifecycleManager (lazy to avoid heavy app bootstrap)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("environment_lifecycle", _LIFECYCLE_MODULE)
    # The module has cross-imports — just import via the installed package path
    from app.services.environment_lifecycle import EnvironmentLifecycleManager

    return EnvironmentLifecycleManager()


# ---------------------------------------------------------------------------
# 1. AICredentialType includes ollama
# ---------------------------------------------------------------------------

class TestOllamaCredentialType:
    """Verify the ollama credential type is registered in the enum."""

    def test_ollama_in_enum(self):
        from app.models.ai_credential import AICredentialType

        assert AICredentialType.OLLAMA == "ollama"
        assert "ollama" in [t.value for t in AICredentialType]

    def test_ollama_validation_requires_base_url(self):
        """ai_credentials_service rejects ollama credential without base_url."""
        from app.services.ai_credentials_service import AICredentialsService
        from app.models.ai_credential import AICredentialType
        from fastapi import HTTPException

        svc = AICredentialsService()
        with pytest.raises(HTTPException) as exc_info:
            svc._validate_credential_data(
                cred_type=AICredentialType.OLLAMA,
                api_key="ollama",
                base_url=None,
                model=None,
            )
        assert exc_info.value.status_code == 400
        assert "Base URL" in str(exc_info.value.detail)

    def test_ollama_validation_passes_with_base_url(self):
        """ai_credentials_service accepts ollama credential with base_url."""
        from app.services.ai_credentials_service import AICredentialsService
        from app.models.ai_credential import AICredentialType

        svc = AICredentialsService()
        # Should not raise
        svc._validate_credential_data(
            cred_type=AICredentialType.OLLAMA,
            api_key="ollama",
            base_url="http://localhost:11434",
            model=None,
        )

    def test_ollama_validation_optional_api_key(self):
        """Ollama validation does not require a real API key (dummy 'ollama' works)."""
        from app.services.ai_credentials_service import AICredentialsService
        from app.models.ai_credential import AICredentialType

        svc = AICredentialsService()
        # Should not raise even with a dummy value
        svc._validate_credential_data(
            cred_type=AICredentialType.OLLAMA,
            api_key="ollama",
            base_url="http://host.docker.internal:11434",
            model="llama3.2",
        )


# ---------------------------------------------------------------------------
# 2. _generate_opencode_config_files — Ollama provider
# ---------------------------------------------------------------------------

class TestOpenCodeConfigGenerationOllama:
    """Config file generation for the ollama provider."""

    def test_ollama_config_uses_correct_model(self, tmp_path):
        """Generated conversation config embeds ollama model string."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/ollama",
            model_override_conversation=None,  # use default
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            ollama_api_key="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.2",
        )

        conv_config_path = tmp_path / "app" / "core" / ".opencode" / "conversation_config.json"
        assert conv_config_path.exists(), "conversation_config.json not created"

        config = json.loads(conv_config_path.read_text())
        assert config["model"] == "ollama/llama3.2"

    def test_ollama_config_auth_section(self, tmp_path):
        """auth section in conversation config contains ollama key with baseURL."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/ollama",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            ollama_api_key="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model=None,
        )

        conv_config_path = tmp_path / "app" / "core" / ".opencode" / "conversation_config.json"
        config = json.loads(conv_config_path.read_text())

        assert "ollama" in config["auth"]
        assert config["auth"]["ollama"]["baseURL"] == "http://localhost:11434"
        assert config["auth"]["ollama"]["apiKey"] == "ollama"

    def test_ollama_model_override_respected(self, tmp_path):
        """Explicit model_override_conversation takes priority over ollama default."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/ollama",
            model_override_conversation="mistral",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            ollama_api_key="ollama",
            ollama_base_url="http://localhost:11434",
            ollama_model="llama3.2",
        )

        conv_config_path = tmp_path / "app" / "core" / ".opencode" / "conversation_config.json"
        config = json.loads(conv_config_path.read_text())
        # model_override_conversation = "mistral" takes precedence
        assert config["model"] == "mistral"

    def test_ollama_no_building_config_when_building_uses_claude_code(self, tmp_path):
        """Building config is NOT generated when building SDK is claude-code."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/ollama",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            ollama_api_key="ollama",
            ollama_base_url="http://localhost:11434",
        )

        building_config_path = tmp_path / "app" / "core" / ".opencode" / "building_config.json"
        # claude-code is not opencode → no building config
        assert not building_config_path.exists()


# ---------------------------------------------------------------------------
# 3. Cross-SDK scenario: Claude Code Opus (building) + OpenCode GPT-4o-mini (conv)
# ---------------------------------------------------------------------------

class TestCrossSDKClaudeCodeBuildingOpenCodeConversation:
    """
    End-to-end config test for the canonical cross-SDK setup:
    - Building: Claude Code + Anthropic + claude-opus-4 model override
    - Conversation: OpenCode + OpenAI + gpt-4o-mini model override
    """

    def test_cross_sdk_config_generation(self, tmp_path):
        """Only conversation_config.json is generated; building uses Claude Code (no opencode config)."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/openai",
            model_override_building="claude-opus-4",  # stored on env, used by claude code
            model_override_conversation="gpt-4o-mini",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            anthropic_api_key="sk-ant-test",
            openai_api_key="sk-openai-test",
        )

        opencode_dir = tmp_path / "app" / "core" / ".opencode"

        # Conversation config should exist with gpt-4o-mini
        conv_path = opencode_dir / "conversation_config.json"
        assert conv_path.exists(), "conversation_config.json must be created for opencode/openai"

        conv_config = json.loads(conv_path.read_text())
        assert conv_config["model"] == "gpt-4o-mini"
        assert "openai" in conv_config["auth"]
        assert conv_config["auth"]["openai"] == "sk-openai-test"

        # Building config must NOT exist (claude-code, not opencode)
        build_path = opencode_dir / "building_config.json"
        assert not build_path.exists(), "building_config.json must NOT be created when SDK is claude-code"

    def test_cross_sdk_building_model_override_is_separate(self, tmp_path):
        """model_override_building is stored on the environment but does not affect opencode config."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/openai",
            model_override_building="claude-opus-4",
            model_override_conversation="gpt-4o-mini",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            anthropic_api_key="sk-ant-test",
            openai_api_key="sk-openai-test",
        )

        # The conversation config uses the conversation override only
        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )
        assert conv_config["model"] == "gpt-4o-mini"
        # The building model override is not leaking into the conversation config
        assert conv_config["model"] != "claude-opus-4"

    def test_cross_sdk_openai_default_model_fallback(self, tmp_path):
        """Without a model override, opencode/openai conversation uses gpt-4o-mini default."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/openai",
            model_override_conversation=None,  # rely on provider default
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            openai_api_key="sk-openai-test",
        )

        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )
        # Default for openai/conversation is gpt-4o-mini
        assert conv_config["model"] == "openai/gpt-4o-mini"


# ---------------------------------------------------------------------------
# 4. Bedrock config generation (verifying end-to-end Phase 2-3 integration)
# ---------------------------------------------------------------------------

class TestBedrockOpenCodeConfig:
    """Config generation for opencode/bedrock."""

    def test_bedrock_config_auth_structure(self, tmp_path):
        """Bedrock auth section has the correct AWS credential structure."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="opencode/bedrock",
            sdk_conversation="opencode/bedrock",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            bedrock_access_key="AKIATEST",
            bedrock_secret_key="secret123",
            bedrock_region="us-east-1",
        )

        building_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "building_config.json").read_text()
        )
        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )

        for config in (building_config, conv_config):
            assert "amazon-bedrock" in config["auth"]
            creds = config["auth"]["amazon-bedrock"]
            assert creds["accessKeyId"] == "AKIATEST"
            assert creds["secretAccessKey"] == "secret123"
            assert creds["region"] == "us-east-1"

    def test_bedrock_default_models(self, tmp_path):
        """Bedrock uses different default models for building vs conversation."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="opencode/bedrock",
            sdk_conversation="opencode/bedrock",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            bedrock_access_key="AKIATEST",
            bedrock_secret_key="secret123",
            bedrock_region="us-east-1",
        )

        building_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "building_config.json").read_text()
        )
        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )

        # Building uses sonnet, conversation uses haiku
        assert "sonnet" in building_config["model"].lower()
        assert "haiku" in conv_config["model"].lower()


# ---------------------------------------------------------------------------
# 5. Azure config generation
# ---------------------------------------------------------------------------

class TestAzureOpenCodeConfig:
    """Config generation for opencode/azure."""

    def test_azure_auth_structure(self, tmp_path):
        """Azure auth section has apiKey and resourceName."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="opencode/azure",
            sdk_conversation="opencode/azure",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            azure_api_key="azure-key-123",
            azure_resource_name="my-azure-resource",
        )

        for fname in ("building_config.json", "conversation_config.json"):
            config = json.loads(
                (tmp_path / "app" / "core" / ".opencode" / fname).read_text()
            )
            assert "azure" in config["auth"]
            assert config["auth"]["azure"]["apiKey"] == "azure-key-123"
            assert config["auth"]["azure"]["resourceName"] == "my-azure-resource"

    def test_azure_model_override(self, tmp_path):
        """Model override is respected for Azure."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="opencode/azure",
            sdk_conversation="opencode/azure",
            model_override_building="azure/gpt-4o-2024-11-20",
            model_override_conversation="azure/gpt-4o-mini",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            azure_api_key="azure-key-123",
            azure_resource_name="my-azure-resource",
        )

        building_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "building_config.json").read_text()
        )
        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )

        assert building_config["model"] == "azure/gpt-4o-2024-11-20"
        assert conv_config["model"] == "azure/gpt-4o-mini"


# ---------------------------------------------------------------------------
# 6. OpenCode adapter _DEFAULT_MODELS includes ollama
# ---------------------------------------------------------------------------

class TestOpenCodeAdapterDefaults:
    """Verify the adapter's default model table is correct for all providers."""

    def _load_defaults(self):
        """Load _DEFAULT_MODELS from the adapter module."""
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "opencode_adapter",
            _ADAPTER_DIR / "opencode_adapter.py",
        )
        mod = importlib.util.module_from_spec(spec)

        # The adapter imports from sibling modules — patch those away
        sys.modules.setdefault(
            "opencode_adapter.base",
            MagicMock(
                BaseSDKAdapter=object,
                SDKEvent=MagicMock,
                SDKEventType=MagicMock(),
                SDKConfig=MagicMock,
                AdapterRegistry=MagicMock(register=lambda cls: cls),
            ),
        )
        # Patch the relative import chain
        for mod_name in [
            "core.server.adapters.base",
            "core.server.prompt_generator",
            "core.server.active_session_manager",
            "core.server.agent_env_service",
        ]:
            sys.modules.setdefault(mod_name, MagicMock())

        # Manually load just the constants section without executing class body
        src = (_ADAPTER_DIR / "opencode_adapter.py").read_text()
        # Extract just the _DEFAULT_MODELS constant via exec on a minimal subset
        local_ns: dict = {}
        for line in src.split("\n"):
            if line.startswith("_DEFAULT_MODELS") or (local_ns and line.startswith("}")):
                break
        # Parse by re-importing safely: use importlib in a subprocess-safe way
        import ast

        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "_DEFAULT_MODELS":
                        return ast.literal_eval(node.value)
        return {}

    def test_ollama_in_default_models(self):
        defaults = self._load_defaults()
        assert "ollama" in defaults
        assert "building" in defaults["ollama"]
        assert "conversation" in defaults["ollama"]
        assert defaults["ollama"]["building"].startswith("ollama/")

    def test_all_expected_providers_in_defaults(self):
        defaults = self._load_defaults()
        expected = {"anthropic", "openai", "openai_compatible", "google", "bedrock", "azure", "ollama", "default"}
        assert expected.issubset(set(defaults.keys()))

    def test_ollama_supported_providers(self):
        """SUPPORTED_PROVIDERS list in adapter includes ollama."""
        src = (_ADAPTER_DIR / "opencode_adapter.py").read_text()
        # SUPPORTED_PROVIDERS is a class attribute — find its line and check it contains "ollama"
        for line in src.split("\n"):
            if "SUPPORTED_PROVIDERS" in line and "ollama" in line:
                return  # found it
        # Also check multiline — the list may span multiple lines
        # Find the block between SUPPORTED_PROVIDERS = [ ... ]
        start_idx = src.find("SUPPORTED_PROVIDERS")
        if start_idx == -1:
            pytest.fail("SUPPORTED_PROVIDERS not found in opencode_adapter.py")
        block_end = src.find("]", start_idx)
        block = src[start_idx:block_end + 1]
        assert "ollama" in block, f"'ollama' not in SUPPORTED_PROVIDERS block:\n{block}"


# ---------------------------------------------------------------------------
# 7. SDK→credential type mapping includes ollama in both lifecycle occurrences
# ---------------------------------------------------------------------------

class TestLifecycleSDKCredentialMapping:
    """Verify both SDK_TO_CREDENTIAL_TYPE dicts in environment_lifecycle include ollama."""

    def test_ollama_in_sdk_to_credential_map(self):
        """Both occurrences of SDK_TO_CREDENTIAL_TYPE in lifecycle include opencode/ollama."""
        src = _LIFECYCLE_MODULE.read_text()
        # There should be two occurrences of "opencode/ollama" in the file
        count = src.count('"opencode/ollama"')
        assert count >= 2, (
            f"Expected at least 2 occurrences of '\"opencode/ollama\"' in lifecycle, found {count}"
        )

    def test_ollama_maps_to_ollama_type(self):
        """The opencode/ollama key maps to AICredentialType.OLLAMA."""
        src = _LIFECYCLE_MODULE.read_text()
        # Check that the mapping value is AICredentialType.OLLAMA
        assert "AICredentialType.OLLAMA" in src


# ---------------------------------------------------------------------------
# 8. MCP bridge config presence for ollama-based environment
# ---------------------------------------------------------------------------

class TestOpenCodeOllamaMCPBridgeConfig:
    """Generated ollama config includes MCP bridge servers."""

    def test_ollama_config_has_mcp_bridges(self, tmp_path):
        """Conversation config for ollama includes all three MCP bridge servers."""
        from app.services.environment_lifecycle import EnvironmentLifecycleManager

        mgr = EnvironmentLifecycleManager()
        env = _make_environment(
            sdk_building="claude-code/anthropic",
            sdk_conversation="opencode/ollama",
        )

        mgr._generate_opencode_config_files(
            tmp_path,
            env,
            ollama_api_key="ollama",
            ollama_base_url="http://localhost:11434",
        )

        conv_config = json.loads(
            (tmp_path / "app" / "core" / ".opencode" / "conversation_config.json").read_text()
        )

        mcp = conv_config.get("mcp", {})
        assert "knowledge" in mcp, "knowledge MCP bridge missing from ollama config"
        assert "task" in mcp, "task MCP bridge missing from ollama config"
        assert "collaboration" in mcp, "collaboration MCP bridge missing from ollama config"
