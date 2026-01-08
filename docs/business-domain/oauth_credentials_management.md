# OAuth Credentials Management for Google Services

## Implementation Status

**Last Updated**: 2026-01-05

| Step | Status | Description |
|------|--------|-------------|
| **Step 1** | ✅ **COMPLETED** | Data structures, API routes scaffolding, UI components |
| **Step 2** | ⏳ **PENDING** | OAuth flow implementation, token exchange, storage |
| **Step 3** | ⏳ **PENDING** | Token refresh & background jobs |

### What's Working Now (Step 1 Completed)

✅ **Backend**:
- 6 OAuth credential types defined in `CredentialType` enum
- Stub API endpoints for OAuth flow (`/oauth/authorize`, `/oauth/callback`, `/oauth/metadata`, `/oauth/refresh`)
- Routes registered and OpenAPI spec generated

✅ **Frontend**:
- Unified OAuth UI component (`OAuthCredentialFields`) for all OAuth types
- All 6 OAuth credential types available in dropdowns
- Placeholder "Grant from Google" button (disabled, ready for Step 2)
- Mock OAuth metadata display
- Type-safe client with OAuth endpoints

✅ **User Experience**:
- Users can create OAuth credential records (name, type, notes)
- Credential detail pages show OAuth-specific UI (not manual token fields)
- Consistent labeling across all UI components

### Implementation Notes

**Design Changes from Original Plan**:
- ✅ **Unified OAuth UI**: Instead of creating a separate component per OAuth type, implemented a single reusable `OAuthCredentialFields` component that handles all 6 OAuth types
- ✅ **Included `gmail_oauth`**: The existing `gmail_oauth` type now uses the same unified OAuth UI (replaced old `GmailOAuthFields` with manual token inputs)
- ✅ **Component naming**: Created `OAuthCredentialFields.tsx` instead of `OAuthCredentialForm.tsx` to match the project's naming convention for credential field components

### Next Steps

⏳ **Step 2 Required**:
- Implement `OAuthCredentialsService` for actual Google OAuth integration
- Enable "Grant from Google" button functionality
- Token exchange and storage
- Display real OAuth metadata

## Overview

Users need a simple way to grant their Google service credentials (Gmail, Google Drive, Google Calendar) to their agents through OAuth flow. Instead of manually copying access tokens, users click "Grant from Google" and complete the OAuth authorization, which automatically stores the credentials for agent use.

**Key Points**:
- **Builds on existing infrastructure**: Leverages existing credential storage, encryption, and agent environment sync
- **Unified OAuth experience**: All 6 OAuth types (including existing `gmail_oauth`) use the same UI and flow
- **Automatic sync**: Uses existing `CredentialsService` event handlers to sync tokens to running agent environments
- **No agent changes needed**: Credentials appear in standard `workspace/credentials/credentials.json` file

## Business Requirements

### Supported Google OAuth Credential Types

1. **Gmail OAuth** (`gmail_oauth`) - Full access to Gmail
   - Scopes: `https://www.googleapis.com/auth/gmail.modify`, `https://www.googleapis.com/auth/gmail.send`
   - Use case: Read emails, send emails, manage labels, delete messages

2. **Gmail OAuth Read-Only** (`gmail_oauth_readonly`)
   - Scopes: `https://www.googleapis.com/auth/gmail.readonly`
   - Use case: Read emails only, safer for monitoring/analysis agents

3. **Google Drive OAuth** (`gdrive_oauth`) - Full access to Google Drive
   - Scopes: `https://www.googleapis.com/auth/drive`
   - Use case: Read, create, modify, delete files and folders

4. **Google Drive OAuth Read-Only** (`gdrive_oauth_readonly`)
   - Scopes: `https://www.googleapis.com/auth/drive.readonly`
   - Use case: Read files only, safer for analysis/reporting agents

5. **Google Calendar OAuth** (`gcalendar_oauth`) - Full access to Google Calendar
   - Scopes: `https://www.googleapis.com/auth/calendar`
   - Use case: Read, create, modify, delete calendar events

6. **Google Calendar OAuth Read-Only** (`gcalendar_oauth_readonly`)
   - Scopes: `https://www.googleapis.com/auth/calendar.readonly`
   - Use case: Read calendar events only, safer for monitoring agents

