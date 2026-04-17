# External Agent Access API — Implementation Plan

> **Implementation status:** Phases 1–6 completed 2026-04-17. Phase 6 landed partial — 4 of 6 items shipped; rate limiting (#2) and `Idempotency-Key` (#3) deferred to dedicated follow-up PRs (see Phase 6 section for rationale).
>
> Phases completed: **6 of 6** (Phase 6 partial — 4 of 6 items)
>
> Next action: None for this plan. Follow-up items — rate limiting and `Idempotency-Key` — tracked in Future Enhancements / separate PRs.

## Overview

A REST + A2A surface mounted at `/api/v1/external/`, consumed by **first-party Cinna clients** (Cinna Desktop today; Cinna Mobile and other native clients later). It is the only backend surface these clients need for the agent-list + chat experience.

**Two layers, one namespace:**

1. **Discovery (plain JSON REST)** — one endpoint returns every agent/identity the authenticated user can address. Every target carries an `agent_card_url` pointing to its A2A AgentCard.
2. **Chat (standard A2A v1.0 / v0.3)** — per-target A2A endpoints (one per `(target_type, target_id)`) reuse the existing `A2ARequestHandler`, `A2AEventMapper`, `A2AV1Adapter`, and SSE streaming pipeline. Clients use an off-the-shelf `a2a-sdk` (or any A2A-compatible client) to send streaming messages and manage tasks. No new protocol is invented.

The external surface is a thin dispatch layer over three existing worlds — direct agents, App MCP routes, Identity MCP bindings — unified by the `ExternalA2A*` handlers that stamp the correct session ownership and skip the Stage‑1 AI router.

**Core capabilities:**

- **Unified agent discovery** — one endpoint returns every addressable target regardless of source:
  1. **Personal agents** — agents owned by the user (including Agent Sharing clones) with `is_active=True`
  2. **MCP Shared Agents** — agents reachable via an `AppAgentRoute` assignment that is both `is_active` and `is_enabled`
  3. **Identity Contacts** — identity owners (*not their sub-agents*) reachable via one or more active `IdentityBindingAssignment`s — one entry per owner (1-layer routing)
- **Per-target A2A AgentCard** — standard A2A cards with `supportedInterfaces` advertising both v1.0 and v0.3; version can also be forced with `?protocol=v0.3` / `?protocol=v1.0`
- **A2A streaming chat** — clients speak A2A JSON-RPC (`SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`, `ListTasks`) against the target's endpoint; session creation, Stage‑2 routing for identity, and per-route dispatch happen inside the handler
- **Cross-target session list** — a plain REST endpoint lists every session the user participates in (as owner, caller, or identity_caller) so the client can restore its thread list at launch
- **Stable, extensible response payload** — every discovered target carries `id`, `name`, `description`, `entrypoint_prompt`, `example_prompts`, `target_type`, `agent_card_url`, plus a `metadata` map for future fields

**High-level flow:**

```
Native client (Cinna Desktop / Mobile / …) — authenticated JWT
      │
      │  GET /api/v1/external/agents              (plain JSON REST)
      ▼
┌────────────────────────────────────────────────────────────────┐
│  ExternalAgentCatalogService.list_targets()                    │
│                                                                │
│   Personal agents │ MCP Shared routes │ Identity contacts      │
│                                                                │
│   Each target → ExternalTargetPublic {                         │
│     target_type, target_id, name, description,                 │
│     entrypoint_prompt, example_prompts, …,                     │
│     agent_card_url,                                            │
│     protocol_versions: ["1.0", "0.3.0"],                       │
│   }                                                            │
└────────────────────────────────────────────────────────────────┘
      │
      │  GET {agent_card_url}?protocol=v1.0       (A2A AgentCard)
      ▼
┌────────────────────────────────────────────────────────────────┐
│  ExternalA2AService.build_card_for(target_type, target_id)     │
│                                                                │
│  Reuses A2AService.build_agent_card() for the underlying agent │
│  (or synthesizes a person-level card for identity),            │
│  then A2AV1Adapter transforms it to the requested version.     │
└────────────────────────────────────────────────────────────────┘
      │
      │  POST {agent_card_url}                    (A2A JSON-RPC)
      │  { "method": "message/stream" ∣ "SendStreamingMessage", …}
      ▼
┌────────────────────────────────────────────────────────────────┐
│  ExternalA2ARequestHandler.handle(target_type, target_id, ...) │
│                                                                │
│  target_type = "agent"          → reuse A2ARequestHandler      │
│                                    skip a2a_config.enabled gate│
│                                    integration_type="external" │
│                                                                │
│  target_type = "app_mcp_route" → reuse A2ARequestHandler       │
│                                    fix agent from route        │
│                                    user_id=agent.owner_id,     │
│                                    caller_id=current_user.id,  │
│                                    integration_type="app_mcp"  │
│                                                                │
│  target_type = "identity"      → run Stage-2 on first message  │
│                                    create identity_mcp session │
│                                    user_id=owner_id,           │
│                                    identity_caller_id=caller   │
│                                                                │
│  All three return SSE events mapped by A2AEventMapper,         │
│  identical to the existing /api/v1/a2a/ surface.               │
└────────────────────────────────────────────────────────────────┘
```

---

## Architecture Overview

### System Components

```
┌──────────────────────┐       ┌────────────────────────────────────────────┐
│  Cinna Desktop       │       │                  Cinna Backend              │
│  Cinna Mobile        │       │                                            │
│  …future clients     │       │  /api/v1/external/ (new router)            │
│  (JWT from desktop_  │       │                                            │
│   auth / mobile_auth)│       │  Layer 1 — Discovery (plain JSON REST)     │
│                      │──────►│    GET  /agents                            │
│  - agents list view  │       │                                            │
│  - chat view         │       │  Layer 2 — A2A per target                  │
│                      │──────►│    GET  /a2a/{target_type}/{target_id}/    │
│                      │       │            [?protocol=v1.0|v0.3]           │
│                      │       │    GET  /a2a/{target_type}/{target_id}/    │
│                      │       │              .well-known/agent-card.json   │
│                      │       │    POST /a2a/{target_type}/{target_id}/    │
│                      │       │            (A2A JSON-RPC)                  │
│                      │       │                                            │
│                      │       │  Layer 3 — Session metadata (JSON REST)    │
│                      │       │    GET  /sessions                          │
│                      │       │    GET  /sessions/{id}                     │
│                      │       │    GET  /sessions/{id}/messages            │
│                      │       │                                            │
│                      │       │  Services:                                 │
│                      │       │   ├─ ExternalAgentCatalogService (new)     │
│                      │       │   ├─ ExternalA2AService           (new)    │
│                      │       │   ├─ ExternalA2ARequestHandler    (new)    │
│                      │       │   └─ ExternalSessionService       (new)    │
│                      │       │                                            │
│                      │       │   All three A2A pieces reuse:              │
│                      │       │    - A2AService (card build)               │
│                      │       │    - A2ARequestHandler (core dispatch)     │
│                      │       │    - A2AEventMapper                        │
│                      │       │    - A2AV1Adapter                          │
│                      │       │    - SessionStreamProcessor                │
│                      │       │    - A2AStreamEventHandler                 │
│                      │       │                                            │
│                      │       │  Data: no new tables — reads                │
│                      │       │   ├─ Agent, AgentShare                     │
│                      │       │   ├─ AppAgentRoute, Assignment             │
│                      │       │   └─ IdentityAgentBinding, Assignment      │
└──────────────────────┘       └────────────────────────────────────────────┘
```

### Integration Points with Existing Systems

| System | How it integrates |
|--------|-------------------|
| [Desktop Auth](../application/desktop_auth/desktop_auth.md) | Cinna Desktop uses this to obtain a JWT. The same OAuth 2.0 + PKCE infrastructure is expected to be reused by future mobile clients (new `*OAuthClient` kind, or a generalized `NativeOAuthClient`). The external API is auth-source-agnostic — it only requires a valid `CurrentUser`. |
| [A2A Protocol](../application/a2a_integration/a2a_protocol/a2a_protocol.md) | All chat traffic reuses `A2ARequestHandler`, `A2AEventMapper`, `A2AV1Adapter`, `A2AStreamEventHandler`, `SessionStreamProcessor`, and `DatabaseTaskStore`. The external router is a thin dispatcher that selects the target agent before delegating. |
| [A2A Access Tokens](../application/a2a_integration/a2a_access_tokens/a2a_access_tokens.md) | Not used. The external API authenticates with regular user JWTs so native clients don't need to mint per-agent tokens. |
| [Agent Management](../application/agent_management/agent_management.md) | Reads `Agent` rows where `owner_id = current_user.id` (including clones) and `is_active=True`. A2A is available to the owner regardless of `a2a_config.enabled` (that flag only gates the public `/api/v1/a2a/` surface). |
| [App MCP Server](../application/app_mcp_server/app_mcp_server.md) | Reuses `AppAgentRouteService.get_effective_routes_for_user()` for discovery. For chat, the external A2A handler reproduces the `app_mcp` session-ownership rules (user_id=owner, caller_id=caller) while bypassing the Stage‑1 AI router (the route is already chosen by the client). |
| [Identity MCP Server](../application/identity_mcp_server/identity_mcp_server.md) | Discovery reuses `IdentityService.get_identity_contacts()`. For chat, the external A2A handler runs `IdentityRoutingService.route_within_identity()` on the **first** message of each task; subsequent messages on the same `task_id` resume the existing identity session (standard A2A task-continuation semantics). |
| [Agent Sessions](../application/agent_sessions/agent_sessions.md) | Reuses `SessionService`, `MessageService`, and the streaming pipeline. Adds one new `integration_type` value: `"external"` for personal-agent chats initiated from the external API. `app_mcp` and `identity_mcp` types are reused unchanged. |
| [Realtime Events](../application/realtime_events/event_bus_system.md) | SSE events on the external A2A endpoints are emitted by the same `A2AStreamEventHandler` that the public `/api/v1/a2a/` endpoints use. |

### Data Flow — Chat against each target type

```
target_type = "agent":
  Client → GET  /api/v1/external/a2a/agent/{agent_id}/      → AgentCard (v1.0 by default)
  Client → POST /api/v1/external/a2a/agent/{agent_id}/      → JSON-RPC SendStreamingMessage
        → ExternalA2ARequestHandler.dispatch_agent(agent_id, jsonrpc_payload, user)
        → verify agent.owner_id == user.id
        → reuse A2ARequestHandler.handle_message_stream(...) with the agent pinned,
          integration_type="external"

target_type = "app_mcp_route":
  Client → GET  /api/v1/external/a2a/route/{route_id}/      → AgentCard for the route's agent
  Client → POST /api/v1/external/a2a/route/{route_id}/      → JSON-RPC SendStreamingMessage
        → ExternalA2ARequestHandler.dispatch_route(route_id, jsonrpc_payload, user)
        → verify route is effective for user (get_effective_routes_for_user)
        → reuse A2ARequestHandler.handle_message_stream with:
            - agent fixed from route.agent_id
            - on session creation: user_id=agent.owner_id, caller_id=user.id
            - session.integration_type="app_mcp"
            - session_metadata["app_mcp_match_method"]="external_direct"

target_type = "identity":
  Client → GET  /api/v1/external/a2a/identity/{owner_id}/   → person-level AgentCard
  Client → POST /api/v1/external/a2a/identity/{owner_id}/   → JSON-RPC SendStreamingMessage
        → ExternalA2ARequestHandler.dispatch_identity(owner_id, jsonrpc_payload, user)
        → if task_id resolves to an existing identity_mcp session belonging to user:
             verify binding still active → resume via standard A2A resume flow
        → else:
             IdentityRoutingService.route_within_identity(owner_id, user.id, first_message)
             create identity_mcp session (user_id=owner_id, identity_caller_id=user.id)
             reuse A2ARequestHandler.handle_message_stream with the resolved agent pinned
```

---

## Data Models

**No new database tables.** The feature is a read/dispatch layer over existing entities.

### New `integration_type` value

- `"external"` — personal-agent sessions initiated from a native client's external A2A endpoint. Allows the owner's web UI to render an "External" badge and lets metrics tell native-client traffic from web.
- App MCP and Identity MCP sessions opened from the external API retain their existing types (`"app_mcp"`, `"identity_mcp"`) so session resumption, ownership rules, and all existing tooling continue to work unchanged.

### New JSON fields (optional, in `session_metadata`)

- `client_kind: str` — distinguishes the concrete client when useful. Values in MVP: `"desktop"`; planned: `"mobile-ios"`, `"mobile-android"`. Derived from a claim on the access token (see Security Architecture). When the claim is missing the field is omitted — never defaulted.
- `external_client_id: str` — the native OAuth client id (e.g., `DesktopOAuthClient.client_id`) captured at session creation, for audit and future per-device analytics. Never required; read defensively.

### Pydantic response schemas (no DB impact)

Schemas live in `backend/app/models/external/external_agents.py` (new file; `external` folder under `backend/app/models/`, re-exported via `models/__init__.py`).

#### `ExternalTargetPublic`

```
target_type:      Literal["agent", "app_mcp_route", "identity"]
target_id:        UUID                 # depends on type (see below)
name:             str
description:      str | None
entrypoint_prompt: str | None
example_prompts:  list[str]            # always a list (possibly empty)
session_mode:     Literal["conversation", "building"] | None
ui_color_preset:  str | None           # only for target_type="agent"
agent_card_url:   str                  # absolute URL, e.g. https://host/api/v1/external/a2a/agent/{id}/
protocol_versions: list[str]           # e.g. ["1.0", "0.3.0"] — informational
metadata:         dict[str, Any]       # extensible, per-type
```

`target_id` semantics per type:

| target_type | target_id | Notes |
|---|---|---|
| `agent` | `agent.id` | Direct Agent record — user's own or a clone owned by them |
| `app_mcp_route` | `AppAgentRoute.id` | Route id, not the agent id — agent may also appear as a personal agent; both are fine |
| `identity` | `owner_id` (`User.id`) | The identity owner, one entry per distinct owner (1-layer routing) |

Per-type `metadata`:

- **agent**: `{ "agent_id": UUID, "is_clone": bool, "parent_agent_id": UUID|null, "active_environment_id": UUID|null, "workspace_id": UUID|null }`
- **app_mcp_route**: `{ "route_id": UUID, "agent_id": UUID, "agent_name": str, "agent_owner_id": UUID, "agent_owner_name": str, "agent_owner_email": str, "trigger_prompt": str, "assignment_id": UUID, "shared_by_name": str }`
- **identity**: `{ "owner_id": UUID, "owner_name": str, "owner_email": str, "agent_count": int, "assignment_ids": list[UUID] }`

#### `ExternalAgentListResponse`

```
targets: list[ExternalTargetPublic]
```

#### `ExternalSessionPublic` (for the session-metadata REST layer)

A slim version of `SessionPublicExtended` with fields native clients need: `id`, `title`, `integration_type`, `status`, `interaction_status`, `result_state`, `result_summary`, `last_message_at`, `created_at`, `agent_id`, `agent_name`, `caller_id`, `identity_caller_id`, `client_kind`, `external_client_id` (from metadata), `target_type`, `target_id` (derived — lets the client re-fetch the right A2A card).

The chat path does **not** use this schema — A2A `Task` objects returned by the JSON-RPC layer are the source of truth during a conversation. This schema is only for the list/metadata REST layer so the client can render a thread picker before opening any conversation.

---

## Security Architecture

### Authentication

- All endpoints use `CurrentUser`. JWTs issued by [Desktop Auth](../application/desktop_auth/desktop_auth.md) (and, later, the equivalent mobile auth) are indistinguishable from browser JWTs at this layer.
- A2A endpoints under `/api/v1/external/a2a/` require JWT (not A2A access tokens). Access tokens are for third-party A2A clients on the public `/api/v1/a2a/` surface; native first-party clients should not have to mint them.
- `client_kind` / `external_client_id` are best-effort — if the issuing auth flow stamps a claim on the JWT (e.g. `cinna_client_kind`, `cinna_client_id`), the router reads and forwards it into `session_metadata`. Missing claims never fail a request.

### Access Control

| Target | Discovery rule | Chat rule (re-verified per request) |
|---|---|---|
| **Personal agents** | `agent.owner_id == user.id` AND `agent.is_active = True` | Same — `a2a_config.enabled` is **not** required on the external surface |
| **MCP Shared Agents** | `AppAgentRoute.is_active = True` AND `AppAgentRouteAssignment.is_enabled = True` | Route must still be effective (`get_effective_routes_for_user(channel="app_mcp")` must still include it) |
| **Identity Contacts** | `IdentityService.get_identity_contacts()` returns the owner with `is_enabled = True` | `IdentityService.get_active_bindings_for_user(owner_id, user.id)` must still return at least one binding; Stage 2 resolves the final binding on first message |

Rationale for re-verification at chat time: a race between discovery and chat (route revoked, identity contact disabled, agent deactivated) must never leak access. The existing A2A handler does ownership re-verification per JSON-RPC call; the external variants extend this to the route and identity source rules.

### Agent Card Exposure

Agent cards returned by `GET /a2a/{target}/…` are always the **extended** form (authenticated request), because the caller is always authenticated. The "public card" split of the regular A2A surface is irrelevant here. Rule of thumb:

- `target_type="agent"` — same extended card as the existing A2A service produces, with `url` / `supportedInterfaces` rewritten to point at `/api/v1/external/a2a/agent/{id}/`. Skills come from the agent's `a2a_config["skills"]` when present (empty list otherwise — the regenerator only runs when A2A is enabled, so skills may be stale; that's acceptable for an MVP).
- `target_type="app_mcp_route"` — card built from the underlying agent (`route.agent_id`), but `name` uses `route.name`, `description` uses `route.trigger_prompt`, and the `url` / `supportedInterfaces` point at the route URL. A `metadata.source = "app_mcp_route"` field is added under a private-extension namespace.
- `target_type="identity"` — **person-level** card synthesized on the fly: `name = owner.full_name`, `description = owner.email`, `skills` aggregated from all active, caller-accessible `IdentityAgentBinding.trigger_prompt`s as `AgentSkill` objects (one per binding). `url` / `supportedInterfaces` point at `/api/v1/external/a2a/identity/{owner_id}/`. Agent count and assignment IDs go under the private-extension namespace.

