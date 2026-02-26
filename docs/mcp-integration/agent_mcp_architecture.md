# Agent MCP Connector — Architecture Overview

## What It Does

Exposes platform agents as **remote MCP servers** so that any MCP-compatible client — Claude Desktop, Claude.ai, Cursor, Windsurf, VS Code Copilot — can connect to an agent and interact with it as a tool provider. The MCP client sends tool calls, the agent processes them via its environment (Docker container running Google ADK / Claude Code), and results stream back over the MCP protocol.

This is the MCP counterpart of our A2A integration. While A2A is agent-to-agent task delegation (JSON-RPC), MCP is tool-use — an AI client calls our agent as a tool. Both share the same underlying infrastructure (SessionService, MessageService, agent environments), but speak different protocols at the API boundary.

### Why MCP

- **Universal client support** — Claude Desktop, Claude.ai, Cursor, and others already support adding remote MCP servers
- **Zero-config for the user** — paste one URL into the MCP client; it auto-discovers OAuth, auto-registers, handles auth
- **OAuth-based auth** — standardized authentication, no manual token management
- **Richer than chat** — MCP supports tools, resources, and prompts (not just messages)

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

### AS/RS Separation

The architecture separates OAuth into two distinct roles:

| Role | Implementation | URL Space |
|------|---------------|-----------|
| **Authorization Server (AS)** | Our own FastAPI routes | `/mcp/oauth/...` (shared, one set of endpoints for all connectors) |
| **Resource Server (RS)** | One MCPServer instance per connector, using TokenVerifier | `/mcp/{connector_id}/...` (per-connector) |

**Why this split:**
- The MCP SDK binds `issuer_url` and `resource_server_url` per MCPServer instance — a single instance can't serve different connectors
- Each connector needs its own `resource_server_url` (token audience), but all connectors share one OAuth endpoint set
- The SDK auto-generates `/.well-known/oauth-protected-resource` per connector, pointing to the shared AS
- Our FastAPI OAuth routes handle all authorization logic — DCR, authorize, token exchange, revocation

---

## Core Concepts

### MCP Connector

An **MCP Connector** is a named, scoped access point that exposes an agent as an MCP server. It is the MCP equivalent of an A2A access token or a guest share link.

| Property | Description |
|----------|-------------|
| **name** | Display name (e.g., "Cursor - conversation", "Claude Desktop - building") |
| **mode** | `conversation` or `building` — controls which agent mode MCP sessions use |
| **is_active** | Enable/disable without deletion |
| **allowed_emails** | Email addresses allowed to authenticate (empty = owner only) |
| **max_clients** | Maximum DCR client registrations allowed (default 10) |
| **MCP Server URL** | `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` — the only thing the user copies |

**Why multiple connectors?** Different MCP clients may need different permission levels:
- A "conversation" connector for quick tasks (cheaper, faster)
- A "building" connector for development work (full tool access)
- Separate connectors for different users or teams (each with its own email list and session isolation)

### Email-Based Access Control

Access to a connector is controlled by an `allowed_emails` list, not by URL secrecy:

- **Owner always has access** — bypasses the email check
- **Empty list = owner only** — default, most restrictive
- **Explicit sharing** — owner adds email addresses to grant access
- **Checked during OAuth consent** — unauthorized users cannot obtain tokens even if they have the URL
- **Revocable without URL change** — remove an email to revoke access; no need to re-create the connector

This is more secure than URL-as-security-boundary because URLs can leak inadvertently (browser history, chat logs, screenshots), while the email list gives explicit, auditable control.

### Mapping MCP Primitives to the Platform

| MCP Primitive | Platform Mapping |
|---------------|-----------------|
| **Tool** (`send_message`) | Send a message to the agent, receive a response |
| **MCP Session** | Platform Session (one MCP session = one chat session) |
| **Resource** (future) | Agent workspace files |
| **Prompt** (future) | Agent prompt templates |

### Tool Design

The agent exposes a single primary tool:

**`send_message`** — Send a message to the agent and receive a response. The agent processes the request using its configured capabilities, tools, and knowledge.

Session continuity is automatic — all `send_message` calls within the same MCP session go to the same platform chat session. New MCP session = new conversation.

---

## Authentication & Authorization Flow

### End-to-End Flow

