"""
App MCP Server — creates the singleton application-level MCP server instance.

The App MCP Server acts as a router: it receives a message from any authenticated
user, routes it to the appropriate agent, and returns the response.

URL pattern: /mcp/app/mcp
"""
import logging

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings

from app.core.config import settings
from app.mcp.app_token_verifier import AppMCPTokenVerifier
from app.mcp.server import _build_transport_security
from app.mcp.shared_session_manager import SharedSessionManager

logger = logging.getLogger(__name__)


def create_app_mcp_server() -> FastMCP:
    """Create the singleton App MCP Server instance."""
    base_url = (settings.MCP_SERVER_BASE_URL or "").rstrip("/")
    resource_url = f"{base_url}/app/mcp"
    issuer_url = f"{base_url}/oauth"

    server = FastMCP(
        name="app-mcp-server",
        auth=AuthSettings(
            issuer_url=issuer_url,
            resource_server_url=resource_url,
        ),
        token_verifier=AppMCPTokenVerifier(),
        transport_security=_build_transport_security(),
    )

    # Register tool handlers
    from app.mcp.app_tools import register_app_mcp_tools
    register_app_mcp_tools(server)

    # Register dynamic per-user prompts
    from app.mcp.app_prompts import register_app_mcp_prompts
    register_app_mcp_prompts(server)

    # Inject DB-backed session manager (same pattern as per-connector server)
    server._session_manager = SharedSessionManager(
        connector_id="app",  # special sentinel — not a UUID
        app=server._mcp_server,
        event_store=server._event_store,
        json_response=server.settings.json_response,
        stateless=server.settings.stateless_http,
        security_settings=server.settings.transport_security,
    )

    logger.info("[AppMCP] App MCP Server created | resource_url=%s", resource_url)
    return server
