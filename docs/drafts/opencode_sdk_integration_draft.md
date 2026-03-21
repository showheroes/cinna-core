# OpenCode SDK Integration — Draft

## Goal

Add OpenCode as a new SDK adapter option alongside the existing Claude Code and Google ADK adapters, allowing users to select OpenCode-powered agents with any of its 75+ supported AI providers.

---

## What is OpenCode

OpenCode is an open-source AI coding agent (similar to Claude Code) with:
- **75+ AI provider support** via AI SDK / Models.dev — Anthropic, OpenAI, Google, Amazon Bedrock, Azure, Ollama, local models, and any OpenAI-compatible endpoint
- **Client-server architecture** — a Go-based server exposing an HTTP API (OpenAPI 3.1) + SSE events, with TUI/CLI/Web/SDK clients
- **Built-in tools** — `read`, `write`, `edit`, `patch`, `bash`, `grep`, `glob`, `list`, `webfetch`, `websearch`, `lsp`, `question`, `todowrite`, `todoread`
- **MCP server support** — local and remote MCP servers configured in `opencode.json`
- **Custom tools** — TypeScript/JS-based tool definitions in `.opencode/tools/`
- **Granular permissions** — per-tool allow/ask/deny with glob pattern matching
- **Session persistence** — create, resume, delete sessions; multi-session support
- **System prompt customization** — `AGENTS.md` file + `instructions` field in config
- **JavaScript/TypeScript SDK** (`@opencode-ai/sdk`) — programmatic client for the server API

---

## How OpenCode Works (Architecture)

```
opencode serve  →  HTTP Server (port 4096)  →  AI Provider (Anthropic, OpenAI, etc.)
                       │
                       ├── POST /session              → Create session
                       ├── POST /session/:id/message   → Send message (sync)
                       ├── POST /session/:id/prompt_async → Send message (async)
                       ├── GET /global/event           → SSE event stream
                       ├── PUT /auth/:id               → Set provider credentials
                       ├── PATCH /config               → Update config
                       └── GET /doc                    → OpenAPI spec
```

**Key design points:**
- Server starts with `opencode serve --port <port> --hostname <host>`
- No subprocess-based SDK like Claude Code — it's a standalone HTTP server
- The `@opencode-ai/sdk` npm package is a thin HTTP client wrapper
- Config via `opencode.json` (project-level) + env vars
- Credentials stored in `~/.local/share/opencode/auth.json` (set via `/connect` command or `PUT /auth/:id` API)
- Model selection: `"model": "provider/model-name"` in config (e.g., `"anthropic/claude-sonnet-4-5"`)
- Server password protection via `OPENCODE_SERVER_PASSWORD` env var

---

## Current Multi-SDK Architecture (Our Platform)

```
SDK_ADAPTER_{MODE} env var  →  SDKConfig.from_env(mode)  →  AdapterRegistry  →  Adapter instance
                                                                                    │
                                                                                    ▼
                                                                              send_message_stream()
                                                                                    │
                                                                                    ▼
                                                                           AsyncIterator[SDKEvent]
```

**Existing adapters:**
| Adapter Type | Providers | How it communicates | Custom tools |
|---|---|---|---|
| `claude-code` | `anthropic`, `minimax` | Python SDK (`claude_agent_sdk`) → subprocess | MCP servers via `create_sdk_mcp_server()` |
| `google-adk-wr` | `openai-compatible`, `gemini` (placeholder), `vertex` (placeholder) | Python library (`google.adk`) → in-process | `FunctionTool` wrappers (Bash, Read) |

**Key interfaces:**
- `BaseSDKAdapter` — abstract base with `send_message_stream()` and `interrupt_session()`
- `SDKEvent` / `SDKEventType` — unified event format (SESSION_CREATED, ASSISTANT, TOOL_USE, DONE, ERROR, etc.)
- `AdapterRegistry` — decorator-based registration
- `SDKConfig` — config from env vars
- `PromptGenerator` — builds system prompts per mode
- Custom tools: knowledge query, create agent task, respond to task, update session state, create collaboration, post finding, get collaboration status

