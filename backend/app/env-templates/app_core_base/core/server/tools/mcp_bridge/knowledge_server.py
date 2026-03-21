"""
Knowledge MCP Bridge Server.

Exposes the query_integration_knowledge tool as an MCP stdio server so that
OpenCode agents can call it via the local MCP server config in opencode.json.

This server is launched by OpenCode as a child process when the environment
uses the opencode adapter. It makes HTTP calls to the backend, exactly as the
Claude Code adapter's knowledge_query.py does.

Run with:
    python3 /app/core/server/tools/mcp_bridge/knowledge_server.py
"""

import json
import logging
import os
import re
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config from environment
# ---------------------------------------------------------------------------

BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")
AGENT_AUTH_TOKEN = os.getenv("AGENT_AUTH_TOKEN", "")
ENV_ID = os.getenv("ENV_ID", "")

# UUID validation pattern
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_article_ids(raw: Any) -> list[str] | None:
    """
    Normalise article_ids to a list of UUID strings.

    Accepts None, single UUID string, CSV string, or list of UUID strings.
    Returns None if the result is empty or all IDs are invalid.
    """
    if not raw:
        return None

    if isinstance(raw, list):
        result: list[str] = []
        for item in raw:
            if isinstance(item, str):
                for part in item.split(","):
                    part = part.strip()
                    if part and _UUID_PATTERN.match(part):
                        result.append(part)
        return result or None

    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or re.match(r"^\[\s*\]$", raw):
            return None
        result = []
        for part in raw.split(","):
            part = part.strip()
            if part and _UUID_PATTERN.match(part):
                result.append(part)
        return result or None

    return None


def _format_article_list(articles: list[dict], query: str) -> str:
    lines = [f"Found {len(articles)} relevant articles:", ""]
    for i, article in enumerate(articles, 1):
        lines.append(f"{i}. [{article['id']}] {article['title']}")
        lines.append(f"   Description: {article['description']}")
        if article.get("tags"):
            lines.append(f"   Tags: {', '.join(article['tags'])}")
        if article.get("features"):
            lines.append(f"   Features: {', '.join(article['features'])}")
        lines.append(f"   Source: {article.get('source_name', 'Unknown')}")
        lines.append("")
    lines.append("To retrieve full article content, call this tool again with:")
    lines.append(
        f'query_integration_knowledge(query="{query}", article_ids="<article_id_1>,<article_id_2>")'
    )
    return "\n".join(lines)


def _format_full_articles(articles: list[dict]) -> str:
    lines = [f"Retrieved {len(articles)} article(s):", "=" * 80, ""]
    for article in articles:
        lines.append(f"# {article['title']}")
        lines.append("")
        lines.append(f"**Description:** {article['description']}")
        lines.append(f"**Source:** {article.get('source_name', 'Unknown')}")
        lines.append(f"**File:** {article.get('file_path', 'N/A')}")
        if article.get("tags"):
            lines.append(f"**Tags:** {', '.join(article['tags'])}")
        if article.get("features"):
            lines.append(f"**Features:** {', '.join(article['features'])}")
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append(article.get("content", "No content available"))
        lines.append("")
        lines.append("=" * 80)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("knowledge")


@mcp.tool()
def query_integration_knowledge(query: str, article_ids: str = "") -> str:
    """
    Query the knowledge base for integration guidance.

    Use in two steps:
    1. Discovery: call with only 'query' to get a list of relevant articles.
    2. Retrieval: call with 'query' and 'article_ids' (comma-separated UUIDs)
       to fetch full article content.

    Args:
        query: Search query string.
        article_ids: Optional comma-separated article UUIDs to retrieve in full.
    """
    if not query.strip():
        return "Error: query parameter is required"

    if not BACKEND_URL:
        return "Error: Backend URL not configured. Cannot query knowledge base."

    if not AGENT_AUTH_TOKEN:
        return "Error: Authentication token not configured. Cannot query knowledge base."

    if not ENV_ID:
        return "Error: Environment ID not configured. Cannot query knowledge base."

    normalized_ids = _normalize_article_ids(article_ids) if article_ids.strip() else None

    if article_ids.strip() and normalized_ids is None:
        return (
            f"Error: Invalid article_ids format. Expected UUID(s) in CSV format. "
            f"Received: {article_ids!r}"
        )

    payload: dict[str, Any] = {"query": query.strip()}
    if normalized_ids:
        payload["article_ids"] = normalized_ids

    headers = {
        "Authorization": f"Bearer {AGENT_AUTH_TOKEN}",
        "X-Agent-Env-Id": ENV_ID,
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{BACKEND_URL}/api/v1/knowledge/query",
                json=payload,
                headers=headers,
            )

        if resp.status_code == 200:
            data = resp.json()
            response_type = data.get("type")

            if response_type == "article_list":
                articles = data.get("articles", [])
                if not articles:
                    return "No relevant articles found in the knowledge base for this query."
                return _format_article_list(articles, query.strip())

            if response_type == "full_articles":
                articles = data.get("articles", [])
                if not articles:
                    return "No articles found with the specified IDs."
                return _format_full_articles(articles)

            return f"Unexpected response format from knowledge base: {response_type}"

        if resp.status_code == 401:
            return "Error: Authentication failed. Invalid environment ID or authentication token."

        return f"Error: Knowledge query failed (HTTP {resp.status_code}): {resp.text}"

    except httpx.TimeoutException:
        return "Error: Request to knowledge base timed out. Please try again."
    except httpx.RequestError as exc:
        return f"Error: Failed to connect to knowledge base: {exc}"
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected error in query_integration_knowledge: %s", exc, exc_info=True)
        return f"Error: Unexpected error: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    mcp.run(transport="stdio")
