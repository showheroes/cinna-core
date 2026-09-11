# Input Tasks — Technical Reference

## File Locations

### Backend

**Models:**
- `backend/app/models/tasks/input_task.py` — InputTask table, all schema classes, `InputTaskStatus` constants
- `backend/app/models/tasks/task_comment.py` — TaskComment table, `TaskCommentCreate`, `AgentTaskCommentCreate`, `TaskCommentPublic`
- `backend/app/models/tasks/task_attachment.py` — TaskAttachment table, `TaskAttachmentPublic`
- `backend/app/models/tasks/task_status_history.py` — TaskStatusHistory table, `TaskStatusHistoryPublic`
- `backend/app/models/sessions/session.py` — `source_task_id`, `todo_progress`, `result_state`, `result_summary` additions
- `backend/app/models/__init__.py` — exports

**Routes:**
- `backend/app/api/routes/input_tasks.py` — CRUD, refinement, execution, collaboration endpoints (comments, attachments, subtasks, short-code access); note: `archive_task` and `update_task_status` are `async def` (they need a running event loop to emit the real-time event; from a sync worker thread that emit is scheduled best-effort and dropped silently on failure)
- `backend/app/api/routes/task_agent_api.py` — internal agent API endpoints (called by MCP tools)
- `backend/app/api/main.py` — router registration

**Services:**
- `backend/app/services/tasks/input_task_service.py` — main service (extended with collaboration methods)
- `backend/app/services/tasks/task_comment_service.py` — comment creation, listing, deletion
- `backend/app/services/tasks/task_attachment_service.py` — file upload, workspace attach, download
- `backend/app/services/sessions/session_service.py` — `create_session`, `list_task_sessions`, `delete_session`
- `backend/app/services/events/activity_service.py` — task activity lifecycle handlers
- `backend/app/services/ai_functions/ai_functions_service.py` — `refine_task` method

**AI Functions:**
- `backend/app/agents/task_refiner.py` — LLM task refinement agent
- `backend/app/agents/prompts/task_refiner_prompt.md` — refinement system prompt
- `backend/app/agents/__init__.py` — exports `refine_task`