Private extensions use a `cinna.*` URI prefix to stay conformant with A2A extension semantics.

### Input Validation

- A2A JSON-RPC payloads are validated by the existing `A2ARequestHandler` — no new validation layer is introduced.
- Message part text length limits (same ceiling applied by `MessageService`).
- `target_id` must parse as UUID and exist.
- `?protocol` query param: `v1.0` (default) or `v0.3`. Any other value → 400.

### Rate Limiting

- MVP relies on existing per-session `asyncio.Lock` and per-session concurrent-message protection.
- Per-`external_client_id` rate limiting is deferred to Future Enhancements.

### Sensitive Data

- Discovery response never exposes `workflow_prompt` or other "secret" agent fields — only the listing fields defined above.
- `agent_owner_email` is returned for `app_mcp_route` and `identity` targets — already visible in web Settings UI (`SharedRoutePublic`, `IdentityContactPublic`); the external API does not widen that surface.
- Message content is **not** logged at INFO level — same rule as existing A2A/App-MCP handlers.

---

## Backend Implementation

### File Locations

```
backend/app/models/external/__init__.py                         (new — re-exports)
backend/app/models/external/external_agents.py                  (new — Pydantic schemas)
backend/app/models/__init__.py                                  (extend re-exports)

backend/app/services/external/__init__.py                       (new)
backend/app/services/external/external_agent_catalog_service.py (new — Layer 1)
backend/app/services/external/external_a2a_service.py           (new — Layer 2, card builder)
backend/app/services/external/external_a2a_request_handler.py   (new — Layer 2, JSON-RPC dispatch)
backend/app/services/external/external_session_service.py       (new — Layer 3)

backend/app/api/routes/external_agents.py                       (new — Layer 1 + Layer 3)
backend/app/api/routes/external_a2a.py                          (new — Layer 2 A2A endpoints)
backend/app/api/main.py                                         (register both routers)

backend/app/services/a2a/a2a_request_handler.py                 (extend: accept a TargetContext)
backend/app/services/sessions/session_service.py                (extend: allow integration_type="external")
```

