# Input Tasks

## Purpose

Enable users to receive, refine, and execute incoming tasks through an AI-assisted preparation workflow. Tasks transform vague or incomplete requests into detailed, agent-ready instructions before execution, and can be created manually or by other agents.

The task system also serves as the primary **collaboration surface** for agent work: every agent — whether standalone or part of a team — reports findings, deliverables, and progress by posting comments on tasks. File attachments, status history, and subtask hierarchies make the full work trail visible to users without needing to read raw session logs.

## Core Concepts

- **Input Task**: A user-facing request container that goes through refinement before agent execution. Holds original message, current description, and refinement history.
- **Short Code**: Human-readable task identifier auto-generated on creation (e.g., `TASK-1`, `HR-42`). Globally unique per owner. Uses the team's `task_prefix` when the task belongs to a team; otherwise defaults to `"TASK"`.
- **Title**: Short label derived from the first line of `original_message` on creation (max 100 chars). User-editable. Falls back to truncated message if null.
- **Priority**: `low`, `normal` (default), `high`, `urgent`. Affects display ordering on the task board.
- **Task Status**: Lifecycle state from creation through execution to archival.
- **Refinement**: AI-assisted process to improve a task description using the target agent's workflow prompt as context.
- **Refinement History**: Append-only log of user comments and AI responses during refinement.
- **Task Execution**: Creating a session linked to the task and sending the refined description as the initial message.
- **Task Comment**: Structured message posted on a task by an agent, a user, or the system. The primary way agents report results and findings.
- **Task Attachment**: File attached to a task or comment — deliverables, reports, data exports, images. Files from agent workspaces are transferred to backend storage so they persist even if the environment is stopped.
- **Status History**: Immutable, append-only audit trail of every status transition, recording who made the change and why.
- **Subtask**: A child task created within a parent task's hierarchy. Inherits `team_id` and `owner_id` from the parent. Agents in teams create subtasks via the `mcp__agent_task__create_subtask` tool.
- **Team-Scoped Task**: Task with `team_id` set. Enables delegation tools and uses the team's short-code prefix.
- **Agent-Initiated Task**: Task created by an agent via the `mcp__agent_task__create_task` tool, either for direct handover or user inbox.
- **Auto-Execute**: Flag on agent-created tasks that triggers immediate execution without user review.
- **Source Session**: The agent session that created a task via handover; used for delegation tracking.
- **Todo Progress**: Real-time task completion progress from agent's TodoWrite tool calls.

## User Stories / Flows

### Flow 1: User-Initiated Task

1. User creates a task with an initial message description (title and priority are optional)
2. System auto-generates `short_code` (e.g., `TASK-1`) and derives a title
3. User opens the task detail page
4. Left panel: description editor, agent selector, execute button, sessions list
5. Right panel: task comments and attachments; AI refinement chat
6. User sends refinement comments — AI refines description and provides feedback
7. User continues refining or clicks Execute
8. System creates a session linked to the task via `source_task_id`
9. Session start automatically transitions task status to `in_progress`
10. Agent works and posts comments with findings; files are attached to comments
11. Session completion automatically transitions task to `completed`
12. User sees the full comment thread and any deliverable files
13. User archives completed tasks

### Flow 2: Agent-Initiated Direct Handover

1. Source agent calls `mcp__agent_task__create_task` with a target agent name
2. System creates task with `agent_initiated=true`, `auto_execute=true`, generates short code
3. If target agent has `refiner_prompt`, message is auto-refined
4. System auto-creates session; task transitions to `in_progress`
5. Target agent posts progress comments; attaches deliverables
6. Session completes; task transitions to `completed`
7. Task appears in Tasks list with full comment history

### Flow 3: Agent-Initiated Inbox Task

1. Source agent calls `mcp__agent_task__create_task` without specifying a target agent
2. System creates task with `agent_initiated=true`, `auto_execute=false`
3. Task appears in user's task inbox with status `new`
4. User reviews, optionally refines, selects agent, and executes
5. Subsequent flow matches Flow 1 from step 8

### Flow 4: Team Agent Delegation (Subtask Hierarchy)

1. User creates task assigned to a team's lead agent (team scoped, e.g., `HR-1`)
2. Lead agent starts session; task auto-transitions to `in_progress`
3. Lead agent calls `mcp__agent_task__create_subtask` to delegate work to connected team members
4. Each subtask is created with the team prefix (e.g., `HR-2`, `HR-3`), auto-executed for target agents
5. Each sub-agent posts comments with their results; attaches files; session completes
6. System posts a system comment on the parent task: "Subtask HR-2 completed by Recruiting Agent"
7. Lead agent receives notification; reads subtask comments via `mcp__agent_task__get_details`
8. Lead agent aggregates results, posts a summary comment on `HR-1`, attaches final report
9. Lead agent's session completes; parent task transitions to `completed`
10. User sees the full task tree with all subtask work at a glance

### Flow 5: Email-Originated Task

1. Incoming email creates a task automatically (via email integration)
2. System assigns short code, derives title from email subject
3. Assigned agent's session starts; agent posts progress comments
4. User can trigger `send-answer` to email the result back to the sender

## Business Rules

### Task Status Lifecycle

| Status | Description | Automatic? |
|--------|-------------|-----------|
| `new` | Created, awaiting refinement or assignment | — |
| `refining` | User actively refining with AI | — |
| `open` | Refined and assigned, ready for execution | — |
| `in_progress` | Agent actively working | Yes — session start |
| `blocked` | Agent waiting for external input or dependency | Agent tool only |
| `completed` | Task finished successfully | Yes — session completion |
| `error` | Task failed | Yes — session error |
| `cancelled` | Cancelled by user or agent | — |
| `archived` | Archived by user | — |

