"""
MCP OAuth Authorization Server routes.

Thin route handlers that delegate all business logic to MCPOAuthService.
Mounted at /mcp/oauth in the main FastAPI app.
"""
import logging

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.core.config import settings
from app.core.db import create_session
from app.services.mcp.mcp_oauth_service import (
    MCPOAuthService,
    DCRInput,
    AuthorizeInput,
    TokenExchangeInput,
    RefreshInput,
    extract_connector_id_from_resource_path,
    get_as_metadata_dict,
)
from app.services.mcp.mcp_errors import MCPError
from app.services.app_mcp.app_mcp_oauth_service import AppMCPOAuthService, is_app_mcp_resource

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp-oauth"])


def _handle_mcp_error(e: MCPError) -> None:
    """Convert service exceptions to HTTP exceptions."""
    raise HTTPException(status_code=e.status_code, detail=e.message)


# ── RFC 9728 Protected Resource Metadata (root-level) ────────────────────
# This router is mounted at the app root (not under /mcp/oauth) because
# RFC 9728 requires /.well-known/oauth-protected-resource to be at the origin root.

wellknown_router = APIRouter(tags=["mcp-oauth"])


@wellknown_router.get("/.well-known/oauth-protected-resource/{resource_path:path}")
def get_protected_resource_metadata(resource_path: str) -> JSONResponse:
    """RFC 9728 — OAuth Protected Resource Metadata."""
    base = settings.MCP_SERVER_BASE_URL.rstrip("/") if settings.MCP_SERVER_BASE_URL else ""

    # Handle App MCP Server path (e.g. "mcp/app/mcp" or "app/mcp")
    stripped = resource_path.strip("/")
    if stripped in ("mcp/app/mcp", "app/mcp"):
        return JSONResponse({
            "resource": f"{base}/app/mcp",
            "authorization_servers": [f"{base}/oauth"],
            "bearer_methods_supported": ["header"],
            "scopes_supported": ["mcp:tools", "mcp:resources"],
        })

    connector_id_str = extract_connector_id_from_resource_path(resource_path)
    if not connector_id_str:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource_url = f"{base}/{connector_id_str}/mcp"

    return JSONResponse({
        "resource": resource_url,
        "authorization_servers": [f"{base}/oauth"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp:tools", "mcp:resources"],
    })


@wellknown_router.get("/.well-known/oauth-authorization-server")
def get_as_metadata_wellknown_root() -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata (exact path, no suffix).

    Some MCP clients request this path without appending the issuer path.
    This avoids a 307 redirect from FastAPI's trailing-slash handling.
    """
    return JSONResponse(get_as_metadata_dict())


@wellknown_router.get("/.well-known/oauth-authorization-server/{issuer_path:path}")
def get_as_metadata_wellknown(issuer_path: str) -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata (root-level well-known path).

    MCP clients discover the AS by requesting:
      /.well-known/oauth-authorization-server/mcp/oauth
    (issuer path appended after the well-known prefix per RFC 8414 Section 3).
    """
    return JSONResponse(get_as_metadata_dict())


# ── AS Metadata ──────────────────────────────────────────────────────────

@router.get("/.well-known/oauth-authorization-server")
def get_as_metadata() -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata."""
    return JSONResponse(get_as_metadata_dict())


# ── Dynamic Client Registration (RFC 7591) ──────────────────────────────

class DCRRequest(BaseModel):
    client_name: str = ""
    redirect_uris: list[str] = []
    grant_types: list[str] = ["authorization_code", "refresh_token"]
    response_types: list[str] = ["code"]
    resource: str = ""  # MCP resource URL containing connector_id


@router.post("/register")
def register_client(body: DCRRequest) -> JSONResponse:
    """Dynamic Client Registration (RFC 7591).

    The `resource` field is optional — some MCP clients (e.g. Claude Desktop)
    don't send it during DCR. If provided, the client is linked to the specific
    connector (or the App MCP Server if resource ends in /app/mcp).
    Otherwise, the client is registered globally and the connector
    binding happens during the authorize step.
    """
    # Delegate to App MCP OAuth if resource points to the app-level server
    if is_app_mcp_resource(body.resource):
        with create_session() as db:
            from app.services.app_mcp.app_mcp_oauth_service import AppDCRInput
            result = AppMCPOAuthService.register_client(
                db,
                AppDCRInput(
                    client_name=body.client_name,
                    redirect_uris=body.redirect_uris,
                    grant_types=body.grant_types,
                    response_types=body.response_types,
                    resource=body.resource,
                ),
            )
        return JSONResponse(status_code=201, content=result)

    with create_session() as db:
        try:
            result = MCPOAuthService.register_client(
                db,
                DCRInput(
                    client_name=body.client_name,
                    redirect_uris=body.redirect_uris,
                    grant_types=body.grant_types,
                    response_types=body.response_types,
                    resource=body.resource,
                ),
            )
        except MCPError as e:
            _handle_mcp_error(e)

    return JSONResponse(
        status_code=201,
        content={
            "client_id": result.client_id,
            "client_secret": result.client_secret,
            "client_name": result.client_name,
            "redirect_uris": result.redirect_uris,
            "grant_types": result.grant_types,
            "response_types": result.response_types,
        },
    )


# ── Authorization Endpoint ───────────────────────────────────────────────

@router.get("/authorize")
def authorize(
    response_type: str,
    client_id: str,
    redirect_uri: str,
    scope: str = "",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
    resource: str = "",
) -> RedirectResponse:
    """OAuth 2.1 Authorization Endpoint — redirects to frontend consent page."""
    # Detect App MCP clients: by resource URL or by client_id lookup
    # (some MCP clients omit the resource parameter during authorize)
    use_app_mcp = is_app_mcp_resource(resource)
    if not use_app_mcp:
        with create_session() as db:
            from app.models.app_mcp.app_mcp_oauth_client import AppMCPOAuthClient
            from sqlmodel import select as sa_select
            use_app_mcp = db.exec(
                sa_select(AppMCPOAuthClient).where(AppMCPOAuthClient.client_id == client_id)
            ).first() is not None

    if use_app_mcp:
        with create_session() as db:
            try:
                consent_url = AppMCPOAuthService.create_authorization(
                    db_session=db,
                    client_id=client_id,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    state=state,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    resource=resource,
                )
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        return RedirectResponse(url=consent_url, status_code=302)

    with create_session() as db:
        try:
            consent_url = MCPOAuthService.create_authorization(
                db,
                AuthorizeInput(
                    response_type=response_type,
                    client_id=client_id,
                    redirect_uri=redirect_uri,
                    scope=scope,
                    state=state,
                    code_challenge=code_challenge,
                    code_challenge_method=code_challenge_method,
                    resource=resource,
                ),
            )
        except MCPError as e:
            _handle_mcp_error(e)

    return RedirectResponse(url=consent_url, status_code=302)


# ── Token Endpoint ───────────────────────────────────────────────────────

@router.post("/token")
def exchange_token(
    grant_type: str = Form(...),
    code: str = Form(""),
    redirect_uri: str = Form(""),
    client_id: str = Form(""),
    client_secret: str = Form(""),
    code_verifier: str = Form(""),
    resource: str = Form(""),
    refresh_token: str = Form(""),
) -> JSONResponse:
    """OAuth 2.1 Token Endpoint (application/x-www-form-urlencoded)."""
    # Detect App MCP clients: check client_id in AppMCPOAuthClient first,
    # then check if the auth code belongs to the App MCP flow (client may
    # have registered in the per-connector table without resource during DCR)
    with create_session() as db:
        from app.models.app_mcp.app_mcp_oauth_client import AppMCPOAuthClient
        from sqlmodel import select as sa_select
        is_app_client = db.exec(
            sa_select(AppMCPOAuthClient).where(AppMCPOAuthClient.client_id == client_id)
        ).first() is not None
        if not is_app_client and grant_type == "authorization_code" and code:
            from app.models.app_mcp.app_mcp_auth_code import AppMCPAuthCode
            is_app_client = db.get(AppMCPAuthCode, code) is not None
        if not is_app_client and grant_type == "refresh_token" and refresh_token:
            from app.models.app_mcp.app_mcp_token import AppMCPToken
            import hashlib
            rh = hashlib.sha256(refresh_token.encode()).hexdigest()
            is_app_client = db.exec(
                sa_select(AppMCPToken).where(
                    AppMCPToken.token_hash == rh,
                    AppMCPToken.token_type == "refresh",
                )
            ).first() is not None

    if is_app_client:
        with create_session() as db:
            try:
                if grant_type == "authorization_code":
                    result = AppMCPOAuthService.exchange_authorization_code(
                        db_session=db,
                        code=code,
                        redirect_uri=redirect_uri,
                        client_id=client_id,
                        client_secret=client_secret,
                        code_verifier=code_verifier,
                        resource=resource,
                    )
                elif grant_type == "refresh_token":
                    result = AppMCPOAuthService.refresh_access_token(
                        db_session=db,
                        client_id=client_id,
                        client_secret=client_secret,
                        refresh_token=refresh_token,
                    )
                else:
                    raise HTTPException(status_code=400, detail="Unsupported grant_type")
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
        response = {
            "access_token": result.access_token,
            "token_type": result.token_type,
            "expires_in": result.expires_in,
            "scope": result.scope,
        }
        if result.refresh_token:
            response["refresh_token"] = result.refresh_token
        return JSONResponse(response)

    with create_session() as db:
        try:
            if grant_type == "authorization_code":
                result = MCPOAuthService.exchange_authorization_code(
                    db,
                    TokenExchangeInput(
                        code=code,
                        redirect_uri=redirect_uri,
                        client_id=client_id,
                        client_secret=client_secret,
                        code_verifier=code_verifier,
                        resource=resource,
                    ),
                )
            elif grant_type == "refresh_token":
                result = MCPOAuthService.refresh_access_token(
                    db,
                    RefreshInput(
                        client_id=client_id,
                        client_secret=client_secret,
                        refresh_token=refresh_token,
                    ),
                )
            else:
                raise HTTPException(status_code=400, detail="Unsupported grant_type")
        except MCPError as e:
            _handle_mcp_error(e)

    response = {
        "access_token": result.access_token,
        "token_type": result.token_type,
        "expires_in": result.expires_in,
        "scope": result.scope,
    }
    if result.refresh_token:
        response["refresh_token"] = result.refresh_token

    return JSONResponse(response)


# ── Token Revocation (RFC 7009) ─────────────────────────────────────────

@router.post("/revoke")
def revoke_token(
    token: str = Form(...),
    client_id: str = Form(""),
    client_secret: str = Form(""),
) -> JSONResponse:
    """Revoke an access or refresh token.

    Tries both App MCP and per-connector token stores.
    Always returns 200 per RFC 7009.
    """
    with create_session() as db:
        # Try App MCP token first
        AppMCPOAuthService.revoke_token(db, token)
        # Also try per-connector token
        MCPOAuthService.revoke_token(db, token)
    return JSONResponse(status_code=200, content={})
