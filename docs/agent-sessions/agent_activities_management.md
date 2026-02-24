# Agent Activities Management

## Overview

Activities are a notification/logging system that tracks important system events and agent actions. They serve as a persistent activity feed that keeps users informed about what happened in their agent ecosystem, especially when they weren't actively watching.

## Purpose & Motivation

**Problem**: Users may start long-running agent tasks and close their browser. When they return, they need to know:
- Did the session complete?
- Did the agent ask questions that need answers?
- What files were created?
- What other important events occurred?

**Solution**: Activities provide a centralized, persistent log of important events with:
- Read/unread tracking (automatically marked read after 2 seconds of visibility)
- Action-required indicators (e.g., "agent asked questions")
- Links to related sessions for quick navigation
- Agent-based filtering

## Core Concepts

### Activity Structure

Each activity has:
- **user_id**: Owner of the activity
- **session_id**: Related session (optional, for session-specific events)
- **agent_id**: Related agent (optional, for agent-specific events)
- **input_task_id**: Related input task (optional, for email task events)
- **activity_type**: Type of event (see types below)
- **text**: Human-readable description
- **action_required**: Empty string or specific action type (e.g., "answers_required")
- **is_read**: Boolean flag for read status
- **created_at**: Timestamp

### Activity Types

Current types (more can be added):
- `session_running`: Session is actively streaming (shown while session has interaction_status = "running")
- `session_completed`: Background session finished its work
- `questions_asked`: Agent returned with questions using AskUserQuestion tool
- `error_occurred`: Session encountered an error
- `email_task_incoming`: Email created a new task (action_required: "task_review_required")
- `email_task_reply_pending`: Email task completed, reply not yet sent (action_required: "reply_pending")
- `file_created`: Agent created a file (future)
- `agent_notification`: General agent notification (future)

### Read/Unread Mechanism

**Automatic Read Marking**:
- Frontend uses IntersectionObserver to track which activities are fully visible
- After 2 seconds of continuous visibility, activity is marked as read
- Batch API call marks multiple activities as read at once

**Why 2 seconds?**: Ensures user actually saw the activity, not just scrolled past it.

### Action Required System

**Purpose**: Distinguish between informational activities and those requiring user action.

**Current Action Types**:
- `""` (empty): No action needed, informational only
- `"answers_required"`: Agent asked questions, user needs to answer
- `"task_review_required"`: Email task arrived, user needs to review
- `"reply_pending"`: Email task completed, user needs to send reply

**Visual Indicators**:
- Sidebar bell icon changes color:
  - Default color: No unread activities
  - Green (primary): Unread informational activities
  - Red (destructive): Unread activities requiring action
- Activity list shows "Action required" badge for action-required items

## Implementation Architecture

### Backend

**Models** (`backend/app/models/activity.py`):
- `Activity`: Database table with all activity fields
- `ActivityCreate`: Schema for creating new activities
- `ActivityUpdate`: Schema for updating activities (mainly is_read)
- `ActivityPublic`: Public response schema
- `ActivityPublicExtended`: Includes agent name, session title, color presets
- `ActivityStats`: Contains unread_count and action_required_count

**Service** (`backend/app/services/activity_service.py`):
- `create_activity()`: Create new activity
- `list_user_activities()`: List with agent filtering, pagination, ordering
- `mark_as_read()`: Mark single activity as read
- `mark_multiple_as_read()`: Batch mark as read (used by frontend)
- `get_activity_stats()`: Get counts for sidebar indicator
- `update_activity()`: Generic update
- `delete_activity()`: Delete activity
- `find_activity_by_session_and_type()`: Find activity by session_id and activity_type
- `delete_activity_by_session_and_type()`: Delete activity by session_id and activity_type
- `find_activity_by_task_and_type()`: Find activity by input_task_id and activity_type
- `delete_activity_by_task_and_type()`: Delete activity by input_task_id and activity_type (returns deleted for event emission)

**Event Handlers** (registered in `main.py` startup):
- `handle_stream_started()`: React to STREAM_STARTED events
- `handle_stream_completed()`: React to STREAM_COMPLETED events
- `handle_stream_error()`: React to STREAM_ERROR events
- `handle_stream_interrupted()`: React to STREAM_INTERRUPTED events
- `handle_task_created()`: React to TASK_CREATED events (email task incoming activity)
- `handle_task_status_changed()`: React to TASK_STATUS_UPDATED events (manages email task activity lifecycle)

