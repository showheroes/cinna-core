"""
Create Collaboration Tool for Agent Environment.

Allows a coordinator agent to dispatch a set of subtasks to multiple agents
simultaneously. Each subtask runs as an independent session. The coordinator
receives feedback as each subtask completes (via auto-feedback mechanism).
"""
import os
import logging
from typing import Any
import httpx

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)

# Environment variables for backend connection
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")

# Import functions to get current backend session_id
from ..sdk_manager import get_backend_session_id


@tool(
    "create_collaboration",
    "Create a multi-agent collaboration. Dispatches subtasks to multiple agents "
    "simultaneously. You will receive feedback as each subtask completes. "
    "Use this when a task requires input from multiple agents at the same time. "
    "Each entry in subtasks must have: target_agent_id (str UUID), task_message (str). "
    "Optional: order (int) for display ordering.",
    {"title": str, "description": str, "subtasks": list}
)
async def create_collaboration(args: dict[str, Any]) -> dict[str, Any]:
    """
    Create a multi-agent collaboration.

    Args:
        args: Dictionary with:
            - title: Short title for the collaboration (required)
            - description: Longer description of the overall goal (optional)
            - subtasks: List of dicts, each with:
                - target_agent_id: UUID of the target agent (required)
                - task_message: Instructions for the target agent (required)
                - order: Display order (optional, default 0)

    Returns:
        Tool response with success status and collaboration_id, or error.
    """
    title = args.get("title", "").strip()
    description = args.get("description", "").strip() or None
    subtasks = args.get("subtasks", [])

    if not title:
        return {
            "content": [{"type": "text", "text": "Error: title parameter is required"}],
            "is_error": True,
        }

    if not subtasks or not isinstance(subtasks, list):
        return {
            "content": [{"type": "text", "text": "Error: subtasks must be a non-empty list"}],
            "is_error": True,
        }

    # Validate each subtask has required fields
    for i, subtask in enumerate(subtasks):
        if not isinstance(subtask, dict):
            return {
                "content": [{"type": "text", "text": f"Error: subtask {i} must be a dict"}],
                "is_error": True,
            }
        if not subtask.get("target_agent_id"):
            return {
                "content": [{"type": "text", "text": f"Error: subtask {i} missing target_agent_id"}],
                "is_error": True,
            }
        if not subtask.get("task_message", "").strip():
            return {
                "content": [{"type": "text", "text": f"Error: subtask {i} missing task_message"}],
                "is_error": True,
            }

    if not BACKEND_URL:
        return {
            "content": [{"type": "text", "text": "Error: Backend URL not configured"}],
            "is_error": True,
        }

    if not AGENT_AUTH_TOKEN:
        return {
            "content": [{"type": "text", "text": "Error: Authentication token not configured"}],
            "is_error": True,
        }

    source_session_id = get_backend_session_id()
    if not source_session_id:
        return {
            "content": [{"type": "text", "text": "Error: Backend session ID not available"}],
            "is_error": True,
        }

    try:
        url = f"{BACKEND_URL}/api/v1/agents/collaborations/create"
        headers = {
            "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "title": title,
            "description": description,
            "subtasks": subtasks,
            "source_session_id": source_session_id,
        }

        logger.info(f"Creating collaboration '{title}' with {len(subtasks)} subtasks")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                collaboration_id = data.get("collaboration_id")
                subtask_count = data.get("subtask_count", 0)
                logger.info(f"Collaboration created: {collaboration_id} ({subtask_count} subtasks)")
                return {
                    "content": [{
                        "type": "text",
                        "text": (
                            f"Collaboration '{title}' created successfully (ID: {collaboration_id}). "
                            f"Dispatched {subtask_count} subtask(s) to target agents. "
                            f"You will receive feedback as each subtask completes."
                        ),
                    }],
                }
            else:
                error = data.get("error", "Unknown error")
                logger.error(f"Collaboration creation failed: {error}")
                return {
                    "content": [{"type": "text", "text": f"Collaboration creation failed: {error}"}],
                    "is_error": True,
                }
        elif response.status_code == 401:
            return {
                "content": [{"type": "text", "text": "Error: Authentication failed"}],
                "is_error": True,
            }
        else:
            logger.error(f"Collaboration creation failed HTTP {response.status_code}: {response.text}")
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: Request failed (HTTP {response.status_code}): {response.text}",
                }],
                "is_error": True,
            }

    except httpx.TimeoutException:
        return {
            "content": [{"type": "text", "text": "Error: Request timed out"}],
            "is_error": True,
        }
    except httpx.RequestError as e:
        logger.error(f"Request error creating collaboration: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: Failed to connect to backend: {str(e)}"}],
            "is_error": True,
        }
    except Exception as e:
        logger.error(f"Unexpected error creating collaboration: {e}", exc_info=True)
        return {
            "content": [{"type": "text", "text": f"Error: Unexpected error: {str(e)}"}],
            "is_error": True,
        }