---

## Rethinking the Environment Creation UX: SDK → Credentials → Model

### Problem with Current Approach

The current AddEnvironment dialog has **two flat SDK dropdowns** (conversation / building) where the SDK value implicitly determines which credential type is needed. This works for 3 options but breaks down when adding OpenCode because:

1. **SDK and AI provider are conflated** — `claude-code/anthropic` means both "use Claude Code SDK" AND "use Anthropic API key". With OpenCode, the same Anthropic API key can be used with a completely different SDK.
2. **No model override** — Building mode always uses Sonnet, conversation always uses Haiku. Users can't pick a specific model (e.g., Opus for building, GPT-4o for conversation).
3. **Credential filtering is SDK-specific** — Adding OpenCode doubles the SDK list but many entries share the same credential type.

### Proposed UX: Three-Step Selection Per Mode

Instead of a single SDK dropdown, split into a **three-step cascading selection** for each mode (building and conversation):

```
┌─────────────────────────────────────────────────────────┐
│  Building Mode                                          │
│                                                         │
│  1. SDK Engine:    [Claude Code  ▾]                     │
│  2. AI Credential: [Production Anthropic (default) ▾]   │
│  3. Model:         [Claude Opus 4  ▾]  (optional)       │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Conversation Mode                                      │
│                                                         │
│  1. SDK Engine:    [OpenCode  ▾]                        │
│  2. AI Credential: [My OpenAI Key ▾]                    │
│  3. Model:         [gpt-4o-mini  ▾]  (optional)         │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**Step 1 — SDK Engine** (determines runtime and tool capabilities):

| SDK Engine | Description | Compatible Credential Types |
|---|---|---|
| Claude Code | Anthropic's CLI agent SDK | `anthropic`, `minimax` |
| OpenCode | Multi-provider open-source agent | `anthropic`, `openai`, `openai_compatible`, `google`, `bedrock`, `azure` |
| Google ADK | Google's Agent Development Kit | `openai_compatible`, `google`, `vertex` |

**Step 2 — AI Credential** (determines API key and provider):
- Dropdown is **filtered by SDK compatibility** — only shows credential types the selected SDK supports
- Shows named credentials from the user's AI Credentials list (already exists)
- "Use Default" toggle still available for quick setup
- If no compatible credentials exist, show warning with link to Settings

**Step 3 — Model Override** (optional, determines cost/quality tradeoff):
- Optional text field or dropdown with common models for the selected credential type
- If left empty, SDK adapter uses its own defaults (Sonnet for building, Haiku for conversation with Claude Code; whatever OpenCode defaults for OpenCode)
- Examples: `claude-opus-4`, `claude-sonnet-4-5`, `gpt-4o`, `gpt-4o-mini`, `gemini-2.5-pro`
- Stored on the environment, passed to the adapter at runtime

**This design enables combinations like:**

| Use Case | Building SDK | Building Cred | Building Model | Conv SDK | Conv Cred | Conv Model |
|---|---|---|---|---|---|---|
| Full Anthropic | Claude Code | anthropic key | opus (default) | Claude Code | anthropic key | haiku (default) |
| Cost-optimized | Claude Code | anthropic key | sonnet | OpenCode | openai key | gpt-4o-mini |
| Local dev | OpenCode | ollama key | llama3.2 | OpenCode | ollama key | llama3.2 |
| Mixed providers | Claude Code | anthropic key | opus | OpenCode | anthropic key | haiku |
| Enterprise | Claude Code | bedrock key | via bedrock | OpenCode | azure key | gpt-4o |

### Data Model Changes

**`AgentEnvironment` model:**
```python
# Existing (renamed for clarity)
agent_sdk_conversation: str       # SDK engine ID: "claude-code", "opencode", "google-adk-wr"
agent_sdk_building: str           # SDK engine ID

