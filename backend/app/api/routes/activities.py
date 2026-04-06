import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    ActivityCreate,
    ActivityUpdate,
    ActivityPublic,
    ActivitiesPublicExtended,
    ActivityStats,
    Agent,
    Session,
)
from app.services.events.activity_service import (
    ActivityService,
    ActivityNotFoundError,
    ActivityPermissionError,
)

router = APIRouter(prefix="/activities", tags=["activities"])


def _handle_activity_error(e: Exception) -> None:
    """Convert service exceptions to HTTP responses."""
    if isinstance(e, ActivityNotFoundError):
        raise HTTPException(status_code=404, detail="Activity not found")
    if isinstance(e, ActivityPermissionError):
        raise HTTPException(status_code=400, detail="Not enough permissions")
    raise e


@router.post("/", response_model=ActivityPublic)
def create_activity(
    *, session: SessionDep, current_user: CurrentUser, activity_in: ActivityCreate
) -> Any:
    """Create new activity."""
    # Validate referenced entities belong to current user
    if activity_in.agent_id:
        agent = session.get(Agent, activity_in.agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if agent.owner_id != current_user.id:
            raise HTTPException(status_code=400, detail="Not enough permissions")

    if activity_in.session_id:
        session_obj = session.get(Session, activity_in.session_id)
        if not session_obj:
            raise HTTPException(status_code=404, detail="Session not found")
        if session_obj.user_id != current_user.id:
            raise HTTPException(status_code=400, detail="Not enough permissions")

    return ActivityService.create_activity(
        db_session=session, user_id=current_user.id, data=activity_in
    )


@router.get("/", response_model=ActivitiesPublicExtended)
def list_activities(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID | None = None,
    user_workspace_id: str | None = None,
    include_archived: bool = False,
    skip: int = 0,
    limit: int = 100,
    order_desc: bool = True,
) -> Any:
    """List user's activities with optional filtering.

    By default excludes archived activities. Pass include_archived=true for all logs.
    """
    try:
        return ActivityService.list_user_activities_extended(
            db_session=session,
            user_id=current_user.id,
            agent_id=agent_id,
            user_workspace_id=user_workspace_id,
            include_archived=include_archived,
            skip=skip,
            limit=limit,
            order_desc=order_desc,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace ID format")


@router.post("/archive-logs", response_model=dict)
def archive_logs(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """Archive non-active log activities (marks them as archived and read)."""
    count = ActivityService.archive_logs(
        db_session=session, user_id=current_user.id,
    )
    return {"archived_count": count}


@router.get("/stats", response_model=ActivityStats)
def get_activity_stats(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """Get activity statistics (unread count, action required count)."""
    stats = ActivityService.get_activity_stats(
        db_session=session, user_id=current_user.id
    )
    return ActivityStats(**stats)


@router.patch("/{activity_id}", response_model=ActivityPublic)
async def update_activity(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    activity_id: uuid.UUID,
    activity_in: ActivityUpdate,
) -> Any:
    """Update activity (e.g., mark as read)."""
    try:
        return await ActivityService.update_activity(
            db_session=session,
            activity_id=activity_id,
            user_id=current_user.id,
            data=activity_in,
        )
    except (ActivityNotFoundError, ActivityPermissionError) as e:
        _handle_activity_error(e)


@router.post("/mark-read", response_model=dict)
async def mark_activities_as_read(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    activity_ids: list[uuid.UUID],
) -> Any:
    """Mark multiple activities as read."""
    count = await ActivityService.mark_multiple_as_read(
        db_session=session,
        user_id=current_user.id,
        activity_ids=activity_ids,
    )
    return {"updated_count": count}


@router.delete("/{activity_id}")
async def delete_activity(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    activity_id: uuid.UUID,
) -> Any:
    """Delete activity."""
    try:
        await ActivityService.delete_activity_for_user(
            db_session=session,
            activity_id=activity_id,
            user_id=current_user.id,
        )
    except (ActivityNotFoundError, ActivityPermissionError) as e:
        _handle_activity_error(e)
    return {"message": "Activity deleted successfully"}


@router.delete("/")
async def delete_all_activities(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """Delete all activities for the current user."""
    deleted_count = await ActivityService.delete_all_for_user(
        db_session=session,
        user_id=current_user.id,
    )
    return {"message": f"Deleted {deleted_count} activities", "deleted_count": deleted_count}
