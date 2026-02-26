# MCP Integration Tests

Tests the MCP (Model Context Protocol) integration feature end-to-end: connector CRUD, OAuth 2.1 authorization server, Dynamic Client Registration, consent flow, PKCE, token management, well-known metadata endpoints, and transport security.

## Autouse Fixtures (conftest.py)

Same infrastructure as `tests/api/agents/conftest.py` (session proxy, environment adapter stub, background task collector, external service mocks) plus:

- **`patch_mcp_server_base_url`** — Sets `MCP_SERVER_BASE_URL` to `http://localhost:8000/mcp` so resource URLs are predictable in tests.
- **`patch_create_session` (extended)** — Patches `app.mcp.oauth_routes._get_db` and `app.mcp.tools.create_session` so MCP OAuth routes and the tool handler stay on the test transaction.
- **`patch_mcp_registry_remove`** — Prevents `mcp_registry.remove()` calls (during connector deactivation/deletion) from crashing since no real MCP servers exist in tests.

See `tests/api/agents/README.md` for shared fixture details.

## Test Files

| File | Description |
|------|-------------|
| `test_mcp_connector_crud.py` | CRUD lifecycle, multiple connectors, ownership enforcement, partial updates, edge cases |
| `test_mcp_oauth_flow.py` | Full OAuth flow (with/without PKCE), DCR (with/without resource), consent, token refresh/revocation, form-encoded token endpoint, root-level well-known endpoints, transport security, error cases, end-to-end scenarios |
| `test_mcp_send_message.py` | MCP tool handler: session creation with correct fields, user+agent message storage, session reuse, external session ID preservation, inactive connector rejection, agent response metadata |

## Live Testing Fix Coverage

Tests in `test_mcp_oauth_flow.py` cover the following issues discovered during live testing with Claude Desktop (see `discovered_errors_to_update_in_tests.md`):

| Error # | Issue | Test |
|---------|-------|------|
| #2 | RFC 9728 Protected Resource Metadata at root | `test_protected_resource_metadata_root_level` |
| #3 | RFC 8414 AS Metadata at root with issuer path | `test_as_metadata_root_level_with_issuer_path` |
| #4 | DCR without resource field | `test_dcr_without_resource` |
| #5 | Token endpoint form-encoded (not JSON) | `test_token_exchange_form_encoded`, `test_token_exchange_json_body_rejected` |
| #6 | Scope field in token response (DetachedInstanceError) | `test_token_exchange_form_encoded` (asserts scope) |
| #9 | Transport security with external hostname | `test_transport_security_includes_external_hostname` |
| #10 | AS Metadata at exact root path (no 307 redirect) | `test_as_metadata_root_level_no_path` |

All token/revoke helpers and inline calls use `data=` (form-encoded) instead of `json=`, matching the production endpoint's `Form(...)` parameters.

## Test Utilities

Helpers in `tests/utils/mcp.py`:

| Helper | Description |
|--------|-------------|
| `create_mcp_connector` | Create connector via POST API |
| `list_mcp_connectors` | List connectors via GET API |
| `get_mcp_connector` | Get connector by ID via GET API |
| `update_mcp_connector` | Update connector via PUT API |
| `delete_mcp_connector` | Delete connector via DELETE API |
| `register_oauth_client` | Register OAuth client via DCR with resource URL |
| `register_oauth_client_without_resource` | Register OAuth client via DCR without resource (global client) |
| `get_as_metadata` | Fetch AS metadata (router-level `/.well-known/oauth-authorization-server`) |
| `get_as_metadata_root_level` | Fetch AS metadata (root-level, with or without issuer path) |
| `get_protected_resource_metadata` | Fetch RFC 9728 protected resource metadata (root-level) |
| `start_authorize` | Start OAuth authorize flow, extract nonce from 302 redirect |
| `get_consent_info` | Fetch consent page details |
| `approve_consent` | Approve OAuth consent with JWT auth |
| `exchange_auth_code` | Exchange authorization code for tokens (form-encoded) |
| `refresh_access_token` | Refresh an access token (form-encoded) |
| `revoke_token` | Revoke a token (form-encoded) |
| `generate_pkce_pair` | Generate PKCE code_verifier + code_challenge (S256) |
| `run_full_oauth_flow` | Convenience: DCR → authorize → consent → token exchange in one call |

## Related Documentation

- `docs/mcp-integration/agent_mcp_connector.md` — Implementation reference
- `docs/mcp-integration/implementation_plan.md` — Phased implementation plan
- `discovered_errors_to_update_in_tests.md` — Live testing issues with test coverage mapping
