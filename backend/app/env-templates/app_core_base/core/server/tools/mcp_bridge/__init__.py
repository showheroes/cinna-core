"""
MCP Bridge Servers for OpenCode Adapter.

This package contains lightweight stdio MCP servers that expose our platform's
custom tools to OpenCode agents. Each server wraps the same HTTP calls that the
Claude Code adapter makes, but as standalone processes launched by OpenCode via
its local MCP server config.

Servers:
- knowledge_server.py  — query_integration_knowledge (building mode)
- task_server.py       — add_comment, update_status, create_task, create_subtask,
                         get_details, list_tasks (agent_task server, conversation mode)

Session context (backend_session_id, opencode_session_id) is shared via a JSON
file written by the OpenCodeAdapter before each message into the per-mode
runtime dir (e.g. /tmp/.opencode_building/session_context.json).  Bridge
servers read it from cwd, which opencode serve sets to the runtime dir.
"""
