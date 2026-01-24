# Input Task Management - Implementation Reference

## Purpose

Enable users to receive, refine, and execute incoming tasks through an AI-assisted preparation workflow. Tasks often arrive with incomplete information - this feature provides a structured way to transform vague requests into detailed, agent-ready instructions before execution.

## Feature Overview

**Flow (User-Initiated):**
1. User creates new task (manual entry or external source)
2. User opens task refinement screen with split view
3. Left panel: Task description editor + agent selector + execute button + sessions list
4. Right panel: AI refinement chat interface
5. User sends refinement comments → AI refines description and provides feedback
6. User reviews, continues refining, or clicks Execute
7. On Execute: system creates session linked to task via `source_task_id`
8. User can execute same task multiple times (creates additional sessions)
9. Task status syncs with session state (running, pending_input, completed, error)
10. User archives completed tasks to clear from active view

**Flow (Agent-Initiated via Direct Handover):**
1. Source agent triggers `create_agent_task` tool with target agent specified
2. System creates InputTask with `agent_initiated=true`, `auto_execute=true`
3. If target agent has `refiner_prompt`, message is auto-refined
4. System auto-creates session and sends the (possibly refined) message
5. Task appears in Tasks list with `agent_initiated` flag
6. Task status syncs with session state as usual

**Flow (Agent-Initiated via Inbox Task):**
1. Source agent triggers `create_agent_task` tool WITHOUT target agent
2. System creates InputTask with `agent_initiated=true`, `auto_execute=false`
3. Task appears in user's inbox with status `NEW`
4. User reviews task, optionally refines description
5. User selects appropriate agent
6. User executes task when ready
7. Task status syncs with session state as usual

**Flow (Session State Reporting & Bi-Directional Feedback):**
1. Target agent finishes processing → calls `update_session_state(state, summary)`
2. Session's `result_state` and `result_summary` are updated
3. `SESSION_STATE_UPDATED` event emitted for real-time frontend updates
4. Activity created for offline notification (type depends on state)
5. If task has `auto_feedback=true` → feedback message sent to source session
6. Source agent receives feedback → auto-responds or escalates to user
7. Source agent can reply via `respond_to_task(task_id, message)` → resets session state, resumes target

## Architecture

```
Frontend UI → Backend API → AI Functions → Session Service
(React)       (FastAPI)     (LLM Refiner)  (Creates Sessions)

Task (1) ─────────────> (N) Session
       session_id            source_task_id
       (latest/primary)      (authoritative FK)

Bi-Directional Feedback:
Source Session ──create_agent_task──> Task ──execute──> Target Session
       ↑                                                      │
       └──── deliver_feedback_to_source ◄── update_session_state
              (user message + initiate_stream)    (result_state + summary)
```

**Key Relationships:**
- A single task can spawn multiple sessions (retries, re-runs). The `Session.source_task_id` field links sessions back to their originating task.
- Tasks created by agents have `source_session_id` linking back to the creating session, enabling feedback delivery.

## Data/State Lifecycle

### Task Status States

| Status | Description | User Action |
|--------|-------------|-------------|
| `new` | Task created, not yet refined | Refine or Execute |
| `refining` | User actively refining | Continue or Execute |
| `running` | Session active, agent working | Monitor |
| `pending_input` | Agent needs user input | Go to session |
| `completed` | Agent finished successfully | Archive |
| `error` | Agent encountered error | Review, retry, Archive |
| `archived` | User archived task | - |

### Session-to-Task Status Sync

When a task has connected sessions (via `source_task_id`), the task status automatically syncs based on session states:

**Computation Logic (priority order):**
- If ANY session has `status='error'` → task = `ERROR`
- If ANY session has unanswered `tool_questions_status='unanswered'` → task = `PENDING_INPUT`
- If ANY session is active with `interaction_status='running'` → task = `RUNNING`
- If ALL sessions are `completed` → task = `COMPLETED`
- Otherwise → task = `RUNNING` (active but not streaming)

**Status Protection:**
- Only tasks in execution phase (`running`, `pending_input`, `completed`, `error`) are synced
- Tasks in `new`, `refining`, or `archived` status are NOT overridden by session events

