"""
App Agent Router — classifies a user message and selects the best matching agent.

Uses the provider manager for cascade provider selection.
"""
import logging
from pathlib import Path

from .provider_manager import get_provider_manager

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent / "prompts"
APP_AGENT_ROUTER_PROMPT = PROMPTS_DIR / "app_agent_router_prompt.md"


def _load_prompt_template(file_path: Path) -> str:
    """Load prompt template from file."""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to load prompt template from {file_path}: {e}")


def route_to_agent(
    message: str,
    available_agents: list[dict],
    provider_kwargs: dict | None = None,
) -> str | None:
    """Classify a user message and pick the best matching agent.

    Args:
        message: The user's message to classify.
        available_agents: List of dicts with keys: id, name, trigger_prompt.
        provider_kwargs: Optional kwargs passed to the provider manager.

    Returns:
        Agent ID string of the best match, or None if no agent fits.
    """
    if not available_agents:
        return None

    try:
        template = _load_prompt_template(APP_AGENT_ROUTER_PROMPT)

        # Build agent list section
        agents_section = "\n".join(
            f"- **ID**: {agent['id']}\n  **Name**: {agent['name']}\n  **Description**: {agent['trigger_prompt']}"
            for agent in available_agents
        )

        prompt = f"""{template}

---

## Available Agents

{agents_section}

---

## User Message

{message}

---

Return the agent ID or NONE:
"""

        manager = get_provider_manager()
        response = manager.generate_content(prompt, **(provider_kwargs or {}))

        result = response.text.strip()
        logger.debug("App agent router response: %r", result)

        if result == "NONE" or not result:
            return None

        # Validate it looks like a UUID (basic check)
        if len(result) == 36 and result.count("-") == 4:
            return result

        logger.warning("App agent router returned unexpected value: %r", result)
        return None

    except Exception as e:
        logger.error("App agent routing failed: %s", e, exc_info=True)
        return None
