# AI Credentials Management - Implementation Reference

## Purpose

Enable users to manage multiple named AI credentials (API keys) for different SDK providers, with default credential selection that auto-syncs to user profile for backward compatibility.

## Feature Overview

- User creates named AI credentials (e.g., "Production Anthropic", "Testing OpenAI")
- User marks one credential of each type as "default"
- Default credential values auto-sync to user's profile fields (`ai_credentials_encrypted`)
- Existing environment creation continues to work via synced profile fields
- Explicit credential linking to agent environments
- Owner-provided credentials during agent sharing
- AI credentials step in accept share wizard
- Clone credential setup with sharing support

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

## Phase 2 Implementation Details

### Environment Credential Linking

**Purpose:** Allow environments to use specific credentials instead of defaults

**Schema Changes:** `backend/app/models/environment.py`
- `use_default_ai_credentials` (BOOLEAN, default true) - Use user's default credentials
- `conversation_ai_credential_id` (UUID, nullable) - Explicit link for conversation SDK
- `building_ai_credential_id` (UUID, nullable) - Explicit link for building SDK

**Migration:** `backend/app/alembic/versions/k1f2g3h4i5j6_add_env_ai_credentials.py`

**Service Updates:** `backend/app/services/environment_service.py`
- `SDK_TO_CREDENTIAL_TYPE` mapping at line 24 - Maps SDK IDs to AI credential types
- `create_environment()` - Resolves defaults from AICredential table or validates linked credentials

**Frontend Updates:** `frontend/src/components/Environments/AddEnvironment.tsx`
- "Use Default AI Credentials" switch (default: ON)
- When OFF: Credential dropdowns for conversation/building modes filtered by SDK type
- Validation: Check defaults exist or explicit credentials selected

### Agent Share Credential Provision

**Purpose:** Owner can attach AI credentials to share so recipient doesn't need their own

**Schema Changes:** `backend/app/models/agent_share.py`
- `provide_ai_credentials` (BOOLEAN, default false) - Owner provides credentials
- `conversation_ai_credential_id` (UUID, nullable) - Owner's credential for conversation SDK
- `building_ai_credential_id` (UUID, nullable) - Owner's credential for building SDK
- `AICredentialRequirement` schema - SDK type and purpose for wizard

**New Model:** `backend/app/models/ai_credential_share.py`
- `AICredentialShare` table - Junction for sharing credentials with recipients
- `AICredentialSharePublic`, `AICredentialShareCreate` schemas

**Migration:** `backend/app/alembic/versions/j0e1f2g3h4i5_add_share_ai_credentials.py`

**Service Updates:** `backend/app/services/agent_share_service.py`
- `share_agent()` - Accepts `provide_ai_credentials`, `conversation_ai_credential_id`, `building_ai_credential_id`
- Validates credentials exist and belong to owner

**Frontend Updates:** `frontend/src/components/Agents/AgentSharingTab.tsx`
- "Provide AI Credentials" switch in share dialog
- When ON: Credential dropdowns based on agent's active environment SDKs
- Info text explaining credential sharing implications

### Accept Share Wizard AI Credentials Step

**Purpose:** Handle AI credential selection/display when accepting a share

**New Component:** `frontend/src/components/Agents/AcceptShareWizard/WizardStepAICredentials.tsx`

**If owner provided credentials:**
- Green section: "AI Credentials Provided"
- Shows credential names with "Provided by owner" badge
- No action needed from recipient

**If owner did NOT provide credentials:**
- Shows required SDKs based on agent's environment
- Checks if recipient has matching default credentials
- If defaults exist: Shows "Using default: [Name]" with green badge
- If no defaults: Dropdown to select from existing credentials
- If no credentials: Error message with link to Settings

**Validation:**
- Continue button disabled until all required SDK types have credentials
- Both explicit selection and default fallback are valid

**Wizard Flow Update:** `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx`
- Step type: `"overview" | "ai_credentials" | "credentials" | "confirm"`
- State: `aiCredentialSelections` with `conversationCredentialId`, `buildingCredentialId`
- AI Credentials step shown when `!share.ai_credentials_provided && required_ai_credential_types.length > 0`
- Accept mutation includes `ai_credential_selections` in request body

