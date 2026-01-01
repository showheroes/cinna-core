# Agent Solutions Knowledge Tool

## Business Logic & Use Case

Agents running in isolated Docker environments need access to integration knowledge when building custom solutions. This implements a **reverse API call pattern** where agent environments call back to the main backend to query integration knowledge.

**Benefits**:
- Centralized knowledge management (stays in backend, not duplicated)
- User-specific access based on environment ownership
- Secure authentication using environment token

**Flow**:
```
Agent (building mode) → uses query_integration_knowledge tool
    → Agent-Env makes authenticated HTTP call to backend
    → Backend validates environment ID + token
    → Returns integration guidance (currently stub: "write it in python")
    → Agent uses knowledge to build integration
```

## Architecture

```
┌──────────────────────────────────────────────┐
│         Backend (FastAPI)                    │
│  POST /api/v1/knowledge/query                │
│  - Validates Authorization + X-Agent-Env-Id  │
│  - Queries database for AgentEnvironment     │
│  - Verifies token matches config.auth_token  │
│  - Returns stub: "write it in python"        │
└────────────────▲─────────────────────────────┘
                 │
                 │ HTTP POST with headers:
                 │   Authorization: Bearer <token>
                 │   X-Agent-Env-Id: <uuid>
                 │
┌────────────────┴─────────────────────────────┐
│    Agent Environment (Docker Container)      │
│  Custom Tool: query_integration_knowledge    │
│  - Reads BACKEND_URL, AGENT_AUTH_TOKEN,      │
│    ENV_ID from environment variables         │
│  - Makes async HTTP request                  │
│  - Returns formatted response                │
│                                               │
│  SDK Manager (Building Mode Only)            │
│  - Creates MCP server with custom tool       │
│  - Registers as mcp__knowledge__*            │
└───────────────────────────────────────────────┘
```

### Security Model

**Two-Factor Authentication**:
1. **Bearer Token** - `AGENT_AUTH_TOKEN` (in Authorization header)
2. **Environment ID** - `ENV_ID` (in X-Agent-Env-Id header)

Backend validates both match database record, preventing token reuse across environments.

## Implementation

### Backend Components

**File**: `backend/app/api/routes/knowledge.py`

**Key Functions**:
- `verify_agent_auth_token(session, authorization, x_agent_env_id)` - Dependency
  - Parses headers, validates UUID format
  - Queries `AgentEnvironment` from database
  - Compares stored token with provided token
  - Returns environment object or raises 401
  - Logs all authentication attempts

- `query_knowledge(request, environment)` - Endpoint
  - Route: `POST /api/v1/knowledge/query`
  - Currently returns stub: `{"content": "write it in python", "source": "stub"}`
  - Environment object available for future user-based permissions

**Registration**: Added to `backend/app/api/main.py`

**Environment Config**: `backend/app/services/environment_lifecycle.py`
- Method `_generate_env_file()` adds `BACKEND_URL=http://backend:8000`
- Uses Docker network service name for container-to-container communication

### Agent-Env Components

**File**: `backend/app/env-templates/python-env-advanced/app/core/server/tools/knowledge_query.py`

**Tool Function**: `query_integration_knowledge(args)`
- Decorated with `@tool()` from claude-agent-sdk
- Reads environment variables: `BACKEND_URL`, `AGENT_AUTH_TOKEN`, `ENV_ID`
- Makes HTTP POST with both headers
- Handles errors: timeout, connection, authentication
- Returns Claude SDK tool response format

**File**: `backend/app/env-templates/python-env-advanced/app/core/server/sdk_manager.py`

**Method**: `send_message_stream()` (around line 96-116)

**Logic**:
- Checks if `mode == "building"`
- Imports tool: `from .tools.knowledge_query import query_integration_knowledge`
- Creates MCP server: `create_sdk_mcp_server(name="knowledge", tools=[...])`
- Adds to `options.mcp_servers` and `options.allowed_tools`
- Tool becomes: `mcp__knowledge__query_integration_knowledge`
- Graceful error handling if import fails

**Note**: Tool is **only available in building mode**, not conversation mode.

## Environment Variables

**Agent-Env Container** (set in `.env` file):
- `BACKEND_URL` - Backend API URL (http://backend:8000)
- `AGENT_AUTH_TOKEN` - Authentication token (generated at env creation)
- `ENV_ID` - Environment UUID
- `ANTHROPIC_API_KEY` - For Claude SDK
- `CLAUDE_CODE_WORKSPACE` - /app/app

## Security Validation Flow

```
1. Request arrives with headers:
   Authorization: Bearer <token>
   X-Agent-Env-Id: <env_uuid>

2. verify_agent_auth_token() dependency:
   - Parse headers (validate format)
   - Parse UUID from X-Agent-Env-Id
   - Query: SELECT * FROM agent_environments WHERE id = <env_uuid>
   - If not found → 401 "Invalid environment ID"
   - Get stored_token = environment.config["auth_token"]
   - Compare: stored_token == <token>
   - If mismatch → 401 "Invalid authentication token"
   - If match → return AgentEnvironment object

3. query_knowledge() receives validated environment
```

## Testing

**Manual Test**:
1. Create or rebuild environment (to get BACKEND_URL env var)
2. Start session with `mode: "building"`
3. Agent can use tool: `query_integration_knowledge({"query": "odoo api integration"})`
4. Response: "Knowledge Query Result:\n\nwrite it in python\n\n(Source: stub)"

**Verify Logs**:
- Backend: `"Knowledge query from environment {env_id}: ..."`
- Agent-Env: `"Querying knowledge base from env {env_id}: ..."`

**Test Authentication**:
- Invalid token → 401 "Invalid authentication token"
- Invalid env ID → 401 "Invalid environment ID"
- Missing headers → 401 "Missing X-Agent-Env-Id header"

## File Reference

**Backend (New/Modified)**:
- `backend/app/api/routes/knowledge.py` - NEW - Knowledge API endpoint
- `backend/app/api/main.py` - MODIFIED - Added knowledge router
- `backend/app/services/environment_lifecycle.py` - MODIFIED - Added BACKEND_URL to env vars
- `backend/app/env-templates/python-env-advanced/.env.template` - MODIFIED - Documented BACKEND_URL

**Agent-Env (New/Modified)**:
- `backend/app/env-templates/python-env-advanced/app/core/server/tools/__init__.py` - NEW
- `backend/app/env-templates/python-env-advanced/app/core/server/tools/knowledge_query.py` - NEW - Tool implementation
- `backend/app/env-templates/python-env-advanced/app/core/server/sdk_manager.py` - MODIFIED - Tool loading logic

## Troubleshooting

**Tool not available**:
- Check session is in building mode (not conversation)
- Rebuild environment to get latest SDK manager
- Check agent-env logs for tool import errors

**Authentication failures**:
- Verify `ENV_ID` matches database ID
- Verify `AGENT_AUTH_TOKEN` matches `environment.config["auth_token"]`
- Check backend logs for specific auth failure reason

**Connection errors**:
- Verify agent container on `agent-bridge` network
- Check backend is running: `docker ps | grep backend`
- Test connectivity: `docker exec <container> curl http://backend:8000/health`

## Next Steps for Implementation

**Knowledge Database** (not yet implemented):
- Create `IntegrationKnowledge` model with topic/content/user_id
- Create `KnowledgeService.search_knowledge(query, user_id)` method
- Update `query_knowledge()` endpoint to query database instead of returning stub
- Filter by user ownership via `environment.agent_id → agent.owner_id`

**Current State**: Stub returns "write it in python" for all queries.
