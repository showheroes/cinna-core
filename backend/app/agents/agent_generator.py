"""
Agent generator - creates agent configuration from user description.
"""
import json
from google.genai import Client


def generate_agent_config(description: str, api_key: str) -> dict:
    """
    Generate agent configuration (name, entrypoint_prompt) from description.

    Args:
        description: User's description of what the agent should do
        api_key: Google API key for Gemini

    Returns:
        dict with keys: name, entrypoint_prompt
    """
    # Create Google GenAI client
    client = Client(api_key=api_key)

    # Create prompt
    prompt = f"""You are an AI assistant that helps create agent configurations.

Given a user's description of what they want an agent to do, generate:
1. A concise name for the agent (max 50 characters, descriptive)
2. An entrypoint_prompt that describes what the agent should do

User's description: {description}

Return ONLY a JSON object with these exact keys: "name", "entrypoint_prompt"
Do not include markdown formatting, just the raw JSON.

Example format:
{{"name": "Code Review Assistant", "entrypoint_prompt": "Review code and provide detailed feedback on quality, potential bugs, and improvements"}}
"""

    # Generate content
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )

    # Extract response text
    response_text = response.text.strip()

    # Clean up response - remove markdown code blocks if present
    if response_text.startswith("```json"):
        response_text = response_text[7:]
    if response_text.startswith("```"):
        response_text = response_text[3:]
    if response_text.endswith("```"):
        response_text = response_text[:-3]
    response_text = response_text.strip()

    try:
        config = json.loads(response_text)

        # Validate required fields
        required_fields = ["name", "entrypoint_prompt"]
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required field: {field}")

        return config
    except (json.JSONDecodeError, ValueError) as e:
        # Fallback to simple config if JSON parsing fails
        return {
            "name": f"Agent for: {description[:30]}...",
            "entrypoint_prompt": description,
        }
