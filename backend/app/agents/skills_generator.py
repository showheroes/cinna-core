"""
A2A Skills Generator - extracts skills from workflow prompts.

This module generates A2A-compatible skills from an agent's workflow prompt.
Skills enable other agents to discover capabilities via the A2A protocol.
Uses the provider manager for cascade provider selection.
"""
import json
import logging
from pathlib import Path

from .provider_manager import get_provider_manager


logger = logging.getLogger(__name__)

# Paths to prompt template files
PROMPTS_DIR = Path(__file__).parent / "prompts"
SKILLS_PROMPT_TEMPLATE = PROMPTS_DIR / "skills_generator_prompt.md"


def _load_prompt_template(file_path: Path) -> str:
    """Load prompt template from file."""
    try:
        return file_path.read_text(encoding="utf-8")
    except Exception as e:
        raise RuntimeError(f"Failed to load prompt template from {file_path}: {e}")


def _parse_skills_response(response_text: str) -> list[dict]:
    """Parse the LLM response into a list of skill dictionaries."""
    text = response_text.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        text = "\n".join(lines).strip()

    # Parse JSON
    try:
        skills = json.loads(text)
        if not isinstance(skills, list):
            logger.warning(f"Skills response is not a list: {type(skills)}")
            return []

        # Validate each skill has required fields
        valid_skills = []
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            if all(key in skill for key in ["id", "name", "description"]):
                # Ensure optional fields have defaults
                skill.setdefault("tags", [])
                skill.setdefault("examples", [])
                valid_skills.append(skill)
            else:
                logger.warning(f"Skill missing required fields: {skill}")

        return valid_skills
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse skills JSON: {e}")
        return []


def generate_a2a_skills(workflow_prompt: str) -> list[dict]:
    """
    Generate A2A skills from a workflow prompt.

    Args:
        workflow_prompt: The agent's workflow prompt describing its capabilities

    Returns:
        List of skill dictionaries with keys:
            - id: Kebab-case identifier
            - name: Human-readable name
            - description: What the skill does
            - tags: List of keywords for discovery
            - examples: Sample prompts that trigger this skill
    """
    if not workflow_prompt or not workflow_prompt.strip():
        return []

    try:
        manager = get_provider_manager()

        # Load template
        template = _load_prompt_template(SKILLS_PROMPT_TEMPLATE)

        # Construct full prompt
        prompt = f"""{template}

---

## Workflow Prompt to Analyze

{workflow_prompt}

---

Generate the A2A skills JSON array now. Remember: Return only valid JSON, no markdown formatting.
"""

        # Call LLM using provider manager (cascade fallback)
        response = manager.generate_content(prompt)

        # Parse response
        skills = _parse_skills_response(response.text)

        logger.info(f"Generated {len(skills)} A2A skills from workflow prompt")
        return skills

    except Exception as e:
        logger.warning(f"Failed to generate A2A skills: {str(e)}")
        return []