**Event Handlers:**
- `STREAM_STARTED` → syncs task to `RUNNING`
- `STREAM_COMPLETED` → computes and syncs status from all sessions
- `STREAM_ERROR` → syncs task to `ERROR`
- `TODO_LIST_UPDATED` → propagates session todo progress to linked task, emits `TASK_TODO_UPDATED`

**Session Deletion Reset:**
- When a session linked to a task is deleted (`DELETE /api/v1/sessions/{id}`), the system checks if any sessions remain for that task
- If ALL sessions are deleted and the task is in execution phase (`running`, `pending_input`, `completed`, `error`):
  - Task status resets to `NEW`
  - `session_id`, `todo_progress`, `error_message` are cleared
  - `executed_at`, `completed_at` timestamps are cleared
- If some sessions remain after deletion, the task status is recomputed from the remaining sessions
- Tasks in `new`, `refining`, or `archived` status are not affected by session deletion

### Session Result State

Agents can explicitly declare session outcomes via the `update_session_state` tool. This is stored on the session and propagated to linked tasks.

| result_state | Meaning | Activity Type | Source Agent Action |
|--------------|---------|---------------|---------------------|
| `null` | Session in progress | - | - |
| `completed` | Agent finished successfully | `session_completed` | Acknowledge result |
| `needs_input` | Agent needs clarification | `session_feedback_required` | Call `respond_to_task` |
| `error` | Unrecoverable issue | `error_occurred` | Retry or inform user |

**Key behaviors:**
- `result_state` is set on the `Session` model and joined to `InputTaskPublicExtended` for display
- When `result_state` is set, the generic "Session completed" activity from `handle_stream_completed` is suppressed
- The `result_summary` field contains the agent's description (result, question, or error details)
- Calling `respond_to_task` resets `result_state` to null (session back in progress)

### Auto-Feedback Mechanism

Controls whether session state changes are automatically forwarded to the source agent:

- `auto_feedback` flag on `AgentHandoverConfig` → copied to `InputTask` at task creation
- When `auto_feedback=true` and target agent calls `update_session_state`:
  - A "user" role message is created in the source session (e.g., `[Sub-task completed] Done processing`)
  - If source session is idle, agent processing is triggered automatically
  - If source session is streaming, message stays pending until current stream ends
- `feedback_delivered` flag prevents duplicate delivery

### Refinement History Structure

Stored as JSON array in `InputTask.refinement_history`:
- Each item: `{ role: "user"|"ai", content: string, timestamp: ISO8601 }`
- Append-only for audit trail
- Last 5 items passed as context to AI refiner

### Todo Progress Tracking

When an agent uses the TodoWrite tool during execution, the progress is tracked for real-time display:

**Data Structure** (stored in `Session.todo_progress` and `InputTask.todo_progress`):
```json
[
  {"content": "Run the build", "activeForm": "Running the build", "status": "completed"},
  {"content": "Fix type errors", "activeForm": "Fixing type errors", "status": "in_progress"},
  {"content": "Update tests", "activeForm": "Updating tests", "status": "pending"}
]
```

**Event Flow:**
1. Agent calls TodoWrite tool during message processing
2. `MessageService.stream_message_with_events()` detects the tool call
3. Session's `todo_progress` is updated in database
4. `TODO_LIST_UPDATED` event is emitted with session_id and todos
5. `InputTaskService.handle_todo_list_updated()` handler:
   - Checks if session is linked to a task via `source_task_id`
   - Saves todos to task's `todo_progress` for persistence
   - Emits `TASK_TODO_UPDATED` event for frontend real-time updates

**Frontend Display:**
- `TaskTodoProgress` component shows horizontal progress indicator
- Each todo is a circle (pending), spinning loader (in_progress), or checkmark (completed)
- Tooltip shows full task content on hover
- Current in-progress step shown as text hint

## Database Schema

