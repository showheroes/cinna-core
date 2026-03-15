"""
Agent Collaboration Service — fan-out / fan-in multi-agent coordination.

A coordinator agent creates a collaboration by dispatching subtasks to multiple
target agents simultaneously. Each subtask is an InputTask/Session pair. As
subtasks complete and report state via update_session_state, the collaboration
tracks progress and marks itself complete when all subtasks finish.
"""
from uuid import UUID
from datetime import UTC, datetime
import logging

from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import Session, select

from app.models.agent_collaboration import (
    AgentCollaboration,
    CollaborationSubtask,
    AgentCollaborationPublic,
    CollaborationSubtaskPublic,
)
from app.models import Agent, User, Session as ChatSession

logger = logging.getLogger(__name__)

# Valid subtask status transitions
SUBTASK_TERMINAL_STATUSES = {"completed", "error"}
COLLABORATION_TERMINAL_STATUSES = {"completed", "error"}


class AgentCollaborationError(Exception):
    """Base exception for collaboration service errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentCollaborationService:

    @staticmethod
    async def create_collaboration(
        session: Session,
        user: User,
        coordinator_agent_id: UUID,
        source_session_id: UUID | None,
        title: str,
        description: str | None,
        subtasks: list[dict],
    ) -> AgentCollaboration:
        """
        Create a multi-agent collaboration by dispatching subtasks to target agents.

        For each subtask entry in `subtasks`:
          1. Validates the target agent exists and belongs to the user.
          2. Creates a CollaborationSubtask record.
          3. Calls AgentService.create_agent_task() to dispatch the task immediately.
          4. Links back the created InputTask id and Session id.

        Args:
            session: Database session.
            user: Authenticated user (coordinator owner).
            coordinator_agent_id: UUID of the coordinator agent.
            source_session_id: UUID of the coordinator's current session (optional).
            title: Short title for this collaboration.
            description: Longer description of the overall goal (optional).
            subtasks: List of dicts with keys: target_agent_id (str), task_message (str),
                      and optional order (int).

        Returns:
            The created AgentCollaboration with subtasks eager-loaded.

        Raises:
            AgentCollaborationError: If any validation fails.
        """
        from app.services.agent_service import AgentService

        if not subtasks:
            raise AgentCollaborationError("At least one subtask is required")

        # Validate coordinator agent
        coordinator = session.get(Agent, coordinator_agent_id)
        if not coordinator:
            raise AgentCollaborationError("Coordinator agent not found", 404)
        if coordinator.owner_id != user.id:
            raise AgentCollaborationError("Not enough permissions", 403)

        # Create AgentCollaboration record
        collaboration = AgentCollaboration(
            title=title,
            description=description,
            status="in_progress",
            coordinator_agent_id=coordinator_agent_id,
            source_session_id=source_session_id,
            shared_context={"findings": []},
            owner_id=user.id,
        )
        session.add(collaboration)
        session.commit()
        session.refresh(collaboration)

        logger.info(
            f"Created collaboration {collaboration.id} with {len(subtasks)} subtasks "
            f"for coordinator agent {coordinator_agent_id}"
        )

        # Process each subtask
        for i, subtask_data in enumerate(subtasks):
            target_agent_id_raw = subtask_data.get("target_agent_id")
            task_message = subtask_data.get("task_message", "").strip()
            order = subtask_data.get("order", i)

            if not target_agent_id_raw:
                logger.warning(f"Subtask {i} missing target_agent_id, skipping")
                continue
            if not task_message:
                logger.warning(f"Subtask {i} missing task_message, skipping")
                continue

            try:
                target_agent_id = UUID(str(target_agent_id_raw))
            except (ValueError, AttributeError):
                logger.warning(f"Subtask {i} invalid target_agent_id: {target_agent_id_raw}")
                continue

            # Validate target agent
            target_agent = session.get(Agent, target_agent_id)
            if not target_agent or target_agent.owner_id != user.id:
                logger.warning(f"Subtask {i}: target agent {target_agent_id} not found or not owned by user")
                continue

            # Create the subtask record (pending until dispatched)
            subtask = CollaborationSubtask(
                collaboration_id=collaboration.id,
                target_agent_id=target_agent_id,
                task_message=task_message,
                status="pending",
                order=order,
            )
            session.add(subtask)
            session.commit()
            session.refresh(subtask)

            # Dispatch via AgentService.create_agent_task (auto_execute=True)
            try:
                success, task_id, new_session_id, error = await AgentService.create_agent_task(
                    session=session,
                    user=user,
                    task_message=task_message,
                    source_session_id=source_session_id,
                    target_agent_id=target_agent_id,
                    target_agent_name=target_agent.name,
                )

                if success and task_id and new_session_id:
                    subtask.input_task_id = task_id
                    subtask.session_id = new_session_id
                    subtask.status = "running"
                    logger.info(
                        f"Dispatched subtask {subtask.id} to agent {target_agent_id}: "
                        f"task={task_id}, session={new_session_id}"
                    )
                else:
                    subtask.status = "error"
                    subtask.result_summary = error or "Failed to dispatch task"
                    logger.error(
                        f"Failed to dispatch subtask {subtask.id} to agent {target_agent_id}: {error}"
                    )
            except Exception as e:
                subtask.status = "error"
                subtask.result_summary = str(e)
                logger.error(
                    f"Exception dispatching subtask {subtask.id} to agent {target_agent_id}: {e}",
                    exc_info=True,
                )

            subtask.updated_at = datetime.now(UTC)
            session.add(subtask)
            session.commit()

        # Refresh to load subtasks
        session.refresh(collaboration)
        return collaboration

    @staticmethod
    def post_finding(
        session: Session,
        collaboration_id: UUID,
        agent_id: UUID,
        finding: str,
    ) -> list[str]:
        """
        Append a finding to the collaboration's shared_context["findings"] list.

        Args:
            session: Database session.
            collaboration_id: Target collaboration UUID.
            agent_id: The agent posting the finding (used for attribution).
            finding: The finding text to append.

        Returns:
            Updated list of all findings.

        Raises:
            AgentCollaborationError: If collaboration not found or agent is not a participant.
        """
        collaboration = session.get(AgentCollaboration, collaboration_id)
        if not collaboration:
            raise AgentCollaborationError("Collaboration not found", 404)

        # Verify the agent is a participant (subtask target or coordinator)
        is_coordinator = collaboration.coordinator_agent_id == agent_id
        is_participant = is_coordinator or any(
            st.target_agent_id == agent_id for st in collaboration.subtasks
        )
        if not is_participant:
            raise AgentCollaborationError("Agent is not a participant in this collaboration", 403)

        # Append finding with attribution
        agent = session.get(Agent, agent_id)
        agent_name = agent.name if agent else str(agent_id)

        finding_entry = f"[{agent_name}] {finding.strip()}"

        if not collaboration.shared_context:
            collaboration.shared_context = {"findings": []}

        findings = collaboration.shared_context.get("findings", [])
        findings.append(finding_entry)
        collaboration.shared_context["findings"] = findings
        collaboration.updated_at = datetime.now(UTC)

        flag_modified(collaboration, "shared_context")
        session.add(collaboration)
        session.commit()

        logger.info(
            f"Agent {agent_id} posted finding to collaboration {collaboration_id}: "
            f"{finding[:80]}..."
        )

        return findings

    @staticmethod
    def get_collaboration_status(
        session: Session,
        collaboration_id: UUID,
        user_id: UUID,
    ) -> AgentCollaborationPublic:
        """
        Return full collaboration status including all subtasks.

        Args:
            session: Database session.
            collaboration_id: Target collaboration UUID.
            user_id: Requesting user (for ownership check).

        Returns:
            AgentCollaborationPublic with subtask details and agent names.

        Raises:
            AgentCollaborationError: If not found or permission denied.
        """
        collaboration = session.get(AgentCollaboration, collaboration_id)
        if not collaboration:
            raise AgentCollaborationError("Collaboration not found", 404)
        if collaboration.owner_id != user_id:
            raise AgentCollaborationError("Not enough permissions", 403)

        subtask_publics = []
        for subtask in collaboration.subtasks:
            target_agent = session.get(Agent, subtask.target_agent_id)
            subtask_publics.append(
                CollaborationSubtaskPublic(
                    id=subtask.id,
                    collaboration_id=subtask.collaboration_id,
                    target_agent_id=subtask.target_agent_id,
                    target_agent_name=target_agent.name if target_agent else None,
                    task_message=subtask.task_message,
                    status=subtask.status,
                    result_summary=subtask.result_summary,
                    input_task_id=subtask.input_task_id,
                    session_id=subtask.session_id,
                    order=subtask.order,
                    created_at=subtask.created_at,
                    updated_at=subtask.updated_at,
                )
            )

        return AgentCollaborationPublic(
            id=collaboration.id,
            title=collaboration.title,
            description=collaboration.description,
            status=collaboration.status,
            coordinator_agent_id=collaboration.coordinator_agent_id,
            source_session_id=collaboration.source_session_id,
            shared_context=collaboration.shared_context or {},
            owner_id=collaboration.owner_id,
            created_at=collaboration.created_at,
            updated_at=collaboration.updated_at,
            subtasks=subtask_publics,
        )

    @staticmethod
    def handle_subtask_state_update(
        session: Session,
        subtask_session_id: UUID,
        state: str,
        summary: str,
    ) -> tuple[bool, bool]:
        """
        Update a subtask's status based on a session state report.

        Called from the auto-feedback hook in InputTaskService when a session
        belonging to a collaboration subtask reports its state.

        Args:
            session: Database session.
            subtask_session_id: The session ID of the subtask.
            state: New state ("completed", "needs_input", "error").
            summary: Agent's result/question/error description.

        Returns:
            Tuple of (found: bool, collaboration_complete: bool).
            - found: True if a matching subtask was found.
            - collaboration_complete: True if all subtasks are now in terminal states.
        """
        # Find the subtask by session_id
        subtask = session.exec(
            select(CollaborationSubtask).where(
                CollaborationSubtask.session_id == subtask_session_id
            )
        ).first()

        if not subtask:
            return False, False

        # Map session state → subtask status
        status_map = {
            "completed": "completed",
            "needs_input": "needs_input",
            "error": "error",
        }
        subtask.status = status_map.get(state, state)
        subtask.result_summary = summary
        subtask.updated_at = datetime.now(UTC)
        session.add(subtask)
        session.commit()

        logger.info(
            f"Updated subtask {subtask.id} status to '{subtask.status}' "
            f"for collaboration {subtask.collaboration_id}"
        )

        # Check if all subtasks are in terminal states
        # Query fresh subtask statuses to avoid stale cache after the recent commit
        collaboration = session.get(AgentCollaboration, subtask.collaboration_id)
        if not collaboration or collaboration.status in COLLABORATION_TERMINAL_STATUSES:
            return True, False

        all_subtask_statuses = session.exec(
            select(CollaborationSubtask.status).where(
                CollaborationSubtask.collaboration_id == subtask.collaboration_id
            )
        ).all()

        all_terminal = all(s in SUBTASK_TERMINAL_STATUSES for s in all_subtask_statuses)

        if all_terminal:
            any_error = any(s == "error" for s in all_subtask_statuses)
            collaboration.status = "error" if any_error else "completed"
            collaboration.updated_at = datetime.now(UTC)
            session.add(collaboration)
            session.commit()

            logger.info(
                f"Collaboration {collaboration.id} marked as '{collaboration.status}' "
                f"(all {len(all_subtask_statuses)} subtasks terminal)"
            )
            return True, True

        return True, False

    @staticmethod
    def get_collaboration_by_session(
        session: Session,
        session_id: UUID,
    ) -> dict | None:
        """
        Find collaboration context for a participant session.

        Used by prompt injection to give agents awareness of the collaboration
        they are participating in.

        Args:
            session: Database session.
            session_id: Session UUID to look up.

        Returns:
            Dict with collaboration context keys, or None if not a collaboration session.
        """
        subtask = session.exec(
            select(CollaborationSubtask).where(
                CollaborationSubtask.session_id == session_id
            )
        ).first()

        if not subtask:
            return None

        collaboration = session.get(AgentCollaboration, subtask.collaboration_id)
        if not collaboration:
            return None

        # Build list of other participants
        other_participants = []
        for st in collaboration.subtasks:
            if st.id == subtask.id:
                continue
            agent = session.get(Agent, st.target_agent_id)
            if agent:
                other_participants.append(agent.name)

        return {
            "collaboration_id": str(collaboration.id),
            "collaboration_title": collaboration.title,
            "collaboration_description": collaboration.description or "",
            "collaboration_role": subtask.task_message,
            "collaboration_other_participants": other_participants,
            "subtask_id": str(subtask.id),
        }
