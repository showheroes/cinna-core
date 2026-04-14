"""
Admin API routes for Application Agent Routes management.

Superusers can create, update, delete, and assign routes for any agent.
"""
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import SessionDep, get_current_active_superuser
from app.models import User, Message
from app.models.app_mcp.app_agent_route import (
    AppAgentRouteCreate,
    AppAgentRouteUpdate,
    AppAgentRoutePublic,
    AppAgentRouteAssignmentPublic,
)
from app.services.app_mcp.app_agent_route_service import AppAgentRouteService

router = APIRouter(prefix="/admin/app-agent-routes", tags=["app-agent-routes"])

SuperUser = Annotated[User, Depends(get_current_active_superuser)]


@router.get("/", response_model=list[AppAgentRoutePublic])
def list_app_agent_routes(
    session: SessionDep,
    current_user: SuperUser,
) -> Any:
    """List all application agent routes."""
    return AppAgentRouteService.list_routes(db_session=session)


@router.post("/", response_model=AppAgentRoutePublic)
def create_app_agent_route(
    *,
    session: SessionDep,
    current_user: SuperUser,
    route_in: AppAgentRouteCreate,
) -> Any:
    """Create a new application agent route."""
    try:
        return AppAgentRouteService.create_route(
            db_session=session,
            data=route_in,
            current_user=current_user,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{route_id}", response_model=AppAgentRoutePublic)
def get_app_agent_route(
    session: SessionDep,
    current_user: SuperUser,
    route_id: uuid.UUID,
) -> Any:
    """Get a specific application agent route."""
    route = AppAgentRouteService.get_route(db_session=session, route_id=route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.put("/{route_id}", response_model=AppAgentRoutePublic)
def update_app_agent_route(
    *,
    session: SessionDep,
    current_user: SuperUser,
    route_id: uuid.UUID,
    route_in: AppAgentRouteUpdate,
) -> Any:
    """Update an application agent route."""
    route = AppAgentRouteService.update_route(
        db_session=session,
        route_id=route_id,
        data=route_in,
    )
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return route


@router.delete("/{route_id}")
def delete_app_agent_route(
    session: SessionDep,
    current_user: SuperUser,
    route_id: uuid.UUID,
) -> Message:
    """Delete an application agent route."""
    deleted = AppAgentRouteService.delete_route(db_session=session, route_id=route_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Route not found")
    return Message(message="Route deleted successfully")


@router.post("/{route_id}/assignments", response_model=list[AppAgentRouteAssignmentPublic])
def assign_users_to_route(
    *,
    session: SessionDep,
    current_user: SuperUser,
    route_id: uuid.UUID,
    user_ids: list[uuid.UUID],
) -> Any:
    """Assign users to an application agent route."""
    route = AppAgentRouteService.get_route(db_session=session, route_id=route_id)
    if not route:
        raise HTTPException(status_code=404, detail="Route not found")
    return AppAgentRouteService.assign_users(
        db_session=session,
        route_id=route_id,
        user_ids=user_ids,
        auto_enable=route.auto_enable_for_users,
    )


@router.delete("/{route_id}/assignments/{user_id}")
def remove_user_assignment(
    session: SessionDep,
    current_user: SuperUser,
    route_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Message:
    """Remove a user assignment from an application agent route."""
    removed = AppAgentRouteService.remove_assignment(
        db_session=session,
        route_id=route_id,
        user_id=user_id,
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return Message(message="Assignment removed successfully")
