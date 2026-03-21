# Multi-SDK Support — Technical Reference

## File Locations

**Backend — Models:**
- `backend/app/models/user.py` — `User`, `UserUpdateMe`, `UserPublic` (SDK default fields), `AIServiceCredentials`, `AIServiceCredentialsUpdate`, `UserPublicWithAICredentials`
- `backend/app/models/environment.py` — `AgentEnvironment`, `AgentEnvironmentCreate`, `AgentEnvironmentPublic` (SDK selection fields)

**Backend — Services:**
- `backend/app/services/environment_service.py` — SDK constants, default cascade logic, credential validation
- `backend/app/services/environment_lifecycle.py` — env file generation, settings file generation, rebuild regeneration

**Backend — Routes:**
- `backend/app/api/routes/users.py` — AI credential endpoints, SDK default update
- `backend/app/api/routes/agents.py` — environment creation with SDK fields

**Migrations:**
- `backend/app/alembic/versions/776395044d2b_add_agent_sdk_fields_to_environment.py`
- `backend/app/alembic/versions/c8d9e0f1a2b3_add_default_sdk_fields_to_user.py`
- `backend/app/alembic/versions/f0920ee2eeab_add_model_override_fields_to_environment.py`
- `backend/app/alembic/versions/a1b2c3d4e5f7_add_default_credential_fields_to_user.py`

**Frontend — Components:**
- `frontend/src/components/UserSettings/AICredentials.tsx`
- `frontend/src/components/Environments/AddEnvironment.tsx`
- `frontend/src/components/Environments/EnvironmentCard.tsx`

**Frontend — Client:**
- `frontend/src/client/` (auto-generated OpenAPI types and service classes)

**Agent Environment (inside container):**
- `backend/app/env-templates/app_core_base/core/server/sdk_manager.py`
- `backend/app/env-templates/app_core_base/core/server/adapters/base.py`
- `backend/app/env-templates/app_core_base/core/server/adapters/claude_code.py`
- `backend/app/env-templates/app_core_base/core/server/adapters/opencode_adapter.py`
- `backend/app/env-templates/app_core_base/core/server/adapters/google_adk.py`
- `backend/app/env-templates/app_core_base/core/server/tools/mcp_bridge/knowledge_server.py`
- `backend/app/env-templates/app_core_base/core/server/tools/mcp_bridge/task_server.py`
- `backend/app/env-templates/app_core_base/core/server/tools/mcp_bridge/collaboration_server.py`

## Database Schema

**User table** (`backend/app/models/user.py`):
- `default_sdk_conversation` — nullable string, SDK ID for conversation mode default (e.g., `claude-code/anthropic`)
- `default_sdk_building` — nullable string, SDK ID for building mode default
- `ai_credentials_encrypted` — encrypted JSON blob containing all AI provider credentials (legacy; still used for backward compat when no named credential is set)
- `default_ai_credential_conversation_id` — UUID FK to `ai_credential.id` (nullable, `ondelete=SET NULL`); user's preferred named credential for new environments in conversation mode
- `default_ai_credential_building_id` — UUID FK to `ai_credential.id` (nullable, `ondelete=SET NULL`); user's preferred named credential for new environments in building mode
- `default_model_override_conversation` — nullable string (max 255); optional model override saved as part of user's conversation mode default preference
- `default_model_override_building` — nullable string (max 255); optional model override saved as part of user's building mode default preference

**AgentEnvironment table** (`backend/app/models/environment.py`):
- `agent_sdk_conversation` — string, SDK ID selected at creation, immutable
- `agent_sdk_building` — string, SDK ID selected at creation, immutable

**Schema constants** (`backend/app/services/environment_service.py`):
- `SDK_ANTHROPIC` (`claude-code/anthropic`), `SDK_MINIMAX` (`claude-code/minimax`), `SDK_OPENAI_COMPATIBLE` (`google-adk-wr/openai-compatible`)
- `SDK_ENGINE_CLAUDE_CODE`, `SDK_ENGINE_OPENCODE`, `SDK_ENGINE_GOOGLE_ADK` — engine-only prefix constants
- `VALID_SDK_ENGINES` — list of the three valid engine prefixes
- `SDK_CREDENTIAL_COMPATIBILITY` — dict mapping engine → list of compatible credential type strings
- `SDK_TO_CREDENTIAL_TYPE` — full SDK ID → `AICredentialType` mapping including all `opencode/*` variants

**AgentEnvironment model** (`backend/app/models/environment.py`):
- `model_override_conversation: str | None` — optional model override for conversation mode (e.g., `gpt-4o-mini`)
- `model_override_building: str | None` — optional model override for building mode (e.g., `claude-opus-4`)

## API Endpoints

