# Agent MCP Connector — Concept & Architecture

## What We Want

Expose platform agents as **remote MCP servers** so that any MCP-compatible tool — Claude Desktop, Claude.ai, Cursor, Windsurf, VS Code Copilot, or custom clients — can connect to an agent and interact with it as a tool provider. The agent becomes a first-class MCP endpoint: the MCP client sends tool calls, the agent processes them via its environment (Docker container running Google ADK / Claude Code), and results stream back over the MCP protocol.

This is conceptually similar to our existing A2A integration (see `docs/a2a/a2a_integration.md`), but speaks the **Model Context Protocol** instead of the A2A JSON-RPC protocol. Like A2A access tokens and guest share links, a single agent can expose **multiple MCP connector endpoints** with different permission levels (conversation vs. building mode). Access to each connector is controlled via an **email-based allowed list** — the connector owner specifies which email addresses can authenticate, replacing URL-as-security-boundary with explicit access control.

### Why MCP?

- **Universal tool interoperability** — MCP is becoming the standard protocol for connecting AI tools. Claude Desktop, Claude.ai (Pro/Max/Team/Enterprise), Cursor, and others already support adding remote MCP servers.
- **Two-way communication** — MCP supports tools (client→server), resources (server→client discovery), and prompts — richer than simple chat.
- **OAuth-based auth** — The MCP authorization spec provides a standardized way for users to authenticate, eliminating the need for manual token management.
- **Complements A2A** — A2A is agent-to-agent (task delegation). MCP is tool-use (the AI calls our agent as a tool). Different use cases, same underlying agent.

---

## High-Level Architecture

```
┌──────────────────────┐
│  MCP Client          │
│  (Claude Desktop,    │    Streamable HTTP + OAuth 2.1
│   Cursor, etc.)      │◄──────────────────────────────────►┌──────────────────────────────────┐
└──────────────────────┘                                     │  Our Backend (FastAPI)            │
                                                             │                                  │
                                                             │  Shared OAuth AS:                │
                                                             │  /mcp/oauth/...                  │
                                                             │  (our FastAPI routes)            │
                                                             │                                  │
                                                             │  Per-Connector RS:               │
                                                             │  /mcp/{connector_id}/...         │
                                                             │       ┌────────────────────┐     │
                                                             │       │ MCPServerRegistry   │     │
                                                             │       │  ┌──MCPServer(A)──┐ │     │
                                                             │       │  ├──MCPServer(B)──┤ │     │
                                                             │       │  └──MCPServer(C)──┘ │     │
                                                             │       └─────────┬──────────┘     │
                                                             │                 │                │
                                                             │       SessionService /           │
                                                             │       MessageService             │
                                                             │                 │                │
                                                             └─────────────────┼────────────────┘
                                                                               │
                                                                       SSE / HTTP
                                                                               │
                                                             ┌─────────────────┴────────────────┐
                                                             │  Agent Environment               │
                                                             │  (Docker Container)              │
                                                             │  Google ADK / Claude Code        │
                                                             └──────────────────────────────────┘
```

### Architecture: AS/RS Separation

The MCP Python SDK's `AuthSettings` binds `issuer_url` and `resource_server_url` **per MCPServer instance**. This means a single `MCPServer` instance can only represent one OAuth identity — it cannot serve different `issuer_url` or `resource_server_url` values for different connectors.

Our architecture separates the two OAuth roles:

| Role | Implementation | URL Space |
|------|---------------|-----------|
| **Authorization Server (AS)** | Our own FastAPI routes | `/mcp/oauth/...` (shared, one set of endpoints) |
| **Resource Server (RS)** | One `MCPServer` instance per connector, using `token_verifier` | `/mcp/{connector_id}/...` (per-connector) |

**Why this works:**
- Each `MCPServer` instance is created with `token_verifier=OurTokenVerifier` (no `auth_server_provider`) and `auth=AuthSettings(issuer_url=shared_oauth_url, resource_server_url=per_connector_url)`
- The SDK automatically generates `/.well-known/oauth-protected-resource` for each connector, pointing to the shared AS
- The SDK does NOT generate OAuth routes (`/authorize`, `/token`, `/register`, `/revoke`) when only `token_verifier` is provided — confirmed in `MCPServer.streamable_http_app()` (line 967 of SDK source)
- `auth_server_provider` and `token_verifier` are **mutually exclusive** in `MCPServer.__init__`
- Our shared FastAPI OAuth routes handle all authorization logic — DCR, authorize, token exchange, revocation

**SDK source references:**
| File | What We Reference |
|------|-------------------|
| `src/mcp/server/auth/provider.py` | `TokenVerifier` protocol, `AccessToken` model |
| `src/mcp/server/auth/settings.py` | `AuthSettings` (`issuer_url` + `resource_server_url`) |
| `src/mcp/server/auth/routes.py` | `create_protected_resource_routes()`, `build_resource_metadata_url()` |
| `src/mcp/server/auth/middleware/bearer_auth.py` | `BearerAuthBackend`, `RequireAuthMiddleware` |
| `src/mcp/server/mcpserver/server.py` | `MCPServer.__init__` (`token_verifier` vs `auth_server_provider`), `streamable_http_app()` |
| `examples/servers/simple-auth/` | Canonical AS/RS separation example |

---

### URL Scheme & Routing

MCP endpoints live under the `/mcp/` prefix — separate from the `/api/v1/` prefix used by the frontend.

**Routing table:**

| URL Pattern | Handler | Purpose |
|-------------|---------|---------|
| `/mcp/oauth/.well-known/oauth-authorization-server` | Our FastAPI route | AS metadata (RFC 8414) |
| `/mcp/oauth/register` | Our FastAPI route | Dynamic Client Registration (RFC 7591) |
| `/mcp/oauth/authorize` | Our FastAPI route | OAuth authorization (redirects to frontend consent) |
| `/mcp/oauth/token` | Our FastAPI route | Token exchange (code→token, refresh) |
| `/mcp/oauth/revoke` | Our FastAPI route | Token revocation (RFC 7009) |
| `/mcp/{connector_id}/.well-known/oauth-protected-resource` | SDK auto-generated | Protected Resource Metadata (RFC 9728) — points to shared AS |
| `/mcp/{connector_id}/mcp` | SDK `MCPServer` (per-connector instance) | MCP Streamable HTTP endpoint |

**Important**: The `/mcp/` routes are for **external MCP clients only**, not our frontend. The frontend manages connectors via the standard `/api/v1/agents/{agent_id}/mcp-connectors/` endpoints.

**Production deployment:** In production, we can set up a dedicated subdomain `mcp.domain.com` via nginx reverse proxy:

```nginx
server {
    server_name mcp.domain.com;
    location / {
        proxy_pass http://backend:8000/mcp/;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /;
    }
}
```

This means:
- External MCP clients use: `https://mcp.domain.com/{connector_id}/mcp`
- OAuth endpoints at: `https://mcp.domain.com/oauth/...`
- nginx strips the subdomain and proxies to: `http://backend:8000/mcp/...`

### Configuration: `MCP_SERVER_BASE_URL`

All externally-facing MCP URLs (OAuth metadata, token audience, the copyable MCP Server URL shown in the frontend) are derived from a single configuration variable:

```
MCP_SERVER_BASE_URL=https://mcp.domain.com
```

This is the **base URL that MCP clients will use to reach our backend's `/mcp/` routes**. It is set in the backend `.env` file and also exposed to the frontend (via `VITE_MCP_SERVER_BASE_URL` or via the API config endpoint).

**Why a dedicated config variable instead of `X-Forwarded-Host`?**

In our architecture the frontend and backend run on **separate ports/origins** (e.g., frontend on `localhost:5173`, backend on `localhost:8000`). The backend cannot infer the correct external MCP domain from the incoming request headers because:
- Local dev requests come from the frontend origin, not from the MCP client
- The frontend needs to display the MCP Server URL to the user *before* any MCP client connects
- In production with an nginx subdomain proxy, the backend receives proxied requests — but the URL shown in the UI must still be built from a known, stable value

A single config variable eliminates all ambiguity and works identically across environments.

**How URLs are built:**

| What | Built URL |
|------|-----------|
| MCP Server URL (shown in UI, user copies this) | `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` |
| Protected Resource Metadata (SDK auto-generated) | `{MCP_SERVER_BASE_URL}/{connector_id}/.well-known/oauth-protected-resource` |
| Authorization Server Metadata | `{MCP_SERVER_BASE_URL}/oauth/.well-known/oauth-authorization-server` |
| OAuth authorize | `{MCP_SERVER_BASE_URL}/oauth/authorize` |
| OAuth token | `{MCP_SERVER_BASE_URL}/oauth/token` |
| DCR register | `{MCP_SERVER_BASE_URL}/oauth/register` |
| Token audience (`resource` parameter) | `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` |

#### Production Configuration

In production with the nginx subdomain proxy (`mcp.domain.com` → `backend:8000/mcp/`):

```env
# .env (backend)
MCP_SERVER_BASE_URL=https://mcp.domain.com
```

The nginx proxy forwards requests from `https://mcp.domain.com/...` to the backend at `http://backend:8000/mcp/...`. The backend uses `MCP_SERVER_BASE_URL` (not request headers) to build all OAuth metadata and URLs, so they always reflect the external `mcp.domain.com` origin.

If you don't use a dedicated subdomain, point to your main domain with the `/mcp` prefix:

```env
MCP_SERVER_BASE_URL=https://yourdomain.com/mcp
```

#### Local Development with Pinggy (or ngrok / Cloudflare Tunnel)

