# Tools Approval Management

## Overview

Agent environments use the Claude SDK which requires explicit tool permissions. When plugins introduce new tools (e.g., MCP servers), the agent pauses execution waiting for user approval. This creates friction in the user experience.

The tools approval system provides:
- **Pre-allowed tools**: Core tools always permitted (Read, Write, Bash, etc.)
- **User-approved tools**: Plugin tools explicitly approved by the user
- **Persistent approvals**: Once approved, tools remain allowed across sessions

## Problem Statement

When a plugin provides MCP tools, the agent may pause mid-execution:

```
Using tool: mcp__plugin_context7__resolve-library-id
I need permission to use the Context7 tool to fetch documentation.
```

This disrupts workflow continuity and requires manual intervention for each new tool.

## Core Concepts

### Two-Tier Tool Authorization

**Pre-Allowed Tools** (no approval required)
- Core SDK tools: Read, Edit, Glob, Grep, Bash, Write, WebFetch, WebSearch, TodoWrite
- Custom tools added per mode: knowledge query (building), agent handover (conversation)
- Hardcoded in `sdk_manager.py`, always included in SDK options

**User-Approved Tools** (require explicit approval)
- Tools from installed plugins (MCP servers, custom commands)
- Stored in `agent_sdk_config.allowed_tools` on the agent model
- Synced to agent-env via `settings.json`

### Approval Persistence

Approved tools are stored at the agent level, not session level:
- Approvals persist across sessions
- Shared between conversation and building modes
- Synced to all running/suspended environments

### Settings.json Integration

Tool approvals are synced alongside plugin settings:
- Same sync mechanism as plugin configuration
- `settings.json` contains both `active_plugins` and `allowed_tools`
- Agent-env reads settings on each SDK session initialization

## Data Flow

```
1. User installs plugin → Plugin provides new tools
2. Agent uses tool → SDK pauses for approval (if not in allowed_tools)
3. User clicks "Approve Tools" → Backend updates agent_sdk_config.allowed_tools
4. Backend syncs settings.json to agent-env → Includes updated allowed_tools
5. Next SDK session → Reads allowed_tools from settings.json
6. SDK initialized with merged tools → Pre-allowed + user-approved
```

### Sync on Approval

When user approves tools:
1. API updates `agent.agent_sdk_config.allowed_tools`
2. Triggers `sync_allowed_tools_to_environment()`
3. Sends updated `settings.json` to running agent-env
4. No plugin file re-sync needed (only settings update)

## Database Model

**File**: `backend/app/models/agent.py`

### Agent.agent_sdk_config

JSON field storing SDK configuration for the agent.

| Key | Type | Purpose |
|-----|------|---------|
| `sdk_tools` | `list[str]` | All tools discovered from agent-env (for tracking) |
| `allowed_tools` | `list[str]` | Tools approved by user for automatic permission |

### AgentSdkConfig Schema

**File**: `backend/app/models/agent.py`

| Field | Purpose |
|-------|---------|
| `sdk_tools` | Read-only list of discovered tools |
| `allowed_tools` | User-approved tools list |

## Backend Service

**File**: `backend/app/services/agent_service.py`

### SDK Config Methods

| Method | Purpose |
|--------|---------|
| `get_sdk_config()` | Returns current AgentSdkConfig for agent |
| `add_allowed_tools()` | Adds tools to allowed_tools (no duplicates) |
| `get_pending_tools()` | Returns sdk_tools - allowed_tools (needs approval) |
| `update_sdk_tools()` | Incrementally updates discovered sdk_tools |
| `sync_allowed_tools_to_environment()` | Syncs settings.json to active environment |

### Plugin Service Integration

**File**: `backend/app/services/llm_plugin_service.py`

Method `prepare_plugins_for_environment()`:
- Accepts optional `allowed_tools` parameter
- Includes `allowed_tools` in returned `settings_json`
- Used during environment sync and tool approval sync

### Environment Lifecycle

**File**: `backend/app/services/environment_lifecycle.py`

Method `_sync_plugins_to_environment()`:
- Reads `agent.agent_sdk_config.allowed_tools`
- Passes to `prepare_plugins_for_environment()`
- Syncs complete settings.json including allowed_tools

## Agent-Env Integration

### Settings Reader

**File**: `backend/app/env-templates/python-env-advanced/app/core/server/agent_env_service.py`

| Method | Purpose |
|--------|---------|
| `get_plugins_settings()` | Returns full settings.json content |
| `get_allowed_tools()` | Returns `allowed_tools` array from settings |

### SDK Manager

**File**: `backend/app/env-templates/python-env-advanced/app/core/server/sdk_manager.py`

In `send_message_stream()`:
1. Defines pre-allowed tools list (hardcoded)
2. Calls `agent_env_service.get_allowed_tools()` for user approvals
3. Merges both lists (no duplicates)
4. Passes merged list to `ClaudeAgentOptions(allowed_tools=...)`

### Workspace Structure

```
/app/workspace/plugins/
└── settings.json
```

