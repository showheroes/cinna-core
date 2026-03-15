"""
Agent Collaboration API Routes.

All endpoints use the same environment auth token as agent task creation
(Bearer AGENT_AUTH_TOKEN via CurrentUser), so the calling agent-env can
authenticate using its per-agent token.

Routes:
  POST   /agents/collaborations/create
  POST   /agents/collaborations/{id}/findings
  GET    /agents/collaborations/{id}/status
  GET    /agents/collaborations/by-session/{session_id}
"""
import uuid
import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Session as ChatSession,
)
from app.models.agent_collaboration import (
    AgentCollaborationPublic,
    PostFindingRequest,
    PostFindingResponse,
    CreateCollaborationRequest,
    CreateCollaborationResponse,
)
from app.services.agent_collaboration_service import (
    AgentCollaborationService,
    AgentCollaborationError,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents/collaborations", tags=["collaborations"])


@router.post("/create", response_model=CreateCollaborationResponse)
async def create_collaboration(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: CreateCollaborationRequest,
) -> Any:
    """
    Create a multi-agent collaboration (called by agent-env create_collaboration tool).

    Dispatches subtasks to all listed target agents simultaneously.
    The calling agent acts as coordinator. Each subtask is created as an
    InputTask with auto_execute=True.

    The source_session_id must be a valid session owned by the caller.
    """
    logger.info(
        f"Create collaboration from user {current_user.id}: "
        f"title='{data.title}', subtasks={len(data.subtasks)}, "
        f"source_session_id={data.source_session_id}"
    )

    # Resolve source_session_id
    source_session_id: uuid.UUID | None = None
    source_session: ChatSession | None = None
    if data.source_session_id:
        try:
            source_session_id = uuid.UUID(data.source_session_id)
        except ValueError:
            return CreateCollaborationResponse(
                success=False,
                error="Invalid source_session_id format",
            )

        source_session = session.get(ChatSession, source_session_id)
        if not source_session or source_session.user_id != current_user.id:
            return CreateCollaborationResponse(
                success=False,
                error="Source session not found or not accessible",
            )

    # Derive coordinator_agent_id from source session's environment
    coordinator_agent_id: uuid.UUID | None = None
    if source_session_id and source_session:
        if source_session.environment_id:
            from app.models import AgentEnvironment
            env = session.get(AgentEnvironment, source_session.environment_id)
            if env:
                coordinator_agent_id = env.agent_id

    if not coordinator_agent_id:
        # Fallback: try to find coordinator from subtask context — not ideal.
        # In practice source_session always provides the coordinator.
        return CreateCollaborationResponse(
            success=False,
            error="Could not determine coordinator agent from source session",
        )

    try:
        collaboration = await AgentCollaborationService.create_collaboration(
            session=session,
            user=current_user,
            coordinator_agent_id=coordinator_agent_id,
            source_session_id=source_session_id,
            title=data.title,
            description=data.description,
            subtasks=data.subtasks,
        )

        return CreateCollaborationResponse(
            success=True,
            collaboration_id=str(collaboration.id),
            subtask_count=len(collaboration.subtasks),
            message=(
                f"Collaboration '{collaboration.title}' created with "
                f"{len(collaboration.subtasks)} subtask(s)"
            ),
        )

    except AgentCollaborationError as e:
        logger.error(f"AgentCollaborationError creating collaboration: {e.message}")
        return CreateCollaborationResponse(
            success=False,
            error=e.message,
        )
    except Exception as e:
        logger.error(f"Unexpected error creating collaboration: {e}", exc_info=True)
        return CreateCollaborationResponse(
            success=False,
            error=str(e),
        )


@router.post("/{collaboration_id}/findings", response_model=PostFindingResponse)
def post_finding(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    collaboration_id: uuid.UUID,
    data: PostFindingRequest,
) -> Any:
    """
    Post an intermediate finding to the collaboration's shared context.

    Called by participant agents (coordinator or subtask agents) to share
    intermediate results, observations, or data with all other participants.
    Findings accumulate in shared_context["findings"].

    Pass source_session_id to attribute the finding to the correct participant
    agent (derived from the session's environment). Falls back to coordinator
    agent if source_session_id is not provided or cannot be resolved.
    """
    if not data.finding.strip():
        return PostFindingResponse(
            success=False,
            error="finding is required",
        )

    from app.models.agent_collaboration import AgentCollaboration
    collaboration = session.get(AgentCollaboration, collaboration_id)
    if not collaboration:
        return PostFindingResponse(success=False, error="Collaboration not found")
    if collaboration.owner_id != current_user.id:
        return PostFindingResponse(success=False, error="Not enough permissions")

    # Resolve agent_id: try to derive from source_session_id, fall back to coordinator
    agent_id = collaboration.coordinator_agent_id
    if data.source_session_id:
        try:
            src_session_uuid = uuid.UUID(data.source_session_id)
            src_session = session.get(ChatSession, src_session_uuid)
            if src_session and src_session.environment_id:
                from app.models import AgentEnvironment
                env = session.get(AgentEnvironment, src_session.environment_id)
                if env and env.agent_id:
                    agent_id = env.agent_id
        except Exception as e:
            logger.debug(f"Could not resolve agent from source_session_id: {e}")

    try:
        findings = AgentCollaborationService.post_finding(
            session=session,
            collaboration_id=collaboration_id,
            agent_id=agent_id,
            finding=data.finding,
        )
        return PostFindingResponse(success=True, findings=findings)

    except AgentCollaborationError as e:
        return PostFindingResponse(success=False, error=e.message)
    except Exception as e:
        logger.error(f"Error posting finding: {e}", exc_info=True)
        return PostFindingResponse(success=False, error=str(e))


@router.get("/{collaboration_id}/status", response_model=AgentCollaborationPublic)
def get_collaboration_status(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    collaboration_id: uuid.UUID,
) -> Any:
    """
    Get full collaboration status including all subtask statuses and findings.
    """
    try:
        return AgentCollaborationService.get_collaboration_status(
            session=session,
            collaboration_id=collaboration_id,
            user_id=current_user.id,
        )
    except AgentCollaborationError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/by-session/{session_id}")
def get_collaboration_by_session(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
) -> Any:
    """
    Get collaboration context for a session that belongs to a subtask.

    Called by the prompt generator to inject collaboration context into
    the system prompt for participant agents.

    Returns collaboration context dict or null if session is not a collaboration subtask.
    """
    chat_session = session.get(ChatSession, session_id)
    if not chat_session or chat_session.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session not found")

    context = AgentCollaborationService.get_collaboration_by_session(
        session=session,
        session_id=session_id,
    )

    # Return empty dict (not 404) when session is not a collaboration subtask
    return context or {}
