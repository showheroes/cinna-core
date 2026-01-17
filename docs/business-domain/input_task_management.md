# Input Task Management - Implementation Reference

## Purpose

Enable users to receive, refine, and execute incoming tasks through an AI-assisted preparation workflow. Tasks often arrive with incomplete information - this feature provides a structured way to transform vague requests into detailed, agent-ready instructions before execution.

## Business Goal

Many real-world tasks arrive with missing context that only the user knows. For example:
- "Send me a report about employees" - which employees? what format? what time period?
- "Generate sales analysis" - which products? which regions? what metrics?

The Input Task Management feature bridges this gap by:
1. Capturing incoming task requests (from external systems, manual entry, or other sources)
2. Providing an interactive refinement interface with AI assistance
3. Allowing users to iteratively clarify details in conversation with an AI refiner
4. Creating properly scoped agent sessions only when the task is fully specified
5. Tracking task lifecycle from creation to completion/archival

## Feature Overview

**High-Level Flow:**
```
Task Created → Refinement Screen → AI-Assisted Preparation → Execute → Session Created → Monitor → Complete/Archive
```

**Detailed Flow:**
1. User creates new task (manual entry or external source)
2. User opens task refinement screen
3. Screen displays:
   - Current task description (editable, with markdown preview toggle)
   - Agent selector (which agent will execute this task)
   - Refinement chat input for iterative improvements
4. User sends refinement comments → AI Function processes:
   - Current task description
   - Selected agent's workflow prompt (context for what agent can do)
   - User's refinement comments
   - Conversation history of previous refinement exchanges
