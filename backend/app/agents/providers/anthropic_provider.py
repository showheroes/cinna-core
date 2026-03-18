"""
Anthropic Provider - direct HTTP calls to Anthropic Messages API.

Makes direct httpx calls to https://api.anthropic.com/v1/messages.
No Anthropic SDK dependency — only httpx (already a project dependency).

Intended for per-user personal API key usage, NOT system-level credentials.
All errors raise ProviderError with recoverable=False because if the user
has chosen "anthropic" as their AI functions provider, we should not fall
back to system providers on failure.
"""
import logging
from typing import Optional

import httpx

from .base import BaseAIProvider, ProviderError, ProviderResponse

logger = logging.getLogger(__name__)


class AnthropicProvider(BaseAIProvider):
    """
    Anthropic provider using direct HTTP calls to the Messages API.

    Accepts an explicit api_key (does NOT read from environment variables).
    Intended for per-user personal API key routing.

    Default model: claude-haiku-4-5 (fast, cheap)
    """

    PROVIDER_NAME = "anthropic"
    DEFAULT_MODEL = "claude-haiku-4-5"
    API_URL = "https://api.anthropic.com/v1/messages"
    API_VERSION = "2023-06-01"
    REQUEST_TIMEOUT = 30.0

    def __init__(self, api_key: str):
        """
        Initialize the Anthropic provider.

        Args:
            api_key: Anthropic API key (required). Must be provided explicitly —
                     this provider does not read from environment variables.
        """
        self._api_key = api_key

    def is_available(self) -> bool:
        """Check if the provider is available (API key is set)."""
        return bool(self._api_key)

    def generate_content(self, prompt: str, model: Optional[str] = None) -> ProviderResponse:
        """
        Generate content by calling the Anthropic Messages API.

        Args:
            prompt: The prompt to send
            model: Optional model override (default: claude-haiku-4-5)

        Returns:
            ProviderResponse with generated text

        Raises:
            ProviderError: On any failure (recoverable=False — no cascade intended)
        """
        if not self.is_available():
            raise ProviderError(
                "Anthropic API key not provided",
                self.PROVIDER_NAME,
                recoverable=False,
            )

        model_name = model or self.DEFAULT_MODEL

        try:
            response = httpx.post(
                self.API_URL,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": self.API_VERSION,
                    "content-type": "application/json",
                },
                json={
                    "model": model_name,
                    "max_tokens": 1024,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=self.REQUEST_TIMEOUT,
            )

            if response.status_code != 200:
                error_body = response.text[:300]
                logger.warning(
                    f"Anthropic API returned {response.status_code}: {error_body}"
                )
                raise ProviderError(
                    f"Anthropic API returned HTTP {response.status_code}: {error_body}",
                    self.PROVIDER_NAME,
                    recoverable=False,
                )

            data = response.json()
            text = data["content"][0]["text"].strip()

            logger.debug(
                f"Anthropic generated {len(text)} chars using {model_name}"
            )

            return ProviderResponse(
                text=text,
                provider_name=self.PROVIDER_NAME,
                model=model_name,
            )

        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError(
                "Anthropic API request timed out",
                self.PROVIDER_NAME,
                recoverable=False,
            )
        except Exception as e:
            raise ProviderError(
                f"Anthropic API call failed: {e}",
                self.PROVIDER_NAME,
                recoverable=False,
            )