**Migrations:**
- `backend/app/alembic/versions/l2g3h4i5j6k7_add_input_task_table.py` - Creates `input_task` table, adds `source_task_id` to `session`
- `backend/app/alembic/versions/o5j6k7l8m9n0_add_agent_initiated_fields_to_input_task.py` - Adds agent handover fields
- `backend/app/alembic/versions/p6k7l8m9n0o1_add_todo_progress_to_session.py` - Adds `todo_progress` JSON field to session and input_task tables
- `backend/app/alembic/versions/u1p2q3r4s5t6_add_session_state_and_task_feedback.py` - Adds `result_state`/`result_summary` to session, `auto_feedback`/`feedback_delivered` to input_task, `auto_feedback` to agent_handover_config

**Models:** `backend/app/models/input_task.py`
- `InputTask` - Database table with:
  - Core fields: owner_id, original_message, current_description, status
  - Agent fields: selected_agent_id, session_id, user_workspace_id
  - **Agent-initiated fields**: `agent_initiated` (bool), `auto_execute` (bool), `source_session_id` (UUID, FK to session)
  - **Feedback control**: `auto_feedback` (bool, default=True), `feedback_delivered` (bool, default=False)
  - History: refinement_history (JSON array)
  - **Todo progress**: `todo_progress` (JSON array) - Tracks TodoWrite tool progress from agent execution
  - Timestamps: created_at, updated_at, executed_at, completed_at, archived_at
- `InputTaskCreate`, `InputTaskUpdate` - API input schemas (Create includes agent_initiated, auto_execute, source_session_id)
- `InputTaskPublic`, `InputTaskPublicExtended` - API response schemas (extended includes agent_name, result_state, result_summary)
- `RefineTaskRequest`, `RefineTaskResponse` - Refinement action schemas
- `ExecuteTaskRequest`, `ExecuteTaskResponse` - Execution action schemas
- `InputTaskStatus` - Status enum constants

**Session Model Update:** `backend/app/models/session.py`
- Added `source_task_id: uuid.UUID | None` with FK to `input_task.id`
- Added `todo_progress: list | None` (JSON) - Stores TodoWrite tool progress during agent execution
- Added `result_state: str | None` - Agent-declared outcome ("completed", "needs_input", "error")
- Added `result_summary: str | None` - Agent's description of result/question/error
- All fields included in `SessionPublic` schema

**Handover Config Update:** `backend/app/models/agent_handover.py`
- Added `auto_feedback: bool = True` to `AgentHandoverConfig` - Controls automatic feedback delivery
- Added `UpdateSessionStateRequest`, `UpdateSessionStateResponse` - Session state endpoint schemas
- Added `RespondToTaskRequest` - Task response endpoint schema

## Backend Implementation

### API Routes

**File:** `backend/app/api/routes/input_tasks.py`

**Architecture:** Routes are thin controllers that delegate to `InputTaskService` methods. Service exceptions (`InputTaskError` subclasses) are converted to HTTP exceptions via `_handle_service_error()`.

**CRUD Operations:**
- `POST /api/v1/tasks` - Create new task (uses `verify_agent_access`, `create_task`)
- `GET /api/v1/tasks` - List tasks with status filter (uses `list_tasks_extended`)
- `GET /api/v1/tasks/{id}` - Get single task with agent name (uses `get_task_extended`)
- `PATCH /api/v1/tasks/{id}` - Update task (uses `get_task_with_ownership_check`, `verify_agent_access`, `update_task`)
- `DELETE /api/v1/tasks/{id}` - Delete task (uses `get_task_with_ownership_check`, `delete_task`)

**Actions:**
- `POST /api/v1/tasks/{id}/refine` - Refine with AI (uses `get_task_with_ownership_check`, `refine_task`)
- `POST /api/v1/tasks/{id}/execute` - Execute task (uses `get_task_with_ownership_check`, `execute_task_sync`)
- `POST /api/v1/tasks/{id}/archive` - Archive task (uses `get_task_with_ownership_check`, `update_status`)
- `GET /api/v1/tasks/{id}/sessions` - List sessions (uses `get_task_with_ownership_check`, `SessionService.list_task_sessions`)

