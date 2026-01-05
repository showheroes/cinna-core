# Credentials Security - Whitelist Approach

**Last Updated**: 2026-01-05

## Overview

The credentials system uses a **whitelist approach** to control what data is exposed to agent environments. This prevents accidental exposure of sensitive credentials like OAuth refresh tokens and client secrets.

## Security Architecture

### Three-Layer Security Model

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: Database Encryption                                │
│ - All credentials encrypted at rest                          │
│ - Stored in Credential.encrypted_data field                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Field Whitelisting (credentials.json)              │
│ - WHITELIST approach: Only explicitly allowed fields pass    │
│ - Default behavior: DENY (unknown fields excluded)          │
│ - Applied before syncing to agent container                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Value Redaction (README.md)                        │
│ - Shows FILTERED structure (same as credentials.json)       │
│ - Sensitive values replaced with ***REDACTED***             │
│ - Fields removed by whitelist don't appear at all           │
│ - Included in agent prompt for context                      │
└─────────────────────────────────────────────────────────────┘
```

## Whitelist Configuration

### Location
`backend/app/services/credentials_service.py:AGENT_ENV_ALLOWED_FIELDS`

### Design Principles

1. **Explicit Allow**: Only fields in the whitelist are transferred
2. **Fail-Safe Default**: Unknown credential types return empty dict
3. **Minimal Exposure**: Agent gets only what it needs to function
4. **No Refresh Tokens**: Backend handles OAuth token refresh
5. **No Secrets**: Client secrets never leave backend

### Whitelist Examples

#### OAuth Credentials (Gmail, Drive, Calendar)
```python
"gmail_oauth": [
    "access_token",       # ✅ Required for API calls
    "token_type",         # ✅ Usually "Bearer"
    "expires_at",         # ✅ Token expiration timestamp
    "scope",              # ✅ Granted scopes
    "granted_user_email", # ✅ User's email (for display)
    "granted_user_name"   # ✅ User's name (for display)
]

# ❌ NOT INCLUDED (security-critical):
# - refresh_token (backend handles refresh automatically)
# - client_secret (should never leave backend server)
# - granted_at (not needed by agent)
```

#### Non-OAuth Credentials
```python
"email_imap": [
    "host",     # ✅ IMAP server hostname
    "port",     # ✅ Port number
    "login",    # ✅ Username
    "password", # ✅ Password (needed for agent to connect)
    "is_ssl"    # ✅ SSL/TLS flag
]

"api_token": [
    "http_header_name",  # ✅ Pre-processed header name
    "http_header_value"  # ✅ Pre-processed header value with token
]
# ❌ NOT INCLUDED:
# - api_token_type (already processed)
# - api_token_template (already processed)
# - api_token (already included in http_header_value)
```

## Implementation Details

### Filter Function

**File**: `backend/app/services/credentials_service.py:201`

```python
@staticmethod
def filter_credential_data_for_agent_env(
    credential_type: str,
    credential_data: dict
) -> dict:
    """
    Filter using WHITELIST approach.

    Returns:
        New dict with ONLY whitelisted fields
    """
    allowed_fields = AGENT_ENV_ALLOWED_FIELDS.get(credential_type, [])

    if not allowed_fields:
        # Fail-safe: unknown types return empty dict
        return {}

    # Build new dict with ONLY whitelisted fields
    return {
        field: credential_data[field]
        for field in allowed_fields
        if field in credential_data
    }
```

### Usage in Sync Flow

**File**: `backend/app/services/credentials_service.py:649`

```python
@staticmethod
def prepare_credentials_for_environment(session, agent_id) -> dict:
    # Get credentials with decrypted data
    credentials = get_agent_credentials_with_data(session, agent_id)

    # Apply whitelist filtering
    filtered_credentials = []
    for cred in credentials:
        filtered_cred = copy.deepcopy(cred)
        filtered_cred["credential_data"] = filter_credential_data_for_agent_env(
            cred["type"],
            cred["credential_data"]
        )
        filtered_credentials.append(filtered_cred)

    return {
        "credentials_json": filtered_credentials,  # ← Whitelisted data
        "credentials_readme": generate_credentials_readme(credentials)
    }
```

## Security Benefits

### 1. Prevents Accidental Exposure
- New sensitive fields added to database won't be auto-exposed
- Developer must explicitly add field to whitelist
- Code review catches unintended additions

### 2. Clear Audit Trail
- Whitelist is version-controlled
- Changes to allowed fields are tracked in git
- Security team can review what's exposed

### 3. Fail-Safe Default
- Unknown credential types get empty credentials
- Better to break functionality than leak secrets
- Forces developer to explicitly define security boundary

### 4. Separation of Concerns
- **Backend**: Manages refresh tokens, client secrets
- **Agent Environment**: Only gets access tokens and metadata
- **Agent Prompt**: Only sees redacted structure

## OAuth-Specific Security

### Why No Refresh Tokens in Agent Environment?

1. **Backend Handles Refresh**:
   - Token refresh happens automatically in backend
   - Agent always gets fresh access token
   - No need for agent to manage refresh logic

2. **Reduced Attack Surface**:
   - If agent container is compromised, attacker only gets short-lived access token
   - Refresh token (long-lived) remains secure in backend database
   - Attacker can't maintain persistent access after token expires

3. **Simplified Agent Logic**:
   - Agent doesn't need OAuth refresh logic
   - Just use the access token provided
   - Works the same as API token credentials

### Example: Gmail OAuth Flow

```
┌──────────────────────────────────────────────────────────────┐
│ Backend Database (encrypted)                                  │
│ {                                                             │
│   "access_token": "ya29.a0...",     ← Expires in 1 hour      │
│   "refresh_token": "1//0gXXX...",   ← Never expires (kept!)  │
│   "client_secret": "GOCSPX-...",    ← App secret (kept!)     │
│   "expires_at": 1735689600,                                  │
│   "scope": "https://www.googleapis.com/auth/gmail.modify",   │
│   "granted_user_email": "user@gmail.com",                    │
│   "granted_user_name": "John Doe",                           │
│   "granted_at": 1735603200          ← When granted           │
│ }                                                             │
└──────────────────────────────────────────────────────────────┘
                            │
                            │ Whitelist Filter
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ Agent Environment (credentials.json)                         │
│ {                                                             │
│   "access_token": "ya29.a0...",     ← Agent can use this     │
│   "token_type": "Bearer",                                    │
│   "expires_at": 1735689600,         ← Agent knows when stale │
│   "scope": "...",                   ← Agent knows permissions│
│   "granted_user_email": "user@gmail.com",  ← For logging    │
│   "granted_user_name": "John Doe"          ← For logging    │
│ }                                                             │
│ ❌ NO refresh_token                                           │
│ ❌ NO client_secret                                           │
│ ❌ NO granted_at                                              │
└──────────────────────────────────────────────────────────────┘
                            │
                            │ Redaction (for prompt context)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│ Agent Environment (credentials/README.md)                    │
