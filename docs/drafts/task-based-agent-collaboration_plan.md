# Task-Based Agent Collaboration — Implementation Plan

## Overview

Evolution of the existing Input Task system into a structured, Jira-like task management model
with comments, file attachments, short-code IDs, status history, and subtask delegation. The
existing `input_task` table is extended — not replaced — so all current flows (user-created tasks,
email-originated tasks, agent handovers, triggers) continue working while gaining new
collaboration capabilities.

The key paradigm shift: **sessions are where agents work; comments are how they report results.**
Every agent — whether in a team or standalone — posts findings, deliverables, and status updates
as task comments. Team membership unlocks delegation (subtasks) and topology-aware routing, but
the core comment/status/attachment model is universal.

Core capabilities:

- **Short-code task IDs** — default prefix "TASK" (TASK-1, TASK-42); teams can set a custom prefix in team settings (e.g., "HR" → HR-1)
- **Task comments** — agents and users post structured comments on tasks (replacing auto-feedback session messages)
- **File attachments** — agents attach deliverables (CSV, reports, images) to tasks or comments from their workspace
- **Status history** — immutable audit trail of every status transition
- **Subtask delegation** — agents in teams create child tasks assigned to connected team members
- **Team-scoped tasks** — tasks optionally belong to a team (`team_id`); team prefix used for short-code
- **Session-per-task** — agents still get sessions for execution, but results flow back as task comments
- **Universal model** — standalone agents use the same comment/status/attachment pattern; team membership just adds delegation

High-level flow (team context):

```
User creates task TASK-1 → Assigned to Lead Agent (team HR)
                                  │
                            Lead starts session (status auto → in_progress)
                                  │
                            Creates subtask HR-2 → Recruiting Agent
                            Creates subtask HR-3 → Employee Agent
                                  │                       │
                            Recruiting Agent          Employee Agent
                            starts session            starts session
                            Generates CSV             Queries birthdays
                            Attaches file via comment Posts comment with results
                            Status → completed        Status → completed
                                  │                       │
                                  └───────────┬───────────┘
                                              │
                            Lead Agent receives notifications
                            Reads subtask comments & attachments
                            Aggregates results
                            Posts summary comment on TASK-1
                            Attaches final report
                            Status → completed
                                  │
                            User sees full task tree with all work
```

High-level flow (standalone agent, no team):

```
Email arrives → Task TASK-5 created → Assigned to Support Agent
                                           │
                                     Agent starts session
                                     Posts comment: "Processing email request..."
                                     Status → in_progress
                                           │
                                     Agent works in session
                                     Posts comment: "Found the answer: ..."
                                     Attaches generated PDF
                                     Status → completed
                                           │
                                     User sees task with full comment trail
```

---

## Architecture Overview

```
User / Email / Trigger / Agent
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │  Backend API (FastAPI)                                       │
  │                                                              │
  │  /api/v1/tasks/                    (existing, extended)      │
  │  /api/v1/tasks/{short_code}/       (new: access by code)    │
  │  /api/v1/tasks/{short_code}/comments/                       │
  │  /api/v1/tasks/{short_code}/attachments/                    │
  │  /api/v1/tasks/{short_code}/subtasks/                       │
  │                                                              │
  │  InputTaskService (extended)  ←── Core orchestration         │
  │  TaskCommentService (new)                                    │
  │  TaskAttachmentService (new)                                 │
  │                                                              │
  └──────────┬──────────────────────────────────────────────────┘
             │
             ▼
  ┌──────────────────────┐    ┌──────────────────────────────────┐
  │  PostgreSQL           │    │  Agent Environment               │
  │                      │    │  (Docker Container)              │
  │  input_task (ext.)   │    │                                  │
  │  task_comment (new)  │◄───│  MCP Tools (clean):              │
  │  task_attachment(new)│    │  - mcp__agent_task__add_comment        │
  │  task_status_history │    │  - mcp__agent_task__update_status      │
  │  (new)               │    │  - mcp__agent_task__create_task        │
  │                      │    │  - mcp__agent_task__create_subtask     │
  │  (existing tables)   │    │  - mcp__agent_task__get_details        │
  │  session             │    │  - mcp__agent_task__list_tasks         │
  │  agentic_team        │    │                                  │
  │  agentic_team_node   │    │                                  │
  └──────────────────────┘    └──────────────────────────────────┘
             │
             ▼
  ┌──────────────────────┐
  │  WebSocket / SSE      │
  │  Real-time events:   │
  │  - task_comment_added│
  │  - task_status_change│
  │  - task_file_attached│
  │  - subtask_completed │
  └──────────────────────┘
```

Integration with existing systems:

- **Input Tasks** — the SAME `input_task` table, extended with new columns
- **Agentic Teams** — tasks optionally scoped to a team; topology defines delegation paths
- **Sessions** — sessions remain the agent's workspace; results posted back as task comments
- **Agent Environments** — MCP tools updated/extended to support comments, status, attachments
- **Email Integration** — emails create tasks as before; agents now respond via task comments
- **Real-time Events** — new event types on existing WebSocket event bus
- **File Management** — task attachments reuse existing file upload/storage infrastructure
- **Task Triggers** — CRON/webhook triggers create tasks as before; gains short-codes automatically

---

## Data Models

### Table: `input_task` — Extended Columns

The existing `input_task` table gains new columns. All existing columns and behavior preserved.

| New Column | Type | Constraints | Default |
|------------|------|-------------|---------|
| `short_code` | VARCHAR(20) | NOT NULL, UNIQUE | auto-generated |
| `sequence_number` | INTEGER | NOT NULL | auto-incremented globally |
| `title` | VARCHAR(500) | nullable | NULL |
| `priority` | VARCHAR(20) | NOT NULL | `"normal"` |
| `parent_task_id` | UUID | FK → `input_task.id` SET NULL, nullable | NULL |
| `team_id` | UUID | FK → `agentic_team.id` SET NULL, nullable | NULL |
| `assigned_node_id` | UUID | FK → `agentic_team_node.id` SET NULL, nullable | NULL |
| `created_by_node_id` | UUID | FK → `agentic_team_node.id` SET NULL, nullable | NULL |

New indexes:
- `ix_input_task_short_code` UNIQUE on `(short_code)` — globally unique short codes
- `ix_input_task_parent_task_id` on `(parent_task_id)`
- `ix_input_task_team_id` on `(team_id)`
- `ix_input_task_assigned_node_id` on `(assigned_node_id)`

**Short-code generation**:

Short codes are globally unique across the platform (per user). Generation logic:

1. If task has `team_id` and the team has a non-default `task_prefix`: use team prefix
2. Otherwise: use default prefix `"TASK"`
3. Increment the global sequence counter (new `task_sequence_counter` column on `user` table, or
   a dedicated sequence table) atomically
4. Format: `{prefix}-{counter}` (e.g., "TASK-1", "HR-42")

Alternative: use a per-owner sequence (each user has their own counter). This avoids global
lock contention and keeps numbering personal: user A has TASK-1 through TASK-50, user B has
their own TASK-1 through TASK-30.

Recommended approach: **per-owner sequence** via `task_sequence_counter` on `user` table.
When a team prefix is used, the counter is still the owner's global counter (so HR-42 means
the owner's 42nd task overall, not the 42nd HR task). This keeps short-codes unique per owner
without needing per-team counters.

**`title`**: Derived from `original_message` on creation (first line or first 100 chars,
trimmed). User-editable afterward. Used for display on task boards and cards. If NULL, falls
back to truncated `original_message`.

**`priority`**: `"low"`, `"normal"`, `"high"`, `"urgent"`. Default "normal". Affects display
ordering on task board.

**`parent_task_id`**: Self-referential FK for subtask hierarchy. SET NULL on parent delete —
orphaned subtasks become root tasks. Unlimited depth but practically 2-3 levels.

**`team_id`**: Optional team association. When set, the task is "team-scoped" and delegation
tools become available. When NULL, the task is standalone.

**`assigned_node_id`**: The team node assigned to this task (provides role context). Only
meaningful when `team_id` is set. The agent is still identified by `selected_agent_id` (existing
column). Both are set together for team-scoped tasks.

**`created_by_node_id`**: Which team node created this task (for agent-initiated subtasks).
NULL for user-created tasks or non-team tasks.

### Existing column reuse:

- `selected_agent_id` — the agent assigned to execute the task (works for both team and standalone)
- `session_id` — the primary execution session (unchanged)
- `source_session_id` — the session that spawned this task via delegation (unchanged)
- `source_agent_id` — the agent that created this task (unchanged)
- `status` — extended with new status values (see below)
- `owner_id` — task owner (unchanged)
- `user_workspace_id` — workspace scoping (unchanged)