### User Experience Flow

1. **Credential Creation**:
   - User navigates to create new credential
   - Selects credential type (e.g., `gmail_oauth`)
   - Form shows:
     - **Name** field (e.g., "My Gmail Account")
     - **Notes** field (optional)
     - **"Grant from Google"** button (no manual token fields)
   - User clicks "Grant from Google"
   - OAuth flow initiates → Google authorization screen
   - User grants permissions
   - Callback handler receives tokens and saves credential
   - User redirected back to credential details page

2. **Credential Update**:
   - User views existing OAuth credential
   - Shows metadata: email, granted scopes, expiration time
   - "Re-authorize with Google" button to refresh permissions
   - Standard edit fields for name/notes

3. **Automatic Token Refresh**:
   - System monitors token expiration times
   - Cron job runs periodically (e.g., every hour)
   - Refreshes tokens for credentials expiring within 24 hours
   - Updates credential with new access token and expiration
   - Syncs updated credentials to running agent environments
   - Logs refresh failures for user notification

### Credential Data Structure

OAuth credentials store the following data in `encrypted_data`:

```json
{
  "access_token": "ya29.a0AfH6...",
  "refresh_token": "1//0gXXX...",
  "token_type": "Bearer",
  "expires_at": 1735689600,
  "scope": "https://www.googleapis.com/auth/gmail.modify https://www.googleapis.com/auth/gmail.send",
  "granted_user_email": "user@gmail.com",
  "granted_user_name": "John Doe",
  "granted_at": 1735603200
}
```

**Field Descriptions**:
- `access_token`: Short-lived token for API calls (expires in ~1 hour)
- `refresh_token`: Long-lived token to obtain new access tokens (persists until revoked)
- `token_type`: Always "Bearer" for Google OAuth
- `expires_at`: Unix timestamp when access token expires
- `scope`: Space-separated list of granted OAuth scopes
- `granted_user_email`: Google account email (for user reference)
- `granted_user_name`: Google account display name (for user reference)
- `granted_at`: Unix timestamp when credential was initially granted

## Security & Authorization

### State Management
- CSRF protection via state tokens (same as user OAuth login)
- State tokens stored in-memory with 10-minute expiration
- State tokens include credential type and user ID context

### Authorization Rules
- Only credential owner can initiate OAuth flow for their credentials
- Only credential owner can view OAuth metadata (email, scopes)
- OAuth callback validates state token ownership before saving

### Token Storage
- All tokens encrypted at rest using existing `encrypt_field()` mechanism
- Refresh tokens never exposed in API responses (only decrypted for token refresh)
- Access tokens only sent to agent environments, never to frontend

## Technical Implementation Plan

### Overview

This implementation is split into **3 major steps**, each with clear sub-steps:

1. **Step 1: Data Structures & UI Scaffolding** - Set up models, stub API routes, and basic UI (no business logic)
2. **Step 2: OAuth Flow Implementation** - Implement actual OAuth redirects, token exchange, storage, and UI verification
3. **Step 3: Token Refresh & Background Jobs** - Add automatic token refresh and cron jobs

### File Organization

Following the project's separation of concerns pattern:

**Models**: Each entity in its own file
- `backend/app/models.py` or `backend/app/models/credential.py` - Credential model (existing, to be updated)

**Services**: Business logic separated by domain
- `backend/app/services/oauth_credentials_service.py` - OAuth flow handling (new)
- `backend/app/services/credentials_service.py` - Credential management (existing, already has encryption, sync, README generation)

**Routes**: API endpoints by domain
- `backend/app/api/routes/oauth_credentials.py` - OAuth endpoints (new)
- `backend/app/api/routes/credentials.py` - Credential CRUD (existing, already handles create/update/delete with auto-sync)

**Tasks**: Background jobs
- `backend/app/tasks/refresh_oauth_tokens.py` - Token refresh cron (new)

### Existing Infrastructure

The following components **already exist** and handle OAuth credentials:

**Encryption & Storage**:
- `encrypt_field()` / `decrypt_field()` in `backend/app/core/security.py`
- Credentials stored in `Credential.encrypted_data` JSON field

