# Accept Agent Share Wizard - Implementation Reference

## Purpose

Multi-step dialog wizard that guides users through accepting a shared agent, handling credential setup, and creating a clone agent with proper configuration.

## Feature Overview

**Flow:**
1. User receives pending share notification on Agents page
2. User clicks "Accept" on pending share card
3. Wizard opens with step indicator
4. Step 1 (Overview): Review agent details, access level, what they'll receive
5. Step 2 (Credentials): Configure non-shareable credentials (skipped if all shared)
6. Step 3 (Confirm): Review summary and accept
7. Clone agent created, wizard closes, agents list refreshes

**Key Concepts:**
- **Dynamic Step Count**: 2 steps if all credentials are shareable, 3 steps if setup required
- **Credential Categories**: Shareable (ready to use) vs Setup Required (user must configure)
- **Skip Option**: Users can skip credential setup and configure later
- **Clone Creation**: Calls `AgentSharesService.acceptShare()` with credentials data

## Architecture

```
PendingAgentCard → AcceptShareWizard → WizardSteps → AgentSharesService.acceptShare()
                           │
                    ┌──────┴──────┐
                    │             │
             WizardStepOverview   WizardStepCredentials
                    │                    │
                    └────────────────────┘
                              │
                     WizardStepConfirm
                              │
                     AgentCloneService.create_clone()
```

## Data/State Lifecycle

### Wizard State

| State | Type | Description |
|-------|------|-------------|
| `currentStep` | `"overview" \| "credentials" \| "confirm"` | Active wizard step |
| `credentialsData` | `Record<string, Record<string, string>>` | User-provided credential values |

### Step Navigation Logic

| Condition | Step Progression |
|-----------|------------------|
| All credentials shareable | Overview → Confirm (2 steps) |
| Has non-shareable credentials | Overview → Credentials → Confirm (3 steps) |

### Credential Requirement Categories

| Category | `allow_sharing` | UI Treatment |
|----------|-----------------|--------------|
| Ready to Use | `true` | Green badge, "Shared by owner" |
| Setup Required | `false` | Yellow card, value input field |

## Database Schema

### Related Models

**PendingSharePublic:** `backend/app/models/agent_share.py`
- `id`, `original_agent_id`, `original_agent_name`
- `share_mode` - "user" or "builder"
- `shared_by_email`, `shared_by_name`
- `credentials_required` - List of `CredentialRequirement`

**CredentialRequirement:** `backend/app/models/agent_share.py`
- `name` - Credential name
- `type` - Credential type (e.g., "api_token", "gmail_oauth")
- `allow_sharing` - Whether owner has enabled sharing

### Clone Creation

When wizard completes, `AgentCloneService.create_clone()` creates:
- Agent record with `is_clone=true`, `parent_agent_id` set
- Environment for clone (same template as parent)
- Workspace files copied from parent
- Credentials: shared (via `CredentialShare`) or placeholders

## Backend Implementation

### Routes

**File:** `backend/app/api/routes/agent_shares.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/shares/pending` | List pending shares for current user |
| `POST` | `/shares/{share_id}/accept` | Accept share with credentials data |
| `POST` | `/shares/{share_id}/decline` | Decline share |

### Services

**AgentShareService:** `backend/app/services/agent_share_service.py`
- `get_pending_shares(session, user_id)` - Query pending shares for user
- `accept_share(session, share_id, recipient_id, credentials_data)` - Validate and create clone

**AgentCloneService:** `backend/app/services/agent_clone_service.py`
- `create_clone(session, original_agent, recipient_id, clone_mode, credentials_data)` - Full clone creation
- `copy_workspace(original_env_id, clone_env_id)` - Copy scripts, docs, knowledge
- `setup_clone_credentials(session, original_agent, clone, user_provided_data)` - Handle credential sharing/placeholders

### Request/Response Models

**AcceptShareRequest:** `backend/app/api/routes/agent_shares.py:53`
- `credentials` - Optional dict `{credential_name: {field: value}}`

## Frontend Implementation

### Component Structure

**AcceptShareWizard:** `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx`
- Main dialog container with step indicator
- Manages wizard state and navigation
- Handles accept mutation via `AgentSharesService.acceptShare()`

**WizardStepOverview:** `frontend/src/components/Agents/AcceptShareWizard/WizardStepOverview.tsx`
- Displays agent info, sharer details
- Explains access level (User vs Builder permissions)
- Lists what recipient will receive (copy, prompts, scripts, updates)

**WizardStepCredentials:** `frontend/src/components/Agents/AcceptShareWizard/WizardStepCredentials.tsx`
- Groups credentials: Ready to Use vs Setup Required
- Renders input fields for non-shareable credentials
- Allows "Skip for now" to proceed without configuring

