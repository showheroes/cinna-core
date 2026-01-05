# Agent Environment Credentials Management

## Overview

Agents can access user-provided credentials (email, APIs, databases) to perform automated tasks. Credentials are encrypted in the database, securely synced to agent environments, and made available to scripts in two formats:
- **Full data** (`credentials.json`) - for scripts to use programmatically
- **Redacted documentation** (`credentials/README.md`) - for building agent's prompt context

## Architecture

### Data Flow

1. **User manages credentials** → Stored encrypted in database (`Credential` model)
2. **User shares credential with agent** → Link created (`AgentCredentialLink`)
3. **Environment starts/rebuilds** → Credentials synced to container
4. **User updates credential** → Auto-syncs to all running environments

### File Structure in Agent Environment

```
workspace/
└── credentials/
    ├── credentials.json      # Full credentials data (for scripts)
    └── README.md            # Redacted docs (for agent prompt)
```

## Components

### Backend Services

**`CredentialsService`** (`backend/app/services/credentials_service.py`)
- `prepare_credentials_for_environment()` - Prepares both JSON and README data
- `generate_credentials_readme()` - Creates redacted documentation with ID-based lookup examples
- `redact_credential_data()` - Redacts sensitive fields only if they have values
- `_process_api_token_credential()` - Processes API Token credentials to generate ready-to-use HTTP headers
- `sync_credentials_to_agent_environments()` - Syncs to all running environments
- Event handlers: `event_credential_updated()`, `event_credential_deleted()`, `event_credential_shared()`, `event_credential_unshared()`

**`EnvironmentLifecycleManager`** (`backend/app/services/environment_lifecycle.py`)
- `_sync_agent_data()` - Syncs prompts and credentials after start/rebuild
- Called automatically after: start, restart, rebuild (if was running)

### Agent Environment Service

**`AgentEnvService`** (`backend/app/env-templates/python-env-advanced/app/core/server/agent_env_service.py`)
- `update_credentials()` - Writes both `credentials.json` and `README.md`
- `get_credentials_readme()` - Loads README content for prompt

**API Route** (`backend/app/env-templates/python-env-advanced/app/core/server/routes.py`)
- `POST /config/credentials` - Accepts credentials data from backend

### API Routes

**Credentials Routes** (`backend/app/api/routes/credentials.py`)
- CREATE, UPDATE, DELETE operations trigger automatic environment sync
- All operations use `CredentialsService` for business logic

**Agent Routes** (`backend/app/api/routes/agents.py`)
- Link/unlink credentials trigger automatic environment sync
- Uses `CredentialsService.link_credential_to_agent()` / `unlink_credential_from_agent()`

## Credential Types

### Supported Types

1. **`email_imap`** - IMAP email access
   - Fields: `host`, `port`, `login`, `password`, `is_ssl`
   - Sensitive: `password`

2. **`odoo`** - Odoo ERP API
   - Fields: `url`, `database_name`, `login`, `api_token`
   - Sensitive: `api_token`

3. **`gmail_oauth`** - Gmail OAuth
   - Fields: `access_token`, `refresh_token`, `token_type`, `expires_at`, `scope`
   - Sensitive: `access_token`, `refresh_token`

4. **`api_token`** - API Token (Bearer or Custom)
   - Input fields: `api_token_type` ("bearer" or "custom"), `api_token_template`, `api_token`
   - Processed to: `http_header_name`, `http_header_value` (ready-to-use HTTP headers)
   - Sensitive: `http_header_value`
   - **Processing Logic**:
     - **Bearer type**: Generates `{"http_header_name": "Authorization", "http_header_value": "Bearer {token}"}`
     - **Custom type**: Parses template (e.g., `"X-API-Key: {TOKEN}"`) to generate appropriate header fields
   - This eliminates the need for agents to parse templates - they just use the pre-processed headers

   **Example**:
   ```python
   # User input (UI):
   {
     "api_token_type": "custom",
     "api_token_template": "X-API-Key: {TOKEN}",
     "api_token": "abc123xyz"
   }

   # Processed output (credentials.json):
   {
     "http_header_name": "X-API-Key",
     "http_header_value": "abc123xyz"
   }

   # Agent usage:
   import requests
   headers = {
     config['http_header_name']: config['http_header_value']
   }
   response = requests.get('https://api.example.com', headers=headers)
   ```