**User credentials and SDK defaults** (`backend/app/api/routes/users.py`):
- `GET /api/v1/users/me` — returns `default_sdk_conversation`, `default_sdk_building`, `default_ai_credential_conversation_id`, `default_ai_credential_building_id`, `default_model_override_conversation`, `default_model_override_building`
- `PATCH /api/v1/users/me` — updates SDK default fields including `default_ai_credential_*_id` and `default_model_override_*`; SDK ID values validated against `VALID_SDK_OPTIONS`
- `GET /api/v1/users/me/ai-credentials/status` — boolean key presence flags + all SDK default fields (used by frontend to pre-populate both the Settings panel and Add Environment dialog)
- `GET /api/v1/users/me/ai-credentials` — full credentials including `openai_compatible_base_url`, `openai_compatible_model`
- `PATCH /api/v1/users/me/ai-credentials` — updates credential fields (partial update, non-empty fields only)

**Environment creation** (`backend/app/api/routes/agents.py`):
- `POST /api/v1/agents/{id}/environments` — accepts `agent_sdk_conversation`, `agent_sdk_building`

## Services & Key Methods

**`backend/app/services/environment_service.py`:**
- `SDK_API_KEY_MAP` — maps legacy SDK ID to required credential field name (for backward compat)
- `SDK_CREDENTIAL_COMPATIBILITY` — maps engine prefix to list of compatible credential type strings
- `_validate_sdk_credential_compatibility()` — raises `EnvironmentCredentialError` if SDK engine and credential type are incompatible
- `create_environment()` — applies default SDK cascade, validates SDK ↔ credential compatibility, passes credential params to background task

**`backend/app/services/environment_lifecycle.py`:**
- `create_environment_instance()` — accepts all credential params for supported provider types
- `_update_environment_config()` — fetches user credentials and triggers env file generation
- `_generate_env_file()` — writes `.env`; conditionally includes `ANTHROPIC_API_KEY`; calls settings generators for MiniMax, OpenAI Compatible, and OpenCode
- `_generate_minimax_settings_files()` — writes JSON settings to `app/core/.claude/`
- `_generate_openai_compatible_settings_files()` — writes JSON settings to `app/core/.google-adk/`
- `_generate_opencode_config_files()` — writes `building_config.json` and `conversation_config.json` to `app/core/.opencode/`; embeds auth credentials (Anthropic, OpenAI, Google, or OpenAI-compatible), model selection (with override support), and MCP bridge server references; called when either mode uses `opencode/*`
- `rebuild_environment()` — after core replacement, regenerates settings files for all adapter types including OpenCode

## Frontend Components

**`frontend/src/components/UserSettings/AICredentials.tsx`:**
- Two-panel layout: AI Credentials list (left) and Default SDK Preferences (right)
- Default SDK Preferences panel renders two bordered sections (Conversation Mode, Building Mode), each with three cascading controls: SDK Engine select, Credential select, Model Override input
- SDK Engine options: `claude-code` ("Claude Code"), `opencode` ("OpenCode"), `google-adk-wr` ("Google ADK (simplified)")
- Credential dropdown filtered via `SDK_CREDENTIAL_COMPATIBILITY` map; first option is "Use Default" (`__default__` sentinel)
- Model Override input uses `<datalist>` for type-specific suggestions (`SUGGESTED_MODELS` map)
- All three values per mode saved together via a single "Save Preferences" button (`handleSavePreferences`)
- Engine change cascades: resets credential to `__default__` and clears model override
- Initializes from `status.default_sdk_*`, `status.default_ai_credential_*_id`, `status.default_model_override_*` on first load
- `updateSdkMutation` sends `default_sdk_*`, `default_ai_credential_*_id`, and `default_model_override_*` in one `PATCH /users/me` call

**`frontend/src/components/Environments/AddEnvironment.tsx`:**
- Cascading SDK Engine → Credential → Model Override per mode (same three-step pattern as User Settings)
- Credential dropdown is always visible inline (no "Use Default AI Credentials" toggle)
- First credential option is "Default (use account default)" (`__default__` sentinel); text hint shown below: "Will use your default credential for this provider type."
- Pre-populated on dialog open from `credentialsStatus.default_sdk_*`, `default_ai_credential_*_id`, `default_model_override_*`
- `composeSDKId(engine, credential)` builds the full SDK ID sent to the backend (`engine/credentialType`)
- Submit logic: if both modes use `__default__` sentinel → sends `use_default_ai_credentials: true`; otherwise sends explicit credential IDs, with `undefined` for modes still on "Default"

**`frontend/src/components/Environments/EnvironmentCard.tsx`:**
- SDK badges with MessageCircle (conversation) and Wrench (building) icons
- `getSDKDisplayName()` converts SDK ID to display label

**React Query hooks:**
- `useQuery(["aiCredentialsStatus"])` — boolean flags + SDK defaults including `default_ai_credential_*_id` and `default_model_override_*`; used by AICredentials and AddEnvironment
- `useQuery(["aiCredentialsList"])` — list of `AICredentialPublic` objects for credential dropdowns in both components
- `useMutation` in AICredentials — SDK preference update: sends `default_sdk_*`, `default_ai_credential_*_id`, `default_model_override_*` together via `PATCH /users/me`; invalidates `aiCredentialsStatus` + `currentUser`

## Adapter Architecture (inside container)