**Automatic status management**: The backend infers status from the session lifecycle. Agents should not call `mcp__agent_task__update_status` for normal completion — only for edge cases (`blocked`, explicit `cancelled`, or early `completed` before the session ends).

**Removed statuses (migrated)**:
- `running` — migrated to `in_progress`
- `pending_input` — migrated to `blocked`

### Session-to-Task Status Sync

- Session start → task = `in_progress` (system comment: "Agent {name} started working")
- Session completion → task = `completed` (system comment; triggers parent notification if subtask)
- Session error → task = `error` (system comment with error details)
- If task has `parent_task_id` and transitions to `completed` → system comment posted on parent; parent agent notified

### Short Code Generation

- Per-owner monotonic counter (`task_sequence_counter` on `user` table), incremented atomically
- Prefix determined at creation: team's `task_prefix` if task has `team_id` and team has non-null prefix; otherwise `"TASK"`
- Format: `{prefix}-{counter}` (e.g., `TASK-1`, `HR-42`)
- Counter is global per owner — the 42nd task of any prefix is the user's 42nd overall task
- Short codes are globally unique per owner

### Comment Types

| Type | Description | Author |
|------|-------------|--------|
| `message` | Regular user or agent comment | User or agent |
| `result` | Agent final result / deliverable (semantically tagged) | Agent |
| `status_change` | Auto-generated on every status transition | System |
| `assignment` | Auto-generated on task assignment change | System |
| `system` | Platform notifications (subtask completion, etc.) | System |

### Task Attachments

- Files from agent workspaces are fetched by the backend from the agent-env HTTP API and stored in `backend/data/uploads/{owner_id}/task_attachments/{attachment_id}/{filename}`
- Files persist in backend storage even when the agent environment is stopped or rebuilt
- `source_agent_id` and `source_workspace_path` record provenance ("generated by Recruiting Agent at `output/report.csv`")
- Attachments can be linked to a specific comment (`comment_id`) or standalone on the task
- Download endpoint: `GET /api/v1/tasks/{task_id}/attachments/{attachment_id}/download`

### Subtask Rules

- Only agents in a **team context** can create subtasks (requires `team_id` on parent task)
- Delegation is topology-constrained: the creating agent's node must have a directed connection to the target node in the team graph
- Orphaned subtasks become root tasks on parent delete (SET NULL, not CASCADE)
- Subtask inherits `team_id` and `owner_id` from parent; gets its own short code with the team prefix

### Refinement Rules

- `original_message` is immutable after creation (audit trail)
- `refinement_history` is append-only
- Refinement uses the target agent's `workflow_prompt` as AI context
- Last 5 history items are passed to the AI refiner for context

### Execution Rules

- Task must have a selected agent to execute
- Agent must have an active environment to execute
- Archived tasks cannot be re-executed without first becoming active

### Todo Progress Tracking

- When agent calls TodoWrite tool during execution, progress is captured
- Stored on both Session and InputTask for persistence and display
- Real-time updates via `TASK_TODO_UPDATED` event

## Architecture Overview

```
User → Frontend → Backend API → InputTaskService → SessionService
                      │
                      ├── Refine: AIFunctionsService → TaskRefiner (LLM)
                      ├── Execute: SessionService.create_session(source_task_id)
                      ├── Comments: TaskCommentService
                      └── Attachments: TaskAttachmentService ←→ Agent Environment HTTP API

Task (1) ──────────────────────────────────────> (N) Session
        source_task_id (authoritative FK)

Task (1) ──────────────────────────────────────> (N) TaskComment
Task (1) ──────────────────────────────────────> (N) TaskAttachment
Task (1) ──────────────────────────────────────> (N) TaskStatusHistory
Task (1, parent) ──────────────────────────────> (N) Task (subtasks, parent_task_id)

Agent Collaboration (team context):
Parent Task ──create_subtask──> Subtask ──auto_execute──> Target Agent Session
      ↑                                                           │
      └──── system comment on parent ◄── session completed ───────┘
```

## Integration Points

- **Agent Handover**: Source agent uses `mcp__agent_task__create_task` to create tasks for direct handover or inbox — see [Agent Handover](../../agents/agent_handover/agent_handover.md)
- **Agentic Teams**: Team-scoped tasks use the team's `task_prefix`; subtask delegation follows team topology — see [Agentic Teams](../../agentic_teams/agentic_teams/agentic_teams.md)
- **Sessions**: Task execution creates sessions with `source_task_id` backlink; session lifecycle events drive automatic status updates — see [Agent Sessions](../agent_sessions/agent_sessions.md)
- **Agent Environment Core**: Six MCP tools (`mcp__agent_task__*`) let agents interact with tasks from inside environments — see [Agent Environment Core](../../agents/agent_environment_core/agent_environment_core.md)
- **Task Triggers**: Automated rules (CRON, webhook, date) that fire task execution; gains short-codes automatically — see [Task Triggers](task_triggers.md)
- **Activities**: Session state events generate activities for user notification — see [Agent Activities](../agent_activities/agent_activities.md)
- **Email Integration**: Incoming emails can create tasks automatically — see [Email Integration](../email_integration/email_integration.md)
- **File Management**: Task attachments use the same storage infrastructure as agent file management — see [Agent File Management](../../agents/agent_file_management/agent_file_management.md)
- **Real-time Events**: `TASK_COMMENT_ADDED`, `TASK_STATUS_CHANGED`, `TASK_ATTACHMENT_ADDED`, `SUBTASK_COMPLETED` events notify the frontend — see [Real-time Events](../realtime_events/event_bus_system.md)
