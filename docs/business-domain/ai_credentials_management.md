# AI Credentials Management - Implementation Reference

## Purpose

Enable users to manage multiple named AI credentials (API keys) for different SDK providers, with default credential selection that auto-syncs to user profile for backward compatibility.

## Feature Overview

**Current Implementation (Phase 1):**
1. User creates named AI credentials (e.g., "Production Anthropic", "Testing OpenAI")
2. User marks one credential of each type as "default"
3. Default credential values auto-sync to user's profile fields (`ai_credentials_encrypted`)
4. Existing environment creation continues to work via synced profile fields

**Future Phases (Not Yet Implemented):**
- Explicit credential linking to agent environments
- Owner-provided credentials during agent sharing
- Environment SDK settings synchronization during clone creation

## Architecture

```
User creates AI Credential → Encrypted storage in ai_credential table
                          ↓
User sets as default → Auto-sync to user.ai_credentials_encrypted
                          ↓
Environment creation → Reads from user profile (backward compatible)
```

**Key Concepts:**
- **Named AI Credentials**: Reusable credentials with names, stored encrypted
- **Default Credentials**: One credential per type marked as default
- **Auto-Sync**: Default credentials automatically update user profile fields

## Data/State Lifecycle

### AI Credential Types

| Type | SDK ID | Required Fields |
|------|--------|-----------------|
| `anthropic` | `claude-code/anthropic` | `api_key` |
| `minimax` | `claude-code/minimax` | `api_key` |
| `openai_compatible` | `google-adk-wr/openai-compatible` | `api_key`, `base_url`, `model` |

**Reference:** SDK to credential type mapping in `backend/app/services/environment_service.py:24` (`SDK_API_KEY_MAP`)

### Credential States

| Field | Values | Description |
|-------|--------|-------------|
| `is_default` | `true` / `false` | Whether this is the default for its type |
| `encrypted_data` | JSON string | Encrypted `{api_key, base_url?, model?}` |

## Database Schema

**Migration:** `backend/app/alembic/versions/h8c9d0e1f2g3_add_ai_credentials_table.py`

**Table:** `ai_credential`
- `id` (UUID, PK)
- `owner_id` (UUID, FK → user.id, CASCADE)
- `name` (VARCHAR 255)
- `type` (VARCHAR 50) - "anthropic" | "minimax" | "openai_compatible"
- `encrypted_data` (TEXT) - Fernet-encrypted JSON
- `is_default` (BOOLEAN)
- `created_at`, `updated_at` (DATETIME)

**Indexes:**
- `ix_ai_credential_owner_type` - (owner_id, type)
- `ix_ai_credential_owner_default` - (owner_id, is_default)

**Models:** `backend/app/models/ai_credential.py`
- `AICredential` (table model)
- `AICredentialCreate`, `AICredentialUpdate` (input schemas)
- `AICredentialPublic`, `AICredentialsPublic` (response schemas)
- `AICredentialType` (enum)
- `AICredentialData` (internal decrypted data schema)

## Backend Implementation

### API Routes

**File:** `backend/app/api/routes/ai_credentials.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/ai-credentials/` | List user's AI credentials |
| `POST` | `/api/v1/ai-credentials/` | Create new AI credential |
| `GET` | `/api/v1/ai-credentials/{credential_id}` | Get credential details |
| `PATCH` | `/api/v1/ai-credentials/{credential_id}` | Update credential |
| `DELETE` | `/api/v1/ai-credentials/{credential_id}` | Delete credential |
| `POST` | `/api/v1/ai-credentials/{credential_id}/set-default` | Set as default, sync to user profile |

**Router Registration:** `backend/app/api/main.py`

### Service

**File:** `backend/app/services/ai_credentials_service.py`

**Class:** `AICredentialsService` (singleton: `ai_credentials_service`)

**Methods:**
- `list_credentials(session, user_id)` - List all credentials for user
- `get_credential(session, credential_id, user_id)` - Get with ownership check
- `create_credential(session, user_id, data)` - Create and encrypt
- `update_credential(session, credential_id, user_id, data)` - Update encrypted data
- `delete_credential(session, credential_id, user_id)` - Delete, clear profile if default
- `set_default(session, credential_id, user_id)` - Set default, sync to user profile
- `get_default_for_type(session, user_id, cred_type)` - Get default credential
- `_decrypt_credential(credential)` - Decrypt to `AICredentialData`
- `_sync_default_to_user_profile(session, user, credential)` - Auto-sync to user fields
- `_clear_user_profile_for_type(session, user, cred_type)` - Clear on default deletion

### Encryption

**Pattern:** Uses existing Fernet encryption from `backend/app/core/security.py`
- `encrypt_field(value)` - Encrypt string
- `decrypt_field(encrypted_value)` - Decrypt string

Credential data stored as encrypted JSON: `{"api_key": "...", "base_url": "...", "model": "..."}`