**Sub-Task Queries:**
- `GET /api/v1/tasks/by-source-session/{session_id}` - List tasks created by a source session (powers SubTasksPanel)

**Session State & Feedback (Agent-Env Routes):**

**File:** `backend/app/api/routes/agents.py`

- `POST /api/v1/agents/sessions/update-state` - Agent declares session outcome
  - Validates state ("completed"/"needs_input"/"error"), updates session fields
  - Emits `SESSION_STATE_UPDATED` event → triggers activity creation + task feedback
- `POST /api/v1/agents/tasks/respond` - Source agent responds to sub-task
  - Verifies source_session_id ownership, resets session result_state to null
  - Sends message to target session via `SessionService.send_session_message()`

**Router Registration:** `backend/app/api/main.py` - includes `input_tasks.router`

### Services

**InputTaskService:** `backend/app/services/input_task_service.py`

*Exception Classes:*
- `InputTaskError` - Base exception with message and status_code
- `TaskNotFoundError` - Task not found (404)
- `AgentNotFoundError` - Agent not found (404)
- `PermissionDeniedError` - User lacks permissions (400)
- `ValidationError` - Validation failed (400)

*Helper Methods:*
- `verify_agent_access()` - Verify agent exists and user has access, optionally require active environment
- `get_task_with_ownership_check()` - Get task and verify ownership
- `parse_status_filter()` - Parse status filter string to list of statuses
- `parse_workspace_filter()` - Parse workspace filter string to UUID and apply flag
- `get_task_extended()` - Get task with agent name and sessions info
- `list_tasks_extended()` - List tasks with extended info, handles filter parsing

*CRUD Operations:*
- `create_task()` - Create with original_message = current_description
- `get_task()`, `get_task_with_agent()` - Retrieve with optional agent name join
- `list_tasks()` - Filter by status, workspace, with pagination
- `update_task()`, `update_description()` - Modify task fields
- `update_status()` - Change status with appropriate timestamp updates
- `append_to_refinement_history()` - Add user/ai message to history
- `link_session()` - Set session_id and status to running
- `reset_task_if_no_sessions()` - Reset task to `NEW` if all linked sessions are deleted; recomputes status if sessions remain
- `delete_task()` - Remove task

*Business Logic Operations:*
- `refine_task()` - Full refinement workflow: status transition, history, AI call, update
- `execute_task_sync()` - Synchronous task execution: agent validation, session creation, linking
- `create_task_with_auto_refine()` - Creates task and auto-refines if agent has `refiner_prompt`
  - Returns `(task, message_to_send)` tuple
  - Used by agent handover flow
- `execute_task()` - Async version that creates session, links to task, sends message
  - Returns `(success, session, error)` tuple
  - Used by agent handover flow

*Session State & Feedback Methods:*
- `list_tasks_by_source_session()` - Query tasks by source_session_id, joins session result_state/result_summary
- `deliver_feedback_to_source()` - Creates user message in source session with task_feedback metadata, triggers agent processing if idle

*Event Handlers (static async methods):*
- `handle_stream_started()` - Syncs task status to RUNNING
- `handle_stream_completed()` - Computes and syncs status from all linked sessions
- `handle_stream_error()` - Syncs task status to ERROR
- `handle_todo_list_updated()` - Propagates session todo progress to linked task, emits `TASK_TODO_UPDATED` event
- `handle_session_state_updated()` - Checks auto_feedback flag, calls deliver_feedback_to_source if enabled

**SessionService Updates:** `backend/app/services/session_service.py`
- `create_session()` - Now accepts optional `source_task_id` parameter
- `list_task_sessions()` - List sessions by source_task_id
- `delete_session()` - Returns `source_task_id` of deleted session (or None) to enable task status reset

**ActivityService Updates:** `backend/app/services/activity_service.py`
- `handle_session_state_updated()` - Maps state to activity type, creates activity for offline notification
- `create_completion_activities()` - Modified to skip generic activity when `session.result_state` is already set

**AIFunctionsService:** `backend/app/services/ai_functions_service.py`
- `refine_task()` - Wrapper that fetches agent workflow_prompt and refiner_prompt, calls task refiner

