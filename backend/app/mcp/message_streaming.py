"""
Shared MCP message streaming utilities.

Provides the ``stream_and_collect_response`` entry point used by both the
per-connector MCPRequestHandler and the App MCP AppMCPRequestHandler.

Internally delegates to ``SessionStreamProcessor`` with an ``MCPEventHandler``
so that the streaming lifecycle (collect pending → mark sent → stream →
finalize) is shared with the UI and A2A paths.
"""

import json
import logging
import time
from typing import Callable
from uuid import UUID

from sqlmodel import Session as DbSession

from app.services.sessions.stream_processor import (
    SessionStreamProcessor,
    SessionLockBusyError,
)
from app.services.sessions.stream_event_handlers import MCPEventHandler

logger = logging.getLogger(__name__)


# Re-export for backward compatibility — callers that imported these from here
from app.services.sessions.stream_processor import get_session_lock  # noqa: F401


async def send_mcp_progress(
    mcp_ctx,
    event: dict,
    progress: int,
    last_info_time: float,
) -> tuple[int, float]:
    """Send MCP progress and log notifications for a streaming event.

    Standalone helper kept for backward compatibility and direct testing.
    The ``MCPEventHandler`` uses equivalent logic internally.

    Returns updated ``(progress, last_info_time)`` tuple.
    Failures are silently caught — notifications must never crash the tool.
    """
    if mcp_ctx is None:
        return progress, last_info_time

    event_type = event.get("type", "")
    now = time.monotonic()

    try:
        if event_type == "assistant" and progress < 100:
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, "Processing...")
        elif event_type == "tool" and progress < 100:
            tool_name = event.get("name", "tool")
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, f"Using tool: {tool_name}")
        elif event_type == "thinking" and progress < 100:
            progress = min(progress + 10, 100)
            await mcp_ctx.report_progress(progress, 100, "Thinking...")
    except Exception:
        logger.debug("[MCP] Failed to send progress notification (non-fatal)", exc_info=True)

    try:
        if event_type == "assistant":
            content = event.get("content", "")
            if content and (now - last_info_time) >= 0.5:
                await mcp_ctx.info(content)
                last_info_time = now
    except Exception:
        logger.debug("[MCP] Failed to send log notification (non-fatal)", exc_info=True)

    return progress, last_info_time


async def stream_and_collect_response(
    *,
    session_id: UUID,
    get_fresh_db_session: Callable[[], DbSession],
    mcp_ctx=None,
    timeout_seconds: int = 120,
    log_prefix: str = "[MCP]",
) -> str:
    """Ensure environment is ready, stream response, and return text or error JSON.

    This encapsulates Phases 2–3 of the MCP message pipeline:

    - Phase 2: ensure environment is ready for streaming (wakes suspended envs)
    - Phase 3: collect pending messages, mark as sent, stream, collect response

    The caller must have already created the user message in the DB
    (with default ``sent_to_agent_status="pending"``) before calling this.

    Args:
        session_id: Platform session UUID.
        get_fresh_db_session: Factory for new DB sessions.
        mcp_ctx: Optional MCP context for progress notifications.
        timeout_seconds: Max wait for environment readiness.
        log_prefix: Logging prefix ("[MCP]" or "[AppMCP]").

    Returns:
        The agent's response text (empty string if no response),
        or a JSON error string with ``error`` and ``context_id`` keys.
    """
    result_context_id = str(session_id)

    handler = MCPEventHandler(mcp_ctx=mcp_ctx, log_prefix=log_prefix)

    processor = SessionStreamProcessor(
        session_id=session_id,
        get_fresh_db_session=get_fresh_db_session,
        event_handler=handler,
        use_session_lock=True,
        ensure_env_ready=True,
        env_timeout_seconds=timeout_seconds,
        inject_recovery_context=False,
        inject_webapp_context=False,
        log_prefix=log_prefix,
    )

    try:
        response_text = await processor.process()
    except SessionLockBusyError:
        return json.dumps({
            "error": "Another message is being processed. Please wait.",
            "context_id": result_context_id,
        })
    except (ValueError, RuntimeError) as e:
        logger.error("%s Environment not ready for streaming: %s", log_prefix, e)
        return json.dumps({
            "error": f"Environment not ready: {e}",
            "context_id": result_context_id,
        })
    except Exception as e:
        logger.error("%s Error streaming from agent environment: %s", log_prefix, e)
        return json.dumps({
            "error": f"Failed to communicate with agent environment: {e}",
            "context_id": result_context_id,
        })

    # If the handler captured an error event from the agent, return it
    if handler.error_content:
        return json.dumps({
            "error": f"Error from agent: {handler.error_content}",
            "context_id": result_context_id,
        })

    return response_text if response_text else ""
