# Agent Session Recovery

## Purpose

Defines how sessions recover from lost SDK connections (e.g., after agent-env container rebuild), allowing users to continue conversations without losing context.

## Feature Overview

**Problem:** When an agent-env Docker container is rebuilt, the SDK session (`external_session_id`) is lost. The next user message fails because the backend tries to resume a non-existent SDK session, producing a system error message. Users have no way to recover — they must create a new session and lose all context.

**Solution:** A "Recover Session" button appears on all system error messages. It marks the session for recovery. If the last user message was followed by a system error (the typical failure pattern), the backend automatically re-queues and resends that message — no duplicate message is created. The user clicks one button and the conversation seamlessly continues. Otherwise, the user sends a new message manually. The backend creates a fresh SDK session with conversation history prepended (invisible to the user in the UI, but providing context to the agent). A "Session recovered" system message is always added to the chat.

**Flow (auto-resend — typical case):**
1. SDK session is lost (container rebuild, crash, etc.)
2. User sends a message → system error message appears in chat
3. User clicks "Recover Session" button on the error message
4. Confirmation modal shows "Recover & Resend" — explains the last message will be automatically resent
5. User confirms → backend clears SDK metadata, sets `recovery_pending` flag, resets the failed user message to `pending`, and adds a "Session recovered" system message
6. Backend calls `initiate_stream()` which re-processes the existing user message with recovery context prepended
7. Agent-env creates a fresh SDK session (since `external_session_id` is cleared)
8. Agent responds with awareness of previous context

**Flow (manual — no failed message detected):**
1. User clicks "Recover Session" on any system error
2. Modal shows "Recover Session" — tells user to send a new message after recovery
3. User confirms → backend clears SDK metadata, sets `recovery_pending` flag, and adds a "Session recovered" system message
4. User sends a new message manually → backend prepends conversation history
5. Agent-env creates a fresh SDK session

## Architecture

```
Error Message → Recover Button → API Call → Mark Recovery + Reset Message + System Message → initiate_stream (if resendable) → Context Injected → Fresh SDK Session
(frontend)      (frontend)        (backend)  (backend/DB)                                     (backend)                          (backend)          (agent-env)
```

**Key Design Decisions:**
- Recovery context is injected into the message content sent to agent-env only — the original user message in the DB is NOT modified
- The UI shows only the user's original message (recovery context is invisible)
- The `recovery_pending` flag is consumed once on the next message, then cleared
- Recovery is idempotent — clicking "Recover Session" multiple times is harmless
- Auto-resend is fully backend-driven: the backend detects the failed-message pattern, resets the existing user message to `pending`, and triggers `initiate_stream()` — no duplicate user message is created
- Frontend detects the same pattern for UI purposes only (button text and toast message)
- A "Session recovered" system message is always inserted into the chat history

## Data Flow

### Session Metadata Changes

| Field | Before Recovery | After `mark_session_for_recovery()` | After Next Message |
|-------|----------------|--------------------------------------|-------------------|
| `external_session_id` | `"sdk-123"` | removed | new value from agent-env |
| `sdk_type` | `"claude"` | removed | new value from agent-env |
| `last_sdk_message_id` | `"msg-456"` | removed | new value from agent-env |
| `recovery_pending` | absent | `true` | removed |
| `status` | `"error"` / any | `"active"` | `"active"` |

### Failed User Message Reset

When the backend detects the failed-message pattern (trailing system errors followed by a user message), it resets the existing user message:

| Field | Before Recovery | After `mark_session_for_recovery()` |
|-------|----------------|--------------------------------------|
| `sent_to_agent_status` | `"sent"` | `"pending"` |

This allows `process_pending_messages()` to pick it up and re-send it without creating a duplicate.

### Recovery Context Format

Prepended to the user's message content (sent to agent-env only):

```
[SESSION RECOVERY]
Previous conversation history:
User: <full message content>
Assistant: <full message content>
...
[END SESSION RECOVERY]
Please continue the conversation. The user's new message follows:

<actual user message>
```

**Limits:** Last 20 messages, full content (no truncation). System messages are excluded.

### Auto-Resend Detection

Both the backend and frontend independently detect the failed-message pattern by walking backwards from the end of the messages list:
1. Skip all trailing system error messages (`role === "system" && status === "error"`)
2. If the next message is a user message (`role === "user"`), it is the "failed message"
3. **Backend**: resets the message's `sent_to_agent_status` to `"pending"` and calls `initiate_stream()`
4. **Frontend**: adapts UI — shows "Recover & Resend" button text and resend toast (purely cosmetic, no message creation)

## Backend Implementation

### Services

**Session Service:** `backend/app/services/session_service.py`
- `mark_session_for_recovery()` — Clears SDK metadata, sets `recovery_pending = True`, resets status to `active`. Detects failed-message pattern and resets the existing user message to `sent_to_agent_status = "pending"`. Returns `bool` indicating whether a resendable message was found.

**Message Service:** `backend/app/services/message_service.py`
- `build_recovery_context()` — Fetches last 20 messages, filters to user/agent only, formats as recovery block with full message content
- `process_pending_messages()` — Checks `recovery_pending` flag, prepends recovery context to concatenated content, clears flag

### API Endpoint

**Route:** `backend/app/api/routes/sessions.py`
- `POST /api/v1/sessions/{id}/recover` (async) — Validates ownership, calls `mark_session_for_recovery()`, creates a "Session recovered" system message. If a resendable message was found, calls `SessionService.initiate_stream()` to trigger background streaming.

## Frontend Implementation

### Components

**RecoverSessionModal:** `frontend/src/components/Chat/RecoverSessionModal.tsx`
- Radix UI Dialog with explanation of recovery behavior
- Uses `hasFailedUserMessage()` to detect the failed-message pattern from the React Query cache (for UI display only)
- Adapts UI based on detection: "Recover & Resend" button vs "Recover Session" button
- Calls `SessionsService.recoverSession()` via `useMutation`
- On success with auto-resend detected: shows resend toast
- On success without auto-resend: shows standard recovery toast
- Does NOT create or send any messages — the backend handles resending entirely

**MessageBubble:** `frontend/src/components/Chat/MessageBubble.tsx`
- Shows "Recover Session" button on all system error messages (`isSystemError && sessionId`)
- Renders `RecoverSessionModal` when button is clicked

**MessageList:** `frontend/src/components/Chat/MessageList.tsx`
- Passes `sessionId` prop through to all `MessageBubble` instances

**Session Route:** `frontend/src/routes/_layout/session/$sessionId.tsx`
- Passes `sessionId` from route params to `MessageList`

### Generated Client

`SessionsService.recoverSession()` in `frontend/src/client/sdk.gen.ts` — auto-generated from OpenAPI spec.

## File Locations Reference

**Backend:**
- `backend/app/services/session_service.py` — `mark_session_for_recovery()`
- `backend/app/services/message_service.py` — `build_recovery_context()`, injection in `process_pending_messages()`
- `backend/app/api/routes/sessions.py` — `POST /{id}/recover` endpoint

**Frontend:**
- `frontend/src/components/Chat/RecoverSessionModal.tsx`
- `frontend/src/components/Chat/MessageBubble.tsx`
- `frontend/src/components/Chat/MessageList.tsx`
- `frontend/src/routes/_layout/session/$sessionId.tsx`

---

**Document Version:** 1.2
**Last Updated:** 2026-02-21
**Status:** Implemented
**Related Documents:**
- `docs/agent-sessions/agent_env_data_management.md` — Data management and environment lifecycle
- `docs/agent-sessions/agent_env_docker.md` — Docker architecture and lifecycle
