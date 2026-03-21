"""
SDK Adapters Package

This package provides a unified interface for different AI SDK providers.
Each adapter converts SDK-specific messages to a common event format
that the backend can process uniformly.

Supported adapters:
- claude-code/*: Claude Code SDK (Anthropic, MiniMax)
- google-adk-wr/*: Google ADK Wrapper (OpenAI-compatible, Gemini, Vertex)
- opencode/*: OpenCode multi-provider agent (Anthropic, OpenAI, Google, Bedrock, Azure, etc.)
"""

from .base import (
    BaseSDKAdapter,
    SDKEvent,
    SDKEventType,
    SDKConfig,
    AdapterRegistry,
)
from .claude_code import ClaudeCodeAdapter
from .google_adk import GoogleADKAdapter
from .opencode_adapter import OpenCodeAdapter

__all__ = [
    "BaseSDKAdapter",
    "SDKEvent",
    "SDKEventType",
    "SDKConfig",
    "AdapterRegistry",
    "ClaudeCodeAdapter",
    "GoogleADKAdapter",
    "OpenCodeAdapter",
]
