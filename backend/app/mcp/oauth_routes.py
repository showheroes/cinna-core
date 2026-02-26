import hashlib
import secrets
import uuid
import logging
from datetime import datetime, timedelta, UTC
from urllib.parse import urlencode

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlmodel import select

from app.core.config import settings
from app.core.db import create_session
from app.models.mcp_connector import MCPConnector
from app.models.mcp_oauth_client import MCPOAuthClient
from app.models.mcp_auth_code import MCPAuthCode, MCPAuthRequest
from app.models.mcp_token import MCPToken

logger = logging.getLogger(__name__)

router = APIRouter(tags=["mcp-oauth"])



def _extract_connector_id_from_resource(resource_url: str) -> str | None:
    """Extract connector_id UUID from resource URL like {base}/connector-id/mcp."""
    if not resource_url or not settings.MCP_SERVER_BASE_URL:
        return None
    base = settings.MCP_SERVER_BASE_URL.rstrip("/")
    if not resource_url.startswith(base + "/"):
        return None
    remainder = resource_url[len(base) + 1:]  # "connector-id/mcp" or "connector-id/mcp/"
    parts = remainder.strip("/").split("/")
    if len(parts) >= 1:
        try:
            uuid.UUID(parts[0])
            return parts[0]
        except ValueError:
            return None
    return None


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _verify_secret(plain: str, hashed: str) -> bool:
    return _hash_secret(plain) == hashed


def _generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


# ── RFC 9728 Protected Resource Metadata (root-level) ────────────────────
# This router is mounted at the app root (not under /mcp/oauth) because
# RFC 9728 requires /.well-known/oauth-protected-resource to be at the origin root.
# The MCP SDK generates resource_metadata URLs like:
#   https://host/.well-known/oauth-protected-resource/mcp/{connector_id}/mcp
# which must resolve at the server root level.

wellknown_router = APIRouter(tags=["mcp-oauth"])


@wellknown_router.get("/.well-known/oauth-protected-resource/{resource_path:path}")
def get_protected_resource_metadata(resource_path: str) -> JSONResponse:
    """RFC 9728 — OAuth Protected Resource Metadata."""
    connector_id_str = _extract_connector_id_from_resource_path(resource_path)
    if not connector_id_str:
        raise HTTPException(status_code=404, detail="Resource not found")

    base = settings.MCP_SERVER_BASE_URL.rstrip("/") if settings.MCP_SERVER_BASE_URL else ""
    resource_url = f"{base}/{connector_id_str}/mcp"

    return JSONResponse({
        "resource": resource_url,
        "authorization_servers": [f"{base}/oauth"],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["mcp:tools", "mcp:resources"],
    })


def _as_metadata_response() -> JSONResponse:
    """Build the RFC 8414 Authorization Server Metadata JSON response."""
    base = settings.MCP_SERVER_BASE_URL.rstrip("/") if settings.MCP_SERVER_BASE_URL else ""
    return JSONResponse({
        "issuer": f"{base}/oauth",
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["mcp:tools", "mcp:resources"],
    })


@wellknown_router.get("/.well-known/oauth-authorization-server")
def get_as_metadata_wellknown_root() -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata (exact path, no suffix).

    Some MCP clients request this path without appending the issuer path.
    This avoids a 307 redirect from FastAPI's trailing-slash handling.
    """
    return _as_metadata_response()


@wellknown_router.get("/.well-known/oauth-authorization-server/{issuer_path:path}")
def get_as_metadata_wellknown(issuer_path: str) -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata (root-level well-known path).

    MCP clients discover the AS by requesting:
      /.well-known/oauth-authorization-server/mcp/oauth
    (issuer path appended after the well-known prefix per RFC 8414 Section 3).
    """
    return _as_metadata_response()


def _extract_connector_id_from_resource_path(resource_path: str) -> str | None:
    """Extract connector_id UUID from a resource path like 'mcp/{connector_id}/mcp'."""
    parts = resource_path.strip("/").split("/")
    # Expected: ["mcp", "{connector_id}", "mcp"] or ["{connector_id}", "mcp"]
    for part in parts:
        try:
            uuid.UUID(part)
            return part
        except ValueError:
            continue
    return None


# ── AS Metadata ──────────────────────────────────────────────────────────

