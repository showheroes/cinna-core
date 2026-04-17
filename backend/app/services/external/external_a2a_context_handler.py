"""
ExternalA2AContextHandler — A2ARequestHandler subclass for the external surface.

Inherits all core A2A plumbing from A2ARequestHandler and adds the context-based
methods that were previously bolted onto the core handler as overloads.  Moving
them here keeps the core A2A handler free of external-only concerns.

This module also defines TargetContext, the pre-resolved target descriptor used
by ExternalA2ARequestHandler to pass ownership and integration hints into the
handler without re-deriving them from agent_id.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional
from uuid import UUID

from sqlmodel import Session as DbSession

from app.models import Session as ChatSession
from app.services.a2a.a2a_request_handler import A2ARequestHandler
from app.services.a2a.a2a_event_mapper import A2AEventMapper
from app.services.external.errors import (
    IdentityBindingRevokedError,
    InvalidExternalParamsError,
    NoActiveEnvironmentError,
    TargetNotAccessibleError,
    TaskScopeViolationError,
)
from app.services.sessions.session_service import SessionService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TargetContext — pre-resolved target descriptor
# ---------------------------------------------------------------------------


@dataclass
class TargetContext:
    """Pre-resolved target context for external A2A dispatch.

    Used by ExternalA2ARequestHandler to pass ownership and integration
    hints into ExternalA2AContextHandler without re-deriving them from
    agent_id alone.
    """

    agent: Any  # Agent
    environment: Any  # AgentEnvironment
    integration_type: str  # "external", "app_mcp", "identity_mcp"
    session_owner_id: UUID  # user_id for the session
    caller_id: Optional[UUID] = None  # for app_mcp: the calling user's ID
    identity_caller_id: Optional[UUID] = None  # for identity_mcp
    match_method: Optional[str] = None  # for app_mcp: "external_direct"
    route_id: Optional[UUID] = None  # for app_mcp: the AppAgentRoute.id
    route_source: Optional[str] = None  # for app_mcp: "admin" or "user"
    # Identity-specific fields (only set when integration_type == "identity_mcp")
    identity_binding_id: Optional[UUID] = None
    identity_binding_assignment_id: Optional[UUID] = None
    identity_stage2_match_method: Optional[str] = None  # "only_one" | "pattern" | "ai"
    identity_owner_name: Optional[str] = None
    identity_caller_name: Optional[str] = None
    # Client attribution — populated from JWT claims when the request originates
    # from a desktop/mobile native client.  Written into session_metadata by
    # _stamp_session_context for all integration types.
    client_kind: Optional[str] = None        # e.g. "desktop", "mobile"
    external_client_id: Optional[str] = None  # DesktopOAuthClient.id (str UUID)


# ---------------------------------------------------------------------------
# ExternalA2AContextHandler
# ---------------------------------------------------------------------------


class ExternalA2AContextHandler(A2ARequestHandler):
    """A2ARequestHandler subclass that adds context-scoped dispatch methods.

    The external A2A surface needs caller-scope enforcement (so one caller cannot
    access another caller's sessions) and session stamping (writing caller_id,
    integration metadata, and client attribution into new sessions).  Those
    concerns live here, not in the core A2ARequestHandler.
    """

    # ------------------------------------------------------------------
    # Session validation helpers
    # ------------------------------------------------------------------

    def _parse_and_validate_session_id_with_context(
        self,
        task_id: str | None,
        context: TargetContext,
    ) -> UUID | None:
        """Parse task_id and enforce caller-scope per context.integration_type.

        - "external":     session.user_id must equal context.session_owner_id
        - "app_mcp":      session.caller_id must equal context.caller_id
        - "identity_mcp": session.identity_caller_id must equal context.identity_caller_id

        Returns None when task_id is falsy or not a UUID (new session will be
        created).

        Raises:
            TaskScopeViolationError: Session exists but belongs to a different caller.
            IdentityBindingRevokedError: Identity session's binding/assignment
                was disabled mid-conversation.
        """
        if not task_id:
            return None
        try:
            session_id = UUID(task_id)
        except ValueError:
            return None

        with self.get_db_session() as db:
            session = SessionService.get_session(db, session_id)
            if session is None:
                return None

            if context.integration_type == "app_mcp":
                if session.caller_id != context.caller_id:
                    raise TaskScopeViolationError()
            elif context.integration_type == "identity_mcp":
                if session.identity_caller_id != context.identity_caller_id:
                    raise TaskScopeViolationError()
                if session.user_id != context.session_owner_id:
                    raise TaskScopeViolationError()
                # Re-check binding validity so mid-conversation revocations surface.
                from app.services.identity.identity_service import IdentityService
                validity_error = IdentityService.check_session_validity(db, session)
                if validity_error:
                    raise IdentityBindingRevokedError(validity_error)
            else:  # "external" and any other owner-scoped type
                if session.user_id != context.session_owner_id:
                    raise TaskScopeViolationError()
        return session_id

    def _stamp_session_context(
        self,
        session_id: UUID,
        context: TargetContext,
    ) -> None:
        """Set caller_id / identity_caller_id + session_metadata for a new
        context-scoped session.

        Also writes client attribution claims (client_kind / external_client_id)
        into session_metadata for all integration types when present in the context.
        """
        with self.get_db_session() as db:
            session = SessionService.get_session(db, session_id)
            if session is None:
                return

            if context.integration_type == "external":
                # Owner-only sessions: no caller_id / identity stamping needed.
                # Only write client attribution if present.
                if context.client_kind is not None:
                    meta: dict[str, Any] = dict(session.session_metadata or {})
                    meta["client_kind"] = context.client_kind
                    if context.external_client_id is not None:
                        meta["external_client_id"] = context.external_client_id
                    session.session_metadata = meta
                    db.add(session)
                    db.commit()
                return

            if context.integration_type == "app_mcp":
                session.caller_id = context.caller_id
                meta: dict[str, Any] = dict(session.session_metadata or {})
                if context.route_id is not None:
                    meta["app_mcp_route_id"] = str(context.route_id)
                if context.route_source is not None:
                    meta["app_mcp_route_type"] = context.route_source
                if context.match_method is not None:
                    meta["app_mcp_match_method"] = context.match_method
                meta.setdefault("app_mcp_agent_name", context.agent.name)
                if context.client_kind is not None:
                    meta["client_kind"] = context.client_kind
                    if context.external_client_id is not None:
                        meta["external_client_id"] = context.external_client_id
                session.session_metadata = meta
            elif context.integration_type == "identity_mcp":
                session.identity_caller_id = context.identity_caller_id
                if context.identity_binding_id is not None:
                    session.identity_binding_id = context.identity_binding_id
                if context.identity_binding_assignment_id is not None:
                    session.identity_binding_assignment_id = (
                        context.identity_binding_assignment_id
                    )
                meta: dict[str, Any] = dict(session.session_metadata or {})
                if context.identity_owner_name is not None:
                    meta["identity_owner_name"] = context.identity_owner_name
                if context.identity_caller_name is not None:
                    meta["identity_caller_name"] = context.identity_caller_name
                if context.identity_stage2_match_method is not None:
                    meta["identity_match_method"] = (
                        context.identity_stage2_match_method
                    )
                if context.match_method is not None:
                    meta["app_mcp_match_method"] = context.match_method
                meta.setdefault("app_mcp_route_type", "identity")
                if context.client_kind is not None:
                    meta["client_kind"] = context.client_kind
                    if context.external_client_id is not None:
                        meta["external_client_id"] = context.external_client_id
                session.session_metadata = meta

            db.add(session)
            db.commit()

    # ------------------------------------------------------------------
    # Context-based dispatch methods
    # ------------------------------------------------------------------

    async def handle_message_send_with_context(
        self,
        params: dict[str, Any],
        context: TargetContext,
    ) -> Any:
        """Handle message/send with a pre-resolved TargetContext."""
        from a2a.types import Task, TaskState, TaskStatus, Message, Part, TextPart
        from datetime import UTC, datetime

        message_data = params.get("message", {})
        config = params.get("configuration", {})

        content = self._extract_text_from_parts(message_data.get("parts", []))

        task_id = message_data.get("taskId") or message_data.get("task_id")
        session_id = self._parse_and_validate_session_id_with_context(task_id, context)
        is_new_session = session_id is None

        if session_id is not None:
            try:
                await SessionService.ensure_environment_ready_for_streaming(
                    session_id=session_id,
                    get_fresh_db_session=self.get_db_session,
                    timeout_seconds=120,
                )
            except (ValueError, RuntimeError) as e:
                raise NoActiveEnvironmentError(f"Environment error: {str(e)}")

        result = await SessionService.send_session_message(
            session_id=session_id,
            user_id=context.session_owner_id,
            content=content,
            file_ids=None,
            answers_to_message_id=None,
            get_fresh_db_session=self.get_db_session,
            backend_base_url=self.backend_base_url,
            agent_id=context.agent.id if session_id is None else None,
            integration_type=context.integration_type if session_id is None else None,
        )

        if result.get("action") == "error":
            raise ValueError(result.get("message", "Unknown error"))

        if result.get("action") == "command_executed":
            cmd_session_id = result.get("session_id", session_id)
            return Task(
                id=str(cmd_session_id),
                contextId=str(cmd_session_id),
                status=TaskStatus(
                    state=TaskState.completed,
                    timestamp=datetime.now(UTC).isoformat() + "Z",
                    message=Message(
                        messageId="cmd_response",
                        role="agent",
                        parts=[Part(root=TextPart(text=result.get("message", "")))],
                    ),
                ),
            )

        session_id = result.get("session_id", session_id)

        if is_new_session and session_id is not None:
            self._stamp_session_context(session_id, context)

        if result.get("action") in ["pending", "message_created"]:
            try:
                await SessionService.ensure_environment_ready_for_streaming(
                    session_id=session_id,
                    get_fresh_db_session=self.get_db_session,
                    timeout_seconds=120,
                )
                result = await SessionService.initiate_stream(
                    session_id=session_id,
                    get_fresh_db_session=self.get_db_session,
                )
            except (ValueError, RuntimeError) as e:
                raise NoActiveEnvironmentError(f"Environment error: {str(e)}")

        if result.get("action") == "streaming":
            import asyncio
            from app.services.a2a.a2a_task_store import DatabaseTaskStore
            from a2a.types import TaskState

            max_wait = 300
            poll_interval = 1
            elapsed = 0
            while elapsed < max_wait:
                task = self.task_store.get(str(session_id))
                if task and task.status.state in [
                    TaskState.completed,
                    TaskState.failed,
                    TaskState.canceled,
                    TaskState.input_required,
                ]:
                    return task
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

        history_length = config.get("historyLength", config.get("history_length", 10))
        task = self.task_store.get_task_with_limited_history(str(session_id), history_length)
        if not task:
            from a2a.types import Task, TaskState, TaskStatus
            from datetime import UTC, datetime
            task = Task(
                id=str(session_id),
                contextId=str(session_id),
                status=TaskStatus(
                    state=TaskState.completed,
                    timestamp=datetime.now(UTC).isoformat() + "Z",
                ),
            )
        return task

    async def handle_message_stream_with_context(
        self,
        params: dict[str, Any],
        request_id: Any,
        context: TargetContext,
    ) -> AsyncIterator[str]:
        """Handle message/stream with a pre-resolved TargetContext."""
        from app.services.sessions.stream_processor import SessionStreamProcessor
        from app.services.sessions.stream_event_handlers import A2AStreamEventHandler
        from a2a.types import TaskState

        message_data = params.get("message", {})
        content = self._extract_text_from_parts(message_data.get("parts", []))

        task_id = message_data.get("taskId") or message_data.get("task_id")
        try:
            session_id = self._parse_and_validate_session_id_with_context(task_id, context)
        except (TaskScopeViolationError, IdentityBindingRevokedError) as e:
            yield self._format_sse_error(request_id, e.jsonrpc_code, e.message)
            return
        is_new_session = session_id is None

        result = await SessionService.send_session_message(
            session_id=session_id,
            user_id=context.session_owner_id,
            content=content,
            file_ids=None,
            answers_to_message_id=None,
            get_fresh_db_session=self.get_db_session,
            initiate_streaming=False,
            backend_base_url=self.backend_base_url,
            agent_id=context.agent.id if session_id is None else None,
            integration_type=context.integration_type if session_id is None else None,
        )

        if result["action"] == "error":
            yield self._format_sse_error(request_id, -32001, result["message"])
            return

        if result["action"] == "command_executed":
            cmd_session_id = result.get("session_id", session_id)
            task_id_str = str(cmd_session_id)
            completed_event = A2AEventMapper._create_status_update(
                task_id=task_id_str,
                context_id=task_id_str,
                state=TaskState.completed,
                final=True,
                message=result.get("message", ""),
            )
            yield self._format_sse_event(request_id, completed_event)
            return

        session_id = result.get("session_id", session_id)

        if is_new_session and session_id is not None:
            self._stamp_session_context(session_id, context)

        task_id_str = str(session_id)
        context_id_str = str(session_id)

        initial_event = A2AEventMapper._create_status_update(
            task_id=task_id_str,
            context_id=context_id_str,
            state=TaskState.working,
            final=False,
        )
        yield self._format_sse_event(request_id, initial_event)

        env_status = context.environment.status
        if env_status in ["suspended", "activating", "starting"]:
            activation_event = A2AEventMapper._create_status_update(
                task_id=task_id_str,
                context_id=context_id_str,
                state=TaskState.working,
                final=False,
                message="Starting up the agent environment, this may take a moment...",
            )
            yield self._format_sse_event(request_id, activation_event)

        handler = A2AStreamEventHandler(
            task_id=task_id_str,
            context_id=context_id_str,
            request_id=request_id,
            format_sse_event=self._format_sse_event,
        )

        processor = SessionStreamProcessor(
            session_id=session_id,
            get_fresh_db_session=self.get_db_session,
            event_handler=handler,
            use_session_lock=False,
            ensure_env_ready=True,
            env_timeout_seconds=120,
            log_prefix="[ExternalA2A]",
        )

        try:
            await processor.process()
        except (ValueError, RuntimeError) as e:
            error_event = A2AEventMapper._create_status_update(
                task_id=task_id_str,
                context_id=context_id_str,
                state=TaskState.failed,
                final=True,
                message=f"Environment error: {str(e)}",
            )
            yield self._format_sse_event(request_id, error_event)
            return
        except Exception as e:
            logger.error(f"Error streaming external A2A message: {e}")
            error_event = A2AEventMapper._create_status_update(
                task_id=task_id_str,
                context_id=context_id_str,
                state=TaskState.failed,
                final=True,
                message=f"Error: {str(e)}",
            )
            yield self._format_sse_event(request_id, error_event)
            return

        for sse_event in handler.events:
            yield sse_event

    async def handle_tasks_get_with_context(
        self,
        params: dict[str, Any],
        context: TargetContext,
    ) -> Optional[Any]:
        """Handle tasks/get with a pre-resolved TargetContext."""
        task_id = params.get("id")
        if not task_id:
            return None

        try:
            session_uuid = UUID(task_id)
        except ValueError:
            return None

        with self.get_db_session() as db:
            session = SessionService.get_session(db, session_uuid)
            if session is None:
                return None
            if not self._session_matches_context(session, context):
                raise TaskScopeViolationError()

        history_length = params.get("historyLength", params.get("history_length", 10))
        return self.task_store.get_task_with_limited_history(task_id, history_length)

    async def handle_tasks_list_with_context(
        self,
        params: dict[str, Any],
        context: TargetContext,
    ) -> list[Any]:
        """Handle tasks/list with a pre-resolved TargetContext."""
        limit = min(params.get("limit", 20), 100)
        offset = params.get("offset", 0)

        tasks: list[Any] = []

        with self.get_db_session() as db:
            sessions = SessionService.list_environment_sessions(
                db_session=db,
                environment_id=context.environment.id,
                limit=limit,
                offset=offset,
            )
            for session in sessions:
                if not self._session_matches_context(session, context):
                    continue
                task = self.task_store.get_task_with_limited_history(str(session.id), 0)
                if task:
                    tasks.append(task)

        return tasks

    async def handle_tasks_cancel_with_context(
        self,
        params: dict[str, Any],
        context: TargetContext,
    ) -> dict:
        """Handle tasks/cancel with a pre-resolved TargetContext."""
        from app.services.sessions.active_streaming_manager import active_streaming_manager

        task_id = params.get("id")
        if not task_id:
            raise InvalidExternalParamsError("Task ID is required")

        try:
            session_id = UUID(task_id)
        except (ValueError, TypeError):
            raise InvalidExternalParamsError("Task ID must be a UUID")

        with self.get_db_session() as db:
            session = SessionService.get_session(db, session_id)
            if not session:
                raise TargetNotAccessibleError("Task not found")
            if session.environment_id != context.environment.id:
                raise TargetNotAccessibleError("Task does not belong to this agent")
            if not self._session_matches_context(session, context):
                raise TaskScopeViolationError()

        await active_streaming_manager.request_interrupt(session_id)
        return {}

    @staticmethod
    def _session_matches_context(
        session: ChatSession,
        context: TargetContext,
    ) -> bool:
        """Caller-scope check: compare session fields to context.

        - app_mcp:      session.caller_id == context.caller_id
        - identity_mcp: session.identity_caller_id == context.identity_caller_id
        - external:     session.user_id == context.session_owner_id
        """
        if context.integration_type == "app_mcp":
            return session.caller_id == context.caller_id
        if context.integration_type == "identity_mcp":
            return (
                session.identity_caller_id == context.identity_caller_id
                and session.user_id == context.session_owner_id
            )
        return session.user_id == context.session_owner_id
