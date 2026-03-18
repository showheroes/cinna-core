"""
Task refiner - helps users refine task descriptions for AI agent execution.

Uses the provider manager for cascade provider selection.
"""
import json
from pathlib import Path

from .provider_manager import get_provider_manager


# Path to prompt template
PROMPTS_DIR = Path(__file__).parent / "prompts"
TASK_REFINER_PROMPT = PROMPTS_DIR / "task_refiner_prompt.md"


def _load_prompt_template() -> str:
    """Load the task refiner prompt template."""
    try:
        return TASK_REFINER_PROMPT.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to load task refiner prompt: {e}")


def refine_task(
    current_description: str,
    agent_workflow_prompt: str | None,
    user_comment: str,
    refinement_history: list[dict] | None = None,
    user_selected_text: str | None = None,
    agent_refiner_prompt: str | None = None,
    provider_kwargs: dict | None = None,
) -> dict:
    """
    Refine a task description based on user feedback.

    Args:
        current_description: The current task description
        agent_workflow_prompt: The selected agent's workflow prompt (for context)
        user_comment: User's refinement request or feedback
        refinement_history: Previous refinement conversation history
        user_selected_text: Optional text selected by user from the task body
        agent_refiner_prompt: Agent-specific instructions for refining task descriptions

    Returns:
        dict with keys:
            - success: bool
            - refined_description: The improved description (if success)
            - feedback_message: Brief message about changes or questions
            - error: Error message (if not success)
    """
    manager = get_provider_manager()

    # Load system prompt
    system_prompt = _load_prompt_template()

    # Build context about the agent if available
    agent_context = ""
    if agent_workflow_prompt:
        agent_context = f"""
## Target Agent Context
This task will be executed by an agent with the following capabilities:
{agent_workflow_prompt}

Consider the agent's capabilities when refining the task description.
"""

    # Build agent-specific refinement instructions if available
    refiner_context = ""
    if agent_refiner_prompt:
        refiner_context = f"""
## Agent-Specific Refinement Instructions
Follow these guidelines when refining tasks for this agent:
{agent_refiner_prompt}

Apply these instructions to fill in defaults, validate mandatory fields, and enhance the task description accordingly.
"""

    # Build history context
    history_context = ""
    if refinement_history:
        history_items = []
        for item in refinement_history[-5:]:  # Last 5 items for context
            role = "User" if item.get("role") == "user" else "Assistant"
            content = item.get("content", "")
            history_items.append(f"**{role}**: {content}")
        if history_items:
            history_context = f"""
## Previous Refinement Conversation
{chr(10).join(history_items)}
"""

    # Build user selected text context
    selected_text_context = ""
    if user_selected_text:
        selected_text_context = f"""
## User-Selected Text Reference
The user has highlighted the following specific text from the task description that their feedback relates to:
---
{user_selected_text}
---
Pay special attention to this section when processing the user's feedback.
"""

    # Build the full prompt
    prompt = f"""{system_prompt}
{agent_context}
{refiner_context}
{history_context}
## Current Task Description
{current_description}
{selected_text_context}
## User's Request/Feedback
{user_comment}

## Your Task
Refine the task description based on the user's feedback. Return a valid JSON response with the structure shown in the Response Format section above.

IMPORTANT: Return ONLY the JSON object, no markdown code blocks or other formatting.
"""

    try:
        response = manager.generate_content(prompt, **(provider_kwargs or {}))
        response_text = response.text.strip()

        # Clean up response if wrapped in code blocks
        if response_text.startswith("```"):
            # Remove markdown code blocks
            lines = response_text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].strip() == "```":
                lines = lines[:-1]
            response_text = "\n".join(lines)

        # Parse JSON response
        result = json.loads(response_text)

        if not isinstance(result, dict):
            return {
                "success": False,
                "error": "Invalid response format - expected JSON object",
            }

        refined = result.get("refined_description", "")
        feedback = result.get("feedback_message", "")

        if not refined:
            return {
                "success": False,
                "error": "No refined description in response",
            }

        return {
            "success": True,
            "refined_description": refined,
            "feedback_message": feedback,
        }

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Failed to parse AI response as JSON: {str(e)}",
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to refine task: {str(e)}",
        }