# New fields
model_override_conversation: str | None = None  # e.g., "gpt-4o-mini", "claude-haiku-4-5"
model_override_building: str | None = None      # e.g., "claude-opus-4", "gpt-4o"
```

Note: Credential linking already exists via `conversation_ai_credential_id` / `building_ai_credential_id` on the environment model. The SDK engine determines the adapter type; the credential determines the provider and API key; the model override determines the exact model.

**SDK ID simplification:**
Currently SDK IDs encode both engine and provider (e.g., `claude-code/anthropic`). With the new approach, the SDK ID only needs to identify the **engine** since the provider comes from the credential:

| Current SDK ID | New SDK Engine | Provider From |
|---|---|---|
| `claude-code/anthropic` | `claude-code` | credential type = `anthropic` |
| `claude-code/minimax` | `claude-code` | credential type = `minimax` |
| `google-adk-wr/openai-compatible` | `google-adk-wr` | credential type = `openai_compatible` |
| `opencode/anthropic` (new) | `opencode` | credential type = `anthropic` |
| `opencode/openai` (new) | `opencode` | credential type = `openai` |

The full adapter ID (`claude-code/anthropic`) is still composed at runtime by combining the SDK engine + credential type. This is backward compatible — existing environments keep their current `agent_sdk_*` values.

### SDK ↔ Credential Compatibility Matrix

Defined as a constant shared between backend validation and frontend filtering:

```python
SDK_CREDENTIAL_COMPATIBILITY = {
    "claude-code": ["anthropic", "minimax"],
    "opencode": ["anthropic", "openai", "openai_compatible", "google", "bedrock", "azure"],
    "google-adk-wr": ["openai_compatible", "google", "vertex"],
}
```

```typescript
// Frontend equivalent
const SDK_CREDENTIAL_COMPATIBILITY: Record<string, string[]> = {
  "claude-code": ["anthropic", "minimax"],
  "opencode": ["anthropic", "openai", "openai_compatible", "google", "bedrock", "azure"],
  "google-adk-wr": ["openai_compatible", "google", "vertex"],
}
```

### Frontend Flow (AddEnvironment dialog)

1. User selects **SDK Engine** for a mode → credential dropdown filters to compatible types
2. User selects **AI Credential** → model override field appears with suggested models for that credential type
3. User optionally sets **Model Override** → free-text or dropdown
4. Repeat for the other mode (or "Same as building" checkbox for quick setup)
5. On submit, backend validates: SDK ↔ credential compatibility, credential exists, model format valid

**Credential dropdown behavior:**
- Groups credentials by type with type headers
- Shows credential name + "(default)" badge
- Disables credentials whose type is incompatible with selected SDK
- If "Use Default" is on, auto-resolves default credential for each compatible type

### Backend Validation Changes

```python
# In environment_service.py create_environment()
def _validate_sdk_credential_compatibility(sdk_engine: str, credential: AICredential):
    compatible_types = SDK_CREDENTIAL_COMPATIBILITY.get(sdk_engine, [])
    if credential.type not in compatible_types:
        raise ValueError(
            f"SDK '{sdk_engine}' is not compatible with credential type '{credential.type}'. "
            f"Compatible types: {compatible_types}"
        )
