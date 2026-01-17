"""
Input Task Service - handles task creation, retrieval, updates, and status management.
"""
from uuid import UUID
from datetime import datetime
import logging
from typing import Optional
from sqlmodel import Session as DBSession, select
from sqlalchemy.orm.attributes import flag_modified

from app.models import (
    InputTask,
    InputTaskCreate,
    InputTaskUpdate,
    InputTaskStatus,
    Agent,
)

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
