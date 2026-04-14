"""
App MCP Server tools — registers the send_message tool on the App MCP FastMCP instance.
"""
import json
import logging
import uuid

from app.mcp.context_vars import mcp_authenticated_user_id_var, mcp_session_id_var

logger = logging.getLogger(__name__)


def register_app_mcp_tools(server) -> None:
    """Register all App MCP tools on the given FastMCP server instance."""
    from mcp.server.fastmcp.server import Context

    @server.tool(
        name="send_message",
        description=(
            "Send a message to the platform. The system will automatically route it "
            "to the appropriate AI agent based on your message content.\n\n"
            "Returns a JSON object with 'response', 'context_id', and 'agent_name' fields. "
            "IMPORTANT: Always pass back the 'context_id' from the previous response "
            "to continue the conversation with the same agent. "
            "On the first message in a new conversation, omit context_id or pass an empty string."
        ),
    )
    async def send_message(message: str, context_id: str = "", ctx: Context = None) -> str:
        try:
            return await _handle_send_message(message, context_id or None, ctx)
        except Exception as e:
            logger.exception("[AppMCP] Unhandled error in send_message tool: %s", e)
            return json.dumps({"error": str(e), "context_id": context_id or ""})


async def _handle_send_message(
    message: str,
    context_id: str | None,
    ctx=None,
) -> str:
    """Extract user identity and delegate to AppMCPRequestHandler."""
    from app.services.app_mcp.app_mcp_request_handler import AppMCPRequestHandler

    auth_user_id_str = mcp_authenticated_user_id_var.get(None)
    if not auth_user_id_str:
        return json.dumps({"error": "Not authenticated", "context_id": ""})

    try:
        user_id = uuid.UUID(auth_user_id_str)
    except ValueError:
        return json.dumps({"error": "Invalid user identity", "context_id": ""})

    return await AppMCPRequestHandler.handle_send_message(
        user_id=user_id,
        message=message,
        context_id=context_id,
        mcp_ctx=ctx,
    )
