"""
Title generator - creates concise conversation titles from first message.
"""
from google.genai import Client


def generate_conversation_title(message_content: str, api_key: str) -> str:
    """
    Generate a concise title for a conversation based on the first message.

    Args:
        message_content: First message from the user
        api_key: Google API key for Gemini

    Returns:
        str: Concise title for the conversation (max 100 chars)
    """
    # Create Google GenAI client
    client = Client(api_key=api_key)

    # Create prompt
    prompt = f"""You are an AI assistant that creates concise conversation titles.

Given the first message from a user, generate a short, descriptive title for the conversation (maximum 100 characters).
The title should capture the main topic or intent of the message.

User's message: {message_content}

Return ONLY the title text, without any quotes, markdown, or formatting.
"""

    # Generate content
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )

    # Extract title
    title = response.text.strip()

    # Remove quotes if present
    if (title.startswith('"') and title.endswith('"')) or (
        title.startswith("'") and title.endswith("'")
    ):
        title = title[1:-1]

    # Truncate to 100 chars if needed
    if len(title) > 100:
        title = title[:97] + "..."

    # Fallback to truncated message if result is empty
    if not title:
        title = message_content[:100]
        if len(message_content) > 100:
            title += "..."

    return title