5. AI returns:
   - Refined task description (updated version)
   - Feedback message (response to user's comments, clarifying questions)
6. User reviews, continues refining, or approves
7. On "Execute": system creates session with refined task, redirects to session
8. Session runs (user can leave - continues in background)
9. Task status updates based on session state:
   - `running` → agent is working
   - `pending_input` → agent needs user response (questions, tool approval)
   - `completed` → agent finished successfully
   - `error` → agent encountered an error
10. User reviews completed task, clicks "Archive" to clear from active view

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Frontend                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  Tasks List Page          Task Refinement Page          Session Page        │
│  ┌─────────────────┐      ┌──────────────────────┐     ┌──────────────────┐│
│  │ New/Running/    │      │ Task Description     │     │ Agent Session    ││
│  │ Pending/Done    │─────▶│ (Edit/Preview)       │────▶│ (Execution)      ││
│  │ Tasks           │      │                      │     │                  ││
│  │                 │      │ Agent Selector       │     │                  ││
│  │ [+New Task]     │      │                      │     │                  ││
│  │                 │      │ Refinement Chat      │     │                  ││
│  │ [Go to Session] │      │ ┌────────────────┐   │     │                  ││
│  │ [View Original] │      │ │ AI Feedback    │   │     │                  ││
│  └─────────────────┘      │ │ ────────────── │   │     └──────────────────┘│
│                           │ │ User Input     │   │                         │
│                           │ └────────────────┘   │                         │
│                           │                      │                         │
│                           │ [Execute Task]       │                         │
│                           └──────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Backend API                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  /api/v1/tasks/*                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ CRUD Operations          Refinement              Execution           │   │
│  │ - Create task            - POST /refine          - POST /execute     │   │
│  │ - List tasks             - AI Function call      - Create session    │   │
│  │ - Get task               - Update description    - Link task ↔ sess  │   │
│  │ - Update task            - Append history        - Redirect          │   │
│  │ - Archive task                                                       │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           AI Functions Service                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Task Refiner Agent                                                         │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │ Inputs:                          Outputs:                            │   │
│  │ - System prompt (refiner role)   - refined_prompt: string           │   │
│  │ - Current task description       - feedback_message: string         │   │
│  │ - Agent workflow prompt          - success: boolean                 │   │
│  │ - User comment                   - error: string (if failed)        │   │
│  │ - Refinement history                                                 │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Data Flow - Refinement:**
```
User Comment
     │
     ▼
┌─────────────────────────────────────────┐
│ POST /api/v1/tasks/{id}/refine          │
│                                         │
│ Body: { comment: string, agent_id: UUID }│
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ TaskService.refine_task()               │
│                                         │
│ 1. Load task (current description,      │
│    refinement_history)                  │
│ 2. Load agent (workflow_prompt)         │
│ 3. Call AI Function                     │
│ 4. Update task with new description     │
│ 5. Append to refinement_history         │
│ 6. Return feedback to user              │
└─────────────────────────────────────────┘
     │
     ▼
{ refined_prompt, feedback_message }
```

**Data Flow - Execution:**
```
Execute Button
     │
     ▼
┌─────────────────────────────────────────┐
│ POST /api/v1/tasks/{id}/execute         │
│                                         │
│ Body: { agent_id: UUID }                │
└─────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────┐
│ TaskService.execute_task()              │
│                                         │
│ 1. Create session for agent             │
│ 2. Send initial message (refined task)  │
│ 3. Link task.session_id                 │
│ 4. Update task.status = 'running'       │
│ 5. Return session URL                   │
└─────────────────────────────────────────┘
     │
     ▼
Redirect to /session/{session_id}
```

## Data/State Lifecycle

### Task Status States

| Status | Description | User Action |
|--------|-------------|-------------|
| `new` | Task created, not yet refined or executed | Refine or Execute |
| `refining` | User is actively refining the task | Continue refining or Execute |
| `running` | Session created, agent is working | Monitor, wait |
| `pending_input` | Agent needs user input (questions, approvals) | Go to session, respond |
| `completed` | Agent finished successfully | Review, Archive |
| `error` | Agent encountered an error | Review, retry, or Archive |
| `archived` | User archived the task | - |

### Status Transitions

```
           ┌─────────┐
           │   new   │
           └────┬────┘
                │
    ┌───────────┼───────────┐
    │           │           │
    ▼           │           ▼
┌─────────┐     │     ┌───────────┐
│refining │─────┼────▶│  running  │
└─────────┘     │     └─────┬─────┘
                │           │
                │     ┌─────┴─────────┐
                │     │               │
                │     ▼               ▼
                │ ┌─────────┐   ┌───────────────┐
                │ │  error  │   │ pending_input │
                │ └────┬────┘   └───────┬───────┘
                │      │               │
                │      ▼               ▼
                │ ┌─────────┐   ┌───────────┐
                │ │archived │◀──│ completed │
                │ └─────────┘   └───────────┘
                │      ▲               │
                │      │               │
                │      └───────────────┘
                │
                └──────────▶ (can execute at any point)
```

### Refinement History Structure

Store refinement conversation in JSON field:

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Also include data for Q4 2025",
      "timestamp": "2026-01-17T10:30:00Z"
    },
    {
      "role": "assistant",
      "content": "I've updated the task to include Q4 2025 data. Should I also include year-over-year comparisons?",
      "timestamp": "2026-01-17T10:30:05Z"
    },
    {
      "role": "user",
      "content": "Yes, add YoY comparison",
      "timestamp": "2026-01-17T10:31:00Z"
    },
    {
      "role": "assistant",
      "content": "Done. The task now requests a report with Q4 2025 data including year-over-year comparisons.",
      "timestamp": "2026-01-17T10:31:03Z"
    }
  ]
}
```

## Database Schema

### New Model: InputTask

**File:** `backend/app/models/input_task.py`

```
InputTask (table)
├── id: UUID (PK)
├── owner_id: UUID (FK → User)
├── original_message: str         # Immutable original task text
├── current_description: str      # Refined task description (editable)
├── status: str                   # new, refining, running, pending_input, completed, error, archived
├── selected_agent_id: UUID (FK → Agent, nullable)  # Agent chosen for execution
├── session_id: UUID (FK → Session, nullable)       # Created session (after execute)
├── refinement_history: JSON      # Conversation history for refinement
├── created_at: datetime
├── updated_at: datetime
├── executed_at: datetime (nullable)
├── completed_at: datetime (nullable)
├── archived_at: datetime (nullable)
├── error_message: str (nullable) # Error details if status=error
```

**Pydantic Schemas:**
- `InputTaskBase` - Shared fields
- `InputTaskCreate` - For creating new task (original_message required)
- `InputTaskUpdate` - For updating (current_description, status, selected_agent_id)
- `InputTaskPublic` - API response model
- `InputTasksPublic` - List response with pagination

### Migration

Create migration: `backend/app/alembic/versions/xxxx_add_input_task_model.py`

- Create `input_task` table
- Add foreign keys: `owner_id` → users, `selected_agent_id` → agents, `session_id` → sessions
- Add index on `owner_id` and `status` for efficient listing

## Backend Implementation

### Routes

**File:** `backend/app/api/routes/input_tasks.py`

**CRUD Operations:**
```
POST   /api/v1/tasks              # Create new task
GET    /api/v1/tasks              # List tasks (with status filter)
GET    /api/v1/tasks/{id}         # Get single task
PATCH  /api/v1/tasks/{id}         # Update task (description, agent)
DELETE /api/v1/tasks/{id}         # Delete task
```

**Refinement:**
```
POST   /api/v1/tasks/{id}/refine  # Refine task with AI
Body: { comment: string, agent_id: UUID }
Response: { refined_prompt: string, feedback_message: string }
```

**Execution:**
```
POST   /api/v1/tasks/{id}/execute # Execute task (create session)
Body: { agent_id: UUID }
Response: { session_id: UUID, redirect_url: string }
```

**Archival:**
```
POST   /api/v1/tasks/{id}/archive # Archive completed task
```

**Listing with filters:**
```
GET    /api/v1/tasks?status=new,running,pending_input  # Filter by status
GET    /api/v1/tasks?status=archived                    # View archived
```

### Service Layer

**File:** `backend/app/services/input_task_service.py`

**Key Methods:**

```python
class InputTaskService:
    @staticmethod
    def create_task(session: Session, user: User, message: str) -> InputTask:
        """Create new task from original message."""

    @staticmethod
    def refine_task(
        session: Session,
        task: InputTask,
        comment: str,
        agent_id: UUID
    ) -> RefineResult:
        """
        Refine task using AI Function.

        1. Load agent's workflow_prompt
        2. Build prompt with system instructions, current description,
           agent context, refinement history, and user comment
        3. Call AI Function (task_refiner)
        4. Parse response (refined_prompt, feedback_message)
        5. Update task.current_description
        6. Append exchange to refinement_history
        7. Return feedback to display
        """

    @staticmethod
    def execute_task(
        session: Session,
        task: InputTask,
        agent_id: UUID,
        user: User
    ) -> ExecuteResult:
        """
        Execute task by creating agent session.

        1. Create new session for agent (conversation mode)
        2. Send task.current_description as initial message
        3. Link session to task (task.session_id)
        4. Update task.status = 'running'
        5. Return session info for redirect
        """

    @staticmethod
    def update_status_from_session(session: Session, task: InputTask) -> None:
        """
        Sync task status from linked session state.
        Called by session event handlers.

        Session states → Task status:
        - Session has pending questions/approvals → 'pending_input'
        - Session completed successfully → 'completed'
        - Session errored → 'error'
        """

    @staticmethod
    def archive_task(session: Session, task: InputTask) -> InputTask:
        """Mark task as archived."""
```

### AI Function - Task Refiner

**File:** `backend/app/agents/task_refiner.py`

**System Prompt Template:** `backend/app/agents/prompts/task_refiner_prompt.md`

The system prompt should instruct the LLM to:
1. Act as a task preparation assistant
2. Understand the target agent's capabilities (from workflow_prompt)
3. Help user clarify and complete the task description
4. Ask specific questions about missing details
5. Return structured JSON with refined_prompt and feedback_message

**Implementation Pattern:**
```python
def refine_task(
    current_description: str,
    agent_workflow_prompt: str,
    user_comment: str,
    refinement_history: list[dict]
) -> dict:
    """
    Refine task description based on user feedback.

    Returns:
        {
            "success": true,
            "refined_prompt": "Updated task description...",
            "feedback_message": "I've added X. Do you also want Y?"
        }
    """
```

**Prompt Structure:**
```
[System Prompt - Task Refiner Role]

## Agent Capabilities
{agent_workflow_prompt}

## Current Task Description
{current_description}

## Refinement History
{formatted_history}

## User's Latest Comment
{user_comment}

---
Return JSON: { "refined_prompt": "...", "feedback_message": "..." }
```

### Session Status Sync

**Integration Point:** When session state changes (via WebSocket events or polling), update linked task status.

**File:** Extend existing session event handlers or add to `backend/app/services/session_service.py`

Monitor for:
- Session has `questions_pending` or `tools_pending` → task status = `pending_input`
- Session completed → task status = `completed`
- Session error → task status = `error`

This can be implemented via:
1. WebSocket event handler in backend that checks for linked task
2. Periodic sync job
3. Session status change hooks in SessionService

## Frontend Implementation

### Routes

**Tasks List Page:** `frontend/src/routes/_layout/tasks.tsx`
- Lists all tasks with status filters (tabs or dropdown)
- Create new task button → modal with text input
- Each task row shows: title (truncated), status badge, agent name, timestamps
- Action buttons: Go to Session (if exists), View Original Message, Archive

**Task Refinement Page:** `frontend/src/routes/_layout/task/$taskId.tsx`
- Task description editor (textarea with markdown preview toggle)
- Agent selector dropdown
- Refinement chat interface
- Execute button

### Components Structure

```
frontend/src/components/Tasks/
├── TasksList.tsx                 # Main tasks list component
├── TaskCard.tsx                  # Individual task row/card
├── TaskStatusBadge.tsx           # Status badge with color coding
├── CreateTaskDialog.tsx          # Modal for creating new task
├── ViewOriginalDialog.tsx        # Modal to view original message
├── TaskRefinement/
│   ├── TaskRefinementPage.tsx    # Main refinement page container
│   ├── TaskDescriptionEditor.tsx # Editable description with preview
│   ├── AgentSelector.tsx         # Dropdown to select target agent
│   ├── RefinementChat.tsx        # Chat interface for refinement
│   ├── RefinementMessage.tsx     # Individual message in chat
│   └── ExecuteButton.tsx         # Execute task button
```

### Components Detail

**TasksList.tsx:**
- Fetches tasks with `InputTasksService.listTasks({ status: activeFilter })`
- Status filter tabs: All, New, Running, Needs Input, Completed, Archived
- Subscribe to WebSocket events for real-time status updates
- Handle create task via `CreateTaskDialog`

**TaskCard.tsx:**
- Display: original message (truncated), status badge, selected agent, timestamps
- Actions:
  - "Refine" → navigate to `/task/{id}`
  - "Go to Session" → navigate to `/session/{session_id}` (if session exists)
  - "View Original" → open `ViewOriginalDialog`
  - "Archive" → call archive endpoint (only for completed/error)

**TaskDescriptionEditor.tsx:**
- Two modes: Edit (textarea) and Preview (markdown rendered)
- Toggle button to switch modes
- Auto-save on blur or explicit save button
- Uses existing markdown rendering component

**AgentSelector.tsx:**
- Dropdown of user's agents
- Shows agent name and brief description
- Required before refinement or execution

**RefinementChat.tsx:**
- Display refinement_history messages (user and assistant)
- Input field for new comment
- Send button triggers refine API
- Shows loading state during AI processing
- Displays AI feedback_message after each refinement

**ExecuteButton.tsx:**
- Disabled until agent selected and description is non-empty
- On click: calls execute endpoint, redirects to session
- Confirmation dialog optional

### Sidebar Integration

**File:** `frontend/src/components/Sidebar/AppSidebar.tsx`

Add "Tasks" menu item after Dashboard:

```tsx
const itemsBeforeActivities: Item[] = [
  { icon: Home, title: "Dashboard", path: "/" },
  { icon: ClipboardList, title: "Tasks", path: "/tasks" },  // New
]
```

Include badge showing count of tasks needing attention (new + pending_input).

### API Client

After implementing backend routes, regenerate client:
```bash
bash scripts/generate-client.sh
```

**Expected Service:** `InputTasksService`
- `createTask()`
- `listTasks()`
- `getTask()`
- `updateTask()`
- `deleteTask()`
- `refineTask()`
- `executeTask()`
- `archiveTask()`

**Expected Types:**
- `InputTaskPublic`
- `InputTaskCreate`
- `InputTaskUpdate`
- `RefineTaskRequest`
- `RefineTaskResponse`
- `ExecuteTaskResponse`

## Security & Access Control

### Authorization Rules

| Action | Owner | Other Users | Superuser |
|--------|-------|-------------|-----------|
| Create task | Yes | - | Own tasks only |
| View task | Yes | No | Own tasks only |
| Refine task | Yes | No | Own tasks only |
| Execute task | Yes | No | Own tasks only |
| Archive task | Yes | No | Own tasks only |
| Delete task | Yes | No | Own tasks only |

### Data Protection

- `original_message` is immutable after creation (audit trail)
- `refinement_history` is append-only (conversation audit)
- Tasks can only be linked to agents owned by the same user
- Sessions created inherit ownership from task owner

### Validation

- Agent must be active and have running environment to execute
- Task must have non-empty `current_description` to execute
- `status` transitions are validated (can't go from archived to running)

## Integration Points

### With Sessions

- Task creates session on execute
- Task monitors session status for updates
- Session page shows link back to originating task (if exists)

### With Agents

- Refinement uses agent's `workflow_prompt` as context
- Execution requires active agent environment
- Agent selector shows only user's active agents

### With Activities

- Task status changes could create activity notifications
- "Task needs input" could appear in activities

### With WebSocket Events

New event types for task updates:
- `TASK_CREATED`
- `TASK_STATUS_CHANGED`
- `TASK_ARCHIVED`

Subscribe in Tasks list and Sidebar for real-time updates.

## File Locations Reference

**Backend - Model:**
- `backend/app/models/input_task.py` (new)

**Backend - Routes:**
- `backend/app/api/routes/input_tasks.py` (new)
- `backend/app/api/main.py` (register routes)

**Backend - Service:**
- `backend/app/services/input_task_service.py` (new)

**Backend - AI Function:**
- `backend/app/agents/task_refiner.py` (new)
- `backend/app/agents/prompts/task_refiner_prompt.md` (new)
- `backend/app/agents/__init__.py` (export)
- `backend/app/services/ai_functions_service.py` (add method)

**Backend - Migration:**
- `backend/app/alembic/versions/xxxx_add_input_task_model.py` (new)

**Frontend - Routes:**
- `frontend/src/routes/_layout/tasks.tsx` (new)
- `frontend/src/routes/_layout/task/$taskId.tsx` (new)

**Frontend - Components:**
- `frontend/src/components/Tasks/` (new directory)
- `frontend/src/components/Sidebar/AppSidebar.tsx` (modify)

**Frontend - Client (auto-generated):**
- `frontend/src/client/sdk.gen.ts`
- `frontend/src/client/types.gen.ts`

## Implementation Phases

| Phase | Description | Dependencies |
|-------|-------------|--------------|
| 1 | Database model & migration | - |
| 2 | Backend CRUD routes | Phase 1 |
| 3 | AI Function for refinement | Phase 1 |
| 4 | Backend refine/execute endpoints | Phase 2, 3 |
| 5 | Frontend Tasks list page | Phase 2 |
| 6 | Frontend Task refinement page | Phase 4 |
| 7 | Session status sync | Phase 4 |
| 8 | WebSocket events integration | Phase 7 |
| 9 | Sidebar integration | Phase 5 |

---

**Document Version:** 1.0
**Last Updated:** 2026-01-17
**Status:** Design Complete - Ready for Implementation
