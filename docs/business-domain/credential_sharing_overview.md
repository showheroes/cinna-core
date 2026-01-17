# Credential Sharing Feature - Implementation Reference

## Purpose

Enables users to share their credentials with other users, allowing recipients to use shared credentials in their agents without exposing the actual credential values (passwords, tokens, etc.).

## Feature Overview

**Flow:**
1. Credential owner enables sharing on a credential (`allow_sharing=true`)
2. Owner shares credential with another user by email
3. Recipient sees credential in "Shared with Me" section
4. Recipient can link shared credential to their agents
5. Owner can revoke share at any time (immediate effect)
6. Owner can disable sharing entirely (revokes all shares)

## Architecture

```
Frontend UI → Backend API → CredentialShare Table → Recipient Access
(React)       (FastAPI)     (DB Association)        (Read-only usage)
```

**Access Model:**
- **Owner:** Full control (view/edit/delete credential, manage shares, see credential values)
- **Recipient:** Read-only access (view metadata, link to own agents, cannot see values, cannot edit/delete)

## Data/State Lifecycle

### Credential Sharing States

| State | Description | Transitions |
|-------|-------------|-------------|
| `allow_sharing=false` | Credential cannot be shared | → Enable sharing |
| `allow_sharing=true` | Credential can be shared | → Share with user, Disable sharing |
| Shared | CredentialShare record exists | → Revoke share |

### Business Rules

- Cannot share credentials with `allow_sharing=false`
- Cannot share with yourself
- Cannot create duplicate shares (same credential + same user)
- Disabling `allow_sharing` immediately revokes ALL existing shares
- Deleting credential cascades to delete all shares

## Database Schema

**Migration:** `backend/app/alembic/versions/g7b8c9d0e1f2_add_credential_sharing.py`

**Modified Table: `credential`**
- Added column: `allow_sharing` (boolean, default false)
- Added index: `ix_credential_allow_sharing` (partial index for shareable credentials)

**New Table: `credential_shares`**
- `id` (UUID, primary key)
- `credential_id` (UUID, FK to credential, CASCADE delete)
- `shared_with_user_id` (UUID, FK to user, CASCADE delete)
- `shared_by_user_id` (UUID, FK to user)
- `shared_at` (datetime)
- `access_level` (varchar, default 'read')
- Unique constraint: `(credential_id, shared_with_user_id)`

**Models:** `backend/app/models/credential_share.py`
- `CredentialShare` (table model)
- `CredentialSharePublic` (response with resolved user emails)
- `CredentialShareCreate` (request with target email)
- `CredentialSharesPublic` (list response)
- `SharedCredentialPublic` (credential shared with current user)
- `SharedCredentialsPublic` (list response)

**Updated:** `backend/app/models/credential.py`
- `CredentialBase` - Added `allow_sharing: bool`
- `CredentialUpdate` - Added `allow_sharing: bool | None`
- `CredentialPublic` - Added `share_count: int`, `is_shared: bool`, `owner_email: str | None`

## Backend Implementation

### API Routes

**Credential Sharing:** `backend/app/api/routes/credential_shares.py`
- `POST /api/v1/credentials/{credential_id}/shares` - Share credential with user by email
- `GET /api/v1/credentials/{credential_id}/shares` - List all shares for a credential
- `DELETE /api/v1/credentials/{credential_id}/shares/{share_id}` - Revoke specific share
- `GET /api/v1/credentials/shared-with-me` - Get credentials shared with current user
- `PATCH /api/v1/credentials/{credential_id}/sharing` - Enable/disable sharing

**Updated:** `backend/app/api/routes/credentials.py`
- `GET /api/v1/credentials/{id}` - Now allows viewing if user owns OR has share (returns `is_shared=true` for shared)
- All endpoints now return `share_count`, `is_shared`, `owner_email` in `CredentialPublic` response
- Uses `_credential_to_public()` helper to compute share count and ownership info

### Services

**CredentialShareService:** `backend/app/services/credential_share_service.py`
- `share_credential()` - Create share with validations (ownership, allow_sharing, target exists, not self, not duplicate)
- `revoke_credential_share()` - Delete share record with ownership check
- `get_shares_by_credential()` - List shares with resolved user emails
- `get_credentials_shared_with_me()` - Query shares where user is recipient
- `get_share_count_for_credential()` - Count shares for a credential
- `update_credential_sharing()` - Toggle allow_sharing, auto-revokes all shares when disabled
- `can_user_access_credential()` - Check if user owns OR has share
- `delete_all_shares_for_credential()` - Bulk delete (for credential deletion)

**Updated:** `backend/app/services/credentials_service.py`
- `get_credential_with_data()` - Added `allow_sharing` to response
- `link_credential_to_agent()` - Updated to allow linking shared credentials (not just owned)

### Configuration

**Router Registration:** `backend/app/api/main.py`
- Added `credential_shares.router` import
- Registered `api_router.include_router(credential_shares.router)`

## Frontend Implementation

### Components