### AI Function - Task Refiner

**Agent:** `backend/app/agents/task_refiner.py`
- `refine_task()` - Takes current_description, agent_workflow_prompt, user_comment, refinement_history
- Uses `get_provider_manager()` for LLM calls
- Returns `{ success, refined_description, feedback_message }` or `{ success: false, error }`

**System Prompt:** `backend/app/agents/prompts/task_refiner_prompt.md`
- Defines task refinement assistant role
- Instructions for analyzing and improving task descriptions
- JSON output format specification

**Export:** `backend/app/agents/__init__.py` - exports `refine_task`

### Agent-Env Tools (MCP Server)

**Tool:** `update_session_state` — `backend/app/env-templates/python-env-advanced/app/core/server/tools/update_session_state.py`
- Called by target agent to declare session outcome
- Parameters: `state` ("completed"/"needs_input"/"error"), `summary` (result/question/error description)
- Calls backend `POST /api/v1/agents/sessions/update-state`

**Tool:** `respond_to_task` — `backend/app/env-templates/python-env-advanced/app/core/server/tools/respond_to_task.py`
- Called by source agent to reply to sub-task clarification requests
- Parameters: `task_id`, `message`
- Calls backend `POST /api/v1/agents/tasks/respond`

**Registration:** `backend/app/env-templates/python-env-advanced/app/core/server/adapters/claude_code.py`
- Both tools registered in the `task` MCP server alongside `create_agent_task`

**PRE_ALLOWED_TOOLS:** `backend/app/services/message_service.py`
- Added `mcp__task__update_session_state`, `mcp__task__respond_to_task`

### Agent Prompts

**Task Session Prompt** (appended in `prompt_generator.py`):
- All conversation-mode sessions get "Session State Reporting" instructions
- Instructs agents to call `update_session_state` when finished, needing input, or on error

**Handover Feedback Prompt** (appended in `agent_service.py` during `sync_agent_handover_config`):
- Source agents get "Handling Sub-Task Feedback" instructions
- Describes message prefixes (`[Sub-task completed]`, `[Sub-task needs input]`, `[Sub-task error]`)
- Instructs use of `respond_to_task` tool for clarification responses

### Event Handler Registration

**File:** `backend/app/main.py`

```python
event_service.register_handler(EventType.SESSION_STATE_UPDATED, ActivityService.handle_session_state_updated)
event_service.register_handler(EventType.SESSION_STATE_UPDATED, InputTaskService.handle_session_state_updated)
```

## Frontend Implementation

### Routes

**Tasks List:** `frontend/src/routes/_layout/tasks.tsx`
- Status filter sidebar (active, completed, archived, all)
- Task cards with status badge, agent name, description preview
- Create task button → `CreateTaskDialog`
- Navigate to task detail on click
- "Go to Session" button for running tasks

**Task Detail/Refinement:** `frontend/src/routes/_layout/task/$taskId.tsx`
- Split view: left panel (description, agent, execute, sessions list), right panel (refinement chat)
- Agent selector dropdown
- Description with edit/preview toggle
- Original message display (read-only, shown when different from current)
- Execute button (changes to "Run Again" when sessions exist)
- Sessions list showing all sessions spawned by this task with status indicators
- Delete confirmation dialog

### Components

**Tasks Directory:** `frontend/src/components/Tasks/`

**TaskStatusBadge:** `frontend/src/components/Tasks/TaskStatusBadge.tsx`
- Color-coded status badges with icons for each status

**CreateTaskDialog:** `frontend/src/components/Tasks/CreateTaskDialog.tsx`
- Modal with textarea for original_message
- Optional agent selector
- Creates task and navigates to refinement page

**RefinementChat:** `frontend/src/components/Tasks/RefinementChat.tsx`
- Displays refinement_history messages (user and AI)
- Input for new refinement comments
- Calls `TasksService.refineTask()` on submit
- Shows loading state during AI processing

