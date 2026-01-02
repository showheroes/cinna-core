"""
Agent Handover Tool for Agent Environment.

This tool allows a conversational agent to hand over to another agent by creating
a new session for the target agent and sending a handover message.
"""
import os
import json
import logging
from typing import Any
import httpx

from claude_agent_sdk import tool

logger = logging.getLogger(__name__)

# Environment variables for backend connection
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN")
ENV_ID = os.getenv("ENV_ID")
AGENT_ID = os.getenv("AGENT_ID")

# Path to handover config file in workspace
HANDOVER_CONFIG_PATH = "/app/workspace/docs/agent_handover_config.json"


def load_handover_config() -> dict[str, Any]:
    """Load handover configuration from JSON file."""
    try:
        if os.path.exists(HANDOVER_CONFIG_PATH):
            with open(HANDOVER_CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load handover config: {e}")

    return {"handovers": []}


@tool(
    "agent_handover",
    "Hand over to another agent by creating a new session and sending a message. Use this when you need to delegate work to a specialized agent.",
    {"target_agent_id": str, "target_agent_name": str, "handover_message": str}
)
async def agent_handover(args: dict[str, Any]) -> dict[str, Any]:
    """
    Hand over to another agent by creating a new session and sending a handover message.

    This tool is only available in conversation mode and allows agents to trigger
    other agents when specific conditions are met.

    Args:
        args: Dictionary with:
            - target_agent_id: UUID of the target agent
            - target_agent_name: Name of the target agent
            - handover_message: Message to send to the target agent

    Returns:
        Tool response with success status or error message
    """
    target_agent_id = args.get("target_agent_id", "").strip()
    target_agent_name = args.get("target_agent_name", "").strip()
    handover_message = args.get("handover_message", "").strip()

    # Validate parameters
    if not target_agent_id:
        return {
            "content": [{
                "type": "text",
                "text": "Error: target_agent_id parameter is required"
            }],
            "is_error": True
        }

    if not target_agent_name:
        return {
            "content": [{
                "type": "text",
                "text": "Error: target_agent_name parameter is required"
            }],
            "is_error": True
        }

    if not handover_message:
        return {
            "content": [{
                "type": "text",
                "text": "Error: handover_message parameter is required"
            }],
            "is_error": True
        }

    # Load handover config and verify this handover is configured
    config = load_handover_config()
    handovers = config.get("handovers", [])

    # Check if this agent ID is in the configured handovers
    configured_agent_ids = [h.get("id") for h in handovers]
    if target_agent_id not in configured_agent_ids:
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Handover to agent '{target_agent_name}' ({target_agent_id}) is not configured. Available handovers: {', '.join([h.get('name', 'Unknown') for h in handovers])}"
            }],
            "is_error": True
        }

    # Validate backend configuration
    if not BACKEND_URL:
        logger.error("BACKEND_URL not configured")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Backend URL not configured. Cannot execute handover."
            }],
            "is_error": True
        }

    if not AGENT_AUTH_TOKEN:
        logger.error("AGENT_AUTH_TOKEN not configured")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Authentication token not configured. Cannot execute handover."
            }],
            "is_error": True
        }

    try:
        logger.info(f"Executing handover from agent {AGENT_ID} to agent {target_agent_id} ({target_agent_name})")

        # Prepare request to create session and send message
        url = f"{BACKEND_URL}/api/v1/agents/handover/execute"
        headers = {
            "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = {
            "target_agent_id": target_agent_id,
            "target_agent_name": target_agent_name,
            "handover_message": handover_message
        }

        logger.debug(f"Making handover request to {url}")

        # Make request to backend
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                success = data.get("success", False)
                session_id = data.get("session_id")
                error = data.get("error")

                if success and session_id:
                    logger.info(f"Handover successful: Created session {session_id} for agent {target_agent_id}")

                    # Now send the handover message to the new session
                    # We'll use the messages API endpoint
                    message_url = f"{BACKEND_URL}/api/v1/sessions/{session_id}/messages"
                    message_payload = {
                        "content": handover_message
                    }

                    message_response = await client.post(
                        message_url,
                        json=message_payload,
                        headers=headers
                    )

                    if message_response.status_code in [200, 201]:
                        return {
                            "content": [{
                                "type": "text",
                                "text": f"Successfully handed over to agent '{target_agent_name}'. A new session (ID: {session_id}) has been created and your message has been sent."
                            }]
                        }
                    else:
                        logger.error(f"Failed to send message to new session: {message_response.status_code} {message_response.text}")
                        return {
                            "content": [{
                                "type": "text",
                                "text": f"Session created but failed to send message: {message_response.text}"
                            }],
                            "is_error": True
                        }
                else:
                    logger.error(f"Handover failed: {error}")
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Handover failed: {error}"
                        }],
                        "is_error": True
                    }
            elif response.status_code == 401:
                logger.error("Authentication failed when executing handover")
                return {
                    "content": [{
                        "type": "text",
                        "text": "Error: Authentication failed. Invalid authentication token."
                    }],
                    "is_error": True
                }
            else:
                logger.error(f"Handover request failed with status {response.status_code}: {response.text}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error: Handover request failed (HTTP {response.status_code}): {response.text}"
                    }],
                    "is_error": True
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout executing handover to {target_agent_name}")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Handover request timed out. Please try again."
            }],
            "is_error": True
        }
    except httpx.RequestError as e:
        logger.error(f"Request error executing handover: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Failed to connect to backend: {str(e)}"
            }],
            "is_error": True
        }
    except Exception as e:
        logger.error(f"Unexpected error executing handover: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Unexpected error: {str(e)}"
            }],
            "is_error": True
        }
