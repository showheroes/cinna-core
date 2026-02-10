# Affected Environments & Rebuild Widget

## Purpose

Provides visibility and control when AI credentials are updated. Shows which agent environments are using a credential and enables easy batch or individual rebuild operations to apply new credentials.

## When It Appears

The dialog automatically opens after:
1. **Credential Update** - User edits an AI credential (API key, name, etc.)
2. **Set as Default** - User marks a credential as default via star icon

## What It Shows

### Environment Information
- **Agent Name** - Which agent the environment belongs to
- **Environment Name** - Instance name (e.g., "Production", "Development")
- **Status Badge** - Current state (running, suspended, stopped, error)
- **Usage Type** - How credential is used:
  - "conversation" - For conversation mode only
  - "building" - For building mode only
  - "conversation & building" - For both modes
- **Owner Email** - Environment owner (useful for shared credentials)

### Sharing Information
- **Shared Users Alert** - Shows which users have access to this credential
- **Format**: "Shared with: user1@example.com, user2@example.com"
- **Note**: Shared users may also have environments using this credential

### Warnings
- **Running Environments Alert** - "Some environments are currently running. Rebuilding will interrupt active sessions."

## User Actions

### 1. Batch Rebuild (Default Workflow)
- **All environments pre-selected by default** ✓ (fastest option)
- Click **"Rebuild Selected"** button
- All selected environments rebuild in parallel
- Dialog can be closed immediately (rebuilds continue in background)

### 2. Selective Rebuild
- Deselect specific environments using checkboxes
- Click **"Rebuild Selected"** with custom selection
- Only selected environments will rebuild

### 3. Individual Rebuild
- Click **"Rebuild"** button on individual environment card
- Single environment rebuilds independently

### 4. Skip Rebuilding
- Click **"Close"** button
- Environments will continue using old credentials until manually rebuilt later
- No impact on environment operation (old credentials still work)

## Rebuild Behavior

### Status Preservation
Environments maintain their status after rebuild:
- **Running** → Rebuild → **Restart automatically** (applies new credentials immediately)
- **Suspended** → Rebuild → **Stay suspended** (new credentials ready, but not started)
- **Stopped** → Rebuild → **Stay stopped** (new credentials ready, but not started)

### What Happens During Rebuild
1. Environment container stopped (if running)
2. Docker image rebuilt with new credentials
3. Container recreated with new configuration
4. Environment restarted if it was previously running
5. WebSocket events provide real-time progress updates

### Background Execution
- Rebuilds run asynchronously (non-blocking)
- Dialog can be closed during rebuild process
- Toast notification: "Rebuilds will continue in background"
- WebSocket events update environment statuses in UI

## Empty State

When no environments use the credential:
- Shows info icon with friendly message
- "No environments are using this credential yet."
- "You can safely update or delete it without any impact."

## Architecture

### Backend Query Flow

```
User Action (Update/Set Default)
         ↓
GET /api/v1/ai-credentials/{id}/affected-environments
         ↓
AICredentialsService.get_affected_environments()
         ↓
Query: JOIN AgentEnvironment + Agent + User
Filter: conversation_ai_credential_id OR building_ai_credential_id = credential_id
         ↓
Calculate usage per environment (conversation/building/both)
Query AICredentialShare for shared users
         ↓
Return: AffectedEnvironmentsPublic
  - environments: list[AffectedEnvironmentPublic]
  - shared_with_users: list[SharedUserPublic]
  - count: int
```

### Rebuild Flow

```
User clicks "Rebuild Selected"
         ↓
Promise.allSettled([
  POST /api/v1/environments/{env1_id}/rebuild,
  POST /api/v1/environments/{env2_id}/rebuild,
  POST /api/v1/environments/{env3_id}/rebuild
])
         ↓
For each environment:
  - Validate ownership
  - Stop container (if running)
  - Rebuild Docker image
  - Recreate container with new credentials
  - Start container (if was running)
  - Emit WebSocket events
         ↓
Frontend receives:
  - Success count: "Successfully started rebuild for 3 environments"
  - Or partial failure: "2 succeeded, 1 failed. Check console."
         ↓
Query invalidation: ["environments"]
WebSocket updates: Real-time status changes
```

## Implementation Details

### Backend Components

**Models:** `backend/app/models/ai_credential.py`
```python
class AffectedEnvironmentPublic(SQLModel):
    environment_id: uuid.UUID
    agent_id: uuid.UUID
    agent_name: str
    environment_name: str
    status: str
    usage: str  # "conversation" | "building" | "conversation & building"
    owner_id: uuid.UUID
    owner_email: str

class SharedUserPublic(SQLModel):
    user_id: uuid.UUID
    email: str
    shared_at: datetime

class AffectedEnvironmentsPublic(SQLModel):
    credential_id: uuid.UUID
    credential_name: str
    environments: list[AffectedEnvironmentPublic]
    shared_with_users: list[SharedUserPublic]
    count: int
```

**Service:** `backend/app/services/ai_credentials_service.py`
```python
def get_affected_environments(
    session: Session,
    credential_id: uuid.UUID,
    user_id: uuid.UUID,
) -> AffectedEnvironmentsPublic:
    # Verifies user access (ownership or share)
    # Queries environments using this credential
    # Returns structured response
```

**API Endpoint:** `backend/app/api/routes/ai_credentials.py`
```python
@router.get("/{credential_id}/affected-environments")
def get_affected_environments(
    session: SessionDep,
    current_user: CurrentUser,
    credential_id: uuid.UUID
) -> AffectedEnvironmentsPublic
```

