# AI Credentials Management - Technical Details

## File Locations

### Backend

**Models:**
- `backend/app/models/ai_credential.py` - `AICredential` (table), `AICredentialCreate`, `AICredentialUpdate`, `AICredentialPublic`, `AICredentialsPublic`, `AICredentialType` (enum), `AICredentialData`, `AffectedEnvironmentPublic`, `SharedUserPublic`, `AffectedEnvironmentsPublic`
- `backend/app/models/ai_credential_share.py` - `AICredentialShare` (table), `AICredentialSharePublic`, `AICredentialShareCreate`
- `backend/app/models/user.py` - `ai_credentials_encrypted` field (sync target)

**Routes:**
- `backend/app/api/routes/ai_credentials.py` - CRUD + set-default + affected-environments endpoints
- `backend/app/api/main.py` - Router registration

**Services:**
- `backend/app/services/ai_credentials_service.py` - `AICredentialsService` (singleton: `ai_credentials_service`)
- `backend/app/services/environment_service.py:27` - `SDK_API_KEY_MAP`, `SDK_TO_CREDENTIAL_TYPE` mappings
- `backend/app/services/agent_share_service.py` - AI credential provision handling in shares
- `backend/app/services/agent_clone_service.py` - Clone AI credential setup
- `backend/app/services/environment_lifecycle.py` - Credential type detection and `.env` generation

**Utilities:**
- `backend/app/utils.py:163` - `detect_anthropic_credential_type()` function
- `backend/app/core/security.py` - `encrypt_field()`, `decrypt_field()` (Fernet encryption)
- `backend/app/services/ai_credentials_service.py` - `_sync_default_to_user_profile()` for profile sync

**Templates:**
- `backend/app/env-templates/python-env-advanced/docker-compose.template.yml` - Container env var pass-through

**Migrations:**
- `backend/app/alembic/versions/h8c9d0e1f2g3_add_ai_credentials_table.py` - Core table
- `backend/app/alembic/versions/i9d0e1f2g3h4_add_ai_credential_shares.py` - Shares table
- `backend/app/alembic/versions/j0e1f2g3h4i5_add_share_ai_credentials.py` - Agent share credential fields
- `backend/app/alembic/versions/k1f2g3h4i5j6_add_env_ai_credentials.py` - Environment credential fields
- `backend/app/alembic/versions/67bd39e7e42c_add_expiry_notification_date_to_ai_.py` - Expiry date field

### Frontend

**Components:**
- `frontend/src/components/UserSettings/AICredentials.tsx` - Main credentials list with expiry badges, set-default, delete actions
- `frontend/src/components/UserSettings/AICredentialDialog.tsx` - Add/edit dialog with type selector, auto-fill expiry
- `frontend/src/components/UserSettings/AnthropicCredentialsModal.tsx` - Instructions modal for Anthropic API Key / OAuth setup
- `frontend/src/components/UserSettings/AffectedEnvironmentsDialog.tsx` - Post-update rebuild dialog
- `frontend/src/components/Environments/AddEnvironment.tsx` - Credential selection UI (default toggle + dropdowns)
- `frontend/src/components/Agents/AgentSharingTab.tsx` - Share dialog AI credentials toggle + selection
- `frontend/src/components/Agents/AcceptShareWizard/WizardStepAICredentials.tsx` - Accept wizard credential step
- `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx` - Wizard flow with AI credentials step
- `frontend/src/components/Common/RelativeTime.tsx` - Extended with badge/color-code support for expiry display

**Client (auto-generated):**
- `frontend/src/client/sdk.gen.ts` - `AiCredentialsService`
- `frontend/src/client/types.gen.ts` - `AICredentialPublic`, `AICredentialCreate`, `AICredentialUpdate`, `AICredentialsPublic`, `AICredentialType`

## Database Schema

### Table: `ai_credential`

- `id` (UUID, PK)
- `owner_id` (UUID, FK → user.id, CASCADE)
- `name` (VARCHAR 255)
- `type` (VARCHAR 50) - "anthropic" | "minimax" | "openai_compatible"
- `encrypted_data` (TEXT) - Fernet-encrypted JSON
- `is_default` (BOOLEAN)
- `expiry_notification_date` (DATETIME, nullable) - Informational expiry reminder
- `created_at`, `updated_at` (DATETIME)

Indexes: `ix_ai_credential_owner_type` (owner_id, type), `ix_ai_credential_owner_default` (owner_id, is_default)

### Table: `ai_credential_shares`

- `id` (UUID, PK)
- `ai_credential_id` (UUID, FK → ai_credential.id, CASCADE)
- `shared_with_user_id` (UUID, FK → user.id, CASCADE)
- `shared_by_user_id` (UUID, FK → user.id)
- `shared_at` (DATETIME)

Indexes: `ix_ai_credential_shares_credential` (ai_credential_id), `ix_ai_credential_shares_recipient` (shared_with_user_id)

### Environment Credential Fields (on `agent_environment`)

- `use_default_ai_credentials` (BOOLEAN, default true)
- `conversation_ai_credential_id` (UUID, nullable)
- `building_ai_credential_id` (UUID, nullable)

### Agent Share Credential Fields (on `agent_share`)

