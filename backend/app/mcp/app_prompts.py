"""
App MCP Server prompts — exposes user's active agent routes as MCP prompts.

This enables external AI clients (Claude Desktop, Cursor) to discover
available agents via MCP prompts/list without guessing.
"""
import logging
import re
import uuid

from app.mcp.context_vars import mcp_authenticated_user_id_var

logger = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """Convert a route name to a slug suitable for use as a prompt name."""
    slug = name.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug or "agent"


def register_app_mcp_prompts(server) -> None:
    """Register dynamic per-user prompts on the App MCP FastMCP instance."""

    @server.prompt()
    async def list_available_agents() -> list:
        """List available agents as MCP prompts for the authenticated user.

        Returns prompts representing each active route's trigger description.
        """
        from app.core.db import create_session
        from app.services.app_mcp.app_agent_route_service import AppAgentRouteService

        auth_user_id_str = mcp_authenticated_user_id_var.get(None)
        if not auth_user_id_str:
            return []

        try:
            user_id = uuid.UUID(auth_user_id_str)
        except ValueError:
            return []

        try:
            with create_session() as db:
                effective_routes = AppAgentRouteService.get_effective_routes_for_user(
                    db_session=db,
                    user_id=user_id,
                    channel="app_mcp",
                )
        except Exception as e:
            logger.error("[AppMCP] Failed to load prompts for user %s: %s", user_id, e)
            return []

        from mcp.types import TextContent, PromptMessage
        prompts = []
        for route in effective_routes:
            prompts.append(
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=route.trigger_prompt,
                    ),
                )
            )
        return prompts
