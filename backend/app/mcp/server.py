import uuid
import logging
from contextlib import asynccontextmanager
from contextvars import ContextVar
from urllib.parse import urlparse

import anyio
from starlette.responses import JSONResponse
from starlette.routing import get_route_path
from starlette.types import ASGIApp, Receive, Scope, Send

from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings

from sqlmodel import Session as DBSession

from app.core.config import settings
from app.core.db import engine
from app.models.mcp_connector import MCPConnector
from app.mcp.token_verifier import MCPTokenVerifier

logger = logging.getLogger(__name__)

# Context var to pass connector_id to tool handlers
mcp_connector_id_var: ContextVar[str] = ContextVar("mcp_connector_id")


def _build_transport_security() -> TransportSecuritySettings:
    """Build TransportSecuritySettings from the configured MCP_SERVER_BASE_URL.

    The MCP SDK auto-enables DNS rebinding protection for localhost, only
    allowing 127.0.0.1/localhost/[::1]. When the server is behind a tunnel
    (e.g. pinggy), the Host header is the tunnel hostname, which gets rejected.
    We extract the host from MCP_SERVER_BASE_URL and allow it explicitly.
    """
    base_url = settings.MCP_SERVER_BASE_URL or ""
    parsed = urlparse(base_url)
    hostname = parsed.hostname or ""

    # Always allow localhost variants
    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    allowed_origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]

    # Add the configured external host (e.g. tunnel hostname)
    if hostname and hostname not in ("127.0.0.1", "localhost", "::1"):
        allowed_hosts.append(f"{hostname}:*")
        # Also allow without port (Host header may omit default ports)
        allowed_hosts.append(hostname)
        scheme = parsed.scheme or "https"
        allowed_origins.append(f"{scheme}://{hostname}:*")
        allowed_origins.append(f"{scheme}://{hostname}")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


def create_mcp_server_for_connector(connector_id: str) -> FastMCP:
    """Create a FastMCP server instance for a specific connector."""
    base_url = settings.MCP_SERVER_BASE_URL.rstrip("/")
    resource_url = f"{base_url}/{connector_id}/mcp"
    issuer_url = f"{base_url}/oauth"

    server = FastMCP(
        name=f"mcp-connector-{connector_id}",
        auth=AuthSettings(
            issuer_url=issuer_url,
            resource_server_url=resource_url,
        ),
        token_verifier=MCPTokenVerifier(connector_id),
        transport_security=_build_transport_security(),
    )

    # Register tool handlers
    from app.mcp.tools import register_mcp_tools
    register_mcp_tools(server)

    return server


