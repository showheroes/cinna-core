# MCP Integration — Phased Implementation Plan

This plan breaks the Agent MCP Connector feature (see `docs/agent_mcp_connector_concept.md`) into sequential phases. Each phase is self-contained, testable, and builds on the previous one.

---

## Phase Overview

| Phase | Name | Depends On | Deliverable |
|-------|------|------------|-------------|
| 1 | Database Models & Migration | — | Tables, SQLModel models, schemas, Alembic migration |
| 2 | Connector CRUD API & Service | Phase 1 | `/api/v1/agents/{agent_id}/mcp-connectors/` endpoints |
| 3 | Shared OAuth Authorization Server | Phase 1 | `/mcp/oauth/` endpoints (metadata, DCR, authorize, token, revoke) |
| 4 | Frontend: OAuth Consent Page | Phase 3 | `/oauth/mcp-consent` route + consent approval API |
| 5 | MCP Server Infrastructure | Phase 3 | MCPTokenVerifier, MCPServerRegistry, per-connector MCPServer instances, ASGI mounting |
| 6 | Tool Handlers & Session Mapping | Phase 5 | `send_message` tool, MCP↔platform session mapping, SSE streaming |
| 7 | Frontend: Connector Management UI | Phase 2 | MCPConnectorsCard in Integrations tab |
| 8 | Configuration, Testing & Hardening | Phase 1–7 | `MCP_SERVER_BASE_URL` config, tunnel setup, token cleanup, end-to-end testing |

```
Phase 1 ──► Phase 2 ──────────────────────────────► Phase 7
  │                                                    │
  ├──► Phase 3 ──► Phase 4                             │
  │      │                                             │
  │      └──► Phase 5 ──► Phase 6                      │
  │                                                    │
  └────────────────────────────────────────────────► Phase 8
```

Phases 2 and 3 can start in parallel after Phase 1.
Phases 4 and 7 are frontend phases that can proceed in parallel once their backend dependencies are met.

---

## Phase 1: Database Models & Migration

**Goal**: All database tables, SQLModel models, and Pydantic schemas needed by every subsequent phase.

### Scope

#### New Models (one file per entity in `backend/app/models/`)

1. **`mcp_connector.py`** — `MCPConnector` table + schemas
   - Table fields: `id`, `agent_id` (FK→Agent), `owner_id` (FK→User), `name`, `mode` (conversation/building), `is_active`, `allowed_emails` (JSONB), `max_clients`, `created_at`, `updated_at`
   - Schemas: `MCPConnectorBase`, `MCPConnectorCreate`, `MCPConnectorUpdate`, `MCPConnectorPublic`, `MCPConnectorsPublic` (list + count)
   - The `MCPConnectorPublic` schema should include a computed `mcp_server_url` field (built from `MCP_SERVER_BASE_URL` + connector `id`)

2. **`mcp_oauth_client.py`** — `MCPOAuthClient` table
   - Fields: `id`, `client_id` (unique), `client_secret_hash`, `client_name`, `redirect_uris` (JSONB), `grant_types` (JSONB), `response_types` (JSONB), `connector_id` (FK→MCPConnector CASCADE), `created_at`

3. **`mcp_auth_code.py`** — `MCPAuthCode` table + `MCPAuthRequest` table
   - `MCPAuthCode`: `code` (PK), `client_id`, `user_id` (FK→User), `connector_id` (FK→MCPConnector), `redirect_uri`, `code_challenge`, `scope`, `resource`, `expires_at`, `used`, `created_at`
   - `MCPAuthRequest`: `nonce` (PK), `connector_id` (FK→MCPConnector CASCADE), `client_id`, `redirect_uri`, `code_challenge`, `code_challenge_method`, `scope`, `state`, `resource`, `expires_at`, `used`, `created_at`

4. **`mcp_token.py`** — `MCPToken` table
   - Fields: `id`, `token` (unique), `token_type` (access/refresh), `client_id`, `user_id` (FK→User CASCADE), `connector_id` (FK→MCPConnector CASCADE), `scope`, `resource`, `expires_at`, `revoked`, `created_at`
   - Indexes on `token`, `connector_id`, `user_id`