### Frontend Components

**Main Dialog:** `frontend/src/components/UserSettings/AffectedEnvironmentsDialog.tsx`

**Props:**
```typescript
interface AffectedEnvironmentsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  credentialId: string
  credentialName: string
}
```

**Key Features:**
- React Query data fetching (`enabled: open`)
- Selection state with `Set<string>`
- All environments pre-selected on load
- Individual and batch rebuild mutations
- `Promise.allSettled` for parallel execution
- Real-time rebuilding state tracking

**Integration Points:**

1. **AICredentialDialog** (`frontend/src/components/UserSettings/AICredentialDialog.tsx`)
   - Triggers after update mutation succeeds
   - Passes credential ID and name

2. **AICredentials** (`frontend/src/components/UserSettings/AICredentials.tsx`)
   - Triggers after set-default mutation succeeds
   - Passes credential ID and name from star button click

### State Management

**Query Keys:**
- `["affectedEnvironments", credentialId]` - Affected environments data
- `["environments"]` - Invalidated after rebuilds to refresh list

**Mutations:**
- Individual rebuild: `EnvironmentsService.rebuildEnvironment({ id })`
- Batch rebuild: Multiple parallel mutations with `Promise.allSettled`

## User Experience Scenarios

### Scenario 1: Quick Batch Rebuild (Default Workflow)

```
1. User edits "Production Anthropic" credential
2. Changes API key from old to new token
3. Clicks "Update"
4. Success toast: "AI credential updated successfully"
5. Dialog opens showing 3 environments (all selected ✓)
6. User clicks "Rebuild Selected" (no need to select, already selected)
7. Success toast: "Successfully started rebuild for 3 environments"
8. User closes dialog
9. Rebuilds continue in background
10. Environment statuses update in real-time via WebSocket
```

**Time Saved:** User doesn't need to select environments manually (pre-selected by default)

### Scenario 2: Selective Rebuild

```
1. User sets credential as default (star icon)
2. Dialog shows 5 environments
3. User notices "Testing Environment" is running (orange warning shown)
4. User unchecks "Testing Environment" to avoid interruption
5. Clicks "Rebuild Selected" (4 environments)
6. Testing environment keeps old credentials (will update later)
7. Other 4 environments rebuild with new credentials
```

### Scenario 3: Individual Rebuild

```
1. Dialog shows 3 environments
2. User wants to rebuild one at a time to observe behavior
3. Clicks "Rebuild" on first environment
4. Waits for completion (watches status change via WebSocket)
5. Clicks "Rebuild" on second environment
6. Continues incrementally
```

### Scenario 4: No Environments (New Credential)

```
1. User creates new credential "Backup Anthropic"
2. User immediately edits it to fix typo in name
3. Dialog opens showing empty state
4. Message: "No environments are using this credential yet"
5. User clicks "Close"
6. No rebuilds needed
```

### Scenario 5: Shared Credential Update

```
Owner:
1. Updates shared credential "Team Claude"
2. Dialog shows environments from both owner and recipients
3. Alert: "Shared with: alice@example.com, bob@example.com"
4. Owner rebuilds all environments (including recipients')
5. All environments get new credentials

Recipients (alice & bob):
- Their environments automatically updated by owner
- Or they can manually rebuild later if owner skipped them
```

### Scenario 6: Partial Rebuild Failure

```
1. User rebuilds 5 environments
2. 3 succeed (Docker build completes)
3. 2 fail (e.g., Docker build timeout)
4. Toast: "3 succeeded, 2 failed. Check console for details."
5. Console shows specific error messages
6. Failed environments show "error" status badge
7. User investigates issues
8. User clicks "Rebuild" on failed environments individually
9. Retry succeeds after fixing issues
```

## Security & Access Control

**Access Restrictions:**
- Only credential owner or shared users can view affected environments
- Users can only rebuild their own environments
- Shared credential users cannot rebuild other users' environments
- API keys never exposed in responses (only metadata shown)

**Validation:**
- Credential existence verified before query
- User access checked via `can_access_credential()`
- Environment ownership validated before rebuild
- 403 error if unauthorized, 404 if credential not found

## Performance Characteristics

**Database Query:**
- Single JOIN query (no N+1 problem)
- Existing indexes on credential foreign keys
- Expected response time: <50ms for typical user

**Frontend:**
- Data fetched only when dialog opens
- React Query caching prevents redundant requests
- No pagination needed (typical: 3-10 environments)

**Rebuild Execution:**
- Parallel execution (non-blocking)
- Async Docker operations
- WebSocket progress updates (no polling)
- No hard timeout (long builds supported)

## Error Handling

**Backend Errors:**
- `403 Forbidden` - User not authorized
- `404 Not Found` - Credential doesn't exist
- `500 Internal Server Error` - Database failure (logged)

**Frontend Errors:**
- Network failure: Error toast, can retry by reopening dialog
- Partial rebuild failures: Shows success/failure counts
- Empty list: Not treated as error (shows empty state)

**Rebuild Errors:**
- Docker build failure: Environment marked "error", logged
- Missing dependencies: Error message shown
- Container start failure: WebSocket error event emitted

## Related Components

**See Also:**
- `docs/business-domain/ai_credentials_management.md` - AI credentials core management
- `docs/agent-sessions/agent_env_docker.md` - Environment rebuild mechanics
- `docs/business-domain/shared_agents_management.md` - Credential sharing behavior

---

**Document Version:** 1.0
**Created:** 2026-01-29
**Component Type:** Widget (Dialog + Backend API)
**Status:** Implemented