│ {                                                             │
│   "access_token": "***REDACTED***", ← Value hidden           │
│   "token_type": "Bearer",                                    │
│   "expires_at": 1735689600,                                  │
│   "scope": "...",                                            │
│   "granted_user_email": "user@gmail.com",                    │
│   "granted_user_name": "John Doe"                            │
│ }                                                             │
│ ✅ Same structure as credentials.json                        │
│ ❌ refresh_token does NOT appear (was filtered out)          │
│ ❌ client_secret does NOT appear (was filtered out)          │
│ ❌ granted_at does NOT appear (was filtered out)             │
└──────────────────────────────────────────────────────────────┘
```

## Adding New Credential Types

### Checklist

When adding a new credential type:

1. ✅ **Define database model** in `backend/app/models/credential.py`
2. ✅ **Add to CredentialType enum**
3. ✅ **Add whitelist entry** in `AGENT_ENV_ALLOWED_FIELDS`
   - ⚠️ **CRITICAL**: Only include fields agent needs
   - ⚠️ **NEVER** include refresh tokens, secrets, API keys meant for backend
4. ✅ **Add redaction rules** in `SENSITIVE_FIELDS` (for README)
5. ✅ **Test filtering** - verify sensitive fields are excluded

### Example: Adding Slack OAuth

```python
# 1. Add to enum
class CredentialType(str, Enum):
    SLACK_OAUTH = "slack_oauth"

# 2. Define whitelist (CRITICAL STEP)
AGENT_ENV_ALLOWED_FIELDS = {
    "slack_oauth": [
        "access_token",        # ✅ For API calls
        "team_id",             # ✅ Workspace ID
        "team_name",           # ✅ Workspace name
        "user_id",             # ✅ Authorized user
        "scope"                # ✅ Granted scopes
        # ❌ NOT refresh_token
        # ❌ NOT client_secret
        # ❌ NOT signing_secret
    ]
}

# 3. Define redaction rules (for README)
SENSITIVE_FIELDS = {
    "slack_oauth": ["access_token", "refresh_token"]
}
```

## Testing Whitelist

### Manual Verification

```python
# Test that sensitive fields are filtered out
credential_data = {
    "access_token": "ya29...",
    "refresh_token": "1//0g...",  # Should be removed
    "client_secret": "GOCSPX-...",  # Should be removed
    "expires_at": 1234567890
}

filtered = CredentialsService.filter_credential_data_for_agent_env(
    "gmail_oauth",
    credential_data
)

assert "access_token" in filtered
assert "expires_at" in filtered
assert "refresh_token" not in filtered  # ✅ Excluded
assert "client_secret" not in filtered  # ✅ Excluded
```

### Log Verification

Check logs when credentials sync to agent environment:

```
INFO: Excluded 2 field(s) from gmail_oauth before agent env sync: ['client_secret', 'refresh_token']
DEBUG: Including 'access_token' in gmail_oauth for agent env
DEBUG: Including 'token_type' in gmail_oauth for agent env
DEBUG: Including 'expires_at' in gmail_oauth for agent env
```

## Comparison: Whitelist vs Blacklist

### ❌ Blacklist Approach (What We DON'T Use)

```python
# Bad: Remove specific fields
EXCLUDED_FIELDS = {
    "gmail_oauth": ["refresh_token", "client_secret"]
}

# Problem: New field "internal_user_id" added to database
# → Automatically exposed to agent (security risk!)
```

### ✅ Whitelist Approach (What We DO Use)

```python
# Good: Include only specific fields
ALLOWED_FIELDS = {
    "gmail_oauth": ["access_token", "token_type", "expires_at"]
}

# Benefit: New field "internal_user_id" added to database
# → Automatically excluded from agent (secure by default!)
```

## Related Documentation

- [Agent Environment Credentials Management](./agent-sessions/agent_env_credentials_management.md)
- [OAuth Credentials Management](./oauth_credentials_management.md)
- Credential Models: `backend/app/models/credential.py`
- Credentials Service: `backend/app/services/credentials_service.py`

## Security Audit Checklist

When reviewing credential security:

- [ ] All credential types have `AGENT_ENV_ALLOWED_FIELDS` entry
- [ ] OAuth types do NOT include `refresh_token` or `client_secret`
- [ ] Non-OAuth types only include fields needed for agent function
- [ ] New credential types reviewed by security team
- [ ] Sync logs show excluded fields count
- [ ] Agent environment tests verify filtering works
