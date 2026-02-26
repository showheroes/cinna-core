"""
MCP Request Handler - handles MCP tool requests.

This module bridges MCP protocol requests to internal services,
handling message send operations through the service layer.

All data access is done through the service layer (SessionService, MessageService)
rather than direct database queries (following the same pattern as A2ARequestHandler).
"""
import asyncio
import logging
from typing import Callable
from uuid import UUID

from sqlmodel import Session as DbSession

from app.models import Agent
from app.models.environment import AgentEnvironment
from app.models.mcp_connector import MCPConnector
from app.services.session_service import SessionService
from app.services.message_service import MessageService
from app.utils import create_task_with_error_logging

logger = logging.getLogger(__name__)

# Per-session locks for sequential message processing
_session_locks: dict[str, asyncio.Lock] = {}


def _get_session_lock(session_id: str) -> asyncio.Lock:
    if session_id not in _session_locks:
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


class MCPRequestHandler:
    """
    Handles MCP tool requests by delegating to internal services.

    Follows the same isolation pattern as A2ARequestHandler:
    - Receives pre-resolved entities (agent, environment, connector)
    - All data access through SessionService and MessageService
    - No direct database queries in this handler
    """

    def __init__(
        self,
        agent: Agent,
        environment: AgentEnvironment,
        connector: MCPConnector,
        get_db_session: Callable[[], DbSession],
    ):
        """
        Initialize the request handler.

        Args:
            agent: The Agent model instance
            environment: The agent's active environment
            connector: The MCP connector instance
            get_db_session: Callable that returns a fresh database session
        """
        self.agent = agent
        self.environment = environment
        self.connector = connector
        self.get_db_session = get_db_session

    async def handle_send_message(
        self,
        message: str,
        mcp_session_id: str | None = None,
    ) -> str:
        """
        Handle send_message tool call.

        Uses the same SessionService/MessageService pipeline as A2A integration:
        1. Get/create platform session for this MCP connector
        2. Create user message
        3. Ensure environment is ready for streaming
        4. Stream response from agent environment
        5. Return response text

        Args:
            message: User message content
            mcp_session_id: Optional MCP transport session ID (from client header)

        Returns:
            Agent response text or error string
        """
        # Phase 1: Get/create session and create user message
        with self.get_db_session() as db:
            try:
                platform_session, is_new_session = SessionService.get_or_create_mcp_session(
                    db_session=db,
                    connector=self.connector,
                    mcp_session_id=mcp_session_id,
                )
            except ValueError as e:
                return f"Error: {e}"

            session_id = platform_session.id
            external_session_id = (platform_session.session_metadata or {}).get(
                "external_session_id"
            )
            logger.info(
                "[MCP] Using platform_session=%s | is_new=%s | external_session_id=%s",
                session_id, is_new_session, external_session_id or "(none)",
            )

            # Create user message (same as email/A2A pipeline)
            MessageService.create_message(
                session=db,
                session_id=session_id,
                role="user",
                content=message,
            )

        # Trigger title generation for new sessions (background task)
        if is_new_session:
            create_task_with_error_logging(
                SessionService.auto_generate_session_title(
                    session_id=session_id,
                    first_message_content=message,
                    get_fresh_db_session=self.get_db_session,
                ),
                task_name=f"auto_generate_title_session_{session_id}",
            )

        # Phase 2: Ensure environment is ready for streaming
        # (activates suspended environments, same as A2A handler)
        try:
            environment, _agent = await SessionService.ensure_environment_ready_for_streaming(
                session_id=session_id,
                get_fresh_db_session=self.get_db_session,
                timeout_seconds=120,
            )
        except (ValueError, RuntimeError) as e:
            logger.error(f"[MCP] Environment not ready for streaming: {e}")
            return f"Error: Environment not ready: {str(e)}"

        # Phase 3: Stream response with per-session locking
        session_id_str = str(session_id)
        lock = _get_session_lock(session_id_str)
        if lock.locked():
            return "Error: Another message is being processed. Please wait."

        response_parts: list[str] = []
        async with lock:
            try:
                async for event in MessageService.stream_message_with_events(
                    session_id=session_id,
                    environment_id=environment.id,
                    user_message_content=message,
                    session_mode=self.connector.mode,
                    external_session_id=external_session_id,
                    get_fresh_db_session=self.get_db_session,
                ):
                    event_type = event.get("type", "")

                    if event_type == "assistant":
                        content = event.get("content", "")
                        if content:
                            response_parts.append(content)

                    elif event_type == "error":
                        error_content = event.get("content", "Unknown error")
                        logger.error("[MCP] Error event from agent: %s", error_content)
                        return f"Error from agent: {error_content}"

            except Exception as e:
                logger.error(f"[MCP] Error streaming from agent environment: {e}")
                return f"Error: Failed to communicate with agent environment: {str(e)}"

        full_response = "\n\n".join(response_parts)
        logger.info(
            "[MCP] Response complete | session=%s | response_parts=%d | length=%d",
            session_id, len(response_parts), len(full_response),
        )
        return full_response if full_response else "No response from agent"