**Credential Type**:
- `gmail_oauth` already exists in `CredentialType` enum
- Stores: `access_token`, `refresh_token`, `token_type`, `expires_at`, `scope`

**Automatic Synchronization** (via `CredentialsService`):
- `prepare_credentials_for_environment()` - Prepares JSON + README for agent environments
- `sync_credentials_to_agent_environments()` - Auto-syncs to all running environments
- Event handlers: `event_credential_updated()`, `event_credential_deleted()`, `event_credential_shared()`, `event_credential_unshared()`
- Syncs to: `workspace/credentials/credentials.json` and `workspace/credentials/README.md`

**README Generation**:
- `generate_credentials_readme()` - Creates redacted docs with ID-based lookup examples
- `redact_credential_data()` - Redacts sensitive fields for agent prompt context

**What We're Adding**:
- New OAuth credential types (Google Drive, Calendar, read-only variants)
- OAuth authorization flow (redirect to Google, callback handling)
- Automatic token refresh (cron job)
- OAuth-specific UI components

### How It Integrates

**OAuth Flow** (new) → **Credential Storage** (existing) → **Agent Environment Sync** (existing)

1. **User initiates OAuth flow** → New `OAuthCredentialsService` generates authorization URL
2. **Google redirects back** → New callback handler exchanges code for tokens
3. **Tokens stored in credential** → Uses existing `encrypt_field()` and `Credential.encrypted_data`
4. **Credential updated** → Existing `event_credential_updated()` triggers
5. **Synced to agent environments** → Existing `sync_credentials_to_agent_environments()` runs
6. **Available to agents** → Existing `workspace/credentials/credentials.json` and `README.md`

**Token Refresh** (new) → **Credential Update** (existing) → **Auto-Sync** (existing)

1. **Cron job runs** → New `refresh_expiring_oauth_tokens()` checks for expiring tokens
2. **Refresh token used** → New `refresh_oauth_token()` gets new access token
3. **Credential updated** → Uses existing credential update mechanism
4. **Auto-synced** → Existing event handlers sync to all running environments
5. **Agent gets fresh token** → No action needed by agent scripts

---

## Step 1: Data Structures & UI Scaffolding

**Status**: ✅ **COMPLETED** (2026-01-05)

**Goal**: Set up database models, API routes (without business logic), and basic UI for managing OAuth credentials.

### Step 1.1: Update Credential Model ✅

**File**: `backend/app/models/credential.py:11-20`

**Completed Changes**:
- ✅ Added 5 new credential types to `CredentialType` enum:
  - `GMAIL_OAUTH_READONLY = "gmail_oauth_readonly"` - Gmail read-only access
  - `GDRIVE_OAUTH = "gdrive_oauth"` - Google Drive full access
  - `GDRIVE_OAUTH_READONLY = "gdrive_oauth_readonly"` - Google Drive read-only access
  - `GCALENDAR_OAUTH = "gcalendar_oauth"` - Google Calendar full access
  - `GCALENDAR_OAUTH_READONLY = "gcalendar_oauth_readonly"` - Google Calendar read-only access
- ✅ Kept existing `gmail_oauth` type unchanged
- ✅ **Implementation Note**: Updated `gmail_oauth` to use the same unified OAuth UI as the new types (uses `OAuthCredentialFields` component)

**Notes**:
- No database migration needed - credential types are enum values, data stored in existing `encrypted_data` JSON field
- The `Credential` model already has all necessary fields (`encrypted_data`, encryption methods, relationships)
- All OAuth types (including `gmail_oauth`) now use the same data structure and UI

### Step 1.2: Create OAuth Routes Skeleton ✅

**Created File**: `backend/app/api/routes/oauth_credentials.py`

**Completed Endpoints** (stub implementations with placeholders):

- ✅ `POST /api/v1/credentials/{credential_id}/oauth/authorize`
  - Request: None (credential ID in path)
  - Response: `OAuthAuthorizeResponse` with `{"authorization_url": str, "state": str}`
  - Authorization: Only credential owner (verified with `CurrentUser` dependency)
  - Stub: Returns placeholder Google OAuth URL and state token
  - TODO (Step 2): Implement actual OAuth flow with `OAuthCredentialsService`

