"""
Agent Task API Routes — internal endpoints called by MCP tools in agent environments.

Authentication: These endpoints use the same Bearer token auth as other agent-facing
endpoints (CurrentUser resolves agent identity via JWT token created per-session).

Agent identity is resolved via task.selected_agent_id (the agent assigned to the task).
The caller authenticates as the task owner using their JWT; the agent identity is then
derived from the task record itself.

Routes:
  POST  /agent/tasks/{task_id}/comment    — Agent posts comment (with optional files)
  POST  /agent/tasks/{task_id}/status     — Agent updates task status (edge cases)
  POST  /agent/tasks/{task_id}/subtask    — Agent creates subtask (team context)
  GET   /agent/tasks/my-tasks             — Agent lists assigned tasks
  GET   /agent/tasks/{task_id}/details    — Agent gets task detail
"""
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    InputTasksPublicExtended,
    AgentTaskStatusUpdate,
    AgentSubtaskCreate,
    AgentTaskOperationResponse,
    AgentTaskCommentCreate,
    TaskCommentPublic,
)
from app.services.input_task_service import (
    InputTaskService,
    InputTaskError,
    ValidationError,
)
from app.services.task_comment_service import TaskCommentService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["agent-tasks"])


def _handle_error(e: InputTaskError) -> None:
    """Convert service exceptions to HTTP exceptions."""
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/agent/tasks/{task_id}/comment", response_model=TaskCommentPublic)
async def agent_add_comment(
    *,
    db_session: SessionDep,
    current_user: CurrentUser,
    task_id: uuid.UUID,
    data: AgentTaskCommentCreate,
) -> Any:
    """
    Agent posts a comment on a task (with optional workspace file attachments).

    Called by the mcp__agent_task__add_comment MCP tool.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=db_session,
            task_id=task_id,
            user_id=current_user.id,
        )
        comment = TaskCommentService.add_comment_from_agent(
            db_session=db_session,
            task_id=task_id,
            agent_id=task.selected_agent_id,
            data=data,
        )
        return TaskCommentService._to_public(db_session, comment)
    except InputTaskError as e:
        _handle_error(e)


@router.post("/agent/tasks/{task_id}/status", response_model=AgentTaskOperationResponse)
async def agent_update_status(
    *,
    db_session: SessionDep,
    current_user: CurrentUser,
    task_id: uuid.UUID,
    data: AgentTaskStatusUpdate,
) -> Any:
    """
    Agent explicitly updates task status.

    Only for edge cases: blocked, completed (explicit), cancelled.
    Standard transitions (in_progress, completed) are handled automatically
    by the backend session lifecycle events.

    Called by the mcp__agent_task__update_status MCP tool.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=db_session,
            task_id=task_id,
            user_id=current_user.id,
        )
        if not task.selected_agent_id:
            raise ValidationError("Task has no assigned agent")

        updated = InputTaskService.update_task_status_from_agent(
            db_session=db_session,
            task_id=task_id,
            agent_id=task.selected_agent_id,
            data=data,
        )
        return AgentTaskOperationResponse(
            success=True,
            task=updated.short_code,
            message=f"Status updated to {data.status}",
        )
    except InputTaskError as e:
        _handle_error(e)


@router.post("/agent/tasks/{task_id}/subtask", response_model=AgentTaskOperationResponse)
async def agent_create_subtask(
    *,
    db_session: SessionDep,
    current_user: CurrentUser,
    task_id: uuid.UUID,
    data: AgentSubtaskCreate,
) -> Any:
    """
    Agent creates a subtask (team context required).

    Validates team membership and connection topology before creating the subtask.

    Called by the mcp__agent_task__create_subtask MCP tool.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=db_session,
            task_id=task_id,
            user_id=current_user.id,
        )
        if not task.selected_agent_id:
            raise ValidationError("Task has no assigned agent")

        subtask = InputTaskService.create_subtask(
            db_session=db_session,
            parent_task_id=task_id,
            creating_agent_id=task.selected_agent_id,
            data=data,
        )
        return AgentTaskOperationResponse(
            success=True,
            task=subtask.short_code,
            message=f"Subtask {subtask.short_code} created",
        )
    except InputTaskError as e:
        _handle_error(e)


@router.get("/agent/tasks/my-tasks", response_model=InputTasksPublicExtended)
def agent_list_tasks(
    db_session: SessionDep,
    current_user: CurrentUser,
    status: str | None = None,
    scope: str = "assigned",
) -> Any:
    """
    Agent lists tasks assigned to them or created by them.

    scope values:
    - "assigned" (default): tasks where selected_agent_id matches the calling agent
    - "created": tasks created by this agent (agent_initiated=True from this agent)
    - "team": all tasks in the agent's team

    Called by the mcp__agent_task__list_tasks MCP tool.
    """
    try:
        data, count = InputTaskService.list_agent_tasks(
            db_session=db_session,
            user_id=current_user.id,
            status=status,
            scope=scope,
        )
        return InputTasksPublicExtended(data=data, count=count)
    except InputTaskError as e:
        _handle_error(e)


@router.get("/agent/tasks/{task_id}/details")
def agent_get_task_details(
    db_session: SessionDep,
    current_user: CurrentUser,
    task_id: uuid.UUID,
) -> Any:
    """
    Agent gets full task details including recent comments and subtask progress.

    Called by the mcp__agent_task__get_details MCP tool.
    Returns a simplified view optimized for agent consumption.
    """
    try:
        return InputTaskService.get_agent_task_details(
            db_session=db_session,
            task_id=task_id,
            user_id=current_user.id,
        )
    except InputTaskError as e:
        _handle_error(e)
