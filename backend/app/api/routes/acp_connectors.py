"""Authenticated owner controls for remote Agent Client Protocol access."""

import uuid

from fastapi import APIRouter, HTTPException, Response
from sqlmodel import Session

from app.api.deps import CurrentUser, SessionDep
from app.models import Agent, Message, User
from app.models.acp.acp_connector import (
    ACPConnector,
    ACPConnectorCreate,
    ACPConnectorPublic,
    ACPConnectorsPublic,
    ACPConnectorUpdate,
)
from app.models.acp.acp_token import (
    ACPToken,
    ACPTokenCreate,
    ACPTokenCreated,
    ACPTokenPublic,
    ACPTokensPublic,
)
from app.services.acp.connector_service import ACPConnectorService
from app.services.users.role_service import RoleService

router = APIRouter(tags=["acp-connectors"])


def _owned_agent(db: Session, agent_id: uuid.UUID, owner_id: uuid.UUID) -> Agent:
    agent = db.get(Agent, agent_id)
    if agent is None or agent.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _owned_connector(
    db: Session, agent_id: uuid.UUID, connector_id: uuid.UUID, owner_id: uuid.UUID
) -> ACPConnector:
    connector = db.get(ACPConnector, connector_id)
    if (
        connector is None
        or connector.owner_id != owner_id
        or connector.agent_id != agent_id
    ):
        raise HTTPException(status_code=404, detail="ACP connector not found")
    _owned_agent(db, connector.agent_id, owner_id)
    return connector


def _scoped_token(
    db: Session, connector_id: uuid.UUID, token_id: uuid.UUID
) -> ACPToken:
    token = db.get(ACPToken, token_id)
    if token is None or token.connector_id != connector_id:
        raise HTTPException(status_code=404, detail="ACP token not found")
    return token


def _check_mode(mode: str, user: User) -> None:
    if mode == "building" and not RoleService.is_developer(user):
        raise HTTPException(
            status_code=403, detail="Building mode requires the agent-developer role"
        )


@router.post("/agents/{agent_id}/acp-connectors", response_model=ACPConnectorPublic)
def create_acp_connector(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_in: ACPConnectorCreate,
) -> ACPConnectorPublic:
    """Expose an owned agent to clients holding a connector-scoped ACP token."""
    agent = _owned_agent(session, agent_id, current_user.id)
    _check_mode(connector_in.mode, current_user)
    return ACPConnectorService.to_public(
        ACPConnectorService.create_connector(session, agent, connector_in)
    )


@router.get("/agents/{agent_id}/acp-connectors", response_model=ACPConnectorsPublic)
def list_acp_connectors(
    session: SessionDep, current_user: CurrentUser, agent_id: uuid.UUID
) -> ACPConnectorsPublic:
    _owned_agent(session, agent_id, current_user.id)
    connectors = ACPConnectorService.list_connectors(session, agent_id, current_user.id)
    return ACPConnectorsPublic(
        data=[ACPConnectorService.to_public(c) for c in connectors],
        count=len(connectors),
    )


@router.get(
    "/agents/{agent_id}/acp-connectors/{connector_id}",
    response_model=ACPConnectorPublic,
)
def get_acp_connector(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
) -> ACPConnectorPublic:
    return ACPConnectorService.to_public(
        _owned_connector(session, agent_id, connector_id, current_user.id)
    )


@router.put(
    "/agents/{agent_id}/acp-connectors/{connector_id}",
    response_model=ACPConnectorPublic,
)
def update_acp_connector(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
    connector_in: ACPConnectorUpdate,
) -> ACPConnectorPublic:
    connector = _owned_connector(session, agent_id, connector_id, current_user.id)
    if connector_in.mode is not None:
        _check_mode(connector_in.mode, current_user)
    return ACPConnectorService.to_public(
        ACPConnectorService.update_connector(session, connector, connector_in)
    )


@router.delete(
    "/agents/{agent_id}/acp-connectors/{connector_id}", response_model=Message
)
def delete_acp_connector(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
) -> Message:
    connector = _owned_connector(session, agent_id, connector_id, current_user.id)
    ACPConnectorService.delete_connector(session, connector)
    return Message(message="ACP connector deleted")


@router.post(
    "/agents/{agent_id}/acp-connectors/{connector_id}/tokens",
    response_model=ACPTokenCreated,
)
def create_acp_token(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
    token_in: ACPTokenCreate,
    response: Response,
) -> ACPTokenCreated:
    """Mint a bearer token. Its value is returned once and never stored."""
    connector = _owned_connector(session, agent_id, connector_id, current_user.id)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return ACPConnectorService.create_token(session, connector, token_in)


@router.get(
    "/agents/{agent_id}/acp-connectors/{connector_id}/tokens",
    response_model=ACPTokensPublic,
)
def list_acp_tokens(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
) -> ACPTokensPublic:
    _owned_connector(session, agent_id, connector_id, current_user.id)
    tokens = ACPConnectorService.list_tokens(session, connector_id)
    return ACPTokensPublic(data=tokens, count=len(tokens))


@router.post(
    "/agents/{agent_id}/acp-connectors/{connector_id}/tokens/{token_id}/revoke",
    response_model=ACPTokenPublic,
)
def revoke_acp_token(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
    token_id: uuid.UUID,
) -> ACPTokenPublic:
    """Permanently revoke a token.

    Create a replacement to restore access. Conversations started with the
    revoked token cannot be reopened: each ACP session is bound to the token
    that created it, so a replacement token starts fresh.
    """
    _owned_connector(session, agent_id, connector_id, current_user.id)
    token = _scoped_token(session, connector_id, token_id)
    return ACPConnectorService.revoke_token(session, token)


@router.delete(
    "/agents/{agent_id}/acp-connectors/{connector_id}/tokens/{token_id}",
    response_model=Message,
)
def delete_acp_token(
    session: SessionDep,
    current_user: CurrentUser,
    agent_id: uuid.UUID,
    connector_id: uuid.UUID,
    token_id: uuid.UUID,
) -> Message:
    """Delete a token.

    Like revoking it, this permanently ends the app's access, and conversations
    started with this token cannot be reopened — each ACP session is bound to
    the token that created it.
    """
    _owned_connector(session, agent_id, connector_id, current_user.id)
    ACPConnectorService.delete_token(
        session, _scoped_token(session, connector_id, token_id)
    )
    return Message(message="ACP token deleted")
