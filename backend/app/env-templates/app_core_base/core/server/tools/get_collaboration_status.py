"""
Get Collaboration Status Tool for Agent Environment.

Allows any participant agent to check the current status of a collaboration,
see which subtasks have completed, and read findings from other agents.
"""
import os
import logging
from typing import Any
import httpx

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")


@tool(
    "get_collaboration_status",
    "Check the current status of a multi-agent collaboration. "
    "Returns overall status, individual subtask statuses, and any findings "
    "posted by other agents. Use this to monitor progress and read shared results.",
    {"collaboration_id": str}
)
async def get_collaboration_status(args: dict[str, Any]) -> dict[str, Any]:
    """
    Get the status of a collaboration.

    Args:
        args: Dictionary with:
            - collaboration_id: UUID of the collaboration (required)

    Returns:
        Tool response with collaboration status, subtask details, and findings.
    """
    collaboration_id = args.get("collaboration_id", "").strip()

    if not collaboration_id:
        return {
            "content": [{"type": "text", "text": "Error: collaboration_id is required"}],
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
        url = f"{BACKEND_URL}/api/v1/agents/collaborations/{collaboration_id}/status"
        headers = {"Authorization": f"Bearer {AGENT_AUTH_TOKEN}"}

        logger.info(f"Fetching collaboration status for {collaboration_id}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)

        if response.status_code == 200:
            data = response.json()

            # Format a readable summary
            status = data.get("status", "unknown")
            title = data.get("title", "")
            description = data.get("description", "")
            subtasks = data.get("subtasks", [])
            findings = data.get("shared_context", {}).get("findings", [])

            lines = [
                f"## Collaboration: {title}",
                f"**Status**: {status}",
            ]

            if description:
                lines.append(f"**Description**: {description}")

            lines.append(f"\n**Subtasks** ({len(subtasks)} total):")
            for st in subtasks:
                agent_name = st.get("target_agent_name") or st.get("target_agent_id", "Unknown")
                st_status = st.get("status", "unknown")
                summary = st.get("result_summary", "")
                summary_str = f" — {summary}" if summary else ""
                lines.append(f"  - [{st_status.upper()}] {agent_name}{summary_str}")

            if findings:
                lines.append(f"\n**Shared Findings** ({len(findings)} total):")
                for finding in findings:
                    lines.append(f"  - {finding}")
            else:
                lines.append("\n**Shared Findings**: None yet")

            text = "\n".join(lines)
            return {"content": [{"type": "text", "text": text}]}

        elif response.status_code == 404:
            return {
                "content": [{"type": "text", "text": f"Collaboration {collaboration_id} not found"}],
                "is_error": True,
            }
        elif response.status_code == 401:
            return {
                "content": [{"type": "text", "text": "Error: Authentication failed"}],
                "is_error": True,
            }
        else:
            logger.error(f"Get collaboration status failed HTTP {response.status_code}: {response.text}")
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
        logger.error(f"Request error getting collaboration status: {e}")
        return {
            "content": [{"type": "text", "text": f"Error: Failed to connect to backend: {str(e)}"}],
            "is_error": True,
        }
    except Exception as e:
        logger.error(f"Unexpected error getting collaboration status: {e}", exc_info=True)
        return {
            "content": [{"type": "text", "text": f"Error: Unexpected error: {str(e)}"}],
            "is_error": True,
        }