### Clone Credential Setup

**Service Updates:** `backend/app/services/agent_clone_service.py`

**`create_clone()` changes:**
1. Gets original agent's active environment SDK settings
2. Creates clone environment with same SDK settings
3. If share has `provide_ai_credentials=true`:
   - Creates `AICredentialShare` links for recipient via `AICredentialsService.share_credential()`
   - Links clone environment to shared credentials
4. If share has `provide_ai_credentials=false`:
   - Uses recipient's credentials selected in wizard (from `ai_credential_selections`)
   - Falls back to recipient's default credentials if not explicitly selected

### AI Credential Sharing Table

**New Table:** `ai_credential_shares`

**Migration:** `backend/app/alembic/versions/i9d0e1f2g3h4_add_ai_credential_shares.py`

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `ai_credential_id` | UUID | FK to ai_credential.id (CASCADE) |
| `shared_with_user_id` | UUID | FK to user.id (CASCADE) |
| `shared_by_user_id` | UUID | FK to user.id |
| `shared_at` | DATETIME | When share was created |

**Indexes:**
- `ix_ai_credential_shares_credential` - (ai_credential_id)
- `ix_ai_credential_shares_recipient` - (shared_with_user_id)

**Service Methods:** `backend/app/services/ai_credentials_service.py`
- `share_credential(session, credential_id, owner_id, recipient_id)` - Creates share link
- `can_access_credential(session, credential_id, user_id)` - Checks ownership or share access
- `get_credential_for_use(session, credential_id, user_id)` - Returns decrypted data if accessible
- `revoke_share(session, credential_id, recipient_id)` - Removes share link
- `list_shared_with_me(session, user_id)` - Lists credentials shared with user

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

## Phase 3: Dual Anthropic Credential Types & Expiry Management

### Purpose

Support both Anthropic API Keys and Claude Code OAuth Tokens with automatic detection, appropriate environment variable handling, and expiry notification management.

### Feature Overview

- **Dual Credential Types**: Support `sk-ant-api*` (API Keys) and `sk-ant-oat*` (OAuth Tokens)
- **Auto-Detection**: System detects credential type by prefix and sets appropriate environment variable
- **Expiry Notifications**: Optional expiry date field with auto-set for OAuth tokens (11 months)
- **Environment Variables**: `ANTHROPIC_API_KEY` for API keys, `CLAUDE_CODE_OAUTH_TOKEN` for OAuth tokens
- **UI Enhancements**: Instructions modal, auto-fill expiry dates, visual expiry badges

### Anthropic Credential Types

| Prefix | Type | Environment Variable | Typical Expiry | Notes |
|--------|------|---------------------|----------------|-------|
| `sk-ant-api*` | API Key | `ANTHROPIC_API_KEY` | None | Traditional API keys from console.anthropic.com |
| `sk-ant-oat*` | OAuth Token | `CLAUDE_CODE_OAUTH_TOKEN` | 1 year | Generated via `claude setup-token` CLI |

**Reference:** `backend/app/utils.py:155` - `detect_anthropic_credential_type()`

### Auto-Detection Logic

**File:** `backend/app/utils.py`

```python
def detect_anthropic_credential_type(api_key: str) -> tuple[str, str]:
    """
    Returns (env_var_name, key_type_description)
    - sk-ant-oat* → ("CLAUDE_CODE_OAUTH_TOKEN", "OAuth Token")
    - sk-ant-api* → ("ANTHROPIC_API_KEY", "API Key")
    - other → ("ANTHROPIC_API_KEY", "API Key (Unknown Format)")
    """
```

**Detection Points:**

1. **On Credential Creation** (`ai_credentials_service.py:76-83`)
   - Detects OAuth tokens
   - Auto-sets `expiry_notification_date` to 11 months from now (335 days)
   - Logs: `"Auto-set OAuth token expiry notification to YYYY-MM-DD"`

2. **On Credential Update** (`ai_credentials_service.py:130-136`)
   - When API key is updated to OAuth token
   - Auto-sets expiry if not explicitly provided
   - Logs: `"Auto-set OAuth token expiry notification to YYYY-MM-DD (key updated)"`

