"""
MCP tool registration and MCP-specific request dispatching.

This module contains only MCP-specific logic:
- Context variable extraction (connector_id, mcp_session_id)
- MCP transport session ID resolution from multiple sources
- Tool registration on FastMCP server instances

All business logic (session management, message creation, streaming)
is delegated to MCPRequestHandler, following the same isolation pattern
as A2ARequestHandler.
"""
import uuid
import logging

from app.core.db import create_session
from app.services.mcp_connector_service import MCPConnectorService
from app.mcp.request_handler import MCPRequestHandler
from app.mcp.server import mcp_connector_id_var, mcp_session_id_var

logger = logging.getLogger(__name__)


async def handle_send_message(message: str, ctx=None) -> str:
    """
    MCP tool handler: send a message to the agent and return the response.

    This is registered on each per-connector FastMCP server instance.

    IMPORTANT: Any unhandled exception here kills the MCP session, causing all
    subsequent requests to return 400. Always return an error string instead.
    """
    try:
        return await _handle_send_message_inner(message, ctx)
    except Exception as e:
        logger.exception(f"Unhandled error in MCP send_message tool: {e}")
        return f"Error: {str(e)}"


async def _handle_send_message_inner(message: str, ctx=None) -> str:
    """
    MCP-specific entry point: extract MCP context, resolve entities, delegate.

    Analogous to the A2A route handler that resolves agent/environment
    before creating A2ARequestHandler.
    """
    # Extract connector_id from context var (set by MCPServerRegistry)
    connector_id_str = mcp_connector_id_var.get(None)
    if not connector_id_str:
        return "Error: No connector context available"

    # Extract MCP transport session ID from context var (set by MCPServerRegistry)
    mcp_transport_session_id = mcp_session_id_var.get(None)

    # Also try to get it from the tool context (Starlette request headers)
    ctx_session_id = None
    if ctx is not None:
        try:
            req_ctx = getattr(ctx, 'request_context', None)
            if req_ctx is not None:
                starlette_request = getattr(req_ctx, 'request', None)
                if starlette_request is not None:
                    ctx_session_id = starlette_request.headers.get("mcp-session-id")
        except Exception as e:
            logger.debug(f"[MCP] Could not extract session ID from ctx: {e}")

    # Use whichever source has the session ID
    effective_mcp_session_id = mcp_transport_session_id or ctx_session_id

    logger.info(
        "[MCP] send_message called | connector=%s | mcp_session_id(contextvar)=%s | "
        "mcp_session_id(ctx)=%s | effective=%s | ctx_type=%s | message_preview=%.80s",
        connector_id_str,
        mcp_transport_session_id or "(none)",
        ctx_session_id or "(none)",
        effective_mcp_session_id or "(none)",
        type(ctx).__name__ if ctx else "None",
        message,
    )

    connector_id = uuid.UUID(connector_id_str)

    # Resolve connector, agent, and environment (analogous to A2A route resolution)
    with create_session() as db:
        try:
            connector, agent, environment = MCPConnectorService.resolve_connector_context(
                db, connector_id,
            )
        except ValueError as e:
            logger.warning("[MCP] Context resolution failed for connector %s: %s", connector_id_str, e)
            return f"Error: {e}"

    # Create handler and delegate (same pattern as A2ARequestHandler)
    handler = MCPRequestHandler(
        agent=agent,
        environment=environment,
        connector=connector,
        get_db_session=create_session,
    )
    return await handler.handle_send_message(message, effective_mcp_session_id)


def register_mcp_tools(server) -> None:
    """Register all MCP tools on the given FastMCP server instance."""
    from mcp.server.fastmcp.server import Context

    @server.tool(
        name="send_message",
        description="Send a message to the AI agent and receive a response. The agent can use tools, write code, and perform tasks based on your message.",
    )
    async def send_message(message: str, ctx: Context = None) -> str:
        return await handle_send_message(message, ctx)