```

### Config Generation with Model Override

The model override is passed through to the adapter's config generation:

- **Claude Code**: `options.model = model_override or ("haiku" if conversation else None)`
- **OpenCode**: `opencode.json` → `"model": model_override or "anthropic/claude-sonnet-4-5"`
- **Google ADK**: `LiteLlm(model=model_override or default_model)`

The adapter resolves the model by: **explicit override → mode default → SDK default**.

---

## Proposed Integration Approach

### New Adapter: `opencode`

Register a new adapter type `opencode` that wraps the OpenCode server. Unlike Claude Code (which embeds the provider in the SDK ID), the OpenCode adapter determines its provider from the linked credential at runtime:

| SDK Engine | Credential Type | Effective Provider | Model Format |
|---|---|---|---|
| `opencode` | `anthropic` | `anthropic/...` | `anthropic/claude-sonnet-4-5` |
| `opencode` | `openai` | `openai/...` | `openai/gpt-4o` |
| `opencode` | `openai_compatible` | `openai-compatible/...` | Custom via base_url |
| `opencode` | `google` | `google/...` | `google/gemini-2.5-pro` |
| `opencode` | `bedrock` | `amazon-bedrock/...` | `amazon-bedrock/...` |
| `opencode` | `azure` | `azure/...` | `azure/gpt-4o` |

### Runtime Architecture

```
Agent Environment Container
├── opencode serve (background process, port 4096)
│   ├── opencode.json (generated by backend)
│   ├── auth.json (credentials injected)
│   └── AGENTS.md (system prompt)
│
└── OpenCodeAdapter (Python, inside core server)
    ├── HTTP client → localhost:4096
    ├── POST /session → create session
    ├── POST /session/:id/message → send message
    ├── GET /global/event → SSE stream for events
    └── Converts HTTP responses → SDKEvent stream