3. **On Environment Generation** (`environment_lifecycle.py:1293-1309`)
   - Detects credential type
   - Sets appropriate environment variable in `.env` file
   - Logs: `"Detected Anthropic credential: {key_type} -> {env_var_name}"`

### Expiry Notification Date

**Schema Addition:** `ai_credential.expiry_notification_date` (DATETIME, nullable)

**Migration:** `backend/app/alembic/versions/67bd39e7e42c_add_expiry_notification_date_to_ai_.py`

**Purpose:** Reminder date for credential renewal, not enforcement

**Behavior:**
- **OAuth Tokens**: Auto-set to 11 months (335 days) from creation/update
- **API Keys**: Optional, user can manually set if desired
- **User Override**: User can always modify or clear the auto-set date

**Models Updated:**
- `AICredentialBase.expiry_notification_date` (shared field)
- `AICredentialCreate.expiry_notification_date` (optional input)
- `AICredentialUpdate.expiry_notification_date` (optional input)
- `AICredentialPublic.expiry_notification_date` (API response)

### Environment Variable Generation

**File:** `backend/app/services/environment_lifecycle.py:1293-1344`

**Process:**

1. Checks if Anthropic SDK is used (`uses_anthropic`)
2. If yes and credential exists:
   - Detects credential type via `detect_anthropic_credential_type()`
   - Sets appropriate env var based on detection
   - Adds comment for unused variable
3. Generates `.env` file with both variables

**Example Output:**

```bash
# For OAuth Token (sk-ant-oat01-...)
ANTHROPIC_API_KEY=
# ANTHROPIC_API_KEY not set
CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-xxxxxxxxxxxx

# For API Key (sk-ant-api03-...)
ANTHROPIC_API_KEY=sk-ant-api03-xxxxxxxxxxxx
CLAUDE_CODE_OAUTH_TOKEN=
# CLAUDE_CODE_OAUTH_TOKEN not set
```

**Docker Template:** `backend/app/env-templates/python-env-advanced/docker-compose.template.yml:22-23`

Both environment variables passed to container (optional with `:-` syntax):
```yaml
- ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
- CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN:-}
```

### Frontend UI Enhancements

#### 1. Anthropic Credentials Instructions Modal

**File:** `frontend/src/components/UserSettings/AnthropicCredentialsModal.tsx`

**Structure:**
- Encyclopedia-style modal (pattern from `GettingStartedModal.tsx`)
- Violet accent colors, dark mode support
- 800px max width, 80vh max height
- Sidebar navigation between articles

**Articles:**

1. **"Setup via API Keys"**
   - Link to console.anthropic.com with external link icon
   - Step-by-step instructions for getting API keys
   - Security warning about API key storage
   - Example key format display

2. **"Setup via Claude Code OAuth"**
   - Installation link to `https://claude.com/product/claude-code`
   - Command: `claude setup-token`
   - Emphasized: "Copy token from console immediately"
   - Warning: Token only shown once
   - 1-year expiration notice with Calendar icon

**Triggered From:** `AICredentialDialog.tsx:226-241`
- Info banner when type="anthropic"
- "Instructions" button opens modal
- Shows: "Anthropic supports API Keys (sk-ant-api...) and OAuth Tokens (sk-ant-oat...)"

#### 2. Auto-Fill Expiry Date

**File:** `frontend/src/components/UserSettings/AICredentialDialog.tsx:92-101`

**Behavior:**
- `useEffect` watches `apiKey` and `type` state
- When user types OAuth token (`sk-ant-oat*`):
  - Calculates: `today + 335 days`
  - Auto-fills expiry date field
  - User can adjust or clear if desired

**Help Text:**
> "Auto-fills to 11 months from now when you enter an OAuth token (sk-ant-oat...). You can adjust this date."

#### 3. Expiry Date Badges in Credentials List

**File:** `frontend/src/components/UserSettings/AICredentials.tsx:49-89, 249-267`

**Badge Function:** `getExpiryBadgeProps(expiryDate)`

**Color Coding:**