@router.get("/.well-known/oauth-authorization-server")
def get_as_metadata() -> JSONResponse:
    """RFC 8414 — Authorization Server Metadata."""
    base = settings.MCP_SERVER_BASE_URL.rstrip("/") if settings.MCP_SERVER_BASE_URL else ""
    return JSONResponse({
        "issuer": f"{base}/oauth",
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "registration_endpoint": f"{base}/oauth/register",
        "revocation_endpoint": f"{base}/oauth/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": ["mcp:tools", "mcp:resources"],
    })


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
    connector. Otherwise, the client is registered globally and the connector
    binding happens during the authorize step.
    """
    connector_id: uuid.UUID | None = None
    connector_id_str = _extract_connector_id_from_resource(body.resource)

    if connector_id_str:
        connector_id = uuid.UUID(connector_id_str)
        with create_session() as db:
            connector = db.get(MCPConnector, connector_id)
            if not connector or not connector.is_active:
                raise HTTPException(status_code=404, detail="Connector not found or inactive")

            # Enforce max_clients
            existing_count = db.exec(
                select(MCPOAuthClient).where(MCPOAuthClient.connector_id == connector_id)
            ).all()
            if len(existing_count) >= connector.max_clients:
                raise HTTPException(status_code=429, detail="Maximum number of clients reached")

    with create_session() as db:
        # Generate credentials
        client_id = str(uuid.uuid4())
        client_secret = secrets.token_urlsafe(48)

        oauth_client = MCPOAuthClient(
            client_id=client_id,
            client_secret_hash=_hash_secret(client_secret),
            client_name=body.client_name,
            redirect_uris=body.redirect_uris,
            grant_types=body.grant_types,
            response_types=body.response_types,
            connector_id=connector_id,
        )
        db.add(oauth_client)
        db.commit()

    return JSONResponse(
        status_code=201,
        content={
            "client_id": client_id,
            "client_secret": client_secret,
            "client_name": body.client_name,
            "redirect_uris": body.redirect_uris,
            "grant_types": body.grant_types,
            "response_types": body.response_types,
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
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Unsupported response_type")

    connector_id_str = _extract_connector_id_from_resource(resource)
    if not connector_id_str:
        raise HTTPException(status_code=400, detail="Invalid resource URL")

    connector_id = uuid.UUID(connector_id_str)

    with create_session() as db:
        # Validate client exists (may be global or connector-specific)
        oauth_client = db.exec(
            select(MCPOAuthClient).where(MCPOAuthClient.client_id == client_id)
        ).first()
        if not oauth_client:
            raise HTTPException(status_code=400, detail="Unknown client_id for this resource")

        # Store auth request
        nonce = secrets.token_urlsafe(32)
        auth_request = MCPAuthRequest(
            nonce=nonce,
            connector_id=connector_id,
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            scope=scope,
            state=state,
            resource=resource,
            expires_at=datetime.now(UTC) + timedelta(minutes=10),
        )
        db.add(auth_request)
        db.commit()

    # Redirect to frontend consent page
    frontend_url = settings.FRONTEND_HOST.rstrip("/")
    consent_url = f"{frontend_url}/oauth/mcp-consent?nonce={nonce}"
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
    if grant_type == "authorization_code":
        return _handle_authorization_code(
            grant_type=grant_type, code=code, redirect_uri=redirect_uri,
            client_id=client_id, client_secret=client_secret,
            code_verifier=code_verifier, resource=resource,
        )
    elif grant_type == "refresh_token":
        return _handle_refresh_token(
            client_id=client_id, client_secret=client_secret,
            refresh_token=refresh_token,
        )
    else:
        raise HTTPException(status_code=400, detail="Unsupported grant_type")


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    """Verify PKCE S256 challenge."""
    if not code_verifier or not code_challenge:
        return False
    import base64
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return computed == code_challenge


def _handle_authorization_code(
    *, grant_type: str, code: str, redirect_uri: str,
    client_id: str, client_secret: str, code_verifier: str, resource: str,
) -> JSONResponse:
    with create_session() as db:
        # Validate client credentials
        oauth_client = db.exec(
            select(MCPOAuthClient).where(MCPOAuthClient.client_id == client_id)
        ).first()
        if not oauth_client or not _verify_secret(client_secret, oauth_client.client_secret_hash):
            raise HTTPException(status_code=401, detail="Invalid client credentials")

        # Look up auth code
        auth_code = db.get(MCPAuthCode, code)
        if not auth_code:
            raise HTTPException(status_code=400, detail="Invalid authorization code")
        if auth_code.used:
            raise HTTPException(status_code=400, detail="Authorization code already used")
        now = datetime.now(UTC).replace(tzinfo=None)
        if auth_code.expires_at < now:
            raise HTTPException(status_code=400, detail="Authorization code expired")
        if auth_code.client_id != client_id:
            raise HTTPException(status_code=400, detail="Client ID mismatch")

        # Verify PKCE
        if auth_code.code_challenge:
            if not _verify_pkce(code_verifier, auth_code.code_challenge):
                raise HTTPException(status_code=400, detail="Invalid code_verifier")

        # Verify resource matches
        if resource and auth_code.resource and resource != auth_code.resource:
            raise HTTPException(status_code=400, detail="Resource mismatch")

        # Mark code as used
        auth_code.used = True
        db.add(auth_code)

        # Generate tokens
        access_token_str = _generate_opaque_token()
        refresh_token_str = _generate_opaque_token()

        access_token = MCPToken(
            token=access_token_str,
            token_type="access",
            client_id=client_id,
            user_id=auth_code.user_id,
            connector_id=auth_code.connector_id,
            scope=auth_code.scope,
            resource=auth_code.resource,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        refresh_token = MCPToken(
            token=refresh_token_str,
            token_type="refresh",
            client_id=client_id,
            user_id=auth_code.user_id,
            connector_id=auth_code.connector_id,
            scope=auth_code.scope,
            resource=auth_code.resource,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        db.add(access_token)
        db.add(refresh_token)
        db.commit()

        granted_scope = auth_code.scope

    return JSONResponse({
        "access_token": access_token_str,
        "token_type": "bearer",
        "expires_in": 3600,
        "refresh_token": refresh_token_str,
        "scope": granted_scope,
    })


def _handle_refresh_token(
    *, client_id: str, client_secret: str, refresh_token: str,
) -> JSONResponse:
    with create_session() as db:
        # Validate client credentials
        oauth_client = db.exec(
            select(MCPOAuthClient).where(MCPOAuthClient.client_id == client_id)
        ).first()
        if not oauth_client or not _verify_secret(client_secret, oauth_client.client_secret_hash):
            raise HTTPException(status_code=401, detail="Invalid client credentials")

        # Look up refresh token
        token_record = db.exec(
            select(MCPToken).where(
                MCPToken.token == refresh_token,
                MCPToken.token_type == "refresh",
            )
        ).first()
        if not token_record:
            raise HTTPException(status_code=400, detail="Invalid refresh token")
        if token_record.revoked:
            raise HTTPException(status_code=400, detail="Refresh token revoked")
        now = datetime.now(UTC).replace(tzinfo=None)
        if token_record.expires_at < now:
            raise HTTPException(status_code=400, detail="Refresh token expired")
        if token_record.client_id != client_id:
            raise HTTPException(status_code=400, detail="Client ID mismatch")

        # Generate new access token
        new_access_token_str = _generate_opaque_token()
        new_access_token = MCPToken(
            token=new_access_token_str,
            token_type="access",
            client_id=client_id,
            user_id=token_record.user_id,
            connector_id=token_record.connector_id,
            scope=token_record.scope,
            resource=token_record.resource,
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        db.add(new_access_token)
        db.commit()

        granted_scope = token_record.scope

    return JSONResponse({
        "access_token": new_access_token_str,
        "token_type": "bearer",
        "expires_in": 3600,
        "scope": granted_scope,
    })


# ── Token Revocation (RFC 7009) ─────────────────────────────────────────

@router.post("/revoke")
def revoke_token(
    token: str = Form(...),
    client_id: str = Form(""),
    client_secret: str = Form(""),
) -> JSONResponse:
    """Revoke an access or refresh token (application/x-www-form-urlencoded)."""
    with create_session() as db:
        token_record = db.exec(
            select(MCPToken).where(MCPToken.token == token)
        ).first()
        if token_record:
            token_record.revoked = True
            db.add(token_record)
            db.commit()
    # Always return 200 per RFC 7009
    return JSONResponse(status_code=200, content={})
