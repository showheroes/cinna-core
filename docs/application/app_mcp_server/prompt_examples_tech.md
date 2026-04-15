# Prompt Examples -- Technical Details

## File Locations

### Backend -- Models

- `backend/app/models/app_mcp/app_agent_route.py` -- `AppAgentRoute.prompt_examples` (Text, nullable); included in `AppAgentRouteCreate`, `AppAgentRouteUpdate`, `AppAgentRoutePublic`, `SharedRoutePublic` schemas
- `backend/app/models/identity/identity_models.py` -- `IdentityAgentBinding.prompt_examples` (Text, nullable); included in `IdentityAgentBindingCreate`, `IdentityAgentBindingUpdate`, `IdentityAgentBindingPublic` schemas

### Backend -- Routes (Validation)

- `backend/app/api/routes/agent_app_mcp_routes.py` -- `_validate_prompt_examples()` called on create and update; enforces 2000 char / 10 line limits with HTTP 422
- `backend/app/api/routes/identity.py` -- identical `_validate_prompt_examples()` function for identity bindings

### Backend -- Services

- `backend/app/services/app_mcp/app_agent_route_service.py` -- `EffectiveRoute.prompt_examples` field; `_build_identity_prompt_examples()` aggregates and prefixes identity binding examples for a caller; `get_effective_routes_for_user()` populates `prompt_examples` on both direct routes and identity routes
- `backend/app/services/identity/identity_service.py` -- passes `prompt_examples` through on create and update; returns in `IdentityAgentBindingPublic`

### Backend -- MCP Prompts

- `backend/app/mcp/app_prompts.py` -- `register_app_mcp_prompts()` iterates `route.prompt_examples`, splits by newline, emits each non-empty line as an individual `PromptMessage`

### Backend -- Migration

- `backend/app/alembic/versions/b5a73df91425_add_prompt_examples_to_routes_and_bindings.py` -- adds `prompt_examples` (Text, nullable) to `app_agent_route` and `identity_agent_binding`

### Frontend

- `frontend/src/components/Agents/McpConnectorsCard.tsx` -- `appMcpPromptExamples`, `identityPromptExamples`, `editRoutePromptExamples` state variables; "Prompt Examples" textarea in App MCP and Identity forms; passed in create/update payloads
- `frontend/src/components/UserSettings/IdentityServerCard.tsx` -- `editPromptExamples` state; "Prompt Examples" textarea in edit binding dialog with helper text explaining name prefixing

### Tests

- `backend/tests/api/app_mcp/prompt_examples_test.py` -- four scenarios: AppAgentRoute lifecycle (create/update/clear), AppAgentRoute validation (>2000 chars, >10 lines, boundary), IdentityAgentBinding lifecycle, IdentityAgentBinding validation

## Database Schema

### `app_agent_route.prompt_examples`

- Type: Text, nullable, default null
- Contains newline-separated short prompt strings
- No database-level length or line-count constraint (enforced at API layer)

### `identity_agent_binding.prompt_examples`

- Same schema as above

## Key Implementation Details

### Identity Example Aggregation

`AppAgentRouteService._build_identity_prompt_examples()` runs a JOIN query across `IdentityAgentBinding` and `IdentityBindingAssignment`, filtering for active bindings and active+enabled assignments for the target caller. Each non-empty line from matching bindings is prefixed with `"ask {owner_name} ({owner_email}) to {line}"` and all results are joined with newlines.

This aggregated string is set as `prompt_examples` on the identity `EffectiveRoute`, so `app_prompts.py` handles it identically to direct route examples.

### MCP Prompt Emission

In `app_prompts.py`, `list_available_agents()` iterates effective routes. For each route:
1. Always emits the `trigger_prompt` as a `PromptMessage`
2. If `prompt_examples` is set, splits by newline and emits each non-empty stripped line as an additional `PromptMessage`

### Validation

Both route files (`agent_app_mcp_routes.py`, `identity.py`) define an identical `_validate_prompt_examples()` helper:
- Returns early if value is None or empty
- Checks total length > 2000 → HTTP 422
- Counts non-empty lines > 10 → HTTP 422
- Called before service-layer create/update