| Status | Days Until Expiry | Color | Example |
|--------|------------------|-------|---------|
| Expired | < 0 | Red | `bg-red-100 dark:bg-red-950` |
| Expiring Very Soon | ≤ 30 | Orange | `bg-orange-100 dark:bg-orange-950` |
| Expiring Soon | 31-60 | Amber | `bg-amber-100 dark:bg-amber-950` |
| Not Expiring Soon | > 60 | Gray | `bg-muted text-muted-foreground` |

**Display:**
```
[Credential Name] ⭐ [📅 Dec 26, 2026] [Type] [Actions...]
```

**Tooltip:**
- Expired: "Expired on {date}"
- Active: "Expires in {X} days ({date})"
- Future: "Expires on {date} (in {X} days)"

#### 4. RelativeTime Component Extensions

**File:** `frontend/src/components/Common/RelativeTime.tsx`

**New Parameters:**

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `asBadge` | boolean | Display as colored badge | `false` |
| `icon` | ReactNode | Icon before text | `undefined` |
| `showTooltip` | boolean | Show full date tooltip | `false` |
| `colorCode` | boolean | Auto-color by recency | `false` |
| `tooltipContent` | string | Custom tooltip text | Full date/time |

**Color Coding (when colorCode=true):**

| Time Range | Color | Badge Class |
|------------|-------|-------------|
| < 5 minutes | Green | `bg-green-100 dark:bg-green-950` |
| < 30 minutes | Blue | `bg-blue-100 dark:bg-blue-950` |
| < 24 hours | Violet | `bg-violet-100 dark:bg-violet-950` |
| < 7 days | Amber | `bg-amber-100 dark:bg-amber-950` |
| Older | Gray | `bg-muted` |

**Usage Example:**
```tsx
<RelativeTime
  timestamp={session.last_message_at}
  asBadge={true}
  icon={<Clock className="h-3 w-3" />}
  showTooltip={true}
  colorCode={true}
/>
```

**Output:** `[🕐 5 minutes ago]` (green badge with tooltip "Jan 25, 2026, 3:45 PM")

### Backend Implementation Details

#### Service Updates

**File:** `backend/app/services/ai_credentials_service.py`

**New Import:** `from app.utils import detect_anthropic_credential_type`

**create_credential() Enhancement:**
```python
# Lines 76-83
if data.type == AICredentialType.ANTHROPIC and not expiry_date:
    env_var_name, key_type = detect_anthropic_credential_type(data.api_key)
    if env_var_name == "CLAUDE_CODE_OAUTH_TOKEN":
        expiry_date = datetime.now(timezone.utc) + timedelta(days=335)
        logger.info(f"Auto-set OAuth token expiry notification to {expiry_date.date()}")
```

**update_credential() Enhancement:**
```python
# Lines 130-136
if data.api_key is not None and credential.type == AICredentialType.ANTHROPIC and data.expiry_notification_date is None:
    env_var_name, key_type = detect_anthropic_credential_type(new_api_key)
    if env_var_name == "CLAUDE_CODE_OAUTH_TOKEN":
        credential.expiry_notification_date = datetime.now(timezone.utc) + timedelta(days=335)
        logger.info(f"Auto-set OAuth token expiry notification to {credential.expiry_notification_date.date()} (key updated)")
```

#### Environment Lifecycle Updates

**File:** `backend/app/services/environment_lifecycle.py`

**Import Added:** `from app.utils import detect_anthropic_credential_type`

**_generate_env_file() Enhancement:** Lines 1293-1344

```python
# Generate Anthropic credential environment variables based on credential type
if uses_anthropic and anthropic_api_key:
    env_var_name, key_type = detect_anthropic_credential_type(anthropic_api_key)
    logger.info(f"Detected Anthropic credential: {key_type} -> {env_var_name}")

    if env_var_name == "ANTHROPIC_API_KEY":
        anthropic_api_key_line = f"ANTHROPIC_API_KEY={anthropic_api_key}"
        claude_code_oauth_token_line = "# CLAUDE_CODE_OAUTH_TOKEN not set"
    else:  # CLAUDE_CODE_OAUTH_TOKEN
        anthropic_api_key_line = "# ANTHROPIC_API_KEY not set"
        claude_code_oauth_token_line = f"CLAUDE_CODE_OAUTH_TOKEN={anthropic_api_key}"
```