**WizardStepConfirm:** `frontend/src/components/Agents/AcceptShareWizard/WizardStepConfirm.tsx`
- Summary card with agent name, access level, sharer
- Credentials status (shared, configured, skipped counts)
- Warning alert if credentials were skipped
- Final accept button triggers clone creation

**Index Export:** `frontend/src/components/Agents/AcceptShareWizard/index.ts`
- Exports `AcceptShareWizard` component

### Parent Components

**PendingAgentCard:** `frontend/src/components/Agents/PendingAgentCard.tsx`
- Card displaying pending share info
- Accept/Decline buttons
- Clicking Accept opens wizard (in parent route)

**Agents Page:** `frontend/src/routes/_layout/agents.tsx`
- Fetches pending shares via `AgentSharesService.getPendingShares()`
- Renders PendingAgentCard for each pending share
- Manages wizard open state and selected share
- Handles decline mutation inline

### Hooks and State

**React Query Usage:**
- `useMutation()` for `AgentSharesService.acceptShare()`
- Query invalidation on success: `["agents"]`, `["pendingShares"]`

**Component Props:**
- `open` / `onOpenChange` - Dialog visibility control
- `share` - `PendingSharePublic` object with all share details
- `onComplete` - Callback after successful acceptance

## Security Features

### Validation Rules

**Backend:**
- Share must exist and be in "pending" status
- Recipient ID must match `shared_with_user_id`
- Original agent must still exist

**Frontend:**
- Credential inputs use `type="password"` for sensitive values
- No credential values stored in URL or visible state

### Access Control

- Only the designated recipient can accept/decline
- Credentials with `allow_sharing=false` require user to provide own values
- Clone inherits share mode (user/builder) restrictions

## Key Integration Points

### Wizard Entry Point

`frontend/src/routes/_layout/agents.tsx`
- Renders `AcceptShareWizard` when user clicks Accept on `PendingAgentCard`
- Passes selected `PendingSharePublic` object to wizard

### Clone Creation Chain

1. `AcceptShareWizard` calls `AgentSharesService.acceptShare()`
2. Route `POST /shares/{share_id}/accept` → `agent_shares.py:accept_share()`
3. `AgentShareService.accept_share()` validates and delegates to clone service
4. `AgentCloneService.create_clone()` creates agent, environment, workspace, credentials

### Credential Resolution

`backend/app/api/routes/agent_shares.py:_share_to_pending_public()`
- Queries `AgentCredentialLink` for original agent's credentials
- Builds `CredentialRequirement` list with `allow_sharing` status
- Frontend uses this to determine which step/fields to show

## File Locations Reference

### Frontend - Wizard Components

- `frontend/src/components/Agents/AcceptShareWizard/AcceptShareWizard.tsx` - Main wizard container
- `frontend/src/components/Agents/AcceptShareWizard/WizardStepOverview.tsx` - Step 1: Agent overview
- `frontend/src/components/Agents/AcceptShareWizard/WizardStepCredentials.tsx` - Step 2: Credential setup
- `frontend/src/components/Agents/AcceptShareWizard/WizardStepConfirm.tsx` - Step 3: Confirmation
- `frontend/src/components/Agents/AcceptShareWizard/index.ts` - Module export

### Frontend - Related Components

- `frontend/src/components/Agents/PendingAgentCard.tsx` - Share card with Accept/Decline
- `frontend/src/routes/_layout/agents.tsx` - Agents page with pending shares section

### Backend - Routes

- `backend/app/api/routes/agent_shares.py` - Share acceptance endpoints

### Backend - Services

- `backend/app/services/agent_share_service.py` - `accept_share()`, `get_pending_shares()`
- `backend/app/services/agent_clone_service.py` - `create_clone()`, `setup_clone_credentials()`

### Backend - Models

- `backend/app/models/agent_share.py` - `PendingSharePublic`, `CredentialRequirement`
- `backend/app/models/credential.py` - `Credential.allow_sharing` field

### Frontend - Generated Client

- `frontend/src/client/sdk.gen.ts` - `AgentSharesService.acceptShare()`, `getPendingShares()`
- `frontend/src/client/types.gen.ts` - `PendingSharePublic`, `AcceptShareRequest`

### Related Documentation

- `docs/business-domain/shared_agents_management.md` - Full sharing feature overview
- `docs/business-domain/ai_credentials_management.md` - AI credentials integration (planned)

---

**Document Version:** 1.0
**Last Updated:** 2026-01-17
**Status:** Complete
