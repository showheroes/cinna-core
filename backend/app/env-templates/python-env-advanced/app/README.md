# Agent Workspace

This directory is the workspace where your agent operates.

## Build Mode

When you start a session in "building" mode, Claude Code SDK has access to this workspace with the following tools:

- **Read**: Read files and explore code
- **Edit**: Modify existing files
- **Write**: Create new files
- **Glob**: Find files by pattern
- **Grep**: Search code content
- **Bash**: Execute commands

Claude will help you:
- Write scripts and utilities
- Set up configurations
- Create project structures
- Debug and fix code

## Conversation Mode

In "conversation" mode, the agent uses pre-built tools and scripts from this workspace to help with tasks.

## Directory Structure

- `/credentials/` - Service credentials (read-only)
- `/databases/` - SQLite or other local databases
- `/files/` - User-uploaded files
- `/logs/` - Agent logs
- `/scripts/` - Custom scripts
- `/server/` - Optional: Custom API endpoints
- `/docs/` - Documentation and specifications