**TaskTodoProgress:** `frontend/src/components/Tasks/TaskTodoProgress.tsx`
- Horizontal progress indicator for agent's TodoWrite tool usage
- Shows circles for each todo item (pending/in_progress/completed)
- Tooltip on hover shows full task content
- Displays current in-progress step as text hint
- Subscribes to `TASK_TODO_UPDATED` events for real-time updates

### Sub-Tasks Panel & Session State Display

**SubTasksPanel:** `frontend/src/components/Chat/SubTasksPanel.tsx`
- Slide-out overlay from right side of chat view
- Fetches sub-tasks via `GET /api/v1/tasks/by-source-session/{sessionId}`
- Shows task cards with: state icon, agent name, status badge, original message, result summary
- Links to sub-task sessions via TanStack Router `Link`
- Real-time updates via `SESSION_STATE_UPDATED` event subscription (invalidates query)
- Polling fallback every 10 seconds

**ChatHeader Badge:** `frontend/src/components/Chat/ChatHeader.tsx`
- Badge button (ListTodo icon) showing count of sub-tasks for current session
- Only visible when sub-tasks exist (`count > 0`)
- Toggles SubTasksPanel overlay on click

**Task Feedback Messages:** `frontend/src/components/Chat/MessageBubble.tsx`
- Detects `message_metadata.task_feedback === true`
- Renders with colored left border (green=completed, amber=needs_input, red=error)
- Shows state-specific icon (CheckCircle2/HelpCircle/AlertTriangle)
- Displays task summary text

**Activity Type:** `frontend/src/routes/_layout/activities.tsx`
- Added `session_feedback_required` case → renders HelpCircle icon

**Handover Config:** `frontend/src/components/Agents/AgentHandovers.tsx`
- Auto-feedback toggle switch per handover configuration
- Controls whether source agent auto-runs when sub-tasks report state

**Event Type:** `frontend/src/services/eventService.ts`
- Added `SESSION_STATE_UPDATED: "session_state_updated"` to EventTypes

### Sidebar Integration

**File:** `frontend/src/components/Sidebar/AppSidebar.tsx`
- Added `ClipboardList` icon import
- Added Tasks menu item to `itemsAfterActivities` array: `{ icon: ClipboardList, title: "Tasks", path: "/tasks" }`

### API Client

**Generated Service:** `TasksService` in `frontend/src/client/sdk.gen.ts`
- `createTask()`, `listTasks()`, `getTask()`, `updateTask()`, `deleteTask()`
- `refineTask()`, `executeTask()`, `archiveTask()`
- `listTaskSessions()` - List sessions for a task

**Generated Types:** `frontend/src/client/types.gen.ts`
- `InputTaskPublic`, `InputTaskPublicExtended`, `InputTasksPublicExtended`
- `InputTaskCreate`, `InputTaskUpdate`
- `RefineTaskRequest`, `RefineTaskResponse`
- `ExecuteTaskRequest`, `ExecuteTaskResponse`

## Security Features

### Authorization Rules

- All task operations restricted to owner (or superuser for their own tasks)
- Agent selection validated for ownership
- Sessions inherit ownership from task owner

### Data Protection

- `original_message` immutable after creation (audit trail)
- `refinement_history` append-only (conversation audit)
- Tasks only linkable to user's own agents

### Validation

- Agent must have active environment to execute
- Task must have selected_agent_id to execute
- Status transitions validated (archived tasks cannot be re-executed without first becoming active)

## Key Integration Points

### With Agent Task Creation

Agents can create tasks via the `create_agent_task` tool in two modes:

**Direct Handover (target agent specified):**
- `AgentService.create_agent_task()` calls `InputTaskService.create_task_with_auto_refine()`
- Task is created with `agent_initiated=true`, `auto_execute=true`, `source_session_id` set
- If target agent has `refiner_prompt`, message is automatically refined
- `InputTaskService.execute_task()` creates session and sends message
- System message logged in source session with link to new session

**Inbox Task (no target agent):**
- `AgentService.create_agent_task()` calls `InputTaskService.create_task()`
- Task is created with `agent_initiated=true`, `auto_execute=false`, `source_session_id` set
- NO auto-refinement (user will refine manually)
- NO auto-execution (user will select agent and execute)
- System message logged in source session with link to task page
- Task appears in user's inbox for review and action