**settings.json format**:
```json
{
  "active_plugins": [...],
  "allowed_tools": ["mcp__plugin_context7__resolve-library-id", ...]
}
```

## API Routes

**File**: `backend/app/api/routes/agents.py`

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/agents/{id}/sdk-config` | GET | Get current SDK config |
| `/agents/{id}/allowed-tools` | PATCH | Add tools to allowed list, sync to env |
| `/agents/{id}/pending-tools` | GET | Get tools needing approval |

### Request/Response Models

**AllowedToolsUpdate** (request):
- `tools: list[str]` - Tool names to approve

**AgentSdkConfig** (response):
- `sdk_tools: list[str]` - All discovered tools
- `allowed_tools: list[str]` - Approved tools

**PendingToolsResponse** (response):
- `pending_tools: list[str]` - Tools needing approval

## Message-Level Tool Approval Display

### Problem: Stale Approval Status on Page Reload

When a message is created, `tools_needing_approval` is stored in message metadata based on the agent's `allowed_tools` at that moment. If the user approves tools and then reloads the page, the stored metadata would still show tools as needing approval (stale data).

### Solution: Backend Filtering at Query Time

**File**: `backend/app/api/routes/messages.py`

The `get_messages` endpoint filters `tools_needing_approval` against the agent's current `allowed_tools` before returning messages:

1. Fetches messages via `MessageService.get_session_messages()`
2. Retrieves agent's current `allowed_tools` from `agent.agent_sdk_config`
3. For each message with `tools_needing_approval` metadata, removes tools that are now in `allowed_tools`
4. Returns filtered messages (no database writes, response-only modification)

This ensures:
- Approval button only shows for genuinely unapproved tools
- Page reload doesn't show stale approval requests
- No database writes needed (filtering is response-only)

### Data Flow for Tool Approval Display

```
1. Message created → tools_needing_approval stored in metadata (snapshot)
2. User approves tools → agent.agent_sdk_config.allowed_tools updated
3. Page reload → GET /sessions/{id}/messages called
4. Backend filters tools_needing_approval against current allowed_tools
5. Frontend receives filtered list → Shows button only if tools remain
```

## Frontend Components

### Tool Approval Hook

**File**: `frontend/src/hooks/useToolApproval.ts`

Manages approval state and API calls for tool approval actions. Reads `tools_needing_approval` from message metadata (already filtered by backend).

### Message Components

**File**: `frontend/src/components/Chat/MessageBubble.tsx`

Detects tool messages requiring approval and shows action button.

**File**: `frontend/src/components/Chat/MessageActions.tsx`

Renders "Approve Tools" action with loading state.

## Implementation References

### Backend

| File | Purpose |
|------|---------|
| `backend/app/models/agent.py` | `agent_sdk_config` field, AgentSdkConfig schema |
| `backend/app/services/agent_service.py` | SDK config methods, sync to environment |
| `backend/app/services/message_service.py` | Stores `tools_needing_approval` in message metadata during streaming |
| `backend/app/services/llm_plugin_service.py` | `prepare_plugins_for_environment()` with allowed_tools |
| `backend/app/services/environment_lifecycle.py` | `_sync_plugins_to_environment()` |
| `backend/app/api/routes/agents.py` | Tool management API endpoints |
| `backend/app/api/routes/messages.py` | Filters `tools_needing_approval` against `allowed_tools` on fetch |

### Agent-Env

| File | Purpose |
|------|---------|
| `backend/app/env-templates/.../agent_env_service.py` | `get_allowed_tools()` |
| `backend/app/env-templates/.../sdk_manager.py` | Merge pre-allowed + user-approved tools |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/hooks/useToolApproval.ts` | Approval state management |
| `frontend/src/components/Chat/MessageBubble.tsx` | Tool approval detection |
| `frontend/src/components/Chat/MessageActions.tsx` | Approval action button |

## Similar Patterns

### Plugin Sync

Tool approval sync follows the same pattern as plugin sync:
1. Backend updates agent record
2. Calls `prepare_plugins_for_environment()` with relevant data
3. Adapter sends `set_plugins()` to agent-env
4. Agent-env updates `settings.json`
5. SDK reads settings on next session

See: `docs/agent-sessions/agent_plugins_management.md`

### Credentials Sync

Same HTTP adapter pattern for syncing configuration to running environments.

See: `docs/agent-sessions/agent_env_credentials_management.md`

## Benefits

1. **Reduced Friction**: Pre-approved tools don't interrupt execution
2. **Persistent Approvals**: One-time approval per tool, not per session
3. **Unified Settings**: Tools and plugins share same sync mechanism
4. **Environment Consistency**: Approvals synced to all environments
5. **Security**: Explicit user consent for plugin tool access
6. **Visibility**: UI shows which tools are pending vs approved

## Future Considerations

1. **Bulk Approval**: Approve all pending tools at once
2. **Tool Categories**: Group tools by plugin source
3. **Tool Revocation**: Remove previously approved tools
4. **Auto-Approval Rules**: Patterns for trusting specific plugins
5. **Audit Log**: Track approval history for compliance

---

**Last Updated**: 2026-01-12