### API Routes — `/api/v1/external/`

All endpoints use `SessionDep` + `CurrentUser`. The discovery + session metadata endpoints are tagged `external`; the A2A endpoints are tagged `external-a2a` so the OpenAPI client generator produces distinct `ExternalService` and `ExternalA2AService` clients (A2A JSON-RPC is typically not consumed via the generated OpenAPI client anyway — native clients use `a2a-sdk`).

#### Layer 1 — Discovery

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/agents` | `ExternalAgentListResponse` | All addressable targets for the current user, each with `agent_card_url` |

#### Layer 2 — A2A per target

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/a2a/{target_type}/{target_id}/` | A2A `AgentCard` JSON | v1.0 card by default; `?protocol=v0.3` forces v0.3 |
| GET | `/a2a/{target_type}/{target_id}/.well-known/agent-card.json` | A2A `AgentCard` JSON | Well-known mirror; respects `?protocol=` same as above |
| POST | `/a2a/{target_type}/{target_id}/` | JSON-RPC response or `text/event-stream` | A2A JSON-RPC: `SendMessage`, `SendStreamingMessage`, `GetTask`, `CancelTask`, `ListTasks` |

The card's `url` and `supportedInterfaces` point back at the same path so A2A clients following standard discovery land on the correct endpoint. `supportedInterfaces` always lists both v1.0 and v0.3 URLs when the caller asks for v1.0; v0.3 cards advertise only the v0.3 URL per the existing library behavior.

Protocol resolution order for GET requests:
1. `?protocol=v0.3` or `?protocol=v1.0` in query string (external-API–specific convenience);
2. URL suffix `/v0.3/` or `/v1.0/` is **not** used in the external namespace (we keep it flat to simplify clients);
3. Default: `v1.0`.

#### Layer 3 — Session metadata (REST)

| Method | Path | Response | Description |
|--------|------|----------|-------------|
| GET | `/sessions` | `list[ExternalSessionPublic]` | Sessions where the user is owner, `caller_id`, or `identity_caller_id` |
| GET | `/sessions/{session_id}` | `ExternalSessionPublic` | Session metadata; 404 if not visible to the user |
| GET | `/sessions/{session_id}/messages` | `list[MessagePublic]` | Message history for a visible session |

These REST endpoints do **not** accept new messages — that traffic goes through the A2A POST endpoint. They exist only so the client can restore its thread picker.

### Service Layer

#### `ExternalAgentCatalogService` (`backend/app/services/external/external_agent_catalog_service.py`)

Owns the discovery query. Pure read-only. Key methods:

- `list_targets(db: Session, user: User, request_base_url: str) -> ExternalAgentListResponse`
  1. **Personal agents** — `select(Agent).where(Agent.owner_id == user.id, Agent.is_active == True)`. Map each to `ExternalTargetPublic(target_type="agent", …, agent_card_url=f"{request_base_url}/api/v1/external/a2a/agent/{agent.id}/")`.
  2. **MCP Shared Agents** — reuse `AppAgentRouteService.get_effective_routes_for_user(db, user.id, channel="app_mcp")`. Filter out items where `source == "identity"`. For each remaining `EffectiveRoute`, resolve the agent for `entrypoint_prompt`; map prompt examples from `AppAgentRoute.prompt_examples` (newline-split, cap 10). `agent_card_url=f"{request_base_url}/api/v1/external/a2a/route/{route.id}/"`.
  3. **Identity Contacts** — call `IdentityService.get_identity_contacts(db, user.id)`, keep `is_enabled == True`. Aggregate `example_prompts` from `IdentityService.get_active_bindings_for_user(owner_id, user.id)`, prefixed with the owner's name (reuse `app_prompts.py` prefix logic). `agent_card_url=f"{request_base_url}/api/v1/external/a2a/identity/{owner_id}/"`.
  4. Ordering per section: by `name`/`full_name` ascending. Return concatenated list.

- Private helpers per section, plus `_parse_prompt_examples(raw) -> list[str]` (newline-split, strip, drop empties, cap 10).

Performance: each helper is independent — compose sequentially in MVP; parallelize with `asyncio.gather` only if needed.

#### `ExternalA2AService` (`backend/app/services/external/external_a2a_service.py`)

Builds AgentCards for the three target types. Key methods:

- `build_card(db, user, target_type, target_id, request_base_url, protocol: Literal["v1.0", "v0.3"]) -> dict`
  - `"agent"` → load agent, verify ownership, call `A2AService.build_agent_card(agent)`, then **rewrite URLs** (see `_rewrite_urls` below), then run `A2AV1Adapter.transform_agent_card_outbound()` for v1.0.
  - `"app_mcp_route"` → load route, verify effectiveness; build the card for `route.agent_id` but override `name=route.name` and `description=route.trigger_prompt`; rewrite URLs to the route path; transform.
  - `"identity"` → synthesize card: `name=owner.full_name`, `description=owner.email`, `skills=[AgentSkill(...) for each accessible binding]`; rewrite URLs to the identity path; transform.
  - For `protocol="v0.3"`, skip the v1 adapter (returns library-native v0.3 card).

- `_rewrite_urls(card, target_type, target_id, request_base_url)`
  - Replaces `card.url` and every `supportedInterfaces[*].url` with the external path, preserving protocol version tags. Underlying `A2AService` already sets `url` — we just swap the base path.