### Auto-Sync Logic

When `set_default()` is called:
1. Unset previous default for same type
2. Set new credential as default
3. Decrypt credential data
4. Update user's `ai_credentials_encrypted` via `crud.update_user_ai_credentials()`

**Mapping:**
- `anthropic` → `anthropic_api_key`
- `minimax` → `minimax_api_key`
- `openai_compatible` → `openai_compatible_api_key`, `openai_compatible_base_url`, `openai_compatible_model`

## Frontend Implementation

### Components

**AICredentials Settings:** `frontend/src/components/UserSettings/AICredentials.tsx`
- Credentials list card with compact line items
- Each row: name, default star icon, type label, edit/delete buttons
- Add button opens dialog
- Set default via star icon button
- SDK Preferences card (unchanged from before)

**Add/Edit Dialog:** `frontend/src/components/UserSettings/AICredentialDialog.tsx`
- Name input
- Type selector (disabled when editing)
- API Key input (password field)
- OpenAI Compatible: Base URL and Model inputs
- "Set as default" checkbox

### API Client

**Service:** `frontend/src/client/sdk.gen.ts` - `AiCredentialsService`
- `listAiCredentials()` - GET list
- `createAiCredential(data)` - POST create
- `getAiCredential(data)` - GET single
- `updateAiCredential(data)` - PATCH update
- `deleteAiCredential(data)` - DELETE
- `setAiCredentialDefault(data)` - POST set default

**Types:** `frontend/src/client/types.gen.ts`
- `AICredentialPublic`, `AICredentialCreate`, `AICredentialUpdate`
- `AICredentialsPublic`
- `AICredentialType`

### State Management

**Query Keys:**
- `["aiCredentialsList"]` - List of named credentials
- `["aiCredentialsStatus"]` - User's credential status (has_* flags)

**Mutations:**
- Create/Update/Delete invalidate both query keys
- Set default also invalidates `["aiCredentialsStatus"]`

## Security Features

**Encryption:**
- All API keys encrypted at rest using Fernet (PBKDF2-HMAC-SHA256)
- Decryption only when needed (set default sync, credential usage)
- Never expose raw keys in API responses (`has_api_key: true` instead)

**Access Control:**
- All routes require authentication (`CurrentUser` dependency)
- Ownership validation on all operations
- CASCADE delete when user deleted

**Validation:**
- API key required for all types
- Base URL and Model required for `openai_compatible` type
- Name required, max 255 characters

## Backward Compatibility

**User Profile Auto-Sync:**
- When credential set as default → values copied to `user.ai_credentials_encrypted`
- Existing code reading from user profile continues to work
- Environment creation unchanged

**Existing UI:**
- Old flat credential inputs removed from UI
- All credential management now via named credentials
- SDK Preferences card unchanged

## File Locations Reference

### Backend

**Models:**
- `backend/app/models/ai_credential.py` - AICredential model and schemas
- `backend/app/models/__init__.py` - Exports added

**Routes:**
- `backend/app/api/routes/ai_credentials.py` - CRUD endpoints
- `backend/app/api/main.py` - Router registration

**Services:**
- `backend/app/services/ai_credentials_service.py` - Core logic

**Migration:**
- `backend/app/alembic/versions/h8c9d0e1f2g3_add_ai_credentials_table.py`

**Encryption:**
- `backend/app/core/security.py` - `encrypt_field()`, `decrypt_field()`

**Related:**
- `backend/app/crud.py` - `update_user_ai_credentials()` for sync
- `backend/app/models/user.py` - `ai_credentials_encrypted` field

### Frontend

**Components:**
- `frontend/src/components/UserSettings/AICredentials.tsx` - Main settings UI
- `frontend/src/components/UserSettings/AICredentialDialog.tsx` - Add/Edit dialog

**Client (auto-generated):**
- `frontend/src/client/sdk.gen.ts` - `AiCredentialsService`
- `frontend/src/client/types.gen.ts` - TypeScript types

## Planned Features (Phase 2)

### Environment Credential Linking

**Purpose:** Allow environments to use specific credentials instead of defaults

**Schema Changes:** `backend/app/models/environment.py`
- `use_default_ai_credentials` (BOOLEAN, default true) - Use user's default credentials
- `conversation_ai_credential_id` (UUID, nullable) - Explicit link for conversation SDK
- `building_ai_credential_id` (UUID, nullable) - Explicit link for building SDK

**Service Updates:** `backend/app/services/environment_service.py`
- `create_environment()` - Resolve defaults from AICredential table or validate linked credentials
- `resolve_ai_credentials_for_environment()` - Get actual credential data for container injection

**Frontend Updates:** `frontend/src/components/Environments/AddEnvironment.tsx`
- Add "Use Default AI Credentials" switch (default: ON)
- When OFF: Show credential dropdowns for conversation/building modes
- Validation: Check defaults exist or explicit credentials selected

