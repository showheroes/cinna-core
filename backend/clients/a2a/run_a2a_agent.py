#!/usr/bin/env python3
"""
Interactive A2A Client for testing agent communication.

This script connects to an A2A-compatible agent using URL and token from .env file,
allows interactive conversation, and logs all A2A payloads to a session log file.

Usage:
    python run_a2a_agent.py

Environment variables (in .env file):
    A2A_AGENT_URL - The base URL of the A2A agent (e.g., https://api.example.com/api/v1/a2a/{agent_id}/)
    A2A_ACCESS_TOKEN - JWT access token for authentication
"""

import asyncio
from pathlib import Path

from utils import A2AConnection, SessionLogger, extract_text_from_message, load_config


class InteractiveChatClient:
    """Interactive console client for chat communication with A2A agent."""

    def __init__(self, connection: A2AConnection):
        """Initialize chat client.

        Args:
            connection: A2AConnection instance for agent communication
        """
        self.connection = connection

    async def chat(self, message: str) -> str | None:
        """Send a chat message and print the response.

        Args:
            message: Message text to send

        Returns:
            Full response text or None on error
        """
        response_parts: list[str] = []
        print("\nAgent: ", end="", flush=True)

        async for event_type, content in self.connection.send_message(message):
            if event_type == "text":
                print(content, end="", flush=True)
                response_parts.append(content)
            elif event_type == "error":
                print(f"\nError: {content}")
                return None

        print()  # New line after response
        return "".join(response_parts)

    def handle_command(self, command: str) -> bool | str:
        """Handle a chat command.

        Args:
            command: Command string (e.g., '/quit', '/new')

        Returns:
            True if should continue chat loop (command handled),
            False if should exit,
            'async' if command needs async handling
        """
        parts = command.split(maxsplit=1)
        cmd_name = parts[0].lower()

        if cmd_name in ["/quit", "/exit"]:
            print("Goodbye!")
            return False

        if cmd_name == "/new":
            self.connection.reset_conversation()
            print("Started new conversation")
            return True

        if cmd_name == "/status":
            print(f"  Task ID: {self.connection.task_id or '(none)'}")
            print(f"  Context ID: {self.connection.context_id or '(none)'}")
            if self.connection.logger:
                print(f"  Log file: {self.connection.logger.log_file}")
            return True

        if cmd_name in ["/session", "/task"]:
            # Need async handling
            return "async"

        if cmd_name == "/tasks":
            # Need async handling
            return "async"

        # Unknown command, treat as regular message
        return True

    async def handle_async_command(self, command: str) -> None:
        """Handle commands that require async operations.

        Args:
            command: Command string
        """
        parts = command.split(maxsplit=1)
        cmd_name = parts[0].lower()

        if cmd_name in ["/session", "/task"]:
            if len(parts) < 2:
                print("Usage: /session <task_id>")
                return

            session_id = parts[1].strip()
            print(f"\nResuming session: {session_id}")

            # Fetch task to verify it exists
            task = await self.connection.get_task(session_id)
            if task:
                self.connection.set_session(session_id)
                print("  Session resumed successfully")
                state = task.status.state if task.status else "unknown"
                # Handle TaskState enum
                state_str = state.value if hasattr(state, "value") else str(state)
                print(f"  State: {state_str}")
                if task.status and task.status.timestamp:
                    print(f"  Last updated: {task.status.timestamp}")

                # Show message history
                if task.history:
                    print(f"\n  --- Conversation History ({len(task.history)} messages) ---\n")
                    for msg in task.history:
                        role = msg.role
                        role_str = role.value if hasattr(role, "value") else str(role)
                        text = extract_text_from_message(msg)
                        if role_str == "user":
                            print(f"You: {text}\n")
                        else:
                            print(f"Agent: {text}\n")
                    print("  --- End of History ---")
            else:
                print("  Error: Task not found or access denied")

        elif cmd_name == "/tasks":
            print("\nFetching tasks...")
            tasks = await self.connection.list_tasks(limit=20)

            if not tasks:
                print("  No tasks found")
                return

            print(f"\n  {'ID':<36}  {'State':<15}  {'Updated'}")
            print("  " + "-" * 70)
            for task in tasks:
                state = task.status.state if task.status else "unknown"
                timestamp = task.status.timestamp[:19] if task.status and task.status.timestamp else "N/A"
                task_id = task.id or "N/A"
                print(f"  {task_id:<36}  {state:<15}  {timestamp}")

            print(f"\n  Total: {len(tasks)} task(s)")
            print("  Use '/session <id>' to resume a session")

    async def run(self) -> None:
        """Run the interactive chat loop."""
        self._print_banner()

        if not await self.connection.connect():
            return

        print("\nType your message and press Enter to send.")
        print("=" * 60)

        try:
            while True:
                try:
                    user_input = input("\nYou: ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\nGoodbye!")
                    break

                if not user_input:
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    result = self.handle_command(user_input)
                    if result is False:
                        break
                    if result == "async":
                        await self.handle_async_command(user_input)
                        continue
                    if result is True:
                        # Command handled synchronously
                        cmd_name = user_input.split()[0].lower()
                        if cmd_name in ["/new", "/status"]:
                            continue

                # Send message to agent
                await self.chat(user_input)

        finally:
            await self.connection.close()

    def _print_banner(self) -> None:
        """Print the welcome banner with usage instructions."""
        print("\n" + "=" * 60)
        print("Interactive A2A Client")
        print("=" * 60)
        print("Commands:")
        print("  /quit or /exit   - Exit the client")
        print("  /new             - Start a new conversation")
        print("  /status          - Show current session info")
        print("  /tasks           - List all tasks (sessions)")
        print("  /session <id>    - Resume a session by task ID")
        print("  /task <id>       - Alias for /session")
        print("=" * 60)


async def main() -> None:
    """Main entry point."""
    agent_url, access_token = load_config()
    logs_dir = Path(__file__).parent / "logs"

    logger = SessionLogger(logs_dir)
    connection = A2AConnection(agent_url, access_token, logger)
    client = InteractiveChatClient(connection)

    await client.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye!")