**Related Documentation:** `docs/agent-sessions/agent_handover_management.md`

### With Session State & Bi-Directional Feedback

Session state management enables agents to report outcomes and communicate across sessions:

**State Reporting Flow:**
1. Target agent calls `update_session_state(state, summary)` → backend updates session
2. `SESSION_STATE_UPDATED` event fires → two handlers execute:
   - `ActivityService.handle_session_state_updated()` → creates activity for user notification
   - `InputTaskService.handle_session_state_updated()` → delivers feedback to source session

**Feedback Delivery:**
- Creates message with `role="user"` and `message_metadata.task_feedback=true`
- Content prefixed: `[Sub-task completed]`, `[Sub-task needs input]`, `[Sub-task error]`
- If source session is idle (`interaction_status=""`), triggers `initiate_stream`
- If source session is streaming, message stays pending until stream ends

**Clarification Loop:**
1. Target agent: `update_session_state("needs_input", "What category?")`
2. Source agent receives feedback message → calls `respond_to_task(task_id, "Travel")`
3. Backend resets `result_state` to null, sends message to target session
4. Target agent processes response → calls `update_session_state("completed", "Done")`

### With Sessions

- Task creates session on execute via `SessionService.create_session(source_task_id=task.id)`
- Session stores `source_task_id` for backlink
- Task refinement page lists all sessions via `TasksService.listTaskSessions()`
- Task `session_id` field stores latest/primary session for quick access
- Deleting a session triggers `reset_task_if_no_sessions()`: if no sessions remain, task reverts to `NEW`

### With Agents

- Refinement uses agent's `workflow_prompt` as AI context
- Execution requires active agent environment (`agent.active_environment_id`)
- Agent selector shows user's agents with names

### With AI Functions

- `AIFunctionsService.refine_task()` orchestrates LLM call
- Uses provider manager for cascade provider selection
- Task refiner prompt provides structured output format

## File Locations Reference

**Backend - Models:**
- `backend/app/models/input_task.py`
- `backend/app/models/session.py` (source_task_id addition)
- `backend/app/models/__init__.py` (exports)

**Backend - Routes:**
- `backend/app/api/routes/input_tasks.py`
- `backend/app/api/main.py` (router registration)

**Backend - Services:**
- `backend/app/services/input_task_service.py`
- `backend/app/services/session_service.py` (create_session, list_task_sessions)
- `backend/app/services/ai_functions_service.py` (refine_task method)

**Backend - AI Function:**
- `backend/app/agents/task_refiner.py`
- `backend/app/agents/prompts/task_refiner_prompt.md`
- `backend/app/agents/__init__.py`

**Backend - Agent-Env Tools:**
- `backend/app/env-templates/python-env-advanced/app/core/server/tools/update_session_state.py`
- `backend/app/env-templates/python-env-advanced/app/core/server/tools/respond_to_task.py`
- `backend/app/env-templates/python-env-advanced/app/core/server/adapters/claude_code.py` (tool registration)
- `backend/app/env-templates/python-env-advanced/app/core/server/prompt_generator.py` (session state prompt)

**Backend - Migration:**
- `backend/app/alembic/versions/l2g3h4i5j6k7_add_input_task_table.py`
- `backend/app/alembic/versions/u1p2q3r4s5t6_add_session_state_and_task_feedback.py`

**Frontend - Routes:**
- `frontend/src/routes/_layout/tasks.tsx`
- `frontend/src/routes/_layout/task/$taskId.tsx`

**Frontend - Components:**
- `frontend/src/components/Tasks/TaskStatusBadge.tsx`
- `frontend/src/components/Tasks/CreateTaskDialog.tsx`
- `frontend/src/components/Tasks/RefinementChat.tsx`
- `frontend/src/components/Tasks/TaskTodoProgress.tsx`
- `frontend/src/components/Chat/SubTasksPanel.tsx` (sub-tasks overlay)
- `frontend/src/components/Chat/ChatHeader.tsx` (sub-tasks badge)
- `frontend/src/components/Chat/MessageBubble.tsx` (task feedback rendering)
- `frontend/src/components/Agents/AgentHandovers.tsx` (auto-feedback toggle)
- `frontend/src/components/Sidebar/AppSidebar.tsx`

