"""
Agent Webapp Interface Config Service - Business logic for webapp interface settings.
"""
import uuid
import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.models import (
    Agent,
    AgentWebappInterfaceConfig,
    AgentWebappInterfaceConfigUpdate,
    AgentWebappInterfaceConfigPublic,
)

logger = logging.getLogger(__name__)


class InterfaceConfigError(Exception):
    """Base exception for interface config service errors."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class AgentNotFoundError(InterfaceConfigError):
    def __init__(self, message: str = "Agent not found"):
        super().__init__(message, status_code=404)


class AgentPermissionError(InterfaceConfigError):
    def __init__(self, message: str = "Agent not found"):
        super().__init__(message, status_code=404)


class AgentWebappInterfaceConfigService:

    @staticmethod
    def _verify_agent_ownership(
        session: Session, user_id: uuid.UUID, agent_id: uuid.UUID
    ) -> Agent:
        """Verify agent exists and is owned by user. Returns the agent."""
        agent = session.get(Agent, agent_id)
        if not agent:
            raise AgentNotFoundError()
        if agent.owner_id != user_id:
            raise AgentPermissionError()
        return agent

    @staticmethod
    def _get_config_by_agent(
        session: Session, agent_id: uuid.UUID
    ) -> AgentWebappInterfaceConfig | None:
        """Get the interface config record for an agent, or None."""
        return session.exec(
            select(AgentWebappInterfaceConfig).where(
                AgentWebappInterfaceConfig.agent_id == agent_id
            )
        ).first()

    @staticmethod
    def get_or_create(
        session: Session,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
    ) -> AgentWebappInterfaceConfigPublic:
        AgentWebappInterfaceConfigService._verify_agent_ownership(
            session, user_id, agent_id
        )

        config = AgentWebappInterfaceConfigService._get_config_by_agent(
            session, agent_id
        )

        if not config:
            config = AgentWebappInterfaceConfig(agent_id=agent_id)
            session.add(config)
            session.commit()
            session.refresh(config)

        return AgentWebappInterfaceConfigPublic.model_validate(config)

    @staticmethod
    def update(
        session: Session,
        user_id: uuid.UUID,
        agent_id: uuid.UUID,
        data: AgentWebappInterfaceConfigUpdate,
    ) -> AgentWebappInterfaceConfigPublic:
        AgentWebappInterfaceConfigService._verify_agent_ownership(
            session, user_id, agent_id
        )

        config = AgentWebappInterfaceConfigService._get_config_by_agent(
            session, agent_id
        )

        if not config:
            config = AgentWebappInterfaceConfig(agent_id=agent_id)
            session.add(config)

        if data.show_header is not None:
            config.show_header = data.show_header
        if data.show_chat is not None:
            config.show_chat = data.show_chat

        config.updated_at = datetime.now(UTC)
        session.add(config)
        session.commit()
        session.refresh(config)

        return AgentWebappInterfaceConfigPublic.model_validate(config)

    @staticmethod
    def get_by_agent_id(
        session: Session,
        agent_id: uuid.UUID,
    ) -> dict:
        """Get interface config for a given agent (no auth check, used by public endpoints)."""
        config = AgentWebappInterfaceConfigService._get_config_by_agent(
            session, agent_id
        )

        if not config:
            return {"show_header": True, "show_chat": False}

        return {
            "show_header": config.show_header,
            "show_chat": config.show_chat,
        }