**`adapters/base.py`:**
- `SDKConfig` — parses `SDK_ADAPTER_{MODE}` env var; splits provider/variant (e.g., `claude-code/anthropic`)
- `BaseSDKAdapter` — abstract base; all adapters must implement `send_message_stream()`
- `AdapterRegistry` — maps SDK prefix to adapter class; `create_adapter(config)` instantiates correct adapter
- `SDKEvent` + `SDKEventType` — unified event format produced by all adapters

**`adapters/claude_code.py` — `ClaudeCodeAdapter`:**
- Handles `claude-code/*` variants (anthropic, minimax)
- Settings file detection: checks `/app/core/.claude/{mode}_settings.json`; if present, passes path via `options.settings`
- Falls back to `ANTHROPIC_API_KEY` env var if no settings file found

**`adapters/google_adk.py` — `GoogleADKAdapter`:**
- Handles `google-adk-wr/*` variants (openai-compatible, gemini)
- `_load_settings_for_mode(mode)` — reads `/app/core/.google-adk/{mode}_settings.json`
- `_get_openai_compatible_config(mode)` — extracts `api_key`, `base_url`, `model` from settings
- Gemini provider is a placeholder

**`adapters/opencode_adapter.py` — `OpenCodeAdapter`:**
- Handles all `opencode/*` variants
- Reads per-mode config from `/app/core/.opencode/{mode}_config.json` (generated by backend at create/rebuild)
- Runs `opencode serve` as a background subprocess on port 4096
- Communicates via HTTP: `POST /session`, `POST /session/:id/message`, `GET /global/event` (SSE), `DELETE /session/:id`
- Writes system prompt to `/app/core/.opencode/AGENTS.md` before each message
- Writes session context to `/app/core/.opencode/session_context.json` for MCP bridge servers
- Custom tools exposed via `mcp_bridge/` stdio servers configured in the generated `opencode.json`

**`tools/mcp_bridge/` — MCP Bridge Servers (OpenCode only):**
- `knowledge_server.py` — stdio MCP server wrapping `knowledge_query` tool
- `task_server.py` — stdio MCP server wrapping `create_agent_task`, `respond_to_task`, `update_session_state`
- `collaboration_server.py` — stdio MCP server wrapping `create_collaboration`, `post_finding`, `get_collaboration_status`

### SDKEvent Fields

`SDKEvent` dataclass (`adapters/base.py`):
- `type: SDKEventType` — `SESSION_CREATED`, `ASSISTANT`, `TOOL_USE`, `THINKING`, `DONE`, `INTERRUPTED`, `ERROR`
- `content: str` — human-readable message
- `session_id: str` — SDK session identifier
- `metadata: dict` — event-specific additional data
- `tool_name: str` — populated for `TOOL_USE` events
- `error_type: str` — populated for `ERROR` events

## Configuration

**Environment variables injected into container:**
- `SDK_ADAPTER_BUILDING` — SDK ID for building mode (e.g., `claude-code/anthropic`)
- `SDK_ADAPTER_CONVERSATION` — SDK ID for conversation mode

**Settings file locations inside container:**
- `app/core/.claude/building_settings.json` — MiniMax building mode config
- `app/core/.claude/conversation_settings.json` — MiniMax conversation mode config
- `app/core/.google-adk/building_settings.json` — OpenAI Compatible building mode config
- `app/core/.google-adk/conversation_settings.json` — OpenAI Compatible conversation mode config
- `app/core/.opencode/building_config.json` — OpenCode building mode: model, auth, mcp, permissions
- `app/core/.opencode/conversation_config.json` — OpenCode conversation mode: model, auth, mcp, permissions

**MiniMax settings file fields:** `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN`, model mappings

**OpenAI Compatible settings file fields:** `providers.openai-compatible.api_key`, `providers.openai-compatible.base_url`, `providers.openai-compatible.model`

**OpenCode config file fields:**
- `model` — provider-qualified model string (e.g., `anthropic/claude-sonnet-4-5`, `openai/gpt-4o`); set from `model_override_*` if provided, else from per-provider mode defaults
- `permission` — tool permission map (all tools set to `"allow"`)
- `tools` — per-tool enable flags (webfetch, websearch, bash, read, write, edit, glob, grep, list, patch)
- `mcp` — MCP bridge server commands for custom platform tools (knowledge, task, collaboration)
- `server` — `{"port": 4096, "hostname": "127.0.0.1"}`
- `auth` — provider credentials (format varies: Anthropic = string key, OpenAI = string key, Google = string key, OpenAI-compatible = object with api_key/base_url/model)

## Security

- SDK values validated against `VALID_SDK_OPTIONS` before database write
- User must have required credentials before environment creation — checked via `SDK_API_KEY_MAP`
- AI credentials stored encrypted in `ai_credentials_encrypted` JSON blob; decrypted only during env generation
- Settings files are generated per-environment with the owning user's keys
- SDK selection is immutable post-creation — no runtime SDK switching
- API keys not accessible across users; credentials fetched by user ID in service layer