### Backward Compatibility

**✓ No Breaking Changes:**

1. **Existing Credentials:** All existing Anthropic credentials continue working
2. **Unknown Prefixes:** Default to `ANTHROPIC_API_KEY` if prefix not recognized
3. **Optional Expiry:** `expiry_notification_date` is nullable, no migration data needed
4. **Environment Regeneration:** `.env` files regenerated on environment start with new variables
5. **API Compatibility:** New optional fields don't affect existing API calls

### Verification Steps

#### Backend Verification

1. **Test API Key Detection:**
   ```bash
   from app.utils import detect_anthropic_credential_type
   env_var, key_type = detect_anthropic_credential_type("sk-ant-api03-abc123")
   # Returns: ("ANTHROPIC_API_KEY", "API Key")
   ```

2. **Test OAuth Token Detection:**
   ```bash
   from app.utils import detect_anthropic_credential_type
   env_var, key_type = detect_anthropic_credential_type("sk-ant-oat01-xyz789")
   # Returns: ("CLAUDE_CODE_OAUTH_TOKEN", "OAuth Token")
   ```

3. **Check Database Schema:**
   ```bash
   docker compose exec backend python -c "from sqlalchemy import inspect, create_engine; from app.core.config import settings; engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI)); inspector = inspect(engine); columns = inspector.get_columns('ai_credential'); print([c['name'] for c in columns])"
   # Should include 'expiry_notification_date'
   ```

#### Frontend Verification

1. **Create OAuth Token Credential:**
   - Open AI Credentials dialog
   - Select "Anthropic" type
   - Click "Instructions" - modal should open
   - Enter `sk-ant-oat01-...` in API key field
   - Expiry date should auto-fill to 11 months from now

2. **Create API Key Credential:**
   - Enter `sk-ant-api03-...` in API key field
   - Expiry date should remain empty (optional)

3. **View Credentials List:**
   - Credentials with expiry dates show colored badges
   - Badge color indicates urgency (red/orange/amber/gray)
   - Tooltip shows full expiry details

4. **Check Environment Container:**
   - Start environment
   - Check `.env` file has both variables
   - Verify correct variable is set based on credential type

### Security Considerations

**No Security Changes:**
- Expiry date is informational only, not enforced
- Both credential types encrypted identically
- No additional exposure of sensitive data
- Auto-detection happens server-side only

**OAuth Token Security:**
- Tokens shown once during CLI setup (not retrievable)
- Users warned to copy immediately
- Instructions emphasize one-time visibility
- Same encryption as API keys

### File Locations Reference

#### Backend

**Utilities:**
- `backend/app/utils.py:155-187` - `detect_anthropic_credential_type()` function

**Models:**
- `backend/app/models/ai_credential.py:25, 45, 63, 80` - `expiry_notification_date` field additions

**Services:**
- `backend/app/services/ai_credentials_service.py:15, 76-83, 130-136, 238` - Auto-set expiry logic
- `backend/app/services/environment_lifecycle.py:18, 1293-1344` - Environment variable generation

**Templates:**
- `backend/app/env-templates/python-env-advanced/docker-compose.template.yml:23` - OAuth token env var

**Migrations:**
- `backend/app/alembic/versions/67bd39e7e42c_add_expiry_notification_date_to_ai_.py` - Expiry date field

#### Frontend

**Components:**
- `frontend/src/components/UserSettings/AnthropicCredentialsModal.tsx` - Instructions modal (NEW)
- `frontend/src/components/UserSettings/AICredentialDialog.tsx:57, 92-101, 277-303` - Auto-fill & expiry field
- `frontend/src/components/UserSettings/AICredentials.tsx:3, 49-89, 249-267` - Expiry badges
- `frontend/src/components/Common/RelativeTime.tsx:1-119` - Extended with badge support

**Client (regenerated):**
- `frontend/src/client/types.gen.ts` - Updated TypeScript types with `expiry_notification_date`

### Implementation Scenarios

#### Scenario 1: User Creates OAuth Token Credential

