from datetime import datetime, UTC
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlmodel import select

from app.api.deps import CurrentUser, SessionDep
from app.services.mcp.mcp_consent_service import MCPConsentService
from app.services.mcp.mcp_errors import MCPError

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


def _handle_mcp_error(e: MCPError) -> None:
    """Convert service exceptions to HTTP exceptions."""
    raise HTTPException(status_code=e.status_code, detail=e.message)


def _get_app_mcp_consent_info(session: SessionDep, nonce: str) -> ConsentInfo | None:
    """Try to look up an app-level MCP auth request by nonce.

    Returns ConsentInfo if the nonce belongs to an AppMCPAuthRequest, or None
    if no such record exists (caller should fall through to per-connector logic).
    Raises HTTPException for expired/used requests.
    """
    from app.models.app_mcp.app_mcp_auth_code import AppMCPAuthRequest
    from app.models.app_mcp.app_mcp_oauth_client import AppMCPOAuthClient

    auth_request = session.get(AppMCPAuthRequest, nonce)
    if auth_request is None:
        return None

    if auth_request.used:
        raise HTTPException(status_code=400, detail="Auth request already used")

    now = datetime.now(UTC).replace(tzinfo=None)
    if auth_request.expires_at < now:
        raise HTTPException(status_code=400, detail="Auth request expired")

    oauth_client = session.exec(
        select(AppMCPOAuthClient).where(
            AppMCPOAuthClient.client_id == auth_request.client_id
        )
    ).first()
    client_name = ""
    if oauth_client:
        client_name = oauth_client.client_name
    else:
        # Fall back to per-connector table (client may have registered without resource)
        from app.models.mcp.mcp_oauth_client import MCPOAuthClient
        per_connector_client = session.exec(
            select(MCPOAuthClient).where(
                MCPOAuthClient.client_id == auth_request.client_id
            )
        ).first()
        if per_connector_client:
            client_name = per_connector_client.client_name
    client_name = client_name or "Unknown Client"

    scopes = (
        [s for s in auth_request.scope.split(" ") if s]
        if auth_request.scope
        else []
    )

    return ConsentInfo(
        agent_name="Application MCP Server",
        connector_name="App MCP Server",
        connector_mode="routing",
        client_name=client_name,
        scopes=scopes,
        expires_at=auth_request.expires_at,
    )


@router.get("/{nonce}", response_model=ConsentInfo)
def get_consent_info(
    session: SessionDep,
    nonce: str,
    app_mcp: bool = Query(default=False),
) -> Any:
    """Fetch auth request details for the consent page. Public endpoint.

    Handles both per-connector and app-level (App MCP Server) consent flows.
    The optional `app_mcp` query param is a hint from the frontend, but the
    endpoint always does a real DB lookup to determine the request type.
    """
    # Check app-level MCP consent first — these use AppMCPAuthRequest
    app_consent = _get_app_mcp_consent_info(session, nonce)
    if app_consent is not None:
        return app_consent

    # Fall through to per-connector consent (MCPAuthRequest)
    try:
        details = MCPConsentService.get_consent_details(session, nonce)
    except MCPError as e:
        _handle_mcp_error(e)

    return ConsentInfo(
        agent_name=details.agent_name,
        connector_name=details.connector_name,
        connector_mode=details.connector_mode,
        client_name=details.client_name,
        scopes=details.scopes,
        expires_at=details.expires_at,
    )


@router.post("/{nonce}/approve", response_model=ConsentApproveResponse)
def approve_consent(
    session: SessionDep,
    current_user: CurrentUser,
    nonce: str,
) -> Any:
    """User approves the OAuth consent. Requires JWT auth.

    Handles both per-connector and app-level (App MCP Server) consent flows.
    """
    from app.models.app_mcp.app_mcp_auth_code import AppMCPAuthRequest
    from app.services.app_mcp.app_mcp_oauth_service import AppMCPOAuthService

    # Check if this is an app-level consent request
    auth_request = session.get(AppMCPAuthRequest, nonce)
    if auth_request is not None:
        try:
            _code, redirect_url = AppMCPOAuthService.create_auth_code_from_request(
                db_session=session,
                nonce=nonce,
                user_id=current_user.id,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return ConsentApproveResponse(redirect_url=redirect_url)

    # Fall through to per-connector consent
    try:
        redirect_url = MCPConsentService.approve_consent(
            session, nonce, current_user,
        )
    except MCPError as e:
        _handle_mcp_error(e)

    return ConsentApproveResponse(redirect_url=redirect_url)