### Agent Share Credential Provision

**Purpose:** Owner can attach AI credentials to share so recipient doesn't need their own

**Schema Changes:** `backend/app/models/agent_share.py`
- `provide_ai_credentials` (BOOLEAN, default false) - Owner provides credentials
- `conversation_ai_credential_id` (UUID, nullable) - Owner's credential for conversation SDK
- `building_ai_credential_id` (UUID, nullable) - Owner's credential for building SDK

**New Model:** `backend/app/models/ai_credential_share.py`
- Junction table linking shared credentials to recipients
- Similar pattern to existing `CredentialShare`

**Service Updates:** `backend/app/services/agent_share_service.py`
- `share_agent()` - Accept optional credential provision fields
- Validate credentials exist and belong to owner
- Validate credentials match required SDKs for share mode

**Frontend Updates:** `frontend/src/components/Agents/AgentSharingTab.tsx`
- Add "Provide AI Credentials" switch in share dialog
- When ON: Show credential dropdowns based on agent's active environment SDKs
- Info alert explaining credential sharing implications

### Accept Share Wizard AI Credentials Step

**Purpose:** Handle AI credential selection/display when accepting a share

**New Component:** `frontend/src/components/Agents/AcceptShareWizard/WizardStepAICredentials.tsx`

**If owner provided credentials:**
- Show "Ready to Use" section
- Badge: "Provided by owner"
- No action needed from recipient

**If owner did NOT provide credentials:**
- Show required SDKs based on share mode
- Check if recipient has matching default credentials
- If YES: Show "Using your default: [Name]" with green badge
- If NO: Dropdown to select from existing credentials or link to Settings

**Blocker validation:**
- If any required SDK lacks credentials → disable Continue button
- Show "Cannot create clone without [SDK Type] credentials" error

**Wizard Flow Update:** `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx`
- New step order: Overview → AI Credentials → Integration Credentials → Confirm
- Skip AI Credentials step if owner provided all needed credentials

### Clone Credential Setup

**Service Updates:** `backend/app/services/agent_clone_service.py`

**`create_clone()` changes:**
1. Get original agent's active environment SDK settings
2. Clone environment with same SDK settings
3. If share has `provide_ai_credentials=true`:
   - Create `AICredentialShare` links for recipient
   - Link clone environment to shared credentials
4. If share has `provide_ai_credentials=false`:
   - Use recipient's credentials selected in wizard
   - If recipient has matching defaults, use those

**`push_updates()` changes:**
- Include environment SDK settings in update payload
- If parent's active environment SDK changed, update clone's environment
- Do NOT change credential links (credentials belong to clone owner)

## Implementation Scenarios

### Scenario 1: User creates environment with default credentials

```
1. User selects SDKs for conversation/building
2. use_default_ai_credentials = true (default)
3. Backend resolves user's default credentials for each SDK type
4. Environment created, credentials injected into container
5. If no default exists → error returned
```

### Scenario 2: User creates environment with specific credentials

```
1. User selects SDKs for conversation/building
2. User toggles use_default_ai_credentials = false
3. User selects specific credentials from dropdowns
4. Backend validates credentials match SDK requirements
5. Environment created with explicit credential links
6. Credentials injected into container
```

### Scenario 3: Owner shares agent WITH AI credentials

```
1. Owner creates share, toggles "Provide AI Credentials" ON
2. Owner selects credentials for conversation (and building if builder mode)
3. Share record created with credential IDs
4. Recipient accepts share in wizard
5. Wizard shows "Credentials provided by owner" - no action needed
6. Clone created, owner's credentials linked via AICredentialShare
7. Clone environment uses shared credentials
```

### Scenario 4: Owner shares agent WITHOUT AI credentials

```
1. Owner creates share, leaves "Provide AI Credentials" OFF
2. Share record created without credential IDs
3. Recipient accepts share in wizard
4. Wizard shows AI Credentials step:
   a. If recipient has matching defaults → auto-selected
   b. If recipient lacks credentials → must add or blocked
5. Clone created with recipient's own credentials
6. Clone environment uses recipient's credentials
```

### Scenario 5: Owner pushes update with SDK change

```
1. Owner changes active environment to one with different SDKs
2. Owner pushes update to clones
3. Clone receives SDK setting update
4. Clone's credential links NOT changed (clone owner's responsibility)
5. If SDK change makes clone's credentials incompatible:
   - Clone environment shows warning
   - Clone owner must update credential links manually
```

## Related Documentation

- `docs/business-domain/shared_agents_management.md` - Agent sharing feature
- `docs/agent-sessions/agent_env_docker.md` - Environment architecture
- `docs/security_credentials_whitelist.md` - Credential encryption pattern

---

**Document Version:** 2.0
**Last Updated:** 2026-01-17
**Status:** Phase 1 Implemented (Core CRUD + Auto-Sync), Phase 2 Planned