```
1. User opens AI Credentials dialog
2. Selects type: "Anthropic"
3. Clicks "Instructions" button
4. Modal opens with OAuth token setup guide
5. User runs `claude setup-token` on local machine
6. Copies token: sk-ant-oat01-xxxxxxxxxxxx
7. Pastes into API key field
8. Frontend auto-fills expiry: Dec 26, 2026 (11 months)
9. User saves credential
10. Backend detects OAuth token
11. Backend sets expiry_notification_date if not provided
12. Credential stored with type detection logged
```

#### Scenario 2: User Creates API Key Credential

```
1. User opens AI Credentials dialog
2. Selects type: "Anthropic"
3. Enters API key: sk-ant-api03-xxxxxxxxxxxx
4. Expiry field remains empty (optional)
5. User optionally sets expiry date manually
6. User saves credential
7. Backend detects API key type
8. Credential stored without auto-expiry
```

#### Scenario 3: Environment Uses OAuth Token

```
1. User creates environment with Anthropic SDK
2. Environment has OAuth token credential set as default
3. Environment lifecycle manager generates .env file
4. Detection runs: detect_anthropic_credential_type("sk-ant-oat01-...")
5. Returns: ("CLAUDE_CODE_OAUTH_TOKEN", "OAuth Token")
6. .env file written with:
   - ANTHROPIC_API_KEY=
   - CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
7. Docker container starts with OAuth token
8. Agent SDK reads CLAUDE_CODE_OAUTH_TOKEN
```

#### Scenario 4: User Views Expiring Credentials

```
1. User opens Settings > AI Credentials
2. Credentials list shows expiry badges:
   - "Test Token" [📅 Feb 15, 2026] (orange, 25 days)
   - "Production Key" [📅 Dec 26, 2026] (gray, 335 days)
3. User hovers over orange badge
4. Tooltip: "Expires in 25 days (Feb 15, 2026)"
5. User clicks edit on "Test Token"
6. Can update expiry date or generate new token
```

#### Scenario 5: User Updates API Key to OAuth Token

```
1. User has existing credential with API key
2. User edits credential
3. Replaces API key with OAuth token: sk-ant-oat01-...
4. Frontend auto-fills new expiry date
5. User saves
6. Backend detects type change
7. Auto-sets expiry_notification_date
8. Logs: "Auto-set OAuth token expiry notification to 2026-12-26 (key updated)"
```

## Related Documentation

- `docs/business-domain/shared_agents_management.md` - Agent sharing feature
- `docs/agent-sessions/agent_env_docker.md` - Environment architecture
- `docs/security_credentials_whitelist.md` - Credential encryption pattern

## Phase 2 File Locations Reference

### Backend - Models

- `backend/app/models/ai_credential_share.py` - AICredentialShare model and schemas
- `backend/app/models/agent_share.py` - Updated with AI credential provision fields
- `backend/app/models/environment.py` - Updated with AI credential linking fields

### Backend - Migrations

- `backend/app/alembic/versions/i9d0e1f2g3h4_add_ai_credential_shares.py` - AI credential shares table
- `backend/app/alembic/versions/j0e1f2g3h4i5_add_share_ai_credentials.py` - Agent share AI credential fields
- `backend/app/alembic/versions/k1f2g3h4i5j6_add_env_ai_credentials.py` - Environment AI credential fields

### Backend - Services

- `backend/app/services/ai_credentials_service.py` - Sharing methods added
- `backend/app/services/environment_service.py` - SDK to credential type mapping
- `backend/app/services/agent_share_service.py` - AI credential provision handling
- `backend/app/services/agent_clone_service.py` - Clone AI credential setup

### Backend - Routes

- `backend/app/api/routes/agent_shares.py` - Updated endpoints for AI credentials

### Frontend - Components

- `frontend/src/components/Environments/AddEnvironment.tsx` - Credential selection UI
- `frontend/src/components/Agents/AgentSharingTab.tsx` - Share dialog AI credentials
- `frontend/src/components/Agents/AcceptShareWizard/WizardStepAICredentials.tsx` - New wizard step
- `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx` - Updated wizard flow

---

**Document Version:** 4.0
**Last Updated:** 2026-01-25
**Status:** Implemented (Phase 3 completed)