### Task Statuses (Clean)

The task status set is redesigned for clarity. Old statuses (`running`, `pending_input`) are
removed in favor of a clean, consistent set:

| Status | Description |
|--------|-------------|
| `new` | Created, awaiting refinement or assignment |
| `refining` | User actively refining with AI |
| `open` | Refined and assigned, ready for agent execution |
| `in_progress` | Agent actively working |
| `blocked` | Agent blocked, waiting for external input or dependency |
| `completed` | Task finished successfully |
| `error` | Task failed |
| `cancelled` | Task cancelled by user or agent |
| `archived` | Archived by user |

**Removed statuses**:
- `running` → replaced by `in_progress`
- `pending_input` → replaced by `blocked` (more general, covers both user input and external waits)

**Migration**: Existing tasks with `running` status are migrated to `in_progress`. Existing
tasks with `pending_input` are migrated to `blocked`. This is a data migration in the Alembic
upgrade step.

Valid transitions:

```
new → refining, open, in_progress, cancelled, archived
refining → new, open, in_progress
open → in_progress, cancelled
in_progress → completed, blocked, cancelled, error
blocked → in_progress, cancelled
completed → archived
error → new, in_progress, archived
cancelled → archived
archived → (terminal)
```

---

### Table: `task_comment` (NEW)

Purpose: the collaboration surface. Agents and users post comments on tasks to share findings,
ask questions, report progress, and deliver results.

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| `id` | UUID | PK | uuid4 |
| `task_id` | UUID | FK → `input_task.id` CASCADE, NOT NULL | required |
| `content` | TEXT | NOT NULL, min 1 | required |
| `comment_type` | VARCHAR(30) | NOT NULL | `"message"` |
| `author_node_id` | UUID | FK → `agentic_team_node.id` SET NULL, nullable | NULL |
| `author_agent_id` | UUID | FK → `agent.id` SET NULL, nullable | NULL |
| `author_user_id` | UUID | FK → `user.id` SET NULL, nullable | NULL |
| `metadata` | JSON | nullable | NULL |
| `created_at` | DATETIME | NOT NULL | utcnow |

Indexes:
- `ix_task_comment_task_id` on `(task_id)`

**Comment types**:
- `"message"` — regular text comment (default)
- `"status_change"` — auto-generated when status changes (metadata: `{from_status, to_status}`)
- `"assignment"` — auto-generated when task is assigned/reassigned
- `"system"` — platform-generated notifications (e.g., "Subtask HR-43 completed")
- `"result"` — agent's final result/deliverable comment (semantically tagged for aggregation)

**Author tracking**:
- `author_agent_id` — set when an agent posts (standalone or team). Always set for agent comments.
- `author_node_id` — additionally set when the agent is acting in a team role.
- `author_user_id` — set when a human posts.
- System comments: all author fields NULL.

This triple-author pattern allows: "Posted by Support Agent" (standalone) vs "Posted by
Recruiting Agent (HR Team)" (team context) vs "Posted by John" (user).

---

### Table: `task_attachment` (NEW)

Purpose: files attached to tasks — deliverables, reports, data exports, images.

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| `id` | UUID | PK | uuid4 |
| `task_id` | UUID | FK → `input_task.id` CASCADE, NOT NULL | required |
| `comment_id` | UUID | FK → `task_comment.id` SET NULL, nullable | NULL |
| `file_name` | VARCHAR(500) | NOT NULL | required |
| `file_path` | VARCHAR(1000) | NOT NULL | required |
| `file_size` | BIGINT | nullable | NULL |
| `content_type` | VARCHAR(200) | nullable | NULL |
| `uploaded_by_agent_id` | UUID | FK → `agent.id` SET NULL, nullable | NULL |
| `uploaded_by_user_id` | UUID | FK → `user.id` SET NULL, nullable | NULL |
| `source_agent_id` | UUID | FK → `agent.id` SET NULL, nullable | NULL |
| `source_workspace_path` | VARCHAR(1000) | nullable | NULL |
| `created_at` | DATETIME | NOT NULL | utcnow |

Indexes:
- `ix_task_attachment_task_id` on `(task_id)`
- `ix_task_attachment_comment_id` on `(comment_id)`

**Origin tracking**: When a file is attached from an agent workspace, `source_agent_id` and
`source_workspace_path` record where it came from (e.g., Recruiting Agent +
`/app/workspace/output/report.csv`). The agent is the stable identity — environments are rebuilt
and files are copied between them, but the agent persists. This lets the UI show provenance
("generated by Recruiting Agent at `output/report.csv`") and enables navigating to the agent's
workspace to find related files. `uploaded_by_agent_id` identifies WHO attached the file (could
be the same agent or a different one forwarding); `source_agent_id` identifies WHERE the file
originally lived. For user-uploaded files both source fields are NULL.

**Storage**: Reuse existing file upload infrastructure from `agent_file_management`. Files stored
in `backend/data/uploads/{user_id}/{attachment_id}/` (same directory convention as `file_upload`).
`file_path` is the backend storage path. Files are served via a new download endpoint with
ownership-based access control.

**Comment association**: If `comment_id` is set, the attachment is inline with that comment.
If NULL, it's a standalone task attachment.

**File transfer from agent environment to backend storage**:

When an agent calls `mcp__agent_task__add_comment(content="...", files=["report.csv"])`, the flow is:

1. MCP tool on agent-env resolves workspace paths (e.g., `/app/workspace/report.csv`)
2. MCP tool calls backend agent API: `POST /agent/tasks/{task_id}/comment` with `file_paths`
3. Backend's `TaskAttachmentService.attach_from_workspace()` is called for each path
4. For each file path, the backend calls the agent environment's HTTP API to download the file:
   `GET /files/download?path={workspace_path}` (existing agent-env file API)
5. Backend stores the file in `backend/data/uploads/{owner_id}/{attachment_id}/{filename}`
6. Backend creates `TaskAttachment` record with `file_path`, `file_size`, `content_type`
7. Attachment is linked to the comment (or standalone if no comment)

This is the same pattern used by the existing file viewing feature — the backend already has
the ability to fetch files from agent environment workspaces via the environment's HTTP API.

**User downloads task attachments**:

Users download attachments via `GET /api/v1/tasks/{task_id}/attachments/{attachment_id}/download`.
The backend streams the file from its local storage (not from the agent environment — the file
was already copied to backend storage on attachment creation). This means attachments remain
accessible even if the agent environment is stopped or rebuilt.

---

### Table: `task_status_history` (NEW)

Purpose: immutable audit trail of every status transition.

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| `id` | UUID | PK | uuid4 |
| `task_id` | UUID | FK → `input_task.id` CASCADE, NOT NULL | required |
| `from_status` | VARCHAR(30) | NOT NULL | required |
| `to_status` | VARCHAR(30) | NOT NULL | required |
| `changed_by_agent_id` | UUID | FK → `agent.id` SET NULL, nullable | NULL |
| `changed_by_user_id` | UUID | FK → `user.id` SET NULL, nullable | NULL |
| `reason` | TEXT | nullable | NULL |
| `created_at` | DATETIME | NOT NULL | utcnow |

Indexes:
- `ix_task_status_history_task_id` on `(task_id)`

---

### Modifications to Existing Tables

#### `agentic_team` — new column

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| `task_prefix` | VARCHAR(10) | nullable | NULL |

When NULL, tasks in this team use the default "TASK" prefix. When set (e.g., "HR"), tasks
created in this team's context use this prefix. User-editable via team settings.

#### `user` — new column

| Column | Type | Constraints | Default |
|--------|------|-------------|---------|
| `task_sequence_counter` | INTEGER | NOT NULL | 0 |

Per-user monotonic counter for short-code generation. Incremented atomically:
`UPDATE user SET task_sequence_counter = task_sequence_counter + 1 WHERE id = :user_id RETURNING task_sequence_counter`

---

### Model Schema Classes

File: `backend/app/models/input_task.py` — extended

```
InputTaskBase              — (existing) + title, priority
InputTask                  — (existing table, extended) + short_code, sequence_number, title,
                             priority, parent_task_id, team_id, assigned_node_id, created_by_node_id
InputTaskCreate            — (existing) + title?, priority?, team_id?, assigned_node_id?,
                             parent_task_id?
InputTaskUpdate            — (existing) + title?, priority?, assigned_node_id?
InputTaskPublic            — (existing) + short_code, title, priority, team_id, parent_task_id,
                             assigned_node_id, subtask_count, subtask_completed_count
InputTaskPublicExtended    — (existing) + same new fields + assigned_node_name, team_name
InputTaskDetailPublic      — InputTaskPublicExtended + comments: list[TaskCommentPublic],
                             attachments: list[TaskAttachmentPublic],
                             subtasks: list[InputTaskPublic],
                             status_history: list[TaskStatusHistoryPublic]
```

