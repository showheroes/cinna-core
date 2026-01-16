# A2A Access Tokens

## Purpose

Provides scoped JWT-based authentication tokens for external A2A clients to access agents without full user credentials.

## Feature Overview

1. User creates access token for a specific agent via UI
2. Token is generated with mode, scope, and 5-year expiration
3. External client uses token in Authorization header for A2A requests
4. Backend validates token and enforces mode/scope restrictions
5. Sessions created via token are linked for scope enforcement

## Architecture

```
External Client → A2A Router → Auth Context → A2A Request Handler → Session/Message Services
                      ↓
              Access Token Validation
                      ↓
              Mode/Scope Enforcement
```

### Authentication Flow

```
Token in Header → get_a2a_auth_context() → Decode JWT
                          ↓
                  Check token_type='agent'
                          ↓
            ┌─────────────┴─────────────┐
            ↓                           ↓
    A2A Token                    User JWT Token
            ↓                           ↓
    Validate against DB         Standard user auth
            ↓                           ↓
    Return A2AAuthContext       Return A2AAuthContext
    (with payload+token_id)     (with user)
```

## Token Properties

### Mode

Controls which agent modes the token can access:

| Mode | Description | Allowed Operations |
|------|-------------|-------------------|
| `conversation` | Default. Chat-only access | message/send, message/stream in conversation mode |
| `building` | Full access (includes conversation) | All modes including building |

### Scope

Controls session visibility:

| Scope | Description | Session Access |
|-------|-------------|----------------|
| `limited` | Default. Isolated access | Only sessions created by this token |
| `general` | Full access | All sessions for the agent (including UI-created) |

**Use Cases:**
- `limited`: Share agent with external users who shouldn't see your conversations
- `general`: Your own external UI that needs access to all sessions

## Data/State Lifecycle

### Token States

| State | Description |
|-------|-------------|
| Active | Token is valid and usable |
| Revoked | Token marked as revoked, cannot be used |
| Expired | Token past expiration date (5 years from creation) |
| Deleted | Token removed from database |

### Session-Token Relationship

- Sessions store `access_token_id` when created via A2A token
- `limited` scope tokens can only access sessions where `session.access_token_id` matches
- `general` scope tokens can access all sessions for the agent
- If token is deleted, sessions retain `access_token_id` (SET NULL on delete)

## Database Schema

**Migration:** `backend/app/alembic/versions/f6a7b8c9d0e1_add_agent_access_tokens.py`

**Tables:**
- `agent_access_tokens` - Token metadata (name, mode, scope, hash, prefix, expiration, revoked status)

**Models:** `backend/app/models/agent_access_token.py`
- `AgentAccessToken` (table model)
- `AgentAccessTokenPublic`, `AgentAccessTokenCreated`, `AgentAccessTokenCreate`, `AgentAccessTokenUpdate` (schemas)
- `AccessTokenMode`, `AccessTokenScope` (enums)
- `A2ATokenPayload` (JWT payload structure)

**Updated:** `backend/app/models/session.py`
- `Session.access_token_id` - Foreign key to `agent_access_tokens.id` (nullable, SET NULL on delete)

## Backend Implementation

### API Routes

