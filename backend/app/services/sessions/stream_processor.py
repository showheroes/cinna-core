"""
Unified session stream processor.

Provides a single streaming pipeline used by all message-processing paths:
UI (WebSocket), MCP (per-connector & App MCP), and A2A (SSE streaming).

Each path supplies a ``StreamEventHandler`` that customises event delivery
and error handling while the core lifecycle is shared:

    collect pending → inject context → mark sent → stream → finalize

The processor replaces duplicated logic that previously lived in:
- ``MessageService.process_pending_messages`` (UI path)
- ``message_streaming.stream_and_collect_response`` (MCP/App MCP path)
- ``A2ARequestHandler.handle_message_stream`` inline loop (A2A path)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Protocol, runtime_checkable
from uuid import UUID

from sqlmodel import Session as DbSession

from app.models import Agent, Session as ChatSession
from app.models.environments.environment import AgentEnvironment
from app.services.sessions.message_service import MessageService
from app.services.sessions.session_service import SessionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Per-session locks — shared singleton across all handler types
# ---------------------------------------------------------------------------
_session_locks: dict[str, asyncio.Lock] = {}
_MAX_SESSION_LOCKS = 1000


def get_session_lock(session_id: str) -> asyncio.Lock:
    """Return (or create) a per-session asyncio.Lock.

    Bounded: evicts unlocked entries when the dict exceeds
    ``_MAX_SESSION_LOCKS`` to prevent unbounded memory growth.
    """
    if session_id not in _session_locks:
        if len(_session_locks) >= _MAX_SESSION_LOCKS:
            to_remove = [
                sid for sid, lock in _session_locks.items()
                if not lock.locked()
            ]
            for sid in to_remove:
                del _session_locks[sid]
        _session_locks[session_id] = asyncio.Lock()
    return _session_locks[session_id]


# ---------------------------------------------------------------------------
# Event handler protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class StreamEventHandler(Protocol):
    """Strategy interface for path-specific event delivery.

    Each integration path (UI, MCP, A2A) implements this to customise
    how streaming events are forwarded to the caller.
    """

    async def on_stream_starting(self, pending_count: int) -> None:
        """Called after messages are collected, before streaming begins."""
        ...

    async def on_event(self, event: dict) -> None:
        """Called for each streaming event from the agent environment."""
        ...

    async def on_error(self, error: Exception) -> None:
        """Called when a fatal error occurs during streaming."""
        ...

    async def on_complete(self, response_text: str) -> None:
        """Called after streaming finishes successfully."""
        ...


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

class SessionStreamProcessor:
    """Unified pipeline: collect → mark sent → stream → finalize.

    Usage::

        processor = SessionStreamProcessor(
            session_id=session_id,
            get_fresh_db_session=get_db,
            event_handler=MyEventHandler(...),
        )
        response_text = await processor.process()
    """

    def __init__(
        self,
        *,
        session_id: UUID,
        get_fresh_db_session: Callable[[], DbSession],
        event_handler: StreamEventHandler,
        use_session_lock: bool = False,
        ensure_env_ready: bool = True,
        env_timeout_seconds: int = 120,
        inject_recovery_context: bool = False,
        inject_webapp_context: bool = False,
        log_prefix: str = "[Stream]",
    ) -> None:
        self.session_id = session_id
        self.get_fresh_db_session = get_fresh_db_session
        self.event_handler = event_handler
        self.use_session_lock = use_session_lock
        self.ensure_env_ready = ensure_env_ready
        self.env_timeout_seconds = env_timeout_seconds
        self.inject_recovery_context = inject_recovery_context
        self.inject_webapp_context = inject_webapp_context
        self.log_prefix = log_prefix

        # Populated during processing
        self.environment: AgentEnvironment | None = None
        self.agent: Agent | None = None

    async def process(self) -> str:
        """Run the full streaming pipeline.

        Returns:
            The agent's collected response text (may be empty).

        Raises:
            EnvironmentNotReadyError: if environment cannot be activated.
            SessionLockBusyError: if per-session lock is already held.
        """
        # Phase 1: Ensure environment is ready
        if self.ensure_env_ready:
            self.environment, self.agent = await SessionService.ensure_environment_ready_for_streaming(
                session_id=self.session_id,
                get_fresh_db_session=self.get_fresh_db_session,
                timeout_seconds=self.env_timeout_seconds,
            )

        # Phase 2: Optionally acquire per-session lock
        if self.use_session_lock:
            return await self._process_with_lock()
        else:
            return await self._process_inner()

    async def _process_with_lock(self) -> str:
        """Acquire per-session lock and run inner pipeline."""
        lock = get_session_lock(str(self.session_id))
        if lock.locked():
            raise SessionLockBusyError(self.session_id)

        async with lock:
            return await self._process_inner()

    async def _process_inner(self) -> str:
        """Core pipeline: collect → context → mark sent → stream → return."""
        # Step 1: Collect pending messages
        with self.get_fresh_db_session() as db:
            concatenated_content, pending_messages = MessageService.collect_pending_messages(
                db, self.session_id
            )
            if not concatenated_content or not pending_messages:
                logger.info(
                    "%s No pending messages for session %s",
                    self.log_prefix, self.session_id,
                )
                return ""

            # Read session metadata for streaming
            chat_session = db.get(ChatSession, self.session_id)
            session_mode = (chat_session.mode or "conversation") if chat_session else "conversation"
            external_session_id = (
                (chat_session.session_metadata or {}).get("external_session_id")
                if chat_session else None
            )

            message_ids = [msg.id for msg in pending_messages]

            # Step 2: Inject recovery context (UI path only)
            if self.inject_recovery_context and chat_session:
                if chat_session.session_metadata.get("recovery_pending"):
                    recovery_context = MessageService.build_recovery_context(db, self.session_id)
                    if recovery_context:
                        concatenated_content = f"{recovery_context}\n\n{concatenated_content}"
                    # Clear recovery_pending flag
                    chat_session.session_metadata.pop("recovery_pending", None)
                    from sqlalchemy.orm.attributes import flag_modified
                    flag_modified(chat_session, "session_metadata")
                    db.add(chat_session)
                    db.commit()
                    db.refresh(chat_session)

            # Step 3: Inject one-time webapp context (UI path only)
            include_extra_instructions: str | None = None
            extra_instructions_prepend: str | None = None
            if self.inject_webapp_context and chat_session:
                has_page_context = any(
                    (msg.message_metadata or {}).get("page_context")
                    for msg in pending_messages
                )
                if has_page_context:
                    should_inject = SessionService.activate_webapp_context(db, self.session_id)
                    if should_inject:
                        extra_instructions_prepend = (
                            "This session is connected to a webapp that the user is viewing.\n"
                            "- The user's current page state is included as <page_context> or "
                            "<context_update> blocks in their messages.\n"
                            "- You can interact with the webapp UI by embedding <webapp_action> "
                            "tags in your responses (see webapp actions documentation for syntax and available actions)."
                        )
                        if session_mode == "conversation":
                            include_extra_instructions = "/app/workspace/webapp/WEB_APP_ACTIONS.md"
                        logger.info(
                            "%s Including one-time webapp context for session %s",
                            self.log_prefix, self.session_id,
                        )

            # Resolve environment if not already done (non-env-ready paths)
            if self.environment is None:
                environment = db.get(AgentEnvironment, chat_session.environment_id) if chat_session else None
                if not environment:
                    logger.error("%s Environment not found for session %s", self.log_prefix, self.session_id)
                    return ""
                self.environment = environment

        # Step 4: Notify handler that streaming is about to start
        await self.event_handler.on_stream_starting(len(pending_messages))

        # Step 5: Mark messages as sent
        with self.get_fresh_db_session() as db:
            MessageService.mark_messages_as_sent(db, message_ids)

        logger.info(
            "%s Streaming %d pending message(s) for session %s",
            self.log_prefix, len(pending_messages), self.session_id,
        )

        # Step 6: Stream and forward events
        response_parts: list[str] = []
        try:
            async for event in MessageService.stream_message_with_events(
                session_id=self.session_id,
                environment_id=self.environment.id,
                user_message_content=concatenated_content,
                session_mode=session_mode,
                external_session_id=external_session_id,
                get_fresh_db_session=self.get_fresh_db_session,
                include_extra_instructions=include_extra_instructions,
                extra_instructions_prepend=extra_instructions_prepend,
            ):
                event_type = event.get("type", "")

                # Accumulate assistant response text
                if event_type == "assistant":
                    content = event.get("content", "")
                    if content:
                        response_parts.append(content)

                # Forward every event to the handler
                await self.event_handler.on_event(event)

                # Early exit on error events
                if event_type == "error":
                    break

        except Exception as e:
            logger.error(
                "%s Error streaming for session %s: %s",
                self.log_prefix, self.session_id, e,
                exc_info=True,
            )
            await self.event_handler.on_error(e)
            raise

        full_response = "\n\n".join(response_parts)

        # Step 7: Notify handler of completion
        await self.event_handler.on_complete(full_response)

        logger.info(
            "%s Response complete | session=%s | parts=%d | length=%d",
            self.log_prefix, self.session_id, len(response_parts), len(full_response),
        )
        return full_response


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SessionLockBusyError(Exception):
    """Raised when a per-session lock is already held."""

    def __init__(self, session_id: UUID) -> None:
        self.session_id = session_id
        super().__init__(f"Another message is being processed for session {session_id}. Please wait.")


class EnvironmentNotReadyError(Exception):
    """Raised when the environment cannot be activated in time."""

    def __init__(self, session_id: UUID, reason: str) -> None:
        self.session_id = session_id
        super().__init__(f"Environment not ready for session {session_id}: {reason}")
