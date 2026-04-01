from uuid import UUID
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session, select

from app.models.agentic_team import (
    AgenticTeamNode,
    AgenticTeamConnection,
    AgenticTeamConnectionCreate,
    AgenticTeamConnectionUpdate,
    AgenticTeamConnectionPublic,
)
from app.services.agentic_team_service import AgenticTeamService


class AgenticTeamConnectionService:

    @staticmethod
    def get_connection(
        session: Session, team_id: UUID, conn_id: UUID, user_id: UUID
    ) -> AgenticTeamConnection:
        """
        Verify team ownership then verify the connection belongs to the team.
        Raises 404 for any failure condition.
        """
        AgenticTeamService.get_team(session, team_id, user_id)
        conn = session.get(AgenticTeamConnection, conn_id)
        if not conn or conn.team_id != team_id:
            raise HTTPException(status_code=404, detail="Connection not found")
        return conn

    @staticmethod
    def list_connections(
        session: Session, team_id: UUID, user_id: UUID
    ) -> list[AgenticTeamConnection]:
        AgenticTeamService.get_team(session, team_id, user_id)
        statement = select(AgenticTeamConnection).where(
            AgenticTeamConnection.team_id == team_id
        )
        return list(session.exec(statement).all())

    @staticmethod
    def create_connection(
        session: Session,
        team_id: UUID,
        user_id: UUID,
        data: AgenticTeamConnectionCreate,
    ) -> AgenticTeamConnection:
        # 1. Verify team ownership
        AgenticTeamService.get_team(session, team_id, user_id)

        # 2. Prevent self-connection
        if data.source_node_id == data.target_node_id:
            raise HTTPException(
                status_code=400,
                detail="Source and target nodes must be different",
            )

        # 3. Verify source node belongs to this team
        source_node = session.get(AgenticTeamNode, data.source_node_id)
        if not source_node or source_node.team_id != team_id:
            raise HTTPException(status_code=404, detail="Source node not found")

        # 4. Verify target node belongs to this team
        target_node = session.get(AgenticTeamNode, data.target_node_id)
        if not target_node or target_node.team_id != team_id:
            raise HTTPException(status_code=404, detail="Target node not found")

        # 5. Prevent duplicate connection
        duplicate_stmt = select(AgenticTeamConnection).where(
            AgenticTeamConnection.team_id == team_id,
            AgenticTeamConnection.source_node_id == data.source_node_id,
            AgenticTeamConnection.target_node_id == data.target_node_id,
        )
        if session.exec(duplicate_stmt).first():
            raise HTTPException(
                status_code=409,
                detail="A connection between these nodes already exists",
            )

        # 6. Create
        conn = AgenticTeamConnection(
            team_id=team_id,
            source_node_id=data.source_node_id,
            target_node_id=data.target_node_id,
            connection_prompt=data.connection_prompt,
            enabled=data.enabled,
        )
        session.add(conn)
        session.commit()
        session.refresh(conn)
        return conn

    @staticmethod
    def update_connection(
        session: Session,
        team_id: UUID,
        conn_id: UUID,
        user_id: UUID,
        data: AgenticTeamConnectionUpdate,
    ) -> AgenticTeamConnection:
        conn = AgenticTeamConnectionService.get_connection(
            session, team_id, conn_id, user_id
        )
        update_dict = data.model_dump(exclude_unset=True)
        conn.sqlmodel_update(update_dict)
        conn.updated_at = datetime.now(timezone.utc)
        session.add(conn)
        session.commit()
        session.refresh(conn)
        return conn

    @staticmethod
    def delete_connection(
        session: Session, team_id: UUID, conn_id: UUID, user_id: UUID
    ) -> None:
        conn = AgenticTeamConnectionService.get_connection(
            session, team_id, conn_id, user_id
        )
        session.delete(conn)
        session.commit()

    @staticmethod
    def connection_to_public(
        session: Session, conn: AgenticTeamConnection
    ) -> AgenticTeamConnectionPublic:
        """Resolve source/target node names and build the public response model."""
        source_node = session.get(AgenticTeamNode, conn.source_node_id)
        target_node = session.get(AgenticTeamNode, conn.target_node_id)
        source_name = source_node.name if source_node else ""
        target_name = target_node.name if target_node else ""
        return AgenticTeamConnectionPublic(
            id=conn.id,
            team_id=conn.team_id,
            source_node_id=conn.source_node_id,
            target_node_id=conn.target_node_id,
            source_node_name=source_name,
            target_node_name=target_name,
            connection_prompt=conn.connection_prompt,
            enabled=conn.enabled,
            created_at=conn.created_at,
            updated_at=conn.updated_at,
        )