class MCPServerRegistry:
    """
    ASGI dispatcher that routes /{connector_id}/... to per-connector MCP server apps.

    Mounted at /mcp in the main FastAPI app, so full paths are:
    /mcp/{connector_id}/mcp -> per-connector MCP Streamable HTTP endpoint

    The registry manages session manager lifecycles: each per-connector FastMCP app
    has a StreamableHTTPSessionManager that requires an active anyio task group.
    The registry's run() context creates a parent task group and starts each
    connector's session_manager.run() within it.
    """

    def __init__(self):
        self._servers: dict[str, ASGIApp] = {}
        self._mcp_instances: dict[str, FastMCP] = {}
        self._task_group: anyio.abc.TaskGroup | None = None

    @asynccontextmanager
    async def run(self):
        """Async context manager that manages the parent task group for all
        per-connector session managers. Must be active before handling requests.

        Use inside the FastAPI app lifespan:
            async with mcp_registry.run():
                yield
        """
        async with anyio.create_task_group() as tg:
            self._task_group = tg
            logger.info("MCP server registry started")
            try:
                yield
            finally:
                tg.cancel_scope.cancel()
                self._task_group = None
                self._servers.clear()
                self._mcp_instances.clear()
                logger.info("MCP server registry shut down")

    async def get_or_create(self, connector_id: str) -> ASGIApp | None:
        """Get or lazily create an ASGI app for the given connector.

        When creating a new app, also starts the session manager's run()
        context in the parent task group so the anyio task group is initialized.
        """
        if connector_id in self._servers:
            return self._servers[connector_id]

        # Validate connector exists and is active
        with DBSession(engine) as db:
            connector = db.get(MCPConnector, uuid.UUID(connector_id))
            if not connector or not connector.is_active:
                return None

        mcp_server = create_mcp_server_for_connector(connector_id)
        asgi_app = mcp_server.streamable_http_app()

        # Start the session manager's run() context in our parent task group.
        # This initializes the anyio task group that StreamableHTTPSessionManager
        # needs for spawning per-session/per-request MCP server tasks.
        session_manager = mcp_server.session_manager

        async def _run_session_manager(*, task_status=anyio.TASK_STATUS_IGNORED):
            async with session_manager.run():
                task_status.started()
                # Keep alive until cancelled by parent task group on shutdown/remove
                await anyio.sleep_forever()

        if self._task_group is None:
            logger.error("MCPServerRegistry.run() is not active — cannot start session manager")
            return None

        await self._task_group.start(_run_session_manager)

        self._servers[connector_id] = asgi_app
        self._mcp_instances[connector_id] = mcp_server
        logger.info(f"Created MCP server for connector {connector_id}")
        return asgi_app

    def remove(self, connector_id: str) -> None:
        """Evict a connector's MCP server (on deactivation/deletion)."""
        removed = False
        if connector_id in self._servers:
            del self._servers[connector_id]
            removed = True
        if connector_id in self._mcp_instances:
            del self._mcp_instances[connector_id]
            removed = True
        if removed:
            logger.info(f"Removed MCP server for connector {connector_id}")

    def clear(self) -> None:
        """Clear all servers (for shutdown). Called by the run() context on exit."""
        self._servers.clear()
        self._mcp_instances.clear()
        logger.info("Cleared all MCP servers")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI dispatcher — extract connector_id from path, delegate to per-connector app."""
        if scope["type"] not in ("http", "websocket"):
            return

        # Use get_route_path to get the effective path with root_path prefix stripped
        # (Starlette Mount sets root_path but does NOT modify scope["path"])
        path = get_route_path(scope)
        # Path format: /{connector_id}/... (root_path prefix stripped by get_route_path)
        parts = path.strip("/").split("/", 1)
        if not parts or not parts[0]:
            response = JSONResponse({"detail": "Connector ID required"}, status_code=404)
            await response(scope, receive, send)
            return

        connector_id_str = parts[0]

        # Validate UUID format
        try:
            uuid.UUID(connector_id_str)
        except ValueError:
            response = JSONResponse({"detail": "Invalid connector ID"}, status_code=404)
            await response(scope, receive, send)
            return

        # Get or create the per-connector app (async — may start session manager)
        app = await self.get_or_create(connector_id_str)
        if app is None:
            response = JSONResponse({"detail": "Connector not found or inactive"}, status_code=404)
            await response(scope, receive, send)
            return

        # Strip stale mcp-session-id headers so the SDK creates a fresh session
        # instead of returning 404 "Session not found" after a server restart.
        scope = dict(scope)
        headers = list(scope.get("headers", []))
        session_id = None
        for name, value in headers:
            if name == b"mcp-session-id":
                session_id = value.decode("ascii", errors="replace")
                break

        if session_id:
            mcp_instance = self._mcp_instances.get(connector_id_str)
            if mcp_instance:
                # Check if the session actually exists in the session manager
                known_sessions = getattr(
                    mcp_instance.session_manager, "_server_instances", {}
                )
                if session_id not in known_sessions:
                    logger.warning(
                        "Stripped stale MCP session ID %s for connector %s",
                        session_id,
                        connector_id_str,
                    )
                    headers = [
                        (n, v) for n, v in headers if n != b"mcp-session-id"
                    ]
                    scope["headers"] = headers

        # Set context var for tool handlers
        token = mcp_connector_id_var.set(connector_id_str)
        try:
            # Rewrite path to strip the connector_id prefix
            remaining_path = f"/{parts[1]}" if len(parts) > 1 else "/"
            scope["path"] = remaining_path
            original_root_path = scope.get("root_path", "")
            scope["root_path"] = f"{original_root_path}/mcp/{connector_id_str}"

            await app(scope, receive, send)
        finally:
            mcp_connector_id_var.reset(token)


# Singleton registry instance
mcp_registry = MCPServerRegistry()
