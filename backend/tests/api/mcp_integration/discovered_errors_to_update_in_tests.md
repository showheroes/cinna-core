# MCP Integration — Errors Discovered During Live Testing with Claude Desktop

These issues were found during end-to-end testing with Claude Desktop as the MCP client,
connecting via a pinggy tunnel to the local backend. Each fix should have corresponding
test coverage added or existing tests updated.

---

## 1. MCPServerRegistry path not stripped by Starlette mount

**Symptom:** All requests to `POST /mcp/{connector_id}/mcp` returned 404 "Invalid connector ID".

**Root cause:** Starlette 0.46 sets `root_path` on mounted ASGI apps but does NOT modify
`scope["path"]`. The `MCPServerRegistry.__call__` was reading `scope["path"]` directly
(which still contained the `/mcp` prefix), so `parts[0]` was `"mcp"` instead of the UUID.

**Fix:** Use `starlette.routing.get_route_path(scope)` which strips the `root_path` prefix.

**File:** `backend/app/mcp/server.py`

**Test needed:** Test MCPServerRegistry with a scope that has `root_path` set (simulating
Starlette mount behavior). Verify it correctly extracts the connector_id from the
effective path, not the raw `scope["path"]`.

---

## 2. RFC 9728 Protected Resource Metadata not served at root level

**Symptom:** `GET /.well-known/oauth-protected-resource/mcp/{id}/mcp` returned 404.
The MCP client couldn't discover the OAuth authorization server.

**Root cause:** Per RFC 9728, the protected resource metadata URL is at the **server origin root**
(`/.well-known/oauth-protected-resource{resource-path}`). The FastMCP SDK generates a route
for this path inside the per-connector app, but that app is mounted under `/mcp/{id}/`,
so the route was unreachable at the root.

**Fix:** Added `wellknown_router` with a root-level `GET /.well-known/oauth-protected-resource/{path}`
endpoint in `oauth_routes.py`, mounted at app root in `main.py`.

**Files:** `backend/app/mcp/oauth_routes.py`, `backend/app/main.py`

**Test needed:** Test that `GET /.well-known/oauth-protected-resource/mcp/{connector_id}/mcp`
returns 200 with correct `resource` and `authorization_servers` fields.

---

## 3. RFC 8414 AS Metadata not served at root level

**Symptom:** `GET /.well-known/oauth-authorization-server/mcp/oauth` returned 404.
After discovering the AS URL from protected resource metadata, the MCP client couldn't
fetch the authorization server metadata.

**Root cause:** Same pattern as #2. RFC 8414 requires AS metadata at
`/.well-known/oauth-authorization-server{issuer-path}` (server root). Our endpoint was
only at `/mcp/oauth/.well-known/oauth-authorization-server` (under the router prefix).

**Fix:** Added `GET /.well-known/oauth-authorization-server/{path}` to the `wellknown_router`.

**File:** `backend/app/mcp/oauth_routes.py`

**Test needed:** Test that `GET /.well-known/oauth-authorization-server/mcp/oauth` returns 200
with correct endpoint URLs.

---

## 4. DCR fails when client doesn't send `resource` parameter

**Symptom:** `POST /mcp/oauth/register` returned 400 "Invalid or missing resource URL".
Claude Desktop registered successfully only after this fix.

**Root cause:** Claude Desktop sends DCR requests without the `resource` field (it's a SHOULD
per the MCP spec, not MUST). Our endpoint required it to determine the connector.

**Fix:**
- Made `connector_id` nullable on `MCPOAuthClient` model (migration `bb07edf29ef1`)
- DCR endpoint now accepts registration without `resource` — client is registered globally
- Connector binding happens during the `/authorize` step where `resource` IS provided

**Files:** `backend/app/models/mcp_oauth_client.py`, `backend/app/mcp/oauth_routes.py`,
`backend/app/alembic/versions/bb07edf29ef1_...py`

**Tests needed:**
- Test DCR with empty `resource` returns 201
- Test DCR with valid `resource` still links to connector
- Test authorize works with a globally-registered client (no connector_id)

---

## 5. Token endpoint rejects form-encoded requests (422)

**Symptom:** `POST /mcp/oauth/token` returned 422 Unprocessable Entity after successful
consent approval. The auth code was issued but couldn't be exchanged for tokens.

**Root cause:** The token endpoint used `body: TokenRequest` (Pydantic model), which expects
`application/json`. OAuth 2.1 requires token endpoints to accept
`application/x-www-form-urlencoded` (form data). All standard OAuth clients send form data.

**Fix:** Changed `/token` and `/revoke` endpoints from JSON body to `Form(...)` parameters.

**File:** `backend/app/mcp/oauth_routes.py`

**Tests needed:**
- Test token exchange with `content-type: application/x-www-form-urlencoded`
- Test refresh token grant with form data
- Test token revocation with form data
- Update any existing tests that send JSON to the token endpoint

---

## 6. Token endpoint 500 — DetachedInstanceError on `auth_code.scope`

**Symptom:** `POST /mcp/oauth/token` returned 500 Internal Server Error after successful
consent approval.

**Root cause:** In `_handle_authorization_code`, `auth_code.scope` was accessed **after** the
`with _get_db() as db:` block exited, causing a SQLAlchemy `DetachedInstanceError`. The
SQLModel instance was no longer attached to a session.

**Fix:** Captured `auth_code.scope` into a local variable `granted_scope` inside the `with`
block, and used that local variable when building the JSON response.

**File:** `backend/app/mcp/oauth_routes.py`

**Test needed:** Test that the authorization_code grant returns a valid response including
the `scope` field without raising DetachedInstanceError.

---

