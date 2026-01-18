"""
Input Task Service - handles task creation, retrieval, updates, and status management.
"""
from uuid import UUID
from datetime import datetime
import logging
from typing import Any, Optional
from sqlmodel import Session as DBSession, select
from sqlalchemy.orm.attributes import flag_modified

from app.models import (
    InputTask,
    InputTaskCreate,
    InputTaskUpdate,
    InputTaskStatus,
    Agent,
    Session,
    SessionMessage,
)
from app.core.db import engine

logger = logging.getLogger(__name__)


class InputTaskService:
    @staticmethod
    def create_task(
        db_session: DBSession,
        user_id: UUID,
        data: InputTaskCreate,
    ) -> InputTask:
        """
        Create a new input task.

        Args:
            db_session: Database session
            user_id: User ID creating the task
            data: Task creation data
        """
        task = InputTask(
            owner_id=user_id,
            original_message=data.original_message,
            current_description=data.original_message,  # Start with same as original
            selected_agent_id=data.selected_agent_id,
            user_workspace_id=data.user_workspace_id,
            status=InputTaskStatus.NEW,
            refinement_history=[],
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def get_task(db_session: DBSession, task_id: UUID) -> Optional[InputTask]:
        """Get task by ID"""
        return db_session.get(InputTask, task_id)

    @staticmethod
    def get_task_with_agent(
        db_session: DBSession, task_id: UUID
    ) -> Optional[tuple[InputTask, str | None]]:
        """Get task with agent name"""
        statement = (
            select(InputTask, Agent.name)
            .outerjoin(Agent, InputTask.selected_agent_id == Agent.id)
            .where(InputTask.id == task_id)
        )
        result = db_session.exec(statement).first()
        if not result:
            return None
        return result  # (task, agent_name)

    @staticmethod
    def list_tasks(
        db_session: DBSession,
        user_id: UUID,
        status_filter: list[str] | None = None,
        user_workspace_id: UUID | None = None,
        apply_workspace_filter: bool = False,
        skip: int = 0,
        limit: int = 100,
        order_desc: bool = True,
    ) -> tuple[list[tuple[InputTask, str | None]], int]:
        """
        List user's tasks with agent names.

        Args:
            db_session: Database session
            user_id: User ID
            status_filter: Optional list of statuses to filter by
            user_workspace_id: Optional workspace filter
            apply_workspace_filter: If True, filter by workspace (None means default workspace)
            skip: Number of records to skip
            limit: Number of records to return
            order_desc: Order by created_at descending

        Returns:
            Tuple of (list of (task, agent_name) tuples, total count)
        """
        # Base query with outer join to get agent name
        statement = (
            select(InputTask, Agent.name)
            .outerjoin(Agent, InputTask.selected_agent_id == Agent.id)
            .where(InputTask.owner_id == user_id)
        )

        # Apply status filter
        if status_filter:
            statement = statement.where(InputTask.status.in_(status_filter))

        # Apply workspace filter
        if apply_workspace_filter:
            statement = statement.where(InputTask.user_workspace_id == user_workspace_id)

        # Get count before pagination
        count_statement = statement.with_only_columns(InputTask.id)

        # Add ordering
        if order_desc:
            statement = statement.order_by(InputTask.created_at.desc())
        else:
            statement = statement.order_by(InputTask.created_at.asc())

        # Add pagination
        statement = statement.offset(skip).limit(limit)

        results = db_session.exec(statement).all()
        count = len(db_session.exec(count_statement).all())

        return results, count

    @staticmethod
    def update_task(
        db_session: DBSession,
        task: InputTask,
        data: InputTaskUpdate,
    ) -> InputTask:
        """
        Update task fields.

        Args:
            db_session: Database session
            task: Task to update
            data: Update data
        """
        update_dict = data.model_dump(exclude_unset=True)
        task.sqlmodel_update(update_dict)
        task.updated_at = datetime.utcnow()

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def update_description(
        db_session: DBSession,
        task: InputTask,
        new_description: str,
    ) -> InputTask:
        """Update task description"""
        task.current_description = new_description
        task.updated_at = datetime.utcnow()

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def update_status(
        db_session: DBSession,
        task: InputTask,
        status: str,
        error_message: str | None = None,
    ) -> InputTask:
        """Update task status"""
        task.status = status
        task.updated_at = datetime.utcnow()

        if error_message:
            task.error_message = error_message
        elif status != InputTaskStatus.ERROR:
            task.error_message = None

        # Update timestamps based on status
        if status == InputTaskStatus.RUNNING:
            task.executed_at = datetime.utcnow()
        elif status == InputTaskStatus.COMPLETED:
            task.completed_at = datetime.utcnow()
        elif status == InputTaskStatus.ARCHIVED:
            task.archived_at = datetime.utcnow()

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def append_to_refinement_history(
        db_session: DBSession,
        task: InputTask,
        role: str,
        content: str,
    ) -> InputTask:
        """
        Append a message to refinement history.

        Args:
            db_session: Database session
            task: Task to update
            role: "user" or "ai"
            content: Message content
        """
        history_item = {
            "role": role,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }

        if task.refinement_history is None:
            task.refinement_history = []

        task.refinement_history.append(history_item)
        flag_modified(task, "refinement_history")
        task.updated_at = datetime.utcnow()

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def link_session(
        db_session: DBSession,
        task: InputTask,
        session_id: UUID,
    ) -> InputTask:
        """Link a session to the task"""
        task.session_id = session_id
        task.status = InputTaskStatus.RUNNING
        task.executed_at = datetime.utcnow()
        task.updated_at = datetime.utcnow()

        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    @staticmethod
    def delete_task(db_session: DBSession, task: InputTask) -> None:
        """Delete a task"""
        db_session.delete(task)
        db_session.commit()

    # Status sync methods - compute and sync task status from connected sessions

    @staticmethod
    def compute_status_from_sessions(db_session: DBSession, task_id: UUID) -> str | None:
        """
        Compute task status from all connected sessions.

        Status computation logic (priority order):
        - If ANY session has status='error' → ERROR
        - If ANY session has unanswered tool_questions → PENDING_INPUT
        - If ANY session is active with interaction_status='running' → RUNNING
        - If ALL sessions are completed → COMPLETED
        - Otherwise → RUNNING (active but not streaming)

        Args:
            db_session: Database session
            task_id: Task UUID

        Returns:
            Computed status string, or None if no sessions connected
        """
        # Query all sessions connected to this task
        sessions = db_session.exec(
            select(Session).where(Session.source_task_id == task_id)
        ).all()

        if not sessions:
            return None

        has_error = False
        has_pending_input = False
        has_running = False
        all_completed = True

        for session in sessions:
            # Check for error status
            if session.status == "error":
                has_error = True
                continue

            # Check if session is not completed
            if session.status != "completed":
                all_completed = False

            # Check for running interaction
            if session.interaction_status == "running":
                has_running = True

            # Check for unanswered tool questions in this session
            unanswered_count = db_session.exec(
                select(SessionMessage)
                .where(SessionMessage.session_id == session.id)
                .where(SessionMessage.tool_questions_status == "unanswered")
            ).first()

            if unanswered_count:
                has_pending_input = True

        # Apply priority: error > pending_input > running > completed
        if has_error:
            return InputTaskStatus.ERROR
        if has_pending_input:
            return InputTaskStatus.PENDING_INPUT
        if has_running:
            return InputTaskStatus.RUNNING
        if all_completed:
            return InputTaskStatus.COMPLETED

        # Default: session exists but not streaming
        return InputTaskStatus.RUNNING

    @staticmethod
    def sync_task_status_from_sessions(
        db_session: DBSession,
        task_id: UUID,
        force_status: str | None = None,
    ) -> InputTask | None:
        """
        Sync task status from connected sessions.

        Only syncs for tasks in execution phase (running, pending_input, completed, error).
        Does NOT override: new, refining, archived statuses.

        Args:
            db_session: Database session
            task_id: Task UUID
            force_status: Optional status to force (skips computation)

        Returns:
            Updated task or None if task not found or status unchanged
        """
        task = db_session.get(InputTask, task_id)
        if not task:
            return None

        # Only sync for tasks in execution phase
        execution_statuses = [
            InputTaskStatus.RUNNING,
            InputTaskStatus.PENDING_INPUT,
            InputTaskStatus.COMPLETED,
            InputTaskStatus.ERROR,
        ]

        if task.status not in execution_statuses:
            # Task is in new, refining, or archived - don't override
            return None

        # Compute or use forced status
        new_status = force_status or InputTaskService.compute_status_from_sessions(
            db_session, task_id
        )

        if not new_status or new_status == task.status:
            # No change needed
            return None

        # Update task status
        return InputTaskService.update_status(
            db_session=db_session,
            task=task,
            status=new_status,
        )

    # Event handlers for streaming lifecycle events

    @staticmethod
    async def handle_stream_started(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_STARTED events and sync task status to RUNNING.

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")

            if not session_id:
                logger.debug("STREAM_STARTED event missing session_id, skipping task sync")
                return

            with DBSession(engine) as db:
                # Get session to find source_task_id
                session = db.get(Session, UUID(session_id))
                if not session or not session.source_task_id:
                    return  # Session not linked to a task

                task = db.get(InputTask, session.source_task_id)
                if not task:
                    return

                # Only update if task is in execution phase
                if task.status in [
                    InputTaskStatus.RUNNING,
                    InputTaskStatus.PENDING_INPUT,
                    InputTaskStatus.COMPLETED,
                    InputTaskStatus.ERROR,
                ]:
                    InputTaskService.update_status(
                        db_session=db,
                        task=task,
                        status=InputTaskStatus.RUNNING,
                    )
                    logger.info(f"Task {task.id} status synced to RUNNING (STREAM_STARTED)")

        except Exception as e:
            logger.error(f"Error handling STREAM_STARTED for task sync: {e}", exc_info=True)

    @staticmethod
    async def handle_stream_completed(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_COMPLETED events and compute task status from sessions.

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")

            if not session_id:
                logger.debug("STREAM_COMPLETED event missing session_id, skipping task sync")
                return

            with DBSession(engine) as db:
                # Get session to find source_task_id
                session = db.get(Session, UUID(session_id))
                if not session or not session.source_task_id:
                    return  # Session not linked to a task

                updated_task = InputTaskService.sync_task_status_from_sessions(
                    db_session=db,
                    task_id=session.source_task_id,
                )

                if updated_task:
                    logger.info(
                        f"Task {updated_task.id} status synced to {updated_task.status} (STREAM_COMPLETED)"
                    )

        except Exception as e:
            logger.error(f"Error handling STREAM_COMPLETED for task sync: {e}", exc_info=True)

    @staticmethod
    async def handle_stream_error(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_ERROR events and sync task status to ERROR.

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")
            error_message = meta.get("error_message", "Unknown error")

            if not session_id:
                logger.debug("STREAM_ERROR event missing session_id, skipping task sync")
                return

            with DBSession(engine) as db:
                # Get session to find source_task_id
                session = db.get(Session, UUID(session_id))
                if not session or not session.source_task_id:
                    return  # Session not linked to a task

                task = db.get(InputTask, session.source_task_id)
                if not task:
                    return

                # Only update if task is in execution phase
                if task.status in [
                    InputTaskStatus.RUNNING,
                    InputTaskStatus.PENDING_INPUT,
                    InputTaskStatus.COMPLETED,
                    InputTaskStatus.ERROR,
                ]:
                    InputTaskService.update_status(
                        db_session=db,
                        task=task,
                        status=InputTaskStatus.ERROR,
                        error_message=error_message,
                    )
                    logger.info(f"Task {task.id} status synced to ERROR (STREAM_ERROR)")

        except Exception as e:
            logger.error(f"Error handling STREAM_ERROR for task sync: {e}", exc_info=True)