```
User creates MCP Connector in our UI → copies MCP Server URL
    │
    ▼

MCP Client                  Per-Connector RS                 Shared OAuth AS
    │                        /{connector_id}/                /oauth/
    │                           │                                │
    │──POST /mcp (no token)────►│                                │
    │◄──401 + WWW-Authenticate──│                                │
    │                           │                                │
    │──GET /.well-known/────────►│                                │
    │  oauth-protected-resource │                                │
    │◄──{authorization_servers}─│                                │
    │                           │                                │
    │──GET .well-known/oauth-authorization-server────────────────►│
    │◄──{authorize, token, registration_endpoint}─────────────────│
    │                           │                                │
    │──POST /register (+ resource param)─────────────────────────►│
    │◄──{client_id, client_secret}────────────────────────────────│
    │                           │                                │
    │  [Browser: /authorize + client_id + PKCE + resource]───────►│
    │  [Backend checks email ACL, redirects to consent page]      │
    │  [User logs in + approves on consent screen]                │
    │◄─[Redirect with auth code]──────────────────────────────────│
    │                           │                                │
    │──POST /token + PKCE verifier───────────────────────────────►│
    │◄──{access_token, refresh_token}─────────────────────────────│
    │                           │                                │
    │──POST /mcp (Bearer token)►│                                │
    │  [TokenVerifier validates] │                                │
    │◄──MCP response────────────│                                │
```

The MCP client handles the entire flow automatically — the user only pastes the URL.

### OAuth Endpoints (Shared AS)

| Endpoint | Purpose | Standard |
|----------|---------|----------|
| `GET /mcp/oauth/.well-known/oauth-authorization-server` | AS metadata — clients discover all endpoints | RFC 8414 |
| `POST /mcp/oauth/register` | Dynamic Client Registration — MCP clients auto-register | RFC 7591 |
| `GET /mcp/oauth/authorize` | Authorization — stores request, redirects to frontend consent | OAuth 2.1 |
| `POST /mcp/oauth/token` | Token exchange — auth code → tokens, refresh → new token | OAuth 2.1 |
| `POST /mcp/oauth/revoke` | Token revocation — immediate invalidation | RFC 7009 |

### Per-Connector Endpoints (RS, SDK-managed)

| Endpoint | Purpose |
|----------|---------|
| `GET /mcp/{connector_id}/.well-known/oauth-protected-resource` | Points MCP client to the shared AS (auto-generated by SDK) |
| `POST /mcp/{connector_id}/mcp` | MCP Streamable HTTP — tool calls, JSON-RPC |
| `GET /mcp/{connector_id}/mcp` | SSE stream for server-initiated notifications |
| `DELETE /mcp/{connector_id}/mcp` | Terminate MCP session |

### Token Model

Tokens are **opaque strings** (not JWTs) stored in the database:

| Token Type | Expiry | Purpose |
|------------|--------|---------|
| Access token | 1 hour | Bearer token on MCP requests |
| Refresh token | 30 days | Exchange for new access token |

Database-backed tokens enable immediate revocation (no waiting for JWT expiry) and are validated via lookup on each MCP request. The TokenVerifier additionally checks:
- Token not expired or revoked
- Token's connector matches the connector being accessed (cross-connector isolation)
- Connector is still active

### Consent Flow

When the OAuth `/authorize` endpoint is hit:

1. Backend stores the full OAuth request server-side (keyed by random nonce) — prevents parameter tampering
2. Redirects to frontend: `/oauth/mcp-consent?nonce={nonce}`
3. Frontend fetches consent details via API — shows agent name, connector mode, client name, scopes
4. User logs in (if needed) and approves
5. Backend checks email ACL (owner or in `allowed_emails`) and issues auth code
6. Browser redirects back to MCP client with auth code
7. MCP client exchanges code for tokens

---

## Session & Message Flow

### MCP ↔ Platform Session Mapping