#### Updated Models

5. **`session.py`** — Add two nullable fields:
   - `mcp_connector_id` (UUID, FK→MCPConnector, SET NULL on delete)
   - `mcp_session_id` (VARCHAR, unique, nullable) — the `Mcp-Session-Id` header value

#### Migration

6. Alembic migration creating all new tables, indexes, and the two new session columns.

#### Exports

7. Register new models in `backend/app/models/__init__.py` so Alembic discovers them.

### Acceptance Criteria

- `make migrate` applies cleanly
- All models importable; no circular imports
- Schemas validate correctly (unit-testable with Pydantic)

---

## Phase 2: Connector CRUD API & Service

**Goal**: Agent owners can create, list, update, and delete MCP connectors via the REST API. Frontend can consume these endpoints. No MCP protocol yet.

### Scope

#### Service Layer

1. **`backend/app/services/mcp_connector_service.py`**
   - `create_connector(db, agent_id, owner_id, name, mode, allowed_emails?)` → MCPConnector
   - `list_connectors(db, agent_id, owner_id)` → list (with registered client count, session count)
   - `get_connector(db, connector_id)` → MCPConnector | None
   - `update_connector(db, connector_id, owner_id, updates)` → MCPConnector
   - `delete_connector(db, connector_id, owner_id)` → None
   - `update_allowed_emails(db, connector_id, owner_id, emails)` → MCPConnector
   - `check_email_access(db, connector_id, email)` → bool (owner or in allowed_emails)
   - Ownership validation: all mutating operations verify `owner_id` matches the connector's owner

#### API Routes

2. **`backend/app/api/routes/mcp_connectors.py`** — FastAPI router, tag `mcp-connectors`

   | Method | Path | Description |
   |--------|------|-------------|
   | POST | `/api/v1/agents/{agent_id}/mcp-connectors/` | Create connector |
   | GET | `/api/v1/agents/{agent_id}/mcp-connectors/` | List connectors for agent |
   | GET | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Get connector detail |
   | PUT | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Update (name, mode, is_active, allowed_emails) |
   | DELETE | `/api/v1/agents/{agent_id}/mcp-connectors/{connector_id}` | Delete connector |

3. Register router in `backend/app/api/main.py`.

### Acceptance Criteria

- CRUD operations work via API (test with curl / Swagger UI)
- Ownership enforced: users can only manage connectors on agents they own
- `MCPConnectorPublic` response includes computed `mcp_server_url`
- Cascade delete: deleting a connector removes its OAuth clients, auth codes, tokens
- Regenerate frontend client (`make gen-client`)

### Tests

- API tests for all CRUD operations
- Ownership validation (403 for non-owners)
- Email ACL update + `check_email_access` logic

---

## Phase 3: Shared OAuth Authorization Server

**Goal**: Implement the shared OAuth 2.1 AS endpoints at `/mcp/oauth/`. After this phase, an MCP client can discover the AS, register via DCR, and complete the authorization flow (minus the consent UI, which is Phase 4 — for now, auto-approve or use a stub).

### Scope

#### OAuth Routes

1. **`backend/app/mcp/oauth_routes.py`** — FastAPI router mounted at `/mcp/oauth`

   | Endpoint | Purpose | Spec |
   |----------|---------|------|
   | `GET /.well-known/oauth-authorization-server` | AS metadata (RFC 8414) | Returns issuer, endpoints, supported grants/scopes/PKCE |
   | `POST /register` | Dynamic Client Registration (RFC 7591) | Extracts `connector_id` from `resource` URL, validates connector active, checks `max_clients`, generates `client_id` + `client_secret`, stores in `mcp_oauth_client` |
   | `GET /authorize` | OAuth authorize | Validates `client_id` belongs to connector (from `resource`), stores full request in `mcp_auth_request` (keyed by nonce), redirects to frontend consent page |
   | `POST /token` | Token exchange | Validates client credentials, PKCE (`code_verifier` vs stored `code_challenge`), `resource` matches auth code's connector, generates opaque access + refresh tokens, stores in `mcp_token` |
   | `POST /revoke` | Token revocation (RFC 7009) | Marks token as revoked in `mcp_token` |