- ✅ `POST /api/v1/credentials/oauth/callback`
  - Request: `OAuthCallbackRequest` with `{"code": str, "state": str}`
  - Response: `OAuthCallbackResponse` with `{"credential_id": UUID, "message": str}`
  - Authorization: Public endpoint (state token validates request)
  - Stub: Returns success message
  - TODO (Step 2): Implement token exchange with `OAuthCredentialsService`

- ✅ `GET /api/v1/credentials/{credential_id}/oauth/metadata`
  - Response: `OAuthMetadataResponse` with user email, name, scopes, expiration, granted time
  - Authorization: Only credential owner
  - Stub: Returns mock metadata
  - TODO (Step 2): Extract actual metadata from credential's `encrypted_data`

- ✅ `POST /api/v1/credentials/{credential_id}/oauth/refresh`
  - Response: `OAuthRefreshResponse` with `{"message": str, "expires_at": int}`
  - Authorization: Only credential owner
  - Stub: Returns success message
  - TODO (Step 3): Implement actual token refresh with `OAuthCredentialsService`

**Router Registration** ✅: Added to `backend/app/api/main.py:15,34`:
```python
from app.api.routes import oauth_credentials
api_router.include_router(oauth_credentials.router, prefix="/credentials", tags=["credentials"])
```

### Step 1.3: Regenerate Frontend Client ✅

**Completed**: Frontend OpenAPI client regenerated successfully

```bash
cd /path/to/workflow-runner-core
source backend/.venv/bin/activate
bash scripts/generate-client.sh
```

**Generated Client Files**:
- ✅ `frontend/src/client/types.gen.ts` - Updated with new credential types
- ✅ `frontend/src/client/sdk.gen.ts` - New OAuth endpoints added to `CredentialsService`:
  - `oauthAuthorize()`
  - `oauthCallback()`
  - `getOauthMetadata()`
  - `refreshOauthToken()`

**Type Verification**:
- ✅ `CredentialType` now includes all 6 OAuth types: `'gmail_oauth' | 'gmail_oauth_readonly' | 'gdrive_oauth' | 'gdrive_oauth_readonly' | 'gcalendar_oauth' | 'gcalendar_oauth_readonly'`

### Step 1.4: Create Frontend UI Components ✅

**Created Component**: `frontend/src/components/Credentials/CredentialFields/OAuthCredentialFields.tsx`
- ✅ Generic OAuth credential form supporting all 6 OAuth types
- ✅ Form fields: name, notes (inherited from parent form)
- ✅ "Grant from Google" button (disabled/placeholder with "Coming in Step 2" message)
- ✅ Display card showing OAuth authorization status
- ✅ Mock OAuth metadata display area (email, name, status, scopes)
- ✅ Maps credential type to friendly display names (e.g., "Google Drive OAuth")

**Updated Components**:
- ✅ `frontend/src/components/Credentials/AddCredential.tsx:44-54,157-167`
  - Added all 6 OAuth credential types to dropdown
  - Updated form schema to accept new types
  - Clear labels: "Gmail OAuth", "Gmail OAuth (Read-Only)", etc.

- ✅ `frontend/src/components/Credentials/EditCredential.tsx:34-38,152-162`
  - Imported `OAuthCredentialFields` component
  - Added conditional rendering for all 6 OAuth types (including `gmail_oauth`)
  - **Unified UI**: All OAuth types now use the same `OAuthCredentialFields` component (replaced old `GmailOAuthFields`)

- ✅ `frontend/src/routes/_layout/credential/$credentialId.tsx:35-39,50-73,222-232`
  - Credential detail page updated with OAuth-specific UI
  - Updated `getCredentialTypeLabel()` with all 6 OAuth types
  - Shows `OAuthCredentialFields` for all OAuth credentials

**Display Label Updates** (all files):
- ✅ `frontend/src/components/Credentials/columns.tsx:35-45` - Table columns
- ✅ `frontend/src/components/Credentials/CredentialCard.tsx:18-61` - Card view + icons
- ✅ `frontend/src/components/Agents/AgentCredentialsTab.tsx:49-72` - Agent credentials tab