```
MCP Client connects (initialize → Mcp-Session-Id assigned by SDK)
    │
    ├─ tools/list → Returns [send_message]
    │
    ├─ tools/call "send_message" {message: "..."}       ← first call
    │   │
    │   ├─ Look up platform session by connector → not found
    │   ├─ Create new platform session (mode from connector, integration_type="mcp")
    │   ├─ Link session to connector
    │   ├─ Send message to agent environment
    │   ├─ Stream response back
    │   └─ Return agent response
    │
    ├─ tools/call "send_message" {message: "..."}       ← subsequent call
    │   │
    │   ├─ Look up platform session by connector → found (conversation continues)
    │   └─ Send message to existing session
    │
    └─ [New MCP connection] → new platform session (no cross-session visibility)
```

**Key behaviors:**
- Each connector maintains one active platform session at a time
- Session belongs to the connector owner (like guest sessions)
- Agent environment auto-starts if not running
- Sequential message processing with per-session locking (concurrent calls queued)
- `mcp_token.user_id` tracks who authenticated (audit trail)

---

## URL Scheme & Configuration

### Routing Table

| URL Pattern | Handler | Purpose |
|-------------|---------|---------|
| `/mcp/oauth/...` | Our FastAPI routes | Shared OAuth AS (metadata, DCR, authorize, token, revoke) |
| `/mcp/{connector_id}/.well-known/...` | SDK auto-generated | Protected Resource Metadata |
| `/mcp/{connector_id}/mcp` | SDK MCPServer (per-connector) | MCP Streamable HTTP endpoint |
| `/api/v1/agents/{agent_id}/mcp-connectors/...` | Our FastAPI routes | Connector CRUD (frontend management) |
| `/api/v1/mcp/consent/{nonce}` | Our FastAPI routes | Consent page API |

**Important:** The `/mcp/` routes are for external MCP clients only. The frontend manages connectors via `/api/v1/` endpoints.

### `MCP_SERVER_BASE_URL` Configuration

All externally-facing MCP URLs are derived from one config variable:

| What | URL |
|------|-----|
| MCP Server URL (user copies this) | `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` |
| AS Metadata | `{MCP_SERVER_BASE_URL}/oauth/.well-known/oauth-authorization-server` |
| OAuth authorize / token / register | `{MCP_SERVER_BASE_URL}/oauth/...` |
| Token audience (resource param) | `{MCP_SERVER_BASE_URL}/{connector_id}/mcp` |

**Production (dedicated subdomain):**
```
MCP_SERVER_BASE_URL=https://mcp.domain.com
```
nginx proxies `mcp.domain.com` → `backend:8000/mcp/`

**Local development (tunnel):**
```
MCP_SERVER_BASE_URL=https://abc123.a.free.pinggy.link/mcp
```
Tunnel forwards to `localhost:8000/mcp/`

---

## Frontend

### Connector Management (Integrations Tab)

The **MCPConnectorsCard** lives in the agent's Integrations tab alongside A2A, Access Tokens, Email, and Guest Share cards.

**Features:**
- Create connector: name, mode (conversation/building), allowed emails
- List connectors with status badges (active/inactive), mode badges
- Copyable MCP Server URL (the one thing users paste into their MCP client)
- Allowed emails display as badges
- Toggle active/inactive, delete with confirmation

### OAuth Consent Page

Public route at `/oauth/mcp-consent` (outside normal auth guard):
- Displays: agent name, connector name/mode, client name, requested scopes
- Redirects to login if unauthenticated
- Authorize / Deny buttons
- On approval → redirects to MCP client's callback with auth code

---

## How It Fits With Other Integrations

| Aspect | A2A | MCP | Guest Sessions |
|--------|-----|-----|----------------|
| **Protocol** | A2A JSON-RPC | MCP JSON-RPC (standard) | WebSocket + REST |
| **Auth** | Bearer JWT (custom tokens) | OAuth 2.1 + DCR (zero-config) | Share links |
| **Client support** | Custom A2A clients | Claude Desktop, Cursor, etc. | Browser |
| **Interaction** | Task-based | Tool-based | Chat-based |
| **Access control** | Access tokens (mode + scope) | Email-based ACL | Share links with optional password |
| **Session ownership** | Access token owner | Connector owner | Guest or share creator |
| **Use case** | Agent-to-agent delegation | AI tool calling our agent | Human chat with agent |

All three share the same underlying services: SessionService, MessageService, agent environments.

---

## Security Model

### Authentication Layers

