from uuid import UUID
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select
from sqlalchemy.orm import selectinload

from app.models.user_dashboard import (
    UserDashboard,
    UserDashboardBlock,
    UserDashboardCreate,
    UserDashboardUpdate,
    UserDashboardBlockCreate,
    UserDashboardBlockUpdate,
    BlockLayoutUpdate,
    UserDashboardBlockPromptAction,
    UserDashboardBlockPromptActionCreate,
    UserDashboardBlockPromptActionUpdate,
)
from app.models.agent import Agent

ALLOWED_VIEW_TYPES = {"webapp", "latest_session", "latest_tasks"}
MAX_DASHBOARDS_PER_USER = 10
MAX_BLOCKS_PER_DASHBOARD = 20


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UserDashboardService:

    @staticmethod
    def list_dashboards(session: Session, owner_id: UUID) -> list[UserDashboard]:
        """List all dashboards for a user, ordered by sort_order, with blocks and prompt_actions eagerly loaded."""
        statement = (
            select(UserDashboard)
            .where(UserDashboard.owner_id == owner_id)
            .order_by(UserDashboard.sort_order)
            .options(
                selectinload(UserDashboard.blocks).selectinload(UserDashboardBlock.prompt_actions)  # type: ignore[attr-defined]
            )
        )
        return list(session.exec(statement).all())

    @staticmethod
    def create_dashboard(
        session: Session, owner_id: UUID, data: UserDashboardCreate
    ) -> UserDashboard:
        """Create a new dashboard for a user. Raises 409 if max limit reached."""
        existing = session.exec(
            select(UserDashboard).where(UserDashboard.owner_id == owner_id)
        ).all()
        if len(existing) >= MAX_DASHBOARDS_PER_USER:
            raise HTTPException(
                status_code=409,
                detail=f"Maximum of {MAX_DASHBOARDS_PER_USER} dashboards allowed per user",
            )

        sort_order = max((d.sort_order for d in existing), default=-1) + 1
        dashboard = UserDashboard(
            name=data.name,
            description=data.description,
            owner_id=owner_id,
            sort_order=sort_order,
        )
        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)
        # Ensure blocks attribute is loaded (empty list for new dashboard)
        _ = dashboard.blocks
        return dashboard

    @staticmethod
    def get_dashboard(
        session: Session, dashboard_id: UUID, owner_id: UUID
    ) -> UserDashboard:
        """Get a dashboard by ID with blocks and prompt_actions eagerly loaded. Raises 404/403 as appropriate."""
        statement = (
            select(UserDashboard)
            .where(UserDashboard.id == dashboard_id)
            .options(
                selectinload(UserDashboard.blocks).selectinload(UserDashboardBlock.prompt_actions)  # type: ignore[attr-defined]
            )
        )
        dashboard = session.exec(statement).first()
        if not dashboard:
            raise HTTPException(status_code=404, detail="Dashboard not found")
        if dashboard.owner_id != owner_id:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return dashboard

    @staticmethod
    def _get_block(
        session: Session, dashboard_id: UUID, block_id: UUID
    ) -> UserDashboardBlock:
        """Fetch a block ensuring it belongs to the given dashboard. Raises 404 if not found."""
        block = session.exec(
            select(UserDashboardBlock).where(
                UserDashboardBlock.id == block_id,
                UserDashboardBlock.dashboard_id == dashboard_id,
            )
        ).first()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")
        return block

    @staticmethod
    def update_dashboard(
        session: Session,
        dashboard_id: UUID,
        owner_id: UUID,
        data: UserDashboardUpdate,
    ) -> UserDashboard:
        """Update dashboard metadata. Raises 404/403 as appropriate."""
        dashboard = UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        update_dict = data.model_dump(exclude_unset=True)
        dashboard.sqlmodel_update(update_dict)
        dashboard.updated_at = _utc_now()
        session.add(dashboard)
        session.commit()
        session.refresh(dashboard)
        _ = dashboard.blocks
        return dashboard

    @staticmethod
    def delete_dashboard(
        session: Session, dashboard_id: UUID, owner_id: UUID
    ) -> bool:
        """Delete a dashboard. Raises 404/403 as appropriate."""
        dashboard = UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        session.delete(dashboard)
        session.commit()
        return True

    @staticmethod
    def add_block(
        session: Session,
        dashboard_id: UUID,
        owner_id: UUID,
        data: UserDashboardBlockCreate,
    ) -> UserDashboardBlock:
        """Add a block to a dashboard. Validates limits, agent access, and view type."""
        dashboard = UserDashboardService.get_dashboard(session, dashboard_id, owner_id)

        # Check block limit
        if len(dashboard.blocks) >= MAX_BLOCKS_PER_DASHBOARD:
            raise HTTPException(
                status_code=409,
                detail=f"Maximum of {MAX_BLOCKS_PER_DASHBOARD} blocks allowed per dashboard",
            )

        # Validate view_type
        if data.view_type not in ALLOWED_VIEW_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid view_type '{data.view_type}'. Must be one of: {', '.join(sorted(ALLOWED_VIEW_TYPES))}",
            )

        # Validate agent access: agent must be owned by this user
        agent = session.get(Agent, data.agent_id)
        if not agent or agent.owner_id != owner_id:
            raise HTTPException(
                status_code=400,
                detail="Agent not found or not accessible",
            )

        # Validate webapp view type
        if data.view_type == "webapp" and not agent.webapp_enabled:
            raise HTTPException(
                status_code=400,
                detail="Web App is not enabled for this agent. Enable it in agent settings first.",
            )

        block = UserDashboardBlock(
            dashboard_id=dashboard_id,
            agent_id=data.agent_id,
            view_type=data.view_type,
            title=data.title,
            show_border=data.show_border,
            show_header=data.show_header,
            grid_x=data.grid_x,
            grid_y=data.grid_y,
            grid_w=data.grid_w,
            grid_h=data.grid_h,
        )
        session.add(block)
        session.commit()
        session.refresh(block)
        return block

    @staticmethod
    def update_block(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        owner_id: UUID,
        data: UserDashboardBlockUpdate,
    ) -> UserDashboardBlock:
        """Update block configuration. Raises 404/403 as appropriate."""
        # Ownership check via dashboard
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)

        block = session.exec(
            select(UserDashboardBlock).where(
                UserDashboardBlock.id == block_id,
                UserDashboardBlock.dashboard_id == dashboard_id,
            )
        ).first()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")

        update_dict = data.model_dump(exclude_unset=True)
        block.sqlmodel_update(update_dict)
        block.updated_at = _utc_now()
        session.add(block)
        session.commit()
        session.refresh(block)
        return block

    @staticmethod
    def delete_block(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        owner_id: UUID,
    ) -> bool:
        """Delete a block from a dashboard. Raises 404/403 as appropriate."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)

        block = session.exec(
            select(UserDashboardBlock).where(
                UserDashboardBlock.id == block_id,
                UserDashboardBlock.dashboard_id == dashboard_id,
            )
        ).first()
        if not block:
            raise HTTPException(status_code=404, detail="Block not found")

        session.delete(block)
        session.commit()
        return True

    @staticmethod
    def update_block_layout(
        session: Session,
        dashboard_id: UUID,
        owner_id: UUID,
        layouts: list[BlockLayoutUpdate],
    ) -> list[UserDashboardBlock]:
        """Bulk update block grid positions in a single transaction."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)

        updated_blocks: list[UserDashboardBlock] = []
        for layout in layouts:
            block = session.exec(
                select(UserDashboardBlock).where(
                    UserDashboardBlock.id == layout.block_id,
                    UserDashboardBlock.dashboard_id == dashboard_id,
                )
            ).first()
            if not block:
                raise HTTPException(
                    status_code=404,
                    detail=f"Block {layout.block_id} not found in this dashboard",
                )
            block.grid_x = layout.grid_x
            block.grid_y = layout.grid_y
            block.grid_w = layout.grid_w
            block.grid_h = layout.grid_h
            block.updated_at = _utc_now()
            session.add(block)
            updated_blocks.append(block)

        session.commit()
        for block in updated_blocks:
            session.refresh(block)
        return updated_blocks

    # ── Prompt Action methods ─────────────────────────────────────────────────

    @staticmethod
    def list_prompt_actions(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        owner_id: UUID,
    ) -> list[UserDashboardBlockPromptAction]:
        """List prompt actions for a block, ordered by sort_order."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        UserDashboardService._get_block(session, dashboard_id, block_id)
        actions = session.exec(
            select(UserDashboardBlockPromptAction)
            .where(UserDashboardBlockPromptAction.block_id == block_id)
            .order_by(UserDashboardBlockPromptAction.sort_order)  # type: ignore[arg-type]
        ).all()
        return list(actions)

    @staticmethod
    def create_prompt_action(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        owner_id: UUID,
        data: UserDashboardBlockPromptActionCreate,
    ) -> UserDashboardBlockPromptAction:
        """Create a prompt action on a block."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        UserDashboardService._get_block(session, dashboard_id, block_id)
        action = UserDashboardBlockPromptAction(
            block_id=block_id,
            prompt_text=data.prompt_text,
            label=data.label,
            sort_order=data.sort_order,
        )
        session.add(action)
        session.commit()
        session.refresh(action)
        return action

    @staticmethod
    def update_prompt_action(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        action_id: UUID,
        owner_id: UUID,
        data: UserDashboardBlockPromptActionUpdate,
    ) -> UserDashboardBlockPromptAction:
        """Update a prompt action."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        UserDashboardService._get_block(session, dashboard_id, block_id)
        action = session.exec(
            select(UserDashboardBlockPromptAction).where(
                UserDashboardBlockPromptAction.id == action_id,
                UserDashboardBlockPromptAction.block_id == block_id,
            )
        ).first()
        if not action:
            raise HTTPException(status_code=404, detail="Prompt action not found")
        update_dict = data.model_dump(exclude_unset=True)
        action.sqlmodel_update(update_dict)
        action.updated_at = _utc_now()
        session.add(action)
        session.commit()
        session.refresh(action)
        return action

    @staticmethod
    def delete_prompt_action(
        session: Session,
        dashboard_id: UUID,
        block_id: UUID,
        action_id: UUID,
        owner_id: UUID,
    ) -> bool:
        """Delete a prompt action."""
        UserDashboardService.get_dashboard(session, dashboard_id, owner_id)
        UserDashboardService._get_block(session, dashboard_id, block_id)
        action = session.exec(
            select(UserDashboardBlockPromptAction).where(
                UserDashboardBlockPromptAction.id == action_id,
                UserDashboardBlockPromptAction.block_id == block_id,
            )
        ).first()
        if not action:
            raise HTTPException(status_code=404, detail="Prompt action not found")
        session.delete(action)
        session.commit()
        return True
