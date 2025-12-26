# AI Functions Development Guide

## Overview

AI Functions provide simple, fast LLM-powered utilities for text generation tasks like creating conversation titles, generating agent configurations, and other quick processing needs. They use Google's Gemini Flash model for cheap, fast inference.

## Architecture

### Key Components

- **`backend/app/services/ai_functions_service.py`** - Service layer that encapsulates AI function calls
- **`backend/app/agents/`** - Individual agent implementations for specific tasks
- **`backend/app/core/config.py`** - Configuration for `GOOGLE_API_KEY`

### Current Implementations

1. **Title Generator** (`backend/app/agents/title_generator.py`)
   - Generates concise conversation titles from first user message
   - Used in: `backend/app/api/routes/messages.py:155-175`

2. **Agent Config Generator** (`backend/app/agents/agent_generator.py`)
   - Generates agent name and entrypoint_prompt from description
   - Used in: `backend/app/services/agent_service.py:132-156`

## Implementation Pattern

All AI functions follow this simple pattern:

1. **Use Google GenAI Client directly** (not ADK)
   - Import: `from google.genai import Client`
   - Create client with API key: `Client(api_key=api_key)`

2. **Simple synchronous calls**
   - Use `client.models.generate_content(model="gemini-2.5-flash-lite", contents=prompt)`
   - Extract response: `response.text.strip()`

3. **Graceful fallbacks**
   - Always include fallback logic if API call fails
   - Return sensible defaults

## Adding New AI Functions

### Step 1: Create Agent File

Create a new file in `backend/app/agents/` (e.g., `my_new_agent.py`):

```
def my_function(input_data: str, api_key: str) -> str:
    client = Client(api_key=api_key)
    prompt = f"Your prompt here with {input_data}"
    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
    )
    return response.text.strip()
```

### Step 2: Export from `__init__.py`

Add to `backend/app/agents/__init__.py`:
```python
from .my_new_agent import my_function
__all__ = ["...", "my_function"]
```

### Step 3: Add Service Method

Add method to `AIFunctionsService` in `backend/app/services/ai_functions_service.py`:

```python
@staticmethod
def my_service_method(input_data: str) -> str:
    try:
        api_key = AIFunctionsService._get_api_key()
        result = my_function(input_data, api_key)
        logger.info(f"Generated result: {result}")
        return result
    except ValueError:
        raise  # Re-raise config errors
    except Exception as e:
        logger.error(f"Failed: {e}", exc_info=True)
        return "fallback value"
```

### Step 4: Use in Application Code

Call from routes or services:
```python
if AIFunctionsService.is_available():
    result = AIFunctionsService.my_service_method(input_data)
else:
    result = fallback_value
```

## Best Practices

### 1. Keep Functions Simple
- AI functions should do ONE thing
- Use fast models (`gemini-2.5-flash-lite`)
- Avoid complex multi-turn conversations

### 2. Always Provide Fallbacks
- Check `AIFunctionsService.is_available()` before calling
- Wrap calls in try/except blocks
- Return sensible defaults on failure

### 3. Use Synchronous Calls
- These are simple text generation tasks
- No need for ADK Runner/Session complexity
- Direct `Client.models.generate_content()` is sufficient

### 4. Prompt Engineering
- Be specific in prompts
- Request exact output format (JSON, plain text, etc.)
- Include examples in prompts when needed

### 5. Response Parsing
- Clean up responses (remove markdown, quotes, etc.)
- Validate expected fields for structured output (JSON)
- Handle parsing failures gracefully

## Configuration

### Environment Variable

Add to `.env`:
```
GOOGLE_API_KEY=your-api-key-here
```

Get API key from: https://makersuite.google.com/app/apikey

### Model Selection

Current model: `gemini-2.5-flash-lite`
- Fast and cheap
- Good for simple text generation
- Sufficient for titles, names, short descriptions

For more complex tasks, consider upgrading to `gemini-2.5-flash` or `gemini-2.5-pro`.

## Testing

When adding new AI functions:

1. **Test with API key configured** - Verify actual LLM calls work
2. **Test without API key** - Verify fallbacks work correctly
3. **Test with malformed responses** - Ensure parsing errors are handled
4. **Test edge cases** - Empty inputs, very long inputs, special characters

## Common Pitfalls

### ❌ Don't Use ADK for Simple Tasks
Google ADK (Agent Development Kit) is for complex multi-agent workflows. For simple text generation, use `google.genai.Client` directly.

### ❌ Don't Make Async Functions
Unless integrating with async routes, keep AI functions synchronous. The GenAI client handles I/O internally.

### ❌ Don't Forget Error Handling
Network issues, API errors, and quota limits can occur. Always wrap calls and provide fallbacks.

### ❌ Don't Hardcode API Keys
Always use `settings.GOOGLE_API_KEY` from config, never hardcode keys in code.

## Examples

See existing implementations:
- Simple text generation: `backend/app/agents/title_generator.py`
- Structured output (JSON): `backend/app/agents/agent_generator.py`
- Service integration: `backend/app/services/ai_functions_service.py`
- Usage in routes: `backend/app/api/routes/messages.py:155-175`
- Usage in services: `backend/app/services/agent_service.py:132-156`

## Future Enhancements

Potential AI functions to add:
- Code snippet summarization
- Error message explanation
- Parameter suggestion from context
- Workflow description generation
- Commit message generation

Keep functions focused, fast, and simple!
