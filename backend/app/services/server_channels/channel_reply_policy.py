"""Per-turn reply placement and durable status-notice addressing."""

import logging
from dataclasses import asdict

from app.models import ChannelThreadBinding, ServerChannel
from app.services.server_channels.adapters.base import (
    ChannelInboundMessage,
    ChannelReplyTarget,
    EffectiveChannelCapabilities,
)
from app.services.server_channels.adapters.email import build_reply_thread_key
from app.services.server_channels.adapters.registry import get_transport

logger = logging.getLogger(__name__)
_LOG_PREFIX = "[ChannelReplyPolicy]"


def legacy_binding_thread_key(
    binding: ChannelThreadBinding, channel: ServerChannel | None = None
) -> str | None:
    """The transport-facing thread key for ``binding``, or ``None``.

    **Total by construction**, and the single place a transport-facing thread
    key is derived from a binding.

    The binding-shaped sibling of
    ``channel_inbound_service._debug_channel_key``, and it exists rather than
    reusing it for one reason: that helper reads ``channel.id``, and there is
    no total reader for a *binding* attribute to reuse. The hazard is
    identical — ``binding.thread_key`` looks like a field read and is not.
    Every path into ``_deliver`` arrives after a ``db.commit()`` (the inbound
    pipeline commits between every progress notice; the event handlers commit
    while resolving the session), which expires the instance, so the read is a
    lazy reload and reloading a concurrently deleted binding raises
    ``ObjectDeletedError``.

    ``None`` means "this message cannot be addressed", and the caller declines
    to send rather than posting to a null thread — the same bargain
    ``_debug_channel_key`` strikes, for the same reason: a delivery aimed at
    nothing is worse than an honest, logged non-delivery.

    **``channel`` and the reply context (settled decision §2.7).** A polled
    transport's reply needs more than a thread id: an email answer carries
    ``In-Reply-To`` and ``References``, which name the *last* inbound message,
    not the thread root. ``send_message(channel, thread_key, text)`` has no
    room for them, so the polled key is a composite —
    ``"<root-message-id>|<last-message-id>"`` — built here and parsed by the
    transport. The **stored** ``binding.thread_key`` is untouched: it stays the
    bare root and remains the unique key everything binds by.

    ``binding.last_external_message_id`` is read **inside the same ``try``**,
    and that placement is the whole point rather than tidiness. It is the same
    expired-instance lazy reload ``thread_key`` is, so a read outside the guard
    would let a concurrently deleted binding raise out of a helper whose
    callers rely on it never raising — turning an honest declined delivery into
    a crash on the delivery path.

    ``channel`` is optional and defaults to "no reply context", which is
    exactly right for every webhook transport (Google Chat's key is already
    complete) and is what a caller that has no channel to hand gets. Only the
    transport shape decides: ``inbound_mode == "polled"``. The composite's
    format belongs to the polled transport that reads it back —
    ``adapters.email`` defines the separator, the builder and the parser in one
    place — so a second polled transport with a different reply shape needs
    its own branch here, not a different spelling of this one.
    """
    try:
        thread_key = str(binding.thread_key)
        # Same reload, same guard. See the docstring.
        last_external_message_id = binding.last_external_message_id
    except Exception:  # noqa: BLE001 — see the docstring
        logger.warning(
            "%s Could not read a thread key from the binding (instance expired "
            "and its row is gone?)",
            _LOG_PREFIX,
            exc_info=True,
        )
        return None

    if channel is None:
        return thread_key

    try:
        # ``channel.channel_type`` is a lazy reload too, and this helper may
        # not raise. A channel we cannot classify degrades to the bare thread
        # key rather than to ``None``: the key is still the right address, and
        # only the threading headers are lost. (``_deliver``'s own
        # ``get_adapter`` call raises on the same row a moment later and is
        # handled there — this is not the place to answer for it.)
        transport = get_transport(channel.channel_type)
    except Exception:  # noqa: BLE001 — degrade, never raise
        logger.warning(
            "%s Could not resolve the transport for a delivery; sending with "
            "the bare thread key",
            _LOG_PREFIX,
            exc_info=True,
        )
        return thread_key

    if transport.inbound_mode != "polled":
        return thread_key
    return build_reply_thread_key(thread_key, last_external_message_id)


