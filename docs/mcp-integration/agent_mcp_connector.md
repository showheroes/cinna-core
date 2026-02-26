# Agent MCP Connector - Implementation Reference

## Purpose

Enable agent owners to expose their agents as MCP (Model Context Protocol) servers, allowing external MCP clients (Claude Desktop, Cursor) to connect, authenticate via OAuth 2.1, and interact with the agent through a `send_message` tool.

## Feature Overview

- Agent owner creates named MCP connectors with mode (conversation/building) and email ACL
- Each connector gets a unique MCP server URL: `{MCP_SERVER_BASE_URL}/{connector_id}/mcp`
- External MCP clients discover the shared OAuth Authorization Server via standard metadata endpoints
- Dynamic Client Registration (RFC 7591) allows MCP clients to register automatically
- OAuth 2.1 authorization flow with PKCE and frontend consent page
- Authenticated MCP clients call `send_message` tool to interact with the agent
- Per-connector session mapping maintains conversation continuity
- Sequential message processing with per-session locking

## Architecture

```
MCP Client (Claude Desktop / Cursor)
        │
        ├─ Discovery: GET /.well-known/oauth-authorization-server
        ├─ DCR: POST /mcp/oauth/register
        ├─ Authorize: GET /mcp/oauth/authorize → redirect to consent page
        ├─ Token: POST /mcp/oauth/token
        │
        └─ Tool call: POST /mcp/{connector_id}/mcp (send_message)
                │
                ▼
        MCPServerRegistry (ASGI dispatcher)
                │
                ├─ Extract connector_id from path
                ├─ Lazy-create per-connector FastMCP server
                ├─ MCPTokenVerifier validates bearer token
                │
                └─ send_message tool handler
                        │
                        ├─ Get/create platform session (linked to connector)
                        └─ Stream response from agent environment
```

**Key Concepts:**
- **MCP Connector**: A named configuration linking an agent to an MCP server endpoint
- **Shared OAuth AS**: Single authorization server at `/mcp/oauth/` serving all connectors
- **MCPServerRegistry**: ASGI dispatcher that routes requests to per-connector FastMCP instances
- **MCPTokenVerifier**: Validates bearer tokens per-connector (checks expiry, revocation, connector match)

## Data/State Lifecycle

### Connector Modes

| Mode | Description |
|------|-------------|
| `conversation` | Chat interactions with the agent |
| `building` | Development/builder tasks |

### Email Access Control

| Configuration | Who Can Authorize |
|---------------|-------------------|
| `allowed_emails = []` | Owner only |
| `allowed_emails = ["a@b.com"]` | Owner + listed emails |

### OAuth Token Lifecycle

| Token Type | Expiry | Storage |
|------------|--------|---------|
| Access token | 1 hour | `mcp_token` table, opaque string |
| Refresh token | 30 days | `mcp_token` table, opaque string |
| Auth code | 5 minutes | `mcp_auth_code` table |
| Auth request (nonce) | 10 minutes | `mcp_auth_request` table |

## Database Schema

### Migration

`backend/app/alembic/versions/dc259404533e_add_mcp_integration_tables.py`

### Table: `mcp_connector`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | Connector identifier |
| `agent_id` | UUID, FK → agent.id (CASCADE) | Linked agent |
| `owner_id` | UUID, FK → user.id (CASCADE) | Connector owner |
| `name` | VARCHAR(255) | Display name |
| `mode` | VARCHAR | "conversation" or "building" |
| `is_active` | BOOLEAN | Whether connector accepts connections |
| `allowed_emails` | JSON | Email ACL list (empty = owner only) |
| `max_clients` | INTEGER | Maximum DCR registrations (default 10) |
| `created_at`, `updated_at` | DATETIME | Timestamps |

