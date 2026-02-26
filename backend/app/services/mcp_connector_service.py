import uuid
import logging
from datetime import datetime, UTC

from sqlmodel import Session as DBSession, select, func

from app.models.mcp_connector import MCPConnector, MCPConnectorCreate, MCPConnectorUpdate
from app.models.mcp_oauth_client import MCPOAuthClient
from app.core.config import settings

logger = logging.getLogger(__name__)


class MCPConnectorService:
    @staticmethod
    def create_connector(
        db_session: DBSession,
        agent_id: uuid.UUID,
        owner_id: uuid.UUID,
        data: MCPConnectorCreate,
    ) -> MCPConnector:
        connector = MCPConnector(
            agent_id=agent_id,
            owner_id=owner_id,
            name=data.name,
            mode=data.mode,
            allowed_emails=data.allowed_emails,
            max_clients=data.max_clients,
        )
        db_session.add(connector)
        db_session.commit()
        db_session.refresh(connector)
        return connector

    @staticmethod
    def list_connectors(
        db_session: DBSession,
        agent_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[MCPConnector]:
        statement = select(MCPConnector).where(
            MCPConnector.agent_id == agent_id,
            MCPConnector.owner_id == owner_id,
        )
        return list(db_session.exec(statement).all())

    @staticmethod
    def get_connector(
        db_session: DBSession,
        connector_id: uuid.UUID,
    ) -> MCPConnector | None:
        return db_session.get(MCPConnector, connector_id)

    @staticmethod
    def update_connector(
        db_session: DBSession,
        connector_id: uuid.UUID,
        owner_id: uuid.UUID,
        data: MCPConnectorUpdate,
    ) -> MCPConnector | None:
        connector = db_session.get(MCPConnector, connector_id)
        if not connector:
            return None
        if connector.owner_id != owner_id:
            raise ValueError("Not authorized")

        update_dict = data.model_dump(exclude_unset=True)
        connector.sqlmodel_update(update_dict)
        connector.updated_at = datetime.now(UTC)

        db_session.add(connector)
        db_session.commit()
        db_session.refresh(connector)

        # Evict MCP server if deactivated
        if "is_active" in update_dict and not connector.is_active:
            from app.mcp.server import mcp_registry
            mcp_registry.remove(str(connector_id))

        return connector

    @staticmethod
    def delete_connector(
        db_session: DBSession,
        connector_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> bool:
        connector = db_session.get(MCPConnector, connector_id)
        if not connector:
            return False
        if connector.owner_id != owner_id:
            raise ValueError("Not authorized")

        db_session.delete(connector)

        # Evict MCP server from registry
        from app.mcp.server import mcp_registry
        mcp_registry.remove(str(connector_id))

        db_session.commit()
        return True

    @staticmethod
    def check_email_access(
        db_session: DBSession,
        connector_id: uuid.UUID,
        email: str,
    ) -> bool:
        """Check if an email has access to the connector (owner or in allowed_emails)."""
        connector = db_session.get(MCPConnector, connector_id)
        if not connector:
            return False
        # If allowed_emails is empty, only owner has access (checked at route level)
        if not connector.allowed_emails:
            return False
        return email.lower() in [e.lower() for e in connector.allowed_emails]

    @staticmethod
    def get_registered_client_count(
        db_session: DBSession,
        connector_id: uuid.UUID,
    ) -> int:
        statement = select(func.count()).where(
            MCPOAuthClient.connector_id == connector_id
        )
        return db_session.exec(statement).one()

    @staticmethod
    def to_public(connector: MCPConnector) -> dict:
        """Convert connector to public dict with computed mcp_server_url."""
        data = {
            "id": connector.id,
            "agent_id": connector.agent_id,
            "owner_id": connector.owner_id,
            "name": connector.name,
            "mode": connector.mode,
            "is_active": connector.is_active,
            "allowed_emails": connector.allowed_emails or [],
            "max_clients": connector.max_clients,
            "mcp_server_url": f"{settings.MCP_SERVER_BASE_URL}/{connector.id}/mcp" if settings.MCP_SERVER_BASE_URL else None,
            "created_at": connector.created_at,
            "updated_at": connector.updated_at,
        }
        return data