class ChannelReplyPolicy:
    @staticmethod
    def resolve(
        inbound: ChannelInboundMessage,
        effective_caps: EffectiveChannelCapabilities,
        binding: ChannelThreadBinding | None = None,
        channel: ServerChannel | None = None,
        *,
        reply_here: bool = False,
    ) -> ChannelReplyTarget | None:
        conversation = inbound.conversation_key or inbound.thread_key
        if not conversation:
            return None
        if not effective_caps.supports_conversations:
            if inbound.conversation_key:
                return ChannelReplyTarget(
                    conversation_key=inbound.conversation_key,
                    asker_external_id=inbound.external_user_id
                    if inbound.conversation_kind == "group"
                    else None,
                )
            legacy = (
                legacy_binding_thread_key(binding, channel)
                if binding is not None
                else inbound.thread_key
            )
            return ChannelReplyTarget(
                conversation_key=conversation,
                thread_key=inbound.thread_key,
                transport_hint=legacy,
                binding_id=str(binding.id) if binding is not None else None,
            )
        hints = inbound.conversation_hints
        here = reply_here and effective_caps.shape.is_group
        mode = "conversation_post"
        thread = None
        quote = None
        stamp = hints.get("message_last_update_time")
        if effective_caps.can_reply_in_thread and inbound.thread_key and not here:
            mode, thread = "thread_reply", inbound.thread_key
        elif effective_caps.supports_quote_reply and inbound.external_message_id:
            # Google cannot quote a thread reply into a new top-level post.
            if not hints.get("quote_requires_same_thread", False) or not here:
                mode, quote = "quote_reply", inbound.external_message_id
        return ChannelReplyTarget(
            conversation_key=conversation,
            thread_key=thread,
            reply_to_message_id=quote,
            mode=mode,
            reply_to_last_update_time=stamp,
            asker_external_id=inbound.external_user_id
            if effective_caps.shape.is_group
            else None,
        )

    @staticmethod
    def remember_target(
        binding: ChannelThreadBinding, target: ChannelReplyTarget
    ) -> None:
        saved = getattr(binding, "reply_target", None)
        target_data = asdict(target)
        placement_keys = (
            "conversation_key",
            "thread_key",
            "reply_to_message_id",
            "mode",
        )
        if (
            saved
            and getattr(binding, "status_message_id", None)
            and any(saved.get(key) != target_data.get(key) for key in placement_keys)
        ):
            # A failed earlier turn can leave its notice behind. Reusing it
            # would put this answer at the old turn's address. This synchronous
            # state transition cannot delete remotely, so leave it unmodified.
            binding.status_message_id = None
            logger.warning("Released stale channel notice after reply target changed")
        binding.reply_target = target_data
        binding.last_reply_mode = target.mode

    @staticmethod
    def resolve_binding(
        binding: ChannelThreadBinding, channel: ServerChannel | None = None
    ) -> ChannelReplyTarget | None:
        try:
            saved = getattr(binding, "reply_target", None)
            if saved and not saved.get("transport_hint"):
                return ChannelReplyTarget(**saved)
            # Legacy polled targets deliberately resolve the latest inbound id
            # at delivery time, exactly as the pre-conversation email path did.
            # A notice can have been prepared before ingestion advanced it.
            legacy = legacy_binding_thread_key(binding, channel)
            if legacy is None:
                return None
            return ChannelReplyTarget(
                conversation_key=getattr(binding, "conversation_key", None)
                or binding.thread_key,
                thread_key=binding.thread_key,
                transport_hint=legacy,
                binding_id=str(binding.id) if getattr(binding, "id", None) else None,
            )
        except Exception:
            logger.warning(
                "Cannot address deleted or expired channel binding", exc_info=True
            )
            return None
