"""Owner-managed ACP connectors and hashed, connector-scoped bearer tokens."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from sqlmodel import Session, select

from app.core.config import settings
from app.models.acp.acp_connector import (
    ACPConnector,
    ACPConnectorCreate,
    ACPConnectorPublic,
    ACPConnectorUpdate,
)
from app.models.acp.acp_token import (
    ACPToken,
    ACPTokenCreate,
    ACPTokenCreated,
    ACPTokenPublic,
)
from app.models.agents.agent import Agent
from app.models.users.user import User
from app.services.users.role_service import RoleService


@dataclass(frozen=True)
class ACPAuthentication:
    connector: ACPConnector
    token: ACPToken
    agent: Agent
    owner: User


class ACPConnectorService:
    @staticmethod
    def list_connectors(
        db: Session, agent_id: uuid.UUID, owner_id: uuid.UUID
    ) -> list[ACPConnector]:
        return list(
            db.exec(
                select(ACPConnector)
                .where(
                    ACPConnector.agent_id == agent_id, ACPConnector.owner_id == owner_id
                )
                .order_by(ACPConnector.created_at.desc())
            ).all()
        )

    @staticmethod
    def delete_connector(db: Session, connector: ACPConnector) -> None:
        db.delete(connector)
        db.commit()

    @staticmethod
    def list_tokens(db: Session, connector_id: uuid.UUID) -> list[ACPTokenPublic]:
        tokens = db.exec(
            select(ACPToken)
            .where(ACPToken.connector_id == connector_id)
            .order_by(ACPToken.created_at.desc())
        ).all()
        return [ACPTokenPublic.model_validate(token) for token in tokens]

    @staticmethod
    def revoke_token(db: Session, token: ACPToken) -> ACPTokenPublic:
        token.revoked = True
        db.add(token)
        db.commit()
        db.refresh(token)
        return ACPTokenPublic.model_validate(token)

    @staticmethod
    def delete_token(db: Session, token: ACPToken) -> None:
        db.delete(token)
        db.commit()

    @staticmethod
    def server_url(connector_id: uuid.UUID) -> str | None:
        base = settings.ACP_SERVER_BASE_URL
        if not base:
            return None
        parsed = urlsplit(base)
        scheme = {"https": "wss", "http": "ws"}.get(parsed.scheme, parsed.scheme)
        return urlunsplit(
            (scheme, parsed.netloc, f"{parsed.path.rstrip('/')}/{connector_id}", "", "")
        )

    @staticmethod
    def to_public(connector: ACPConnector) -> ACPConnectorPublic:
        return ACPConnectorPublic.model_validate(
            connector,
            update={"acp_server_url": ACPConnectorService.server_url(connector.id)},
        )

    @staticmethod
    def create_connector(
        db: Session, agent: Agent, data: ACPConnectorCreate
    ) -> ACPConnector:
        connector = ACPConnector(
            agent_id=agent.id, owner_id=agent.owner_id, **data.model_dump()
        )
        db.add(connector)
        db.commit()
        db.refresh(connector)
        return connector

    @staticmethod
    def update_connector(
        db: Session, connector: ACPConnector, data: ACPConnectorUpdate
    ) -> ACPConnector:
        connector.sqlmodel_update(data.model_dump(exclude_unset=True))
        connector.updated_at = datetime.now(UTC)
        db.add(connector)
        db.commit()
        db.refresh(connector)
        return connector

    @staticmethod
    def create_token(
        db: Session, connector: ACPConnector, data: ACPTokenCreate
    ) -> ACPTokenCreated:
        raw_token = "acp_" + secrets.token_urlsafe(48)
        token = ACPToken(
            connector_id=connector.id,
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            prefix=raw_token[:12],
            label=data.label,
            expires_at=datetime.now(UTC) + timedelta(days=data.expires_in_days),
        )
        db.add(token)
        db.commit()
        db.refresh(token)
        return ACPTokenCreated(
            **ACPTokenPublic.model_validate(token).model_dump(), token=raw_token
        )

    @staticmethod
    def authenticate(
        connector_id: uuid.UUID, raw_token: str, db: Session
    ) -> ACPAuthentication | None:
        """Revalidate current authorization, even inside a long-lived DB session.

        Only the digest is stored. ACP credentials cannot authenticate to any
        other connector or to the platform API. Callers should invoke this on
        every request and during active prompts so revocation takes effect.
        This method does not commit or otherwise mutate the caller's transaction.
        """
        if not raw_token.startswith("acp_") or len(raw_token) > 256:
            return None
        digest = hashlib.sha256(raw_token.encode()).hexdigest()
        rows = db.exec(
            select(ACPConnector, ACPToken, Agent, User)
            .join(ACPToken, ACPToken.connector_id == ACPConnector.id)
            .join(Agent, Agent.id == ACPConnector.agent_id)
            .join(User, User.id == ACPConnector.owner_id)
            .where(
                ACPConnector.id == connector_id,
                ACPConnector.is_active.is_(True),
                ACPToken.token_hash == digest,
                ACPToken.revoked.is_(False),
                ACPToken.expires_at > datetime.now(UTC),
                User.is_active.is_(True),
                Agent.is_active.is_(True),
                Agent.owner_id == ACPConnector.owner_id,
            )
            .execution_options(populate_existing=True)
        ).first()
        if rows is None:
            return None
        connector, token, agent, owner = rows
        if connector.mode == "building" and not RoleService.is_developer(owner):
            return None
        return ACPAuthentication(
            connector=connector, token=token, agent=agent, owner=owner
        )

    @staticmethod
    def mark_used(db: Session, token: ACPToken) -> None:
        """Record a successfully accepted connection separately from validation."""
        token.last_used_at = datetime.now(UTC)
        db.add(token)
        db.commit()