File: `backend/app/models/task_comment.py` — new

```
TaskCommentBase            — content, comment_type
TaskComment                — DB table, all columns
TaskCommentCreate          — content, comment_type?
TaskCommentPublic          — all fields + author_name (resolved), author_role (node name if team),
                             inline_attachments: list[TaskAttachmentPublic]

TaskCommentAgentCreate     — content, file_paths? (list of workspace file paths to attach)
```

File: `backend/app/models/task_attachment.py` — new

```
TaskAttachmentBase         — file_name, content_type
TaskAttachment             — DB table, all columns
TaskAttachmentPublic       — all fields + uploaded_by_name (resolved), download_url,
                             source_agent_name (resolved from uploaded_by_agent_id),
                             source_workspace_path (original path in agent env)
```

File: `backend/app/models/task_status_history.py` — new

```
TaskStatusHistory          — DB table, all columns
TaskStatusHistoryPublic    — all fields + changed_by_name (resolved)
```

Agent-specific request models (in `agent_handover.py` or new file):

```
AgentTaskStatusUpdate      — status, reason?
AgentTaskCommentCreate     — content, file_paths? (workspace paths)
AgentSubtaskCreate         — title, description?, assigned_to? (agent/node name),
                             priority?
```

---

## Security Architecture

### Access Control

All task endpoints require `CurrentUser` (JWT authentication). Ownership: `task.owner_id == current_user.id`.

