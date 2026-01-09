from uuid import UUID
from datetime import datetime
import logging
import asyncio
from typing import Any
from sqlmodel import Session as DBSession, select
from sqlalchemy.orm.attributes import flag_modified
from app.models import Session, SessionCreate, SessionUpdate, Agent, AgentEnvironment
from app.core.db import engine

logger = logging.getLogger(__name__)


class SessionService:
    @staticmethod
    def create_session(
        db_session: DBSession, user_id: UUID, data: SessionCreate
    ) -> Session | None:
        """Create session using agent's active environment"""
        # Get agent to find active environment
        agent = db_session.get(Agent, data.agent_id)
        if not agent or not agent.active_environment_id:
            return None

        session = Session(
            environment_id=agent.active_environment_id,
            user_id=user_id,
            user_workspace_id=agent.user_workspace_id,
            title=data.title,
            mode=data.mode,
            agent_sdk=data.agent_sdk,
        )
        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    @staticmethod
    def get_session(db_session: DBSession, session_id: UUID) -> Session | None:
        """Get session by ID"""
        return db_session.get(Session, session_id)

    @staticmethod
    def update_session(
        db_session: DBSession, session_id: UUID, data: SessionUpdate
    ) -> Session | None:
        """Update session (title, status, mode)"""
        session = db_session.get(Session, session_id)
        if not session:
            return None

        update_dict = data.model_dump(exclude_unset=True)
        session.sqlmodel_update(update_dict)
        session.updated_at = datetime.utcnow()

        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    @staticmethod
    def update_session_status(
        db_session: DBSession, session_id: UUID, status: str
    ) -> Session | None:
        """
        Update session status.

        Valid statuses:
        - "active": Streaming is currently happening
        - "completed": All messages received successfully, nothing to process
        - "error": Server-side error occurred (SDK response failed, HTTP errors, etc.)
        - "paused": Not implemented yet
        """
        session = db_session.get(Session, session_id)
        if not session:
            return None

        session.status = status
        session.updated_at = datetime.utcnow()

        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    @staticmethod
    def switch_mode(db_session: DBSession, session_id: UUID, new_mode: str) -> Session | None:
        """Switch session mode (building <-> conversation)"""
        session = db_session.get(Session, session_id)
        if not session:
            return None

        session.mode = new_mode
        session.updated_at = datetime.utcnow()

        db_session.add(session)
        db_session.commit()
        db_session.refresh(session)
        return session

    @staticmethod
    def list_user_sessions(db_session: DBSession, user_id: UUID) -> list[Session]:
        """List all sessions for user"""
        statement = select(Session).where(Session.user_id == user_id)
        return list(db_session.exec(statement).all())

    @staticmethod
    def list_agent_sessions(db_session: DBSession, agent_id: UUID) -> list[Session]:
        """List all sessions for agent (across all environments)"""
        # Get all environments for this agent
        env_statement = select(AgentEnvironment).where(AgentEnvironment.agent_id == agent_id)
        environments = db_session.exec(env_statement).all()
        env_ids = [env.id for env in environments]

        if not env_ids:
            return []

        # Get all sessions for these environments
        statement = select(Session).where(Session.environment_id.in_(env_ids))
        return list(db_session.exec(statement).all())

    @staticmethod
    def delete_session(db_session: DBSession, session_id: UUID) -> bool:
        """Delete session"""
        session = db_session.get(Session, session_id)
        if not session:
            return False

        db_session.delete(session)
        db_session.commit()
        return True

    # External SDK session management methods

    @staticmethod
    def get_external_session_id(session: Session) -> str | None:
        """Get external SDK session ID from metadata"""
        return session.session_metadata.get("external_session_id")

    @staticmethod
    def set_external_session_id(
        db: DBSession,
        session: Session,
        external_session_id: str,
        sdk_type: str | None = None
    ) -> Session:
        """
        Set external SDK session ID in metadata.
        Called after first message to SDK to store the session ID for resumption.

        Args:
            db: Database session
            session: Session to update
            external_session_id: External SDK session ID
            sdk_type: SDK type (if None, uses session.agent_sdk)
        """
        session.session_metadata["external_session_id"] = external_session_id
        session.session_metadata["sdk_type"] = sdk_type or session.agent_sdk

        # Mark metadata as modified for SQLAlchemy
        flag_modified(session, "session_metadata")

        session.updated_at = datetime.utcnow()
        db.add(session)
        db.commit()
        db.refresh(session)

        return session

    @staticmethod
    def get_sdk_type(session: Session) -> str | None:
        """Get SDK type from metadata"""
        return session.session_metadata.get("sdk_type")

    @staticmethod
    def should_create_new_sdk_session(session: Session) -> bool:
        """
        Determine if we should create a new SDK session or resume existing.

        Returns True if:
        - No external session ID exists
        - Session mode was just switched (different SDK type)
        """
        return not session.session_metadata.get("external_session_id")

    @staticmethod
    def clear_external_session(db: DBSession, session: Session) -> Session:
        """
        Clear external session metadata.
        Used when switching modes or restarting a session.
        """
        session.session_metadata.pop("external_session_id", None)
        session.session_metadata.pop("sdk_type", None)
        session.session_metadata.pop("last_sdk_message_id", None)

        flag_modified(session, "session_metadata")

        session.updated_at = datetime.utcnow()
        db.add(session)
        db.commit()
        db.refresh(session)

        return session

    @staticmethod
    def update_session_mode(
        db: DBSession,
        session: Session,
        new_mode: str,
        clear_external_session: bool = False
    ) -> Session:
        """
        Update session mode.

        Args:
            db: Database session
            session: Session to update
            new_mode: New mode ("building" | "conversation")
            clear_external_session: If True, clear external session ID
                                    (useful when switching between SDKs)
        """
        old_mode = session.mode
        session.mode = new_mode
        session.updated_at = datetime.utcnow()

        # If switching modes and flag is set, clear external session
        if clear_external_session and old_mode != new_mode:
            session.session_metadata.pop("external_session_id", None)
            session.session_metadata.pop("sdk_type", None)
            session.session_metadata.pop("last_sdk_message_id", None)

            flag_modified(session, "session_metadata")

        db.add(session)
        db.commit()
        db.refresh(session)

        return session

    @staticmethod
    async def auto_generate_session_title(
        session_id: UUID,
        first_message_content: str,
        get_fresh_db_session: callable
    ) -> None:
        """
        Auto-generate session title from first message if no title exists.
        Runs asynchronously in the background.

        Args:
            session_id: Session UUID
            first_message_content: Content of the first message
            get_fresh_db_session: Callable that returns a fresh DB session (context manager)
        """
        try:
            from app.services.ai_functions_service import AIFunctionsService

            # Check if AIFunctionsService is available
            if AIFunctionsService.is_available():
                # Generate title using LLM
                title = await asyncio.to_thread(
                    AIFunctionsService.generate_session_title,
                    first_message_content
                )

                # Update session with generated title
                with get_fresh_db_session() as db:
                    SessionService.update_session(
                        db_session=db,
                        session_id=session_id,
                        data=SessionUpdate(title=title)
                    )
                logger.info(f"Generated session title asynchronously: {title}")
            else:
                # If no LLM available, set truncated message immediately
                fallback_title = first_message_content[:100]
                if len(first_message_content) > 100:
                    fallback_title += "..."

                with get_fresh_db_session() as db:
                    SessionService.update_session(
                        db_session=db,
                        session_id=session_id,
                        data=SessionUpdate(title=fallback_title)
                    )
                logger.info(f"Set fallback session title (no LLM): {fallback_title}")

        except Exception as e:
            logger.warning(f"Failed to generate session title asynchronously: {e}")
            # Fallback to truncated message if LLM fails
            fallback_title = first_message_content[:100]
            if len(first_message_content) > 100:
                fallback_title += "..."

            try:
                with get_fresh_db_session() as db:
                    SessionService.update_session(
                        db_session=db,
                        session_id=session_id,
                        data=SessionUpdate(title=fallback_title)
                    )
                logger.info(f"Set fallback session title after error: {fallback_title}")
            except Exception as fallback_error:
                logger.error(f"Failed to set fallback title: {fallback_error}", exc_info=True)

    # Event handlers for event bus integration
    # These handlers react to streaming events and update session status accordingly

    @staticmethod
    async def handle_stream_started(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_STARTED events and update session status.

        When streaming starts:
        - Set interaction_status to "running"
        - Set status to "active"

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")

            if not session_id:
                logger.error(f"Invalid STREAM_STARTED event: missing session_id: {meta}")
                return

            # Use fresh database session to avoid conflicts
            with DBSession(engine) as db:
                session = db.get(Session, UUID(session_id))
                if not session:
                    logger.warning(f"Session {session_id} not found for STREAM_STARTED event")
                    return

                session.interaction_status = "running"
                session.status = "active"
                session.updated_at = datetime.utcnow()

                db.add(session)
                db.commit()

                logger.info(f"Session {session_id} status updated to 'active' with interaction_status 'running' (STREAM_STARTED)")

        except Exception as e:
            logger.error(f"Error handling STREAM_STARTED event: {e}", exc_info=True)

    @staticmethod
    async def handle_stream_completed(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_COMPLETED events and update session status.

        When streaming completes:
        - Clear interaction_status (set to empty string)
        - Set status based on interruption:
          - If interrupted: "active" (user can continue)
          - If not interrupted: "completed"

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")
            was_interrupted = meta.get("was_interrupted", False)

            if not session_id:
                logger.error(f"Invalid STREAM_COMPLETED event: missing session_id: {meta}")
                return

            # Use fresh database session to avoid conflicts
            with DBSession(engine) as db:
                session = db.get(Session, UUID(session_id))
                if not session:
                    logger.warning(f"Session {session_id} not found for STREAM_COMPLETED event")
                    return

                session.interaction_status = ""
                session.status = "active" if was_interrupted else "completed"
                session.updated_at = datetime.utcnow()

                db.add(session)
                db.commit()

                status_msg = f"'active' (interrupted)" if was_interrupted else "'completed'"
                logger.info(f"Session {session_id} status updated to {status_msg} with interaction_status cleared (STREAM_COMPLETED)")

        except Exception as e:
            logger.error(f"Error handling STREAM_COMPLETED event: {e}", exc_info=True)

    @staticmethod
    async def handle_stream_error(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_ERROR events and update session status.

        When streaming encounters an error:
        - Clear interaction_status
        - Set status to "error"

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")
            error_type = meta.get("error_type", "Unknown")

            if not session_id:
                logger.error(f"Invalid STREAM_ERROR event: missing session_id: {meta}")
                return

            # Use fresh database session to avoid conflicts
            with DBSession(engine) as db:
                session = db.get(Session, UUID(session_id))
                if not session:
                    logger.warning(f"Session {session_id} not found for STREAM_ERROR event")
                    return

                session.interaction_status = ""
                session.status = "error"
                session.updated_at = datetime.utcnow()

                db.add(session)
                db.commit()

                logger.info(f"Session {session_id} status updated to 'error' (STREAM_ERROR: {error_type})")

        except Exception as e:
            logger.error(f"Error handling STREAM_ERROR event: {e}", exc_info=True)

    @staticmethod
    async def handle_stream_interrupted(event_data: dict[str, Any]) -> None:
        """
        React to STREAM_INTERRUPTED events and update session status.

        When streaming is interrupted:
        - Clear interaction_status
        - Set status to "active" (user can continue)

        Args:
            event_data: Full event dict with type, model_id, meta, user_id, timestamp
        """
        try:
            meta = event_data.get("meta", {})
            session_id = meta.get("session_id")

            if not session_id:
                logger.error(f"Invalid STREAM_INTERRUPTED event: missing session_id: {meta}")
                return

            # Use fresh database session to avoid conflicts
            with DBSession(engine) as db:
                session = db.get(Session, UUID(session_id))
                if not session:
                    logger.warning(f"Session {session_id} not found for STREAM_INTERRUPTED event")
                    return

                session.interaction_status = ""
                session.status = "active"
                session.updated_at = datetime.utcnow()

                db.add(session)
                db.commit()

                logger.info(f"Session {session_id} status updated to 'active' with interaction_status cleared (STREAM_INTERRUPTED)")

        except Exception as e:
            logger.error(f"Error handling STREAM_INTERRUPTED event: {e}", exc_info=True)