**Models:** `backend/app/models/mcp_connector.py`
- `MCPConnector` (table model)
- `MCPConnectorCreate`, `MCPConnectorUpdate` (input schemas)
- `MCPConnectorPublic`, `MCPConnectorsPublic` (response schemas)
- `MCPConnectorPublic` includes computed `mcp_server_url` field
- `MCPConnectorsPublic` includes `mcp_server_base_url` (current env value, used by frontend to construct URLs dynamically)

### Table: `mcp_oauth_client`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | Internal ID |
| `client_id` | VARCHAR, unique, indexed | OAuth client identifier |
| `client_secret_hash` | VARCHAR | SHA256 hash of client secret |
| `client_name` | VARCHAR | Client display name |
| `redirect_uris` | JSON | Allowed redirect URIs |
| `grant_types` | JSON | Supported grants (default: authorization_code, refresh_token) |
| `response_types` | JSON | Supported responses (default: code) |
| `connector_id` | UUID, FK → mcp_connector.id (CASCADE) | Parent connector |
| `created_at` | DATETIME | Registration timestamp |

**Models:** `backend/app/models/mcp_oauth_client.py`
- `MCPOAuthClient` (table model)
- `MCPOAuthClientPublic` (response schema)

### Table: `mcp_auth_code`

| Column | Type | Description |
|--------|------|-------------|
| `code` | VARCHAR, PK | Authorization code (token_urlsafe 48) |
| `client_id` | VARCHAR, indexed | OAuth client |
| `user_id` | UUID, FK → user.id (CASCADE) | Authorizing user |
| `connector_id` | UUID, FK → mcp_connector.id (CASCADE) | Target connector |
| `redirect_uri` | VARCHAR | Client callback URL |
| `code_challenge` | VARCHAR | PKCE challenge |
| `scope` | VARCHAR | Requested scopes |
| `resource` | VARCHAR | MCP resource URL |
| `expires_at` | DATETIME | Code expiry (5 min) |
| `used` | BOOLEAN | Whether code has been exchanged |
| `created_at` | DATETIME | Timestamp |

### Table: `mcp_auth_request`

| Column | Type | Description |
|--------|------|-------------|
| `nonce` | VARCHAR, PK | Random nonce for consent page lookup |
| `connector_id` | UUID, FK → mcp_connector.id (CASCADE) | Target connector |
| `client_id` | VARCHAR | OAuth client |
| `redirect_uri` | VARCHAR | Client callback URL |
| `code_challenge` | VARCHAR | PKCE challenge |
| `code_challenge_method` | VARCHAR | "S256" |
| `scope` | VARCHAR | Requested scopes |
| `state` | VARCHAR | OAuth state parameter |
| `resource` | VARCHAR | MCP resource URL |
| `expires_at` | DATETIME | Request expiry (10 min) |
| `used` | BOOLEAN | Whether request was approved |
| `created_at` | DATETIME | Timestamp |

**Models:** `backend/app/models/mcp_auth_code.py`
- `MCPAuthCode` (table model)
- `MCPAuthRequest` (table model)

### Table: `mcp_token`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID, PK | Internal ID |
| `token` | VARCHAR, unique, indexed | Opaque bearer token (token_urlsafe 48) |
| `token_type` | VARCHAR | "access" or "refresh" |
| `client_id` | VARCHAR, indexed | OAuth client |
| `user_id` | UUID, FK → user.id (CASCADE) | Token owner |
| `connector_id` | UUID, FK → mcp_connector.id (CASCADE), indexed | Target connector |
| `scope` | VARCHAR | Granted scopes |
| `resource` | VARCHAR | MCP resource URL |
| `expires_at` | DATETIME | Token expiry |
| `revoked` | BOOLEAN | Revocation flag |
| `created_at` | DATETIME | Timestamp |

**Models:** `backend/app/models/mcp_token.py`
- `MCPToken` (table model)

### Session Table Updates

**File:** `backend/app/models/session.py:46-50`

Two new nullable fields added to the `session` table:
- `mcp_connector_id` (UUID, FK → mcp_connector.id, SET NULL on delete)
- `mcp_session_id` (VARCHAR, unique, nullable)