1. **Email ACL** — Only connector owner or users in `allowed_emails` can complete OAuth
2. **PKCE** — Required for all clients; prevents authorization code interception
3. **Client credentials** — DCR-issued `client_id` + `client_secret` (secret stored as SHA256 hash)
4. **Opaque tokens** — Database-backed, immediately revocable
5. **Token audience validation** — TokenVerifier ensures tokens are connector-scoped (cross-connector isolation)
6. **Connector active check** — Deactivated connectors reject all requests

### Cascade Behavior

- **Connector deleted** → All OAuth clients, auth codes, tokens CASCADE-deleted
- **Connector deactivated** → MCP server evicted from registry; TokenVerifier rejects all tokens
- **Email removed from ACL** → Existing tokens remain valid until expiry; for immediate revocation, deactivate the connector

### Session Isolation

- Each MCP connection creates its own platform session
- No cross-session visibility between connections
- Mode enforcement: connector mode determines session mode

---

## Design Decisions

1. **Fixed tool set** — `send_message` rather than auto-generating tools from agent config. Keeps the MCP surface predictable. The agent decides which capabilities to invoke based on the message.

2. **MCP session = platform session** — No `session_id` parameter on tools. Each MCP connection is one conversation. New connection = new session.

3. **Opaque tokens, not JWTs** — Database lookup on each request enables immediate revocation. We already hit the DB for connector validation, so token lookup adds minimal overhead.

4. **One MCPServer per connector** — Required because the SDK binds `resource_server_url` per instance. Also provides natural isolation and simplifies TokenVerifier.

5. **Shared OAuth AS** — Single set of OAuth endpoints for all connectors, using `resource` parameter (RFC 8707) to identify which connector. Avoids duplicating OAuth logic per connector.

6. **Email-based ACL over URL secrecy** — URLs leak easily. Email list gives explicit, auditable, revocable access control without changing the connector URL.

7. **Server-side OAuth request storage** — The consent page receives only an opaque nonce. All sensitive OAuth params stored server-side, preventing parameter tampering by the frontend.

8. **Sequential message processing** — Concurrent `send_message` calls on the same session are queued. Prevents race conditions in agent environment communication.

---

## Future Phases

### Phase 2: Enhanced Tools & Resources
- Workspace resources: `resources/list` and `resources/read` for agent workspace files
- Session management tools: `list_sessions`, `get_session_status`
- Interrupt support, file upload

### Phase 3: Advanced Features
- Prompt templates via MCP `prompts/list`
- External OAuth providers (Auth0/Keycloak) — swap AS, keep TokenVerifier
- Per-connector rate limiting and usage tracking

---

## Protocols & Standards

| Standard | RFC/Spec | Role |
|----------|----------|------|
| MCP Streamable HTTP | [MCP Spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports#streamable-http) | Transport layer |
| MCP Authorization | [MCP Spec 2025-06-18](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) | OAuth flow requirements |
| OAuth 2.1 | [draft-ietf-oauth-v2-1-13](https://datatracker.ietf.org/doc/html/draft-ietf-oauth-v2-1-13) | Core auth framework |
| PKCE | OAuth 2.1 §7.5.2 | Code exchange protection |
| Protected Resource Metadata | [RFC 9728](https://datatracker.ietf.org/doc/html/rfc9728) | Server → AS discovery |
| Auth Server Metadata | [RFC 8414](https://datatracker.ietf.org/doc/html/rfc8414) | Client → endpoint discovery |
| Dynamic Client Registration | [RFC 7591](https://datatracker.ietf.org/doc/html/rfc7591) | Auto-registration |
| Resource Indicators | [RFC 8707](https://www.rfc-editor.org/rfc/rfc8707.html) | Token audience binding |
| Token Revocation | [RFC 7009](https://datatracker.ietf.org/doc/html/rfc7009) | Token invalidation |

---

## Related Documentation

- `docs/agent_mcp_connector_concept.md` — Original concept document (detailed SDK analysis, resolved design questions)
- `docs/mcp-integration/implementation_plan.md` — Phased implementation plan
- `docs/mcp-integration/agent_mcp_connector.md` — Code-level implementation reference
- `docs/a2a/a2a_integration.md` — A2A integration (comparable feature)

---

**Document Version:** 1.0
**Last Updated:** 2026-02-26
**Status:** Implemented (Phase 1 MVP)
