import uuid
from typing import Any

from fastapi import APIRouter

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Message,
    UserDashboardCreate,
    UserDashboardUpdate,
    UserDashboardPublic,
    UserDashboardBlockCreate,
    UserDashboardBlockUpdate,
    UserDashboardBlockPublic,
    BlockLayoutUpdate,
)
from app.services.user_dashboard_service import UserDashboardService

router = APIRouter(prefix="/dashboards", tags=["Dashboards"])


def _block_to_public(block: Any) -> UserDashboardBlockPublic:
    return UserDashboardBlockPublic(
        id=block.id,
        agent_id=block.agent_id,
        view_type=block.view_type,
        title=block.title,
        show_border=block.show_border,
        show_header=block.show_header,
        grid_x=block.grid_x,
        grid_y=block.grid_y,
        grid_w=block.grid_w,
        grid_h=block.grid_h,
        config=block.config,
        created_at=block.created_at,
        updated_at=block.updated_at,
    )


def _dashboard_to_public(dashboard: Any) -> UserDashboardPublic:
    return UserDashboardPublic(
        id=dashboard.id,
        name=dashboard.name,
        description=dashboard.description,
        sort_order=dashboard.sort_order,
        created_at=dashboard.created_at,
        updated_at=dashboard.updated_at,
        blocks=[_block_to_public(b) for b in dashboard.blocks],
    )


# ── Dashboard endpoints ──────────────────────────────────────────────────────


@router.get("/", response_model=list[UserDashboardPublic])
def list_dashboards(session: SessionDep, current_user: CurrentUser) -> Any:
    """List all dashboards for the current user, with their blocks."""
    dashboards = UserDashboardService.list_dashboards(
        session=session, owner_id=current_user.id
    )
    return [_dashboard_to_public(d) for d in dashboards]


@router.post("/", response_model=UserDashboardPublic)
def create_dashboard(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_in: UserDashboardCreate,
) -> Any:
    """Create a new dashboard."""
    dashboard = UserDashboardService.create_dashboard(
        session=session, owner_id=current_user.id, data=dashboard_in
    )
    return _dashboard_to_public(dashboard)


@router.get("/{dashboard_id}", response_model=UserDashboardPublic)
def get_dashboard(
    dashboard_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """Get a single dashboard with all its blocks."""
    dashboard = UserDashboardService.get_dashboard(
        session=session, dashboard_id=dashboard_id, owner_id=current_user.id
    )
    return _dashboard_to_public(dashboard)


@router.put("/{dashboard_id}", response_model=UserDashboardPublic)
def update_dashboard(
    *,
    dashboard_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    dashboard_in: UserDashboardUpdate,
) -> Any:
    """Update dashboard metadata."""
    dashboard = UserDashboardService.update_dashboard(
        session=session,
        dashboard_id=dashboard_id,
        owner_id=current_user.id,
        data=dashboard_in,
    )
    return _dashboard_to_public(dashboard)


@router.delete("/{dashboard_id}")
def delete_dashboard(
    dashboard_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    """Delete a dashboard and all its blocks."""
    UserDashboardService.delete_dashboard(
        session=session, dashboard_id=dashboard_id, owner_id=current_user.id
    )
    return Message(message="Dashboard deleted")


# ── Block endpoints ──────────────────────────────────────────────────────────


@router.post("/{dashboard_id}/blocks", response_model=UserDashboardBlockPublic)
def add_block(
    *,
    dashboard_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    block_in: UserDashboardBlockCreate,
) -> Any:
    """Add a block to a dashboard."""
    block = UserDashboardService.add_block(
        session=session,
        dashboard_id=dashboard_id,
        owner_id=current_user.id,
        data=block_in,
    )
    return _block_to_public(block)


# IMPORTANT: /layout must be registered BEFORE /{block_id} to avoid route conflicts.
@router.put("/{dashboard_id}/blocks/layout", response_model=list[UserDashboardBlockPublic])
def update_block_layout(
    *,
    dashboard_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    layouts: list[BlockLayoutUpdate],
) -> Any:
    """Bulk update block grid positions (for drag-and-drop rearrangement)."""
    blocks = UserDashboardService.update_block_layout(
        session=session,
        dashboard_id=dashboard_id,
        owner_id=current_user.id,
        layouts=layouts,
    )
    return [_block_to_public(b) for b in blocks]


@router.put("/{dashboard_id}/blocks/{block_id}", response_model=UserDashboardBlockPublic)
def update_block(
    *,
    dashboard_id: uuid.UUID,
    block_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    block_in: UserDashboardBlockUpdate,
) -> Any:
    """Update block configuration."""
    block = UserDashboardService.update_block(
        session=session,
        dashboard_id=dashboard_id,
        block_id=block_id,
        owner_id=current_user.id,
        data=block_in,
    )
    return _block_to_public(block)


@router.delete("/{dashboard_id}/blocks/{block_id}")
def delete_block(
    dashboard_id: uuid.UUID,
    block_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Message:
    """Remove a block from a dashboard."""
    UserDashboardService.delete_block(
        session=session,
        dashboard_id=dashboard_id,
        block_id=block_id,
        owner_id=current_user.id,
    )
    return Message(message="Block deleted")
