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
    "Query the knowledge base for integration guidance. Use in two steps: 1) Discovery: query='search terms' returns article list, 2) Retrieval: query='search terms' + article_ids=['id1','id2'] returns full content",
    {"query": str, "article_ids": list[str]}
)
async def query_integration_knowledge(args: dict[str, Any]) -> dict[str, Any]:
    """
    Query the backend knowledge base for integration guidance.

    **Two-step process:**
    1. Discovery: Call with only 'query' to get a list of relevant articles
    2. Retrieval: Call with 'query' and 'article_ids' to get full content

    This tool is only available in building mode and allows the agent to get
    expert guidance on how to build integrations with various systems.

    Args:
        args: Dictionary with:
            - 'query' (str): Search query
            - 'article_ids' (list[str], optional): List of article IDs to retrieve

    Returns:
        Tool response with knowledge content or error message
    """
    query = args.get("query", "").strip()
    article_ids = args.get("article_ids")

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
        logger.info(f"Querying knowledge base from env {ENV_ID}: {query} (article_ids={article_ids})")

        # Prepare request
        url = f"{BACKEND_URL}/api/v1/knowledge/query"
        headers = {
            "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
            "X-Agent-Env-Id": ENV_ID,
            "Content-Type": "application/json"
        }

        # Build payload with optional article_ids
        payload = {"query": query}
        if article_ids:
            payload["article_ids"] = article_ids

        logger.debug(f"Making request to {url} with env_id={ENV_ID}")

        # Make request to backend
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                response_type = data.get("type")

                # Handle discovery response (article list)
                if response_type == "article_list":
                    articles = data.get("articles", [])

                    if not articles:
                        return {
                            "content": [{
                                "type": "text",
                                "text": "No relevant articles found in the knowledge base for this query."
                            }]
                        }

                    # Format article list for agent
                    result_lines = [
                        f"Found {len(articles)} relevant articles:",
                        ""
                    ]

                    for i, article in enumerate(articles, 1):
                        result_lines.append(f"{i}. [{article['id']}] {article['title']}")
                        result_lines.append(f"   Description: {article['description']}")
                        if article.get('tags'):
                            result_lines.append(f"   Tags: {', '.join(article['tags'])}")
                        if article.get('features'):
                            result_lines.append(f"   Features: {', '.join(article['features'])}")
                        result_lines.append(f"   Source: {article.get('source_name', 'Unknown')}")
                        result_lines.append("")

                    result_lines.append("To retrieve full article content, call this tool again with:")
                    result_lines.append(f"query_integration_knowledge({{\"query\": \"{query}\", \"article_ids\": [\"<article_id_1>\", \"<article_id_2>\"]}}")

                    result_text = "\n".join(result_lines)

                    logger.info(f"Discovery successful: found {len(articles)} articles")

                    return {
                        "content": [{
                            "type": "text",
                            "text": result_text
                        }]
                    }

                # Handle retrieval response (full articles)
                elif response_type == "full_articles":
                    articles = data.get("articles", [])

                    if not articles:
                        return {
                            "content": [{
                                "type": "text",
                                "text": "No articles found with the specified IDs."
                            }]
                        }

                    # Format full article content for agent
                    result_lines = [
                        f"Retrieved {len(articles)} article(s):",
                        "=" * 80,
                        ""
                    ]

                    for article in articles:
                        result_lines.append(f"# {article['title']}")
                        result_lines.append("")
                        result_lines.append(f"**Description:** {article['description']}")
                        result_lines.append(f"**Source:** {article.get('source_name', 'Unknown')}")
                        result_lines.append(f"**File:** {article.get('file_path', 'N/A')}")

                        if article.get('tags'):
                            result_lines.append(f"**Tags:** {', '.join(article['tags'])}")
                        if article.get('features'):
                            result_lines.append(f"**Features:** {', '.join(article['features'])}")

                        result_lines.append("")
                        result_lines.append("---")
                        result_lines.append("")
                        result_lines.append(article.get('content', 'No content available'))
                        result_lines.append("")
                        result_lines.append("=" * 80)
                        result_lines.append("")

                    result_text = "\n".join(result_lines)

                    logger.info(f"Retrieval successful: {len(articles)} articles")

                    return {
                        "content": [{
                            "type": "text",
                            "text": result_text
                        }]
                    }

                # Unknown response type
                else:
                    logger.warning(f"Unknown response type: {response_type}")
                    return {
                        "content": [{
                            "type": "text",
                            "text": f"Unexpected response format from knowledge base: {response_type}"
                        }],
                        "is_error": True
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