**Frontend - Client (auto-generated):**
- `frontend/src/client/sdk.gen.ts`
- `frontend/src/client/types.gen.ts`

---

**Document Version:** 2.7
**Last Updated:** 2026-01-24
**Status:** Implementation Complete

**Changes in v2.7:**
- Added session deletion reset: when all sessions are deleted from a task, task reverts to `NEW` status
- `SessionService.delete_session()` now returns `source_task_id` of the deleted session
- Added `InputTaskService.reset_task_if_no_sessions()` method for post-deletion status management
- Session delete route (`DELETE /api/v1/sessions/{id}`) now triggers task status check after deletion
- If partial sessions remain, task status is recomputed from remaining sessions

**Changes in v2.6:**
- Added session state management: agents can declare outcomes via `update_session_state` tool
- Added `result_state`/`result_summary` fields to Session model
- Added `auto_feedback`/`feedback_delivered` fields to InputTask model
- Added `auto_feedback` field to AgentHandoverConfig model
- Added `SESSION_STATE_UPDATED` event type with handlers in ActivityService and InputTaskService
- Added bi-directional agent communication: `deliver_feedback_to_source()` sends messages to source session
- Added `respond_to_task` agent-env tool for source agent replies to sub-task clarifications
- Added `POST /agents/sessions/update-state` and `POST /agents/tasks/respond` endpoints
- Added `GET /tasks/by-source-session/{session_id}` endpoint for SubTasksPanel
- Added SubTasksPanel frontend component with real-time state updates
- Added ChatHeader sub-tasks badge, MessageBubble task feedback rendering
- Added auto-feedback toggle in AgentHandovers UI
- Added session state reporting prompt to all conversation-mode agents
- Migration: `u1p2q3r4s5t6_add_session_state_and_task_feedback.py`

**Changes in v2.5:**
- Added inbox task flow: agents can now create tasks without specifying target agent
- Updated agent tool name from `agent_handover` to `create_agent_task`
- Inbox tasks created with `auto_execute=false` for user review
- System messages now link to task page for inbox tasks (vs session for direct handover)
- Updated integration points documentation to cover both modes

**Changes in v2.4:**
- Added `todo_progress` JSON field to Session and InputTask models for TodoWrite tool tracking
- Added `TODO_LIST_UPDATED` and `TASK_TODO_UPDATED` event types
- Added `InputTaskService.handle_todo_list_updated()` event handler for propagating session todos to tasks
- Added `TaskTodoProgress` frontend component for real-time progress display
- Tasks list now subscribes to `TASK_TODO_UPDATED` events for live updates
- Migration: `p6k7l8m9n0o1_add_todo_progress_to_session.py`

**Changes in v2.3:**
- Refactored routes to be thin controllers delegating to service layer
- Added exception classes: `InputTaskError`, `TaskNotFoundError`, `AgentNotFoundError`, `PermissionDeniedError`, `ValidationError`
- Added helper methods: `verify_agent_access()`, `get_task_with_ownership_check()`, `parse_status_filter()`, `parse_workspace_filter()`
- Added high-level methods: `get_task_extended()`, `list_tasks_extended()`, `refine_task()`, `execute_task_sync()`
- Removed code duplication for ownership/agent verification across routes

**Changes in v2.2:**
- Added agent-initiated task fields: `agent_initiated`, `auto_execute`, `source_session_id`
- Added `create_task_with_auto_refine()` method for task creation with auto-refinement
- Added `execute_task()` method for task execution (session creation + message sending)
- Agent handovers now create tasks instead of sessions directly
- Tasks created by handovers are auto-refined if target agent has `refiner_prompt`

**Changes in v2.1:**
- Removed `ready` status from lifecycle (redundant with `refining`)
- Added session-to-task status sync via event handlers
- Task status now automatically updates based on connected session states