**API Routes** (`backend/app/api/routes/activities.py`):
- `POST /activities/`: Create activity
- `GET /activities/`: List activities with optional agent_id filter
- `GET /activities/stats`: Get unread/action-required counts
- `PATCH /activities/{id}`: Update activity
- `POST /activities/mark-read`: Batch mark as read
- `DELETE /activities/{id}`: Delete activity

### Frontend

**Activities Page** (`frontend/src/routes/_layout/activities.tsx`):
- Main activities list with compact card layout
- Agent filter sidebar (styled like dashboard agent selector)
- IntersectionObserver setup for auto-read tracking
- Click activity to navigate to related session or task (email task activities navigate to task page)
- Visual distinction for action-required items
- Special rendering for `session_running`: emerald background with emerald border, spinning loader icon
- Email task activities (`email_task_incoming`, `email_task_reply_pending`) use Mail icon from lucide-react

**Sidebar Integration** (`frontend/src/components/Sidebar/AppSidebar.tsx`):
- ActivitiesMenu component with bell icon
- Polls activity stats every 10 seconds
- Color-coded bell icon based on unread/action-required status
- Positioned between Dashboard and Agents menu items

## Integration Points

### Where to Create Activities

**Activities are now event-driven** (✅ Implemented):
- Location: `backend/app/services/activity_service.py` - Event handlers
- Triggered by: Streaming events from `MessageService`
- Architecture: Event bus system with `EventService.register_handler()`

**Event Handlers:**

**0. Session Running** (`handle_stream_started`):
- Triggered by: `STREAM_STARTED` event
- When: Stream starts
- Action: Creates `session_running` activity
  - `activity_type`: "session_running"
  - `text`: "Session is running"
  - `is_read`: false
- Lifecycle managed by subsequent events

**1. Session Completion** (`handle_stream_completed`):
- Triggered by: `STREAM_COMPLETED` event
- When: Stream completes successfully
- Logic:
  - **If user connected**: Deletes `session_running` activity
  - **If user disconnected**: Creates `session_completed` + `questions_asked` (if applicable)
- Uses `event_service.is_user_connected(user_id)` to check connection

**2. Questions Asked** (part of `handle_stream_completed`):
- When: Stream completes AND latest message has `tool_questions_status = "unanswered"`
- Action: Creates `questions_asked` activity
  - `activity_type`: "questions_asked"
  - `text`: "Agent asked questions that need answers"
  - `action_required`: "answers_required"
  - `is_read`: false

**3. Error Occurred** (`handle_stream_error`):
- Triggered by: `STREAM_ERROR` event
- When: Stream fails with error
- Action:
  - Deletes `session_running` activity
  - Creates `error_occurred` activity (always, even if user connected)
  - `activity_type`: "error_occurred"
  - `text`: "Error: {error_message}" (truncated to 100 chars)
  - `is_read`: false

**4. Stream Interrupted** (`handle_stream_interrupted`):
- Triggered by: `STREAM_INTERRUPTED` event
- When: User manually interrupts stream
- Action: Deletes `session_running` activity
- No completion activities (session can be resumed)

**5. Email Task Incoming** (`handle_task_created`):
- Triggered by: `TASK_CREATED` event (from `EmailProcessingService._process_email_to_task`)
- Filter: Only fires when `meta.source_email_message_id` is set
- Action: Creates `email_task_incoming` activity with `action_required="task_review_required"`
- Links to task via `input_task_id`
- Dismissed when: task is executed (status changes from "new"), archived, or deleted

**6. Email Task Reply Pending** (`handle_task_status_changed`):
- Triggered by: `TASK_STATUS_UPDATED` event (from `InputTaskService.update_status`)
- Filter: Only fires when `meta.is_email_task` is true
- On status != "new": deletes `email_task_incoming` activity
- On status == "completed": creates `email_task_reply_pending` activity with `action_required="reply_pending"`
- On status != "completed": deletes `email_task_reply_pending` if exists
- Reply pending also dismissed directly by `send_email_answer()` and task deletion

**7. File Created** (Future):
- When: Agent creates file via workspace API
- Create activity linking to file and session

**5. Agent Notifications** (Future):
- When: Agent explicitly requests to notify user
- Custom text from agent

### Integration Considerations

**Background vs Active Sessions**:
- **Background session** (user closed tab): is_read = false, user needs notification
- **Active session** (user watching): is_read = true, activity is just for history

**Detecting Active Sessions**:
- Check if session has active streaming connection
- Backend can track active connections in streaming manager
- Reference: `backend/app/services/active_streaming_manager.py`

