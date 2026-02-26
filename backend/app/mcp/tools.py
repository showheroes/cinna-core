import asyncio
import uuid
import logging
from datetime import datetime, UTC

from sqlmodel import Session as DBSession, select

from app.core.db import engine
from app.models import Agent, Session, SessionCreate, AgentEnvironment
from app.models.mcp_connector import MCPConnector
from app.models.mcp_token import MCPToken
from app.services.session_service import SessionService
from app.services.message_service import MessageService
from app.services.agent_env_connector import agent_env_connector
from app.mcp.server import mcp_connector_id_var

logger = logging.getLogger(__name__)

# Per-session locks for sequential message processing
_session_locks: dict[str, asyncio.Lock] = {}
_MAX_PENDING = 5


def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


async def handle_send_message(message: str, ctx=None) -> str:
    """
    MCP tool handler: send a message to the agent and return the response.

    This is registered on each per-connector FastMCP server instance.

    IMPORTANT: Any unhandled exception here kills the MCP session, causing all
    subsequent requests to return 400. Always return an error string instead.
    """
    try:
        return await _handle_send_message_inner(message)
    except Exception as e:
        logger.exception(f"Unhandled error in MCP send_message tool: {e}")
        return f"Error: {str(e)}"


async def _handle_send_message_inner(message: str) -> str:
    connector_id_str = mcp_connector_id_var.get(None)
    if not connector_id_str:
        return "Error: No connector context available"

    connector_id = uuid.UUID(connector_id_str)

    with DBSession(engine) as db:
        # Load connector
        connector = db.get(MCPConnector, connector_id)
        if not connector or not connector.is_active:
            return "Error: Connector not found or inactive"

        # Load agent
        agent = db.get(Agent, connector.agent_id)
        if not agent or not agent.active_environment_id:
            return "Error: Agent not found or has no active environment"

        # Load environment
        environment = db.get(AgentEnvironment, agent.active_environment_id)
        if not environment:
            return "Error: Agent environment not found"

        # Get or create platform session for this MCP session
        # Use a deterministic mapping: connector_id is used to find/create sessions
        # For now, use one session per connector (can be enhanced with MCP session ID)
        platform_session = db.exec(
            select(Session).where(
                Session.mcp_connector_id == connector_id,
                Session.status == "active",
            )
        ).first()

        if not platform_session:
            session_data = SessionCreate(
                agent_id=connector.agent_id,
                mode=connector.mode,
            )
            platform_session = SessionService.create_session(
                db_session=db,
                user_id=connector.owner_id,
                data=session_data,
                integration_type="mcp",
            )
            if not platform_session:
                return "Error: Failed to create session"

            # Link to MCP connector
            platform_session.mcp_connector_id = connector_id
            db.add(platform_session)
            db.commit()
            db.refresh(platform_session)

        session_id = str(platform_session.id)
        connector_mode = connector.mode

        # Get external session ID for multi-turn (session_metadata may be None)
        session_meta = platform_session.session_metadata or {}
        external_session_id = session_meta.get("external_session_id")

        # Get environment connection info
        base_url = MessageService.get_environment_url(environment)
        auth_headers = MessageService.get_auth_headers(environment)

    # Acquire per-session lock for sequential processing
    lock = _get_session_lock(session_id)
    if lock.locked():
        return "Error: Another message is being processed. Please wait."

    async with lock:
        # Build request payload
        payload = {
            "message": message,
            "mode": connector_mode,
            "session_id": external_session_id,
            "backend_session_id": session_id,
        }

        # Stream the response from agent environment
        response_parts = []
        new_external_session_id = None

        try:
            async for event in agent_env_connector.stream_chat(base_url, auth_headers, payload):
                event_type = event.get("type", "")

                if event_type == "session_created":
                    new_external_session_id = event.get("session_id")

                elif event_type == "assistant":
                    content = event.get("content", "")
                    if content:
                        response_parts.append(content)

                elif event_type == "tool":
                    tool_name = event.get("tool_name", "unknown")
                    tool_content = event.get("content", "")
                    if tool_content:
                        response_parts.append(f"[Tool: {tool_name}] {tool_content}")

                elif event_type == "error":
                    error_content = event.get("content", "Unknown error")
                    return f"Error from agent: {error_content}"

                elif event_type == "done":
                    break

        except Exception as e:
            logger.error(f"Error streaming from agent environment: {e}")
            return f"Error: Failed to communicate with agent environment: {str(e)}"

        # Update external session ID if we got a new one
        if new_external_session_id:
            with DBSession(engine) as db:
                session_record = db.get(Session, uuid.UUID(session_id))
                if session_record:
                    metadata = dict(session_record.session_metadata or {})
                    metadata["external_session_id"] = new_external_session_id
                    session_record.session_metadata = metadata
                    session_record.updated_at = datetime.now(UTC)
                    db.add(session_record)
                    db.commit()

    full_response = "".join(response_parts)
    return full_response if full_response else "No response from agent"


def register_mcp_tools(server) -> None:
    """Register all MCP tools on the given FastMCP server instance."""

    @server.tool(
        name="send_message",
        description="Send a message to the AI agent and receive a response. The agent can use tools, write code, and perform tasks based on your message.",
    )
    async def send_message(message: str) -> str:
        return await handle_send_message(message)