For local testing, the MCP client (Claude Desktop, Cursor, etc.) needs a **publicly accessible HTTPS URL** to reach the backend. Tools like [Pinggy](https://pinggy.io) create an HTTPS tunnel from a public domain to your local port.

**Setup:**

```bash
# Terminal 1: Start backend
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000

# Terminal 2: Start Pinggy tunnel to the backend port
ssh -p 443 -R0:localhost:8000 a.pinggy.io
# Pinggy outputs: https://abc123-xx-yy-zz-ww.a.free.pinggy.link
```

Copy the Pinggy domain and set it in `.env` with the `/mcp` path prefix (since the backend serves MCP routes under `/mcp/`):

```env
# .env (backend) — local dev with Pinggy
MCP_SERVER_BASE_URL=https://abc123-xx-yy-zz-ww.a.free.pinggy.link/mcp
```

```env
# frontend/.env — so the UI can display the correct MCP Server URL
VITE_MCP_SERVER_BASE_URL=https://abc123-xx-yy-zz-ww.a.free.pinggy.link/mcp
```

Also add the Pinggy domain to allowed CORS origins:

```env
BACKEND_CORS_ORIGINS=["http://localhost:5173","https://abc123-xx-yy-zz-ww.a.free.pinggy.link"]
```

Restart the backend after changing `.env`. Now:

1. Open the local frontend (`http://localhost:5173`)
2. Create an MCP Connector in the agent's Integrations tab
3. The UI shows the MCP Server URL as: `https://abc123-xx-yy-zz-ww.a.free.pinggy.link/mcp/{connector_id}/mcp`
4. Copy this URL into Claude Desktop / Cursor
5. The MCP client hits the Pinggy URL → tunnel routes to `localhost:8000/mcp/{connector_id}/...`
6. Full DCR + OAuth flow works through the tunnel

**Request flow:**

```
Claude Desktop                     Pinggy                      Local Backend (port 8000)
     │                               │                               │
     │──POST /mcp (no token)────────►│──────► localhost:8000/mcp/... │
     │◄──401 + WWW-Authenticate──────│◄──────────────────────────────│
     │                               │                               │
     │──GET /.well-known/────────────►│                               │
     │  oauth-protected-resource     │──────► localhost:8000/mcp/... │
     │◄──{authorization_servers}─────│◄──────────────────────────────│
     │                               │                               │
     │──GET oauth/.well-known/───────►│                               │
     │  oauth-authorization-server   │──────► localhost:8000/mcp/... │
     │◄──{authorize, token, reg}─────│◄──────────────────────────────│
     │                               │                               │
     │──POST oauth/register─────────►│──────► localhost:8000/mcp/... │
     │◄──{client_id, client_secret}──│◄──────────────────────────────│
     │                               │                               │
     │──Browser: oauth/authorize────►│──────► localhost:8000/mcp/... │
     │  [User logs in + approves]    │                               │
     │◄─Redirect with auth code──────│◄──────────────────────────────│
     │                               │                               │
     │──POST oauth/token────────────►│──────► localhost:8000/mcp/... │
     │◄──{access_token}──────────────│◄──────────────────────────────│
     │                               │                               │
     │──POST /{id}/mcp (tool call)──►│──────► localhost:8000/mcp/... │
     │◄──MCP response────────────────│◄──────────────────────────────│
```

**Tips for local testing:**

- **Pinggy free tier** gives a random subdomain that changes on each reconnect. This invalidates DCR client registrations and tokens. For sustained testing, use Pinggy's paid custom subdomain or a tool with stable URLs (ngrok paid tier, Cloudflare Tunnel with named tunnel).
- **Frontend runs separately** on `localhost:5173` — it doesn't go through the tunnel. Only the MCP client traffic uses the tunnel.
- **No nginx needed** locally — Pinggy terminates TLS and forwards directly to the backend port.
- After a tunnel restart with a new domain, update `MCP_SERVER_BASE_URL` in both `.env` files, restart the backend, and re-create or re-connect MCP connectors (old URLs are invalid).

### Data Flow

1. MCP client connects to `https://mcp.domain.com/{connector_id}/mcp`
2. Server returns 401 with `WWW-Authenticate` header pointing to protected resource metadata at `/{connector_id}/.well-known/oauth-protected-resource`
3. MCP client fetches protected resource metadata → gets `authorization_servers` array pointing to shared OAuth AS at `/oauth/.well-known/oauth-authorization-server`
4. MCP client fetches AS metadata → discovers `/oauth/register`, `/oauth/authorize`, `/oauth/token`
5. MCP client registers via DCR at shared `/oauth/register` (includes `resource` parameter identifying the connector)
6. OAuth 2.1 authorization flow (shared `/oauth/authorize` → consent → `/oauth/token`) authenticates the user
7. MCP client uses access token to call `POST /{connector_id}/mcp` → per-connector `MCPServer` instance validates token via `TokenVerifier`
8. MCP client discovers available tools via `tools/list`
9. MCP client calls a tool → backend creates/reuses a session, sends message to agent environment
10. Agent environment processes the request, streams response back
11. Backend maps response to MCP tool result and returns to client

---

## Core Concepts

### MCP Connector

An **MCP Connector** is a named, scoped access point that exposes an agent as an MCP server. It is the MCP equivalent of an A2A access token or a guest share link.

| Property | Description |
|----------|-------------|
| `id` | UUID primary key |
| `agent_id` | FK to Agent |
| `owner_id` | FK to User (agent owner) |
| `name` | Display name (e.g., "Cursor - conversation", "Claude Desktop - building") |
| `mode` | `conversation` or `building` — controls which agent mode is used |
| `is_active` | Enable/disable without deletion |
| `allowed_emails` | JSONB list of email addresses allowed to authenticate (empty = owner only) |
| `max_clients` | Maximum DCR client registrations allowed (default 1000) |
| `created_at` | Timestamp |

#### Email-Based Access Control

Access to a connector is controlled via an **allowed emails** list, replacing the old URL-as-security-boundary model:

- **Owner always has access** — the connector owner can always authenticate, regardless of `allowed_emails`
- **Empty list = owner only** — by default, only the owner can use a connector
- **Explicit sharing** — the owner adds email addresses to `allowed_emails` to grant access to specific people
- **Checked during OAuth authorize** — when a user goes through the OAuth flow, the shared `/oauth/authorize` endpoint verifies their email is in the connector's `allowed_emails` (or they are the owner) before proceeding to the consent screen
- **No URL guessing risk** — even if someone obtains the MCP Server URL, they cannot authenticate unless their email is on the allowed list

This model is more secure than URL-as-security-boundary because:
1. URLs can be shared inadvertently (browser history, chat logs, screenshots)
2. Email-based control gives the owner explicit, auditable control over who has access
3. Access can be revoked by removing an email without changing the connector URL (no need to re-create the connector and update all authorized users' MCP client configs)

**Zero-config for the user**: The user only needs to copy the **MCP Server URL** and paste it into their MCP client. The client auto-discovers the OAuth metadata, registers itself via Dynamic Client Registration (RFC 7591), and handles the full OAuth flow. No client IDs or secrets to manage.

**Why multiple connectors?** Different MCP clients may need different permission levels:
- A "conversation" connector for quick tasks (cheaper, faster, limited tools)
- A "building" connector for development work (full tool access, file modification)
- Separate connectors for different users or teams (each with its own allowed emails list, client registrations, and session isolation)

Each MCP session creates its own isolated platform session — there is no cross-session visibility between connections.

### Mapping MCP Primitives to Our Platform

| MCP Primitive | Platform Mapping | Notes |
|---------------|-----------------|-------|
| **Tool** | Agent capability / skill | Exposed via `tools/list`. Each tool maps to a "send message to agent" operation or a platform operation |
| **Resource** | Agent workspace files, session history | Exposed via `resources/list`. Read-only access to workspace files |
| **Prompt** | Agent prompt templates | Optional. Expose pre-built prompt templates |
| **MCP Session** | Platform Session (chat session) | One MCP session maps to one platform chat session |

### Tool Design

The agent exposes a small set of MCP tools that map to platform operations:

#### Primary Tool: `send_message`

The core tool — send a message to the agent and get a response.

```json
{
  "name": "send_message",
  "description": "Send a message to the agent and receive a response. The agent will process your request using its configured capabilities, tools, and knowledge.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "message": {
        "type": "string",
        "description": "The message to send to the agent"
      }
    },
    "required": ["message"]
  }
}
```

Session continuity is handled automatically via the MCP session — all `send_message` calls within the same MCP session go to the same platform chat session (see [Design Decisions](#design-decisions)).

#### Resource: Workspace Files

```json
{
  "uri": "workspace://files",
  "name": "Agent Workspace",
  "description": "Browse and read files in the agent's workspace"
}
```

#### Optional Tools (Phase 2+)

- `list_sessions` — List existing sessions
- `get_session_status` — Check if agent is processing
- `interrupt` — Stop current agent processing
- `upload_file` — Upload a file to agent workspace

---

## Authentication & Authorization

### MCP OAuth 2.1 Spec (Protocol Revision 2025-06-18)

The MCP authorization spec mandates **OAuth 2.1 with PKCE** for remote HTTP servers. Our architecture separates the Authorization Server (AS) and Resource Server (RS):

- **Shared OAuth AS** — Our FastAPI routes at `/mcp/oauth/...`, handling all OAuth protocol endpoints
- **Per-connector RS** — Each connector's `MCPServer` instance (SDK-managed), validating tokens via `TokenVerifier`

### Shared OAuth Authorization Server

Our FastAPI routes implement the OAuth 2.1 Authorization Server. These are **not** SDK-managed — we implement them directly as FastAPI endpoints under `/mcp/oauth/`.

#### Endpoints

| Endpoint | Purpose | Spec Reference |
|----------|---------|----------------|
| `GET /mcp/oauth/.well-known/oauth-authorization-server` | Authorization Server Metadata (RFC 8414) | **MUST** implement |
| `POST /mcp/oauth/register` | Dynamic Client Registration (RFC 7591) | **SHOULD** implement |
| `GET /mcp/oauth/authorize` | OAuth authorization — user login/consent | **MUST** implement |
| `POST /mcp/oauth/token` | Token exchange — code→token, refresh | **MUST** implement |
| `POST /mcp/oauth/revoke` | Token revocation (RFC 7009) | Optional |

#### AS Metadata Response

`GET /mcp/oauth/.well-known/oauth-authorization-server` returns:

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

#### DCR Register (`/mcp/oauth/register`)

Accepts a `resource` parameter to identify which connector the registration is for:

```
POST /mcp/oauth/register
{
  "client_name": "Claude Desktop",
  "redirect_uris": ["http://localhost:..."],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "resource": "{MCP_SERVER_BASE_URL}/{connector_id}/mcp"  // Identifies the connector
}
```

The handler:
1. Extracts `connector_id` from the `resource` URL
2. Validates the connector exists and is active
3. Checks `max_clients` limit for the connector
4. Generates `client_id` + `client_secret`, stores in `mcp_oauth_client` table with `connector_id` FK
5. Returns credentials to the MCP client

#### Authorize (`/mcp/oauth/authorize`)

The authorize endpoint receives the standard OAuth parameters plus the `resource` indicator:

```
GET /mcp/oauth/authorize?
  response_type=code&
  client_id=...&
  redirect_uri=...&
  code_challenge=...&
  code_challenge_method=S256&
  state=...&
  scope=mcp:tools&
  resource={MCP_SERVER_BASE_URL}/{connector_id}/mcp
```

The handler:
1. Extracts `connector_id` from the `resource` URL
2. Validates `client_id` belongs to this connector
3. Stores the full authorization request server-side in `mcp_auth_request` table (keyed by random nonce)
4. Redirects to frontend consent page: `{FRONTEND_HOST}/oauth/mcp-consent?nonce={nonce}`

**Access control check during consent approval**: When the user approves on the consent page, the backend `POST /api/v1/mcp/consent/{nonce}/approve` endpoint verifies:
- The user is the connector owner, OR
- The user's email is in the connector's `allowed_emails` list
- If neither → reject with 403

#### Token (`/mcp/oauth/token`)

Standard OAuth token exchange with PKCE validation. The `resource` parameter is validated against the `connector_id` from the auth code:

```
POST /mcp/oauth/token
  grant_type=authorization_code&
  client_id=...&
  client_secret=...&
  code=...&
  code_verifier=...&
  resource={MCP_SERVER_BASE_URL}/{connector_id}/mcp
```

The handler:
1. Validates `client_id` + `client_secret`
2. Looks up auth code, validates PKCE (`code_verifier` against stored `code_challenge`)
3. Validates `resource` matches the auth code's `connector_id`
4. Generates opaque access + refresh tokens, stores in `mcp_token` table with `connector_id`
5. Returns tokens

#### Revoke (`/mcp/oauth/revoke`)

Marks the token as revoked in the `mcp_token` table. Immediate effect.

### Per-Connector Resource Server

Each connector has its own `MCPServer` instance running in Resource Server mode. The SDK handles:

#### Protected Resource Metadata (SDK auto-generated)

`GET /mcp/{connector_id}/.well-known/oauth-protected-resource` returns:

```json
{
  "resource": "{MCP_SERVER_BASE_URL}/{connector_id}/mcp",
  "authorization_servers": ["{MCP_SERVER_BASE_URL}/oauth"],
  "bearer_methods_supported": ["header"]
}
```

This is generated automatically by the SDK via `create_protected_resource_routes()` when `resource_server_url` is set in `AuthSettings`.

#### MCP Streamable HTTP (SDK-managed)

`POST|GET|DELETE /mcp/{connector_id}/mcp` — the MCP JSON-RPC endpoint. The SDK handles session management, bearer token extraction, and dispatches to our tool handlers.

### TokenVerifier Implementation

The SDK defines a `TokenVerifier` protocol (in `provider.py`) that we implement for database-backed token validation:

```python
from mcp.server.auth.provider import TokenVerifier, AccessToken

class MCPTokenVerifier(TokenVerifier):
    """Database-backed token verifier for MCP Resource Server mode."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Validate an opaque access token against the database.

        Returns AccessToken if valid, None if invalid/expired/revoked.
        """
        # 1. Look up token in mcp_token table
        db_token = await lookup_token(token)
        if not db_token:
            return None

        # 2. Check expiry and revocation
        if db_token.expires_at < utcnow() or db_token.revoked:
            return None

        # 3. CRITICAL: Validate resource (token audience = connector URL)
        #    The SDK's RequireAuthMiddleware does NOT validate the resource field.
        #    It only uses resource_metadata_url for the WWW-Authenticate header.
        #    Resource validation MUST happen here in our verifier.
        expected_resource = f"{MCP_SERVER_BASE_URL}/{db_token.connector_id}/mcp"
        connector_resource = get_current_connector_resource()  # From the MCPServer's AuthSettings
        if expected_resource != connector_resource:
            return None

        # 4. Verify the connector is still active
        connector = await get_connector(db_token.connector_id)
        if not connector or not connector.is_active:
            return None

        # 5. Return SDK AccessToken model
        return AccessToken(
            token=token,
            client_id=db_token.client_id,
            scopes=db_token.scope.split() if db_token.scope else [],
            expires_at=int(db_token.expires_at.timestamp()),
            resource=expected_resource,
        )
```

**Critical note:** `RequireAuthMiddleware` (in `bearer_auth.py`) does NOT validate the `resource` field — it only uses `resource_metadata_url` for the `WWW-Authenticate` header. Resource validation (ensuring a token issued for connector A can't be used on connector B) MUST be done in our `TokenVerifier.verify_token()`. This is confirmed by the SDK source in `bearer_auth.py`.

### Authorization Flow

```
User creates MCP Connector in our UI → copies MCP Server URL
    │
    ▼

MCP Client                  Per-Connector RS                 Shared OAuth AS
    │                        /{connector_id}/                /oauth/
    │                           │                                │
    │──POST /mcp (no token)────►│                                │
    │◄──401 + WWW-Authenticate──│                                │
    │   (resource_metadata URL) │                                │
    │                           │                                │
    │──GET /.well-known/────────►│                                │
    │  oauth-protected-resource │                                │
    │◄──{authorization_servers}─│                                │
    │   (points to shared AS)   │                                │
    │                           │                                │
    │──GET .well-known/oauth-authorization-server────────────────►│
    │◄──{authorize, token, registration_endpoint}─────────────────│
    │                           │                                │
    │──POST /register (+ resource param)─────────────────────────►│
    │  {client_name, redirect_uris, grant_types, resource}       │
    │◄──{client_id, client_secret}────────────────────────────────│
    │                           │                                │
    │  [Browser: /authorize + client_id + PKCE + resource]───────►│
    │  [Backend checks email-based access control]                │
    │  [Redirects to frontend consent page]                       │
    │  [User logs in (if needed) + approves on consent screen]    │
    │  [Frontend calls backend API to issue auth code]            │
    │◄─[Redirect to MCP client's redirect_uri with auth code]────│
    │                           │                                │
    │──POST /token + client_id + client_secret───────────────────►│
    │  + code_verifier + resource                                │
    │◄──{access_token, refresh_token}─────────────────────────────│
    │                           │                                │
    │──POST /mcp (Bearer token)►│                                │
    │  [TokenVerifier validates] │                                │
    │◄──MCP response────────────│                                │
```

The MCP client handles everything automatically — the user only pastes the URL.

#### Key Requirements from the 2025-06-18 Spec

1. **Protected Resource Metadata (RFC 9728)** — Server MUST implement. Returns `authorization_servers` array pointing to shared AS. SDK generates this automatically per connector.
2. **Authorization Server Metadata (RFC 8414)** — MUST provide. Returns all OAuth endpoints. Our shared FastAPI route.
3. **Dynamic Client Registration (RFC 7591)** — SHOULD support. MCP clients auto-register on first connect, receiving `client_id` and `client_secret`. Our shared route uses `resource` parameter to identify the connector.
4. **Resource Indicators (RFC 8707)** — Client MUST include `resource` parameter in auth/token requests. Our `TokenVerifier` validates token audience matches connector.
5. **PKCE** — REQUIRED for all clients (public and confidential).
6. **Token audience validation** — Our `TokenVerifier.verify_token()` enforces this (SDK middleware does NOT).
7. **Bearer tokens** — MUST use `Authorization: Bearer <token>` header on every request.

### Token Format

Tokens are **opaque strings** (not JWTs) — stored in the `mcp_token` table and validated via database lookup on each request. This enables immediate revocation and avoids the complexity of JWT audience/issuer validation.

The token record in the database contains:
- `user_id` — the authenticated user (from the OAuth flow, may differ from connector owner)
- `connector_id` — which connector this token was issued for
- `client_id` — which DCR-registered client obtained this token
- `scope` — OAuth scopes granted (`mcp:tools mcp:resources`)
- `token_type` — `access` or `refresh`
- `expires_at` — expiry timestamp

On each MCP request, the SDK's `BearerAuthBackend` extracts the token from the `Authorization` header and calls our `MCPTokenVerifier.verify_token()`, which does the database lookup, checks expiry/revocation, validates `resource` (connector audience), and verifies the connector is still active.

---

## Transport: Streamable HTTP

We focus exclusively on **Streamable HTTP** (MCP spec 2025-06-18). No SSE-only transport, no stdio.

### How It Works

Single endpoint per connector: `POST|GET|DELETE /mcp/{connector_id}/mcp`

External URL: `https://mcp.domain.com/{connector_id}/mcp` (production) or `https://domain.com/mcp/{connector_id}/mcp` (no subdomain)

| Method | Purpose |
|--------|---------|
| **POST** | Client sends JSON-RPC messages (tool calls, notifications). Server responds with JSON or SSE stream. |
| **GET** | Client opens SSE stream for server-initiated messages (optional, for notifications). |
| **DELETE** | Client terminates the MCP session. |

### Session Management

- Server assigns `Mcp-Session-Id` header on `InitializeResult` response
- Client includes `Mcp-Session-Id` on all subsequent requests
- MCP session ID maps to a platform chat session ID
- Session persists across multiple tool calls (conversation continuity)

### Required Headers

**Client → Server:**
- `Accept: application/json, text/event-stream`
- `Content-Type: application/json`
- `Authorization: Bearer <token>`
- `Mcp-Session-Id: <session-id>` (after initialization)
- `MCP-Protocol-Version: 2025-06-18`

**Server → Client:**
- `Mcp-Session-Id: <session-id>` (on InitializeResult)
- `Content-Type: application/json` or `Content-Type: text/event-stream`

### Response Modes

For tool calls (which take time because the agent processes them):
- **SSE stream** — Preferred. Server opens SSE stream, can send progress notifications, then the final tool result. This allows streaming the agent's response.
- **JSON response** — For fast operations (listing tools, reading resources).

---

## Libraries & Dependencies

### Python MCP SDK (`mcp` package)

**Package**: `mcp` on PyPI (v1.26.0+)
**Install**: `uv add "mcp[cli]"`
**Source**: [github.com/modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk)

The official MCP SDK provides the MCP server, transport, and auth middleware. We use the SDK for per-connector `MCPServer` instances in **Resource Server mode** (with `token_verifier`) and implement the OAuth Authorization Server ourselves as FastAPI routes.

### What the SDK Handles (We Don't Build)

| Feature | SDK Handles | Notes |
|---------|------------|-------|
| `/.well-known/oauth-protected-resource` | Yes (auto-generated per connector) | Via `create_protected_resource_routes()` when `resource_server_url` is set |
| `/mcp` Streamable HTTP endpoint | Yes | JSON-RPC, session management, SSE streaming |
| Bearer token extraction | Yes | `BearerAuthBackend` extracts from `Authorization` header |
| Token verification callback | Yes (calls our `TokenVerifier`) | `RequireAuthMiddleware` invokes our verifier |
| `Mcp-Session-Id` lifecycle | Yes | `StreamableHTTPSessionManager` |
| CORS on protected resource endpoint | Yes | Allows `*` |

### What We Build

| Feature | Where | Notes |
|---------|-------|-------|
| OAuth AS endpoints (metadata, register, authorize, token, revoke) | `backend/app/mcp/oauth_routes.py` | FastAPI router at `/mcp/oauth/` |
| `TokenVerifier` implementation | `backend/app/mcp/token_verifier.py` | DB lookup, resource validation, expiry/revocation check |
| `MCPServerRegistry` | `backend/app/mcp/server.py` | Creates/manages per-connector `MCPServer` instances, ASGI routing |
| Tool handlers (`send_message`) | `backend/app/mcp/tools.py` | Routes to `SessionService`/`MessageService` |
| Frontend consent page | `frontend/src/routes/oauth/mcp-consent.tsx` | Login + consent UI |
| Consent API | `backend/app/api/routes/mcp_consent.py` | `GET/POST /api/v1/mcp/consent/{nonce}` |
| Connector CRUD API | `backend/app/api/routes/mcp_connectors.py` | Owner management |

### Key SDK Components

| Component | Module | Usage |
|-----------|--------|-------|
| `MCPServer` | `mcp.server.mcpserver.server` | High-level server builder with `@tool`, `@resource`, `@prompt` decorators |
| `Context` | `mcp.server.mcpserver.server` | Tool handler context (progress reporting, logging, resource reading) |
| `AuthSettings` | `mcp.server.auth.settings` | OAuth configuration (`issuer_url`, `resource_server_url`) |
| `TokenVerifier` | `mcp.server.auth.provider` | Protocol we implement for token validation |
| `AccessToken` | `mcp.server.auth.provider` | Token data model returned by `verify_token()` |
| `get_access_token()` | `mcp.server.auth.middleware.auth_context` | Get current auth token in tool handlers (contextvar) |
| `MCPServer.streamable_http_app()` | | Returns Starlette ASGI app with RS routes + middleware |

### Per-Connector MCPServer in RS Mode

Each connector gets its own `MCPServer` instance configured in Resource Server mode:

```python
from mcp.server.mcpserver.server import MCPServer, Context
from mcp.server.auth.settings import AuthSettings

def create_mcp_server_for_connector(connector_id: str) -> MCPServer:
    """Create an MCPServer instance for a specific connector (RS mode)."""

    base_url = settings.MCP_SERVER_BASE_URL  # e.g., "https://mcp.domain.com"

    server = MCPServer(
        name=f"Agent MCP Server ({connector_id})",
        auth=AuthSettings(
            issuer_url=f"{base_url}/oauth",               # Shared OAuth AS
            resource_server_url=f"{base_url}/{connector_id}/mcp",  # This connector's resource
            # No client_registration_options or revocation_options — RS doesn't serve OAuth routes
        ),
        token_verifier=MCPTokenVerifier(connector_id),  # Our DB-backed verifier
        # NOTE: No auth_server_provider — mutually exclusive with token_verifier
    )

    # Register tools (shared across all connectors)
    register_mcp_tools(server, connector_id)

    return server
```

**Key point:** `auth_server_provider` and `token_verifier` are mutually exclusive in `MCPServer.__init__`. When `token_verifier` is provided:
- The SDK does NOT create OAuth routes (`/authorize`, `/token`, `/register`, `/revoke`)
- The SDK DOES create `/.well-known/oauth-protected-resource` (via `create_protected_resource_routes()`)
- The SDK DOES apply `RequireAuthMiddleware` with `BearerAuthBackend` on the MCP endpoint
- The `BearerAuthBackend` calls our `MCPTokenVerifier.verify_token()` for each request

### MCPServerRegistry

The registry manages per-connector `MCPServer` instances and acts as an ASGI dispatcher:

```python
import contextvars
from starlette.types import ASGIApp, Receive, Scope, Send

# Contextvar for downstream tool handlers
mcp_connector_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("mcp_connector_id")

class MCPServerRegistry:
    """Manages per-connector MCPServer instances and routes ASGI requests."""

    def __init__(self):
        self._servers: dict[str, ASGIApp] = {}  # connector_id → ASGI app

    async def get_or_create(self, connector_id: str) -> ASGIApp:
        """Get or lazily create an MCPServer ASGI app for a connector."""
        if connector_id not in self._servers:
            # Validate connector exists and is active
            connector = await get_connector(connector_id)
            if not connector or not connector.is_active:
                return None

            server = create_mcp_server_for_connector(connector_id)
            self._servers[connector_id] = server.streamable_http_app(
                streamable_http_path="/mcp"
            )
        return self._servers[connector_id]

    def remove(self, connector_id: str):
        """Remove a connector's MCPServer (on deactivation/deletion)."""
        self._servers.pop(connector_id, None)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """ASGI dispatcher: routes /mcp/{connector_id}/... to the right MCPServer."""
        if scope["type"] in ("http", "websocket"):
            path = scope["path"]  # e.g., "/{connector_id}/mcp" or "/{connector_id}/.well-known/..."
            parts = path.strip("/").split("/", 1)
            if not parts or not parts[0]:
                # No connector_id in path — return 404
                await send_404(scope, receive, send)
                return

            connector_id = parts[0]
            remaining_path = "/" + parts[1] if len(parts) > 1 else "/"

            # Get or create the MCPServer for this connector
            app = await self.get_or_create(connector_id)
            if app is None:
                await send_404(scope, receive, send)
                return

            # Set contextvar for tool handlers
            token = mcp_connector_id_var.set(connector_id)
            try:
                scope = dict(scope)
                scope["path"] = remaining_path
                await app(scope, receive, send)
            finally:
                mcp_connector_id_var.reset(token)
        else:
            await send_404(scope, receive, send)
```

### Mounting in FastAPI

```python
from starlette.routing import Mount

# 1. Create registry
mcp_registry = MCPServerRegistry()

# 2. Create shared OAuth routes (FastAPI router)
from app.mcp.oauth_routes import mcp_oauth_router
app.include_router(mcp_oauth_router, prefix="/mcp/oauth")

# 3. Mount registry as ASGI dispatcher for per-connector routes
app.mount("/mcp", mcp_registry)
```

**Note:** The `/mcp/oauth/...` routes (included via `include_router`) take precedence over the `/mcp/...` mount (Starlette routing precedence: routers before mounts). So OAuth requests go to our FastAPI routes, and per-connector requests go to the registry.

**Lifespan:** Each `MCPServer`'s session manager needs lifecycle management:

```python
@contextlib.asynccontextmanager
async def lifespan(app):
    # The registry manages MCPServer lifecycles internally
    yield
    # Cleanup: stop all session managers
    for connector_id, server_app in mcp_registry._servers.items():
        # ... cleanup logic
    pass

app = FastAPI(lifespan=lifespan)
```

### Accessing Auth in Tool Handlers

The SDK uses a `contextvars.ContextVar` to make the authenticated token available in tool handlers:

```python
from mcp.server.auth.middleware.auth_context import get_access_token

@server.tool()
async def send_message(message: str, ctx: Context) -> str:
    # Get connector context
    connector_id = mcp_connector_id_var.get()  # Our contextvar (from registry dispatcher)
    access_token = get_access_token()           # SDK contextvar (from auth middleware)

    # access_token.client_id  — which DCR client is calling
    # access_token.scopes     — granted OAuth scopes
    # connector_id            — which connector URL was hit

    # ctx.report_progress()   — send MCP progress notifications
    # ctx.log()               — send log messages to client
    ...
```

### `Mcp-Session-Id` and Platform Session Mapping

The SDK manages `Mcp-Session-Id` internally via `StreamableHTTPSessionManager`. The SDK:
- Generates a UUID session ID on first request (no existing header)
- Returns it in the `Mcp-Session-Id` response header
- Routes subsequent requests to the same transport instance

**We don't hook into SDK session lifecycle.** Instead, we create the platform session **lazily on first `send_message`**, keyed by the `Mcp-Session-Id`. The tool handler:
1. Gets the MCP session ID from `ctx.session` (the SDK session object)
2. Looks up `session.mcp_session_id` in the platform database
3. If not found → creates a new platform session, stores the mapping
4. If found → reuses the existing platform session

### Alternative: `fastapi-mcp` Library

**Package**: `fastapi-mcp` on PyPI (11.6k GitHub stars)

This library auto-exposes FastAPI endpoints as MCP tools. Not the right fit for us because we need custom tool definitions that map to agent conversations and per-connector routing/auth.

**Verdict**: Use the official `mcp` SDK directly.

---

## Database Schema

### New Table: `mcp_connector`

```sql
CREATE TABLE mcp_connector (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id        UUID NOT NULL REFERENCES agent(id) ON DELETE CASCADE,
    owner_id        UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
    name            VARCHAR(255) NOT NULL,
    mode            VARCHAR(20) NOT NULL DEFAULT 'conversation',  -- 'conversation' | 'building'
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    allowed_emails  JSONB NOT NULL DEFAULT '[]',                  -- Email addresses allowed to authenticate
    max_clients     INTEGER NOT NULL DEFAULT 1000,                -- Max DCR client registrations
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP
);

CREATE INDEX ix_mcp_connector_agent_id ON mcp_connector(agent_id);
```

### New Table: `mcp_oauth_client` (Dynamic Client Registration)

Stores OAuth clients that MCP tools (Claude Desktop, Cursor, etc.) register automatically via RFC 7591. Each client is associated with a connector via `connector_id` — DCR happens after resource discovery, so we know which connector the registration is for (from the `resource` parameter).

```sql
CREATE TABLE mcp_oauth_client (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    client_id       VARCHAR(255) UNIQUE NOT NULL,     -- Generated on registration
    client_secret_hash VARCHAR(255),                   -- SHA256 hash (NULL for public clients)
    client_name     VARCHAR(255),                      -- e.g., "Claude Desktop"
    redirect_uris   JSONB NOT NULL DEFAULT '[]',
    grant_types     JSONB NOT NULL DEFAULT '["authorization_code", "refresh_token"]',
    response_types  JSONB NOT NULL DEFAULT '["code"]',
    connector_id    UUID NOT NULL REFERENCES mcp_connector(id) ON DELETE CASCADE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_mcp_oauth_client_client_id ON mcp_oauth_client(client_id);
CREATE INDEX ix_mcp_oauth_client_connector_id ON mcp_oauth_client(connector_id);
```

### New Table: `mcp_auth_code` (Authorization Codes — short-lived)

```sql
CREATE TABLE mcp_auth_code (
    code            VARCHAR(255) PRIMARY KEY,
    client_id       VARCHAR(255) NOT NULL,
    user_id         UUID NOT NULL REFERENCES user(id),
    connector_id    UUID NOT NULL REFERENCES mcp_connector(id),
    redirect_uri    VARCHAR(2048) NOT NULL,
    code_challenge  VARCHAR(255) NOT NULL,     -- PKCE
    scope           VARCHAR(255),
    resource        VARCHAR(2048),             -- The resource URL (connector audience)
    expires_at      TIMESTAMP NOT NULL,
    used            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### New Table: `mcp_auth_request` (Server-side OAuth request storage)

Stores the full OAuth authorization request server-side to prevent parameter tampering. The frontend consent page receives only the opaque nonce.

```sql
CREATE TABLE mcp_auth_request (
    nonce           VARCHAR(255) PRIMARY KEY,          -- Random nonce, passed to frontend
    connector_id    UUID NOT NULL REFERENCES mcp_connector(id) ON DELETE CASCADE,
    client_id       VARCHAR(255) NOT NULL,
    redirect_uri    VARCHAR(2048) NOT NULL,
    code_challenge  VARCHAR(255) NOT NULL,             -- PKCE
    code_challenge_method VARCHAR(10) NOT NULL DEFAULT 'S256',
    scope           VARCHAR(255),
    state           VARCHAR(2048),                     -- OAuth state (opaque to us)
    resource        VARCHAR(2048),                     -- The resource URL (connector audience)
    expires_at      TIMESTAMP NOT NULL,                -- Short-lived (e.g., 10 minutes)
    used            BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
```

### New Table: `mcp_token` (Access & Refresh Tokens)

Stores OAuth tokens as opaque strings (not JWTs). Enables immediate revocation and full token lifecycle management.

```sql
CREATE TABLE mcp_token (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token           VARCHAR(255) UNIQUE NOT NULL,     -- Opaque token string (SHA256 of random bytes)
    token_type      VARCHAR(20) NOT NULL,             -- 'access' | 'refresh'
    client_id       VARCHAR(255) NOT NULL,            -- FK to mcp_oauth_client.client_id
    user_id         UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    connector_id    UUID NOT NULL REFERENCES mcp_connector(id) ON DELETE CASCADE,
    scope           VARCHAR(255),                     -- OAuth scopes: "mcp:tools mcp:resources"
    resource        VARCHAR(2048),                    -- The resource URL (connector audience)
    expires_at      TIMESTAMP NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_mcp_token_token ON mcp_token(token);
CREATE INDEX ix_mcp_token_connector_id ON mcp_token(connector_id);
CREATE INDEX ix_mcp_token_user_id ON mcp_token(user_id);
```

Access tokens (1-hour expiry) and refresh tokens (30-day expiry) are both stored here. Token validation on each MCP request is a simple `SELECT` by token value. Connector deletion CASCADE-deletes all tokens immediately.

### Updated Table: `session`

Add fields:
- `mcp_connector_id` (UUID, nullable, FK → `mcp_connector.id` SET NULL) — tracks which MCP connector created this session
- `mcp_session_id` (VARCHAR, nullable, unique) — the `Mcp-Session-Id` value assigned during MCP `initialize`. Used to look up the platform session on subsequent MCP requests within the same MCP session

---

## Backend Implementation Plan

### File Structure

```
backend/app/
├── models/
│   ├── mcp_connector.py           # MCPConnector model + schemas (includes allowed_emails)
│   ├── mcp_oauth_client.py        # MCPOAuthClient model (DCR registrations)
│   ├── mcp_token.py               # MCPToken model (opaque access + refresh tokens)
│   └── mcp_auth_code.py           # MCPAuthCode model + MCPAuthRequest (server-side storage)
│
├── services/
│   └── mcp_connector_service.py   # Connector CRUD + email ACL management
│
├── mcp/
│   ├── server.py                  # MCPServer factory + MCPServerRegistry (ASGI dispatcher)
│   ├── token_verifier.py          # MCPTokenVerifier — implements SDK TokenVerifier protocol
│   ├── oauth_routes.py            # Shared OAuth AS endpoints (FastAPI router at /mcp/oauth/)
│   └── tools.py                   # Tool handlers: send_message (routes to SessionService/MessageService)
│
├── api/routes/
│   ├── mcp_connectors.py          # Owner management: create/list/update/delete connectors + manage allowed_emails
│   └── mcp_consent.py             # POST /api/v1/mcp/consent/approve — frontend consent page callback
│
└── alembic/versions/
    └── xxxx_add_mcp_connector.py  # Migration
```

**Key differences from old design:**
- **No `dispatcher.py`** — replaced by `MCPServerRegistry` in `server.py` (handles both instance management and ASGI routing)
- **No `oauth_provider.py`** — we don't implement `OAuthAuthorizationServerProvider` anymore. OAuth AS is our own FastAPI routes in `oauth_routes.py`
- **New `token_verifier.py`** — implements the SDK's `TokenVerifier` protocol for RS mode
- **New `oauth_routes.py`** — full OAuth AS implementation as FastAPI endpoints

### Service Layer

#### MCPConnectorService

```python
class MCPConnectorService:
    @staticmethod
    async def create_connector(db, agent_id, owner_id, name, mode, allowed_emails=None) -> MCPConnector:
        """Creates connector with optional email ACL. Returns connector with MCP Server URL."""

    @staticmethod
    async def list_connectors(db, agent_id, owner_id) -> list[MCPConnector]:
        """List connectors with session counts and registered client counts."""

    @staticmethod
    async def update_connector(db, connector_id, owner_id, updates) -> MCPConnector:
        """Update connector. If is_active changes to False, remove from MCPServerRegistry."""

    @staticmethod
    async def delete_connector(db, connector_id, owner_id) -> None:
        """Deletes connector. CASCADE removes OAuth clients, auth codes, and tokens.
        Also removes from MCPServerRegistry."""

    @staticmethod
    async def get_connector(db, connector_id) -> MCPConnector | None

    @staticmethod
    async def update_allowed_emails(db, connector_id, owner_id, emails: list[str]) -> MCPConnector:
        """Update the email-based access control list."""

    @staticmethod
    async def check_email_access(db, connector_id, email: str) -> bool:
        """Check if an email is allowed to access a connector (is owner OR in allowed_emails)."""
```

### API Routes

#### Connector Management (Owner)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/agents/{agent_id}/mcp-connectors/` | Create connector |
| `GET` | `/api/v1/agents/{agent_id}/mcp-connectors/` | List connectors |
| `GET` | `/api/v1/agents/{agent_id}/mcp-connectors/{id}` | Get connector details |
| `PUT` | `/api/v1/agents/{agent_id}/mcp-connectors/{id}` | Update connector (name, mode, is_active, allowed_emails) |
| `DELETE` | `/api/v1/agents/{agent_id}/mcp-connectors/{id}` | Delete connector |

#### Consent Page Endpoints (Frontend → Backend)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/mcp/consent/{nonce}` | Frontend fetches auth request details for display (agent name, mode, client name, scopes) |
| `POST` | `/api/v1/mcp/consent/{nonce}/approve` | Frontend calls after user approves. Takes user auth. Checks email ACL. Issues auth code, returns redirect URL. |

#### Shared OAuth AS Endpoints (Under `/mcp/oauth/`)

These are our own FastAPI routes — NOT SDK-managed:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/mcp/oauth/.well-known/oauth-authorization-server` | AS metadata (RFC 8414) |
| `POST` | `/mcp/oauth/register` | DCR (RFC 7591) — `resource` param identifies connector |
| `GET` | `/mcp/oauth/authorize` | OAuth authorize — stores request, redirects to frontend consent |
| `POST` | `/mcp/oauth/token` | Token exchange — code→token, refresh→token |
| `POST` | `/mcp/oauth/revoke` | Token revocation |

#### SDK-Managed Endpoints (Under `/mcp/{connector_id}/`)

These are handled by the per-connector `MCPServer` instances via `MCPServerRegistry`:

| Method | Path | Description | Handled by |
|--------|------|-------------|------------|
| `GET` | `/.well-known/oauth-protected-resource` | Protected Resource Metadata (RFC 9728) | SDK auto (points to shared AS) |
| `POST` | `/mcp` | MCP Streamable HTTP (JSON-RPC) | SDK → tool handlers (via `TokenVerifier`) |
| `GET` | `/mcp` | MCP SSE stream (server→client) | SDK auto |
| `DELETE` | `/mcp` | Terminate MCP session | SDK auto |

### MCP ↔ Platform Session Mapping

```
MCP Client connects to connector (initialize → Mcp-Session-Id assigned)
    │
    │  Backend maps Mcp-Session-Id → platform session (created on first tool call)
    │
    ├─ tools/list → Returns agent's MCP tools
    │
    ├─ tools/call "send_message" {message: "..."}       ← first call in this MCP session
    │   │
    │   ├─ Lookup platform session by Mcp-Session-Id → not found
    │   ├─ SessionService.create_session(
    │   │     environment_id=agent.active_env,
    │   │     user_id=connector.owner_id,      ← session belongs to owner (like guest sessions)
    │   │     mode=connector.mode,
    │   │     mcp_connector_id=connector.id,
    │   │     integration_type="mcp"
    │   │   )
    │   ├─ Store mapping: Mcp-Session-Id → platform session ID
    │   │
    │   ├─ MessageService.stream_message_with_events(session, message)
    │   │   ├─ notifications/progress: "Agent is processing..."
    │   │   ├─ notifications/progress: "Running tool X..."
    │   │   └─ Agent environment completes → final result
    │   │
    │   └─ Return: {content: "Agent response text"}
    │
    ├─ tools/call "send_message" {message: "..."}       ← subsequent call, same MCP session
    │   │
    │   ├─ Lookup platform session by Mcp-Session-Id → found (conversation continues)
    │   └─ MessageService.stream_message_with_events(existing_session, message)
    │
    └─ resources/read "workspace://files/main.py"
        └─ WorkspaceService.get_file(environment_id, "main.py")
```

---

## Frontend Implementation

### Integrations Tab Extension

Add an **MCP Connectors** card to `AgentIntegrationsTab.tsx`, alongside the existing A2A, Access Tokens, Email, and Guest Share cards.

#### MCPConnectorsCard Component

```
MCPConnectorsCard
├── Header: "MCP Connectors" + description
├── Create button → Dialog
│   ├── Name input
│   ├── Mode selector (Conversation / Building)
│   └── Allowed Emails input (comma-separated or chips, empty = owner only)
├── Connector list
│   ├── Name + mode badge
│   ├── MCP Server URL (copyable): {MCP_SERVER_BASE_URL}/{id}/mcp
│   ├── Status badge (Active / Inactive)
│   ├── Allowed emails list (editable)
│   │   ├── "Owner only" indicator when empty
│   │   └── Email chips with add/remove
│   ├── Registered clients count (how many MCP tools have connected)
│   ├── Session count
│   └── Actions: Toggle active, Edit allowed emails, Delete
```

### User Flow

1. Navigate to Agent → Integrations tab
2. Click "Create MCP Connector"
3. Choose name, mode, and optionally add allowed email addresses
4. Copy the **MCP Server URL** (that's the only thing needed)
5. Share the URL with allowed users (they must be on the email list to authenticate)
6. In Claude Desktop / Cursor / etc.: Settings → Connectors → Add → paste URL
7. MCP client auto-discovers OAuth metadata, auto-registers via DCR, opens browser
8. User logs in with their **own platform credentials** — backend checks their email against connector's `allowed_emails`
9. Consent screen shows: agent name, connector mode, MCP client name, requested permissions
10. User approves → MCP client receives access token, starts using agent tools

**Sharing via email list**: The connector owner manages who can access the connector by adding/removing email addresses in the UI. This is more secure than sharing a URL as the sole access control — even if the URL leaks, unauthorized users cannot authenticate.

---

## Protocols & Standards Reference

| Standard | RFC/Spec | Role in Our Implementation |
|----------|----------|---------------------------|
| **MCP Streamable HTTP** | [MCP Spec 2025-06-18 Transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http) | Transport layer — POST/GET/DELETE on single endpoint |
| **MCP Authorization** | [MCP Spec 2025-06-18 Auth](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) | OAuth flow requirements for MCP servers |
| **OAuth 2.1** | [draft-ietf-oauth-v2-1-13](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-13) | Core auth framework |
| **PKCE** | [OAuth 2.1 §7.5.2](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-13#section-7.5.2) | Proof Key for Code Exchange — required |
| **Protected Resource Metadata** | [RFC 9728](https://datatracker.ietf.org/doc/html/rfc9728) | Server advertises auth server location (SDK auto-generates per connector) |
| **Auth Server Metadata** | [RFC 8414](https://datatracker.ietf.org/doc/html/rfc8414) | Client discovers auth endpoints (our shared AS) |
| **Dynamic Client Registration** | [RFC 7591](https://datatracker.ietf.org/doc/html/rfc7591) | MCP clients auto-register on first connect (our shared AS, `resource` param identifies connector) |
| **Resource Indicators** | [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html) | Token audience binding to specific connector's MCP server |
| **Token Revocation** | [RFC 7009](https://datatracker.ietf.org/doc/html/rfc7009) | OAuth token revocation endpoint (our shared AS) |
| **JSON-RPC 2.0** | [jsonrpc.org](https://www.jsonrpc.org/specification) | Message format for MCP protocol |

---

## Phased Implementation Plan

### Phase 1: Core MCP Server (MVP)

**Goal**: A working MCP endpoint that Claude Desktop can connect to.

1. **Database**: `mcp_connector` (with `allowed_emails`) + `mcp_oauth_client` + `mcp_auth_code` + `mcp_token` + `mcp_auth_request` tables + migration
2. **Models**: MCPConnector, MCPOAuthClient, MCPToken, MCPAuthCode, MCPAuthRequest SQLModel + schemas
3. **Connector CRUD**: API routes for creating/managing connectors (`/api/v1/agents/{agent_id}/mcp-connectors/`), including `allowed_emails` management
4. **Shared OAuth AS routes** (`/mcp/oauth/...`):
   - `/.well-known/oauth-authorization-server` — AS metadata
   - `/register` — DCR with `resource` parameter to identify connector, enforces `max_clients`
   - `/authorize` — stores auth request in `mcp_auth_request` (keyed by nonce), redirects to frontend consent page
   - `/token` — validates client credentials, PKCE, exchanges code for opaque tokens, stores in `mcp_token`
   - `/revoke` — marks token as revoked
5. **MCPTokenVerifier**: Implements SDK `TokenVerifier` protocol — DB lookup, resource validation (connector audience), expiry/revocation check, connector `is_active` check
6. **MCPServerRegistry**: Creates/manages per-connector `MCPServer` instances in RS mode, ASGI dispatcher routing `connector_id` to the right instance
7. **MCP Server**: Per-connector `MCPServer` instances with `send_message` tool
   - Each instance: `token_verifier=MCPTokenVerifier`, `auth=AuthSettings(issuer_url=shared_oauth, resource_server_url=per_connector)`
   - SDK auto-generates `/.well-known/oauth-protected-resource` per connector
   - Tool handler routes to SessionService/MessageService
   - SSE streaming with `ctx.report_progress()` for long-running operations
   - Message queuing for concurrent calls on same session
   - Auto-start agent environment with streaming status updates
   - Lazy platform session creation on first `send_message` (keyed by MCP session)
8. **Frontend consent page**: New route `/oauth/mcp-consent` — login + approval UI
9. **Consent callback**: `POST /api/v1/mcp/consent/{nonce}/approve` — checks email ACL, issues auth code after user approval
10. **Frontend**: MCPConnectorsCard in Integrations tab with email-based access management UI
11. **Token cleanup**: Background job to purge expired tokens from `mcp_token`
12. **Configuration**: `MCP_SERVER_BASE_URL` in backend `.env` + `VITE_MCP_SERVER_BASE_URL` in frontend `.env`
13. **Testing**: Manual test with Claude Desktop via Pinggy tunnel

### Phase 2: Enhanced Tools & Resources

1. **Workspace resources**: `resources/list` and `resources/read` for workspace files
2. **Session management tools**: `list_sessions`, `get_session_status`
3. **Streaming progress**: Use MCP progress notifications during long tool calls
4. **Interrupt support**: `interrupt` tool
5. **File upload**: `upload_file` tool

### Phase 3: Advanced Features

1. **Prompt templates**: Expose agent prompts via MCP `prompts/list`
2. **External OAuth providers**: Auth0/Keycloak integration for enterprise (the AS/RS separation makes this straightforward — swap out our OAuth routes for an external AS, keep the `TokenVerifier` pattern)
3. **Rate limiting**: Per-connector rate limits
4. **Usage tracking**: Token usage, request counts per connector
5. **Webhook notifications**: Notify owner when connector is used

---

## Security Considerations

### Client Registration Security

- MCP clients auto-register via Dynamic Client Registration (RFC 7591) at the shared `/mcp/oauth/register` endpoint
- `resource` parameter in DCR request identifies which connector — limits are enforced per connector
- `client_secret` stored as SHA256 hash only in `mcp_oauth_client` table
- Each registered client is scoped to a single connector (CASCADE on delete)
- Client credentials validated on every token exchange request
- Connector owner can see registered clients and revoke them

### Token Security

- OAuth tokens are **opaque strings** stored in the `mcp_token` database table (not JWTs)
- Tokens validated via database lookup on every request — enables immediate revocation
- Short-lived access tokens (1 hour) + refresh tokens (30 days)
- Token revocation supported (RFC 7009) — mark token as revoked. Immediate effect, no waiting for JWT expiry
- Connector deletion CASCADE-deletes all tokens immediately
- PKCE prevents authorization code interception

### Resource Validation in TokenVerifier

**Critical:** The SDK's `RequireAuthMiddleware` does NOT validate the `resource` field on tokens. It only uses `resource_metadata_url` for the `WWW-Authenticate` response header. This means a token issued for connector A could theoretically be used on connector B if we don't validate.

Our `MCPTokenVerifier.verify_token()` MUST:
1. Look up the token's `connector_id` from the database
2. Build the expected resource URL: `{MCP_SERVER_BASE_URL}/{connector_id}/mcp`
3. Compare against the connector's `resource_server_url` from `AuthSettings`
4. Reject the token if they don't match

This ensures tokens are audience-bound to their specific connector.

### Email-Based Access Control

- Access to connectors is controlled by `allowed_emails` list on the connector model
- **Checked during OAuth authorize**: The `/oauth/authorize` endpoint (and consent approval callback) verifies the user's email is allowed
- **Owner always has access**: Connector owner bypasses the email check
- **Empty list = owner only**: Default is most restrictive
- **Revocable without URL change**: Remove an email to revoke access — no need to change the connector URL
- **Audit trail**: `mcp_token.user_id` tracks which user authenticated, even though sessions belong to the connector owner

### Session Isolation

- Each MCP session maps to exactly one platform session
- MCP clients can only access sessions created through their own connection
- No cross-session visibility between connections
- Mode enforcement: `conversation` connectors cannot access building mode

### MCP-Specific Security

- Validate `Origin` header on all requests (DNS rebinding prevention)
- `resource` parameter validated at multiple points: DCR, authorize, token exchange, and TokenVerifier
- HTTPS required for all auth endpoints (production)
- DCR client limit per connector (default 1000) prevents registration abuse

---

## Comparison with A2A Integration

| Aspect | A2A | MCP |
|--------|-----|-----|
| **Protocol** | A2A JSON-RPC (custom) | MCP JSON-RPC (standard) |
| **Transport** | HTTP + SSE | Streamable HTTP |
| **Auth** | Bearer JWT (custom tokens) | OAuth 2.1 + DCR (standard flow, opaque tokens, zero-config) |
| **Discovery** | AgentCard endpoint | MCP `initialize` + `tools/list` |
| **Interaction model** | Task-based (send message, get task status) | Tool-based (call tools, get results) |
| **Client support** | Custom A2A clients | Claude Desktop, Cursor, VS Code, etc. |
| **Session model** | Task = Session | MCP Session = Platform Session |
| **Streaming** | SSE events | SSE within Streamable HTTP |
| **Access control** | Access tokens (mode + scope) | MCP Connectors (mode, email-based ACL, sessions owned by connector owner) |
| **Use case** | Agent-to-agent delegation | AI tool calling our agent |

Both share the same underlying infrastructure: `SessionService`, `MessageService`, agent environments. The difference is the protocol spoken at the API boundary.

---

## Design Decisions

1. **Fixed tool set**: We use a fixed set of MCP tools (`send_message`, `list_sessions`, etc.) rather than auto-generating tools from `a2a_config.skills`. This keeps the MCP surface predictable, simplifies client UX, and avoids coupling MCP tool definitions to A2A skill configuration. The agent's capabilities are accessed through `send_message` — the agent itself decides which skills to invoke based on the message content.

2. **MCP session = platform session**: The MCP session ID (assigned via `Mcp-Session-Id` header on `InitializeResult`) maps directly to a single platform chat session. No `session_id` parameter on `send_message` — each MCP session is one continuous conversation. If the MCP client reconnects with a new MCP session, a new platform session is created. This keeps the model simple and aligns with how MCP clients expect sessions to work.

3. **MCP progress notifications for long-running operations**: Agent processing can take 30+ seconds. We use MCP progress notifications (`notifications/progress`) streamed over SSE within the Streamable HTTP response. This gives the MCP client real-time feedback (e.g., "Agent is processing...", "Running tool X...") while waiting for the final tool result. The SSE stream stays open until the agent completes, then sends the final JSON-RPC result.

4. **Custom OAuth consent screen**: During the OAuth `/authorize` flow, the shared AS stores the full authorization request server-side (keyed by a random nonce) and redirects to the frontend consent page with only the nonce. The frontend fetches request details via API, shows a consent page (agent name, connector mode, MCP client name, requested scopes), and on approval calls the backend to issue the auth code. This prevents parameter tampering since the frontend never handles sensitive OAuth params directly.

5. **Opaque connector ID in URL**: The MCP Server URL uses the opaque UUID connector ID: `{MCP_SERVER_BASE_URL}/{connector_id}/mcp`. No human-readable slugs. This avoids name collision issues, renaming invalidation, and information leakage about the agent. The connector name is only visible in our UI and in the OAuth consent screen.

6. **One MCPServer per connector (RS mode)**: Each connector gets its own `MCPServer` instance configured with `token_verifier` (Resource Server mode) rather than sharing a single instance with `auth_server_provider`. This is required because the SDK's `AuthSettings` binds `issuer_url` and `resource_server_url` per instance — a single instance cannot serve different `resource_server_url` values for different connectors. The per-instance approach also provides natural isolation between connectors and simplifies the `TokenVerifier` (each verifier knows its connector).

7. **Shared OAuth Authorization Server**: Instead of using the SDK's `OAuthAuthorizationServerProvider` (which is per-MCPServer-instance), we implement OAuth endpoints as shared FastAPI routes at `/mcp/oauth/`. This avoids duplicating OAuth logic per connector, provides a single set of well-known endpoints for all connectors, and allows us to use the `resource` parameter (RFC 8707) to identify which connector a DCR/authorize/token request is for. The AS/RS separation is the canonical pattern shown in the SDK's `examples/servers/simple-auth/` example.

8. **Email-based access control**: Connector access is controlled by an `allowed_emails` list rather than URL-as-security-boundary. This is more secure (URLs leak easily), more auditable (explicit list of who has access), and more manageable (revoke access by removing an email, no need to re-create the connector). The check happens during OAuth authorize, so unauthorized users cannot obtain tokens even if they have the URL.

9. **Resource validation in TokenVerifier**: The SDK's `RequireAuthMiddleware` does NOT enforce token audience (`resource` field) — it only uses the resource metadata URL for the `WWW-Authenticate` header. Our `MCPTokenVerifier.verify_token()` must explicitly validate that the token's `connector_id` matches the connector being accessed. Without this, a token issued for one connector could be used on another. This is a critical security boundary.

---

## Resolved Questions

The following questions were identified during concept design and have been resolved.

### OQ-1: OAuth consent screen — where does it render?

**Status:** `RESOLVED`

**Decision: Redirect to the frontend SPA.**

The shared OAuth AS `/oauth/authorize` endpoint:

1. Stores the full authorization request server-side in `mcp_auth_request` table (connector_id, client_id, redirect_uri, code_challenge, scope, state, resource) keyed by a **random nonce**
2. Returns a redirect URL to the frontend: `{FRONTEND_HOST}/oauth/mcp-consent?nonce={nonce}`

The frontend consent page:

1. Fetches authorization request details from backend using the nonce (gets agent name, connector mode, client name, requested scopes)
2. Handles login if user is not already authenticated
3. Shows consent screen with: agent name, connector permissions (mode), MCP client name (from DCR `client_name`), requested scopes
4. On user approval, calls `POST /api/v1/mcp/consent/approve` with the nonce + user auth
5. Backend validates nonce, **checks email-based access control** (user must be owner or in `allowed_emails`), issues auth code (stored in `mcp_auth_code`), returns the MCP client's `redirect_uri` with auth code and state
6. Frontend redirects to that URL

**Security:** The frontend never sees or handles sensitive OAuth parameters (redirect_uri, code_challenge). It only passes the opaque nonce. All parameters are validated server-side when issuing the auth code. This prevents parameter tampering.

**Implication:** The frontend needs a new public route `/oauth/mcp-consent` that works outside the normal `_layout` auth guard. This route must handle the case where the user is not yet logged in (redirect to login first, then return to consent). The backend needs a `mcp_auth_request` table for server-side storage and a `GET /api/v1/mcp/consent/{nonce}` endpoint to fetch request details for display.

---

### OQ-2: Who can authenticate via MCP OAuth?

**Status:** `RESOLVED`

**Decision: Only users whose email is in the connector's `allowed_emails` list (or the connector owner).**

Access is controlled via an email-based allowed list on each connector:

- **Owner always has access** — the connector owner can always authenticate, regardless of `allowed_emails`
- **Empty `allowed_emails` = owner only** — the default, most restrictive setting
- **Sharing**: the owner adds email addresses to `allowed_emails` to grant access
- **Access check**: performed during the OAuth authorize flow (consent approval step). If the user's email is not allowed, they get a 403 error.
- **Sessions belong to the owner**: Session `user_id` is set to `connector.owner_id`, not the authenticated user. The owner has full access to all sessions — they can see them in the UI, review conversation history, etc.
- **Authenticated user is tracked**: The `mcp_token` table records which user authenticated (`user_id` on the token). This provides an audit trail of who is using the connector.

**Revocation**: Remove an email from `allowed_emails` to prevent future authentication. Existing tokens for that user remain valid until they expire (or the owner can manually revoke tokens). For immediate revocation, the owner can deactivate the connector (all tokens invalidated via `is_active` check in `TokenVerifier`).

**Implication:** The connector management UI needs an `allowed_emails` editor (email chips with add/remove). The consent page shows the agent name and connector permissions so the authenticated user knows what they're authorizing.

---

### OQ-3: Refresh token storage and token revocation

**Status:** `RESOLVED`

**Decision: Custom token storage in the database — not stateless JWTs.**

Both access tokens and refresh tokens are stored in a new `mcp_token` table. Tokens are opaque strings (not JWTs) — the backend looks them up in the database on every request. This provides full compliance with OAuth 2.1 token lifecycle:

- **Access tokens** (1-hour expiry) — stored in `mcp_token`, looked up on each MCP request via `TokenVerifier`
- **Refresh tokens** (30-day expiry) — stored in `mcp_token`, used to issue new access tokens via shared `/oauth/token`
- **Revocation** — mark the token as revoked. Immediate effect, no waiting for JWT expiry
- **Connector deactivation/deletion** — CASCADE delete removes all tokens instantly. `TokenVerifier` also checks `is_active`
- **Token Revocation endpoint** (RFC 7009) — implemented at `/mcp/oauth/revoke`

This is simpler to reason about than JWTs for this use case: we already hit the database for connector validation, so the token lookup adds minimal overhead.

**New table: `mcp_token`** (see Database Schema section).

---

### OQ-4: MCP SDK mounting vs. dynamic `connector_id` routing

**Status:** `RESOLVED`

**Decision: MCPServerRegistry — one MCPServer instance per connector, with ASGI dispatcher.**

The original design used a single shared `MCPServer` instance with a custom ASGI dispatcher. This was flawed because the SDK's `AuthSettings` (specifically `issuer_url` and `resource_server_url`) is bound per `MCPServer` instance — a single instance cannot serve different OAuth identities for different connectors.

**Revised approach — MCPServerRegistry:**

1. Each connector gets its own `MCPServer` instance, created lazily on first request
2. Each instance is configured in RS mode: `token_verifier=MCPTokenVerifier(connector_id)`, `auth=AuthSettings(issuer_url=shared_oauth_url, resource_server_url=per_connector_url)`
3. The `MCPServerRegistry` acts as an ASGI dispatcher: extracts `connector_id` from the URL path, routes to the correct `MCPServer` instance, sets a contextvar for tool handlers
4. On connector deactivation/deletion, the registry removes the instance

See the [MCPServerRegistry](#mcpserverregistry) section for the full implementation.

**Why not a single shared instance?**
- `AuthSettings.resource_server_url` must be unique per connector (it's the token audience)
- `AuthSettings.issuer_url` could theoretically be shared, but the SDK generates `/.well-known/oauth-protected-resource` based on `resource_server_url`, which must differ per connector
- The SDK's middleware uses these settings for the `WWW-Authenticate` header and resource metadata

**Lifecycle considerations:**
- Instances are created lazily (first request for a connector creates it)
- Instances are removed when connectors are deactivated/deleted
- Each instance has its own `StreamableHTTPSessionManager` — this is fine since sessions are connector-scoped anyway

---

### OQ-5: Concurrent `send_message` calls on same MCP session

**Status:** `RESOLVED`

**Decision: Queue and serialize messages.**

Concurrent `send_message` calls on the same MCP session are queued and processed sequentially, similar to how we handle pending messages when the agent environment is activating. The flow:

1. First `send_message` arrives → starts processing immediately, SSE stream stays open
2. Second `send_message` arrives while first is processing → queued, SSE stream stays open with progress notification: `"Message queued, waiting for previous message to complete..."`
3. First completes → second starts processing, progress notifications resume
4. Second completes → result returned

This mirrors the existing pending message queue pattern used for agent environment activation. The MCP client sees progress notifications for both queuing and processing, so it knows the system is responsive.

**Note:** If the queue grows beyond a reasonable limit (e.g., 5 pending messages), reject with an MCP error to prevent unbounded resource usage.

---

### OQ-6: `send_message` return format and streaming

**Status:** `RESOLVED`

**Decision: Stream partial results via SSE, return multi-modal content.**

The `send_message` tool uses MCP's streaming capabilities to deliver results progressively, similar to how we render partial results in the frontend UI:

**Streaming:** The tool result is delivered as an SSE stream within the Streamable HTTP response. As the agent produces output, partial text is sent via MCP progress notifications (`notifications/progress`). This gives the MCP client real-time feedback while the agent is working. The final tool result contains the complete response.

**Return format:** The tool result uses MCP's multi-content support:

- **Text content** (`TextContent`) — the agent's primary text response. Internal tool invocation logs (e.g., "Agent used tool X") are formatted as text and included in the response.
- **Image content** (`ImageContent`) — if the agent produces images, they are included as base64-encoded image content parts.
- **Embedded resources** (`EmbeddedResource`) — for file artifacts the agent creates/modifies, reference them as workspace resource URIs so the MCP client can fetch them separately.

**Agent errors:** Use MCP's `isError: true` on the tool result for hard errors (environment crash, timeout, provisioning failure). Agent-level errors that produce a text response (e.g., "I couldn't complete the task because...") are returned as normal text content — the agent decided the outcome, even if it's a failure.

**Long responses:** No truncation. The MCP protocol handles large responses natively. If a response includes large file contents, prefer returning a resource URI reference instead of inline text.

---

### OQ-7 & OQ-8: Connector scope — removed

**Status:** `RESOLVED`

**Decision: Remove the `scope` field from the connector model entirely.**

Session visibility is limited to the MCP connection itself. Each MCP session maps to exactly one platform session, and MCP clients can only see sessions they created through their own connection. There is no cross-session visibility.

This eliminates both problems:
- No naming collision between "connector scope" and "OAuth scope" — `scope` only means OAuth scope (`mcp:tools`, `mcp:resources`)
- No ambiguity about what `general` means — it doesn't exist

If cross-session visibility is needed in the future (e.g., a `list_sessions` tool in Phase 2), it can be added as a new connector property at that time with a clear, non-overloaded name.

**Impact on model:** The `mcp_connector` table has: `id`, `agent_id`, `owner_id`, `name`, `mode`, `is_active`, `allowed_emails`, `max_clients`, `created_at`, `updated_at`.

---

### OQ-9: DCR abuse / rate limiting

**Status:** `RESOLVED`

**Decision: Max client limit per connector, enforced at the shared DCR endpoint.**

DCR is handled by the shared `/mcp/oauth/register` endpoint, which uses the `resource` parameter to identify the connector. The endpoint enforces a maximum number of registered clients per connector:

- **Default limit:** 1000 registered clients per connector
- **Stored on connector:** `max_clients` field on `mcp_connector` (default 1000), can be increased per-connector if needed
- **Enforcement:** `POST /mcp/oauth/register` extracts `connector_id` from `resource` URL, checks `SELECT COUNT(*) FROM mcp_oauth_client WHERE connector_id = ?`. If >= `max_clients`, return HTTP 429 with `{"error": "too_many_clients", "error_description": "Maximum number of registered clients reached for this connector."}`
- **Owner management:** The connector owner can view registered clients in the UI and delete unused ones to free up slots

This is simple, per-connector, and sufficient for Phase 1. Additional IP-based rate limiting can be added at the nginx level later.

---

### OQ-10: Agent environment not running

**Status:** `RESOLVED`

**Decision: Auto-start with streaming status updates.**

The backend auto-starts the agent environment on `send_message` if it's not running, identical to the A2A and guest session behavior. Progress is communicated via MCP streaming:

1. `send_message` called → backend checks environment status
2. If environment is not running → start it, stream progress notifications:
   - `"Starting agent environment..."`
   - `"Environment activating..."` (periodic heartbeat)
   - `"Environment ready, processing message..."`
3. Once environment is ready → send message, stream agent processing progress as normal
4. If environment fails to start → return MCP tool result with `isError: true` and error description (e.g., `"Failed to start agent environment: provisioning error"`)

**Timeout:** Same as A2A/guest sessions (configurable, default ~120 seconds for environment startup). If exceeded, return error.

**Message queuing integration:** If the environment is activating and multiple `send_message` calls arrive, they are queued (per OQ-5). The first message triggers the activation; queued messages are processed once the environment is ready.

---

**Document Version:** 2.0
**Created:** 2026-02-25
**Status:** Concept / Pre-Implementation
**Related Docs:**
- [A2A Integration](a2a/a2a_integration.md)
- [A2A Access Tokens](a2a/agent_integration_access_tokens.md)
- [Guest Share Sessions](agent-sessions/agent_guest_sessions.md)
- [Streaming Architecture](realtime-events/frontend_backend_agentenv_streaming.md)
- [Business Logic](agent-sessions/business_logic.md)
