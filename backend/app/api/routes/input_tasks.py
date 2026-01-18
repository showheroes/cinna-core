"""
Input Tasks API routes.

Provides CRUD operations for input task management.
"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    InputTaskCreate,
    InputTaskUpdate,
    InputTaskPublic,
    InputTaskPublicExtended,
    InputTasksPublicExtended,
    InputTaskStatus,
    RefineTaskRequest,
    RefineTaskResponse,
    ExecuteTaskRequest,
    ExecuteTaskResponse,
    SessionsPublic,
    SessionPublic,
    Message,
)
from app.services.input_task_service import (
    InputTaskService,
    InputTaskError,
    TaskNotFoundError,
    AgentNotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.services.session_service import SessionService

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _handle_service_error(e: InputTaskError) -> None:
    """Convert service exceptions to HTTP exceptions."""
    raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/", response_model=InputTaskPublic)
def create_task(
    *, session: SessionDep, current_user: CurrentUser, task_in: InputTaskCreate
) -> Any:
    """
    Create a new input task.
    """
    try:
        # Verify agent access if specified
        if task_in.selected_agent_id:
            InputTaskService.verify_agent_access(
                db_session=session,
                agent_id=task_in.selected_agent_id,
                user_id=current_user.id,
            )

        task = InputTaskService.create_task(
            db_session=session, user_id=current_user.id, data=task_in
        )
        return task
    except InputTaskError as e:
        _handle_service_error(e)


@router.get("/", response_model=InputTasksPublicExtended)
def list_tasks(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    status: str | None = None,
    user_workspace_id: str | None = None,
) -> Any:
    """
    List user's input tasks.

    Args:
        skip: Number of records to skip
        limit: Number of records to return
        status: Filter by status. Can be:
            - "active": NEW, REFINING, RUNNING, PENDING_INPUT, ERROR
            - "completed": COMPLETED
            - "archived": ARCHIVED
            - "all": No filter
            - Specific status name (e.g., "new", "running")
        user_workspace_id: Optional workspace filter
            - None (not provided): returns all tasks
            - Empty string (""): filters for default workspace (NULL)
            - UUID string: filters for that workspace
    """
    try:
        data, count = InputTaskService.list_tasks_extended(
            db_session=session,
            user_id=current_user.id,
            status=status,
            user_workspace_id=user_workspace_id,
            skip=skip,
            limit=limit,
        )
        return InputTasksPublicExtended(data=data, count=count)
    except InputTaskError as e:
        _handle_service_error(e)


@router.get("/{id}", response_model=InputTaskPublicExtended)
def get_task(session: SessionDep, current_user: CurrentUser, id: uuid.UUID) -> Any:
    """
    Get a single input task with details.
    """
    try:
        return InputTaskService.get_task_extended(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )
    except InputTaskError as e:
        _handle_service_error(e)


@router.patch("/{id}", response_model=InputTaskPublic)
def update_task(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    task_in: InputTaskUpdate,
) -> Any:
    """
    Update an input task.
    """
    try:
        # Get task with ownership check
        task = InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )

        # Verify agent access if being updated
        if task_in.selected_agent_id:
            InputTaskService.verify_agent_access(
                db_session=session,
                agent_id=task_in.selected_agent_id,
                user_id=current_user.id,
            )

        updated_task = InputTaskService.update_task(
            db_session=session, task=task, data=task_in
        )
        return updated_task
    except InputTaskError as e:
        _handle_service_error(e)


@router.delete("/{id}")
def delete_task(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Message:
    """
    Delete an input task.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )
        InputTaskService.delete_task(db_session=session, task=task)
        return Message(message="Task deleted successfully")
    except InputTaskError as e:
        _handle_service_error(e)


@router.post("/{id}/refine", response_model=RefineTaskResponse)
def refine_task(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    refine_in: RefineTaskRequest,
) -> Any:
    """
    Refine a task description with AI assistance.

    Uses AI to improve the task description based on user's feedback or comments.
    Appends the conversation to refinement_history.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )

        result = InputTaskService.refine_task(
            db_session=session,
            task=task,
            user_id=current_user.id,
            user_comment=refine_in.user_comment,
            user_selected_text=refine_in.user_selected_text,
        )

        return RefineTaskResponse(
            success=result["success"],
            refined_description=result.get("refined_description"),
            feedback_message=result.get("feedback_message"),
            error=result.get("error"),
        )
    except InputTaskError as e:
        _handle_service_error(e)


@router.post("/{id}/execute", response_model=ExecuteTaskResponse)
def execute_task(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    execute_in: ExecuteTaskRequest,
) -> Any:
    """
    Execute a task by creating a session and sending the task description as the initial message.

    Requires a selected_agent_id to be set on the task.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )

        success, new_session, error = InputTaskService.execute_task_sync(
            db_session=session,
            task=task,
            user_id=current_user.id,
            mode=execute_in.mode,
        )

        if not success:
            return ExecuteTaskResponse(success=False, error=error)

        return ExecuteTaskResponse(success=True, session_id=new_session.id)
    except InputTaskError as e:
        _handle_service_error(e)


@router.post("/{id}/archive", response_model=InputTaskPublic)
def archive_task(
    session: SessionDep, current_user: CurrentUser, id: uuid.UUID
) -> Any:
    """
    Archive a completed or error task.
    """
    try:
        task = InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )

        updated_task = InputTaskService.update_status(
            db_session=session, task=task, status=InputTaskStatus.ARCHIVED
        )
        return updated_task
    except InputTaskError as e:
        _handle_service_error(e)


@router.get("/{id}/sessions", response_model=SessionsPublic)
def list_task_sessions(
    session: SessionDep,
    current_user: CurrentUser,
    id: uuid.UUID,
    skip: int = 0,
    limit: int = 20,
) -> Any:
    """
    List all sessions spawned by this task.

    A single task can trigger multiple sessions (e.g., retries, re-runs).
    """
    try:
        # Verify task exists and user has access
        InputTaskService.get_task_with_ownership_check(
            db_session=session,
            task_id=id,
            user_id=current_user.id,
        )

        sessions = SessionService.list_task_sessions(
            db_session=session, task_id=id, limit=limit, offset=skip
        )

        return SessionsPublic(
            data=[SessionPublic(**s.model_dump()) for s in sessions],
            count=len(sessions),
        )
    except InputTaskError as e:
        _handle_service_error(e)