**Agent-Env Tools:**
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_add_comment.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_update_status.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_create_task.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_create_subtask.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_get_details.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/agent_task_list_tasks.py` — SDK tool for Claude Code adapter
- `backend/app/env-templates/app_core_base/core/server/tools/mcp_bridge/task_server.py` — MCP bridge server (OpenCode adapter)

**Migrations:**
- `backend/app/alembic/versions/l2g3h4i5j6k7_add_input_task_table.py` — initial `input_task` table
- `backend/app/alembic/versions/o5j6k7l8m9n0_add_agent_initiated_fields_to_input_task.py` — agent_initiated, auto_execute, source_session_id
- `backend/app/alembic/versions/p6k7l8m9n0o1_add_todo_progress_to_session.py` — todo_progress
- `backend/app/alembic/versions/u1p2q3r4s5t6_add_session_state_and_task_feedback.py` — result_state, result_summary, auto_feedback, feedback_delivered
- `backend/app/alembic/versions/i6d5e7f8g9h0_add_input_task_id_to_activity.py` — input_task_id FK on activity
- `backend/app/alembic/versions/8f3a1d7c04e2_add_input_task_external_ref_and_sync_index.py` — `external_ref` column, its partial unique index, and the `(owner_id, updated_at)` sync index

**App Startup:**
- `backend/app/main.py` — event handler registration

### Frontend

**Routes:**
- `frontend/src/routes/_layout/tasks/index.tsx` — Tasks page with view mode toggle (Board / List); header has "New Task" button and view switcher; Board view renders `TaskBoard` component; List view renders a compact table with left sidebar status filters (Open / In Progress / Blocked / Completed, then Archived below a separator — mirroring kanban columns), each filter shows a task count; data is fetched once for all non-archived statuses and filtered client-side for instant switching; archived tasks fetched lazily only when the Archived filter is selected; rows grouped by date (Today, Yesterday, Last week, Older), sorted by `updated_at` desc; each row shows status dot, short code (with `CornerDownRight` icon and parent short code for subtasks), title, team/agent badge with color preset, and relative time
- `frontend/src/routes/_layout/task/$taskId.tsx` — unified task detail page; `taskId` param accepts either a UUID or a short code; detects format with `isUUID()` regex and calls `TasksService.getTaskDetail()` (UUID) or `TasksService.getTaskDetailByCode()` (short code) accordingly; full-width layout (no max-width constraints); sessions displayed as a tab alongside Comments/Sub-tasks/Activity (not as a standalone block); right sidebar shows a "Parent Task" row (above Status) when `task.parent_task_id` is set — the row has a tree icon (`GitBranchPlus`) that opens a `TaskTreePopover` and a clickable badge with `parent_short_code` that navigates to the parent; the "Subtasks" sidebar row shows the same tree icon for root tasks that have subtasks
- `frontend/src/routes/_layout/tasks/$shortCode.tsx` — redirect-only route; performs `beforeLoad` redirect from `/tasks/$shortCode` to `/task/$taskId` preserving the short code value

**Components:**
- `frontend/src/components/Tasks/TaskBoard.tsx` — kanban board with 4 columns: Open (includes `new`, `refining`, `open` statuses), In Progress, Blocked, Completed; each column header shows the column label on the left and a rounded `Badge` (shadcn `secondary` variant, `h-5` pill) on the right with the task count; the Completed column also has an `ArchiveIcon` button next to the badge that archives all completed tasks in parallel via `archiveAllMutation` (`Promise.all`); skeleton loading state also uses a rounded pill skeleton in the header; subscribes to `TASK_STATUS_CHANGED`, `TASK_SUBTASK_CREATED`, `SUBTASK_COMPLETED` for real-time updates; no inline filters or create button (handled by parent page header)
- `frontend/src/components/Tasks/TaskShortCodeBadge.tsx` — clickable or static short code badge with status-aware color; navigates to `/task/$taskId` on click
- `frontend/src/components/Tasks/TaskStatusBadge.tsx` — color-coded status badge with icon
- `frontend/src/components/Tasks/TaskStatusPill.tsx` — compact status indicator used in task detail header and subtask rows
- `frontend/src/components/Tasks/TaskPriorityBadge.tsx` — colored priority label (Low, Normal, High, Urgent)
- `frontend/src/components/Tasks/SubtaskProgressChip.tsx` — `{completed}/{total}` subtask counter with percentage color coding; hidden when `total <= 0`
- `frontend/src/components/Tasks/CreateTaskDialog.tsx` — modal with title input, description textarea, team badge row (visible when at least one team exists; clicking a badge selects the team; "None" badge deselects), agent badge row (shows all workspace agents when no team selected; shows only team member agents sorted lead-first when a team is selected; lead agent has Crown icon and is auto-selected on team selection); agent selection in team mode sets both `assigned_node_id` and `selected_agent_id`; Execute switch in the footer (enabled by default, disabled when no agent is selected) controls whether `auto_execute: true` is sent on the payload; priority selector removed from create flow; generates task and navigates to detail
- `frontend/src/components/Tasks/RefinementChat.tsx` — refinement history display + comment input; calls `TasksService.refineTask()`
- `frontend/src/components/Tasks/TaskTodoProgress.tsx` — horizontal progress indicator for TodoWrite tool usage; subscribes to `TASK_TODO_UPDATED`
- `frontend/src/components/Tasks/TaskSessionsModal.tsx` — modal listing all sessions linked to a task; opened from the sessions block "View all" link
- `frontend/src/components/Chat/SubTasksPanel.tsx` — slide-out showing sub-tasks for current session; real-time via `SESSION_STATE_UPDATED`
- `frontend/src/components/Chat/ChatHeader.tsx` — badge showing subtask count; toggles SubTasksPanel

Note: `TaskDetail.tsx` has been deleted. Its functionality is now handled entirely within `frontend/src/routes/_layout/task/$taskId.tsx` as an inline page component.

**Generated Client:**
- `frontend/src/client/sdk.gen.ts` — `TasksService`
- `frontend/src/client/types.gen.ts` — `InputTaskPublic`, `InputTaskPublicExtended`, `InputTaskDetailPublic`, `InputTaskCreate`, `InputTaskUpdate`, `RefineTaskRequest`, `RefineTaskResponse`, `ExecuteTaskRequest`, `ExecuteTaskResponse`, `TaskCommentPublic`, `TaskAttachmentPublic`, `TaskStatusHistoryPublic`

## Database Schema

### Table: `input_task`

Core fields (existing):
- `id` (UUID PK)
- `owner_id` (UUID FK → user.id CASCADE)
- `original_message` (str, immutable after creation)
- `current_description` (str, updated during refinement)
- `status` (`InputTaskStatus` values — see below)
- `selected_agent_id` (UUID FK → agent.id, nullable)
- `session_id` (UUID FK → session.id, nullable — latest/primary session)
- `user_workspace_id` (UUID FK → user_workspace.id, nullable)
- `agent_initiated` (bool)
- `auto_execute` (bool)
- `source_session_id` (UUID FK → session.id, nullable)
- `auto_feedback` (bool, default=True)
- `feedback_delivered` (bool, default=False)
- `refinement_history` (JSON array — `{role, content, timestamp}` items, append-only)
- `todo_progress` (JSONB array, nullable)
- `error_message` (str, nullable)
- `created_at`, `updated_at`, `executed_at`, `completed_at`, `archived_at`

New collaboration fields:
- `short_code` (VARCHAR(20), nullable, unique per owner)
- `sequence_number` (INTEGER, nullable — from `user.task_sequence_counter`)
- `title` (VARCHAR(500), nullable — editable; derived from first line of `original_message` on creation)
- `priority` (VARCHAR(20), default=`"normal"`)
- `parent_task_id` (UUID FK → input_task.id SET NULL, nullable — subtask hierarchy)
- `team_id` (UUID FK → agentic_team.id SET NULL, nullable — team-scoped tasks)
- `assigned_node_id` (UUID FK → agentic_team_node.id SET NULL, nullable)
- `created_by_node_id` (UUID FK → agentic_team_node.id SET NULL, nullable)

External-client fields:
- `external_executor` (VARCHAR(100), nullable) — normalized external execution owner, exposed on create/PATCH and every public task shape. `ExternalExecutorFields` trims before length validation and normalizes blanks to null.
- `external_ref` (VARCHAR(64), nullable) — caller-supplied idempotency key, unique per owner where present. Normalised on write: blank or whitespace-only becomes `NULL`, because `''` **IS NOT NULL** and would therefore be covered by the partial unique index, turning a second create with an empty field into a constraint violation

Indexes: `ix_input_task_owner_status`, `ix_input_task_parent_task_id`, `ix_input_task_team_id`, `ix_input_task_assigned_node_id`, `ix_input_task_owner_updated` (`(owner_id, updated_at)` — backs the `updated_since` cursor), `ix_input_task_owner_external_ref` (`(owner_id, external_ref)` UNIQUE `WHERE external_ref IS NOT NULL` — partial so the overwhelming majority of tasks, which carry no ref, do not collide with each other)

**Migration `8f3a1d7c04e2`** (`add_input_task_external_ref_and_sync_index`) adds the column and both indexes. Migration `fc99da75645c` (`backend/app/alembic/versions/fc99da75645c_add_external_executor_to_input_tasks.py`) adds the nullable execution marker without changing existing rows.

**`InputTaskStatus` values:**

| Constant | Value | Notes |
|----------|-------|-------|
| `NEW` | `"new"` | |
| `REFINING` | `"refining"` | |
| `OPEN` | `"open"` | New — ready for agent execution |
| `IN_PROGRESS` | `"in_progress"` | Replaces old `running` |
| `BLOCKED` | `"blocked"` | Replaces old `pending_input` |
| `COMPLETED` | `"completed"` | |
| `ERROR` | `"error"` | |
| `CANCELLED` | `"cancelled"` | New |
| `ARCHIVED` | `"archived"` | |

Legacy aliases on `InputTaskStatus`: `RUNNING = "in_progress"`, `PENDING_INPUT = "blocked"` (backward compatibility).

### Table: `task_comment`

- `id` (UUID PK)
- `task_id` (UUID FK → input_task.id CASCADE, NOT NULL)
- `content` (TEXT, min 1, max 10000)
- `comment_type` (VARCHAR(30), default=`"message"`)
- `author_node_id` (UUID FK → agentic_team_node.id SET NULL, nullable)
- `author_agent_id` (UUID FK → agent.id SET NULL, nullable)
- `author_user_id` (UUID FK → user.id SET NULL, nullable)
- `comment_meta` (JSON, nullable — stored as column `metadata`; used by status_change type: `{from_status, to_status}`)
- `created_at` (DATETIME)

Index: `ix_task_comment_task_id`

**Author pattern**: agent comments set `author_agent_id`; team-context agents also set `author_node_id` (role display). User comments set `author_user_id`. System comments leave all author fields NULL.

### Table: `task_attachment`

- `id` (UUID PK)
- `task_id` (UUID FK → input_task.id CASCADE, NOT NULL)
- `comment_id` (UUID FK → task_comment.id SET NULL, nullable — inline or standalone)
- `file_name` (VARCHAR(500))
- `file_path` (VARCHAR(1000) — relative path in backend storage)
- `file_size` (BIGINT, nullable)
- `content_type` (VARCHAR(200), nullable)
- `uploaded_by_agent_id` (UUID FK → agent.id SET NULL, nullable)
- `uploaded_by_user_id` (UUID FK → user.id SET NULL, nullable)
- `source_agent_id` (UUID FK → agent.id SET NULL, nullable — where file originated)
- `source_workspace_path` (VARCHAR(1000), nullable — original path in agent workspace)
- `created_at` (DATETIME)

Indexes: `ix_task_attachment_task_id`, `ix_task_attachment_comment_id`

Storage path: `uploads/{owner_id}/task_attachments/{attachment_id}/{filename}` (relative to `UPLOAD_BASE_PATH`)

### Table: `task_status_history`

- `id` (UUID PK)
- `task_id` (UUID FK → input_task.id CASCADE, NOT NULL)
- `from_status` (VARCHAR(30))
- `to_status` (VARCHAR(30))
- `changed_by_agent_id` (UUID FK → agent.id SET NULL, nullable)
- `changed_by_user_id` (UUID FK → user.id SET NULL, nullable)
- `reason` (TEXT, nullable)
- `created_at` (DATETIME)

Index: `ix_task_status_history_task_id`

### Related Table Modifications

**`agentic_team`** — new column `task_prefix` (VARCHAR(10), nullable). `AgenticTeamCreate` now includes `task_prefix` so it can be set at creation time, not only via update. When non-null, tasks created under this team use this string as the short-code prefix instead of `"TASK"`.

**`user`** — new column `task_sequence_counter` (INTEGER, default=0). Per-user monotonic counter incremented atomically on each task creation.

### Model Schema Classes

**`backend/app/models/tasks/input_task.py`:**
- `InputTaskBase` — `original_message`, `current_description`
- `InputTask` — DB table (all columns above)
- `ExternalExecutorFields` — shared create/update schema with `external_executor: str | None` (max 100, stripped; blank becomes null)
- `InputTaskCreate` — inherits `ExternalExecutorFields`; includes: `title?`, `priority?`, `team_id?`, `assigned_node_id?`, `parent_task_id?`, `auto_execute?` (bool, default `False`; set to `True` by `CreateTaskDialog` when Execute switch is on), `external_ref?` (str ≤ 64 — idempotency key; cleared by `POST /{id}/subtasks/` before the service sees it)
- `InputTaskUpdate` — inherits `ExternalExecutorFields`; omitted marker preserves it, explicit null releases it after validation; includes new: `title?`, `priority?`, `team_id?`, `assigned_node_id?` (team can be changed after creation)
- `InputTaskPublic` — includes new: `short_code`, `title`, `priority`, `parent_task_id`, `team_id`, `assigned_node_id`, `created_by_node_id`, `external_ref`, `external_executor`, `subtask_count`, `subtask_completed_count`
- `InputTaskPublicExtended` — extends Public with: `agent_name`, nullable `result_state` and `result_summary` (typed source-session compatibility fields), `refinement_history`, `todo_progress`, `sessions_count`, `latest_session_id`, `attached_files`, `assigned_node_name`, `team_name`, `parent_short_code` (resolved by service layer via DB lookup), `root_short_code` (walks up hierarchy to root; set only when task has a parent)
- `InputTaskDetailPublic` — extends Extended with: `comments: list[TaskCommentPublic]`, `attachments: list[TaskAttachmentPublic]`, `subtasks: list[InputTaskPublic]`, `status_history: list[TaskStatusHistoryPublic]`
- `InputTaskStatusUpdate` — user-side status write (`status`, `reason?`). Deliberately separate from `InputTaskUpdate` (a status change carries a reason, an audit row and a transition check, none of which the field-patch route does) and from `AgentTaskStatusUpdate` (whose allowed set and consumers belong to the container-side agent API). `reason` is uncapped, matching `AgentTaskStatusUpdate.reason` and the `TaskStatusHistory.reason` column — a length limit only one caller had would break the shared refusal vocabulary
- `AgentTaskStatusUpdate` — agent edge-case status update (`status`, `reason?`, `task?` short code)
- `AgentSubtaskCreate` — agent subtask creation (`title`, `description?`, `assigned_to?`, `priority?`, `task?` short code, `source_session_id?`)
- `AgentTaskCreate` — agent standalone task creation (`title`, `description?`, `assigned_to?`, `priority?`, `source_session_id?`)
- `AgentTaskOperationResponse` — generic agent op response (`success`, `task` short code, `parent_task?` short code, `assigned_to?` resolved name, `message?`, `error?`)

## API Endpoints

### File: `backend/app/api/routes/input_tasks.py`

**Task CRUD:**
- `POST /api/v1/tasks/` — create task; auto-generates `short_code` and `title`; calls `create_task_idempotent` and receives `(task, created)`. If `created` **and** `auto_execute=True` **and** `selected_agent_id` is set, schedules `_auto_execute_task` as a background asyncio task (creates a session and sends the task description as the initial message). The `created` gate is what makes an `external_ref` retry harmless: a matched task is returned without a second execution being scheduled on it
- `GET /api/v1/tasks/` — list tasks; query params: `root_only` (exclude subtasks), `team_id`, `priority`, `updated_since` plus optional `updated_since_id` (incremental cursor — lexicographic `(updated_at, id) >` when both are supplied; timestamp alone retains `updated_at >`, and switches the ordering to `(updated_at asc, id asc)` *only when present*; the route docstring carries the deletion limit and the cursor-not-`skip` paging rule so they reach the generated OpenAPI client)
- `GET /api/v1/tasks/{id}` — get task (`InputTaskPublicExtended`)
- `PATCH /api/v1/tasks/{id}` — update task, including owner-validated `external_executor` claim/release; emits `TASK_UPDATED` when the marker changes
- `DELETE /api/v1/tasks/{id}` — delete task (emits ACTIVITY_DELETED for linked activities)

**Task Actions:**
- `POST /api/v1/tasks/{id}/refine` — AI-assisted refinement
- `POST /api/v1/tasks/{id}/execute` — execute task (creates session)
- `POST /api/v1/tasks/{id}/status` — set status as the calling user (`InputTaskStatusUpdate` → `InputTaskPublic`); `async def`; delegates to `InputTaskService.update_task_status_from_user`. Allowed targets: `open`, `in_progress`, `blocked`, `completed`, `error`, `cancelled`. `400` for a disallowed target, an invalid transition, or a task owned by someone else; `404` only for a task that does not exist. No session side effects. No web UI calls it — the desktop client is its only consumer today
- `POST /api/v1/tasks/{id}/archive` — archive task
- `GET /api/v1/tasks/{id}/sessions` — list all sessions for a task
- `GET /api/v1/tasks/by-source-session/{session_id}` — list tasks created by a source session

**Short-Code Access (new):**
- `GET /api/v1/tasks/by-code/{short_code}` — get task by short code (`InputTaskPublicExtended`)
- `GET /api/v1/tasks/by-code/{short_code}/detail` — full detail: comments, attachments, subtasks, history
- `GET /api/v1/tasks/by-code/{short_code}/tree` — recursive subtask tree (used by `TaskTreePopover` in the frontend)

**Detail by UUID (new):**
- `GET /api/v1/tasks/{id}/detail` — full detail by UUID (`InputTaskDetailPublic`)

**Comments (new):**
- `GET /api/v1/tasks/{id}/comments/` — list comments (chronological, paginated)
- `POST /api/v1/tasks/{id}/comments/` — add comment (user-initiated)
- `DELETE /api/v1/tasks/{id}/comments/{comment_id}` — delete comment (ownership check via task)

**Attachments (new):**
- `GET /api/v1/tasks/{id}/attachments/` — list attachments
- `POST /api/v1/tasks/{id}/attachments/` — upload attachment (multipart)
- `GET /api/v1/tasks/{id}/attachments/{attachment_id}/download` — download file (streaming)
- `DELETE /api/v1/tasks/{id}/attachments/{attachment_id}` — delete attachment and file on disk

**Subtasks:**
- `GET /api/v1/tasks/{id}/subtasks/` — list direct subtasks (`InputTasksPublicExtended`); used by `SubtaskProgressChip` popover via `TasksService.listSubtasks`
- `POST /api/v1/tasks/{id}/subtasks/` — create subtask (user-initiated; sets `parent_task_id` automatically). Clears `subtask_in.external_ref` before calling the service: an idempotency key matching some unrelated root task would return that task while the `parent_task_id` just set is silently dropped — a 200 for a subtask that does not exist. It is cleared rather than rejected so a client that fills the field uniformly still gets a real subtask

**Legacy file attachment (pre-collaboration):**
- `POST /api/v1/tasks/{id}/files/{file_id}` — attach pre-uploaded FileUpload to task
- `DELETE /api/v1/tasks/{id}/files/{file_id}` — detach FileUpload from task

### File: `backend/app/api/routes/task_agent_api.py`

Called by MCP tools inside agent environments. Authentication via the scoped `AgentEnvContextDep` (`backend/app/api/deps.py`) — the env token is rejected by `get_current_user`, so these routes are reachable only by the owning environment, confined to its `(environment, agent, owner)` scope. Agent identity comes from `ctx.agent`; handlers assert the target task/session belongs to `ctx.owner` (+ `ctx.agent` for session-resolved calls). See [Agent Environment Core](../../agents/agent_environment_core/agent_environment_core_tech.md#jwt-authentication-scoped-env-token).

**Helper (module-level):**
- `_resolve_task_from_session(db_session, session_id, ctx) -> InputTask` — resolves via `Session.source_task_id` (immutable FK, survives task re-execution); enforces scope by asserting `session.user_id == ctx.owner.id AND session.agent_id == ctx.agent.id` and `task.owner_id == ctx.owner.id` (raises `PermissionDeniedError` otherwise — a compromised container cannot drive another owner's task by guessing a session UUID); raises `ValidationError` if no linked task; used by all `current/*` endpoints

**Endpoints:**
- `POST /agent/tasks/create` — agent creates standalone task; resolves `assigned_to` by name, inherits team context from session, auto-executes if assigned
- `GET /agent/tasks/by-code/{short_code}` — resolves short code (e.g. `HR-17`) to `{task_id, short_code}`; used by tools that accept a `task` param to obtain the UUID before making subsequent calls
- `POST /agent/tasks/current/comment` — agent posts comment on its current task; requires `source_session_id` in body; calls `_resolve_task_from_session` to find task
- `POST /agent/tasks/current/status` — agent updates status of its current task; requires `source_session_id` in body; calls `_resolve_task_from_session`
- `GET /agent/tasks/current/details` — agent gets details of its current task; `source_session_id` passed as query param; calls `_resolve_task_from_session`; automatically uploads task files to agent environment; `async def`
- `POST /agent/tasks/current/subtask` — agent creates subtask under its current task (resolved from `source_session_id`); delegates to `create_subtask` with team topology validation
- `POST /agent/tasks/{task_id}/comment` — agent posts comment with optional workspace file paths (explicit task_id variant)
- `POST /agent/tasks/{task_id}/status` — agent explicitly updates status (edge cases: blocked, cancelled, completed; explicit task_id variant)
- `POST /agent/tasks/{task_id}/subtask` — agent creates subtask with explicit parent task ID (validates team membership and connection topology)
- `GET /agent/tasks/my-tasks` — agent lists tasks (`scope`: `assigned` / `created` / `team`)
- `GET /agent/tasks/{task_id}/details` — agent gets simplified task detail (recent comments, subtask progress; explicit task_id variant); accepts optional `source_session_id` query param — when provided, uploads task files to agent environment; `async def`

## Services & Key Methods

### `InputTaskService` (`backend/app/services/tasks/input_task_service.py`)

Exception classes: `InputTaskError`, `TaskNotFoundError`, `AgentNotFoundError`, `PermissionDeniedError`, `ValidationError`

**Helper methods:**
- `verify_agent_access()` — verify agent exists and user owns it, optionally require active environment
- `get_task_with_ownership_check()` — get task and verify owner
- `parse_status_filter()`, `parse_workspace_filter()` — filter parsing utilities
- `get_task_extended()` — resolves agent name, team/node names, session data, and `parent_short_code` / `root_short_code` via DB lookup (walks parent chain to root)
- `list_tasks_extended()` — same enrichment with `parent_short_code` batch-resolved in a single query for all tasks in the result set

**CRUD:**
- `create_task_idempotent(db_session, user_id, data) -> tuple[InputTask, bool]` — the real create. Normalises `external_ref` once at the top (`(... or '').strip() or None`) so blank and whitespace-only refs never reach the column; if a ref is present, looks up `(owner_id, external_ref)` first and returns `(existing, False)` on a hit. On insert it catches `IntegrityError`, and **only** when the failing constraint is `ix_input_task_owner_external_ref` (matched by `exc.orig.diag.constraint_name`, falling back to the index name in the message) rolls back, re-reads by `(owner_id, external_ref)` and returns the row that won the race; any other constraint failure is re-raised with its own shape. Both the lookup guard and the fallback guard test `is not None`, so they cannot disagree about what counts as "has a ref". The rollback is safe for the caller: everything before this call on both reachable routes is read-only, so it unwinds only the INSERT and the short-code counter increment — and un-burning that short code is desirable
- `create_task()` — thin wrapper returning only the task, for the seven callers that do not care whether a row was created or matched. **Any caller with a side effect on the new task — scheduling execution, notifying a parent — must use `create_task_idempotent` and gate that effect on `created`.** Generates `short_code` via `_generate_short_code()`, sets `title` from first line of `original_message`; if `team_id` is set but neither `selected_agent_id` nor `assigned_node_id` is provided, queries `AgenticTeamNode` for the lead node (`is_lead=True`) and auto-assigns both `selected_agent_id` and `assigned_node_id`; if `data.user_workspace_id` is `None` and a `selected_agent_id` is set (explicit or team-lead-resolved), loads the `Agent` and inherits its `user_workspace_id` onto the task
- `_auto_execute_task(task_ref: InputTask) -> None` — static async method; opens its own DB session (independent of the request lifecycle); calls `execute_task()` to create a session and send the task description as the initial message; used for both user-created tasks with `auto_execute=True` and agent-created subtasks; no-ops silently if `selected_agent_id` is not set or the task record is missing; previously named `_auto_execute_subtask` (dropped the unused `db_session` parameter in the same rename)
- `execute_task()` routes through `ChannelIngestionService.ingest_inbound_message` with `SessionSender.from_task_execution(...)` (`kind="task_executor"`) — see [channel ingestion](../agent_sessions/channel_ingestion.md) / [tech](../agent_sessions/channel_ingestion_tech.md). The executing human's `user_id` is carried as `sender.platform_user_id` and the service runs a real owner-match access check (NOT a system-trigger fast-path)
- `_generate_short_code(session, owner_id, team_id=None) -> tuple[str, int]` — atomic counter increment; prefix from team or default "TASK"
- `get_task_by_short_code(session, short_code, user_id)` — lookup by `(short_code, owner_id)`
- `get_task_detail(session, task_id, user_id) -> InputTaskDetailPublic` — full detail with comments (inline attachments), standalone attachments, subtasks, status history
- `get_task_tree(session, task_id, user_id)` — recursive subtask tree
- `list_tasks_extended()` — supports filters: `root_only`, `team_id`, `priority`, `updated_since`, `updated_since_id` (passed straight through to `list_tasks`)
- `list_tasks(..., updated_since=None, updated_since_id=None)` — applies `InputTask.updated_at > updated_since`, plus `updated_at == updated_since AND id > updated_since_id` when the companion ID is provided (ID without timestamp raises `ValidationError`) and, when the param is present, replaces the ordering with `(updated_at asc, id asc)`. Clients carry both final-row values into the next request; ordering by ID alone cannot prevent timestamp-only cursors skipping ties at page boundaries. The `id` tiebreak makes the sort total — `updated_at` is not unique, and two rows written in the same transaction would otherwise page in an order that can change between requests. The switch is **conditional on purpose**: making it unconditional would silently reorder the task list for every user on the web. `count_statement` is taken before any `order_by`, so the count is unaffected
- `update_task()`, `delete_task()`, `update_status()`, `append_to_refinement_history()`
- `link_session()` — set session_id, status to in_progress
- `reset_task_if_no_sessions()` — reset to NEW if all linked sessions deleted

**Status and collaboration:**
- `update_task_status(session, task_id, new_status, changed_by_agent_id=None, changed_by_user_id=None, changed_by_system=False, reason=None)` — validates transition, creates `TaskStatusHistory`, creates system comment, emits `TASK_STATUS_CHANGED`
- `update_task_status_from_agent(session, task_id, agent_id, data: AgentTaskStatusUpdate)` — verifies agent is assigned; delegates to `update_task_status()`
- `update_task_status_from_user(session, task_id, user_id, data: InputTaskStatusUpdate)` — the mirror of `update_task_status_from_agent` for a user-authenticated client reporting work executed outside cinna. Ownership via `get_task_with_ownership_check`, then a narrower allowed set (`open`, `in_progress`, `blocked`, `completed`, `error`, `cancelled`; refusal message `"User can only set status to: ..."`), then delegates to the auditing `update_task_status()` with `changed_by_user_id` — **not** the bare `update_status()` the session handlers call, which skips the transition table, the history row and the comment. Never touches sessions
- `create_task_from_agent(session, user_id, data: AgentTaskCreate) -> (InputTask, resolved_name)` — resolves session context, agent name (team node or agent fallback), team inheritance; creates and optionally auto-executes task; posts system message to source session
- `create_subtask(session, parent_task_id, creating_agent_id, data: AgentSubtaskCreate)` — validates team membership, connection topology, creates child task, auto-executes if assigned, posts system comment on parent
- `list_agent_tasks(session, user_id, status=None, scope="assigned")` — scope: assigned / created / team
- `get_agent_task_details(session, task_id, user_id)` — simplified view for agent consumption
- `get_subtask_progress(session, task_id)` — returns `{total, completed, in_progress, blocked}`
- `_notify_parent_task(session, parent_task, completed_subtask)` — post system comment on parent; trigger parent agent if session is idle; emit `SUBTASK_COMPLETED`
- `_collect_task_files_info(session, task_id) -> list[dict]` — queries `InputTaskFile` (user uploads linked to task) and `TaskAttachment` (agent/user attachments on task and its comments); deduplicates by filename; returns list of `{file_name, file_size, content_type, source, storage_path}` dicts
- `upload_task_files_to_agent_env(session, task_details, source_session_id) -> dict` — async; resolves agent environment from `source_session_id`; reads each file from backend storage; POSTs to agent-env `POST /files/upload` with `subfolder=task_{SHORT_CODE}`; files land at `/app/workspace/uploads/task_{SHORT_CODE}/` in the container; injects `uploaded_files` list into returned `task_details`; strips internal `files` key before returning; skips files exceeding size limit; silently skips if environment is not running

**Session event handlers (static async, registered in `backend/app/main.py`):**
- `handle_session_started()` — task → `in_progress` (system comment)
- `handle_session_completed()` — task → `completed` only if all subtasks are also completed (via `compute_status_from_sessions` which checks `get_subtask_progress`); stays `in_progress` if incomplete subtasks remain (system comment; triggers `_notify_parent_task`)
- `handle_session_error()` — task → `error` (system comment with error message)
- `handle_todo_list_updated()` — propagate session todos to task, emit `TASK_TODO_UPDATED`

**Removed methods** (replaced by comment/status model):
- `handle_session_state_updated()` — replaced by `update_task_status()` + task comments
- `deliver_feedback_to_source()` — replaced by `_notify_parent_task()`
- `respond_to_task()` — replaced by `add_comment` on parent task

**Also removed (Phase 4 of the channels & identity unification):** `send_email_answer()` (AI-generated email reply for an email-originated task) and the `source_email_message_id` / `source_agent_id` columns it depended on. Email no longer creates `InputTask` rows at all — see [Email Integration](../email_integration/email_integration.md#capabilities-removed-in-this-refactor).

### `MessageService` — task context enrichment (`backend/app/services/sessions/message_service.py`)

The module-level function `_build_session_context(db, session_db, env, agent)` now queries `InputTask` by `session_id` and — when a matching task is found — populates the following keys into the session context dict. These are consumed by `PromptGenerator.build_task_context_section()` inside the agent environment:

| Key | Source |
|-----|--------|
| `task_short_code` | `InputTask.short_code` |
| `task_title` | `InputTask.title` |
| `task_description` | `InputTask.current_description` |
| `task_priority` | `InputTask.priority` |
| `task_status` | `InputTask.status` |
| `task_created_by_name` | Creator agent name (if `agent_initiated`) or user full name / email |
| `task_created_by_type` | `"agent"` or `"user"` |
| `parent_task_short_code` | `InputTask.short_code` of parent (subtasks only) |
| `parent_task_title` | Parent task title |
| `parent_task_description` | Parent task `current_description` |
| `parent_assigned_agent_name` | Name of agent assigned to parent task |
| `parent_node_name` | Name of team node assigned to parent task |
| `team_name` | `AgenticTeam.name` (team-scoped tasks) |
| `node_name` | `AgenticTeamNode.name` of assigned node |
| `downstream_team_members` | List of `{node_name, agent_name, agent_description, connection_prompt}` dicts for enabled outbound connections from the assigned node |
| `delegation_connection_prompt` | `AgenticTeamConnection.connection_prompt` on the connection from parent node → current node (subtasks with team context) |

The enrichment runs inside a `try/except` block — failures are logged as warnings and do not break message delivery.

### `TaskCommentService` (`backend/app/services/tasks/task_comment_service.py`)

- `add_comment(session, task_id, data, author_agent_id=None, author_node_id=None, author_user_id=None)` — creates comment record, emits `TASK_COMMENT_ADDED`
- `add_comment_from_agent(session, task_id, agent_id, data: AgentTaskCommentCreate)` — resolves agent's node in team context; if `file_paths` provided delegates to `TaskAttachmentService.attach_from_workspace()`; creates comment with agent/node author
- `add_system_comment(session, task_id, content, comment_type="system", comment_meta=None)` — no author fields; used for status changes, subtask notifications
- `list_comments(session, task_id, skip, limit) -> tuple[list[TaskCommentPublic], int]` — chronological ASC; eager-loads inline attachments
- `delete_comment(session, comment_id, user_id)` — ownership check via task
- `_to_public(session, comment, include_attachments=True)` — resolves `author_name`, `author_role`, `inline_attachments`

### `TaskAttachmentService` (`backend/app/services/tasks/task_attachment_service.py`)

- `upload_attachment(session, task_id, file: UploadFile, uploaded_by_user_id=None, comment_id=None)` — stores file, creates `TaskAttachment` record, emits `TASK_ATTACHMENT_ADDED`
- `attach_from_workspace(session, task_id, agent_id, file_paths, comment_id=None)` — resolves agent's active environment; for each path: normalizes to a relative path (handles `./reports/file.json`, `/app/workspace/reports/file.json`, and `reports/file.json` formats), then calls `GET /workspace/download/{rel_path}` on agent-env HTTP API; stores file; creates `TaskAttachment` with origin tracking
- `get_download_stream(session, task_id, attachment_id, user_id) -> tuple[Path, str, str]` — ownership check; returns (abs_path, filename, content_type)
- `list_attachments(session, task_id)` — all attachments for a task (chronological)
- `delete_attachment(session, task_id, attachment_id, user_id)` — deletes DB record and file on disk

**Storage path pattern:** `uploads/{owner_id}/task_attachments/{attachment_id}/{filename}`
Base path resolved from `settings.UPLOAD_BASE_PATH`. Path traversal protection applied before serving.

## External Client Sync Surface

The ordinary user-scoped task API additions let a user-authenticated
client outside cinna (Cinna Desktop) mirror tasks it runs itself. They are not on
the `/api/v1/external/` surface and need no new token type — an ordinary user JWT
is the right identity.

### The two-route split

`POST /api/v1/tasks/{id}/status` (user) and `POST /api/v1/agent/tasks/{task_id}/status`
(container) exist as two routes precisely because **each refuses the other's
token**: `AgentEnvContextDep` rejects a user token, and `get_current_user` rejects
an `aud="agent_env"` token. That invariant is pinned in both directions by
`test_user_route_and_agent_route_do_not_accept_each_others_tokens`. The two
handlers then converge on the same auditing `update_task_status()`, so a status
change from either caller is indistinguishable downstream: same transition table,
same `TaskStatusHistory` row, same `status_change` comment, same
`TASK_STATUS_CHANGED` event.

### Contention with the session-driven recompute

`update_task_status_from_user` writes through the validated path;
`compute_status_from_sessions` / `sync_task_status_from_sessions` write through
the bare `update_status()`, which never consults `VALID_TRANSITIONS`. The
consequence, pinned by test: a user writing `blocked` mid-flight on a task cinna
*is* executing lands, and is then overridden by the recompute on the next session
event — to `completed`, a transition `VALID_TRANSITIONS["blocked"]` would have
refused the user. **The server overrides the client on a transition the client
itself cannot make.** In practice nothing contends, because an externally-executed
task has no session and `sync_task_status_from_sessions` returns `None` for it.

### External execution guard and release

`create_task_idempotent` stores `external_executor` and forces `auto_execute=False`
while marked. The create preparation path returns before automatic refinement;
`refine_task` and `execute_task` refresh the task and refuse marked execution.
The execute route reports its existing `success=False` result shape; PATCH and
refine validation failures return 400. An idempotent create retry returns the
existing row unchanged, including its marker.

`update_task` uses `SELECT ... FOR UPDATE` when PATCH includes the marker.
Changing an existing marker while `in_progress`, `blocked` or `refining` is
refused. A non-null claim is refused if `task.session_id` or any session's
`source_task_id` links cinna work to this task. Repeating the same marker is a
no-op for ownership; explicit null releases it only after leaving active states.
Claiming a legacy sessionless mirror clears `executed_at` and disables automatic
execution. Releasing does not restore `auto_execute`.

`SessionService.create_session` in `backend/app/services/sessions/session_service.py`
locks and freshly reads the same task before inserting a task-linked session,
refuses a non-null marker, and holds the lock through the session insert commit.
This closes the claim-between-execute-check-and-session-insert window for every
caller of that shared session creation path. The early execute check supplies a
friendly error; the session-layer check enforces the invariant at insertion.

Both `update_status` and the auditing `update_task_status` avoid setting
`executed_at` for marked work. Completion still sets `completed_at`, and the user
route still records `changed_by_user_id`. Unmarked legacy clients retain the
previous timestamp semantics. `VALID_TRANSITIONS["completed"]` now includes
`in_progress`, supporting explicit restart and release-then-Run-Again. This is
an additive public contract change; desktop copies need updating to offer the
new path locally, while future narrowing requires a coordinated client release.

Marker-changing PATCH schedules owner-scoped `TASK_UPDATED` after commit with
`task_id`, `short_code`, `parent_task_id` and nullable `external_executor`. No event
is emitted merely for repeating the same marker. The async route preserves a
running event loop for the scheduled event emission.

### `updated_since` — scope of the cursor

Activity detection reads `input_task.updated_at` (with `id` for paging ties), so every write that
changes a task's *activity* has to bump that column even though it writes to a
different table. `app/services/tasks/task_touch.py` holds the one-line helper
(`touch_task`) and the reasoning; it is called from eight write paths:

| Service | Paths |
|---|---|
| `TaskCommentService` | `add_comment`, `add_system_comment`, `delete_comment` |
| `TaskAttachmentService` | upload, `attach_from_workspace`, `delete_attachment` |
| `InputTaskService` | `attach_files_to_task`, `detach_file_from_task` (via `InputTaskService._touch`) |

`touch_task` never commits. It must land in the **same transaction** as the
comment or attachment it describes — a cursor that can observe the bump without
the comment, or the comment without the bump, is worse than no cursor. Callers
invoke it immediately before their own `commit()`.

Pinned by `test_updated_since_reports_comment_and_attachment_changes`, which
walks comment → attachment → comment-deletion, advancing the cursor between
phases and asserting the cursor is caught up before each one (so no phase can
pass on a previous phase's bump).

**Interaction with `status_repair_tasks`.** That sweep uses `updated_at` as an
optimistic lock — it reads a candidate, then re-verifies `updated_at` before
repairing, to avoid repairing a row somebody touched in between. Comment writes
now count as that touch, which makes the sweep *more* conservative in exactly
the right direction: a task whose agent is actively posting comments is alive,
not stranded, so skipping it for the next tick is the correct answer. The
sweep's own docstring already describes `updated_at` as "what tells a row
somebody has touched since we looked from one nobody has".

**Still unreported: deletions.** A deleted task simply stops appearing — there
is no tombstone table, and one was judged not worth a table's worth of
machinery. Clients reconcile with a full pull.

### 400 vs 404

`get_task_with_ownership_check` raises `PermissionDeniedError`, which carries
`status_code=400`; only `TaskNotFoundError` is a 404. Every route in
`input_tasks.py` therefore answers 400 for "exists but is not yours" — the new
status route included, for consistency with its fourteen neighbours. A caller can
consequently distinguish "not yours" from "not there", i.e. the file leaks task
existence. That is pre-existing and file-wide; tightening only this route would
make it the odd one out, and the tests use the established
`assert r.status_code in (400, 404)` shape. Clients should treat the two
identically on these routes.

### Tests

- `backend/tests/api/input_tasks/test_task_status_transitions.py` — the user status route: happy path with history row and comment, invalid transition, disallowed target (`refining` is the case that truly proves the allowed-set gate, since `new → refining` is a *valid* transition and can only be refused by the set), non-owner, the mid-flight recompute override, and the two-token refusal
- `backend/tests/api/input_tasks/test_task_external_sync.py` — `updated_since` filtering and ordering, the conditional sort, the comment-only gap, the non-report of deletions, and `external_ref` create / retry / per-owner scoping / blank-ref normalisation / the subtask route ignoring it / no-re-execute-on-retry

- `backend/tests/api/input_tasks/test_task_external_executor.py` — marker normalization, public response coverage, idempotent retry, guarded execution/refinement, session-backed claim refusal, active-marker release refusal, user attribution/timestamps, marker owner events
- `backend/tests/api/input_tasks/test_task_sync_pagination.py` — paired-cursor paging across timestamp ties and rejection of an ID without a timestamp
- `backend/tests/unit/test_session_external_executor_guard.py` — defensive session-insertion guard regression; this does not simulate a concurrent database race

## Event Handler Registration

**File:** `backend/app/main.py`

- `TASK_CREATED` → `ActivityService.handle_task_created`
- `TASK_STATUS_UPDATED` → `ActivityService.handle_task_status_changed`
- `SESSION_STARTED` → `InputTaskService.handle_session_started`
- `STREAM_COMPLETED` → `InputTaskService.handle_session_completed`
- `STREAM_ERROR` → `InputTaskService.handle_session_error`
- `TODO_LIST_UPDATED` → `InputTaskService.handle_todo_list_updated`

## Real-Time Events

New events emitted from the task collaboration system (file: `backend/app/models/events/event.py`):

| Event | Trigger | Payload |
|-------|---------|---------|
| `TASK_UPDATED` | Marker changes through `InputTaskService.update_task()` | `task_id`, `short_code`, `parent_task_id`, `external_executor` |
| `TASK_COMMENT_ADDED` | `TaskCommentService.add_comment()` | `task_id`, `short_code`, `comment_id`, `author_name`, `has_attachments` |
| `TASK_STATUS_CHANGED` | `InputTaskService.update_task_status()` | `task_id`, `short_code`, `from_status`, `to_status` |
| `TASK_ATTACHMENT_ADDED` | `TaskAttachmentService._emit_attachment_event()` | `task_id`, `short_code`, `attachment_id`, `file_name` |
| `SUBTASK_COMPLETED` | `InputTaskService._notify_parent_task()` | `parent_task_id`, `subtask_id`, `subtask_short_code` |

All events are scoped to the task owner (`user_id`).

The task detail page also subscribes to session-domain events to update the Sessions tab in real time:

| Event | Source | Used For |
|-------|--------|---------|
| `SESSION_UPDATED` | Session service | Refresh sessions list |
| `SESSION_INTERACTION_STATUS_CHANGED` | Session service | Update streaming indicator and tab icon pulse |
| `SESSION_STATE_UPDATED` | Session service | Update session status |
| `STREAM_COMPLETED` | Stream handler | Mark session as complete |

These events are matched by `meta.source_task_id` or by `meta.session_id` / `event.model_id` against a ref-tracked set of known session IDs (`sessionIdsRef`). The ref pattern avoids stale closures — `useMultiEventSubscription` does not re-subscribe when the handler changes, so session IDs are tracked via a `useRef` updated by `useEffect`.

## Frontend Components

- `frontend/src/routes/_layout/tasks/index.tsx` — Tasks page: Board/List view toggle in header; Board view delegates to `TaskBoard` component; List view shows compact table with left sidebar status filters (Open, In Progress, Blocked, Completed, Archived below a separator) each with a count, date-grouped rows (Today/Yesterday/Last week/Older), status dots, short codes (with `CornerDownRight` + parent short code for subtasks that have `parent_task_id`), agent/team badges with color presets, relative timestamps; non-archived tasks fetched once and filtered client-side; archived tasks lazy-fetched only when Archived filter is active
- `frontend/src/routes/_layout/task/$taskId.tsx` — unified task detail page (Linear-style layout): accepts UUID or short code in `$taskId` param; full-width layout with left body and right sidebar panel; four tabs: Comments, Sessions, Sub-tasks, Activity; session and subtask tab icons pulse blue when active sessions or in-progress subtasks exist; tab counters rendered as round pill badges; session rows use `space-y-0.5` (no dividers), agent color-preset badge, relative timestamp; subtask rows use `space-y-0.5`, `treeStatusIcons` status icons, relative timestamp; sidebar shows "Parent Task" row (above Status, when `parent_task_id` set) with `GitBranchPlus` tree icon opening `TaskTreePopover` and clickable `parent_short_code` badge; sidebar "Subtasks" label shows `GitBranchPlus` tree icon for root tasks; WebSocket session event handler uses a `sessionIdsRef` to avoid stale closure issues — matches events by `meta.session_id` or `event.model_id` against known task session IDs; subscribes to `TASK_UPDATED`, `TASK_COMMENT_ADDED`, `TASK_STATUS_CHANGED`, `TASK_ATTACHMENT_ADDED`, `SUBTASK_COMPLETED`, `TASK_SUBTASK_CREATED` (task events) and `SESSION_UPDATED`, `SESSION_INTERACTION_STATUS_CHANGED`, `SESSION_STATE_UPDATED`, `STREAM_COMPLETED` (session events)
- `frontend/src/routes/_layout/tasks/$shortCode.tsx` — redirect-only: `beforeLoad` redirects `/tasks/$shortCode` to `/task/$taskId`
- `frontend/src/components/Tasks/TaskBoard.tsx` — kanban board: 4 columns (Open merges `new`/`refining`/`open`, In Progress, Blocked, Completed); column headers show label left, shadcn `Badge` (secondary variant, `h-5` pill) with count right; Completed column has `ArchiveIcon` button to the left of the badge that archives all completed tasks in parallel (`Promise.all`); skeleton headers use matching rounded pill skeleton; `TaskShortCodeBadge`, `TaskPriorityBadge`, `SubtaskProgressChip` per card; workspace-aware via `useWorkspace`; no inline filters or create dialog (managed by parent page)
- `TaskTreePopover` (inline component in `$taskId.tsx`) — fetches full task tree via `TasksService.getTaskTreeByCode({ shortCode: rootShortCode })`; renders recursive `renderNode` function with depth-based `paddingLeft` indentation; current task node highlighted with `bg-primary/10 font-medium`; all nodes are clickable navigation links showing status icon, short code, title
- `frontend/src/components/Tasks/TaskShortCodeBadge.tsx` — status-color-coded short code badge; `clickable` prop controls navigation to `/task/$taskId`
- `frontend/src/components/Tasks/TaskPriorityBadge.tsx` — colored label for `low`, `normal`, `high`, `urgent`; hides for `"normal"` (default)
- `frontend/src/components/Tasks/SubtaskProgressChip.tsx` — `{completed}/{total}` chip with inline progress bar; hidden when `total <= 0`; requires a `taskId: string` prop; the chip is a `PopoverTrigger` — clicking it (with `e.stopPropagation()`) opens a `PopoverContent` containing a `SubtaskList` subcomponent; `SubtaskList` fetches subtasks via `TasksService.listSubtasks({ id: taskId })` (query key `["subtasks", taskId]`); each subtask row shows a status icon (matching the `treeStatusIcons` palette), short code in monospace, title, and relative time (with exact datetime on hover via `title` attribute); each row is a button that navigates to `/task/$taskId` using `short_code || id`
- `frontend/src/components/Tasks/TaskStatusBadge.tsx` — icon + color per status
- `frontend/src/components/Tasks/TaskStatusPill.tsx` — compact inline status indicator used in header and subtask rows
- `frontend/src/components/Tasks/CreateTaskDialog.tsx` — form with title, description, team badge row, agent badge row, Execute switch; calls `TasksService.createTask()`
- `frontend/src/components/Tasks/RefinementChat.tsx` — shows `refinement_history`; submits via `TasksService.refineTask()`
- `frontend/src/components/Tasks/TaskTodoProgress.tsx` — TodoWrite progress indicator; subscribes to `TASK_TODO_UPDATED`
- `frontend/src/components/Tasks/TaskSessionsModal.tsx` — lists all sessions for a task; opened from the Sessions tab "View all" link
- `frontend/src/components/Chat/SubTasksPanel.tsx` — slide-out subtask list using generated `TasksService.listTasksBySourceSession`; subscribes to `SESSION_STATE_UPDATED`, `TASK_UPDATED`, `TASK_STATUS_CHANGED` with polling fallback. A failed query shows Retry separately from empty results. Execute tracks pending task IDs independently and refuses marked tasks with an explanatory reason
- `frontend/src/components/Tasks/TaskExternalExecutor.tsx` — shared detail notice and `RowFlag` used by task detail, board, list and chat subtasks; labels come from `frontend/src/utils/taskExternalExecutor.ts`. Marker presence disables Execute/Run Again and Refine; comments remain enabled. Marker editing stays API/client-owned

**No frontend surface** exists for `POST /tasks/{id}/status`, `updated_since` or `external_ref`. They land in the generated client (`TasksService`, `frontend/src/client/`) because the client is generated from the OpenAPI spec, but the web UI calls none of them: the web executes tasks with sessions, and the session lifecycle drives status for those.

## Security

- All task endpoints restricted to owner via `CurrentUser` (JWT required)
- Agent API endpoints (`/agent/tasks/*`) authenticate via same JWT; agent identity resolved from `task.selected_agent_id`, not from the token
- Team delegation validated: creating agent's node must have directed connection to target node in team topology
- `original_message` immutable after creation (audit trail)
- `refinement_history` append-only (conversation audit)
- `status_history` append-only, write-only from the API (never deleted)
- Attachment download: ownership verified against `task.owner_id`; path traversal protection applied before serving files
- Agent workspace attach: file content fetched from agent-env HTTP API using per-environment Bearer token; stored in backend — agent env access not required for subsequent user downloads
- Status transitions validated against `InputTaskStatus.VALID_TRANSITIONS` map (for every writer except the session-driven recompute, which goes through the bare `update_status()`)
- `POST /tasks/{id}/status` is user-scoped and owner-gated; the status it can set is restricted to a six-value subset, so `refining` and `archived` cannot be reached sideways and `archived_at` stays owned by `POST /{id}/archive`. It has no session side effects — a client cannot start, resume or interrupt agent work through it
- The user status route and the agent status route reject each other's tokens (`get_current_user` refuses an `aud="agent_env"` token; `AgentEnvContextDep` refuses a user token) — see [External Client Sync Surface](#the-two-route-split)
- `external_ref` is scoped per owner by a partial unique index, so one user's key can never match or reveal another user's task
- "Exists but not yours" answers `400` (`PermissionDeniedError`), only "does not exist" answers `404`, across all of `input_tasks.py`. Task existence is therefore distinguishable by an authenticated non-owner — pre-existing and file-wide, not specific to the newer routes
- `task_prefix` validated: 1–10 uppercase alphanumeric characters (team settings)