**Session Status Tracking**:
- Session model has `status` field: "active", "completed", "error", "paused"
- Session model has `interaction_status` field: "" (default/nothing happening), "running" (active stream)
- Reference: `backend/app/models/session.py`
- `interaction_status` set to "running" when stream starts, cleared when stream completes
- Managed by `MessageService.stream_message_with_events()` in finally block
- When status changes to "completed", create activity

**Message Tool Questions**:
- Messages have `tool_questions_status` field: null, "unanswered", "answered"
- Reference: `backend/app/models/session.py` - SessionMessage model
- When message saved with unanswered questions, create activity

## Business Rules

1. **One activity per event**: Don't create duplicate activities for same event (exception: `session_running` replaced with final state)
2. **User ownership**: Activities only visible to owning user
3. **Cascade deletion**: Activities deleted when related session/agent deleted (database foreign keys)
4. **Privacy**: Activities are private, never shared between users
5. **Retention**: Activities stored indefinitely (can add cleanup later)
6. **Read state persistence**: Once marked read, stays read (no "mark as unread")
7. **Action required is immutable**: Set at creation, doesn't change
8. **Session running lifecycle**: `session_running` activity is temporary, deleted if frontend watching or replaced with final state if not
9. **Error tracking**: Error activities always created, even if frontend was watching (important for audit trail)

## Statistics & Performance

**Stats Endpoint**:
- Returns two counts: unread_count, action_required_count
- Used by sidebar to show notification indicator
- Polled every 10 seconds from frontend
- Should be optimized with database indexes on (user_id, is_read, action_required)

**Pagination**:
- Default limit: 100 activities
- Frontend currently loads all at once
- Can add infinite scroll later if needed

## Future Enhancements

1. **Activity Grouping**: Group multiple similar activities (e.g., "Agent created 5 files")
2. **Activity Preferences**: Let users choose which activity types to show
3. **Push Notifications**: Browser notifications for action-required activities
4. **Activity Search**: Search activities by text
5. **Activity Filtering**: Filter by date range, activity type, read status
6. **Mark All Read**: Bulk action to mark all as read
7. **Activity Retention**: Auto-delete old activities after N days
8. **Rich Content**: Attach file previews, diff views, etc. to activities

## Testing Considerations

When testing activities integration:
1. Test `session_running` activity created when stream starts
2. Test `session_running` deleted when stream completes with frontend watching
3. Test `session_running` replaced with `session_completed` when stream completes without frontend
4. Test `session_running` replaced with `error_occurred` when stream fails
5. Test background session completion while user not watching
6. Test active session events (frontend watching still creates error activities)
7. Test agent asking questions in background session
8. Test sidebar indicator updates correctly
9. Test clicking activity navigates to correct session
10. Test agent filtering works correctly
11. Test read/unread transitions smoothly
12. Test `session_running` shows emerald background with spinning icon
13. Test email task creates `email_task_incoming` activity on arrival
14. Test executing email task dismisses `email_task_incoming` activity
15. Test completing email task creates `email_task_reply_pending` activity
16. Test sending email reply dismisses `email_task_reply_pending` activity
17. Test archiving email task dismisses all email task activities
18. Test deleting email task emits ACTIVITY_DELETED for linked activities
19. Test clicking email task activity navigates to task page

## File Reference Summary

**Backend**:
- Models: `backend/app/models/activity.py`
- Service: `backend/app/services/activity_service.py` (includes event handlers)
- Routes: `backend/app/api/routes/activities.py`
- Event Registration: `backend/app/main.py` (on_startup)
- Migration: `backend/app/alembic/versions/*_add_activity_table.py`
- Migration: `backend/app/alembic/versions/i6d5e7f8g9h0_add_input_task_id_to_activity.py` (adds input_task_id FK)

**Frontend**:
- Page: `frontend/src/routes/_layout/activities.tsx`
- Sidebar: `frontend/src/components/Sidebar/AppSidebar.tsx`
- Client: `frontend/src/client/sdk.gen.ts` (auto-generated ActivitiesService)

**Related Context**:
- Session model: `backend/app/models/session.py` (Session with interaction_status field)
- Message model: `backend/app/models/session.py` (SessionMessage)
- Message service: `backend/app/services/message_service.py` (emits streaming events)
- Event service: `backend/app/services/event_service.py` (event bus with backend handlers)
- Event types: `backend/app/models/event.py` (EventType enum)
- Streaming manager: `backend/app/services/active_streaming_manager.py`
- Question tool block: `frontend/src/components/Chat/AskUserQuestionToolBlock.tsx`
