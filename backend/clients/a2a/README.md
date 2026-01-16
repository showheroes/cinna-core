# A2A Interactive Client

A simple console-based client for testing A2A (Agent-to-Agent) protocol communication with agents.

## Setup

1. Configure the `.env` file with your agent details:

```env
A2A_AGENT_URL=http://localhost:8000/api/v1/a2a/{agent_id}/
A2A_ACCESS_TOKEN=your-jwt-token-here
```

- **A2A_AGENT_URL**: The full URL to your agent's A2A endpoint (found in the agent's Integrations tab)
- **A2A_ACCESS_TOKEN**: JWT access token created in the agent's Integrations tab

2. Run the client from the `backend` directory:

```bash
cd backend
source .venv/bin/activate
python clients/a2a/run_a2a_agent.py
```

## Features

- **Interactive conversation**: Type messages and receive streaming responses
- **Session continuity**: Conversations persist across messages using `task_id` and `context_id`
- **Session resumption**: Resume previous sessions with full conversation history display
- **Task listing**: View all tasks/sessions for the agent via A2A protocol
- **Payload logging**: All A2A payloads (sent and received) are logged to JSON files

## Commands

| Command | Description |
|---------|-------------|
| `/quit` or `/exit` | Exit the client |
| `/new` | Start a new conversation (clears task_id/context_id) |
| `/status` | Show current session info (task_id, context_id, log file path) |
| `/tasks` | List all tasks (sessions) for the agent |
| `/session <id>` | Resume a session by task ID (A2A `tasks/get`) |
| `/task <id>` | Alias for `/session` |

## Session Logs

All A2A payloads are logged to `logs/` directory:

- One JSON file per session: `session_YYYYMMDD_HHMMSS_<id>.json`
- Contains all sent and received payloads with timestamps
- Useful for debugging A2A protocol communication

Example log entry:
```json
[
  {
    "direction": "sent",
    "timestamp": "2026-01-16T10:30:00.123456",
    "payload": { ... }
  },
  {
    "direction": "received",
    "timestamp": "2026-01-16T10:30:01.234567",
    "payload": { ... }
  }
]
```

## Example Session

```
============================================================
Interactive A2A Client
============================================================
Commands:
  /quit or /exit   - Exit the client
  /new             - Start a new conversation
  /status          - Show current session info
  /tasks           - List all tasks (sessions)
  /session <id>    - Resume a session by task ID
  /task <id>       - Alias for /session
============================================================
Connecting to: http://localhost:8000/api/v1/a2a/74937a22-793c-4a2a-9a28-7e11641d36a0/
Fetching agent card from: http://localhost:8000/api/v1/a2a/74937a22-793c-4a2a-9a28-7e11641d36a0/

Connected to agent: My Agent
Description: A helpful assistant
Skills: ['answer_questions', 'provide_information']

Type your message and press Enter to send.
============================================================

You: Hello, how are you?

Agent: Hello! I'm doing well, thank you for asking. How can I help you today?

You: /status
  Task ID: 550e8400-e29b-41d4-a716-446655440000
  Context ID: 550e8400-e29b-41d4-a716-446655440000
  Log file: logs/session_20260116_103000_abc12345.json

You: /tasks

Fetching tasks...

  ID                                    State            Updated
  ----------------------------------------------------------------------
  550e8400-e29b-41d4-a716-446655440000  completed        2026-01-16T10:30
  550e8400-e29b-41d4-a716-446655440001  working          2026-01-16T09:15

  Total: 2 task(s)
  Use '/session <id>' to resume a session

You: /session 550e8400-e29b-41d4-a716-446655440001

Resuming session: 550e8400-e29b-41d4-a716-446655440001
  Session resumed successfully
  State: completed
  Last updated: 2026-01-16T09:15:00Z

  --- Conversation History (3 messages) ---

You: Hello, can you help me with my project?

Agent: Of course! I'd be happy to help. What kind of project are you working on?

You: I'm building a web application with React.

  --- End of History ---

You: Can you continue helping me?

Agent: Absolutely! Where did we leave off with your React application?

You: /quit
Goodbye!
```

## Troubleshooting

**Connection errors:**
- Verify the agent URL is correct and the agent is running
- Check that A2A is enabled for the agent (Integrations tab)
- Ensure the access token is valid and not revoked

**Authentication errors (401/403):**
- Token may be expired or revoked
- Token scope may not allow the requested operation
- Create a new token in the agent's Integrations tab

**Empty responses:**
- Check the session log file for the raw A2A payloads
- The agent may be returning data in a format not yet handled by the text extractor
