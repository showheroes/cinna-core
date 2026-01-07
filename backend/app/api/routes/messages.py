import uuid
from typing import Any
import logging

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlmodel import Session as DBSession

from app.api.deps import CurrentUser, SessionDep
from app.core.db import engine
from app.models import (
    Session,
    AgentEnvironment,
    MessageCreate,
    MessagePublic,
    MessagesPublic,
)
from app.services.message_service import MessageService
from app.services.active_streaming_manager import active_streaming_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sessions", tags=["messages"])


@router.get("/{session_id}/messages", response_model=MessagesPublic)
def get_messages(
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    limit: int = 100,
    offset: int = 0,
) -> Any:
    """
    Get session messages.
    """
    # Verify session exists and user owns it
    chat_session = session.get(Session, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not current_user.is_superuser and (chat_session.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    messages = MessageService.get_session_messages(
        session=session, session_id=session_id, limit=limit, offset=offset
    )
    return MessagesPublic(data=messages, count=len(messages))


@router.post("/{session_id}/messages", response_model=MessagePublic)
def send_message(
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    message_in: MessageCreate,
) -> Any:
    """
    Send message to agent (stub - no actual agent communication yet).

    For Step 1: Just store user message, return mock agent response.
    """
    # Verify session exists and user owns it
    chat_session = session.get(Session, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not current_user.is_superuser and (chat_session.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    # Store user message
    MessageService.create_message(
        session=session,
        session_id=session_id,
        role="user",
        content=message_in.content,
        answers_to_message_id=message_in.answers_to_message_id,
    )

    # TODO: In future steps, actually send to agent and get real response
    # For now, create a mock agent response
    agent_response = MessageService.create_message(
        session=session,
        session_id=session_id,
        role="agent",
        content=f"[Mock response] I received your message: '{message_in.content[:50]}...' (Step 1 stub)",
        message_metadata={"mock": True, "step": 1},
    )

    return agent_response


@router.post("/{session_id}/messages/stream")
async def send_message_stream(
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
    message_in: MessageCreate,
    background_tasks: BackgroundTasks
) -> Any:
    """
    Send message to agent environment and stream response via WebSocket.

    This endpoint:
    1. Validates session ownership and environment
    2. Validates and uploads files (if attached)
    3. Creates user message with file associations
    4. Launches background task to process message
    5. Returns immediately with success status

    Streaming events are emitted via WebSocket to room: session_{session_id}_stream
    Frontend should subscribe to this room before calling this endpoint.
    """
    # Verify session exists and user owns it
    chat_session = session.get(Session, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not current_user.is_superuser and (chat_session.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    # Get environment for file upload
    environment = session.get(AgentEnvironment, chat_session.environment_id)
    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Validate environment is running
    if environment.status != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Environment is not running (status: {environment.status})"
        )

    # Handle file attachments if present
    has_files = bool(message_in.file_ids)

    if has_files:
        # Validate files
        from app.models.file_upload import FileUpload
        from app.services.file_service import FileService
        from sqlmodel import select

        statement = select(FileUpload).where(FileUpload.id.in_(message_in.file_ids))
        files = session.exec(statement).all()

        # Check all files found
        if len(files) != len(message_in.file_ids):
            raise HTTPException(status_code=400, detail="Some files not found")

        # Check ownership and status
        for file in files:
            if file.user_id != current_user.id:
                raise HTTPException(
                    status_code=403,
                    detail=f"Not authorized for file: {file.filename}"
                )
            if file.status != "temporary":
                raise HTTPException(
                    status_code=400,
                    detail=f"File already attached: {file.filename}"
                )

        # Upload files to agent-env
        try:
            agent_file_paths = await FileService.upload_files_to_agent_env(
                session=session,
                file_ids=message_in.file_ids,
                environment_id=chat_session.environment_id,
            )
        except HTTPException:
            raise  # Re-raise HTTP exceptions as-is
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to upload files to agent environment: {str(e)}"
            )

        # Compose message content with file paths for agent
        file_list = "\n".join(f"- {path}" for path in agent_file_paths.values())
        message_content_for_agent = f"Uploaded files:\n{file_list}\n---\n\n{message_in.content}"

        # Create user message with file associations
        from app.models.file_upload import MessageFile

        user_message = MessageService.create_message(
            session=session,
            session_id=session_id,
            role="user",
            content=message_in.content,  # Store original content without file paths
            answers_to_message_id=message_in.answers_to_message_id,
            file_ids=message_in.file_ids,
        )

        # Update message_files with agent_env_paths
        statement = select(MessageFile).where(MessageFile.message_id == user_message.id)
        message_files = session.exec(statement).all()

        for message_file in message_files:
            if message_file.file_id in agent_file_paths:
                message_file.agent_env_path = agent_file_paths[message_file.file_id]

        session.commit()

        # Mark files as attached
        FileService.mark_files_as_attached(
            session=session,
            file_ids=list(agent_file_paths.keys()),
        )

        # For file messages, create a custom background task
        # that doesn't create the user message (already created above)
        async def stream_with_files():
            """Custom streaming task for messages with files"""
            from app.services.event_service import event_service
            from app.services.session_service import SessionService

            try:
                # Get session and environment
                with DBSession(engine) as db:
                    chat_session_db = db.get(Session, session_id)
                    if not chat_session_db:
                        return

                    environment_db = db.get(AgentEnvironment, chat_session_db.environment_id)
                    if not environment_db:
                        return

                    # Auto-generate session title if needed
                    if not chat_session_db.title or chat_session_db.title.strip() == "":
                        import asyncio
                        asyncio.create_task(
                            SessionService.auto_generate_session_title(
                                session_id=session_id,
                                first_message_content=message_in.content,
                                get_fresh_db_session=lambda: DBSession(engine)
                            )
                        )

                    # Set session status to active
                    SessionService.update_session_status(
                        db_session=db,
                        session_id=session_id,
                        status="active"
                    )

                    # Get environment details
                    base_url = MessageService.get_environment_url(environment_db)
                    auth_headers = MessageService.get_auth_headers(environment_db)
                    session_mode = chat_session_db.mode
                    agent_sdk = chat_session_db.agent_sdk
                    external_session_id = SessionService.get_external_session_id(chat_session_db)
                    environment_id = environment_db.id

                # Stream from environment (use composed message with file paths)
                async for event in MessageService.stream_message_with_events(
                    session_id=session_id,
                    environment_id=environment_id,
                    base_url=base_url,
                    auth_headers=auth_headers,
                    user_message_content=message_content_for_agent,  # Use composed content
                    session_mode=session_mode,
                    agent_sdk=agent_sdk,
                    external_session_id=external_session_id,
                    get_fresh_db_session=lambda: DBSession(engine)
                ):
                    # Emit each streaming event via WebSocket
                    await event_service.emit_stream_event(
                        session_id=session_id,
                        event_type=event.get("type"),
                        event_data=event
                    )

            except Exception as e:
                logger.error(f"Error in file message streaming: {e}", exc_info=True)
                await event_service.emit_stream_event(
                    session_id=session_id,
                    event_type="error",
                    event_data={
                        "type": "error",
                        "content": str(e),
                        "error_type": type(e).__name__
                    }
                )

        background_tasks.add_task(stream_with_files)
    else:
        # No files - use standard flow
        background_tasks.add_task(
            MessageService.handle_stream_message_websocket,
            session_id=session_id,
            message_content=message_in.content,
            answers_to_message_id=message_in.answers_to_message_id,
            db_session=session,
            get_fresh_db_session=lambda: DBSession(engine)
        )

    response = {
        "status": "ok",
        "message": "Message processing started",
        "session_id": str(session_id),
        "stream_room": f"session_{session_id}_stream"
    }

    if has_files:
        response["files_attached"] = len(message_in.file_ids)

    return response


@router.post("/{session_id}/messages/interrupt")
async def interrupt_message(
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
) -> Any:
    """
    Interrupt an active streaming message.

    Flow:
    1. Verify session ownership
    2. Request interrupt via active_streaming_manager
    3. Forward interrupt to agent environment if external_session_id available
    4. Return status
    """
    # Verify session exists and user owns it
    chat_session = session.get(Session, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not current_user.is_superuser and (chat_session.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    # Request interrupt via active_streaming_manager
    interrupt_info = await active_streaming_manager.request_interrupt(session_id)

    if not interrupt_info["found"]:
        raise HTTPException(
            status_code=400,
            detail="No active stream to interrupt (message may have already completed)"
        )

    # If interrupt is pending (external_session_id not yet available)
    if interrupt_info["pending"]:
        logger.info(f"Interrupt queued for session {session_id} (waiting for external_session_id)")
        return {
            "status": "ok",
            "message": "Interrupt queued (session starting)",
            "session_id": str(session_id),
            "queued": True
        }

    # External session ID is available - forward to agent env
    external_session_id = interrupt_info["external_session_id"]

    # Get environment
    environment = session.get(AgentEnvironment, chat_session.environment_id)
    if not environment:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Forward interrupt to environment using MessageService
    base_url = MessageService.get_environment_url(environment)
    auth_headers = MessageService.get_auth_headers(environment)

    try:
        result = await MessageService.forward_interrupt_to_environment(
            base_url=base_url,
            auth_headers=auth_headers,
            external_session_id=external_session_id
        )

        return {
            **result,
            "session_id": str(session_id),
            "queued": False
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get("/{session_id}/messages/streaming-status")
async def get_streaming_status(
    session: SessionDep,
    current_user: CurrentUser,
    session_id: uuid.UUID,
) -> Any:
    """
    Check if a session is currently streaming.

    This allows frontend to:
    - Detect ongoing streams after page refresh
    - Reconnect to active streams
    - Show appropriate UI state

    Returns:
        {
            "is_streaming": bool,
            "stream_info": dict | None  # Only if streaming
        }
    """
    # Verify session exists and user owns it
    chat_session = session.get(Session, session_id)
    if not chat_session:
        raise HTTPException(status_code=404, detail="Session not found")

    if not current_user.is_superuser and (chat_session.user_id != current_user.id):
        raise HTTPException(status_code=400, detail="Not enough permissions")

    # Check if session is actively streaming
    is_streaming = await active_streaming_manager.is_streaming(session_id)

    if is_streaming:
        stream_info = await active_streaming_manager.get_stream_info(session_id)
        return {
            "is_streaming": True,
            "stream_info": stream_info
        }
    else:
        return {
            "is_streaming": False,
            "stream_info": None
        }