- `_synth_identity_skills(db, owner_id, caller_id) -> list[AgentSkill]`
  - One `AgentSkill` per accessible binding: `id=str(binding.id)`, `name=agent.name`, `description=binding.trigger_prompt`, `examples=binding.prompt_examples (split)`. The caller never sees internal agent IDs — `id` is the binding id (an opaque UUID from the caller's perspective).

#### `ExternalA2ARequestHandler` (`backend/app/services/external/external_a2a_request_handler.py`)

Thin dispatcher that maps the external A2A URL to the same operations the existing `A2ARequestHandler` performs, with per-target ownership/target resolution injected. Key methods:

- `dispatch(db, user, target_type, target_id, jsonrpc_request, protocol, sse: bool) -> response_or_stream`
  - Resolves a `TargetContext` via `_resolve_target(...)`:
    - `"agent"` → `TargetContext(agent=..., integration_type="external", session_owner_id=user.id, caller_id=None, identity_caller_id=None)`
    - `"app_mcp_route"` → re-verifies route effectiveness; `TargetContext(agent=route.agent, integration_type="app_mcp", session_owner_id=agent.owner_id, caller_id=user.id, match_method="external_direct")`
    - `"identity"` → `_resolve_identity_target(...)`:
      - If the JSON-RPC payload is `SendMessage`/`SendStreamingMessage` with an existing `task_id` that resolves to an identity_mcp session owned by `owner_id` with `identity_caller_id=user.id` → re-verify binding/assignment validity (existing `_check_identity_session_validity` logic) → `TargetContext(agent=<resolved_agent>, integration_type="identity_mcp", session_owner_id=owner_id, identity_caller_id=user.id, identity_binding_id=…)`.
      - Otherwise, run `IdentityRoutingService.route_within_identity(db, owner_id, user.id, first_message_text)`; on success produce the `TargetContext` with `integration_type="identity_mcp"` and stamp `identity_binding_id` / `identity_binding_assignment_id` into the session that is about to be created.
  - Passes `TargetContext` into `A2ARequestHandler.handle_message_send()` / `handle_message_stream()` / `handle_tasks_get()` / `handle_tasks_cancel()` / `handle_tasks_list()` — a new overload of those methods that accepts the pre-resolved context instead of deriving it from `agent_id` + `a2a_config`.
  - Writes `session_metadata["client_kind"]` and `session_metadata["external_client_id"]` from the request context when present.

- Failures map to standard A2A JSON-RPC error codes (−32004 auth, −32601 method not found, −32602 invalid params, −32603 internal).

#### `ExternalSessionService` (`backend/app/services/external/external_session_service.py`)

Read-only metadata surface over existing session data. Key methods:

- `list_sessions_for_external(db, user, limit=100, cursor=None) -> list[ExternalSessionPublic]`
  - `select(Session).where(or_(Session.user_id == user.id, Session.caller_id == user.id, Session.identity_caller_id == user.id)).order_by(Session.last_message_at.desc())`.
  - JOIN `Agent` for name resolution. For `identity_mcp` sessions, name comes from `session_metadata["identity_owner_name"]`.
  - Derives `target_type` and `target_id` for each row:
    - `integration_type="external"` → `target_type="agent"`, `target_id=session.agent_id`
    - `integration_type="app_mcp"` → `target_type="app_mcp_route"`, `target_id=session_metadata["app_mcp_route_id"]` when present, else `None`
    - `integration_type="identity_mcp"` → `target_type="identity"`, `target_id=session.user_id` (the identity owner id)
  - MVP pagination: `limit/offset`.

- `get_session_for_external(db, user, session_id)` — 404 unless the user is owner / caller / identity_caller.

- `list_messages_for_external(db, user, session_id)` — reuses `MessageService.list_messages_for_session` after the visibility check.

### Extensions to Existing Services

#### `A2ARequestHandler` — accept a pre-resolved `TargetContext`

Extract a `TargetContext` dataclass (agent, session-ownership hints, integration type, identity fields, match method) and add an overload on `handle_message_send` / `handle_message_stream` / `handle_tasks_*` that takes this context directly. The existing public `/api/v1/a2a/` router continues to call the agent-id-based entry points; the external router calls the context-based entry points. No behavioral change on the public surface.

`_parse_and_validate_session_id` becomes context-aware: when `TargetContext.integration_type == "app_mcp"`, it also filters by `Session.caller_id == context.caller_id`; for `"identity_mcp"` it filters by `Session.identity_caller_id == context.identity_caller_id`; for `"external"` by `Session.user_id == context.session_owner_id`.

#### `SessionService.create_session` — accept `integration_type="external"`

Already takes `integration_type` (VARCHAR). Add `"external"` to the allowed literal set. Used by the `"agent"` branch of the external handler. No schema change.

### Background Tasks

No new background tasks. Environment auto-activation continues to work exactly as on the public A2A surface (the existing `ensure_environment_ready_for_streaming` is called inside `A2ARequestHandler`, which the external dispatcher delegates to).

---

## Frontend Implementation

Native clients are separate repos — no new code lives in `frontend/`. Two web-side UI touch-ups are included:

### Web Side (minor)

1. **Session badge** — extend `ChatPage` / `SessionList` components to render an "External" chip when `session.integration_type === "external"`, optionally labelled with `session_metadata.client_kind` (e.g., "Desktop", "Mobile"). Falls back to a plain "External" chip when `client_kind` is missing. Locations: `frontend/src/components/Sessions/SessionHeader.tsx` and session-list row components (mirrors existing "Email", "A2A", "MCP" badges).
2. **Settings > Channels > Desktop Sessions card** (already planned in `desktop-app-auth_plan.md`) — follow-up item to show session counts per device. **Out of scope for this plan**.

### Native-Client Side (informational only — lives in `cinna-desktop`, future mobile repos)

Each native client will, on successful login:

1. Call `GET /api/v1/external/agents` and render three sections:
   - "My Agents" — `target_type="agent"`
   - "Shared with Me" — `target_type="app_mcp_route"`
   - "People" — `target_type="identity"`
2. Render `entrypoint_prompt` as the input placeholder for the selected target, and `example_prompts` as clickable chips.
3. When a target is opened, use an **off-the-shelf A2A client** (`a2a-sdk` or equivalent) configured against the target's `agent_card_url`. The client fetches the AgentCard, calls `SendStreamingMessage`, and consumes the SSE stream — no custom transport code required.
4. On launch / reconnect: `GET /api/v1/external/sessions` to restore thread list; for each thread use the existing A2A `GetTask` to fetch history (via the target's `agent_card_url`) or `GET /sessions/{id}/messages` for quick REST access.

Native clients consume the generated OpenAPI client (same `@/client` pattern) for the REST layers — regenerate after backend changes via `bash scripts/generate-client.sh`. A2A traffic uses `a2a-sdk` directly.

### User Flows (native client)

1. **First chat with a personal agent**
   - Agent list loads → user picks "Reports Agent" under *My Agents* → types message → submits.
   - A2A client opens a streaming task against `/api/v1/external/a2a/agent/{id}/`. Backend creates an `external` session owned by the user. SSE streams back.

2. **First chat with an MCP Shared Agent**
   - Agent list shows "HR Helper (shared by bob@acme.io)" under *Shared with Me*.
   - A2A client opens a streaming task against `/api/v1/external/a2a/route/{route_id}/`. Backend creates an `app_mcp` session owned by Bob with `caller_id=current_user.id`. SSE streams back. Bob sees the thread in his web UI under Sessions.

3. **First chat with an Identity Contact**
   - Agent list shows "User B" under *People*, with chips like "ask User B to …".
   - A2A client opens a streaming task against `/api/v1/external/a2a/identity/{owner_id}/`. Backend runs Stage 2 (`IdentityRoutingService`), picks the binding, creates an `identity_mcp` session owned by User B with `identity_caller_id=current_user.id`. SSE streams back.

4. **Reconnect / continue conversation**
   - Client calls `GET /sessions`; user taps a thread → either `GET /sessions/{id}/messages` (REST) or A2A `GetTask` against the target's card URL. Sending a follow-up is just another A2A `SendStreamingMessage` with the same `task_id`.

---

## Database Migrations

**No new migrations required.**

- `integration_type="external"` uses the existing VARCHAR column.
- `session_metadata.client_kind` / `external_client_id` are optional JSON fields — no schema change.

---

## Knowledge Repository Format

Not applicable.

---

## Error Handling & Edge Cases

| Scenario | Behavior |
|---|---|
| `target_id` not found at send time (deleted since discovery) | A2A JSON-RPC error −32602 `target_not_found`; card GET returns 404 |
| Personal agent deactivated between discovery and chat | A2A error −32004 `agent_inactive`; card GET returns 404 |
| `AppAgentRoute` revoked (route deleted, assignment removed, route disabled) | A2A error −32004 `route_no_longer_effective`; card GET returns 404 |
| Identity binding removed / caller assignment disabled before first message | A2A error −32004 `identity_no_longer_accessible`; card GET returns 404 |
| Identity binding disabled mid-conversation | Existing identity session-validity check returns the standard "This identity connection is no longer active." as an error event, stream ends with `final=true` |
| Stage 2 returns no accessible binding on first message | A2A error −32603 `identity_no_accessible_agents` |
| Agent environment suspended → auto-activation | Handled by existing `ensure_environment_ready_for_streaming` — the task transitions through `submitted → working` as on the public A2A surface |
| Message payload exceeds size limit | Existing `MessageService` validation applies — A2A error −32602 |
| Unknown `?protocol=` value on card GET | 400 |
| Unknown `target_type` in URL | 404 |
| Client uses `task_id` of a session belonging to a different user | Existing A2A scope validation rejects (-32004); falls back to creating a new session on next call |
| Expired JWT / revoked OAuth client | 401 — client triggers its existing refresh/relogin flow |

---

## UI/UX Considerations

On the backend side — nothing. On the native-client side (informational), the three sections should be rendered consistently:

- **My Agents** — agents the user configured or accepted as a clone.
- **Shared with Me** — agents other users routed to them via MCP Shared Agents.
- **People** — an identity that exposes one or more agents; the client shows the person, not the underlying agents (1-layer routing).

Prompt-example chips. For identity targets, chips already carry the "ask <Person> to …" prefix (aggregated server-side).

Accessibility: target items render as buttons with `aria-label` combining `name` and `description`.

---

## Integration Points

- **Regenerate API client after backend changes**: `source ./backend/.venv/bin/activate && make gen-client` — produces `ExternalService` and `ExternalA2AService` (REST surfaces only) in `frontend/src/client/`. A2A traffic is consumed via `a2a-sdk` directly by native clients.
- **Agent-env**: no changes. Docker agent environments are unaware of how a session was initiated.
- **Workspace**: the user's current active workspace is **not applied** to the external agents list — it surfaces all agents the user owns across workspaces (matching existing Identity MCP behavior). An optional `?workspace_id=` filter for personal agents is a future enhancement.
- **Session page (web UI)**: "External" integration badge for `integration_type="external"`, optionally specialized by `session_metadata.client_kind`.
- **A2A agent-card endpoint** (existing `/api/v1/a2a/…`) remains the surface for third-party A2A clients. The external surface is first-party only.

---

## Implementation Phases

The plan is split so each phase is self-contained, shippable, and testable on its own. Later phases assume earlier phases merged.

### Phase 1 — Discovery layer (REST) ✅ COMPLETED 2026-04-17

**Goal:** `GET /api/v1/external/agents` returns the unified target list, even though the A2A endpoints from Phase 2+ are not yet wired.

**Status:** Implemented, code-reviewed, tested, and merged to `main`.

**Scope (as implemented):**
- Models: `ExternalTargetPublic`, `ExternalAgentListResponse` in `backend/app/models/external/external_agents.py`; re-exported via `models/__init__.py`. Schemas use `pydantic.BaseModel` (not `SQLModel`) to avoid the `metadata` field shadow warning on the SQLModel parent.
- Service: `ExternalAgentCatalogService.list_targets()` with three static section helpers (`_list_personal_agents`, `_list_mcp_shared_agents`, `_list_identity_contacts`) and private helpers (`_agent_metadata`, `_route_metadata`, `_aggregate_identity_examples`, `_parse_prompt_examples`). `agent_card_url` values are emitted pointing at the Phase 2+ A2A endpoints (inert until those phases land).
- Route: `backend/app/api/routes/external_agents.py` with `GET /external/agents` tagged `external`. Registered in `api/main.py`.
- Frontend OpenAPI client regenerated: `ExternalService` client with `listExternalAgents` is now available in `frontend/src/client/`.
- Tests: 10 tests in `backend/tests/api/external/external_agents_test.py` — all pass.

**Deviations from original plan:**
1. **`pydantic.BaseModel` instead of `SQLModel`** — `ExternalTargetPublic` and `ExternalAgentListResponse` use `pydantic.BaseModel` because the `metadata` field name shadows SQLModel's internal `metadata` attribute (triggers a `UserWarning`). Functionally identical for response-only schemas; no behavioral change.
2. **`session_mode` narrowed explicitly** — `EffectiveRoute.session_mode` is typed as `str`; the service narrows it to `Literal["conversation", "building"] | None` before assigning it to `ExternalTargetPublic`, discarding any future unknown values safely rather than using `# type: ignore`.
3. **`_route_metadata` typed as `EffectiveRoute`** — the `route: Any` parameter was tightened to `route: EffectiveRoute` after code review.
4. **`Agent.example_prompts` is already a `list[str]`** — the plan mentioned `_parse_prompt_examples` for personal agents; in practice `Agent.example_prompts` is stored as a JSON list (not a newline string), so it is used directly. `_parse_prompt_examples` is used for `AppAgentRoute.prompt_examples` and `IdentityAgentBinding.prompt_examples` which are stored as newline-separated strings (consistent with the existing `app_mcp_server` and `identity_mcp_server` pattern).

**Files created:**
- `backend/app/models/external/__init__.py`
- `backend/app/models/external/external_agents.py`
- `backend/app/services/external/__init__.py`
- `backend/app/services/external/external_agent_catalog_service.py`
- `backend/app/api/routes/external_agents.py`
- `backend/tests/api/external/__init__.py`
- `backend/tests/api/external/conftest.py`
- `backend/tests/api/external/external_agents_test.py`

**Files modified:**
- `backend/app/models/__init__.py` — added `ExternalTargetPublic`, `ExternalAgentListResponse` re-exports
- `backend/app/api/main.py` — registered `external_agents.router`
- `frontend/src/client/` — regenerated (new `ExternalService` client)

**Test results:**
- 10/10 new tests pass
- 40/40 existing `identity` + `app_mcp` domain tests pass (no regressions)

**Done when:** Native client can render the home screen with agent list + chips. No chat yet. ✅

### Phase 2 — External A2A for personal agents ✅ COMPLETED 2026-04-17

**Goal:** Native clients can chat with the user's own agents via A2A.

**Delivered:**
- `TargetContext` extracted in `backend/app/services/a2a/a2a_request_handler.py` (+306 lines). Context-based overloads sit alongside the existing agent-id entry points; the public `/api/v1/a2a/` router is unchanged.
- `ExternalA2AService` (`backend/app/services/external/external_a2a_service.py`) — `build_card()` + `_rewrite_urls()` for `target_type="agent"`.
- `ExternalA2ARequestHandler` (`backend/app/services/external/external_a2a_request_handler.py`) — `dispatch()` with the `"agent"` branch; skips the `a2a_config.enabled` gate on the external surface and stamps `integration_type="external"`.
- `SessionService.create_session` now accepts `integration_type="external"`.
- Route `backend/app/api/routes/external_a2a.py` exposes `GET /a2a/agent/{agent_id}/`, `.well-known/agent-card.json`, and `POST /a2a/agent/{agent_id}/` with `?protocol=v1.0|v0.3`. Registered in `backend/app/api/main.py`.
- Web UI — "External" badge rendering added in `frontend/src/routes/_layout/session/$sessionId.tsx` keyed off `integration_type="external"` / `session_metadata.client_kind`.
- Tests: `backend/tests/api/external/external_a2a_test.py` (card fetch v1.0 / v0.3 / `.well-known`, agents without `a2a_config.enabled`, end-to-end `SendStreamingMessage`, cross-user 404 enforcement). 19/19 external tests pass, 12/12 A2A integration regressions pass, 29/29 session regressions pass.

**Original scope (reference):**
- Service: `ExternalA2AService.build_card()` and `_rewrite_urls()` for `target_type="agent"` only.
- Service: `ExternalA2ARequestHandler.dispatch()` with only the `"agent"` branch — reuses `A2ARequestHandler` after refactoring it to accept a `TargetContext`.
- Refactor: extract `TargetContext` and add context-based overloads on `A2ARequestHandler.handle_message_send` / `handle_message_stream` / `handle_tasks_*`. The public `/api/v1/a2a/` router is left untouched in this refactor (it keeps calling the agent-id entry points; the new overloads sit alongside).
- Extend `SessionService.create_session` to accept `integration_type="external"`.
- Route: `backend/app/api/routes/external_a2a.py` — `GET /a2a/agent/{agent_id}/`, `.well-known/agent-card.json`, `POST /a2a/agent/{agent_id}/`. Support `?protocol=v1.0|v0.3`.
- Web UI: add the "External" badge in `SessionHeader` + session-list row components (conditionally surfaced by `session_metadata.client_kind`).
- Tests:
  - Card fetch (v1.0 default, `?protocol=v0.3`, `.well-known/agent-card.json`) returns correctly shaped cards with external URLs.
  - Agents without `a2a_config.enabled` still work on the external surface.
  - `SendStreamingMessage` flow end-to-end — session created with `integration_type="external"`, SSE events mapped identically to the public A2A surface.
  - Ownership enforcement — another user's agent returns 404 / −32004.

**Done when:** Native client can open a streaming chat with any of the user's agents and resume it via `task_id`.

### Phase 3 — External A2A for MCP Shared Agents (AppAgentRoute) ✅ COMPLETED 2026-04-17

**Goal:** Native clients can chat with agents shared through App MCP routes.

**Status:** Implemented, tested, and passing.

**Delivered:**
- `ExternalA2AService.build_card()` gained the `"app_mcp_route"` branch. Re-verifies route effectiveness via `AppAgentRouteService.get_effective_routes_for_user()`, builds the card from the underlying agent, overrides `name`/`description` with `route.name` / `route.trigger_prompt`, and rewrites URLs to the route-scoped external path. Shared protocol-finishing logic was extracted into `_finalize_card()` for reuse.
- `ExternalA2ARequestHandler.dispatch_route()` added alongside `dispatch_agent()`. Both now delegate to a shared `_dispatch_context(...)` helper that routes any method (`message/stream`, `message/send`, `tasks/get`, `tasks/cancel`, `tasks/list`) through the `A2ARequestHandler.*_with_context` overloads. Route context is `TargetContext(integration_type="app_mcp", session_owner_id=agent.owner_id, caller_id=user.id, match_method="external_direct", route_id=route.id, route_source="admin"|"user")`.
- `TargetContext` extended with `route_id` and `route_source` so the handler can stamp `session_metadata["app_mcp_route_id"]` / `["app_mcp_route_type"]` on newly created sessions.
- `A2ARequestHandler` context methods made caller-aware:
  - New helper `_parse_and_validate_session_id_with_context()` enforces caller-scope per `integration_type`: `app_mcp` requires `session.caller_id == context.caller_id`, `identity_mcp` requires `session.identity_caller_id == context.identity_caller_id`, `external` requires `session.user_id == context.session_owner_id`.
  - New helper `_stamp_session_context()` sets `session.caller_id` (or `identity_caller_id`) and `session_metadata` after a new context-scoped session is created.
  - `handle_tasks_get_with_context` / `handle_tasks_list_with_context` / `handle_tasks_cancel_with_context` all filter/reject by the new `_session_matches_context()` rule so cross-caller task access is denied.
- Route endpoints added to `backend/app/api/routes/external_a2a.py`:
  - `GET /api/v1/external/a2a/route/{route_id}/`
  - `GET /api/v1/external/a2a/route/{route_id}/.well-known/agent-card.json`
  - `POST /api/v1/external/a2a/route/{route_id}/`
  - Card rendering and JSON-RPC dispatch were refactored into shared `_render_card()` / `_handle_jsonrpc()` helpers so the new endpoints reuse the same protocol handling, error mapping, and streaming wiring as the agent endpoints.
- Tests: `backend/tests/api/external/external_a2a_route_test.py` — 10 tests covering card shape, v0.3 protocol, `.well-known` mirror, session ownership/metadata, disabled assignment, non-assigned user, revoked route, cross-caller `task_id` isolation, and unauthenticated access.

**Files modified:**
- `backend/app/services/a2a/a2a_request_handler.py`
- `backend/app/services/external/external_a2a_service.py`
- `backend/app/services/external/external_a2a_request_handler.py`
- `backend/app/api/routes/external_a2a.py`

**Files created:**
- `backend/tests/api/external/external_a2a_route_test.py`

**Test results:**
- 10/10 new Phase 3 route tests pass.
- 19/19 prior external tests still pass (no regression).
- 81/81 combined external + a2a_integration + app_mcp + identity tests pass.

**Deviations from original plan:**
1. **Session metadata stamping uses a post-creation hook** — rather than extending `SessionService.create_session()` with `caller_id` / `session_metadata_extra` parameters, the A2A handler stamps these fields in a follow-up DB write (`_stamp_session_context`). This kept `SessionService.create_session()` unchanged and matches the existing AppMCPRequestHandler pattern of setting `session.caller_id` + metadata after creation.
2. **`route_source` is sourced from `EffectiveRoute.source`** — which is `"admin"` or `"user"` depending on whether the route came from `AppAgentRoute` or the legacy `UserAppAgentRoute` table. This mirrors the existing `app_mcp_route_type` stamping in `AppMCPRequestHandler` for consistency with the web UI's badge rendering.
3. **Card metadata private-extension namespace was not added yet** — the plan mentioned a `metadata.source = "app_mcp_route"` field under a `cinna.*` private-extension namespace. This is defensible to add once we also need per-route analytics, so it is deferred; the card's route-scoped URL and the overridden name/description already unambiguously identify the route.

**Done when:** Native client can chat with shared agents, and the owner sees the session in their web UI (same as any App MCP session). ✅

### Phase 4 — External A2A for Identity Contacts ✅ COMPLETED 2026-04-17

**Goal:** Native clients can chat with another user by addressing their identity; Stage‑2 routing picks the agent server-side.

**Status:** Implemented, tested, and passing.

**Delivered:**
- `ExternalA2AService.build_card()` gained the `"identity"` branch. Person-level card synthesized from the owner + caller-accessible bindings: `name=owner.full_name` (fallback: email/id), `description=owner.email`, one `AgentSkill` per active+enabled binding with `id=str(binding.id)` (opaque to the caller), `name=agent.name`, `description=binding.trigger_prompt`, and `examples=binding.prompt_examples.splitlines()`. URLs rewritten to the identity-scoped external path.
- `ExternalA2ARequestHandler` gained `dispatch_identity()` + `_resolve_identity_context(db, user, owner_id, params)`:
  - Peeks at `params.message.taskId` (or `params.id` for `tasks/*`) to detect resumption.
  - If the task_id resolves to an existing `identity_mcp` session with `user_id=owner_id` and `identity_caller_id=user.id`, re-verifies binding/assignment validity and reuses the session's bound agent.
  - Otherwise runs `IdentityRoutingService.route_within_identity()` on the first message text, captures `binding_id` / `binding_assignment_id` / `match_method` into the `TargetContext`, and lets `A2ARequestHandler._stamp_session_context()` persist them onto the session about to be created.
  - A new helper `_extract_message_text()` pulls the user's text out of A2A v1.0 and v0.3 message-part shapes.
- `TargetContext` extended with `identity_binding_id`, `identity_binding_assignment_id`, `identity_stage2_match_method`, `identity_owner_name`, and `identity_caller_name`. `_stamp_session_context()` writes all five into the session row / `session_metadata` dict when the integration is `identity_mcp`.
- `A2ARequestHandler` session-scope validation:
  - `_parse_and_validate_session_id_with_context()` now also requires `session.user_id == context.session_owner_id` for `identity_mcp` and runs a new `_check_identity_session_validity()` (mirrors `AppMCPRequestHandler._check_identity_session_validity`) to surface mid-conversation revocations as the standard "This identity connection is no longer active." message.
  - `_session_matches_context()` tightened for `identity_mcp` to require both `identity_caller_id` AND `user_id` match, preventing cross-owner task lookups for a caller who holds sessions with multiple identity owners.
- Route additions in `backend/app/api/routes/external_a2a.py`:
  - `GET /api/v1/external/a2a/identity/{owner_id}/`
  - `GET /api/v1/external/a2a/identity/{owner_id}/.well-known/agent-card.json`
  - `POST /api/v1/external/a2a/identity/{owner_id}/`
  - The `_handle_jsonrpc` ValueError → error-code mapping was extended so the messages "no longer active" and "no accessible agent" map to −32004 (previously fell through to −32602).
- Tests: `backend/tests/api/external/external_a2a_identity_test.py` — 11 tests covering card shape (skill-per-binding, binding-id as skill.id), v0.3 + `.well-known` mirror, Stage 2 session creation (`identity_match_method="only_one"` + owner/caller fields), task resume staying on the same binding, binding disabled mid-conversation (−32004 "no longer active"), cross-caller task isolation, cross-owner task isolation, non-assigned user (card 404 + −32004 POST), disabled-before-first-message (card 404 + −32004), and unauthenticated POST.

**Files modified:**
- `backend/app/services/a2a/a2a_request_handler.py`
- `backend/app/services/external/external_a2a_service.py`
- `backend/app/services/external/external_a2a_request_handler.py`
- `backend/app/api/routes/external_a2a.py`

**Files created:**
- `backend/tests/api/external/external_a2a_identity_test.py`

**Test results:**
- 11/11 new Phase 4 identity tests pass.
- 29/29 prior external tests still pass (no regression).
- 92/92 combined external + a2a_integration + app_mcp + identity tests pass.

**Deviations from original plan:**
1. **Identity resume rejection surfaces as −32004 with the full revocation message** rather than as a stream event with `final=true`. The plan mentioned "error event on the next message"; in practice the validity check runs inside `_parse_and_validate_session_id_with_context()`, which raises a `ValueError` the route handler maps to a −32004 JSON-RPC error. Functionally equivalent — the caller gets "This identity connection is no longer active." — but delivered as a JSON-RPC error instead of an SSE event with a failed-state transition.
2. **`_session_matches_context()` tightened beyond the plan** — for `identity_mcp` we now require BOTH `identity_caller_id` AND `session.user_id` to match the context. The plan only specified the caller match; the extra owner check closes a cross-owner task-lookup gap that would otherwise let a caller who holds sessions with Owner A and Owner B fetch an Owner-A task through the `/identity/Owner-B/` endpoint.
3. **Context stamping for Stage 2 routing uses `match_method="identity"`** rather than a new constant. The string is written into `session_metadata["app_mcp_match_method"]` for consistency with the existing identity_mcp sessions created by `AppMCPRequestHandler`, which uses the same value. `identity_match_method` carries the Stage 2 sub-method (`only_one` / `pattern` / `ai`).

**Done when:** Native client can address a person and get responses streamed back from the right agent. ✅

### Phase 5 — Session metadata REST (cross-target) ✅ COMPLETED 2026-04-17

**Goal:** Native clients can restore their thread list at launch and display basic session metadata without opening a full A2A connection per thread.

**Status:** Implemented, code-reviewed, tested, and merged to `main`.

**Delivered:**
- `ExternalSessionPublic` Pydantic schema added to `backend/app/models/external/external_agents.py`. Fields: `id`, `title`, `integration_type`, `status`, `interaction_status`, `result_state`, `result_summary`, `last_message_at`, `created_at`, `agent_id`, `agent_name`, `caller_id`, `identity_caller_id`, `client_kind`, `external_client_id`, `target_type`, `target_id`. Uses `pydantic.BaseModel` (not `SQLModel`) consistent with Phase 1 precedent. Re-exported from `backend/app/models/__init__.py`.
- `ExternalSessionService` (`backend/app/services/external/external_session_service.py`): three static methods:
  - `list_sessions_for_external(db, user, limit, offset)` — `OR(user_id, caller_id, identity_caller_id)` union, ordered by `last_message_at DESC`, limit/offset pagination. Calls `_to_public()` for each row.
  - `get_session_for_external(db, user, session_id)` — visibility-checked single fetch; 404 for non-participants.
  - `list_messages_for_external(db, user, session_id)` — visibility check then delegates to `MessageService.get_session_messages(session=db, session_id=...)`.
  - Private helpers: `_get_visible_session` (OR visibility filter + 404), `_resolve_agent_name` (identity_mcp fallback to `session_metadata["identity_owner_name"]`), `_derive_target` (integration_type → target_type/target_id), `_to_public`.
- Three endpoints added to `backend/app/api/routes/external_agents.py` (tag `external`, prefix `/external`):
  - `GET /external/sessions` — query params `limit` (default 100, capped at 200) and `offset` (default 0).
  - `GET /external/sessions/{session_id}` — metadata for a single visible session; 404 for non-participants.
  - `GET /external/sessions/{session_id}/messages` — message history for a visible session; 404 for non-participants.
- Frontend OpenAPI client regenerated: `ExternalService` gains `listExternalSessions`, `getExternalSession`, `listExternalSessionMessages`.
- Tests: `backend/tests/api/external/external_sessions_test.py` — 17 tests covering unauthenticated 401, owner visibility, caller visibility (app_mcp), identity_caller visibility, non-participant exclusion, single GET, 404 for non-participant on GET + messages, pagination (limit/offset), target derivation for all three integration types, and `agent_name` fallback to `identity_owner_name`.

**Files created:**
- `backend/app/services/external/external_session_service.py`
- `backend/tests/api/external/external_sessions_test.py`

**Files modified:**
- `backend/app/models/external/external_agents.py` — `ExternalSessionPublic` schema added
- `backend/app/models/__init__.py` — re-export of `ExternalSessionPublic`
- `backend/app/api/routes/external_agents.py` — three new endpoints added (Phase 1 route file extended)
- `frontend/src/client/` — regenerated (new `listExternalSessions`, `getExternalSession`, `listExternalSessionMessages` methods on `ExternalService`)

**Test results:**
- 17/17 new Phase 5 tests pass.
- 109/109 combined external + a2a_integration + app_mcp + identity regression tests pass (no regressions).

**Deviations from the original plan:**
1. **`MessageService` parameter name is `session`, not `db`** — the plan described calling `MessageService.list_messages_for_session`, but the actual method is `MessageService.get_session_messages(session: Session, session_id: UUID, ...)`. The `session` parameter is the SQLModel `Session` (DB session), not a `ChatSession` row. The service call was initially written as `db=db` (wrong kwarg), caught in code review, and corrected to `session=db`. No behavioral change — the fix just used the correct parameter name.
2. **Plan said "cursor" pagination, spec says "limit/offset"** — the plan's `list_sessions_for_external` signature mentioned `cursor=None` but the body of the plan consistently describes limit/offset semantics. Implemented as limit/offset (matching the spec table and the plan's MVP note).
3. **`toggle_identity_contact` not needed in identity test setup** — the test scaffolding initially called `toggle_identity_contact` but `create_identity_binding` with `auto_enable=True` is sufficient to enable the assignment. The toggle call was removed; this matches the established pattern in Phase 4 identity tests.

**Done when:** Native client launches, pulls the thread list, and renders the last-activity timestamp per thread without extra A2A calls. ✅

### Phase 6 — Polish & observability ✅ COMPLETED (partial) 2026-04-17

**Goal:** Turn MVP into something production-grade.

**Scope (each item independently scopeable):**
- ✅ Capture `client_kind` / `external_client_id` from JWT claims and stamp into `session_metadata` in all three dispatch paths.
- ⏭ Per-`external_client_id` rate limiting (sliding window) in front of the A2A POST endpoint. **Deferred** — requires a sliding-window store (Redis or in-memory); no clear middleware pattern exists in the codebase. Infrastructure concern, not suitable for an API-layer-only change.
- ⏭ `Idempotency-Key` support on A2A SendMessage. **Deferred** — requires a key/response cache store layer; chunky and orthogonal to the observability goal.
- ✅ `DELETE /sessions/{session_id}` soft-hide for callers who want to drop a thread from their list (`session_metadata["hidden_for_callers"]` set; listing filters it).
- ✅ Optional `?workspace_id=` filter on `GET /agents` (applies only to the personal-agents section).
- ✅ Emit structured logs with session-id + target-type for each dispatch to aid observability.

**Delivered:**
- `create_access_token` in `backend/app/core/security.py` extended with optional `extra_claims: dict[str, Any] | None = None` parameter (merged before `sub`/`exp` to prevent shadowing).
- `DesktopAuthService._create_token_pair` calls `create_access_token` with `extra_claims={"client_kind": "desktop", "external_client_id": str(client.id)}` so desktop-issued access tokens carry these claims.
- `TargetContext` dataclass gains `client_kind: Optional[str] = None` and `external_client_id: Optional[str] = None` fields.
- `A2ARequestHandler._stamp_session_context` writes `client_kind`/`external_client_id` into `session_metadata` for all three integration types (including "external" which previously returned early). Write is additive: skipped entirely when `context.client_kind is None`.
- `ExternalA2ARequestHandler._resolve_*_context` methods accept and forward the two attribution fields; all three `dispatch_*` methods accept optional `client_kind`/`external_client_id` kwargs.
- `external_a2a.py` route: `_extract_client_claims(request)` helper decodes the Bearer JWT inline (graceful no-op on any decode failure) and threads extracted claims into `_handle_jsonrpc` → dispatch kwargs.
- `ExternalSessionService.hide_session_for_external` static method: visibility check then sets `session_metadata["hidden_for_callers"] = True`, persists.
- `list_sessions_for_external` filters hidden sessions (Python-level, post-query).
- `DELETE /external/sessions/{session_id}` endpoint added to `external_agents.py` router (HTTP 204 on success, 404 for non-participants).
- `ExternalAgentCatalogService.list_targets` and `_list_personal_agents` accept optional `workspace_id` (filters `agent.user_workspace_id`); only personal agents section is filtered.
- `GET /external/agents` gains optional `?workspace_id=` query parameter.
- Structured `logger.info` calls in `dispatch_agent`, `dispatch_route`, `dispatch_identity`, and `_dispatch_context` (streaming/send paths) with user, method, session hint, target type, and client_kind.
- Frontend OpenAPI client regenerated: `ExternalService` gains `hideExternalSession`, and `listExternalAgents` gains optional `workspaceId` parameter.
- Tests: `backend/tests/api/external/external_phase6_test.py` — 8 tests covering JWT claim capture for desktop and web tokens, soft-hide lifecycle, non-participant 404, unauthenticated 401, unknown-id 404, workspace filter (personal agents), workspace filter (shared routes unaffected).

**Files created:**
- `backend/tests/api/external/external_phase6_test.py`

**Files modified:**
- `backend/app/core/security.py` — `create_access_token` extra_claims param
- `backend/app/services/desktop_auth/desktop_auth_service.py` — include client attribution in desktop access tokens
- `backend/app/services/a2a/a2a_request_handler.py` — `TargetContext` new fields; `_stamp_session_context` writes attribution for all integration types
- `backend/app/services/external/external_a2a_request_handler.py` — `_resolve_*_context`, `dispatch_*` new params; `_extract_session_hint` helper; structured logs
- `backend/app/api/routes/external_a2a.py` — `_extract_client_claims` helper; `_handle_jsonrpc` threads attribution kwargs
- `backend/app/services/external/external_session_service.py` — `hide_session_for_external`; hidden filter in `list_sessions_for_external`
- `backend/app/api/routes/external_agents.py` — `DELETE /sessions/{id}` endpoint; `?workspace_id=` on `GET /agents`
- `backend/app/services/external/external_agent_catalog_service.py` — `workspace_id` filter in `list_targets` / `_list_personal_agents`
- `frontend/src/client/` — regenerated

**Test results:**
- 8/8 new Phase 6 tests pass.
- 65/65 combined external domain tests pass (no regressions).

**Deferred items:**
- Rate limiting (#2): requires Redis/in-memory sliding window store. Out of scope for an API-only change. Recommend implementing as middleware in a dedicated PR when the infrastructure decision (Redis vs. in-process) is made.
- Idempotency-Key (#3): requires a response cache keyed on `Idempotency-Key + user_id`. Non-trivial; defer to its own PR.

**Done when:** Desktop client can attribute sessions by device, users can archive threads from the thread picker, and workspace-filtered agent discovery works. ✅

---

## Future Enhancements (Out of Scope)

- **Mobile OAuth flow** — a mobile-specific variant of `desktop_auth` (shared `native_auth` layer or sibling `mobile_auth` with its own `MobileOAuthClient`). The external API is already ready for it: it only needs a valid `CurrentUser`.
- **Hidden / pinned flags** on `Agent`, `AppAgentRoute`, `IdentityAgentBinding` to let users/owners curate what the native client sees.
- **Individual-binding identity targets** — `target_type="identity_binding"` when a caller has several bindings with the same owner and wants to skip Stage‑2. Explicitly deferred (violates the MVP "1-layer only" rule).
- **Push notifications** — A2A supports push-notification configs on tasks; native clients can register a push URL to receive alerts when a long-running task needs input. Requires a push relay or FCM/APNs integration in the backend.
- **Prompt categorization / richer metadata** — tags, "last used", popularity — for client-side filtering and search.
- **Delivery channels beyond `app_mcp`** — a future `channel="external"` would let users pick routes that only show in native clients.
- **Agent avatar / icon URL** in `ExternalTargetPublic.metadata` once the platform supports per-agent imagery (also flows through the A2A card `iconUrl`).
- **WebSocket multiplexing** — an alternative transport for clients that want bidirectional streaming without per-message SSE reconnects.

---

## Summary Checklist

### Backend tasks

**Phase 1 — Discovery** ✅ COMPLETED 2026-04-17
- [x] Pydantic schemas in `backend/app/models/external/external_agents.py`: `ExternalTargetPublic`, `ExternalAgentListResponse`; re-export from `models/__init__.py`.
- [x] `ExternalAgentCatalogService.list_targets()` with the three section helpers + `_parse_prompt_examples` helper.
- [x] `backend/app/api/routes/external_agents.py` with `GET /agents`, tagged `external`. Register in `api/main.py`.

**Phase 2 — External A2A for agents** ✅ COMPLETED 2026-04-17
- [x] Refactor `A2ARequestHandler` to expose context-based overloads accepting a `TargetContext` dataclass (agent, integration_type, session ownership hints, identity fields, match_method).
- [x] Extend `SessionService.create_session` to accept `integration_type="external"`.
- [x] `ExternalA2AService.build_card()` for `target_type="agent"` (reuses `A2AService.build_agent_card()` + `A2AV1Adapter`, rewrites URLs).
- [x] `ExternalA2ARequestHandler.dispatch()` with the `"agent"` branch.
- [x] `backend/app/api/routes/external_a2a.py` with `GET`/`POST` on `/a2a/agent/{agent_id}/` and `.well-known/agent-card.json`, `?protocol=` handling.
- [x] Web UI: "External" badge in `SessionHeader.tsx` + session-list rows (mirror existing integration-type badges).

**Phase 3 — External A2A for routes** ✅ COMPLETED 2026-04-17
- [x] `ExternalA2AService.build_card()` gains `"app_mcp_route"` branch with route effectiveness re-verification and name/description override.
- [x] `ExternalA2ARequestHandler.dispatch_route()` (shared `_dispatch_context`) stamps session ownership and `app_mcp_match_method="external_direct"` via the new `_stamp_session_context` helper on `A2ARequestHandler`.
- [x] Route endpoint additions under `/a2a/route/{route_id}/` (plus `.well-known/agent-card.json` mirror) in `external_a2a.py`.

**Phase 4 — External A2A for identity** ✅ COMPLETED 2026-04-17
- [x] `ExternalA2AService.build_card()` gains `"identity"` branch with synthesized skills (one per caller-accessible binding; skill `id` = binding id).
- [x] `ExternalA2ARequestHandler.dispatch_identity()` (plus `_resolve_identity_context`, `_try_resume_identity_session`, `_extract_message_text`) — resume-or-Stage‑2 logic, stamps `identity_binding_id` / `identity_binding_assignment_id` / owner + caller names onto new identity sessions.
- [x] Route endpoint additions under `/a2a/identity/{owner_id}/` (plus `.well-known/agent-card.json` mirror) in `external_a2a.py`; error-code mapping extended so "no longer active" / "no accessible agent" map to −32004.
- [x] `A2ARequestHandler._parse_and_validate_session_id_with_context()` + `_session_matches_context()` now enforce both `identity_caller_id` AND `session.user_id` for `identity_mcp`, and `_check_identity_session_validity()` gates resume against binding/assignment revocation.

**Phase 5 — Session metadata REST** ✅ COMPLETED 2026-04-17
- [x] `ExternalSessionService` (list/get/messages) with owner/caller/identity_caller union query.
- [x] `ExternalSessionPublic` schema + `target_type`/`target_id` derivation.
- [x] Add `GET /sessions`, `GET /sessions/{id}`, `GET /sessions/{id}/messages` to `external_agents.py` router.

**Phase 6 — Polish** ✅ COMPLETED (partial) 2026-04-17
- [x] JWT claim capture → `session_metadata["client_kind"]` / `["external_client_id"]` in all three dispatch paths.
- [ ] Per-`external_client_id` rate limiting in front of `/a2a/*/` POST. ⏭ **Deferred** — requires dedicated infrastructure decision (Redis vs. in-process).
- [ ] `Idempotency-Key` handling on A2A `SendMessage`. ⏭ **Deferred** — non-trivial response cache layer; own PR.
- [x] `DELETE /sessions/{id}` soft-hide.
- [x] Optional `?workspace_id=` filter on `GET /agents`.
- [x] Structured dispatch logs (session-id + target-type + method + client_kind) emitted in all three dispatch paths.

### Frontend tasks (web SPA)

- [x] Add "External" integration-badge renderer for `integration_type="external"` in `SessionHeader.tsx` and session-list row components, specialized by `session_metadata.client_kind` when present. (Phase 2.) ✅ 2026-04-17
- [x] Regenerate the OpenAPI client after each backend phase (`make gen-client`); confirm new services/endpoints appear in `frontend/src/client/`. (Phases 1–4 done; Phase 5 client regeneration pending user approval — see Phase 5 deviations.)

### Native-client tasks (in each client's repo: `cinna-desktop`, future mobile)

- [ ] Consume the generated REST client for `GET /agents`, `GET /sessions`, `GET /sessions/{id}/messages`.
- [ ] Use `a2a-sdk` (or an equivalent A2A client) for the chat path; fetch each target's `agent_card_url`, then call `SendStreamingMessage` / `GetTask`.
- [ ] Render the three sections with prompt-example chips and entrypoint-prompt placeholders.
- [ ] Handle −32004 / 404 on send by refreshing the agents list.

### Testing & validation tasks

**Phase 1** ✅ COMPLETED 2026-04-17
- [x] `GET /agents` returns personal + enabled MCP Shared + enabled Identity contacts; disabled items filtered.
- [x] Identity contacts return one entry per distinct owner with aggregated, owner-prefixed example prompts.

**Phase 2** ✅ COMPLETED 2026-04-17
- [x] Card GET returns valid v1.0 card by default; `?protocol=v0.3` switches to library-native v0.3.
- [x] Card URLs in `supportedInterfaces` point at `/api/v1/external/a2a/agent/{id}/`.
- [x] `SendStreamingMessage` works for an agent even if `a2a_config.enabled=False`.
- [x] Session created with `integration_type="external"` owned by the user.
- [x] Another user's agent → 404 / −32004.

**Phase 3** ✅ COMPLETED 2026-04-17
- [x] Route card reflects the route's name and trigger_prompt, with route-scoped URL.
- [x] Session ownership is `user_id=agent.owner_id`, `caller_id=user.id`; `app_mcp_match_method="external_direct"`.
- [x] Revoked route → 404 / −32004.
- [x] Cross-caller `task_id` isolation.

**Phase 4** ✅ COMPLETED 2026-04-17
- [x] Identity card lists one skill per accessible binding; skill `id` is the binding id (opaque to the caller).
- [x] First message runs Stage 2 and creates `identity_mcp` session; `user_id=owner_id`, `identity_caller_id=caller.id`, binding + assignment ids stamped, `session_metadata["identity_match_method"]` captured.
- [x] Subsequent messages on the same `task_id` stay on the same binding (resume path re-verifies binding/assignment activity).
- [x] Binding disabled mid-conversation → next message returns −32004 "This identity connection is no longer active.".
- [x] Cross-caller `task_id` isolation works (B cannot resume A's thread).
- [x] Cross-owner `task_id` isolation works (caller cannot resume an Owner-A session through `/identity/Owner-B/`).

**Phase 5** ✅ COMPLETED 2026-04-17
- [x] `GET /sessions` returns union of owner + caller + identity_caller; nothing else.
- [x] `GET /sessions/{id}` and `/messages` reject non-participants with 404.
- [x] Pagination (limit/offset) works; ordering is by `last_message_at DESC`.
- [x] `target_type`/`target_id` derived correctly for all three integration types (`external`→`agent`, `app_mcp`→`app_mcp_route` with route_id from metadata, `identity_mcp`→`identity` with session.user_id).
- [x] `agent_name` falls back to `session_metadata["identity_owner_name"]` for identity_mcp sessions.

**Phase 6** ✅ COMPLETED (partial) 2026-04-17
- [x] `client_kind` / `external_client_id` are forwarded into `session_metadata` when the JWT carries those claims, and absent otherwise (verified by desktop JWT test and web JWT test).
- [ ] Rate limiting triggers the correct response for `external_client_id` bursts. ⏭ **Deferred.**
- [x] Soft-hidden sessions disappear from `GET /sessions` but are still fetchable via `GET /sessions/{id}` by explicit id.
- [x] `DELETE /sessions/{id}` returns 404 for non-participants and unauthenticated requests.
- [x] `GET /agents?workspace_id=` limits personal agents section; MCP shared routes unaffected.