#### Implementation Details

2. **AS Metadata response** — built from `MCP_SERVER_BASE_URL` config:
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

3. **DCR `/register`** — parse `resource` URL to extract `connector_id`, validate connector exists + is_active, enforce `max_clients`, generate `client_id` (UUID) + `client_secret` (random 48 bytes, base64), store `client_secret` as SHA256 hash, return credentials.

4. **`/authorize`** — store all params in `mcp_auth_request` table keyed by random nonce, redirect to `{FRONTEND_HOST}/oauth/mcp-consent?nonce={nonce}`. Auth request expires in 10 minutes.

5. **`/token`** — support two grant types:
   - `authorization_code`: validate client credentials, look up auth code, verify PKCE, verify `resource` matches, mark code as used, generate access token (1hr) + refresh token (30d), store both in `mcp_token`
   - `refresh_token`: validate client credentials, look up refresh token, verify not revoked/expired, generate new access token, optionally rotate refresh token

6. **`/revoke`** — look up token, mark `revoked=True`

7. **Helper**: `extract_connector_id_from_resource(resource_url)` — parses `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` to extract the UUID.

#### Configuration

8. Add `MCP_SERVER_BASE_URL` to `backend/app/core/config.py` (Settings class). Optional, defaults to empty string.

#### Mounting

9. Include the router in `backend/app/main.py`:
   ```python
   app.include_router(mcp_oauth_router, prefix="/mcp/oauth")
   ```

### Acceptance Criteria

- AS metadata endpoint returns correct JSON
- DCR creates a client and returns credentials; enforces `max_clients`
- `/authorize` stores request and redirects to frontend URL with nonce
- `/token` exchanges valid auth code for tokens; rejects invalid PKCE, expired codes, wrong resource
- `/revoke` immediately invalidates a token
- Refresh token grant issues new access token

### Tests

- Unit tests for PKCE verification logic
- Unit tests for `extract_connector_id_from_resource`
- API tests for each OAuth endpoint (happy path + error cases)
- DCR limit enforcement test

---

## Phase 4: Frontend — OAuth Consent Page

**Goal**: A frontend consent page that the OAuth `/authorize` redirect lands on. The user logs in (if needed), sees what they're authorizing, and approves or denies.

### Scope

#### Backend: Consent API

1. **`backend/app/api/routes/mcp_consent.py`** — FastAPI router

   | Method | Path | Description |
   |--------|------|-------------|
   | GET | `/api/v1/mcp/consent/{nonce}` | Fetch auth request details for display: agent name, connector mode, MCP client name, requested scopes. Public (no auth required — info is non-sensitive). |
   | POST | `/api/v1/mcp/consent/{nonce}/approve` | User approves. Requires user auth (JWT). Checks email ACL (user is owner or email in `allowed_emails`). Issues auth code in `mcp_auth_code`. Returns redirect URL with `code` + `state`. |

2. Register router in `backend/app/api/main.py`.

#### Frontend: Consent Route

