"""
Post Finding Tool for Agent Environment.

Allows a participant agent to share an intermediate finding, observation,
or partial result with all other agents in a collaboration.
"""
import os
import logging
from typing import Any
import httpx

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")

from ..sdk_manager import get_backend_session_id


@tool(
    "post_finding",
    "Post an intermediate finding or observation to the collaboration's shared context. "
    "Other agents in the collaboration can see all findings via get_collaboration_status. "
    "Use this to share partial results, discoveries, or data that other agents may need.",
    {"collaboration_id": str, "finding": str}
)
async def post_finding(args: dict[str, Any]) -> dict[str, Any]:
    """
    Post a finding to a collaboration's shared context.

    Args:
        args: Dictionary with:
            - collaboration_id: UUID of the collaboration (required)
            - finding: The finding text to share (required)

    Returns:
        Tool response with updated findings list, or error.
    """
    collaboration_id = args.get("collaboration_id", "").strip()
    finding = args.get("finding", "").strip()

    if not collaboration_id:
        return {
            "content": [{"type": "text", "text": "Error: collaboration_id is required"}],
            "is_error": True,
        }

    if not finding:
        return {
            "content": [{"type": "text", "text": "Error: finding is required"}],
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

    try:
        url = f"{BACKEND_URL}/api/v1/agents/collaborations/{collaboration_id}/findings"
        headers = {
            "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
            "Content-Type": "application/json",
        }
        # Pass source_session_id so the backend can attribute to the right agent
        source_session_id = get_backend_session_id()
        payload = {"finding": finding}
        if source_session_id:
            payload["source_session_id"] = source_session_id

        logger.info(f"Posting finding to collaboration {collaboration_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                findings_count = len(data.get("findings", []))
                return {
                    "content": [{
                        "type": "text",
                        "text": (
                            f"Finding posted successfully. "
                            f"Total findings in collaboration: {findings_count}."
                        ),
                    }],
                }
            else:
                error = data.get("error", "Unknown error")
                return {
                    "content": [{"type": "text", "text": f"Failed to post finding: {error}"}],
                    "is_error": True,
                }
        elif response.status_code == 401:
            return {
                "content": [{"type": "text", "text": "Error: Authentication failed"}],
                "is_error": True,
            }
        else:
            logger.error(f"Post finding failed HTTP {response.status_code}: {response.text}")
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
        logger.error(f"Request error posting finding: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: Failed to connect to backend: {str(e)}"}],
            "is_error": True,
        }
    except Exception as e:
        logger.error(f"Unexpected error posting finding: {e}", exc_info=True)
        return {
            "content": [{"type": "text", "text": f"Error: Unexpected error: {str(e)}"}],
            "is_error": True,
        }
