 read docs/agent-sessions/business_logic.md

lets move with the next step and implement already communication to our backend/frontend in the backend/app/api/routes/messages.py
backend/app/services/message_service.py ; do the following: make our
  backend to communicate with agent env by starting message streaming and saving messages and meta data (external session id) into our session / messages: expected result
: i can start session in the build mode, send message and receive a response (or multiple mesasges) from the agent env


Summary from the previous step of implementing the SDK communication in the agent env
----
Claude SDK Session Implementation Summary

  Overview

  Implemented Claude Code SDK integration within agent environment containers, enabling build mode sessions with resumption capability.

  Key Files to Read

  Backend - Session Management

  1. backend/app/models/session.py - Session models with external session metadata
  2. backend/app/services/session_service.py - Session lifecycle & external session management
  3. backend/app/api/routes/sessions.py - Session API endpoints

  Backend - Environment Server (Inside Container)

  4. backend/app/env-templates/python-env-advanced/app/server/sdk_manager.py - Claude SDK wrapper
  5. backend/app/env-templates/python-env-advanced/app/server/routes.py - Chat endpoints
  6. backend/app/env-templates/python-env-advanced/app/server/models.py - Request/response models

  Architecture Flow

  User → Main Backend → Environment Container → Claude SDK
                  ↓
           Session DB (stores external_session_id)

  1. Session Creation & Storage

  - Sessions have session_metadata JSON field storing:
    - external_session_id - Claude SDK session ID
    - sdk_type - "claude_code" | "google_adk"
    - last_sdk_message_id - For tracking


 2. Message Flow (Building Mode)

  1. First message:
    - Main backend sends to container /chat or /chat/stream
    - Container creates NEW Claude SDK session
    - SDK returns session_id in stream
    - Main backend calls SessionService.set_external_session_id() to store it
  2. Subsequent messages:
    - Main backend retrieves external_session_id via SessionService.get_external_session_id()
    - Sends to container with session_id in request
    - Container resumes existing SDK session

  3. Environment Server Endpoints

  - POST /chat - Non-streaming chat (collects full response)
  - POST /chat/stream - SSE streaming (real-time updates)
  - POST /config/prompts - Set system prompts
  - GET /sdk/sessions - List active sessions
  - DELETE /sdk/sessions/{id} - Close session

3. Environment Server Endpoints

  - POST /chat - Non-streaming chat (collects full response)
  - POST /chat/stream - SSE streaming (real-time updates)
  - POST /config/prompts - Set system prompts
  - GET /sdk/sessions - List active sessions
  - DELETE /sdk/sessions/{id} - Close session

  4. Stream Event Types

  {
    "type": "session_created" | "assistant" | "tool" | "result" | "error" | "done",
    "content": "...",
    "session_id": "...",
    "metadata": {}
  }

  Key Implementation Points

  SessionService Methods (for message handling)

  - get_external_session_id(session) - Get SDK session ID
  - set_external_session_id(db, session, sdk_id, "claude_code") - Store after first message
  - clear_external_session(db, session) - Reset SDK session

  SDK Manager Logic

  - Maintains in-memory cache: {session_id: sdk_session_object}
  - If session_id provided → resume existing
  - If None → create new via query()
  - Streams responses as dict with type/content/metadata

  Request Format (to Container)

  {
    "message": "user message",
    "session_id": "sdk-session-id" or None,
    "mode": "building",
    "system_prompt": "optional custom prompt"
  }

 For Message Implementation

  Backend Tasks

  1. Create message handler that:
    - Gets session from DB
    - Checks SessionService.get_external_session_id(session)
    - Calls environment server /chat/stream with session_id
    - If session_created event → store via set_external_session_id()
    - Save user message & assistant response to SessionMessage table
  2. Stream to frontend via WebSocket or SSE

  Frontend Tasks

  1. Send message to backend message endpoint
  2. Receive SSE/WebSocket stream
  3. Display real-time updates (assistant text, tool usage)
  4. Show SDK session status in UI (external_session_id)

  Environment Variables Needed

  - ANTHROPIC_API_KEY - Set in container
  - CLAUDE_CODE_WORKSPACE=/app/app - SDK workspace
  - CLAUDE_CODE_PERMISSION_MODE=acceptEdits - Auto-approve edits
  - AGENT_AUTH_TOKEN - Container authentication

  Next Step: Messages Implementation

  Read backend/app/api/routes/messages.py to see existing message structure, then implement streaming handler that bridges main backend ↔ environment container ↔ frontend.
  