3. **`frontend/src/routes/oauth/mcp-consent.tsx`** — public route (outside `_layout` auth guard)
   - Reads `nonce` from query params
   - Fetches consent details from `GET /api/v1/mcp/consent/{nonce}` — displays: agent name, connector name + mode, MCP client name, requested scopes
   - If user not logged in → shows login form (or redirects to login with return URL)
   - Shows "Authorize" / "Deny" buttons
   - On approve → calls `POST /api/v1/mcp/consent/{nonce}/approve` with JWT
   - On success → redirects browser to the returned redirect URL (MCP client's callback with auth code)
   - On deny → redirects to MCP client's `redirect_uri` with `error=access_denied`
   - Error states: expired nonce, already used, email not in allowed list (403)

4. Regenerate frontend client to pick up new consent API types.

### Acceptance Criteria

- `/authorize` redirect lands on the consent page
- Consent page shows agent name, mode, client name, scopes
- Unauthenticated users can log in and then return to consent
- Approval issues auth code and redirects to MCP client's callback
- Denial redirects with `error=access_denied`
- Email not in `allowed_emails` → 403 on approve
- Expired/used nonce → appropriate error display

### Tests

- Backend: API tests for consent endpoints (approval, denial, expired nonce, email ACL check)
- Frontend: manual verification of the consent flow

---

## Phase 5: MCP Server Infrastructure

**Goal**: The core MCP server machinery — TokenVerifier, MCPServerRegistry, per-connector MCPServer instances mounted in FastAPI. After this phase, MCP clients can connect, authenticate (full OAuth flow), and receive a 200 on the MCP endpoint (but no tools yet).

### Scope

#### Dependencies

1. Add `mcp[cli]` (v1.26.0+) to `backend/pyproject.toml` via `uv add "mcp[cli]"`.

#### Token Verifier

2. **`backend/app/mcp/token_verifier.py`** — implements SDK `TokenVerifier` protocol
   - `MCPTokenVerifier(connector_id: str)`
   - `verify_token(token: str) -> AccessToken | None`:
     1. Look up token in `mcp_token` table
     2. Check expiry + revocation
     3. Validate resource: `{MCP_SERVER_BASE_URL}/{db_token.connector_id}/mcp` must match this verifier's connector
     4. Verify connector is still active (`is_active=True`)
     5. Return SDK `AccessToken` model or `None`
   - Needs a DB session — either async session from a factory or a scoped session per request

#### MCPServer Factory

3. **`backend/app/mcp/server.py`** — `create_mcp_server_for_connector(connector_id)` function
   - Creates `MCPServer` instance with:
     - `auth=AuthSettings(issuer_url="{base_url}/oauth", resource_server_url="{base_url}/{connector_id}/mcp")`
     - `token_verifier=MCPTokenVerifier(connector_id)`
   - Registers tool handlers (initially empty, Phase 6 adds `send_message`)
   - Returns the MCPServer instance

#### MCPServerRegistry

4. **`MCPServerRegistry`** class in `backend/app/mcp/server.py`
   - `_servers: dict[str, ASGIApp]` — connector_id → ASGI app (from `server.streamable_http_app()`)
   - `get_or_create(connector_id)` — lazy creation, validates connector exists + active
   - `remove(connector_id)` — evicts on deactivation/deletion
   - `__call__(scope, receive, send)` — ASGI dispatcher:
     - Extracts `connector_id` from path (`/{connector_id}/...`)
     - Rewrites `scope["path"]` to remaining path
     - Sets `mcp_connector_id_var` contextvar
     - Delegates to per-connector ASGI app
     - Returns 404 for unknown/inactive connectors

5. **Contextvar**: `mcp_connector_id_var: ContextVar[str]` — set by registry, read by tool handlers

#### Mounting in FastAPI

6. In `backend/app/main.py`:
   ```python
   # OAuth routes (FastAPI router) — takes precedence over mount
   app.include_router(mcp_oauth_router, prefix="/mcp/oauth")
   # Per-connector MCP routes (ASGI mount)
   app.mount("/mcp", mcp_registry)
   ```
   - Verify Starlette routing precedence: `/mcp/oauth/...` routes match before `/mcp/...` mount

#### Lifespan

7. Add registry cleanup to FastAPI lifespan (shutdown: clear all MCPServer instances).

#### Integration with Connector CRUD

8. When a connector is deactivated or deleted (in `mcp_connector_service.py`), call `mcp_registry.remove(connector_id)` to evict the cached MCPServer instance.

### Acceptance Criteria

- MCP client connecting to `/mcp/{connector_id}/mcp` without a token gets 401 with `WWW-Authenticate` header
- `GET /mcp/{connector_id}/.well-known/oauth-protected-resource` returns correct metadata pointing to shared AS
- After completing the full OAuth flow (DCR → authorize → consent → token), the MCP client can POST to `/mcp/{connector_id}/mcp` with a valid bearer token and get a successful MCP `initialize` response
- Token for connector A rejected when used on connector B
- Deactivated connector returns 404

### Tests

- Unit tests for `MCPTokenVerifier` (valid token, expired, revoked, wrong connector, inactive connector)
- Integration test: full OAuth flow → authenticated MCP request
- Registry: lazy creation, eviction on delete

---

## Phase 6: Tool Handlers & Session Mapping

**Goal**: The `send_message` MCP tool works end-to-end — an MCP client can send a message to the agent, the agent processes it, and the response streams back.

### Scope

#### Tool Registration

1. **`backend/app/mcp/tools.py`** — tool handler definitions
   - `send_message(message: str, ctx: Context) -> list[Content]`:
     1. Get `connector_id` from `mcp_connector_id_var` contextvar
     2. Get `access_token` from SDK's `get_access_token()` context
     3. Load connector from DB (get agent_id, owner_id, mode)
     4. Get or create platform session:
        - Extract MCP session ID from `ctx.session` (SDK session object)
        - Look up `session.mcp_session_id` in platform DB
        - If not found → `SessionService.create_session(environment_id, user_id=owner_id, mode=connector.mode, mcp_connector_id=connector.id, integration_type="mcp")`, store MCP session ID mapping
        - If found → reuse existing session
     5. Check agent environment status; auto-start if not running (stream progress: "Starting agent environment...")
     6. Send message via `MessageService.stream_message_with_events(session, message)`
     7. Stream progress notifications via `ctx.report_progress()` as agent processes
     8. Collect final response; return as `TextContent` (+ `ImageContent` / `EmbeddedResource` if applicable)
     9. On hard error (env crash, timeout) → return tool result with `isError=True`

#### Message Queuing

2. Handle concurrent `send_message` calls on the same MCP session:
   - Use an `asyncio.Lock` per platform session (keyed by session ID)
   - If locked → send progress notification "Message queued, waiting for previous message to complete..."
   - Queue limit: reject with MCP error if >5 pending messages

#### Tool Registration in Server Factory

3. Update `create_mcp_server_for_connector()` (from Phase 5) to call `register_mcp_tools(server, connector_id)` which registers the `send_message` tool via `@server.tool()`.

#### Response Format

4. Map agent response to MCP content types:
   - Text → `TextContent`
   - Images → `ImageContent` (base64)
   - File artifacts → `EmbeddedResource` with workspace URI
   - Tool invocation logs → formatted as text (included in response)

### Acceptance Criteria

- MCP client calls `tools/list` → sees `send_message` tool
- MCP client calls `send_message` → receives agent response
- Same MCP session maintains conversation continuity (multi-turn)
- New MCP session creates a new platform session
- Agent environment auto-starts if not running, with streaming progress
- Concurrent messages on same session are queued and processed sequentially
- Hard errors return `isError: true`

### Tests

- Integration test: `send_message` → response (requires running agent environment or mock)
- Session mapping: verify same MCP session → same platform session
- Session mapping: verify new MCP session → new platform session
- Concurrent message queuing behavior

---

## Phase 7: Frontend — Connector Management UI

**Goal**: Agent owners can create and manage MCP connectors in the frontend Integrations tab.

### Scope

#### Components

1. **`MCPConnectorsCard`** — new card in `AgentIntegrationsTab.tsx`
   - Header: "MCP Connectors" + description text
   - Create button → opens creation dialog
   - List of existing connectors

2. **Create Connector Dialog**
   - Name input
   - Mode selector: Conversation / Building (radio or select)
   - Allowed Emails input (comma-separated or email chips, empty = owner only)
   - Submit → `POST /api/v1/agents/{agent_id}/mcp-connectors/`

3. **Connector List Item**
   - Name + mode badge (conversation/building)
   - MCP Server URL — copyable field: `{MCP_SERVER_BASE_URL}/{id}/mcp`
   - Status badge: Active / Inactive
   - Allowed emails display:
     - "Owner only" when empty
     - Email chips with add/remove capability
   - Stats: registered clients count, session count
   - Actions: Toggle active, Edit (name, mode, emails), Delete with confirmation

4. **Edit Connector Dialog**
   - Same fields as create, pre-populated
   - `PUT /api/v1/agents/{agent_id}/mcp-connectors/{id}`

#### React Query Integration

5. Query key: `["mcp-connectors", agentId]`
6. Mutations for create, update, delete with optimistic updates or invalidation

#### API Client

7. Regenerate frontend client to pick up MCP connector API types and services.

### Acceptance Criteria

- Create connector → appears in list with copyable MCP Server URL
- Edit connector (name, mode, emails, active toggle) works
- Delete connector with confirmation dialog
- Email chips UI: add/remove emails
- Copy MCP Server URL to clipboard
- Correct status badges and stats display

---

## Phase 8: Configuration, Testing & Hardening

**Goal**: End-to-end working system, tested with real MCP clients (Claude Desktop, Cursor). Production-ready configuration.

### Scope

#### Configuration

1. **Backend `.env`**: Add `MCP_SERVER_BASE_URL` (documented, with examples for local dev + production)
2. **Frontend `.env`**: Add `VITE_MCP_SERVER_BASE_URL` (or expose via API config endpoint)
3. **CORS**: Ensure MCP client origins are handled (the SDK's protected resource endpoint allows `*`; our OAuth routes may need explicit CORS for browser-based flows)

#### Local Dev Tunnel Setup

4. Document Pinggy/ngrok setup for local testing:
   - Tunnel to backend port
   - Set `MCP_SERVER_BASE_URL` to tunnel URL + `/mcp` prefix
   - Add tunnel domain to `BACKEND_CORS_ORIGINS`

#### Token Cleanup

5. Background job (or periodic task) to purge expired tokens from `mcp_token` and expired auth requests from `mcp_auth_request`. Can be a simple cron-like task or an on-demand cleanup triggered periodically.

#### Security Hardening

6. Validate `Origin` header on MCP requests (DNS rebinding prevention)
7. Ensure `client_secret` is stored as SHA256 hash only (verify Phase 3 implementation)
8. Rate limiting on DCR endpoint (nginx-level or application-level, beyond `max_clients`)
9. Verify HTTPS enforcement in production config

#### End-to-End Testing

10. **Claude Desktop**: Full flow — add MCP server URL → DCR → OAuth → consent → tool call → response
11. **Cursor**: Same flow if Cursor supports remote MCP servers
12. **Edge cases**:
    - Connector deactivated while client has active session
    - Token expiry → refresh flow
    - Concurrent `send_message` calls
    - Agent environment not running → auto-start
    - Email not in `allowed_emails` → consent rejection
    - DCR limit reached → 429 response

#### Documentation

13. Update `CLAUDE.md` with MCP-related commands and patterns
14. Add local dev setup instructions to `docs/mcp-integration/`

### Acceptance Criteria

- Full end-to-end flow works with Claude Desktop via tunnel
- Token cleanup removes expired records
- Security checks pass (Origin validation, PKCE, resource validation)
- Documentation complete for local dev and production setup

---

## Future Phases (Post-MVP)

These correspond to Phases 2 and 3 from the concept document. Not planned in detail here.

### Enhanced Tools & Resources
- Workspace resources: `resources/list` and `resources/read` for workspace files
- Session management tools: `list_sessions`, `get_session_status`
- Interrupt support: `interrupt` tool
- File upload: `upload_file` tool

### Advanced Features
- Prompt templates via MCP `prompts/list`
- External OAuth providers (Auth0/Keycloak) — swap AS, keep TokenVerifier
- Per-connector rate limiting
- Usage tracking and analytics
- Webhook notifications on connector usage

---

**Document Version:** 1.0
**Created:** 2026-02-25
**Source:** `docs/agent_mcp_connector_concept.md`