**Agent access**: MCP tools authenticate via existing HMAC-signed session context. Backend verifies:
1. The calling agent is `selected_agent_id` on the task (or the task's session matches)
2. For team delegation: agent's node exists in the task's team and is connected to target node

### Agent Authorization Rules

| Action | Standalone Agent | Team Agent |
|--------|-----------------|------------|
| Update own task status | Yes | Yes |
| Add comment on own task | Yes | Yes |
| Attach files to own task | Yes | Yes |
| View own task details | Yes | Yes |
| Create subtask | No | Yes (only to connected downstream nodes) |
| View team tasks | No | Yes (any task in their team) |
| Comment on other team tasks | No | Yes (any task in their team) |

### Input Validation

- `title`: max 500 chars
- `content` (comment): min 1, max 10000 chars
- `priority`: enum validation (low, normal, high, urgent)
- `status`: enum validation with transition rules
- `task_prefix`: 1-10 uppercase alphanumeric chars (team setting)
- File attachments: reuse existing platform file size limits

### Status Transition Rules

```
new → refining, open, in_progress, cancelled, archived
refining → new, open, in_progress
open → in_progress, cancelled
in_progress → completed, blocked, cancelled, error
blocked → in_progress, cancelled
completed → archived
error → new, in_progress, archived
cancelled → archived
archived → (terminal)
```

---

## Backend Implementation

### API Routes — Task Extensions

File: `backend/app/api/routes/input_tasks.py` — extended with new endpoints

The existing task routes are preserved. New endpoints added for comments, attachments, subtasks,
and short-code access.

#### New Task Endpoints (by short_code)

| Method | Path | Description | Auth |
|--------|------|-------------|------|
| `GET` | `/api/v1/tasks/by-code/{short_code}` | Get task detail by short code | CurrentUser + ownership |
| `GET` | `/api/v1/tasks/by-code/{short_code}/detail` | Get full detail (comments, attachments, subtasks, history) | CurrentUser + ownership |
| `GET` | `/api/v1/tasks/by-code/{short_code}/tree` | Get task tree (recursive subtasks) | CurrentUser + ownership |

#### Comment Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tasks/{task_id}/comments/` | List comments (paginated, chronological) |
| `POST` | `/api/v1/tasks/{task_id}/comments/` | Add comment (user-initiated) |
| `DELETE` | `/api/v1/tasks/{task_id}/comments/{comment_id}` | Delete comment |

#### Attachment Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tasks/{task_id}/attachments/` | List attachments |
| `POST` | `/api/v1/tasks/{task_id}/attachments/` | Upload attachment (multipart) |
| `GET` | `/api/v1/tasks/{task_id}/attachments/{attachment_id}/download` | Download file |
| `DELETE` | `/api/v1/tasks/{task_id}/attachments/{attachment_id}` | Delete attachment |

#### Subtask Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/v1/tasks/{task_id}/subtasks/` | List direct subtasks |
| `POST` | `/api/v1/tasks/{task_id}/subtasks/` | Create subtask (sets parent_task_id) |

#### Existing Endpoint Modifications

- `GET /api/v1/tasks/` — add query params: `root_only=true` (exclude subtasks from listing),
  `team_id` (filter by team), `priority` (filter)
- `GET /api/v1/tasks/{task_id}` — response now includes `short_code`, `title`, `priority`,
  `team_id`, `subtask_count`, `subtask_completed_count`

#### Agent MCP Endpoints (internal)

File: `backend/app/api/routes/task_agent_api.py` — new, or extend existing agent task endpoints

These endpoints are called by MCP tools inside agent environments.

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/agent/tasks/{task_id}/comment` | Agent posts comment (with optional file paths) |
| `POST` | `/agent/tasks/{task_id}/status` | Agent updates task status |
| `POST` | `/agent/tasks/{task_id}/subtask` | Agent creates subtask (team context required) |
| `GET` | `/agent/tasks/my-tasks` | Agent lists assigned tasks |
| `GET` | `/agent/tasks/{task_id}/details` | Agent gets task detail with comments |

These mirror the user endpoints but authenticate via session context (HMAC), automatically resolve
the agent identity, and accept workspace file paths for attachments.

---

### Service Layer

#### File: `backend/app/services/input_task_service.py` — Extended

The existing `InputTaskService` is extended with new methods. Existing methods preserved.

New/modified methods:

- `create_task(...)` — **modified**: now generates `short_code` and `sequence_number` on creation.
  Determines prefix from team (if `team_id` set and team has `task_prefix`) or default "TASK".
  Sets `title` from first line of `original_message` if not provided. Calls
  `_generate_short_code()`.

- `_generate_short_code(session, owner_id, team_id=None) -> tuple[str, int]`
  - Atomic: `UPDATE user SET task_sequence_counter = task_sequence_counter + 1 WHERE id = :owner_id RETURNING task_sequence_counter`
  - Determine prefix: if team_id → load team → use `task_prefix` or "TASK"
  - Return (f"{prefix}-{counter}", counter)

- `get_task_by_short_code(session, short_code, user_id) -> InputTask`
  - Lookup by `(short_code, owner_id)`. Return 404 if not found.

- `get_task_detail(session, task_id, user_id) -> InputTaskDetailPublic`
  - Load task + comments (with inline attachments) + standalone attachments + subtasks + status history
  - Resolve all names (agent, node, user)

- `get_task_tree(session, task_id, user_id) -> dict`
  - Recursive load: task + all descendant subtasks with status and assignee info

- `update_task_status(session, task_id, new_status, changed_by_agent_id=None, changed_by_user_id=None, changed_by_system=False, reason=None) -> InputTask`
  - Validate status transition
  - Create `TaskStatusHistory` entry
  - Create system `TaskComment` (comment_type="status_change")
  - Update task timestamps (started_at on first in_progress, completed_at on completed)
  - If completed and has parent: call `_notify_parent_task()`
  - Emit `TASK_STATUS_CHANGED` event

- `update_task_status_from_agent(session, task_id, agent_id, data: AgentTaskStatusUpdate) -> InputTask`
  - Verify agent is assigned to this task (`selected_agent_id`)
  - Delegates to `update_task_status()` with agent identity
  - Only for edge-case statuses: `blocked`, explicit `completed`, `cancelled`

- `handle_session_started(session, session_obj) -> None`
  - If session has linked task (via `source_task_id`): auto-transition task to `in_progress`
  - `changed_by_system=True` — system comment: "Agent {name} started working"

- `handle_session_completed(session, session_obj) -> None`
  - If session has linked task: auto-transition task to `completed`
  - System comment: "Agent {name} completed work"
  - Triggers `_notify_parent_task()` if task has parent

- `handle_session_error(session, session_obj, error_message) -> None`
  - If session has linked task: auto-transition task to `error`
  - System comment: "Agent {name} encountered an error: {error_message}"

- `create_subtask(session, parent_task_id, agent_node_id, data: AgentSubtaskCreate) -> InputTask`
  - Verify parent task has `team_id`
  - Verify creating agent's node is in the team
  - If `assigned_to` specified: resolve name to node, verify connection exists from creator to target
  - Create child task with `parent_task_id`, same `team_id`, same `owner_id`
  - Generate short_code using team prefix
  - If assigned: auto-create session for target agent (existing `auto_execute` pattern)
  - Create system comment on parent: "Created subtask {short_code} → {assigned_agent_name}"
  - Emit `TASK_CREATED` event

- `_notify_parent_task(session, parent_task: InputTask, completed_subtask: InputTask) -> None`
  - Post system comment on parent: "Subtask {short_code} completed by {agent_name}"
  - Count subtasks: if all completed → post "All subtasks completed"
  - If parent agent's session is idle → inject notification, trigger agent processing
  - Emit `SUBTASK_COMPLETED` event (scoped to parent task)

- `get_subtask_progress(session, task_id) -> dict`
  - Returns: `{total: int, completed: int, in_progress: int, blocked: int}`
  - Used for task card badges on the board

**Old methods removed**: The following methods on `InputTaskService` are deleted as part of the
clean break:
- `handle_session_state_updated()` — replaced by `update_task_status()` + task comments
- `deliver_feedback_to_source()` — replaced by parent task notification via comments
- `respond_to_task()` — replaced by `add_comment` on parent task

The old auto-feedback loop (session state → source session message) is removed entirely. The
new model: agent completes subtask → status change + comment on subtask → system comment on
parent task → parent agent re-triggered. All visible as task comments, not hidden session messages.

#### File: `backend/app/services/task_comment_service.py` — NEW

Key methods:

- `add_comment(session, task_id, data: TaskCommentCreate, author_agent_id=None, author_node_id=None, author_user_id=None) -> TaskComment`
  - Create comment record
  - Emit `TASK_COMMENT_ADDED` event

- `add_comment_from_agent(session, task_id, agent_id, data: AgentTaskCommentCreate) -> TaskComment`
  - Resolve agent's node if task has team context
  - If `file_paths` provided: call `TaskAttachmentService.attach_from_workspace()` for each,
    link to comment
  - Create comment with author_agent_id (and author_node_id if team)
  - Emit event

- `list_comments(session, task_id, skip, limit) -> tuple[list[TaskComment], int]`
  - Chronological order (ASC)
  - Eager-load inline attachments per comment

- `add_system_comment(session, task_id, content, comment_type="system", metadata=None) -> TaskComment`
  - No author fields set
  - Used by service layer for status changes, assignment changes, subtask notifications

#### File: `backend/app/services/task_attachment_service.py` — NEW

Key methods:

- `upload_attachment(session, task_id, file, uploaded_by_user_id=None) -> TaskAttachment`
  - Store file using existing file storage infrastructure
  - Create attachment record

- `attach_from_workspace(session, task_id, agent_id, file_paths: list[str], comment_id=None) -> list[TaskAttachment]`
  - Resolve agent's environment from `agent_id` → get environment ID + HTTP endpoint
  - For each workspace path:
    - Call environment API: `GET /files/download?path={path}` to fetch file content
    - Store file in backend: `backend/data/uploads/{owner_id}/{attachment_id}/{filename}`
    - Detect content_type from filename extension
    - Create `TaskAttachment` record with:
      - `file_path`: backend storage path
      - `file_size`, `content_type`: from fetched file
      - `source_agent_id`: the agent whose workspace the file came from
      - `source_workspace_path`: the original workspace path (e.g., `/app/workspace/output/report.csv`)
      - `uploaded_by_agent_id`: the agent that attached it
    - Link to `comment_id` if provided (inline attachment)
  - Files are persisted in backend storage — accessible even if environment is stopped
  - Origin fields enable provenance display and potential re-fetch from environment

- `get_download_stream(session, attachment_id, user_id) -> file stream`
  - Verify ownership chain
  - Return file content

---

### MCP Tools — Clean Redesign

The entire agent task toolset is replaced with a clean, consistent set. Old tools are removed,
not deprecated. The session is the workspace; the task is the record.

#### Tools Removed (breaking change)

The following tools from the existing MCP task server are **deleted**:

| Old Tool | Replacement |
|----------|------------|
| `mcp__agent_task__create_agent_task` | `mcp__agent_task__create_task` |
| `mcp__agent_task__update_session_state` | `mcp__agent_task__update_status` |
| `mcp__agent_task__respond_to_task` | `mcp__agent_task__add_comment` (on parent task) |
| `mcp__agent_task__create_collaboration` | `mcp__agent_task__create_subtask` (multiple calls) |
| `mcp__agent_task__post_finding` | `mcp__agent_task__add_comment` |
| `mcp__agent_task__get_collaboration_status` | `mcp__agent_task__get_details` |

All old tools are removed from the MCP server, prompt templates, and pre-approved tool lists.
Agent prompts are updated to reference only the new tool names.

#### New Tool Set

All tools live under the `agent_task` MCP server with consistent naming: `mcp__agent_task__{action}`.

**Tool: `mcp__agent_task__add_comment`**
```
Parameters:
  - content: str (required) — comment text (markdown supported)
  - files: list[str] (optional) — workspace file paths to attach
  - task: str (optional) — target task short_code; defaults to current task

Returns:
  - comment_id: str
  - task: str — short_code of task the comment was added to
  - attachments_count: int
```

The primary way agents report findings, results, and progress. All agents use this.

**Tool: `mcp__agent_task__update_status`** (optional — for edge cases only)
```
Parameters:
  - status: str (required) — blocked/completed/cancelled
  - reason: str (optional) — explanation for the change
  - task: str (optional) — target task short_code; defaults to current task

Returns:
  - task: str — short_code
  - previous_status: str
  - new_status: str
```

Most status transitions are automatic (backend infers from session lifecycle). This tool is
only needed when the agent wants to signal something the backend can't infer:
- `blocked` — waiting for external input, a dependency, or human action
- `completed` — explicit completion when agent wants to mark done before session ends
- `cancelled` — agent determines the task is not actionable

**Tool: `mcp__agent_task__create_task`**
```
Parameters:
  - title: str (required) — what needs to be done
  - description: str (optional) — detailed context
  - assigned_to: str (optional) — agent name or team member name to assign to
  - priority: str (optional) — low/normal/high/urgent

Returns:
  - task: str — short_code of created task (e.g., "TASK-5" or "HR-42")
  - assigned_to: str | null
```

Creates a new standalone task. For team agents, the task inherits the team context.
Replaces `create_agent_task`.

**Tool: `mcp__agent_task__create_subtask`** — Team agents only
```
Parameters:
  - title: str (required) — what needs to be done
  - description: str (optional) — detailed context
  - assigned_to: str (optional) — name of team member to delegate to
  - priority: str (optional) — low/normal/high/urgent

Returns:
  - task: str — subtask's short_code (e.g., "HR-43")
  - parent_task: str — parent's short_code
  - assigned_to: str | null
```

Only available when the agent is in a team context. Delegation restricted to connected
downstream nodes in team topology.

**Tool: `mcp__agent_task__get_details`**
```
Parameters:
  - task: str (optional) — short_code; defaults to current task

Returns:
  - task: str, title, description, status, priority
  - assigned_to: str
  - created_by: str
  - recent_comments: list[{author, content, created_at, has_files}] (last 10)
  - subtasks: list[{task, title, status, assigned_to}]
  - subtask_progress: {total, completed, in_progress, blocked}
```

**Tool: `mcp__agent_task__list_tasks`**
```
Parameters:
  - status: str (optional) — filter by status
  - scope: str (optional) — "assigned" (default), "created", "team"

Returns:
  - tasks: list[{task, title, status, priority, assigned_to, subtask_progress}]
```

`scope="assigned"` returns tasks assigned to this agent. `scope="created"` includes tasks
this agent created (subtasks it delegated). `scope="team"` returns all tasks in the agent's
team (team agents only).

#### Tool Availability Logic

The prompt generator determines which tools to inject based on context:

| Tool | Standalone Agent (with task) | Team Agent | Usage |
|------|------------------------------|------------|-------|
| `mcp__agent_task__add_comment` | Yes | Yes | Primary — how agents report work |
| `mcp__agent_task__update_status` | Yes | Yes | Optional — only for `blocked`/`cancelled`; standard flow is automatic |
| `mcp__agent_task__get_details` | Yes | Yes | Read task info, comments, subtask progress |
| `mcp__agent_task__list_tasks` | Yes | Yes | See assigned/created/team tasks |
| `mcp__agent_task__create_task` | Yes | Yes | Create new standalone tasks |
| `mcp__agent_task__create_subtask` | **No** | Yes | Delegate work to connected team members |

All tools are pre-approved (no per-call user confirmation).

Agents without an active task context (e.g., building mode sessions) do not receive task tools.

**Key principle**: The backend handles the obvious status lifecycle automatically (session
started → in_progress, session completed → completed, session error → error). Agents focus
on doing the work and posting results via comments. The `update_status` tool exists only for
edge cases the backend can't infer from session state.

#### Prompt Injection

When a session is created for a task (both standalone and team), the system prompt includes task
context. The content varies based on team membership:

**Standalone agent task context:**
```
## Your Current Task: {short_code}
Title: {title}
Priority: {priority}
Status: {status}

Description:
{description}

{if source — who created this task}
## Task Origin
This task was created by: {creator_name} ({creator_type: "user" | "agent"})
{if created_by_agent}
Source agent: {source_agent_name}
Context: The agent delegated this task to you because: {connection_prompt or parent task description}
{endif}
{endif}

## Reporting Your Work
- Use `mcp__agent_task__add_comment` to post findings, results, and deliverables
- Attach files to your comments using the `files` parameter
- Your task status is managed automatically:
  - When you start working: status is already "in_progress"
  - When you finish: status auto-completes when your session ends
  - Use `mcp__agent_task__update_status("blocked", reason="...")` only if you're stuck and need external help
```

**Team agent task context (extends standalone):**
```
## Team Context
Team: {team_name}
Your Role: {node_name} (in the {team_name} team)

{if parent_task}
## Task Origin
Parent task: {parent_short_code} - "{parent_title}"
Delegated by: {parent_assigned_agent_name} ({parent_node_name})
Why you received this: {connection_prompt from parent_node → your_node}
Parent description: {parent_description}

Your job is to complete this subtask and report results. The delegating agent
({parent_assigned_agent_name}) will aggregate your findings with other subtask results.
{endif}

## Team Members You Can Delegate To
{for each downstream connection from this node:}
- **{target_node_name}** ({target_agent_name}): {target_agent_description_short}
  Connection context: "{connection_prompt}"
{endfor}

{if no downstream connections}
You are a leaf node in the team — you execute work directly rather than delegating.
{endif}

## Delegation
{if has downstream connections}
- If your task is complex or spans multiple responsibilities, use `mcp__agent_task__create_subtask`
  to delegate parts to team members listed above
- Each subtask you create will be automatically assigned and executed by the target agent
- Monitor subtask progress with `mcp__agent_task__get_details`
- You'll receive notifications when subtasks complete
- Read subtask comments and attachments to gather results
- Aggregate all subtask results before completing your own task
{endif}

## Completion Protocol
1. Post comments as you work — share findings, intermediate results
2. If you delegated subtasks: wait for all to complete, read their comments, aggregate
3. Post a final summary comment with your complete results
4. Attach any deliverable files
5. Your task will auto-complete when your session ends successfully
```

**Key design for prompt generation**: The `connection_prompt` from the team chart is the critical
piece — it's the "why" behind the delegation. When building the team context section, the prompt
generator:

1. Loads the agent's node in the team
2. Finds all outgoing connections from this node (downstream delegation targets)
3. For each connection: includes target node name, agent name, agent description, AND the
   `connection_prompt` the user configured on that edge
4. If the task has a parent: finds the connection from parent's node to this node and includes
   that `connection_prompt` as the delegation reason

This means the `connection_prompt` field on `agentic_team_connection` (which already exists)
serves as the "handover instruction" — it tells the receiving agent WHY this task was delegated
to them and what's expected. The user configures these in the team chart editor.

---

### Background Processing

#### Automatic Task Status Management

The backend manages task status transitions based on session lifecycle events. Agents do NOT
need to call `mcp__agent_task__update_status` for standard transitions — the backend infers them:

| Session Event | Task Status Transition | System Comment |
|--------------|----------------------|----------------|
| Session created for task | `open` → `in_progress` | "Agent {name} started working" |
| Session streaming begins | (already `in_progress`) | — |
| Session completes normally | `in_progress` → `completed` | "Agent {name} completed work" |
| Session ends with error | `in_progress` → `error` | "Agent {name} encountered an error: {error}" |
| Agent calls `mcp__agent_task__update_status("blocked")` | `in_progress` → `blocked` | "Agent {name} blocked: {reason}" |
| Agent calls `mcp__agent_task__update_status("completed")` | explicit override | "Agent {name} marked as completed: {reason}" |

**How it works**: The `InputTaskService` listens to session lifecycle events (session created,
session ended, session error) and automatically transitions the linked task's status. This is
the same event-driven pattern the platform already uses for session state tracking, but now it
drives task status instead.

**When agents DO use `mcp__agent_task__update_status`**: Only for non-obvious transitions that the
backend cannot infer from session state:
- `blocked` — agent needs external input or is waiting for something
- `completed` — agent wants to explicitly mark done (e.g., if continuing to work in the session
  on other things after the task is logically done)
- `cancelled` — agent determines the task is not actionable

For the common happy path (start working → finish), the agent never touches status at all. It
just does its work, posts comments with results, and when the session completes, the task auto-
completes.

#### Task Execution Flow

When a task is assigned to an agent (via `selected_agent_id` or `assigned_node_id`):
1. If `auto_execute` is true (agent-initiated tasks, subtasks):
   - Create conversation-mode session linked to task
   - Inject task context into system prompt
   - Send task description as first message
   - Task status auto-transitions to `in_progress`
2. If `auto_execute` is false (user-created tasks):
   - Task waits in "new" status for user to execute
   - When user clicks Execute: session created, status auto-transitions to `in_progress`

#### Subtask Completion Cascade

When a subtask status changes to "completed":
1. `_notify_parent_task()` posts system comment on parent
2. Checks if ALL subtasks of parent have reached terminal status
3. If all completed: posts "All N subtasks completed — ready to finalize"
4. If parent agent's session is idle: re-triggers agent processing
5. Parent agent reads subtask results via comments, aggregates, and completes own task

#### Session Model Cleanup

The following fields on the `session` model become unused and should be removed:
- `result_state` — replaced by task status
- `result_summary` — replaced by task comments (comment_type="result")

The `source_task_id` field on session is **preserved** — a single task can be executed multiple
times, producing multiple sessions. `source_task_id` on session is the authoritative FK linking
session → task (one task, many sessions). `input_task.session_id` points to the latest/primary
session for convenience.

The session becomes a pure execution workspace. Task state lives on the task, not the session.

#### Real-time Events

New event types added to existing event bus:

- `TASK_COMMENT_ADDED` — payload: `{task_id, short_code, comment_id, author_name, has_attachments}`
- `TASK_STATUS_CHANGED` — payload: `{task_id, short_code, from_status, to_status, changed_by}`
- `TASK_ATTACHMENT_ADDED` — payload: `{task_id, short_code, attachment_id, file_name}`
- `SUBTASK_COMPLETED` — payload: `{parent_task_id, parent_short_code, subtask_short_code, agent_name}`
- `TASK_SUBTASK_CREATED` — payload: `{parent_task_id, parent_short_code, subtask_short_code, assigned_to}`

Events scoped to `task.owner_id` for WebSocket delivery.

---

## Frontend Implementation

### Routes

| Route file | Path | Description |
|------------|------|-------------|
| `frontend/src/routes/_layout/tasks.tsx` | `/tasks` | Task board (replaces or extends current tasks list page) |
| `frontend/src/routes/_layout/tasks/$shortCode.tsx` | `/tasks/$shortCode` | Task detail page |

The existing task list page at `/tasks` is redesigned as a task board. The task detail page is
new — currently tasks open inline or navigate to sessions; now they get their own detail page
with the comment thread.

For team-scoped views, the team page gains a "Tasks" tab:

| Route file | Path | Description |
|------------|------|-------------|
| `frontend/src/routes/_layout/agentic-teams/$teamId/tasks.tsx` | `/agentic-teams/$teamId/tasks` | Team-filtered task board |

This is the same `TaskBoard` component but pre-filtered to `team_id`.

---

### UI Components

#### Task Board (`TaskBoard.tsx`)

File: `frontend/src/components/Tasks/TaskBoard.tsx`

A Kanban-style board showing **root-level tasks only** (tasks where `parent_task_id` is NULL),
grouped by status columns.

**Columns**: Open | In Progress | Blocked | Completed

**Task card contents**:
- Short code badge (e.g., `TASK-42` or `HR-5`) — monospace, color-coded by status
- Title (truncated to 2 lines)
- Assigned agent avatar + name (or "Unassigned")
- Priority indicator (colored dot: normal=none, high=orange, urgent=red)
- Subtask progress chip: `"3/5 subtasks"` with mini progress bar (only shown if task has subtasks)
- Team badge (small, muted) if task belongs to a team

**Filters bar** (top of board):
- Status filter (multi-select)
- Team filter (dropdown of user's teams + "No team")
- Priority filter
- Assigned agent filter
- Search by title/short_code

**"New" and "Refining" tasks**: Shown in a separate "Inbox" section above the Kanban columns,
or as a collapsed group. These are pre-execution tasks that haven't entered the workflow yet.

**Create Task button**: Opens `CreateTaskDialog`

**Board shows root tasks only**: The API call uses `root_only=true`. Subtask progress is shown
as a chip on the parent card — users click into the task detail to see the subtask tree.

#### Task Detail Page (`TaskDetail.tsx`)

File: `frontend/src/components/Tasks/TaskDetail.tsx`

This is the primary view for task work — everything about a task in one place.

**Layout** (same structure as described in previous version):

```
┌──────────────────────────────────────────────────────────┐
│ ← Back to Board    TASK-42    Priority: High  Status: ●  │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  Title: Generate Q1 HR Report                            │
│  Assigned to: [Bot] Team Lead Agent                      │
│  Team: HR Team (if applicable)                           │
│  Created by: John (user) | 2h ago                        │
│                                                          │
│  Description:                                            │
│  Compile hiring stats, employee milestones, and budget   │
│                                                          │
├──────────────────┬───────────────────────────────────────┤
│  Subtasks (3)    │  Attachments (2)                      │
│  ✓ HR-43 Comp..  │  📎 q1_hiring.csv (45KB)             │
│  ● HR-44 In Pr.. │  📎 birthdays.pdf (12KB)             │
│  ○ HR-45 Open..  │                                       │
├──────────────────┴───────────────────────────────────────┤
│                                                          │
│  Activity & Comments                                     │
│                                                          │
│  [System] — 2h ago                                       │
│  Task created by John                                    │
│                                                          │
│  [Bot] Team Lead Agent — 2h ago                          │
│  Starting analysis of Q1 data...                         │
│                                                          │
│  [System] — 2h ago                                       │
│  Status: open → in_progress                              │
│                                                          │
│  [System] — 1h 50m ago                                   │
│  Created subtask HR-43 → Recruiting Agent                │
│  Created subtask HR-44 → Employee Agent                  │
│                                                          │
│  [Bot] Recruiting Agent — 30m ago                        │
│  (on subtask HR-43)                                      │
│  Completed hiring analysis. 12 open positions found.     │
│  📎 open_positions.csv                                   │
│                                                          │
│  [System] — 30m ago                                      │
│  Subtask HR-43 completed by Recruiting Agent             │
│                                                          │
│  [Bot] Team Lead Agent — 5m ago                          │
│  All subtask data collected. Final report attached.      │
│  📎 q1_hr_report.pdf                                    │
│                                                          │
│  [System] — 5m ago                                       │
│  Status: in_progress → completed                         │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │ Add comment...                 [📎] [Send]       │   │
│  └──────────────────────────────────────────────────┘   │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**Key elements**:
- **Header**: Short code badge, status pill, priority badge, back navigation
- **Metadata**: Title (editable), description (editable), agent assignment, team info, creator
- **Subtasks panel**: Collapsible list of child tasks with status icons. Each clickable → navigates to subtask detail. Shows mini progress bar.
- **Attachments panel**: Files list with download links and file type icons
- **Comment thread**: Chronological feed mixing agent comments, user comments, and system events. System events are styled lighter/smaller. Agent comments show bot icon + agent name + team role (if applicable).
- **Comment input**: Textarea at bottom with file upload button and send button. Users can post comments on any of their tasks.

#### Create Task Dialog (`CreateTaskDialog.tsx`)

File: `frontend/src/components/Tasks/CreateTaskDialog.tsx`

- Title (required, Input)
- Description (optional, Textarea — maps to `original_message` and `current_description`)
- Assign to agent (optional, Select — shows user's agents)
- Team (optional, Select — shows user's agentic teams; when selected, assignee list filters to team nodes)
- Priority (optional, Select: Low/Normal/High/Urgent)
- Submit → creates task with short_code, navigates to detail or shows toast

#### Reusable Components

**`TaskShortCodeBadge.tsx`**: Monospace badge, clickable → task detail. Color-coded by status.

**`TaskStatusPill.tsx`**: Color-coded status:
- new/open: gray
- refining: purple
- in_progress: blue
- blocked: amber
- completed: green
- error/cancelled: red
- archived: muted

**`TaskPriorityBadge.tsx`**: Visual priority indicator (colored dot or text badge).

**`SubtaskProgressChip.tsx`**: Compact chip showing "3/5 subtasks" with tiny progress bar. Used on task board cards.

---

### Team Page Integration

The agentic team page (`/agentic-teams/$teamId`) gains sub-navigation tabs:

```
[Chart]  [Tasks]
```

The **Tasks** tab renders the same `TaskBoard` component but pre-filtered to `team_id={teamId}`.
This shows only tasks belonging to that team, using the team's prefix.

#### Team Settings — Task Prefix

In the team settings (existing `AgenticTeamSettings` or team edit dialog), add:

- **Task Prefix** field (Input, max 10 chars, uppercase alphanumeric)
- Help text: "Short code prefix for tasks in this team (e.g., HR → HR-1, HR-2). Leave empty for default TASK prefix."
- Validation: 1-10 chars, `[A-Z0-9]+`

---

### State Management

**Query keys:**

- `["tasks", filters]` — task board list (filtered)
- `["task", shortCode]` — single task detail (by short code)
- `["taskComments", taskId]` — comment list (if paginated separately)
- `["taskTree", taskId]` — recursive subtask tree
- `["teamTasks", teamId]` — team-filtered task list

**Mutations:**

- `createTaskMutation` — invalidates `["tasks"]`
- `updateTaskMutation` — invalidates `["tasks"]` + `["task", shortCode]`
- `addCommentMutation` — invalidates `["task", shortCode]`
- `uploadAttachmentMutation` — invalidates `["task", shortCode]`

**Real-time updates**: Subscribe to `TASK_*` WebSocket events. On event:
- `TASK_COMMENT_ADDED`: append to comment list in query cache
- `TASK_STATUS_CHANGED`: update task status in board and detail caches
- `SUBTASK_COMPLETED`: update subtask progress counts
- `TASK_SUBTASK_CREATED`: add to subtask list

---

### User Flows

**User creates a standalone task:**
1. Click "Create Task" on task board
2. Fill title, description, assign to agent, set priority
3. Submit → task created as TASK-1 in "new" status
4. Click Execute → session created, task moves to "in_progress"
5. Agent works, posts comments, attaches files
6. Agent completes → user sees full comment trail on task detail

**User creates a team task:**
1. On team tasks tab, click "Create Task"
2. Fill title, description, select team member (node) to assign
3. Submit → task created as HR-1 (using team prefix) in "open" status
4. Assigned agent auto-starts session
5. Agent delegates subtasks HR-2, HR-3 to other team members
6. Board shows HR-1 with "2/2 subtasks" progress chip
7. Subtasks complete → lead aggregates → HR-1 completed

**Email creates a task:**
1. Email arrives → creates task with short_code TASK-15
3. Assigned agent processes email in session
4. Agent posts findings as task comment, attaches response draft
5. User sees task in board with full comment trail

**Agent reports work (standalone):**
1. Session starts → task auto-transitions to `in_progress`
2. Agent works, finds results → calls `mcp__agent_task__add_comment(content="Found X...", files=["report.csv"])`
3. Agent finishes → session ends → task auto-transitions to `completed`
4. All visible on task detail as a clean activity log — no status ceremony required

---

## Database Migrations

### Migration 1: `extend_input_task_for_collaboration.py`

Add columns to `input_task`:
- `short_code` VARCHAR(20) — initially nullable for data migration
- `sequence_number` INTEGER — initially nullable
- `title` VARCHAR(500) nullable
- `priority` VARCHAR(20) NOT NULL DEFAULT 'normal'
- `parent_task_id` UUID FK → `input_task.id` SET NULL nullable
- `team_id` UUID FK → `agentic_team.id` SET NULL nullable
- `assigned_node_id` UUID FK → `agentic_team_node.id` SET NULL nullable
- `created_by_node_id` UUID FK → `agentic_team_node.id` SET NULL nullable

Add indexes as specified.

Data migration: backfill `short_code` and `sequence_number` for existing tasks:
- For each user, iterate their tasks ordered by created_at
- Assign TASK-1, TASK-2, etc.
- Update user's `task_sequence_counter` to match

Then: make `short_code` and `sequence_number` NOT NULL, add UNIQUE constraint.

### Migration 2: `add_task_sequence_counter_to_user.py`

Add to `user` table:
- `task_sequence_counter` INTEGER NOT NULL DEFAULT 0

### Migration 3: `add_task_prefix_to_agentic_team.py`

Add to `agentic_team` table:
- `task_prefix` VARCHAR(10) nullable DEFAULT NULL

### Migration 4: `create_task_comment_attachment_history_tables.py`

Create tables:
1. `task_comment` — with all columns and FK constraints
2. `task_attachment` — with FK to input_task and task_comment
3. `task_status_history` — with FK to input_task

All with indexes as specified.

Downgrade: drop tables in reverse order.

---

## Error Handling & Edge Cases

| Scenario | Handling |
|----------|----------|
| Short_code collision | Cannot happen — per-user atomic counter + UNIQUE constraint |
| Agent not in a team tries `create_subtask` | Tool not available in prompt; if called anyway, 400 "Delegation requires team context" |
| Agent tries to delegate to non-connected node | 400 "Cannot delegate to {name} — no connection in team topology" |
| Invalid status transition | 400 "Cannot transition from {current} to {target}" with valid options listed |
| Agent updates status of task not assigned to them | 403 "Only the assigned agent can update task status" |
| Parent task deleted with subtasks | SET NULL — subtasks become root tasks, visible on board |
| Existing task without short_code (pre-migration) | Migration backfills all; runtime should never encounter NULL short_code post-migration |
| Team prefix changed after tasks exist | Existing tasks keep their short_code; new tasks use new prefix |
| File too large for attachment | 413 — reuse platform file size limits |
| Circular subtask reference | Prevented at service layer — walk parent chain, reject if self found |
| Agent comments on other team member's task | Allowed for team members (all in same team); rejected for non-team tasks |
| Task created via trigger/email with no agent | Task gets short_code, sits in "new", no comments until agent assigned and executed |
| Old agent prompts referencing removed tools | Agent gets error; re-build environment with updated prompts to fix |
| Task board with 100+ root tasks | Paginated (default 50 per page); filter/search to narrow down |

---

## UI/UX Considerations

**Task board:**
- Clean Kanban with 4 status columns
- Root tasks only — subtask progress shown as chip on parent card
- Cards: short_code (monospace, small), title (bold, max 2 lines), agent name/avatar, priority dot
- Subtask chip: "2/3 ✓" with green progress bar — only shown when task has subtasks
- Team badge: small, muted pill showing team name — only for team tasks
- "Inbox" section above columns for new/refining tasks (pre-execution)
- Empty column: "No tasks" with subtle icon

**Task detail:**
- Comment thread takes center stage (like GitHub issue comments)
- System events (status changes, assignments) styled as compact, muted inline entries — not full comment cards
- Agent comments: bot icon + agent name + "(HR Team)" role if team context
- User comments: user avatar + name
- Attachments inline with comments: file icon + name + size, clickable to download
- Subtask panel: concise list with status icon, short_code link, assignee — collapsible

**Short code badge:**
- Monospace, `text-xs`, `bg-muted`, `rounded-sm`, `px-1.5 py-0.5`
- Always clickable → navigates to task detail
- Color coding: gray=open, blue=in_progress, green=completed, amber=blocked, red=error

**Real-time:**
- New comments slide into thread with subtle animation
- Status pill updates color smoothly on status change
- Subtask progress chip updates in real-time on board cards
- Toast notifications for major events: "HR-43 completed by Recruiting Agent"

---

## Integration Points

### API Client Regeneration

After backend changes:
```bash
bash scripts/generate-client.sh
```

### Existing Systems Impact

| System | Impact | Change Required |
|--------|--------|-----------------|
| Input Tasks (model) | Extended with new columns, old statuses migrated | Migration + model update |
| Input Tasks (service) | Old methods removed, new methods added | Service rewrite (task lifecycle) |
| Input Tasks (routes) | New endpoints, existing task list extended | Route file extended |
| User model | New `task_sequence_counter` column | Migration |
| Agentic Teams model | New `task_prefix` column | Migration |
| Sessions | `result_state`, `result_summary` removed; `source_task_id` preserved (one task → many sessions) | Migration (drop 2 columns) |
| Agent Environment | Old MCP tools removed, new tools added, prompt templates rewritten | Breaking change |
| Agent Handover | `create_agent_task` tool removed; `AgentHandoverConfig` model preserved (used for team connection prompts) | Tool removal |
| Agent Collaboration | `AgentCollaboration` + `CollaborationSubtask` models removed; replaced by subtask model | Table removal |
| WebSocket Event Bus | New event types, old session state events removed | Event registration update |
| File Management | Reused for attachments | No change |
| Email Integration | Unchanged — emails create tasks as before (now with short_codes) | No change |
| Task Triggers | Unchanged — triggers create tasks as before (now with short_codes) | No change |
| Existing frontend tasks page | Redesigned as task board | UI rewrite |

### Router Registration

Extend existing task routes in `backend/app/api/main.py` — no new router prefix needed.
Comment/attachment/subtask endpoints are nested under existing `/api/v1/tasks/` prefix.

Add agent task API routes:
```python
from app.api.routes import task_agent_api
api_router.include_router(task_agent_api.router, prefix="/agent/tasks", tags=["agent-tasks"])
```

---

## Future Enhancements (Out of Scope)

- **Task templates** — predefined subtask trees for common workflows
- **SLA / due dates** — deadline tracking with overdue alerts
- **Task dependencies** — blocking relationships beyond parent-child
- **Recurring tasks** — CRON-triggered from templates
- **Task analytics** — completion time, throughput, bottleneck identification
- **Cross-team tasks** — tasks spanning multiple agentic teams
- **Human-in-the-loop tasks** — tasks assigned to human team nodes (Phase 3 vision)
- **Approval workflows** — tasks requiring user sign-off before proceeding
- **Full-text search** — search across titles, descriptions, comments
- **Drag-and-drop status changes** — drag cards between Kanban columns
- **Bulk operations** — multi-select for status change, archive, delete
- **Chart execution trace** — overlay showing task flow through team topology in real-time
- **Webhook/email-to-task** — external events creating team-scoped tasks
- **Comment reactions/threading** — react to comments, reply threads within comments

---

## Implementation Phases

### Phase A: Data Foundation
1. Create new model files: `task_comment.py`, `task_attachment.py`, `task_status_history.py`
2. Extend `input_task.py` with new columns and schema variants; remove old `InputTaskStatus.RUNNING` and `PENDING_INPUT`
3. Add `task_sequence_counter` to user model
4. Add `task_prefix` to agentic_team model
5. Generate and apply all migrations (with data backfill for existing tasks; migrate `running` → `in_progress`, `pending_input` → `blocked`)
6. Remove `result_state` and `result_summary` from session model; generate migration
7. Remove `AgentCollaboration` and `CollaborationSubtask` models; generate migration to drop tables
8. Rewrite `InputTaskService`: remove old methods (`handle_session_state_updated`, `deliver_feedback_to_source`, `respond_to_task`), add new methods (short-code generation, status history, subtask management, comments)
9. Create `TaskCommentService` and `TaskAttachmentService`
10. Add new API endpoints (comments, attachments, subtasks, by-short-code, detail, tree)
11. Remove old agent handover/collaboration API endpoints
12. Add real-time events; remove old `SESSION_STATE_UPDATED` event reliance

### Phase B: Agent Tools
1. Remove old MCP tools: `create_agent_task`, `update_session_state`, `respond_to_task`, `create_collaboration`, `post_finding`, `get_collaboration_status`
2. Add new MCP tools: `mcp__agent_task__add_comment`, `mcp__agent_task__update_status`, `mcp__agent_task__create_task`, `mcp__agent_task__create_subtask`, `mcp__agent_task__get_details`, `mcp__agent_task__list_tasks`
3. Rewrite prompt generator: inject task context for all task-linked sessions
4. Inject team delegation context only when agent is a team member
5. Register all new tools as pre-approved
6. Remove old tool names from pre-approved list and tool name registry

### Phase C: Frontend
1. Create task board page (Kanban, root-tasks-only, subtask progress chips)
2. Create task detail page (comment thread, subtask panel, attachment panel)
3. Create reusable components (ShortCodeBadge, StatusPill, PriorityBadge, SubtaskProgressChip)
4. Add "Tasks" tab to agentic team page
5. Add team task prefix setting to team settings
6. Wire React Query + WebSocket subscriptions
7. Create task dialog with team/agent/priority selection
8. Regenerate API client

### Phase D: Polish
1. Real-time comment streaming on task detail
2. Empty states, loading skeletons, error states
3. Task board filters and search
4. File attachment upload/download UI polish
5. End-to-end testing: standalone agent task flow + team delegation flow + email task flow

---

## Summary Checklist

### Backend Tasks

- [ ] Extend `backend/app/models/input_task.py`: add `short_code` (VARCHAR(20), UNIQUE), `sequence_number` (INTEGER), `title` (VARCHAR(500), nullable), `priority` (VARCHAR(20), default "normal"), `parent_task_id` (UUID FK → input_task.id SET NULL), `team_id` (UUID FK → agentic_team.id SET NULL), `assigned_node_id` (UUID FK → agentic_team_node.id SET NULL), `created_by_node_id` (UUID FK → agentic_team_node.id SET NULL)
- [ ] Extend InputTask schema classes: `InputTaskCreate` (+title, priority, team_id, assigned_node_id, parent_task_id), `InputTaskPublic` (+short_code, title, priority, team_id, subtask_count, subtask_completed_count), new `InputTaskDetailPublic` (comments, attachments, subtasks, status_history)
- [ ] Create `backend/app/models/task_comment.py` with `TaskComment` DB model and schemas (TaskCommentCreate, TaskCommentPublic, AgentTaskCommentCreate)
- [ ] Create `backend/app/models/task_attachment.py` with `TaskAttachment` DB model and schemas (TaskAttachmentPublic)
- [ ] Create `backend/app/models/task_status_history.py` with `TaskStatusHistory` DB model and schema (TaskStatusHistoryPublic)
- [ ] Add `task_sequence_counter` (INTEGER, NOT NULL, DEFAULT 0) to `user` model
- [ ] Add `task_prefix` (VARCHAR(10), nullable) to `agentic_team` model
- [ ] Generate migration `extend_input_task_for_collaboration.py` — add new columns to input_task with data backfill (short_codes for existing tasks)
- [ ] Generate migration `add_task_sequence_counter_to_user.py`
- [ ] Generate migration `add_task_prefix_to_agentic_team.py`
- [ ] Generate migration `create_task_comment_attachment_history_tables.py` — create task_comment, task_attachment, task_status_history tables
- [ ] Extend `backend/app/services/input_task_service.py` with: `_generate_short_code()` (atomic per-user counter), `get_task_by_short_code()`, `get_task_detail()`, `get_task_tree()`, `update_task_status()` (with transition validation + history + system comment), `create_subtask()` (team-only, topology validation), `_notify_parent_task()`, `get_subtask_progress()`
- [ ] Modify existing `create_task()` to generate short_code and title on creation
- [ ] Remove old methods from `InputTaskService`: `handle_session_state_updated()`, `deliver_feedback_to_source()`, `respond_to_task()`
- [ ] Remove `result_state` and `result_summary` columns from session model; generate migration
- [ ] Remove `AgentCollaboration` and `CollaborationSubtask` models (`backend/app/models/agent_collaboration.py`); generate migration to drop `agent_collaboration` and `collaboration_subtask` tables
- [ ] Remove `AgentCollaborationService` (`backend/app/services/agent_collaboration_service.py`)
- [ ] Remove old collaboration/handover agent API endpoints from routes
- [ ] Migrate existing `running` status → `in_progress` and `pending_input` → `blocked` in data migration
- [ ] Create `backend/app/services/task_comment_service.py` with `TaskCommentService` — add_comment, add_comment_from_agent (with workspace file copy), list_comments, add_system_comment
- [ ] Create `backend/app/services/task_attachment_service.py` with `TaskAttachmentService` — upload_attachment, attach_from_workspace, get_download_stream
- [ ] Add new endpoints to `backend/app/api/routes/input_tasks.py`: GET by-code/{short_code}, GET by-code/{short_code}/detail, GET by-code/{short_code}/tree, comments CRUD, attachments CRUD, subtasks list+create
- [ ] Extend existing GET /tasks/ with `root_only`, `team_id`, `priority` query params
- [ ] Create `backend/app/api/routes/task_agent_api.py` with agent-facing endpoints (comment, status, subtask, my-tasks, details)
- [ ] Register agent task routes in `backend/app/api/main.py`
- [ ] Add `TASK_COMMENT_ADDED`, `TASK_STATUS_CHANGED`, `TASK_ATTACHMENT_ADDED`, `SUBTASK_COMPLETED`, `TASK_SUBTASK_CREATED` event types

### Agent Environment Tasks

- [ ] Remove old MCP tools from agent-env task server: `create_agent_task`, `update_session_state`, `respond_to_task`, `create_collaboration`, `post_finding`, `get_collaboration_status`
- [ ] Remove old tool names from `PRE_ALLOWED_TOOLS` list and `tool_name_registry.py`
- [ ] Add new MCP tools: `mcp__agent_task__add_comment`, `mcp__agent_task__update_status`, `mcp__agent_task__create_task`, `mcp__agent_task__create_subtask`, `mcp__agent_task__get_details`, `mcp__agent_task__list_tasks`
- [ ] Register all new tools as pre-approved
- [ ] Rewrite prompt generator: inject task context (short_code, title, description, priority, reporting instructions) for all task-linked sessions
- [ ] Rewrite prompt generator: inject team delegation context (team name, role, downstream members, subtask instructions) only when agent is a team member
- [ ] Remove old prompt sections: `_load_task_creation_prompt()`, `build_collaboration_context_section()`, session state reporting instructions
- [ ] Update tool name registry with new tool names only

### Frontend Tasks

- [ ] Regenerate API client (`bash scripts/generate-client.sh`)
- [ ] Create `frontend/src/routes/_layout/tasks.tsx` — task board page
- [ ] Create `frontend/src/routes/_layout/tasks/$shortCode.tsx` — task detail page
- [ ] Create `frontend/src/routes/_layout/agentic-teams/$teamId/tasks.tsx` — team tasks tab (same TaskBoard, pre-filtered)
- [ ] Create `frontend/src/components/Tasks/TaskBoard.tsx` — Kanban board: root tasks only, 4 status columns, task cards with short_code + title + agent + priority + subtask progress chip, filter bar (status, team, priority, agent, search)
- [ ] Create `frontend/src/components/Tasks/TaskDetail.tsx` — full detail page: header (short_code, status, priority), metadata (title, description, assignee, team, creator), subtask panel (collapsible), attachment panel, chronological comment thread with system events, comment input with file upload
- [ ] Create `frontend/src/components/Tasks/CreateTaskDialog.tsx` — Dialog: title, description, assign agent, team selector (optional, filters agent list to team nodes), priority
- [ ] Create `frontend/src/components/Tasks/TaskShortCodeBadge.tsx` — monospace badge, clickable, status-colored
- [ ] Create `frontend/src/components/Tasks/TaskStatusPill.tsx` — color-coded status pill
- [ ] Create `frontend/src/components/Tasks/TaskPriorityBadge.tsx` — priority visual indicator
- [ ] Create `frontend/src/components/Tasks/SubtaskProgressChip.tsx` — compact "3/5 ✓" with mini progress bar
- [ ] Add "Tasks" tab/link to agentic team page navigation alongside "Chart"
- [ ] Add "Task Prefix" field to agentic team settings (create/edit dialog)
- [ ] Wire React Query: `["tasks", filters]` for board, `["task", shortCode]` for detail
- [ ] Subscribe to `TASK_*` WebSocket events for real-time board and detail updates

### Testing & Validation Tasks

- [ ] Verify short-code generation: per-user atomic counter, correct prefix (default "TASK" or team prefix), globally unique per user
- [ ] Verify existing task flows still work: user-created tasks, email tasks, trigger tasks — all now get short_codes
- [ ] Verify status transitions: valid pass, invalid return 400 with helpful message
- [ ] Verify task comment CRUD: user and agent authors, system auto-comments on status change and assignment
- [ ] Verify file attachments: upload via user endpoint, attach from agent workspace, download, cascade delete
- [ ] Verify subtask creation: only team agents can create, topology validation (connected nodes only)
- [ ] Verify subtask completion cascade: parent notified, "all subtasks completed" detection
- [ ] Verify old MCP tools are fully removed: `create_agent_task`, `update_session_state`, `respond_to_task`, `create_collaboration`, `post_finding` — none available to agents
- [ ] Verify old models removed: `AgentCollaboration` and `CollaborationSubtask` tables dropped; `result_state`/`result_summary` columns removed from session
- [ ] Verify new agent MCP tools: `mcp__agent_task__add_comment`, `mcp__agent_task__update_status`, `mcp__agent_task__create_task`, `mcp__agent_task__create_subtask`, `mcp__agent_task__get_details`, `mcp__agent_task__list_tasks` from agent environment
- [ ] Verify standalone agent flow: agent without team can comment/status/attach but cannot create_subtask
- [ ] Verify team agent flow: full delegation, subtask creation, parent notification, aggregation
- [ ] Verify task board UI: root tasks only, subtask progress chips, filters, team-scoped view
- [ ] Verify task detail UI: comment thread, attachments, subtask panel, system events, real-time updates
- [ ] Verify end-to-end: user creates task → lead delegates → subtask agents complete → lead aggregates → task completed with full audit trail
