"""
User API routes for personal Application Agent Routes.

Users manage their own personal routes (soft-deprecated) and can toggle shared routes.
"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import Message
from app.models.app_mcp.app_agent_route import (
    UserAppAgentRouteCreate,
    UserAppAgentRouteUpdate,
    UserAppAgentRoutePublic,
    UserAppAgentRoutesResponse,
    AppAgentRouteAssignmentPublic,
)
from app.services.app_mcp.app_agent_route_service import (
    AppAgentRouteService,
    UserAppAgentRouteService,
)

router = APIRouter(prefix="/users/me/app-agent-routes", tags=["user-app-agent-routes"])


@router.get("/", response_model=UserAppAgentRoutesResponse)
def list_user_app_agent_routes(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """List personal routes and shared routes for the current user."""
    personal_routes = UserAppAgentRouteService.list_routes(
        db_session=session,
        user_id=current_user.id,
    )
    shared_routes = UserAppAgentRouteService.get_shared_routes(
        db_session=session,
        user_id=current_user.id,
    )
    return UserAppAgentRoutesResponse(
        personal_routes=personal_routes,
        shared_routes=shared_routes,
    )


@router.post("/", response_model=UserAppAgentRoutePublic)
def create_user_app_agent_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    route_in: UserAppAgentRouteCreate,
) -> Any:
    """Create a personal application agent route (soft-deprecated)."""
    try:
        return UserAppAgentRouteService.create_route(
            db_session=session,
            user_id=current_user.id,
            data=route_in,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{route_id}", response_model=UserAppAgentRoutePublic)
def update_user_app_agent_route(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    route_id: uuid.UUID,
    route_in: UserAppAgentRouteUpdate,
) -> Any:
    """Update a personal application agent route."""
    route = UserAppAgentRouteService.update_route(
        db_session=session,
        route_id=route_id,
        user_id=current_user.id,
        data=route_in,
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.delete("/{route_id}")
def delete_user_app_agent_route(
    session: SessionDep,
    current_user: CurrentUser,
    route_id: uuid.UUID,
) -> Message:
    """Delete a personal application agent route."""
    deleted = UserAppAgentRouteService.delete_route(
        db_session=session,
        route_id=route_id,
        user_id=current_user.id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Route not found")
    return Message(message="Route deleted successfully")


@router.patch("/admin-assignments/{assignment_id}", response_model=AppAgentRouteAssignmentPublic)
def toggle_admin_assignment(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    assignment_id: uuid.UUID,
    is_enabled: bool,
) -> Any:
    """Toggle a user's shared route assignment on or off."""
    result = AppAgentRouteService.toggle_admin_assignment(
        db_session=session,
        assignment_id=assignment_id,
        user_id=current_user.id,
        is_enabled=is_enabled,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return result