```

**Why run `opencode serve` as a background process (not SDK library)?**
- OpenCode is a Go binary, not a Python library — no in-process embedding
- The server model is its native architecture
- Session state managed by the server internally
- All tool execution happens inside the server process (same container = same filesystem)

### Implementation Components

#### 1. Backend: Credential & SDK Constants

**Files to modify:**
- `backend/app/models/user.py` — Add `SDK_OPENCODE_ANTHROPIC`, `SDK_OPENCODE_OPENAI`, `SDK_OPENCODE_CUSTOM` to `VALID_SDK_OPTIONS`; add `openai_api_key`, `opencode_api_key`, `opencode_base_url`, `opencode_model` to `AIServiceCredentials`
- `backend/app/services/environment_service.py` — Add to `SDK_API_KEY_MAP`; validation logic
- `backend/app/services/environment_lifecycle.py` — Add `_generate_opencode_config_files()` method

**New credential types** (added to the existing encrypted JSON blob — no migration needed):
```python
# In AIServiceCredentials
openai_api_key: str | None = None          # For opencode/openai
opencode_api_key: str | None = None        # For opencode/custom
opencode_base_url: str | None = None       # For opencode/custom
opencode_model: str | None = None          # For opencode/custom
```

#### 2. Backend: Config File Generation

When an environment uses an `opencode/*` SDK, the lifecycle service generates:

**`/app/core/.opencode/opencode.json`:**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "anthropic/claude-sonnet-4-5",
  "permission": {
    "*": "allow"
  },
  "tools": {
    "webfetch": true,
    "websearch": true,
    "bash": true,
    "read": true,
    "write": true,
    "edit": true,
    "glob": true,
    "grep": true,
    "list": true,
    "patch": true
  },
  "mcp": {},
  "server": {
    "port": 4096,
    "hostname": "127.0.0.1"
  }
}
```

**`/app/core/.opencode/auth.json`:**
```json
{
  "anthropic": "sk-ant-api03-..."
}
```

**`/app/core/.opencode/AGENTS.md`:**
Generated from the system prompt (same PromptGenerator output), written as markdown.

**Per-mode configs:**
Two config files: `building_opencode.json` and `conversation_opencode.json` with different model selections:
- Building: larger model (e.g., `anthropic/claude-sonnet-4-5`)
- Conversation: smaller model (e.g., `anthropic/claude-haiku-4-5-20251001`)

#### 3. Container: OpenCode Installation

**Dockerfile changes** (in the environment template):
```dockerfile
# Install opencode binary
RUN curl -fsSL https://opencode.ai/install | bash
```

OpenCode is a single Go binary — lightweight addition to the container image.

#### 4. Container: OpenCode Adapter

**New file: `backend/app/env-templates/app_core_base/core/server/adapters/opencode_adapter.py`**

```python
@AdapterRegistry.register
class OpenCodeAdapter(BaseSDKAdapter):
    ADAPTER_TYPE = "opencode"
    SUPPORTED_PROVIDERS = ["anthropic", "openai", "custom"]

    OPENCODE_CONFIG_DIR = Path("/app/core/.opencode")
    OPENCODE_PORT = 4096
    OPENCODE_BASE_URL = "http://127.0.0.1:4096"
```

**Key methods:**

| Method | Responsibility |
|---|---|
| `__init__` | Start `opencode serve` subprocess, wait for health check |
| `send_message_stream` | Create/resume session, POST message, stream SSE events, convert to SDKEvent |
| `interrupt_session` | Cancel running session (delete or signal) |
| `_start_opencode_server` | Launch `opencode serve` with config, manage process lifecycle |
| `_ensure_server_running` | Health check + restart if crashed |
| `_create_session` | `POST /session` → returns session_id |
| `_send_message` | `POST /session/:id/message` with prompt |
| `_stream_events` | `GET /global/event` SSE → parse → yield SDKEvent |
| `_inject_system_prompt` | Write AGENTS.md or update config with instructions |
| `_setup_mcp_servers` | Configure custom tools as local MCP servers in opencode.json |

**Session management:**
```python
async def send_message_stream(self, message, session_id=None, ...):
    await self._ensure_server_running()

    # Create or resume session
    if not session_id:
        session_data = await self._create_session()
        session_id = session_data["id"]
        yield SDKEvent(type=SDKEventType.SESSION_CREATED, session_id=session_id)

    # Inject system prompt via AGENTS.md
    system_prompt = system_prompt or self.prompt_generator.generate_prompt(mode)
    self._write_agents_md(system_prompt)

    # Send message
    response = await self._post_message(session_id, message)

    # Stream events from SSE
    async for event in self._stream_sse_events():
        yield self._convert_to_sdk_event(event, session_id)
```

**Event mapping:**

| OpenCode Event | SDKEvent Type | Notes |
|---|---|---|
| Session created | `SESSION_CREATED` | From POST /session response |
| Text content | `ASSISTANT` | Assistant text response |
| Tool call (bash, read, etc.) | `TOOL_USE` | Tool name + input |
| Tool result | `TOOL_RESULT` | Tool output |
| Completion | `DONE` | End of response |
| Error | `ERROR` | Error details |

#### 5. Custom Tools Integration

Our platform's custom tools (knowledge query, create agent task, etc.) need to be available to OpenCode. Two approaches:

**Option A: Local MCP servers (recommended)**
- Write each custom tool as a small MCP server (stdio)
- Configure in the generated `opencode.json`:
```json
{
  "mcp": {
    "knowledge": {
      "type": "local",
      "command": ["python", "/app/core/server/tools/mcp_bridge/knowledge_server.py"],
      "enabled": true
    },
    "task": {
      "type": "local",
      "command": ["python", "/app/core/server/tools/mcp_bridge/task_server.py"],
      "enabled": true
    }
  }
}
```
- This reuses the exact same tool implementations we already have
- OpenCode natively supports MCP servers and auto-discovers their tools
- Permissions set to "allow" for these tools

**Option B: Custom tool files**
- Write TypeScript wrapper files in `.opencode/tools/` that call our Python tool implementations
- More complex, less maintainable

**Recommendation: Option A** — MCP bridge servers are the cleanest path because:
1. We already define tools with MCP-compatible schemas (via `create_sdk_mcp_server`)
2. OpenCode has native MCP support
3. Same tool code runs for both Claude Code and OpenCode adapters
4. Tool permissions managed uniformly

**MCP bridge implementation:**
Create lightweight Python scripts that wrap existing tool functions as stdio MCP servers:
```
/app/core/server/tools/mcp_bridge/
├── knowledge_server.py    # Wraps knowledge_query tool
├── task_server.py         # Wraps create_agent_task, respond_to_task, update_session_state
└── collaboration_server.py # Wraps create_collaboration, post_finding, get_collaboration_status
```

These use the `mcp` Python package (already available) to expose the same tool functions over stdio.

#### 6. Plugin Support

OpenCode supports plugins defined in `opencode.json`. Our platform's agent plugins can be mapped:

```json
{
  "mcp": {
    "plugin_my_plugin": {
      "type": "local",
      "command": ["python", "/app/workspace/plugins/my_plugin/server.py"],
      "enabled": true
    }
  }
}
```

This mirrors how Claude Code adapter loads plugins via `options.plugins`.

#### 7. Frontend Changes

**`frontend/src/components/Environments/AddEnvironment.tsx` — Major Refactor:**

Replace the current flat SDK dropdowns with the three-step cascading selection described in the UX section above. Key changes:

```typescript
// NEW: SDK engine options (no longer coupled to credential type)
const SDK_ENGINE_OPTIONS = [
  { value: "claude-code", label: "Claude Code", description: "Anthropic's CLI agent SDK" },
  { value: "opencode", label: "OpenCode", description: "Multi-provider open-source agent" },
  { value: "google-adk-wr", label: "Google ADK", description: "Google Agent Development Kit" },
]

// NEW: Compatibility matrix for filtering credentials
const SDK_CREDENTIAL_COMPATIBILITY: Record<string, string[]> = {
  "claude-code": ["anthropic", "minimax"],
  "opencode": ["anthropic", "openai", "openai_compatible", "google", "bedrock", "azure"],
  "google-adk-wr": ["openai_compatible", "google", "vertex"],
}

// NEW: Suggested models per credential type (for model override dropdown)
const SUGGESTED_MODELS: Record<string, string[]> = {
  anthropic: ["claude-opus-4", "claude-sonnet-4-5", "claude-haiku-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash"],
  openai_compatible: [],  // user types custom model name
}
```

**New component state (per mode):**
```typescript
// Building mode
const [sdkEngineBuilding, setSdkEngineBuilding] = useState("claude-code")
const [buildingCredentialId, setBuildingCredentialId] = useState<string | null>(null)
const [modelOverrideBuilding, setModelOverrideBuilding] = useState("")

// Conversation mode
const [sdkEngineConversation, setSdkEngineConversation] = useState("claude-code")
const [conversationCredentialId, setConversationCredentialId] = useState<string | null>(null)
const [modelOverrideConversation, setModelOverrideConversation] = useState("")
```

**Cascading behavior:**
- When SDK engine changes → reset credential selection → clear model override
- Credential dropdown filters by `SDK_CREDENTIAL_COMPATIBILITY[selectedEngine]`
- Model override shows `SUGGESTED_MODELS[selectedCredentialType]` as suggestions + free text

**`frontend/src/components/Environments/EnvironmentCard.tsx`:**
- Show SDK engine badge + credential name + model override (if set)
- e.g., "OpenCode · My OpenAI Key · gpt-4o-mini" instead of just "OpenCode + OpenAI"

**`frontend/src/components/UserSettings/AICredentials.tsx`:**
- Add new credential types: `openai`, `google`, `bedrock`, `azure`
- Each type has its own required fields (API key, optional base URL, etc.)

---

## Feature Parity Matrix

| Feature | Claude Code Adapter | Google ADK Adapter | OpenCode Adapter (Proposed) |
|---|---|---|---|
| **Text streaming** | Yes (via SDK messages) | Yes (via ADK events) | Yes (via SSE events) |
| **Tool calls** | Built-in (Read, Write, Bash, etc.) | Custom (Bash, Read only) | Built-in (read, write, edit, bash, grep, glob, etc.) |
| **Session persistence** | SDK-managed (SQLite) | SQLite session service | Server-managed (internal) |
| **Session resumption** | `options.resume = session_id` | SQLite lookup | `POST /session/:id/message` |
| **System prompt** | `options.system_prompt` | Agent `instruction` | `AGENTS.md` file |
| **Custom tools (MCP)** | `create_sdk_mcp_server()` | N/A (function tools) | `opencode.json` → `mcp` config |
| **Custom tools (native)** | N/A | `FunctionTool` | `.opencode/tools/` TypeScript files |
| **Plugins** | `options.plugins` | N/A | `opencode.json` → `mcp` or `plugin` |
| **Model selection** | `options.model` | `LiteLlm(model=...)` | `opencode.json` → `model` field |
| **Permission mode** | `options.permission_mode` | N/A | `opencode.json` → `permission` |
| **Interrupt** | `client.interrupt()` | `task.cancel()` | Delete session or signal |
| **Multi-provider** | Anthropic, MiniMax | OpenAI-compatible, Gemini, Vertex | 75+ providers |
| **Thinking/reasoning** | ThinkingBlock events | N/A | TBD (if provider supports) |
| **Tool approval** | Pre-allowed tools list | N/A | `permission` config |
| **Credential security** | Env var (`ANTHROPIC_API_KEY`) | Env vars + settings file | `auth.json` + server password |

---

## Key Considerations

### 1. Process Management
- OpenCode server runs as a **long-lived subprocess** inside the container
- Need process supervision: health checks, auto-restart on crash
- Server startup adds ~1-2s latency on first message
- Consider starting the server at container boot (in entrypoint script)

### 2. Per-Mode Configuration
- OpenCode has a single model config, but we need different models per mode (building vs. conversation)
- Now solved by the **model override** field — each mode can specify its own model
- **Solution:** Dynamically update config via `PATCH /config` before each message with the mode-specific model
- The adapter reads `model_override_building` / `model_override_conversation` from environment config and applies before each message

### 3. System Prompt Injection
- Claude Code: passed directly as `options.system_prompt`
- OpenCode: written to `AGENTS.md` file OR passed via `instructions` config
- For dynamic per-request prompts, write `AGENTS.md` before each message send
- Concern: file I/O on every message vs. API-level prompt injection
- **Mitigation:** OpenCode config also supports `instructions` pointing to files — pre-write the prompt files and reference them

### 4. Event Stream Parsing
- OpenCode uses SSE (`GET /global/event`) for real-time events
- Events include session updates, message content, tool calls
- Need to map OpenCode's event schema to our SDKEvent format
- The server's OpenAPI spec (at `/doc`) documents exact event types

### 5. Security
- OpenCode server listens on localhost only (not exposed outside container)
- Credentials in `auth.json` — file permissions should be restrictive
- `OPENCODE_SERVER_PASSWORD` adds an extra auth layer (optional in our container since it's isolated)
- Credential access interception (same as ADK adapter): intercept tool calls targeting credential files

### 6. Container Size
- OpenCode is a single Go binary (~50-100MB)
- No additional runtime dependencies (Go is statically compiled)
- Adds to Docker image size but reasonable for the capability added

### 7. AI Credential Types — Expanded
With the new SDK ↔ Credential decoupling, we need more credential types:

| Credential Type | Required Fields | Used By SDKs |
|---|---|---|
| `anthropic` | `api_key` | Claude Code, OpenCode |
| `minimax` | `api_key` | Claude Code |
| `openai` | `api_key` | OpenCode |
| `openai_compatible` | `api_key`, `base_url`, `model` | Google ADK, OpenCode |
| `google` | `api_key` | OpenCode, Google ADK |
| `bedrock` | `access_key`, `secret_key`, `region` | OpenCode |
| `azure` | `api_key`, `resource_name` | OpenCode |

- All stored in existing encrypted JSON blob per named credential (no migration needed for adding fields)
- New credential types need corresponding `AICredential.type` enum values
- Each credential maps to provider-specific auth config in the SDK adapter

### 8. Backward Compatibility
- Existing environments with `agent_sdk_conversation = "claude-code/anthropic"` continue working unchanged
- The adapter registry still accepts full `engine/provider` IDs for backward compat
- New environments use engine-only IDs + credential link + optional model override
- Migration path: no migration needed; old format and new format coexist

---

## Implementation Phases

### Phase 1: UX Refactor — SDK ↔ Credential ↔ Model Decoupling
1. Add `model_override_conversation` and `model_override_building` fields to `AgentEnvironment` model + migration
2. Add `SDK_CREDENTIAL_COMPATIBILITY` constant to backend (shared validation)
3. Refactor `AddEnvironment.tsx`: three-step cascading selection (SDK Engine → Credential → Model Override)
4. Update `EnvironmentCard.tsx` to show engine + credential + model
5. Update backend `create_environment()` to validate SDK ↔ credential compatibility
6. Pass model override through to adapters (Claude Code: `options.model`, Google ADK: `LiteLlm(model=...)`)
7. Backward compat: existing `"claude-code/anthropic"` IDs keep working

### Phase 2: New Credential Types
1. Add new credential types to AI Credentials system: `openai`, `google`, `bedrock`, `azure`
2. Update `AICredentials.tsx` settings page with new credential type forms
3. Update backend credential validation for new types
4. Test credential filtering in AddEnvironment with new types

### Phase 3: OpenCode Adapter (MVP)
1. Install OpenCode binary in Docker image (Dockerfile change)
2. Add `_generate_opencode_config_files()` to environment lifecycle
3. Implement `OpenCodeAdapter` with basic send/receive (text + tool events)
4. Process management: start/health-check/restart `opencode serve`
5. Config generation: `opencode.json`, `auth.json`, `AGENTS.md` from credential + model override
6. Dynamic model switching via `PATCH /config` per mode

### Phase 4: OpenCode Full Features
1. Implement custom tools via MCP bridge servers (knowledge, task, collaboration)
2. Plugin support mapping to OpenCode MCP config
3. Session resumption via `POST /session/:id/message`
4. Interrupt support
5. Tool approval integration via `permission` config
6. Testing across providers (Anthropic, OpenAI, OpenAI-compatible)

### Phase 5: Advanced Providers & Polish
1. Bedrock and Azure credential types + OpenCode adapter support
2. Local model support (Ollama) via OpenCode
3. EnvironmentCard badges for all new combinations
4. Documentation and user guides
5. End-to-end testing: build agent with Claude Code Opus → run conversations with OpenCode + GPT-4o-mini

---

## Open Questions

1. **SDK ID format migration:** Should we migrate existing environments from `"claude-code/anthropic"` to `"claude-code"` + credential link, or keep both formats forever? Dual-format support is simpler but adds complexity to every place that reads SDK IDs.
2. **System prompt updates:** Is writing `AGENTS.md` on every message acceptable, or should we explore the `/session/:id/init` endpoint for prompt injection?
3. **Session lifecycle:** OpenCode manages sessions internally — should we map session IDs 1:1, or maintain a separate mapping?
4. **Tool result rendering:** OpenCode's tool output format may differ from Claude Code's — do we need frontend changes for tool result display?
5. **Version pinning:** Should we pin OpenCode to a specific version in the Dockerfile, or use latest?
6. **Model override validation:** Should we validate model names against a known list per provider, or accept any string (more flexible but error-prone)?
7. **"Same as building" shortcut:** Should the conversation mode default to mirroring the building mode selections, or always start empty? Current UX pre-fills both from user defaults.
8. **Credential type expansion pace:** Do we add all credential types (openai, google, bedrock, azure) in Phase 2, or start with just `openai` and expand incrementally?

---

*Draft created: 2026-03-21*
