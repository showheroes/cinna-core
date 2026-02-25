# Agent Guest Sessions - Integration Architecture

## Overview

Agents can be shared with unauthenticated (or authenticated) users via **guest share links** — time-limited, token-based URLs that give anyone instant access to chat with an agent in conversation mode. The feature reuses the existing JWT auth infrastructure by adding a `role` claim (`"chat-guest"`) and follows the access token pattern for token generation, hashing, and management.

An authenticated user who opens a guest share link receives a **GuestShareGrant** record instead of a new JWT, avoiding token conflicts. Anonymous visitors receive a scoped guest JWT. In both cases, guest sessions run in the agent owner's environment, are tagged with `guest_share_id`, and are visible to the owner.

## Core Concepts

### Naming Convention

This feature uses the **`guest_share`** prefix throughout the codebase (models, routes, services, components) to clearly distinguish it from the existing **agent sharing** system (clone-based sharing for registered users via `agent_share`).

| Concept | Agent Sharing (`share` / `clone`) | Guest Share (`guest_share`) |
|---|---|---|
| **What is shared** | Full agent clone (copied to recipient's account) | Temporary chat access via link (no account needed) |
| **Recipient** | Registered platform user (by email) | Anyone with the link (anonymous) |
| **Requires account** | Yes | No |
| **Result** | Independent agent copy owned by recipient | Ephemeral sessions owned by the link creator |
| **Lifetime** | Permanent (until detached/deleted) | Time-limited (hours to days) |
| **DB table** | `agent_share` | `agent_guest_share` |
| **Route prefix** | `/agents/{id}/shares` | `/agents/{id}/guest-shares` |
| **Session field** | N/A | `session.guest_share_id` |

### Security Model: Token-Based Access

**Problem**: Sharing an agent currently requires the recipient to have a platform account — friction for quick demos, user testing, or support scenarios.

**Solution**: Generate scoped, time-limited bearer tokens embedded in URLs. The token is hashed (SHA256) before storage — only the hash is persisted. The feature supports two access paths:

- **Anonymous visitors**: Receive a guest JWT (`role: "chat-guest"`) containing the `guest_share_id`, `agent_id`, and `owner_id`
- **Authenticated users**: Receive a `GuestShareGrant` record (keep their existing JWT, no token replacement)

### Architecture Pattern

Following the **A2A access token pattern**:
- Owner creates guest share links with configurable expiration (1h, 24h, 7d, 30d)
- Token is generated via `secrets.token_urlsafe(32)`, hashed with SHA256 for lookup, raw token also stored for owner re-access
- Token prefix (first 8 chars) stored for display identification
- Guest sessions execute in the agent owner's environment
- Sessions are tagged with `guest_share_id` for scoping and owner visibility

### Two Access Paths: Anonymous vs Authenticated

```
User opens guest share link: /guest/{guest_share_token}
        |
GET /guest-share/{token}/info  (validity, requires_code, is_code_blocked)
        |
Has valid guest JWT in localStorage?
        |
+------ YES (page refresh) ------+---------- NO -----------+
| Reuse existing JWT,            |                          |
| skip code entry,               | requires_code?           |
| go straight to ready           |    |                     |
+--------------------------------+ YES → show code screen   |
                                 |    (auto-submit on       |
                                 |     first attempt)       |
                                 |    |                     |
                                 | NO ↓                     |
                                 +----+---------------------+
                                      |
                     Has existing JWT in localStorage?
                                      |
              +------------------------+--------------------------------+
              | No existing JWT        | Has existing JWT (logged in)   |
              | (anonymous visitor)    |                                |
              +------------------------+--------------------------------+
              |                        |                                |
              | POST /guest-share/     | POST /guest-share/             |
              |   {token}/auth         |   {token}/activate             |
              |                        | (with user JWT in Auth header) |
              |        |               |          |                     |
              | Backend issues guest   | Backend creates                |
              | JWT (role=chat-guest)  | GuestShareGrant record:        |
              |        |               |   (user_id, guest_share_id)    |
              | Store in localStorage  |          |                     |
              |        |               | User keeps existing JWT        |
              | Use guest JWT for      |          |                     |
              | all API calls          | Frontend redirects to guest    |
              |                        | share page, uses same JWT      |
              +------------------------+--------------------------------+
                                       |
                            Guest chats in conversation mode
```

### JWT Token Structure

**Regular user token** (unchanged):
```json
{
  "sub": "<user_id>",
  "role": "user",
  "exp": "<expiration>"
}
```

**Guest share token** (issued only to anonymous visitors):
```json
{
  "sub": "<guest_share_id>",
  "role": "chat-guest",
  "agent_id": "<agent_id>",
  "owner_id": "<owner_user_id>",
  "token_type": "guest_share",
  "exp": "<expiration>"
}
```

Guest JWT lifetime is capped at 24 hours but never exceeds the guest share link's own expiry.

### Access Control

**New dependency**: `get_current_user_or_guest()` in `deps.py`

Returns either a `User` object (regular JWT) or a `GuestShareContext` object (guest JWT):

```
GuestShareContext:
  guest_share_id: UUID
  agent_id: UUID
  owner_id: UUID
  is_anonymous: bool     # True if JWT role=chat-guest
  user_id: UUID | None   # None for anonymous guests
```

**Resolution logic**:
1. Decode JWT
2. If `role == "chat-guest"` and `token_type == "guest_share"` → build `GuestShareContext` from claims
3. Otherwise → resolve as regular user via `TokenPayload`

**Endpoint access matrix**:

| Action | Regular user | User with grant | Anonymous guest |
|--------|-------------|-----------------|-----------------|
| Own agents/sessions | Yes | Yes | No |
| Guest share sessions (create/list/get) | No (not their agent) | Yes (scoped) | Yes (scoped) |
| Guest share message send/stream | No | Yes (conversation only) | Yes (conversation only) |
| Workspace tree/download/view | Yes (own) | Yes (guest share's env) | Yes (guest share's env) |
| Agent config/update | Yes (own) | No | No |
| Credentials / environment management | Yes | No | No |
| Building mode | Yes (own) | No | No |
| Guest share management (CRUD) | Yes (owner) | No | No |

### Session Ownership and Visibility

- Guest share sessions are created with `user_id = agent.owner_id` (sessions run in the owner's environment)
- The `guest_share_id` field on the session links it to the specific guest share link
- The agent owner sees all sessions (including guest sessions) in their normal session list
- Guests see only sessions matching their `guest_share_id`
- Conversation mode is enforced for all guest share sessions

## File Structure

### New Files

```
backend/app/
├── models/
│   └── agent_guest_share.py           # AgentGuestShare + GuestShareGrant models
│
├── services/
│   └── agent_guest_share_service.py   # Token CRUD, validation, auth, grants
│
├── api/routes/
│   └── guest_shares.py                # Owner management + guest auth routers
│
└── alembic/versions/
    ├── f53ac2dee553_add_agent_guest_share_tables.py
    └── w3r4s5t6u7v8_add_security_code_to_guest_shares.py

backend/tests/
├── api/agents/
│   ├── guest_shares_test.py           # Owner CRUD tests
│   ├── guest_shares_auth_test.py      # Anonymous auth + grant activation tests
│   ├── guest_shares_sessions_test.py  # Session access control tests
│   └── guest_shares_security_code_test.py  # Security code verification tests
└── utils/
    └── guest_share.py                 # Test utilities for guest share creation

frontend/src/
├── components/Agents/
│   └── GuestShareCard.tsx             # Owner UI: create/list/delete guest share links
├── hooks/
│   └── useGuestShare.tsx              # GuestShareProvider context + useGuestShare hook
└── routes/guest/
    └── $guestShareToken.tsx           # Public guest chat page
```

### Modified Files

```
backend/app/
├── models/
│   ├── session.py                     # Added: guest_share_id field on Session + schemas
│   └── __init__.py                    # Registered new model exports
├── services/
│   └── session_service.py             # Added: guest_share_id param on create_session()
├── api/
│   ├── main.py                        # Registered guest_shares router + guest_router
│   ├── deps.py                        # Added: GuestShareContext, get_current_user_or_guest(),
│   │                                  #   CurrentUserOrGuest dependency
│   └── routes/
│       ├── sessions.py                # Updated: CurrentUserOrGuest, guest share access checks,
│       │                              #   guest_share_id filter on list
│       ├── messages.py                # Updated: CurrentUserOrGuest, guest share access checks
│       └── workspace.py               # Updated: CurrentUserOrGuest, _verify_workspace_read_access()

backend/tests/utils/
├── session.py                         # Added: guest_share_id support
└── user.py                            # Updated for guest share test utilities

frontend/src/
├── components/Agents/
│   └── AgentIntegrationsTab.tsx       # Added: GuestShareCard render
├── main.tsx                           # Updated: route registration
├── routeTree.gen.ts                   # Auto-regenerated
└── client/                            # Auto-regenerated (schemas, sdk, types)
    ├── schemas.gen.ts
    ├── sdk.gen.ts
    └── types.gen.ts
```

## Database Schema

### New Tables

**`agent_guest_share`** — Guest share link records

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID, PK | |
| `agent_id` | UUID, FK → `agent.id` CASCADE | Agent this link gives access to |
| `owner_id` | UUID, FK → `user.id` CASCADE | User who created the link |
| `label` | string (max 255), nullable | Optional description (e.g., "Demo for client X") |
| `token_hash` | string, not null | SHA256 hash of the bearer token (used for lookup) |
| `token_prefix` | string (max 12) | First 8 chars for display identification |
| `token` | string, nullable | Raw token stored for owner re-access (share URL reconstruction) |
| `expires_at` | datetime, not null | When the link stops working |
| `created_at` | datetime | |
| `is_revoked` | boolean, default False | Manual revocation flag |
| `security_code_encrypted` | string, nullable | Fernet-encrypted 4-digit security code |
| `failed_code_attempts` | integer, default 0 | Number of failed code entry attempts |
| `is_code_blocked` | boolean, default False | True after 3 failed attempts |

**Indexes:** `agent_id`, `owner_id`, `token_hash`

**`guest_share_grant`** — Tracks which authenticated users have activated a guest share link

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID, PK | |
| `user_id` | UUID, FK → `user.id` CASCADE | Authenticated user who activated the link |
| `guest_share_id` | UUID, FK → `agent_guest_share.id` CASCADE | Which guest share link was activated |
| `activated_at` | datetime | When the grant was created |

**Constraints:** `UNIQUE(user_id, guest_share_id)` — one grant per user per link, idempotent activation. CASCADE on `guest_share_id` — deleting the guest share removes all grants.

### Updated Tables

**`session`** — Added field:
- `guest_share_id` (UUID, nullable, FK → `agent_guest_share.id` SET NULL): Tracks which guest share created this session. SET NULL on delete so sessions are preserved even after guest share link is removed.

## API Endpoints

### Owner Management

**Router**: `backend/app/api/routes/guest_shares.py` — prefix: `/api/v1/agents/{agent_id}/guest-shares`, tags: `guest-shares`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/` | Create guest share link (includes generated security code) | CurrentUser (owner) |
| `GET` | `/` | List guest share links (with session counts, decrypted security codes) | CurrentUser (owner) |
| `GET` | `/{guest_share_id}` | Get single guest share (with decrypted security code) | CurrentUser (owner) |
| `PUT` | `/{guest_share_id}` | Update guest share (label, security code; resets block state) | CurrentUser (owner) |
| `DELETE` | `/{guest_share_id}` | Delete guest share link | CurrentUser (owner) |

### Guest Auth Flow

**Router**: `backend/app/api/routes/guest_shares.py` (second router) — prefix: `/api/v1/guest-share`, tags: `guest-share`

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `POST` | `/{token}/auth` | Authenticate anonymous guest → returns guest JWT (accepts optional `security_code` in body) | None |
| `POST` | `/{token}/activate` | Activate grant for logged-in user (accepts optional `security_code` in body) | CurrentUser |
| `GET` | `/{token}/info` | Get public info (agent name, validity, `requires_code`, `is_code_blocked`) | None |

### Modified Endpoints

**Sessions** (`/api/v1/sessions`):
- `POST /` — Accepts optional `guest_share_id`, validates guest share context, forces conversation mode
- `GET /` — Accepts optional `guest_share_id` query parameter for filtering; auto-filters for anonymous guests
- `GET /{id}` — Verifies guest share access via `_verify_session_access()`

**Messages** (`/api/v1/sessions/{session_id}/messages`):
- All message endpoints (`GET /messages`, `POST /messages/stream`, `POST /messages/interrupt`, `GET /messages/streaming-status`) now accept `CurrentUserOrGuest` and verify access via `_verify_message_access()`

**Workspace** (`/api/v1/environments/{env_id}/workspace`):
- `GET /tree`, `GET /download/{path}`, `GET /view-file/{path}` — Accept `CurrentUserOrGuest` and verify access via `_verify_workspace_read_access()` (checks agent ownership or grant)

## Service Architecture

### AgentGuestShareService

**File**: `backend/app/services/agent_guest_share_service.py`

All methods are `@staticmethod` on `AgentGuestShareService`:

| Method | Description |
|--------|-------------|
| `create_guest_share()` | Generate token, hash, security code, store raw token, create DB record, return token + share_url + security_code |
| `list_guest_shares()` | Query by agent_id with session_count subquery, ordered by created_at DESC; includes share_url, decrypted security_code |
| `get_guest_share()` | Get single share with session count; includes share_url, decrypted security_code |
| `update_guest_share()` | Update label and/or security code; new code resets failed_code_attempts and is_code_blocked |
| `delete_guest_share()` | Ownership check, delete record (CASCADE removes grants, SET NULL on sessions) |
| `validate_token()` | Hash lookup, check not revoked, check not expired |
| `authenticate_anonymous()` | Validate token → verify security code → issue guest JWT (capped at 24h) |
| `activate_for_user()` | Validate token → verify security code → UPSERT grant via `INSERT ... ON CONFLICT DO NOTHING` |
| `get_guest_share_info()` | Public info: agent name, description (first 200 chars), validity, requires_code, is_code_blocked |
| `check_grant()` | Query grant for (user_id, guest_share_id), verify parent share still valid |
| `_hash_token()` | SHA256 helper |
| `_verify_security_code()` | Decrypt stored code, compare, track failed attempts, block after 3 failures |
| `_create_guest_jwt()` | Build JWT with `role: "chat-guest"`, `sub: guest_share_id`, etc. |
| `_find_share_by_token()` | Find share by token without validity checks (for error differentiation) |

### Auth Layer

**File**: `backend/app/api/deps.py`

Added:
- `GuestShareContext` — SQLModel with `guest_share_id`, `agent_id`, `owner_id`, `is_anonymous`, `user_id`
- `get_current_user_or_guest()` — Decodes JWT; returns `User` for regular tokens, `GuestShareContext` for guest tokens
- `CurrentUserOrGuest` — Annotated type alias for the dependency

The existing `get_current_user()` and `CurrentUser` remain unchanged — endpoints that don't support guest access continue using `CurrentUser`.

### Access Verification Helpers

Each route file that supports guest access has a verification helper:

- **`sessions.py`**: `_verify_session_access(caller, chat_session, db_session)` — checks session ownership, guest share ID match, or grant existence
- **`messages.py`**: `_verify_message_access(caller, chat_session, db_session)` — same logic as session access
- **`workspace.py`**: `_verify_workspace_read_access(caller, agent, db_session)` — checks agent ownership or any grant for the agent

### Integration Points with Existing Services

| Existing Service | Integration |
|------------------|-------------|
| `SessionService` | `create_session()` accepts `guest_share_id` parameter |
| `deps.py` | New `CurrentUserOrGuest` dependency used by sessions, messages, workspace routes |
| `AgentIntegrationsTab` | `GuestShareCard` component added to the grid |
| Session components | Reused in guest chat view (MessageList, MessageInput, EnvironmentPanel) |

## Frontend Architecture

### Owner: Guest Share Card

**Component**: `frontend/src/components/Agents/GuestShareCard.tsx`
**Location**: Agent Integrations tab, third card after Access Tokens

Features:
- List active guest share links with label, expiration, session count, status badges
- Create dialog: label input + expiration selector (1h, 24h, 7d, 30d)
- Token display dialog on creation with copy button
- Copy share link button on each active share in the list (owner can re-copy at any time)
- Delete button with AlertDialog confirmation
- Status badges: Active (green), Expired (red), Revoked (gray)
- React Query: query key `["guest-shares", agentId]`, mutations for create/delete

### Guest: Chat Page

**Route**: `frontend/src/routes/guest/$guestShareToken.tsx` (public route, NOT under `_layout/`)

**Page flow**:
1. Extract token from URL params
2. Call `GET /guest-share/{token}/info` for validity check
3. If invalid → show error screen with appropriate message
4. If link is blocked (`is_code_blocked`) → show blocked error screen
5. Check localStorage for existing valid guest JWT (handles page refresh after code entry — skips code screen if token is still valid)
6. If no valid JWT and `requires_code` → show security code entry screen
7. Authenticate:
   - No JWT → call `POST /guest-share/{token}/auth`, store guest JWT
   - Has JWT → call `POST /guest-share/{token}/activate`, keep existing JWT
   - If activate fails with 401/403 → fallback to anonymous auth
8. Render guest chat UI

**Component structure**:

```
GuestChatPage
├── GuestChatHeader
│   ├── Agent name + icon
│   ├── Agent description or "Guest Session" label
│   └── App (environment panel) toggle button
├── GuestSessionSidebar (left panel, hidden on mobile)
│   ├── "New Session" button
│   └── Session list (filtered by guest_share_id, polling every 10s)
├── GuestEmptyState (when no session selected)
│   └── "Start a conversation" prompt with New Session button
└── GuestChatArea (when session selected)
    ├── MessageList (reused)
    ├── EnvironmentPanel (reused)
    └── MessageInput (reused, conversation mode)
```

**Key components reused from existing UI**: `MessageList`, `MessageInput`, `EnvironmentPanel`, `useSessionStreaming`

### Guest Share Context

**Hook**: `frontend/src/hooks/useGuestShare.tsx`

Provides `GuestShareProvider` context wrapping the guest chat page:
```
GuestShareContext:
  isGuest: boolean
  guestShareId: string | null
  agentId: string | null
  guestShareToken: string | null
```

Used by child components to detect guest context and hide restricted UI elements.

### Error States

| State | Display |
|-------|---------|
| Loading | Bot icon + "Loading..." spinner |
| Security code entry | Bot icon + agent name + 4-digit code input + "Continue" button. Auto-submits when all 4 digits are filled (typed or pasted) on the first attempt. After a failed attempt, auto-submit is disabled and the user must press Enter or click "Continue" manually. |
| Authenticating | Bot icon + "Connecting to {agent}..." spinner |
| Invalid link | Error icon + "This guest share link is invalid or has been removed." |
| Expired link | Error icon + "This guest share link has expired. Contact the owner for a new link." |
| Link blocked | Error icon + "This share link has been blocked due to too many failed attempts." |
| Generic error | Error icon + "Something went wrong. Please try again." |

## Security Considerations

### 1. Token Security
- Tokens generated via `secrets.token_urlsafe(32)` (256-bit entropy)
- SHA256 hash stored in DB for fast token lookup
- Raw token also stored in DB so the owner can re-copy the share link (returned only via authenticated owner endpoints)
- Token prefix (first 8 chars) stored for display identification
- Token embedded in URL path: `https://app.example.com/guest/{token}`

### 2. JWT Security
- Guest JWT lifetime capped at 24 hours (or share expiry, whichever is sooner)
- Backend validates guest share status on every request (not just JWT validity)
- Expired/revoked shares immediately block access even if JWT is still valid

### 3. Grant-Based Access (Authenticated Users)
- No JWT replacement — user never loses their existing session
- Multi-tab safe — all tabs share the same JWT
- Owner can test own links without losing owner-level access
- Grants cascade-delete with the guest share link

### 4. Security Code Verification
- Every new guest share link is created with a random 4-digit security code
- The code is encrypted (Fernet) and stored in `security_code_encrypted`
- Guests must provide the correct code before auth/activate succeeds
- After 3 failed attempts, the link is blocked (`is_code_blocked = True`)
- The owner can view the current code via the list/get endpoints
- The owner can set a new code via the PUT update endpoint, which resets `failed_code_attempts` and `is_code_blocked`
- The info endpoint exposes `requires_code` and `is_code_blocked` (no code value) for the frontend to gate the auth flow
- Old shares without a code (`security_code_encrypted IS NULL`) are exempt from verification for backward compatibility

### 5. Bearer Token Risk
- Guest share links are bearer tokens — anyone with the link has access until expiration or revocation
- The mandatory security code adds a second factor: possession of the link alone is insufficient
- Deleting a guest share link immediately invalidates all associated access
- Guest actions execute in the agent owner's environment (owner's resources are used)

### 6. Scope Restrictions
- Guests cannot access credentials, building mode, agent configuration, or environment management
- Database query/schema endpoints remain owner-only (no guest access)
- Conversation mode enforced for all guest share sessions

## Error Handling

### Token Validation

| Scenario | HTTP Status | Detail |
|----------|-------------|--------|
| Token not found | 404 | "Guest share not found" |
| Token expired or revoked | 410 | "Guest share link has expired or been revoked" |
| Invalid JWT format | 403 | "Could not validate credentials" |
| Guest share ID mismatch | 403 | "Guest share ID mismatch" |
| Agent ID mismatch | 403 | "Agent ID mismatch with guest share" |
| Building mode requested | 400 | "Guest share sessions only support conversation mode" |
| Security code required | 403 | "Security code is required" |
| Incorrect security code | 403 | "Incorrect security code. N attempt(s) remaining." |
| Link blocked (3 failures) | 403 | "This share link has been blocked due to too many failed attempts. Contact the owner." |

### Concurrency

- **Grant UPSERT**: Uses `INSERT ... ON CONFLICT DO NOTHING` for idempotent grant creation
- **Session count**: Computed on read via subquery (not cached), always accurate
- **Token deletion**: CASCADE handles grant cleanup atomically

## Implementation References

**Models**:
- `backend/app/models/agent_guest_share.py` — `AgentGuestShare` (includes raw `token` field, security code fields), `AgentGuestShareBase`, `AgentGuestShareCreate`, `AgentGuestShareUpdate`, `AgentGuestSharePublic` (includes `share_url`, `security_code`, `is_code_blocked`), `AgentGuestShareCreated`, `AgentGuestSharesPublic`, `GuestShareGrant`, `GuestShareTokenPayload`
- `backend/app/models/session.py` — `Session` (added `guest_share_id`), `SessionCreate` (added `guest_share_id`), `SessionPublic`/`SessionPublicExtended` (added `guest_share_id`)

**Services**:
- `backend/app/services/agent_guest_share_service.py` — `AgentGuestShareService` (token CRUD, validation, auth, grants)
- `backend/app/services/session_service.py` — `create_session()` (added `guest_share_id` parameter)

**Auth Layer**:
- `backend/app/api/deps.py` — `GuestShareContext`, `get_current_user_or_guest()`, `CurrentUserOrGuest`

**API Routes**:
- `backend/app/api/routes/guest_shares.py` — Owner management router + guest auth router
- `backend/app/api/routes/sessions.py` — Guest share access checks on create/list/get
- `backend/app/api/routes/messages.py` — Guest share access checks on all message endpoints
- `backend/app/api/routes/workspace.py` — Guest share access checks on tree/download/view

**Frontend**:
- `frontend/src/components/Agents/GuestShareCard.tsx` — Owner management card
- `frontend/src/components/Agents/AgentIntegrationsTab.tsx` — GuestShareCard integration
- `frontend/src/routes/guest/$guestShareToken.tsx` — Public guest chat page
- `frontend/src/hooks/useGuestShare.tsx` — Guest share context provider + hook

**Tests**:
- `backend/tests/api/agents/guest_shares_test.py` — Owner CRUD tests
- `backend/tests/api/agents/guest_shares_auth_test.py` — Anonymous auth + grant activation tests
- `backend/tests/api/agents/guest_shares_sessions_test.py` — Session access control tests
- `backend/tests/api/agents/guest_shares_security_code_test.py` — Security code verification tests
- `backend/tests/utils/guest_share.py` — Test utilities

**Migration**:
- `f53ac2dee553` — `agent_guest_share` table + `guest_share_grant` table + `session.guest_share_id` column
- `w3r4s5t6u7v8` — `security_code_encrypted`, `failed_code_attempts`, `is_code_blocked` columns on `agent_guest_share`

## Benefits

1. **Zero-Friction Sharing**: Anyone with a link can chat with an agent — no signup, no login, no onboarding
2. **Reuses Existing Infrastructure**: Same JWT auth, same session/message/workspace APIs, same React components — just one new role claim
3. **Two Access Paths**: Anonymous visitors get guest JWT; authenticated users get grants (no token conflicts)
4. **Time-Limited by Design**: Guest share links expire, with configurable duration (1h to 30d)
5. **Owner Visibility**: All guest sessions appear in the owner's session list, tagged with `guest_share_id`
6. **Conversation-Only**: Guests are restricted to conversation mode — no building, no credentials, no agent config
7. **Immediate Revocation**: Deleting a guest share link immediately blocks all access (backend validates on every request)
8. **Multi-Tab Safe**: Authenticated users keep their JWT — grant-based access avoids localStorage conflicts

## Related Documentation

- [Guest Share Concept](agent_guest_sessions_concept.md) — Original design concept with detailed UX flows and authentication architecture
- [Guest Share Implementation Plan](agent_guest_share_implementation.md) — Phased implementation plan with task breakdowns
- [A2A Access Tokens](../a2a/agent_integration_access_tokens.md) — Similar token-based access pattern for machine clients
- [Shared Agents Management](../business-domain/shared_agents_management.md) — Clone-based sharing for registered users (uses `agent_share` naming)
- [Agent Sessions - Business Logic](business_logic.md) — Session model, modes, and authorization rules
- [Authentication](../business-domain/authentication.md) — JWT infrastructure, user model, auth dependencies