## Backend Implementation

### API Routes — Connector CRUD

**File:** `backend/app/api/routes/mcp_connectors.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/agents/{agent_id}/mcp-connectors` | Create connector |
| `GET` | `/api/v1/agents/{agent_id}/mcp-connectors` | List connectors for agent |
| `GET` | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Get connector detail |
| `PUT` | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Update connector |
| `DELETE` | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Delete connector |

**Router Registration:** `backend/app/api/main.py` (tag: `mcp-connectors`)

**Ownership Enforcement:** All operations verify the current user owns the agent via `_check_agent_owner()`.

### API Routes — OAuth Consent

**File:** `backend/app/api/routes/mcp_consent.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/mcp/consent/{nonce}` | Fetch auth request details (public, no auth) |
| `POST` | `/api/v1/mcp/consent/{nonce}/approve` | Approve consent (requires JWT auth) |

**Router Registration:** `backend/app/api/main.py` (tag: `mcp-consent`)

**Consent Info Response (`ConsentInfo`):** agent name, connector name/mode, client name, scopes, expiry.

**Approval Logic:**
1. Validate nonce exists, not used, not expired
2. Check email ACL: user is connector owner OR email in `allowed_emails`
3. Mark auth request as used
4. Generate auth code (5 min expiry)
5. Return redirect URL with code + state params

### OAuth Authorization Server

**File:** `backend/app/mcp/oauth_routes.py`

Mounted at `/mcp/oauth` in `backend/app/main.py`.

| Endpoint | Purpose | Spec |
|----------|---------|------|
| `GET /.well-known/oauth-authorization-server` | AS metadata | RFC 8414 |
| `POST /register` | Dynamic Client Registration | RFC 7591 |
| `GET /authorize` | OAuth authorize (redirects to consent) | OAuth 2.1 |
| `POST /token` | Token exchange (auth code + refresh) | OAuth 2.1 |
| `POST /revoke` | Token revocation | RFC 7009 |

**AS Metadata Response:**
```json
{
  "issuer": "{MCP_SERVER_BASE_URL}/oauth",
  "authorization_endpoint": "{MCP_SERVER_BASE_URL}/oauth/authorize",
  "token_endpoint": "{MCP_SERVER_BASE_URL}/oauth/token",
  "registration_endpoint": "{MCP_SERVER_BASE_URL}/oauth/register",
  "revocation_endpoint": "{MCP_SERVER_BASE_URL}/oauth/revoke",
  "response_types_supported": ["code"],
  "grant_types_supported": ["authorization_code", "refresh_token"],
  "token_endpoint_auth_methods_supported": ["client_secret_post"],
  "code_challenge_methods_supported": ["S256"],
  "scopes_supported": ["mcp:tools", "mcp:resources"]
}
```

**DCR (`/register`):**
- Extracts `connector_id` from `resource` URL via `_extract_connector_id_from_resource()`
- Validates connector exists and is active
- Enforces `max_clients` limit (429 if exceeded)
- Generates `client_id` (UUID) + `client_secret` (48 bytes, base64url)
- Stores `client_secret` as SHA256 hash

**`/authorize`:**
- Validates `client_id` belongs to connector (from `resource`)
- Stores full request in `mcp_auth_request` (keyed by nonce, 10 min expiry)
- Redirects to `{FRONTEND_HOST}/oauth/mcp-consent?nonce={nonce}`

**`/token` — Authorization Code Grant:**
- Validates client credentials (client_secret_post)
- Looks up auth code, verifies not used/expired
- Verifies PKCE S256 (`code_verifier` vs `code_challenge`)
- Verifies `resource` matches auth code
- Generates access token (1hr) + refresh token (30d)

**`/token` — Refresh Token Grant:**
- Validates client credentials
- Verifies refresh token not revoked/expired
- Generates new access token (1hr)