## Security Model

### Database Layer
- Credentials encrypted using `encrypt_field()` / `decrypt_field()` (`backend/app/core/security.py`)
- Stored in `Credential.encrypted_data` field

### Environment Layer - Multi-Layer Security

**Layer 1: Field Whitelisting (Agent Environment)**
- **`credentials.json`**: Only whitelisted fields are included (WHITELIST approach)
- `CredentialsService.AGENT_ENV_ALLOWED_FIELDS` defines exactly what fields are transferred
- Security-critical fields NEVER exposed to agent container:
  - OAuth `refresh_token` - Backend handles token refresh
  - OAuth `client_secret` - Should never leave backend server
  - Any field not explicitly whitelisted is excluded
- Unknown credential types return empty dict (fail-safe default)

**Example for Gmail OAuth:**
```python
# Fields sent to agent environment (whitelisted):
{
  "access_token": "...",      # Required for API calls
  "token_type": "Bearer",     # Token type
  "expires_at": 1234567890,   # Expiration timestamp
  "scope": "...",             # Granted scopes
  "granted_user_email": "...", # User's email
  "granted_user_name": "..."   # User's name
}

# Fields EXCLUDED (not in whitelist):
# - refresh_token (backend handles refresh)
# - client_secret (should never leave backend)
# - granted_at (not needed by agent)
```

**Layer 2: Redaction (Agent Prompt)**
- **`README.md`**: Redacted data included in agent prompt
- Shows **FILTERED** credential structure (same as credentials.json)
- Sensitive values replaced by `***REDACTED***` for display
- Only redacts fields that have actual values (not empty/null)
- Empty fields shown as-is (safe, indicates missing configuration)
- README shows exact same structure as credentials.json (no confusion)
- **Important**: Fields removed by whitelist (e.g., `refresh_token`) do NOT appear in README

## Automatic Synchronization

### Triggers

Credentials automatically sync to running environments when:

1. **Environment starts** → Initial sync
2. **Environment rebuilds** (if was running) → Re-sync after rebuild
3. **Credential updated** → Sync to all affected agents' running environments
4. **Credential deleted** → Sync to remove from all affected agents
5. **Credential shared with agent** → Sync to that agent's running environments
6. **Credential unshared from agent** → Sync to remove from that agent

### Implementation

- Uses FastAPI background tasks (routes) or direct async calls (services)
- Only syncs to **running** environments (stopped environments sync on next start)
- Errors logged but don't block other environments from syncing

## Prompt Integration

The building agent's prompt includes `credentials/README.md` content via:

**`PromptGenerator`** (`backend/app/env-templates/python-env-advanced/app/core/server/prompt_generator.py`)
- `_load_credentials_readme()` - Loads README from workspace
- `generate_building_mode_prompt()` - Includes credentials in system prompt with security warnings

### Agent Instructions

Building agent receives:
- Full credential structure (with redacted sensitive values)
- Credential IDs for stable lookup (IDs never change, unlike names)
- Security rules (never read credentials.json directly)
- ID-based usage examples (recommended approach)
- Type-based lookup as alternative (for single-credential cases)
- Clear indication when credentials are empty/need configuration

## Best Practices

### For Users
- Update credentials through UI (triggers auto-sync)
- Share credentials before starting environment (or they'll be empty)
- Credentials persist in workspace (survive rebuilds)
- Use credential IDs in agent scripts (more stable than names)

### For Development
- Always use `CredentialsService` methods (never direct crud calls)
- Event handlers ensure consistency across running environments
- Redaction logic keeps sensitive data out of prompts while showing structure
- API Token credentials are pre-processed to generate ready-to-use HTTP headers

### For Agents (in README.md)
- **Use credential IDs for lookup** - IDs never change, unlike names
- Load credentials at script start and reuse connections
- Handle errors gracefully - credentials might be invalid or expired
- Close connections properly when done
- Never hardcode credentials - always read from the credentials file