- `provide_ai_credentials` (BOOLEAN, default false)
- `conversation_ai_credential_id` (UUID, nullable)
- `building_ai_credential_id` (UUID, nullable)

## API Endpoints

**File:** `backend/app/api/routes/ai_credentials.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/ai-credentials/` | List user's AI credentials |
| `POST` | `/api/v1/ai-credentials/` | Create new AI credential |
| `GET` | `/api/v1/ai-credentials/{credential_id}` | Get credential details |
| `PATCH` | `/api/v1/ai-credentials/{credential_id}` | Update credential |
| `DELETE` | `/api/v1/ai-credentials/{credential_id}` | Delete credential |
| `POST` | `/api/v1/ai-credentials/{credential_id}/set-default` | Set as default, sync to user profile |
| `GET` | `/api/v1/ai-credentials/{credential_id}/affected-environments` | Get environments using this credential |

## Services & Key Methods

### `AICredentialsService` (`backend/app/services/ai_credentials_service.py`)

**Core CRUD:**
- `list_credentials(session, user_id)` - List all credentials for user
- `get_credential(session, credential_id, user_id)` - Get with ownership check
- `create_credential(session, user_id, data)` - Create, encrypt, auto-detect Anthropic type for expiry
- `update_credential(session, credential_id, user_id, data)` - Update, re-encrypt if key changed
- `delete_credential(session, credential_id, user_id)` - Delete, clear profile if was default

**Default Management:**
- `set_default(session, credential_id, user_id)` - Unset previous default, set new, sync to profile
- `get_default_for_type(session, user_id, cred_type)` - Get default credential for type

**Sharing:**
- `share_credential(session, credential_id, owner_id, recipient_id)` - Create share link
- `can_access_credential(session, credential_id, user_id)` - Check ownership or share access
- `get_credential_for_use(session, credential_id, user_id)` - Return decrypted data if accessible
- `revoke_share(session, credential_id, recipient_id)` - Remove share link
- `list_shared_with_me(session, user_id)` - List credentials shared with user

**Affected Environments:**
- `get_affected_environments()` - Query environments linked to a credential with usage type

**Internal:**
- `_decrypt_credential(credential)` - Decrypt to `AICredentialData`
- `_sync_default_to_user_profile(session, user, credential)` - Auto-sync values to user fields
- `_clear_user_profile_for_type(session, user, cred_type)` - Clear profile on default deletion

### Auto-Sync Mapping

| Credential Type | User Profile Fields |
|----------------|-------------------|
| `anthropic` | `anthropic_api_key` |
| `minimax` | `minimax_api_key` |
| `openai_compatible` | `openai_compatible_api_key`, `openai_compatible_base_url`, `openai_compatible_model` |

### Environment Service (`backend/app/services/environment_service.py`)

- `SDK_API_KEY_MAP` (line 27) - Maps SDK IDs to API key field names
- `SDK_TO_CREDENTIAL_TYPE` (line 34) - Maps SDK IDs to `AICredentialType` values
- `create_environment()` - Resolves default or validates linked credentials per SDK type

### Clone Service (`backend/app/services/agent_clone_service.py`)

- `create_clone()` - If share has `provide_ai_credentials=true`: creates `AICredentialShare` links and links clone environment. If false: uses recipient's selected or default credentials.

## Frontend Components

### `AICredentials.tsx` - Main Settings UI

- Credentials list card with compact rows: name, default star icon, expiry badge, type label, edit/delete buttons
- Set default via star icon
- Add button opens `AICredentialDialog`
- SDK Preferences card (unchanged)

### `AICredentialDialog.tsx` - Add/Edit Dialog

- Name input, type selector (disabled when editing), API key (password field)
- OpenAI Compatible: additional base_url and model inputs
- "Set as default" checkbox
- Expiry notification date field with auto-fill for Anthropic OAuth tokens
- Anthropic info banner with "Instructions" button opening `AnthropicCredentialsModal`

### `AcceptShareWizard/WizardStepAICredentials.tsx`

- If owner provided: green "AI Credentials Provided" section with owner badge
- If not provided: shows required SDKs, checks defaults, dropdown selection, or error with Settings link
- Wizard step type: `"overview" | "ai_credentials" | "credentials" | "confirm"`
- State: `aiCredentialSelections` with `conversationCredentialId`, `buildingCredentialId`

## State Management

**Query Keys:**
- `["aiCredentialsList"]` - List of named credentials
- `["aiCredentialsStatus"]` - User's credential status (has_* flags)

**Mutations:**
- Create/Update/Delete invalidate both query keys
- Set default also invalidates `["aiCredentialsStatus"]`

## Encryption

- Fernet encryption (PBKDF2-HMAC-SHA256) via `backend/app/core/security.py`
- Credential data stored as encrypted JSON: `{"api_key": "...", "base_url": "...", "model": "..."}`
- Decryption only when needed: set-default sync, environment generation, credential use

## Security

- All routes require authentication (`CurrentUser` dependency)
- Ownership validation on all CRUD operations
- CASCADE delete when user is deleted
- API keys never exposed in responses (`has_api_key: true` pattern)
- Shared credentials: read-only access for recipients
- Expiry date is informational only, not enforced

---

*Last updated: 2026-03-02*