**`/revoke`:**
- Marks token as `revoked=True`
- Always returns 200 per RFC 7009

### Connector Service

**File:** `backend/app/services/mcp_connector_service.py`

**Class:** `MCPConnectorService` (static methods)

**Methods:**
- `create_connector(db_session, agent_id, owner_id, data)` — Create connector
- `list_connectors(db_session, agent_id, owner_id)` — List connectors for agent/owner
- `get_connector(db_session, connector_id)` — Get by ID
- `update_connector(db_session, connector_id, owner_id, data)` — Update with ownership check; evicts MCP server if deactivated
- `delete_connector(db_session, connector_id, owner_id)` — Delete with ownership check; evicts MCP server from registry
- `check_email_access(db_session, connector_id, email)` — Check email in `allowed_emails`
- `get_registered_client_count(db_session, connector_id)` — Count registered OAuth clients
- `to_public(connector)` — Convert to public dict with computed `mcp_server_url`

### MCP Server Infrastructure

#### Token Verifier

**File:** `backend/app/mcp/token_verifier.py`

**Class:** `MCPTokenVerifier(TokenVerifier)` — implements MCP SDK `TokenVerifier` protocol

**`verify_token(token)` logic:**
1. Look up token in `mcp_token` table (type=access)
2. Check expiry
3. Check revocation
4. Verify `connector_id` matches this verifier's connector
5. Verify connector is still active
6. Return SDK `AccessToken` or `None`

#### Server Factory

**File:** `backend/app/mcp/server.py`

**`create_mcp_server_for_connector(connector_id)`:**
- Creates `FastMCP` instance with `AuthSettings` pointing to shared OAuth AS
- Attaches `MCPTokenVerifier` for the connector
- Registers `send_message` tool via `register_mcp_tools()`

#### MCPServerRegistry

**File:** `backend/app/mcp/server.py`

**Class:** `MCPServerRegistry` — ASGI dispatcher mounted at `/mcp`

**Instance:** `mcp_registry` (singleton)

**Behavior:**
- `get_or_create(connector_id)` — Lazy-creates per-connector FastMCP ASGI apps; validates connector exists and is active
- `remove(connector_id)` — Evicts cached server (called on deactivation/deletion)
- `clear()` — Clears all servers (called on app shutdown)
- `__call__(scope, receive, send)` — ASGI dispatcher: extracts `connector_id` from path, sets `mcp_connector_id_var` contextvar, delegates to per-connector app

**Context Variable:** `mcp_connector_id_var: ContextVar[str]` — set by registry, read by tool handlers

#### Mounting in FastAPI

**File:** `backend/app/main.py:208-213`

```python
# MCP OAuth routes (must be before any /mcp mount)
app.include_router(mcp_oauth_router, prefix="/mcp/oauth")

# Per-connector MCP server mount (must be after /mcp/oauth routes)
app.mount("/mcp", mcp_registry)
```

Starlette routing precedence ensures `/mcp/oauth/...` routes match before the `/mcp/...` mount.

**Lifespan:** `mcp_registry.clear()` called on shutdown.

### Tool Handlers

**File:** `backend/app/mcp/tools.py`

**`send_message` Tool:**

`handle_send_message(message, ctx)` logic:
1. Get `connector_id` from `mcp_connector_id_var` contextvar
2. Load connector, agent, and environment from DB
3. Get or create platform session:
   - Query for active session linked to `mcp_connector_id`
   - If not found → create via `SessionService.create_session()` with `integration_type="mcp"`
   - Link session to connector via `mcp_connector_id` field
4. Acquire per-session `asyncio.Lock` for sequential processing
5. Stream response via `agent_env_connector.stream_chat()`
6. Collect response parts (assistant text, tool outputs)
7. Update external session ID for multi-turn continuity
8. Return full response or error

**Message Queuing:**
- Per-session locks via `_session_locks` dict
- Returns error if lock is already held (another message in progress)

