# MCP Integration Tests

Tests the MCP (Model Context Protocol) integration feature end-to-end: connector CRUD, OAuth 2.1 authorization server, Dynamic Client Registration, consent flow, PKCE, token management.

## Autouse Fixtures (conftest.py)

Same infrastructure as `tests/api/agents/conftest.py` (session proxy, environment adapter stub, background task collector, external service mocks) plus:

- **`patch_mcp_server_base_url`** — Sets `MCP_SERVER_BASE_URL` to `http://localhost:8000/mcp` so resource URLs are predictable in tests.
- **`patch_create_session` (extended)** — Patches `app.mcp.oauth_routes._get_db` and `app.mcp.server.DBSession` so MCP OAuth routes and the server registry stay on the test transaction.
- **`patch_mcp_registry_remove`** — Prevents `mcp_registry.remove()` calls (during connector deactivation/deletion) from crashing since no real MCP servers exist in tests.

See `tests/api/agents/README.md` for shared fixture details.

## Test Files

| File | Description |
|------|-------------|
| `test_mcp_connector_crud.py` | CRUD lifecycle, multiple connectors, ownership enforcement, partial updates, edge cases |
| `test_mcp_oauth_flow.py` | Full OAuth flow (with/without PKCE), DCR, consent, token refresh/revocation, error cases, end-to-end scenarios |

## Test Utilities

Helpers in `tests/utils/mcp.py`:

| Helper | Description |
|--------|-------------|
| `create_mcp_connector` | Create connector via POST API |
| `list_mcp_connectors` | List connectors via GET API |
| `get_mcp_connector` | Get connector by ID via GET API |
| `update_mcp_connector` | Update connector via PUT API |
| `delete_mcp_connector` | Delete connector via DELETE API |
| `register_oauth_client` | Register OAuth client via DCR (POST /mcp/oauth/register) |
| `get_as_metadata` | Fetch AS metadata (/.well-known/oauth-authorization-server) |
| `start_authorize` | Start OAuth authorize flow, extract nonce from 302 redirect |
| `get_consent_info` | Fetch consent page details |
| `approve_consent` | Approve OAuth consent with JWT auth |
| `exchange_auth_code` | Exchange authorization code for tokens |
| `refresh_access_token` | Refresh an access token |
| `revoke_token` | Revoke a token |
| `generate_pkce_pair` | Generate PKCE code_verifier + code_challenge (S256) |
| `run_full_oauth_flow` | Convenience: DCR → authorize → consent → token exchange in one call |

## Related Documentation

- `docs/mcp-integration/implementation_plan.md` — Phased implementation plan
- `docs/agent_mcp_connector_concept.md` — Feature concept document