**Removed/Deprecated**:
- ✅ `GmailOAuthFields` removed from exports (no longer used)
- ✅ Old manual token input fields replaced with OAuth UI for `gmail_oauth`

**Deliverables Achieved**:
- ✅ Users can create OAuth credential records (without actual tokens)
- ✅ UI displays placeholder OAuth metadata and authorization status
- ✅ Consistent OAuth experience across all 6 credential types
- ✅ "Grant from Google" button visible but disabled (ready for Step 2 implementation)

---

## Step 2: OAuth Flow Implementation

**Status**: ⏳ **PENDING**

**Goal**: Implement actual OAuth redirect flow, token exchange, storage, and UI verification.

**Prerequisites**: Step 1 completed ✅

### Step 2.1: Create OAuth Service

**New File**: `backend/app/services/oauth_credentials_service.py`

**Integration Notes**:
- Reuse existing Google OAuth configuration from `backend/app/core/config.py` (same `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`)
- Can use similar OAuth flow patterns from `backend/app/api/routes/oauth.py` (user authentication OAuth)
- State token management can follow the same pattern as user OAuth login

**Scope Mapping**:
```python
OAUTH_SCOPES = {
    "gmail_oauth": [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ],
    "gmail_oauth_readonly": [
        "https://www.googleapis.com/auth/gmail.readonly",
    ],
    "gdrive_oauth": [
        "https://www.googleapis.com/auth/drive",
    ],
    "gdrive_oauth_readonly": [
        "https://www.googleapis.com/auth/drive.readonly",
    ],
    "gcalendar_oauth": [
        "https://www.googleapis.com/auth/calendar",
    ],
    "gcalendar_oauth_readonly": [
        "https://www.googleapis.com/auth/calendar.readonly",
    ],
}
```

**Methods**:

- `get_oauth_scopes_for_type(credential_type: str) -> list[str]`
  - Maps credential type to required Google OAuth scopes
  - Returns: List of scope URLs for that credential type

- `initiate_oauth_flow(session: Session, credential_id: UUID, user_id: UUID) -> dict`
  - Generates state token with credential context
  - Builds Google authorization URL with appropriate scopes
  - Returns: `{"authorization_url": str, "state": str}`
  - Validates credential ownership before proceeding

- `handle_oauth_callback(session: Session, code: str, state: str) -> Credential`
  - Validates state token and extracts credential context
  - Exchanges authorization code for access + refresh tokens
  - Verifies Google ID token to get user email/name
  - Saves tokens + metadata to credential's `encrypted_data`:
    ```json
    {
      "access_token": "ya29.a0AfH6...",
      "refresh_token": "1//0gXXX...",
      "token_type": "Bearer",
      "expires_at": 1735689600,
      "scope": "https://www.googleapis.com/auth/gmail.modify",
      "granted_user_email": "user@gmail.com",
      "granted_user_name": "John Doe",
      "granted_at": 1735603200
    }
    ```
  - Uses existing `encrypt_field()` to encrypt the data
  - Returns: Updated Credential object
  - **Note**: Credential sync to agent environments is automatically handled by existing `CredentialsService.event_credential_updated()` when credential is saved

- `get_oauth_metadata(session: Session, credential: Credential) -> dict`
  - Extracts non-sensitive metadata for display
  - Returns: `{"user_email": str, "user_name": str, "scopes": list, "expires_at": int, "granted_at": int}`
  - Does not return tokens (security)

### Step 2.2: Implement OAuth Routes

**File**: `backend/app/api/routes/oauth_credentials.py`

**Replace stub implementations** with actual service calls:
- `POST /credentials/{credential_id}/oauth/authorize` → calls `initiate_oauth_flow()`
- `POST /credentials/oauth/callback` → calls `handle_oauth_callback()`
- `GET /credentials/{credential_id}/oauth/metadata` → calls `get_oauth_metadata()`

### Step 2.3: Update Credentials Service

**File**: `backend/app/services/credentials_service.py`

**Changes**:

