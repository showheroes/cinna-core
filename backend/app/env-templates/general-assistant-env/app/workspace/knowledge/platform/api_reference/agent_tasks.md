# Agent Tasks — API Reference

Auto-generated from OpenAPI spec. Tag: `agent-tasks`

## POST `/api/v1/agent/tasks/{task_id}/comment`
**Agent Add Comment**

**Path parameters:**
- `task_id`: uuid

**Request body** (`AgentTaskCommentCreate`):
  - `content`: string (required)
  - `comment_type`: string
  - `file_paths`: array | null

**Response:** `TaskCommentPublic`

---

## POST `/api/v1/agent/tasks/{task_id}/status`
**Agent Update Status**

**Path parameters:**
- `task_id`: uuid

**Request body** (`AgentTaskStatusUpdate`):
  - `status`: string (required)
  - `reason`: string | null
  - `task`: string | null

**Response:** `AgentTaskOperationResponse`

---

## POST `/api/v1/agent/tasks/{task_id}/subtask`
**Agent Create Subtask**

**Path parameters:**
- `task_id`: uuid

**Request body** (`AgentSubtaskCreate`):
  - `title`: string (required)
  - `description`: string | null
  - `assigned_to`: string | null
  - `priority`: string
  - `task`: string | null

**Response:** `AgentTaskOperationResponse`

---

## GET `/api/v1/agent/tasks/my-tasks`
**Agent List Tasks**

**Query parameters:**
- `status`: string | null
- `scope`: string, default: `assigned`

**Response:** `InputTasksPublicExtended`

---

## GET `/api/v1/agent/tasks/{task_id}/details`
**Agent Get Task Details**

**Path parameters:**
- `task_id`: uuid

---