**Token Management:** `backend/app/api/routes/access_tokens.py`

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/agents/{agent_id}/access-tokens/` | GET | List all tokens for agent |
| `/api/v1/agents/{agent_id}/access-tokens/` | POST | Create new token (returns JWT once) |
| `/api/v1/agents/{agent_id}/access-tokens/{token_id}` | GET | Get token details |
| `/api/v1/agents/{agent_id}/access-tokens/{token_id}` | PUT | Update name or revoke |
| `/api/v1/agents/{agent_id}/access-tokens/{token_id}` | DELETE | Delete token |

**A2A Routes:** `backend/app/api/routes/a2a.py`
- `get_a2a_auth_context()` - Dependency that handles both auth types
- `A2AAuthContext` - Dataclass holding user or A2A token context
- Mode checking before `message/send` and `message/stream`

### Services

**AccessTokenService:** `backend/app/services/access_token_service.py`
- `create_token()` - Generate JWT, hash it, store in DB, return once
- `verify_a2a_token()` - Decode JWT, check token_type='agent'
- `validate_token_for_agent()` - Verify token exists, not revoked, hash matches
- `get_agent_tokens()` - List tokens for agent
- `update_token()` - Update name or revoked status
- `delete_token()` - Remove from database
- `can_access_session()` - Check scope allows session access
- `can_use_mode()` - Check mode allows requested operation

**A2ARequestHandler:** `backend/app/services/a2a_request_handler.py`
- Constructor accepts `a2a_token_payload` and `access_token_id`
- `_get_or_create_session()` - Stores `access_token_id` on new sessions, checks scope on existing
- `handle_tasks_get()` - Checks scope before returning task
- `handle_tasks_cancel()` - Checks scope before canceling

**SessionService:** `backend/app/services/session_service.py`
- `create_session()` - Accepts optional `access_token_id` parameter

### JWT Token Structure

JWT payload (`A2ATokenPayload`):
- `sub` - Token ID (UUID)
- `agent_id` - Agent UUID this token is for
- `mode` - "conversation" or "building"
- `scope` - "limited" or "general"
- `token_type` - Always "agent" (distinguishes from user tokens)
- `exp` - Expiration timestamp (5 years from creation)

### Token Security

- Token value is never stored, only SHA256 hash
- Token prefix (first 8 chars) stored for identification
- Token value returned only once on creation
- Hash verification on every use
- `last_used_at` updated on successful validation

## Frontend Implementation

### Components

**AccessTokensCard:** `frontend/src/components/Agents/AccessTokensCard.tsx`
- Lists tokens with mode/scope badges
- Create dialog with mode and scope selection
- Shows token once on creation with copy button
- Revoke/restore toggle
- Delete with confirmation dialog

**AgentIntegrationsTab:** `frontend/src/components/Agents/AgentIntegrationsTab.tsx`
- Shows AccessTokensCard when A2A is enabled
- Token management only available when A2A integration is active

### State Management

- `useQuery` for token list (`["access-tokens", agentId]`)
- `useMutation` for create, update, delete operations
- Local state for create dialog form

## Security Features

**Token Validation:**
- JWT signature verification
- Token type check (`token_type='agent'`)
- Database existence check
- Revoked status check
- Hash verification (prevents token forgery)
- Expiration check

**Access Control:**
- Token can only access its associated agent
- Mode enforced on message operations
- Scope enforced on session access
- Owner verification for token CRUD (must own the agent)

**Token Storage:**
- SHA256 hash only (not reversible)
- Prefix for user identification
- Soft revoke option (keeps for audit trail)

## Key Integration Points

### Token Creation Flow

`backend/app/api/routes/access_tokens.py:create_access_token()`
1. Verify user owns agent
2. Create DB record with placeholder hash
3. Generate JWT with token ID
4. Update record with hash and prefix
5. Return token (shown only once)

### A2A Authentication Flow

`backend/app/api/routes/a2a.py:get_a2a_auth_context()`
1. Extract token from Authorization header
2. Try to decode as A2A token (check `token_type='agent'`)
3. If A2A token, validate against database
4. If not A2A, try standard user auth
5. Return appropriate `A2AAuthContext`

### Scope Enforcement

`backend/app/services/a2a_request_handler.py:_get_or_create_session()`
1. If accessing existing session with A2A token:
   - Get session from database
   - Call `AccessTokenService.can_access_session()`
   - Deny if limited scope and session.access_token_id doesn't match
2. If creating new session:
   - Pass `access_token_id` to `SessionService.create_session()`
   - Session is linked to this token

## File Locations Reference

### Backend - API Layer
- `backend/app/api/routes/access_tokens.py` - Token CRUD endpoints
- `backend/app/api/routes/a2a.py` - Updated with dual auth support
- `backend/app/api/main.py` - Router registration

### Backend - Services
- `backend/app/services/access_token_service.py` - Token operations and validation
- `backend/app/services/a2a_request_handler.py` - Updated with scope enforcement
- `backend/app/services/session_service.py` - Updated with access_token_id param

### Backend - Models
- `backend/app/models/agent_access_token.py` - Token model and schemas
- `backend/app/models/session.py` - Added access_token_id field
- `backend/app/models/__init__.py` - Exports

### Backend - Migrations
- `backend/app/alembic/versions/f6a7b8c9d0e1_add_agent_access_tokens.py`

### Frontend
- `frontend/src/components/Agents/AccessTokensCard.tsx` - Token management UI
- `frontend/src/components/Agents/AgentIntegrationsTab.tsx` - Updated with AccessTokensCard

---

**Document Version:** 1.0
**Last Updated:** 2026-01-16
**Status:** Implementation Complete