## 7. Token verifier 500 — naive vs aware datetime comparison

**Symptom:** `POST /mcp/{connector_id}/mcp` returned 500 after successful token exchange.
Error: `TypeError: can't compare offset-naive and offset-aware datetimes`.

**Root cause:** In `MCPTokenVerifier.verify_token`, `token_record.expires_at` is a naive
UTC datetime (from the database), but `datetime.now(UTC)` produces an aware datetime.
Python 3 does not allow comparing naive and aware datetimes.

**Fix:** Added `.replace(tzinfo=None)` to `datetime.now(UTC)` to make it naive for
comparison: `datetime.now(UTC).replace(tzinfo=None)`.

**File:** `backend/app/mcp/token_verifier.py`

**Test needed:** Test that token verification works correctly with database-stored naive
UTC datetimes (both valid and expired tokens).

---

## 8. MCP endpoint 500 — "Task group is not initialized"

**Symptom:** `POST /mcp/{connector_id}/mcp` returned 500 after successful OAuth flow.
Error: `RuntimeError: Task group is not initialized. Make sure to use run().`

**Root cause:** `FastMCP.streamable_http_app()` returns a Starlette app with
`lifespan=lambda app: self.session_manager.run()`. This lifespan initializes an `anyio`
task group in `StreamableHTTPSessionManager._task_group`. However, `MCPServerRegistry`
dispatches requests directly to the Starlette app via `await app(scope, receive, send)`
with `http`/`websocket` scope types — it never sends a `lifespan` scope, so the
session manager's `run()` context is never entered and `_task_group` remains `None`.

**Fix:** Added lifecycle management to `MCPServerRegistry`:
- Added `run()` async context manager that creates a parent `anyio` task group
- When `get_or_create()` creates a new connector app, it starts the connector's
  `session_manager.run()` in the parent task group (using `task_group.start()`)
- The FastAPI app lifespan wraps its `yield` with `async with mcp_registry.run()`
- On shutdown, the parent task group cancels all per-connector session managers

**Files:** `backend/app/mcp/server.py`, `backend/app/main.py`

**Tests needed:**
- Test that MCPServerRegistry properly initializes session managers on first request
- Test that MCP tool calls succeed after OAuth authentication
- Test that registry shutdown cleans up all session managers

---

## 9. MCP endpoint 421 — DNS rebinding protection rejects tunnel hostname

**Symptom:** `POST /mcp/{connector_id}/mcp` returned 421 Misdirected Request after successful
OAuth token exchange. Log: `WARNING:mcp.server.transport_security:Invalid Host header: ueobl-84-60-237-183.a.free.pinggy.link`.

**Root cause:** The MCP SDK auto-enables DNS rebinding protection when the FastMCP `host`
defaults to `127.0.0.1`. The default `allowed_hosts` only includes `127.0.0.1:*`,
`localhost:*`, and `[::1]:*`. When requests arrive via a pinggy tunnel, the `Host` header
is the tunnel hostname (e.g. `ueobl-84-60-237-183.a.free.pinggy.link`), which is rejected.

**Fix:** Added `_build_transport_security()` helper that extracts the hostname from
`MCP_SERVER_BASE_URL` and adds it to `allowed_hosts` and `allowed_origins`. The
`TransportSecuritySettings` is passed to `FastMCP(transport_security=...)`.

**File:** `backend/app/mcp/server.py`

**Tests needed:**
- Test that `_build_transport_security()` includes the configured external hostname
- Test that MCP requests with external Host headers are accepted (not 421)
- Test that localhost variants are still allowed

---

## 10. AS Metadata discovery 307 — client doesn't follow redirect

**Symptom:** `GET /.well-known/oauth-authorization-server` returned 307 redirect.
The MCP client (Claude Desktop) did not follow the redirect and fell back to
`POST /register` at root (404), breaking the OAuth flow.

**Root cause:** The `wellknown_router` only had a route with a path parameter:
`/.well-known/oauth-authorization-server/{issuer_path:path}`. A request to
`/.well-known/oauth-authorization-server` (without trailing slash or path suffix)
didn't match this route. FastAPI's `redirect_slashes` behavior returned a 307 redirect
to `/.well-known/oauth-authorization-server/`. Some MCP clients don't follow redirects
for well-known discovery URLs.

**Fix:** Added an exact-match route `GET /.well-known/oauth-authorization-server` (without
path parameter) to the `wellknown_router`, returning the same AS metadata. Extracted the
response body into a shared `_as_metadata_response()` helper.

**File:** `backend/app/mcp/oauth_routes.py`

**Tests needed:**
- Test `GET /.well-known/oauth-authorization-server` (no path) returns 200 with correct metadata
- Test `GET /.well-known/oauth-authorization-server/mcp/oauth` (with path) still returns 200
- Verify `registration_endpoint` in the response points to the correct URL

---

## 11. MCP tool handler 500 — DetachedInstanceError on `connector.mode`

**Symptom:** `send_message` tool call returned error:
`Instance <MCPConnector at 0x...> is not bound to a Session; attribute refresh operation cannot proceed`.

**Root cause:** In `handle_send_message` (tools.py), `connector.mode` was accessed outside
the `with DBSession(engine) as db:` block when building the request payload. The `connector`
SQLModel instance was detached from its session, triggering a lazy-load attempt.

Same class of bug as error #6 (DetachedInstanceError on `auth_code.scope`).

**Fix:** Captured `connector.mode` into a local variable `connector_mode` inside the `with`
block, and used that in the payload dict.

**File:** `backend/app/mcp/tools.py`

**Test needed:** Test that `send_message` tool execution doesn't raise DetachedInstanceError
when accessing connector attributes after the DB session closes.
