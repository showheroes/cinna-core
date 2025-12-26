"""
AI Functions Service - provides simple LLM processing utilities using Google ADK.

This service encapsulates fast, cheap LLM calls for tasks like:
- Generating agent configurations from descriptions
- Creating conversation titles from messages
- Other text generation tasks
"""
import logging
from typing import Optional

from app.core.config import settings
from app.agents import generate_agent_config, generate_conversation_title

logger = logging.getLogger(__name__)


class AIFunctionsService:
    """Service for simple AI-powered text generation tasks."""

    @staticmethod
    def _get_api_key() -> str:
        """
        Get Google API key from settings.

        Raises:
            ValueError: If GOOGLE_API_KEY is not configured
        """
        if not settings.GOOGLE_API_KEY:
            raise ValueError(
                "GOOGLE_API_KEY is not configured. "
                "Please set it in your .env file to use AI functions."
            )
        return settings.GOOGLE_API_KEY

    @staticmethod
    def generate_agent_configuration(description: str) -> dict:
        """
        Generate agent configuration from user description.

        Args:
            description: User's description of what the agent should do

        Returns:
            dict with keys:
                - name: Agent name (str)
                - entrypoint_prompt: Entry point description (str)

        Raises:
            ValueError: If GOOGLE_API_KEY is not configured
            Exception: If agent generation fails
        """
        try:
            api_key = AIFunctionsService._get_api_key()
            config = generate_agent_config(description, api_key)
            logger.info(f"Generated agent config: {config.get('name', 'Unknown')}")
            return config
        except ValueError:
            # Re-raise configuration errors
            raise
        except Exception as e:
            logger.error(f"Failed to generate agent config: {e}", exc_info=True)
            # Return fallback configuration
            return {
                "name": f"Agent: {description[:30]}...",
                "entrypoint_prompt": description,
            }

    @staticmethod
    def generate_session_title(message_content: str) -> str:
        """
        Generate a concise title for a conversation session.

        Args:
            message_content: First message from the user

        Returns:
            str: Concise title (max 100 chars)

        Raises:
            ValueError: If GOOGLE_API_KEY is not configured
        """
        try:
            api_key = AIFunctionsService._get_api_key()
            title = generate_conversation_title(message_content, api_key)
            logger.info(f"Generated session title: {title}")
            return title
        except ValueError:
            # Re-raise configuration errors
            raise
        except Exception as e:
            logger.error(f"Failed to generate session title: {e}", exc_info=True)
            # Return fallback title (truncated message)
            title = message_content[:100]
            if len(message_content) > 100:
                title += "..."
            return title

    @staticmethod
    def is_available() -> bool:
        """
        Check if AI functions are available (GOOGLE_API_KEY is configured).

        Returns:
            bool: True if AI functions can be used, False otherwise
        """
        return bool(settings.GOOGLE_API_KEY)