**`register_mcp_tools(server)`:** Registers `send_message` on the FastMCP instance via `@server.tool()`.

### Configuration

**File:** `backend/app/core/config.py`

| Setting | Default | Description |
|---------|---------|-------------|
| `MCP_SERVER_BASE_URL` | `""` | Base URL for MCP server endpoints (e.g., `https://tunnel.example.com/mcp`) |

## Frontend Implementation

### OAuth Consent Page

**File:** `frontend/src/routes/oauth/mcp-consent.tsx`

**Route:** `/oauth/mcp-consent` (public route, outside `_layout`)

**Flow:**
1. Reads `nonce` from query params
2. `beforeLoad`: Redirects to login if not authenticated (with return URL)
3. Fetches consent info via `GET /api/v1/mcp/consent/{nonce}`
4. Displays: agent name, connector name/mode, client name, scopes
5. "Authorize" button → `POST /api/v1/mcp/consent/{nonce}/approve` → redirects to client callback
6. "Deny" button → redirects to client callback with `error=access_denied`
7. Error states: expired nonce, already used, email not allowed

**UI:** Card layout with ShieldCheck icon, info grid, Authorize/Deny buttons.

### Connector Management Card

**File:** `frontend/src/components/Agents/McpConnectorsCard.tsx`

**Location:** Rendered in `AgentIntegrationsTab.tsx`

**Features:**
- List existing connectors with name, mode badge, active/inactive status
- Copyable MCP Server URL — constructed dynamically from `mcp_server_base_url` (returned by list endpoint) + connector ID, so URLs always reflect the current backend `MCP_SERVER_BASE_URL` env without stale cache
- Edit dialog with read-only MCP server URL, name/mode/email editing
- Create dialog: name, mode selector, allowed emails input
- Toggle active/inactive
- Delete with confirmation dialog

### State Management

**Query Keys:**
- `["mcp-connectors", agentId]` — List of connectors

**Mutations:**
- Create → invalidates connector list
- Delete → invalidates connector list
- Toggle active → invalidates connector list

### API Client

Uses direct `fetch()` calls with JWT auth headers (not auto-generated client).

**Interface:** `McpConnector` defined locally in `McpConnectorsCard.tsx`.

**Dynamic URL Construction:** The list endpoint returns `mcp_server_base_url` alongside connector data. The frontend constructs MCP server URLs as `{mcp_server_base_url}/{connector_id}/mcp` at render time via `getMcpServerUrl()`, rather than relying on the per-connector `mcp_server_url` field. This ensures URLs always reflect the current backend environment, even if React Query serves cached connector data.

## Security Features

**OAuth 2.1 Compliance:**
- PKCE S256 code challenge verification
- Client secret stored as SHA256 hash only
- Opaque bearer tokens (not JWT — no client-side decoding)
- Auth codes single-use with 5-minute expiry
- Token revocation support (RFC 7009)

**Access Control:**
- Connector CRUD: agent ownership validation
- Consent approval: email ACL check (owner or in `allowed_emails`)
- Token verification: per-connector isolation (token for connector A rejected on connector B)
- DCR: `max_clients` limit per connector (429 if exceeded)

**Session Isolation:**
- Each connector gets its own platform sessions
- Deactivated connector returns 404 on MCP requests
- Connector deletion cascades to OAuth clients, auth codes, tokens

## Implementation Scenarios

### Scenario 1: MCP Client Connects to Agent

```
1. Agent owner creates MCP connector in UI
2. Copies MCP Server URL: {MCP_SERVER_BASE_URL}/{connector_id}/mcp
3. Pastes URL into Claude Desktop / Cursor config
4. MCP client discovers AS via /.well-known/oauth-authorization-server
5. MCP client registers via DCR (POST /mcp/oauth/register)
6. MCP client initiates OAuth: GET /mcp/oauth/authorize
7. User redirected to consent page in browser
8. User logs in (if needed) and approves
9. Auth code exchanged for access + refresh tokens
10. MCP client calls send_message tool with bearer token
11. Agent processes message and streams response back
```

