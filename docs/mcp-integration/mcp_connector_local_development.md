# MCP Connector — Local Development & Testing

## Overview

This guide explains how to test the MCP connector integration locally with external MCP clients (Claude Desktop, Cursor, etc.). The core challenge: MCP clients need a **public URL** to reach your backend for the OAuth flow and MCP protocol, but your backend runs on `localhost:8000`. We solve this with a [pinggy](https://pinggy.io) tunnel.

## Architecture (Local Dev)

```
MCP Client (Claude Desktop / Cursor)
    │
    │  HTTPS (MCP protocol + OAuth)
    ▼
Pinggy Tunnel (https://xxx.a.free.pinggy.link)
    │
    │  Forwards to localhost:8000
    ▼
Backend Container (Docker, port 8000)
    │
    │  OAuth /authorize redirects browser to localhost:5173
    ▼
Frontend (localhost:5173) ← consent page loads in browser
```

**Why the frontend doesn't need a tunnel:** The MCP client runs on the same machine as the browser. When the OAuth flow opens the browser for consent, it navigates to `http://localhost:5173` which is directly accessible. Only the MCP protocol endpoints and OAuth token exchange (called programmatically by the MCP client) need the public tunnel URL.

---

## Prerequisites

- Docker services running (`make up`)
- Migrations applied (`make migrate`)
- An agent created in the UI with an active environment
- SSH client installed (for pinggy tunnel)

---

## Step-by-Step Setup

### 1. Start the Tunnel

**Terminal 1:**

```bash
make mcp-tunnel
```

This starts a pinggy SSH tunnel and prints instructions. You'll see output like:

```
Starting pinggy tunnel for MCP...
1) Copy the HTTPS URL from the tunnel output
2) In another terminal, run:
   make mcp-set-url URL=https://YOUR-TUNNEL.a.free.pinggy.link

http://rndzx-xxx-xxx.a.free.pinggy.link
https://rndzx-xxx-xxx.a.free.pinggy.link
```

Copy the **HTTPS** URL. Keep this terminal open — the tunnel stays active as long as the SSH session runs.

### 2. Set URL and Recreate Backend

**Terminal 2:**

```bash
make mcp-set-url URL=https://rndzx-xxx-xxx.a.free.pinggy.link
```

This single command does three things:
1. Updates `MCP_SERVER_BASE_URL` in `.env` (automatically appends `/mcp`)
2. Recreates the backend container with the new env var
3. Verifies the MCP OAuth endpoint is reachable through the tunnel

**What it does under the hood:**
- Writes `MCP_SERVER_BASE_URL=https://rndzx-xxx-xxx.a.free.pinggy.link/mcp` to `.env`
- Runs `docker compose up -d backend` to recreate the container (~2-3 seconds, no rebuild)
- Curls the AS metadata endpoint to confirm everything works

**Why `up -d` and not `restart`:** `docker compose restart` reuses the same container with its original env vars. `docker compose up -d` detects that `.env` has changed and recreates the container, picking up the new `MCP_SERVER_BASE_URL` value.

### 3. Verify (optional manual check)

The `mcp-set-url` command already verifies, but you can also check manually:

```bash
curl -s https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/oauth/.well-known/oauth-authorization-server | python3 -m json.tool
```

Expected response:
```json
{
    "issuer": "https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/oauth",
    "authorization_endpoint": "https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/oauth/authorize",
    "token_endpoint": "https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/oauth/token",
    "registration_endpoint": "https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/oauth/register",
    ...
}
```

If you see this, the tunnel → backend → MCP OAuth chain is working.

### 4. Create an MCP Connector

1. Open the app at `http://localhost:5173`
2. Navigate to your agent → **Integrations** tab
3. Click **Create MCP Connector**
4. Fill in: name, mode (conversation/building), optional allowed emails
5. Copy the **MCP Server URL** from the created connector

The URL will look like:
```
https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/{connector-uuid}/mcp
```

### 5. Configure the MCP Client

#### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "my-agent": {
      "url": "https://rndzx-xxx-xxx.a.free.pinggy.link/mcp/{connector-uuid}/mcp"
    }
  }
}
```

Restart Claude Desktop after saving.

#### Cursor

Settings → MCP → Add Server → paste the MCP Server URL.

### 6. Test the Connection

When the MCP client connects, it will automatically:

1. Hit `/.well-known/oauth-protected-resource` on the connector endpoint
2. Discover the shared OAuth AS via `/.well-known/oauth-authorization-server`
3. Register a client via DCR (`POST /mcp/oauth/register`)
4. Open your browser for OAuth consent (`GET /mcp/oauth/authorize` → redirect to frontend)
5. After you log in and approve, exchange the auth code for tokens
6. Call `send_message` tool with the bearer token

You should see the `send_message` tool available in the MCP client's tool list.

---

## When the Tunnel URL Changes

Free pinggy generates a **random subdomain** each session. If the tunnel drops or you restart it, the URL changes. To recover:

1. Restart the tunnel: `make mcp-tunnel`
2. Copy the new HTTPS URL
3. Run: `make mcp-set-url URL=https://NEW-TUNNEL.a.free.pinggy.link`
4. **MCP connectors keep their UUIDs** — only the base URL prefix changes
5. Update the URL in your MCP client config (Claude Desktop JSON, Cursor settings)
6. The MCP client will need to re-authenticate (old tokens reference the old URL)

