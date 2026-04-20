"""
Command Service - framework for handling slash commands in agent sessions.

Slash commands (e.g., /files) are quick, deterministic commands that don't
require an LLM call. They are executed locally and return markdown responses.
"""
import logging
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass
class CommandContext:
    """Context passed to command handlers."""
    session_id: UUID
    environment_id: UUID
    agent_id: UUID
    user_id: UUID
    access_token_id: UUID | None = None
    frontend_host: str = ""
    backend_base_url: str = ""


@dataclass
class CommandResult:
    """Result from a command execution."""
    content: str
    is_error: bool = False
    routing: str | None = None                      # "command_stream" when handler requests async dispatch
    resolved_command: str | None = None             # Shell command for routing=command_stream
    exec_command_short_name: str | None = None      # Short name for the command


class CommandHandler(ABC):
    """Abstract base class for command handlers."""

    streams: bool = False  # If True, handler queues a pending message instead of returning content
    include_in_llm_context: bool = True  # If False, command output is excluded from <prior_commands> block

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (e.g., '/files')."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of the command."""
        ...

    @abstractmethod
    async def execute(self, context: CommandContext, args: str) -> CommandResult:
        """Execute the command and return a result."""
        ...


class CommandService:
    """Static registry and dispatcher for slash commands."""

    _handlers: dict[str, CommandHandler] = {}

    @classmethod
    def register(cls, handler: CommandHandler) -> None:
        """Register a command handler."""
        cls._handlers[handler.name] = handler
        logger.info(f"Registered command handler: {handler.name}")

    @classmethod
    def is_command(cls, content: str) -> bool:
        """Check if a message starts with a registered command.

        Supports both space-separated form ("/run check") and colon form ("/run:check").
        """
        if not content:
            return False
        stripped = content.strip()
        if not stripped.startswith("/"):
            return False
        # Check colon form: "/run:name" → base name is "/run"
        first_token = stripped.split()[0].lower()
        if ":" in first_token:
            base_name = first_token.split(":")[0]
            return base_name in cls._handlers
        return first_token in cls._handlers

    @classmethod
    def parse_command(cls, content: str) -> tuple[str, str]:
        """Parse command name and arguments from message content.

        Handles both "/run check" and "/run:check" forms.
        For colon form, the suffix becomes the args.
        """
        stripped = content.strip()
        parts = stripped.split(maxsplit=1)
        first_token = parts[0].lower()
        if ":" in first_token:
            # Colon form: "/run:check" → name="/run", args="check"
            colon_idx = first_token.index(":")
            name = first_token[:colon_idx]
            colon_suffix = first_token[colon_idx + 1:]
            # Remaining space-separated args (if any) are appended
            space_args = parts[1] if len(parts) > 1 else ""
            args = (colon_suffix + (" " + space_args if space_args else "")).strip()
        else:
            name = first_token
            args = parts[1] if len(parts) > 1 else ""
        return name, args

    @classmethod
    def get_handler(cls, name: str) -> "CommandHandler | None":
        """Return the handler instance for a given command name, or None if not registered."""
        return cls._handlers.get(name)

    @classmethod
    def list_handlers(cls) -> list[CommandHandler]:
        """Return an ordered list of all registered command handlers."""
        return list(cls._handlers.values())

    @classmethod
    async def execute(cls, content: str, context: CommandContext) -> CommandResult:
        """Dispatch to the appropriate command handler."""
        name, args = cls.parse_command(content)
        handler = cls._handlers.get(name)
        if not handler:
            return CommandResult(
                content=f"Unknown command: `{name}`. Available commands: {', '.join(sorted(cls._handlers.keys()))}",
                is_error=True,
            )
        try:
            return await handler.execute(context, args)
        except Exception as e:
            logger.error(f"Error executing command {name}: {e}", exc_info=True)
            return CommandResult(
                content=f"Error executing `{name}`: {str(e)}",
                is_error=True,
            )
