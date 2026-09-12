"""Resolve transport declarations against the particular conversation."""

import asyncio
from dataclasses import replace

from app.core.config import settings
from app.models import ServerChannel
from app.services.server_channels.adapters.base import (
    ChannelAdapter,
    ChannelInboundMessage,
    EffectiveChannelCapabilities,
)


class ChannelConversationResolver:
    @staticmethod
    def resolve(
        adapter: ChannelAdapter, inbound: ChannelInboundMessage
    ) -> EffectiveChannelCapabilities:
        try:
            caps = adapter.capabilities
            shape = adapter.interpret_conversation_hints(inbound.conversation_hints)
            enabled = caps.supports_conversations and shape.is_known
            return EffectiveChannelCapabilities(
                shape=shape,
                supports_conversations=enabled,
                supports_threads=enabled
                and caps.supports_threads
                and shape.is_threaded,
                supports_thread_creation=enabled
                and caps.supports_thread_creation
                and shape.can_start_thread,
                supports_quote_reply=enabled and caps.supports_quote_reply,
                supports_inbound_quote=enabled and caps.supports_inbound_quote,
                supports_message_fetch=enabled and caps.supports_message_fetch,
                supports_thread_history=enabled
                and caps.supports_thread_history
                and shape.is_threaded,
                history_requires_membership=caps.history_requires_membership,
                can_reply_in_thread=enabled
                and caps.supports_threads
                and shape.can_reply_in_thread,
                can_start_thread=enabled
                and caps.supports_thread_creation
                and shape.can_start_thread,
            )
        except Exception:
            return EffectiveChannelCapabilities()

    @staticmethod
    async def resolve_for_channel(
        adapter: ChannelAdapter, channel: ServerChannel, inbound: ChannelInboundMessage
    ) -> EffectiveChannelCapabilities:
        effective = ChannelConversationResolver.resolve(adapter, inbound)
        if not (effective.supports_message_fetch or effective.supports_thread_history):
            return effective
        try:
            reads = await asyncio.wait_for(
                adapter.resolve_read_capabilities(channel, inbound.conversation_key),
                timeout=settings.CHANNEL_CONTEXT_FETCH_TIMEOUT_SECONDS,
            )
        except Exception:
            reads = {}
        return replace(
            effective,
            supports_message_fetch=effective.supports_message_fetch
            and reads.get("supports_message_fetch", False),
            supports_thread_history=effective.supports_thread_history
            and reads.get("supports_thread_history", False),
        )

    @staticmethod
    def scope_key(
        adapter: ChannelAdapter, inbound: ChannelInboundMessage
    ) -> str | None:
        effective = ChannelConversationResolver.resolve(adapter, inbound)
        if effective.supports_conversations and not effective.shape.is_threaded:
            return inbound.conversation_key or inbound.thread_key
        return inbound.thread_key or inbound.conversation_key