**CredentialSharing:** `frontend/src/components/Credentials/CredentialSharing.tsx`
- Toggle switch to enable/disable sharing
- "Share" button opens dialog with email input form
- List of current shares with revoke buttons
- Confirmation dialog when disabling sharing with active shares

**SharedWithMeCredentials:** `frontend/src/components/Credentials/SharedWithMeCredentials.tsx`
- Displays credentials shared with current user
- Shows owner email and share date
- Blue "Shared" badge to distinguish from owned credentials

**Updated:** `frontend/src/components/Credentials/CredentialCard.tsx`
- Shows "Shareable" badge when `allow_sharing=true` and no shares
- Shows user count badge when credential has active shares
- Tooltip with share status details

### Routes

**Updated:** `frontend/src/routes/_layout/credentials.tsx`
- Split into "My Credentials" and "Shared with Me" sections
- Added `SharedWithMeCredentials` component

**Updated:** `frontend/src/routes/_layout/credential/$credentialId.tsx`
- Detects `is_shared` flag to determine view mode
- `SharedCredentialView` - Read-only view showing metadata only (no credential values)
- `OwnedCredentialView` - Full edit view with credential data and sharing management
- Header shows "Shared" badge and owner email for shared credentials
- Delete button hidden for shared credentials

**Updated:** `frontend/src/components/Agents/AgentCredentialsTab.tsx`
- Fetches both owned credentials and credentials shared with user
- Shows "Shared" indicator in credential selection dropdown
- Displays "Shared" badge in the table for linked shared credentials

### State Management

**Query Keys:**
- `["credentials"]` - User's owned credentials list
- `["credential", credentialId]` - Single credential detail
- `["credential-shares", credentialId]` - Shares for a credential
- `["credentials-shared-with-me"]` - Credentials shared with current user

**Mutations:**
- `shareCredential` - Create new share
- `revokeCredentialShare` - Delete share
- `updateCredentialSharing` - Toggle allow_sharing

## Security Features

**Validation Rules:**
- Owner-only operations: share, revoke, toggle allow_sharing
- Share requires `allow_sharing=true` on credential
- Cannot share with non-existent users
- Cannot share with yourself
- Cannot create duplicate shares

**Access Control:**
- `CredentialShareService.can_user_access_credential()` - Returns true if owner OR has share
- `CredentialsService.link_credential_to_agent()` - Allows linking owned OR shared credentials to agents
- Share recipients get read-only access (can use, cannot see values)
- Credential values (encrypted_data) never exposed to share recipients

**Data Protection:**
- Shared users cannot see/modify actual credential values
- Revoking share immediately removes access
- Disabling sharing is destructive (revokes all shares with warning)

## Key Integration Points

**Share Creation:** `backend/app/services/credential_share_service.py:share_credential()`
1. Validate credential ownership
2. Check `allow_sharing=true`
3. Find target user by email
4. Validate not self-share and not duplicate
5. Create `CredentialShare` record
6. Return populated `CredentialSharePublic`

**Share Revocation:** `backend/app/services/credential_share_service.py:revoke_credential_share()`
1. Find share by ID
2. Verify credential ownership via share.credential_id
3. Delete share record

**Disable Sharing:** `backend/app/services/credential_share_service.py:update_credential_sharing()`
1. Validate credential ownership
2. If disabling and was enabled: delete all shares
3. Update `allow_sharing` field

**Share Count Computation:** `backend/app/api/routes/credentials.py:_credential_to_public()`
1. Get credential model
2. Query `CredentialShareService.get_share_count_for_credential()`
3. Construct `CredentialPublic` with share_count

## File Locations Reference

**Backend:**
- Routes: `backend/app/api/routes/credential_shares.py`, `credentials.py` (updated)
- Services: `backend/app/services/credential_share_service.py` (new), `credentials_service.py` (updated)
- Models: `backend/app/models/credential_share.py` (new), `credential.py` (updated)
- Migration: `backend/app/alembic/versions/g7b8c9d0e1f2_add_credential_sharing.py`
- Router: `backend/app/api/main.py` (updated)
- Exports: `backend/app/models/__init__.py` (updated)

**Frontend:**
- Components: `frontend/src/components/Credentials/CredentialSharing.tsx` (new), `SharedWithMeCredentials.tsx` (new), `CredentialCard.tsx` (updated)
- Routes: `frontend/src/routes/_layout/credentials.tsx` (updated), `credential/$credentialId.tsx` (updated)
- Client: Auto-generated from OpenAPI (`frontend/src/client/*`)

## Future Considerations

This feature is Phase 1 of the Shared Agents implementation. It establishes the credential sharing infrastructure that will be used in subsequent phases:

- **Phase 2-3:** Agent sharing will use credential shares for linked credentials
- **Phase 3:** Placeholder credentials for non-shareable credentials during agent cloning
- **Phase 4+:** Recipients of shared agents will use owner's shared credentials

See: `docs/business-domain/shared_agents_plan/README.md` for full implementation roadmap.

---

**Document Version:** 1.0
**Last Updated:** 2026-01-17
**Status:** Phase 1 Implemented