**Tip:** For a stable URL, use pinggy's paid plan with a custom subdomain, or use an alternative tunnel service with fixed URLs.

---

## What Needs a Tunnel vs. What Doesn't

| Component | Accessed via | Needs tunnel? |
|-----------|-------------|---------------|
| MCP protocol endpoints (`/mcp/{id}/mcp`) | MCP client (programmatic) | Yes |
| OAuth token exchange (`/mcp/oauth/token`) | MCP client (programmatic) | Yes |
| OAuth authorize (`/mcp/oauth/authorize`) | Browser redirect (started by MCP client) | Yes |
| Consent page (`/oauth/mcp-consent`) | Browser (localhost:5173) | No |
| Consent API (`/api/v1/mcp/consent/{nonce}/approve`) | Frontend JS to localhost:8000 | No |
| App UI / Connector management | Browser (localhost:5173) | No |

No CORS configuration changes are needed — MCP protocol calls are server-to-server (no browser origin), and OAuth redirects are browser navigations (not XHR).

---

## `MCP_SERVER_BASE_URL` Format

```
MCP_SERVER_BASE_URL=https://{tunnel-host}/mcp
```

- Must include the `/mcp` suffix (matches the backend mount point)
- No trailing slash
- All MCP-facing URLs are derived from this single value:
  - MCP Server URL (user copies): `{MCP_SERVER_BASE_URL}/{connector_id}/mcp`
  - OAuth AS metadata: `{MCP_SERVER_BASE_URL}/oauth/.well-known/oauth-authorization-server`
  - Token endpoint: `{MCP_SERVER_BASE_URL}/oauth/token`

---

## Troubleshooting

| Problem | Cause | Fix |
|---------|-------|-----|
| 404 on all MCP endpoints | Tunnel URL changed or `MCP_SERVER_BASE_URL` empty | Update `.env`, recreate backend |
| Consent page won't load | Frontend not running | `make dev-front` or `docker compose up -d frontend` |
| "Connector not found or inactive" | Connector deactivated or deleted | Check connector status in the Integrations tab |
| OAuth flow opens browser but hangs | Tunnel SSH session closed | Restart tunnel, update config, recreate backend |
| "Invalid resource URL" on DCR | `MCP_SERVER_BASE_URL` format wrong | Must end with `/mcp`, no trailing slash |
| Token exchange fails | URL mismatch between DCR and token request | Ensure MCP_SERVER_BASE_URL matches the current tunnel |
| `send_message` returns error | Agent environment not running | Start the agent environment from the UI |
| Repeated "unauthorized" after re-auth | Stale tokens from old tunnel URL | Delete MCP client's cached credentials and reconnect |

---

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make mcp-tunnel` | Start pinggy tunnel for MCP testing (keep terminal open) |
| `make mcp-set-url URL=https://xxx.pinggy.link` | Update `.env`, recreate backend, verify endpoint |
| `make dev-tunnel` | Generic tunnel (same SSH command, no MCP instructions) |

## Quick Reference

```bash
# Terminal 1: Start tunnel (keep open)
make mcp-tunnel
# → Copy the HTTPS URL

# Terminal 2: Set URL + recreate backend (one command)
make mcp-set-url URL=https://YOUR-TUNNEL.a.free.pinggy.link

# Then:
# 1. Create MCP connector in UI (localhost:5173 → agent → Integrations)
# 2. Copy MCP Server URL
# 3. Paste into Claude Desktop / Cursor config
# 4. MCP client handles OAuth automatically
```

---

## Related Documentation

- `docs/mcp-integration/agent_mcp_architecture.md` — Architecture overview
- `docs/mcp-integration/agent_mcp_connector.md` — Implementation reference
- `docs/mcp-integration/implementation_plan.md` — Phased implementation plan
