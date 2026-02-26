import secrets
import uuid
from datetime import datetime, timedelta, UTC
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.models import Agent
from app.models.mcp_connector import MCPConnector
from app.models.mcp_oauth_client import MCPOAuthClient
from app.models.mcp_auth_code import MCPAuthCode, MCPAuthRequest

router = APIRouter(prefix="/mcp/consent", tags=["mcp-consent"])


class ConsentInfo(BaseModel):
    """Non-sensitive info displayed on the consent page."""
    agent_name: str
    connector_name: str
    connector_mode: str
    client_name: str
    scopes: list[str]
    expires_at: datetime


class ConsentApproveResponse(BaseModel):
    redirect_url: str


@router.get("/{nonce}", response_model=ConsentInfo)
def get_consent_info(
    session: SessionDep,
    nonce: str,
) -> Any:
    """Fetch auth request details for the consent page. Public endpoint."""
    auth_request = session.get(MCPAuthRequest, nonce)
    if not auth_request:
        raise HTTPException(status_code=404, detail="Auth request not found")
    if auth_request.used:
        raise HTTPException(status_code=400, detail="Auth request already used")
    now = datetime.now(UTC).replace(tzinfo=None)
    if auth_request.expires_at < now:
        raise HTTPException(status_code=400, detail="Auth request expired")

    # Load connector and agent info
    connector = session.get(MCPConnector, auth_request.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    agent = session.get(Agent, connector.agent_id)
    agent_name = agent.name if agent else "Unknown Agent"

    # Load client info
    oauth_client = session.exec(
        select(MCPOAuthClient).where(MCPOAuthClient.client_id == auth_request.client_id)
    ).first()
    client_name = oauth_client.client_name if oauth_client else "Unknown Client"

    scopes = [s for s in auth_request.scope.split(" ") if s] if auth_request.scope else []

    return ConsentInfo(
        agent_name=agent_name,
        connector_name=connector.name,
        connector_mode=connector.mode,
        client_name=client_name,
        scopes=scopes,
        expires_at=auth_request.expires_at,
    )


@router.post("/{nonce}/approve", response_model=ConsentApproveResponse)
def approve_consent(
    session: SessionDep,
    current_user: CurrentUser,
    nonce: str,
) -> Any:
    """User approves the OAuth consent. Requires JWT auth."""
    auth_request = session.get(MCPAuthRequest, nonce)
    if not auth_request:
        raise HTTPException(status_code=404, detail="Auth request not found")
    if auth_request.used:
        raise HTTPException(status_code=400, detail="Auth request already used")
    now = datetime.now(UTC).replace(tzinfo=None)
    if auth_request.expires_at < now:
        raise HTTPException(status_code=400, detail="Auth request expired")

    # Check email access: user must be connector owner or in allowed_emails
    connector = session.get(MCPConnector, auth_request.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    is_owner = connector.owner_id == current_user.id
    email_allowed = (
        current_user.email
        and connector.allowed_emails
        and current_user.email.lower() in [e.lower() for e in connector.allowed_emails]
    )
    if not is_owner and not email_allowed:
        raise HTTPException(status_code=403, detail="You don't have access to this connector")

    # Mark auth request as used
    auth_request.used = True
    session.add(auth_request)

    # Create auth code
    code = secrets.token_urlsafe(48)
    auth_code = MCPAuthCode(
        code=code,
        client_id=auth_request.client_id,
        user_id=current_user.id,
        connector_id=auth_request.connector_id,
        redirect_uri=auth_request.redirect_uri,
        code_challenge=auth_request.code_challenge,
        scope=auth_request.scope,
        resource=auth_request.resource,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    session.add(auth_code)
    session.commit()

    # Build redirect URL with code and state
    params = {"code": code}
    if auth_request.state:
        params["state"] = auth_request.state
    redirect_url = f"{auth_request.redirect_uri}?{urlencode(params)}"

    return ConsentApproveResponse(redirect_url=redirect_url)
