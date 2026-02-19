"""
Injectable connector for agent-env HTTP streaming communication.

Follows the same DI pattern as smtp_connector / imap_connector:
- Module-level instance used by message_service
- Tests patch the module-level instance with a stub
"""
import json
import logging
from typing import AsyncIterator

import httpx

logger = logging.getLogger(__name__)


class AgentEnvConnector:
    """Wraps httpx for agent-env HTTP communication. Injectable for testing."""

    async def stream_chat(
        self,
        base_url: str,
        auth_headers: dict,
        payload: dict,
    ) -> AsyncIterator[dict]:
        """Stream chat events from agent-env /chat/stream endpoint.

        Yields parsed SSE event dicts. Errors are yielded as
        {"type": "error", "content": ..., "error_type": ...} rather than raised,
        matching the existing message_service contract.
        """
        headers = {**auth_headers, "Content-Type": "application/json"}

        logger.info(
            f"Sending message to {base_url}/chat/stream "
            f"(mode={payload.get('mode')}, external_session_id={payload.get('session_id')})"
        )

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream(
                    "POST",
                    f"{base_url}/chat/stream",
                    json=payload,
                    headers=headers,
                ) as response:
                    response.raise_for_status()

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            try:
                                yield json.loads(data_str)
                            except json.JSONDecodeError as e:
                                logger.error(f"Failed to parse SSE event: {data_str}, error: {e}")
                                continue

        except httpx.HTTPStatusError as e:
            try:
                await e.response.aread()
                error_text = e.response.text
            except Exception:
                error_text = "(unable to read response)"
            logger.error(f"HTTP error from environment: {e.response.status_code} - {error_text}")
            yield {
                "type": "error",
                "content": f"Environment returned error: {e.response.status_code}",
                "error_type": "HTTPError",
            }
        except httpx.RequestError as e:
            logger.error(f"Request error to environment: {e}")
            yield {
                "type": "error",
                "content": f"Failed to connect to environment: {str(e)}",
                "error_type": "ConnectionError",
            }
        except Exception as e:
            logger.error(f"Unexpected error streaming from environment: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"Unexpected error: {str(e)}",
                "error_type": type(e).__name__,
            }


# Module-level default instance (patched in tests)
agent_env_connector = AgentEnvConnector()
