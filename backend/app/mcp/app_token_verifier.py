"""
App MCP Token Verifier — validates bearer tokens for the app-level MCP server.

Mirrors MCPTokenVerifier but validates against app_mcp_token (no connector_id).
"""
import logging
from datetime import datetime, UTC

from mcp.server.auth.provider import TokenVerifier, AccessToken
from sqlmodel import Session as DBSession, select

from app.core.db import engine
from app.models.app_mcp.app_mcp_token import AppMCPToken
from app.mcp.context_vars import mcp_authenticated_user_id_var

logger = logging.getLogger(__name__)


def _hash_token(token: str) -> str:
    """SHA256 hash of a token string."""
    import hashlib
    return hashlib.sha256(token.encode()).hexdigest()


class AppMCPTokenVerifier(TokenVerifier):
    """Verifies App MCP bearer tokens against the app_mcp_token table."""

    async def verify_token(self, token: str) -> AccessToken | None:
        """Verify a bearer token and return an AccessToken if valid."""
        token_hash = _hash_token(token)

        with DBSession(engine) as db:
            token_record = db.exec(
                select(AppMCPToken).where(
                    AppMCPToken.token_hash == token_hash,
                    AppMCPToken.token_type == "access",
                )
            ).first()

            if not token_record:
                logger.debug("[AppMCP] Token not found in database")
                return None

            # Check expiry (DB stores naive UTC datetimes)
            if token_record.expires_at < datetime.now(UTC).replace(tzinfo=None):
                logger.debug("[AppMCP] Token expired")
                return None

            # Check revocation
            if token_record.is_revoked:
                logger.debug("[AppMCP] Token revoked")
                return None

            scopes = [s for s in token_record.scope.split(" ") if s] if token_record.scope else []
            expires_at_ts = int(token_record.expires_at.timestamp()) if token_record.expires_at else None

            # Propagate authenticated user identity to tool handlers via ContextVar.
            mcp_authenticated_user_id_var.set(str(token_record.user_id))

            return AccessToken(
                token=token,
                client_id=token_record.client_id,
                scopes=scopes,
                expires_at=expires_at_ts,
                resource=token_record.resource or None,
            )