**Update existing `SENSITIVE_FIELDS` dict** to include new OAuth types:
```python
SENSITIVE_FIELDS = {
    "email_imap": ["password"],
    "odoo": ["api_token"],
    "gmail_oauth": ["access_token", "refresh_token"],  # Already exists
    "gmail_oauth_readonly": ["access_token", "refresh_token"],  # New
    "gdrive_oauth": ["access_token", "refresh_token"],  # New
    "gdrive_oauth_readonly": ["access_token", "refresh_token"],  # New
    "gcalendar_oauth": ["access_token", "refresh_token"],  # New
    "gcalendar_oauth_readonly": ["access_token", "refresh_token"],  # New
    "api_token": ["http_header_value"],
}
```

**Update existing `generate_credentials_readme()` method** to add usage examples for new OAuth types:
- Add **Google Drive API** usage example (similar to existing Gmail example)
  - Show how to list files, upload files, download files
  - Include ID-based credential lookup
- Add **Google Calendar API** usage example
  - Show how to list events, create events
  - Include ID-based credential lookup
- Show how OAuth tokens are automatically refreshed (agent doesn't need to worry about refresh logic)

**Note**:
- The existing `redact_credential_data()` method already handles redacting these sensitive fields for the README
- The existing event handlers (`event_credential_updated()`, etc.) will automatically sync these new credential types to agent environments
- No changes needed to sync mechanism - it already works for all credential types

### Step 2.4: Regenerate Frontend Client

```bash
cd /path/to/workflow-runner-core
source backend/.venv/bin/activate
bash scripts/generate-client.sh
```

### Step 2.5: Implement Frontend OAuth Flow

**Update Component**: `frontend/src/components/Credentials/CredentialFields/OAuthCredentialFields.tsx`
- Implement "Grant from Google" button onClick:
  1. Call `CredentialsService.oauthAuthorize(credential_id)`
  2. Open `authorization_url` in popup or redirect
  3. Handle callback redirect
  4. Refresh credential data
  5. Show success/error message
- Display real OAuth metadata (email, scopes, expiration)

**Update Route**: `frontend/src/routes/_layout/credentials.tsx`
- Implement "Re-authorize" button for expired/expiring credentials
- Show token status indicators (active, expiring soon, expired)
- Add expiration countdown/warnings

### Step 2.6: Environment Variables

**File**: `.env`

**Required Variables** (already configured for user OAuth):
- `GOOGLE_CLIENT_ID`: OAuth client ID from Google Cloud Console (already exists)
- `GOOGLE_CLIENT_SECRET`: OAuth client secret (already exists)

**Google Cloud Console Configuration**:
- Add new **Authorized redirect URI** for credential OAuth flow:
  - Development: `http://localhost:5173/credentials/oauth/callback`
  - Production: `https://yourdomain.com/credentials/oauth/callback`
- Keep existing redirect URI for user authentication: `http://localhost:5173/auth/google/callback`

**Note**:
- Same Google OAuth app is used for both user authentication and credential generation
- The service will request different scopes depending on the credential type
- No new environment variables needed - reuses existing configuration

**Deliverable**: Users can complete OAuth flow, tokens are stored, UI shows real token status and metadata.

---

## Step 3: Token Refresh & Background Jobs

**Status**: ⏳ **PENDING**

**Goal**: Implement automatic token refresh to keep credentials active.

**Prerequisites**: Step 2 completed ⏳

### Step 3.1: Add Token Refresh to OAuth Service

**File**: `backend/app/services/oauth_credentials_service.py`

**New Method**:

- `refresh_oauth_token(session: Session, credential: Credential) -> Credential`
  - Uses refresh token to obtain new access token from Google
  - Updates credential's `encrypted_data` with new access token and expiration
  - Uses existing `encrypt_field()` to re-encrypt the updated data
  - Returns: Updated Credential object
  - Handles refresh failures (logs error, optionally marks credential as invalid)
  - **Note**: Credential sync to agent environments is automatically handled by existing `CredentialsService.event_credential_updated()` when credential is saved

### Step 3.2: Implement Manual Refresh Endpoint

**File**: `backend/app/api/routes/oauth_credentials.py`

**Implement Route**:
- `POST /credentials/{credential_id}/oauth/refresh` → calls `refresh_oauth_token()`

### Step 3.3: Create Token Refresh Cron Job

**New File**: `backend/app/tasks/refresh_oauth_tokens.py`

**Purpose**: Background task to refresh expiring OAuth tokens.

**Methods**:

- `refresh_expiring_oauth_tokens(session: Session)`
  - Queries all OAuth credentials expiring within 24 hours
  - Iterates through credentials and calls `OAuthCredentialsService.refresh_oauth_token()`
  - Logs successful refreshes and failures
  - Sends notifications for failed refreshes (future enhancement)

**Cron Setup**:
- Use `FastAPI Background Tasks` for development
- Use `APScheduler` or external cron for production
- Run every hour or as configured

### Step 3.4: Integrate Cron Job

**File**: `backend/app/main.py`

**Changes**:
- Add startup event to schedule cron job
- Example with APScheduler:
  ```python
  from apscheduler.schedulers.asyncio import AsyncIOScheduler
  from app.tasks.refresh_oauth_tokens import refresh_expiring_oauth_tokens

  scheduler = AsyncIOScheduler()
  scheduler.add_job(refresh_expiring_oauth_tokens, 'interval', hours=1)
  scheduler.start()
  ```

### Step 3.5: Regenerate Frontend Client & Add Manual Refresh UI

```bash
cd /path/to/workflow-runner-core
source backend/.venv/bin/activate
bash scripts/generate-client.sh
```

**Update Component**: `frontend/src/components/Credentials/OAuthCredentialForm.tsx`
- Add "Refresh Token" button (calls manual refresh endpoint)
- Show last refresh timestamp
- Show auto-refresh status

**Deliverable**: Tokens automatically refresh before expiration, users can manually trigger refresh, UI shows refresh status.

---

## Additional Implementation Details

### Scope Mapping Reference

The complete scope mapping is defined in `backend/app/services/oauth_credentials_service.py` (see Step 2.1 for full code).

## Testing Checklist

### OAuth Flow
- [ ] OAuth flow creates credential with correct tokens
- [ ] State token validation prevents CSRF attacks
- [ ] Tokens are properly encrypted in `Credential.encrypted_data`
- [ ] Multiple OAuth credentials can be created per user
- [ ] OAuth metadata displays correctly in UI

### Token Refresh
- [ ] Token refresh updates access token and expiration
- [ ] Expired credentials are detected and refreshed by cron
- [ ] Refresh failures are logged appropriately
- [ ] Revoked tokens are handled gracefully

### Agent Environment Integration
- [ ] New credentials automatically sync to running agent environments (via existing `sync_credentials_to_agent_environments()`)
- [ ] Updated credentials automatically sync to running environments
- [ ] Credentials appear in `workspace/credentials/credentials.json` with full tokens
- [ ] Credentials appear in `workspace/credentials/README.md` with redacted sensitive fields
- [ ] README generation includes correct usage examples for all new OAuth types (Drive, Calendar)
- [ ] Credentials work correctly in agent scripts (Gmail, Drive, Calendar APIs)
- [ ] Agent can read credentials by ID (recommended) and by type
- [ ] Token refresh doesn't interrupt running agents (seamless update)

## Security Considerations

1. **Token Storage**: All tokens encrypted at rest using existing `encrypt_field()` from `backend/app/core/security.py`
2. **State Validation**: CSRF protection via state tokens (same pattern as user OAuth login)
3. **Ownership Check**: Only credential owner can initiate OAuth (enforced by `CurrentUser` dependency)
4. **Scope Validation**: Scopes matched to credential type (enforced by `OAuthCredentialsService`)
5. **Token Exposure**:
   - Refresh tokens never sent to frontend
   - Access tokens only available in agent environments (via `credentials.json`)
   - Sensitive fields redacted in README (via existing `redact_credential_data()`)
6. **Refresh Failures**: Log and notify users of refresh failures
7. **Revocation Handling**: Gracefully handle revoked credentials (mark as invalid, log error)
8. **Agent Environment Isolation**: Credentials scoped to workspace, only accessible by linked agents

## Future Enhancements

- Support for other OAuth providers (Microsoft, Dropbox, etc.)
- Automatic credential revocation detection
- User notifications for expiring/failed credentials
- OAuth scope upgrade flow (add more permissions)
- Refresh token rotation for enhanced security
- Rate limiting on OAuth endpoints