"""
Knowledge Query Tool for Agent Environment.

This tool allows the agent to query the backend's integration knowledge base
for guidance on building integrations with various systems (ERP, CRM, etc.).
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
ENV_ID = os.getenv("ENV_ID")


@tool(
    "query_integration_knowledge",
    "Query the knowledge base for integration guidance (e.g., 'odoo api integration', 'salesforce rest api')",
    {"query": str}
)
async def query_integration_knowledge(args: dict[str, Any]) -> dict[str, Any]:
    """
    Query the backend knowledge base for integration guidance.

    This tool is only available in building mode and allows the agent to get
    expert guidance on how to build integrations with various systems.

    Args:
        args: Dictionary with 'query' key containing the search query

    Returns:
        Tool response with knowledge content or error message
    """
    query = args.get("query", "").strip()

    if not query:
        return {
            "content": [{
                "type": "text",
                "text": "Error: query parameter is required"
            }],
            "is_error": True
        }

    # Validate backend URL is configured
    if not BACKEND_URL:
        logger.error("BACKEND_URL not configured")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Backend URL not configured. Cannot query knowledge base."
            }],
            "is_error": True
        }

    # Validate auth token is configured
    if not AGENT_AUTH_TOKEN:
        logger.error("AGENT_AUTH_TOKEN not configured")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Authentication token not configured. Cannot query knowledge base."
            }],
            "is_error": True
        }

    # Validate environment ID is configured
    if not ENV_ID:
        logger.error("ENV_ID not configured")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Environment ID not configured. Cannot query knowledge base."
            }],
            "is_error": True
        }

    try:
        logger.info(f"Querying knowledge base from env {ENV_ID}: {query}")

        # Prepare request
        url = f"{BACKEND_URL}/api/v1/knowledge/query"
        headers = {
            "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
            "X-Agent-Env-Id": ENV_ID,
            "Content-Type": "application/json"
        }
        payload = {"query": query}

        logger.debug(f"Making request to {url} with env_id={ENV_ID}")

        # Make request to backend
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                content = data.get("content", "No content returned")
                source = data.get("source")

                result_text = f"Knowledge Query Result:\n\n{content}"
                if source:
                    result_text += f"\n\n(Source: {source})"

                logger.info(f"Knowledge query successful: {query}")

                return {
                    "content": [{
                        "type": "text",
                        "text": result_text
                    }]
                }
            elif response.status_code == 401:
                logger.error(f"Authentication failed when querying knowledge base for env {ENV_ID}")
                return {
                    "content": [{
                        "type": "text",
                        "text": "Error: Authentication failed. Invalid environment ID or authentication token."
                    }],
                    "is_error": True
                }
            else:
                logger.error(f"Knowledge query failed with status {response.status_code}: {response.text}")
                return {
                    "content": [{
                        "type": "text",
                        "text": f"Error: Knowledge query failed (HTTP {response.status_code}): {response.text}"
                    }],
                    "is_error": True
                }

    except httpx.TimeoutException:
        logger.error(f"Timeout querying knowledge base: {query}")
        return {
            "content": [{
                "type": "text",
                "text": "Error: Request to knowledge base timed out. Please try again."
            }],
            "is_error": True
        }
    except httpx.RequestError as e:
        logger.error(f"Request error querying knowledge base: {e}")
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Failed to connect to knowledge base: {str(e)}"
            }],
            "is_error": True
        }
    except Exception as e:
        logger.error(f"Unexpected error querying knowledge base: {e}", exc_info=True)
        return {
            "content": [{
                "type": "text",
                "text": f"Error: Unexpected error: {str(e)}"
            }],
            "is_error": True
        }
