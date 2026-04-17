"""
External Agent Access API — discovery and session-metadata routes.

Native clients (Cinna Desktop, Cinna Mobile, etc.) use these to render their
home screen and restore their thread list.  Message traffic itself goes
through the A2A POST endpoints (``/external/a2a/…``); the routes here are
metadata-only.

Endpoints:

  GET    /external/agents                              — unified target list
  GET    /external/sessions                            — sessions visible to caller
  GET    /external/sessions/{session_id}               — single-session metadata
  GET    /external/sessions/{session_id}/messages      — message history
  DELETE /external/sessions/{session_id}               — soft-hide for caller
"""
import uuid as uuid_lib
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.api.deps import CurrentUser, SessionDep
from app.models.external.external_agents import (
    ExternalAgentListResponse,
    ExternalSessionPublic,
)
from app.models.sessions.session import MessagePublic
from app.services.external.errors import ExternalSessionError
from app.services.external.external_agent_catalog_service import (
    ExternalAgentCatalogService,
)
from app.services.external.external_session_service import ExternalSessionService
from app.utils import get_base_url


def _handle_service_error(e: Exception) -> HTTPException:
    """Map ExternalSessionError subclasses to HTTPException."""
    if isinstance(e, ExternalSessionError):
        return HTTPException(status_code=e.http_status, detail=e.message)
    raise e

router = APIRouter(prefix="/external", tags=["external"])


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@router.get("/agents", response_model=ExternalAgentListResponse)
def list_external_agents(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    request: Request,
    workspace_id: uuid_lib.UUID | None = Query(
        default=None,
        description=(
            "Optional workspace filter. When provided, limits the personal agents "
            "section to agents in this workspace. MCP shared agents and identity "
            "contacts are not filtered."
        ),
    ),
) -> Any:
    """Return all addressable targets for the authenticated user.

    Used by native clients to render their home screen agent list. Returns
    three sections (personal agents, MCP shared agents, identity contacts)
    in a single response, each with an ``agent_card_url`` pointing at the
    target's A2A endpoint for chat.
    """
    return ExternalAgentCatalogService.list_targets(
        db=session,
        user=current_user,
        request_base_url=get_base_url(request),
        workspace_id=workspace_id,
    )


# ---------------------------------------------------------------------------
# Session metadata (read-only)
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[ExternalSessionPublic])
def list_external_sessions(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = 100,
    offset: int = 0,
) -> Any:
    """Return all sessions where the current user is owner, caller, or identity_caller.

    Sessions are ordered by last_message_at DESC (most recent first). Covers
    all integration types created via the external surface: "external" (personal
    agents), "app_mcp" (shared agents), "identity_mcp" (identity contacts).

    Intended for native clients to restore their thread list at launch without
    opening a full A2A connection per thread.

    Query params:
      limit  — max results to return (default 100, capped inside the service)
      offset — pagination offset (default 0)
    """
    try:
        return ExternalSessionService.list_sessions_for_external(
            db=session,
            user=current_user,
            limit=limit,
            offset=offset,
        )
    except ExternalSessionError as e:
        raise _handle_service_error(e)


@router.get("/sessions/{session_id}", response_model=ExternalSessionPublic)
def get_external_session(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid_lib.UUID,
) -> Any:
    """Return metadata for a single session.

    Returns 404 if the session does not exist or the current user is not a
    participant (owner, caller, or identity_caller). The 404 response is used
    regardless of whether the session exists, to avoid leaking information
    about sessions the user is not part of.
    """
    try:
        return ExternalSessionService.get_session_for_external(
            db=session,
            user=current_user,
            session_id=session_id,
        )
    except ExternalSessionError as e:
        raise _handle_service_error(e)


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[MessagePublic],
)
def list_external_session_messages(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid_lib.UUID,
) -> Any:
    """Return message history for a visible session.

    Returns 404 if the session does not exist or the current user is not a
    participant. Messages are returned in chronological order (oldest first).

    This endpoint is read-only — to send a new message use the A2A POST
    endpoint for the session's target (``target.agent_card_url``).
    """
    try:
        return ExternalSessionService.list_messages_for_external(
            db=session,
            user=current_user,
            session_id=session_id,
        )
    except ExternalSessionError as e:
        raise _handle_service_error(e)


@router.delete("/sessions/{session_id}", status_code=204)
def hide_external_session(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid_lib.UUID,
) -> Response:
    """Soft-hide a session from the caller's thread list.

    Sets ``session_metadata["hidden_for_callers"] = True`` on the session.
    The session is NOT deleted from the database — it remains accessible to
    the agent owner and for audit purposes.  After this call, the session will
    no longer appear in ``GET /external/sessions`` for this caller.

    Returns 404 if the session does not exist or the current user is not a
    participant (owner, caller, or identity_caller).

    Returns 204 No Content on success.
    """
    try:
        ExternalSessionService.hide_session_for_external(
            db=session,
            user=current_user,
            session_id=session_id,
        )
    except ExternalSessionError as e:
        raise _handle_service_error(e)
    return Response(status_code=204)