### Scenario 2: Multi-Turn Conversation via MCP

```
1. First send_message call → creates new platform session
2. Session linked to connector via mcp_connector_id
3. External session ID stored in session_metadata
4. Subsequent send_message calls → reuse same platform session
5. Agent maintains conversation context across turns
```

### Scenario 3: Connector Deactivation

```
1. Owner toggles connector to inactive
2. MCPConnectorService evicts MCP server from registry
3. Existing tokens remain in DB but:
   - MCPTokenVerifier rejects tokens (connector inactive check)
   - MCPServerRegistry returns 404 for connector path
4. MCP clients receive errors, must wait for reactivation
```

### Scenario 4: Token Refresh Flow

```
1. Access token expires after 1 hour
2. MCP client calls POST /mcp/oauth/token with grant_type=refresh_token
3. Server validates client credentials + refresh token
4. New access token issued (1 hour)
5. MCP client continues with new token
```

## File Locations Reference

### Backend — Models

- `backend/app/models/mcp_connector.py` — MCPConnector model and schemas
- `backend/app/models/mcp_oauth_client.py` — MCPOAuthClient model
- `backend/app/models/mcp_auth_code.py` — MCPAuthCode + MCPAuthRequest models
- `backend/app/models/mcp_token.py` — MCPToken model
- `backend/app/models/session.py:46-50` — MCP fields on session table
- `backend/app/models/__init__.py` — Exports added

### Backend — Routes

- `backend/app/api/routes/mcp_connectors.py` — Connector CRUD endpoints
- `backend/app/api/routes/mcp_consent.py` — OAuth consent endpoints
- `backend/app/mcp/oauth_routes.py` — OAuth AS endpoints (DCR, authorize, token, revoke)
- `backend/app/api/main.py` — Router registration (mcp_connectors, mcp_consent)
- `backend/app/main.py:208-213` — MCP OAuth router + registry mounting

### Backend — Services

- `backend/app/services/mcp_connector_service.py` — Connector CRUD logic

### Backend — MCP Infrastructure

- `backend/app/mcp/__init__.py` — Package init
- `backend/app/mcp/server.py` — FastMCP factory, MCPServerRegistry, mcp_connector_id_var
- `backend/app/mcp/token_verifier.py` — MCPTokenVerifier
- `backend/app/mcp/tools.py` — send_message tool handler, register_mcp_tools()
- `backend/app/mcp/oauth_routes.py` — Shared OAuth Authorization Server

### Backend — Configuration

- `backend/app/core/config.py` — `MCP_SERVER_BASE_URL` setting

### Backend — Migration

- `backend/app/alembic/versions/dc259404533e_add_mcp_integration_tables.py`

### Backend — Dependencies

- `backend/pyproject.toml` — `mcp[cli]` package added

### Frontend

- `frontend/src/routes/oauth/mcp-consent.tsx` — OAuth consent page
- `frontend/src/components/Agents/McpConnectorsCard.tsx` — Connector management card
- `frontend/src/components/Agents/AgentIntegrationsTab.tsx` — Imports McpConnectorsCard

### Tests

- `backend/tests/api/mcp_integration/conftest.py` — Test fixtures
- `backend/tests/api/mcp_integration/test_mcp_connector_crud.py` — Connector CRUD tests
- `backend/tests/api/mcp_integration/test_mcp_oauth_flow.py` — OAuth flow tests
- `backend/tests/utils/mcp.py` — Test utilities

## Related Documentation

- `docs/agent_mcp_connector_concept.md` — Original concept document
- `docs/mcp-integration/implementation_plan.md` — Phased implementation plan

---

**Document Version:** 1.0
**Last Updated:** 2026-02-26
**Status:** Implemented (Phase 1-7 complete, Phase 8 in progress)
