"""Conversation shape, placement, quote addressing and bounded reads without I/O."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.server_channels.adapters.base import (
    ChannelCapabilityUnsupported,
    ChannelConfigError,
    ChannelReplyTarget,
    ChannelSendError,
)
from app.services.server_channels.adapters.google_chat import GoogleChatAdapter
from app.services.server_channels.channel_conversation_resolver import (
    ChannelConversationResolver,
)
from app.services.server_channels.channel_directives import strip_reply_here
from app.services.server_channels.channel_reply_policy import ChannelReplyPolicy


def event(state="THREADED_MESSAGES", kind="SPACE", reply=False):
    return {
        "type": "MESSAGE",
        "space": {
            "name": "spaces/AAA",
            "spaceType": kind,
            "spaceThreadingState": state,
        },
        "message": {
            "name": "spaces/AAA/messages/now",
            "text": "Question",
            "createTime": "2026-01-01T00:00:00Z",
            "thread": {"name": "spaces/AAA/threads/BBB"},
            "threadReply": reply,
            "sender": {
                "type": "HUMAN",
                "name": "users/123",
                "email": "ann@example.org",
            },
        },
    }


@pytest.mark.parametrize(
    "text,expected,matched",
    [
        ("Question\nREPLY HERE!  ", "Question", True),
        ("Question? Reply here.", "Question?", True),
        ("Can you reply here or in DM?", "Can you reply here or in DM?", False),
        ("Please reply here", "Please reply here", False),
    ],
)
def test_anchored_directive(text, expected, matched):
    assert strip_reply_here(text) == (expected, matched)


def test_space_shapes_scope_keys_and_reply_ladder():
    adapter = GoogleChatAdapter()
    inbound = adapter._parse_event(event())
    caps = ChannelConversationResolver.resolve(adapter, inbound)
    assert ChannelConversationResolver.scope_key(adapter, inbound) == inbound.thread_key
    assert ChannelReplyPolicy.resolve(inbound, caps).mode == "thread_reply"
    target = ChannelReplyPolicy.resolve(inbound, caps, reply_here=True)
    assert target.mode == "quote_reply"
    assert target.reply_to_last_update_time == "2026-01-01T00:00:00Z"
    assert target.asker_external_id == "users/123"
    flat = adapter._parse_event(event("UNTHREADED_MESSAGES"))
    assert ChannelConversationResolver.scope_key(adapter, flat) == "spaces/AAA"
    assert (
        ChannelReplyPolicy.resolve(
            flat, ChannelConversationResolver.resolve(adapter, flat)
        ).mode
        == "quote_reply"
    )
    reply = adapter._parse_event(event(reply=True))
    assert (
        ChannelReplyPolicy.resolve(reply, caps, reply_here=True).mode
        == "conversation_post"
    )
    dm = adapter._parse_event(event(None, "DIRECT_MESSAGE"))
    assert (
        ChannelReplyPolicy.resolve(
            dm, ChannelConversationResolver.resolve(adapter, dm), reply_here=True
        ).mode
        == "thread_reply"
    )
    unknown = adapter._parse_event(event(None))
    assert (
        ChannelReplyPolicy.resolve(
            unknown, ChannelConversationResolver.resolve(adapter, unknown)
        ).mode
        == "conversation_post"
    )


@pytest.mark.parametrize(
    "cfg",
    [
        {"reply_here_phrase": " /stop"},
        {"reply_here_phrase": ""},
        {"reply_here_phrase": "two\nlines"},
        {"thread_backfill_enabled": "false"},
    ],
)
def test_config_rejects_misleading_directives_and_non_boolean_switches(cfg):
    with pytest.raises(ChannelConfigError):
        GoogleChatAdapter().validate_config({"project_number": "123", **cfg})


@pytest.mark.anyio
async def test_targets_generate_quote_thread_and_flat_payloads_and_preserve_legacy():
    adapter = GoogleChatAdapter()
    channel = SimpleNamespace(id="channel")
    targets = [
        ChannelReplyTarget(
            "spaces/AAA",
            "spaces/AAA/threads/BBB",
            mode="thread_reply",
            asker_external_id="users/123",
        ),
        ChannelReplyTarget(
            "spaces/AAA",
            reply_to_message_id="spaces/AAA/messages/now",
            mode="quote_reply",
            reply_to_last_update_time="2026-01-01T00:00:00Z",
        ),
        ChannelReplyTarget("spaces/AAA"),
        ChannelReplyTarget(
            "spaces/AAA/threads/BBB", transport_hint="spaces/AAA/threads/BBB"
        ),
    ]
    with (
        patch.object(adapter, "_mint_access_token", AsyncMock(return_value="token")),
        patch.object(adapter, "_load_credentials", return_value={}),
        patch.object(
            adapter, "_request_with_retries", AsyncMock(return_value={"name": "sent"})
        ) as request,
        patch(
            "app.services.server_channels.adapters.google_chat.assert_url_allowed",
            side_effect=lambda url: url,
        ),
    ):
        for target in targets:
            assert await adapter.send_message(channel, target, "**answer**") == "sent"
        calls = request.await_args_list
        assert calls[0].kwargs["payload"] == {
            "text": "<users/123> *answer*",
            "thread": {"name": "spaces/AAA/threads/BBB"},
        }
        assert (
            calls[1].kwargs["payload"]["quotedMessageMetadata"]["lastUpdateTime"]
            == "2026-01-01T00:00:00Z"
        )
        assert calls[2].kwargs["payload"] == {"text": "*answer*"}
        assert calls[2].kwargs["params"] == {}
        assert calls[3].kwargs["payload"]["thread"]["name"] == "spaces/AAA/threads/BBB"


@pytest.mark.anyio
async def test_quote_rejection_falls_back_without_losing_answer_or_asker():
    adapter = GoogleChatAdapter()
    response = httpx.Response(
        400, request=httpx.Request("POST", "https://chat.googleapis.com")
    )
    error = ChannelSendError("quote changed")
    error.__cause__ = httpx.HTTPStatusError(
        "invalid quote", request=response.request, response=response
    )
    target = ChannelReplyTarget(
        "spaces/AAA",
        mode="quote_reply",
        reply_to_message_id="spaces/AAA/messages/now",
        reply_to_last_update_time="2026-01-01T00:00:00Z",
        asker_external_id="users/123",
    )
    with (
        patch.object(adapter, "_mint_access_token", AsyncMock(return_value="token")),
        patch.object(adapter, "_load_credentials", return_value={}),
        patch.object(
            adapter,
            "_request_with_retries",
            AsyncMock(side_effect=[error, {"name": "sent"}]),
        ) as request,
        patch(
            "app.services.server_channels.adapters.google_chat.assert_url_allowed",
            side_effect=lambda url: url,
        ),
    ):
        assert (
            await adapter.send_message(SimpleNamespace(id="channel"), target, "answer")
            == "sent"
        )
        assert request.await_args.kwargs["payload"] == {"text": "<users/123> answer"}


def test_mentions_fit_every_chunk_and_status_patches():
    adapter = GoogleChatAdapter()
    target = ChannelReplyTarget("spaces/AAA", asker_external_id="users/123")
    chunks = adapter._addressed_chunks("word " * 3000, target)
    assert len(chunks) > 1
    assert all(
        chunk.startswith("<users/123> ") and len(chunk) <= 4096 for chunk in chunks
    )
    assert (
        adapter.build_sync_response("**answer**", target)["text"]
        == "<users/123> *answer*"
    )


@pytest.mark.anyio
async def test_history_paginates_newest_first_with_stable_filter_and_limit():
    adapter = GoogleChatAdapter()
    channel = SimpleNamespace(config={"project_number": "123"})

    def msg(name):
        return {
            "name": f"spaces/AAA/messages/{name}",
            "text": name,
            "sender": {"name": "users/456", "type": "BOT"},
            "createTime": "2025-12-01T00:00:00Z",
        }

    with patch.object(
        adapter,
        "_read_resource",
        AsyncMock(
            side_effect=[
                {"messages": [msg("new")], "nextPageToken": "page2"},
                {"messages": [msg("old"), msg("excluded")]},
            ]
        ),
    ) as read:
        messages = await adapter.fetch_thread_history(
            channel, "spaces/AAA/threads/BBB", 2
        )
    assert [m.text for m in messages] == ["new", "old"]
    assert not messages[0].is_platform_authored
    assert read.await_args.args[2] == {
        "pageSize": 2,
        "orderBy": "createTime DESC",
        "filter": "thread.name = spaces/AAA/threads/BBB",
        "pageToken": "page2",
    }


@pytest.mark.anyio
async def test_failed_read_probe_is_cached_and_runtime_caps_fail_closed():
    adapter = GoogleChatAdapter()
    channel = SimpleNamespace(id="failed-probe-test")
    inbound = adapter._parse_event(event())
    adapter.invalidate_token_cache(channel.id)
    with patch.object(
        adapter, "_read_resource", AsyncMock(side_effect=TimeoutError)
    ) as read:
        for _ in range(2):
            effective = await ChannelConversationResolver.resolve_for_channel(
                adapter, channel, inbound
            )
            assert effective.can_reply_in_thread
            assert not effective.supports_message_fetch
            assert not effective.supports_thread_history
    assert read.await_count == 1
    adapter.invalidate_token_cache(channel.id)


@pytest.mark.anyio
async def test_read_probe_total_timeout_preserves_replies():
    adapter = GoogleChatAdapter()

    async def pending_probe(*_args):
        await asyncio.Event().wait()

    with (
        patch.object(adapter, "resolve_read_capabilities", pending_probe),
        patch(
            "app.services.server_channels.channel_conversation_resolver.settings.CHANNEL_CONTEXT_FETCH_TIMEOUT_SECONDS",
            0.001,
        ),
    ):
        effective = await ChannelConversationResolver.resolve_for_channel(
            adapter, SimpleNamespace(id="probe-timeout"), adapter._parse_event(event())
        )
    assert effective.can_reply_in_thread
    assert not effective.supports_message_fetch
    assert not effective.supports_thread_history


@pytest.mark.parametrize("quote_space,expected", [("AAA", True), ("other", False)])
def test_quote_references_stay_in_inbound_and_fetched_conversation(
    quote_space, expected
):
    adapter = GoogleChatAdapter()
    payload = event()
    quote_id = f"spaces/{quote_space}/messages/quote"
    payload["message"]["quotedMessageMetadata"] = {"name": quote_id}
    assert adapter._parse_event(payload).quoted_message_id == (
        quote_id if expected else None
    )
    assert adapter._message_ref(
        payload["message"], SimpleNamespace(id="quote-boundary")
    ).quoted_message_id == (quote_id if expected else None)


@pytest.mark.anyio
async def test_fetch_rejects_response_for_different_message():
    adapter = GoogleChatAdapter()
    with patch.object(
        adapter, "_read_resource", AsyncMock(return_value=event()["message"])
    ):
        with pytest.raises(
            ChannelCapabilityUnsupported, match="message_reference_mismatch"
        ):
            await adapter.fetch_message(
                SimpleNamespace(id="quote-boundary"), "spaces/AAA/messages/requested"
            )


def test_email_reply_headers_follow_latest_inbound_after_saved_notice_target():
    binding = SimpleNamespace(
        thread_key="<root@example.org>",
        last_external_message_id="<new@example.org>",
        reply_target={
            "conversation_key": "<root@example.org>",
            "transport_hint": "<root@example.org>|<old@example.org>",
        },
    )
    target = ChannelReplyPolicy.resolve_binding(
        binding, SimpleNamespace(channel_type="email")
    )
    assert target.legacy_thread_key == "<root@example.org>|<new@example.org>"


def test_new_placement_cannot_patch_notice_at_previous_target():
    binding = SimpleNamespace(
        reply_target={
            "conversation_key": "spaces/AAA",
            "thread_key": "spaces/AAA/threads/BBB",
            "mode": "thread_reply",
        },
        status_message_id="old-notice",
        last_reply_mode="thread_reply",
    )
    target = ChannelReplyTarget("spaces/AAA", mode="conversation_post")
    ChannelReplyPolicy.remember_target(binding, target)
    assert binding.status_message_id is None
    assert binding.last_reply_mode == "conversation_post"
    assert ChannelReplyPolicy.resolve_binding(binding) == target


def test_legacy_payload_without_space_retains_original_sync_address():
    adapter = GoogleChatAdapter()
    payload = event()
    payload.pop("space")
    inbound = adapter._parse_event(payload)
    assert inbound.conversation_key is None
    target = ChannelReplyPolicy.resolve(
        inbound, ChannelConversationResolver.resolve(adapter, inbound)
    )
    assert adapter.build_sync_response("answer", target) == {
        "text": "answer",
        "thread": {"name": inbound.thread_key},
    }


@pytest.mark.anyio
async def test_one_space_probe_failure_does_not_suppress_other_space():
    adapter = GoogleChatAdapter()
    channel = SimpleNamespace(id="independent-spaces")
    adapter.invalidate_token_cache(channel.id)
    with patch.object(
        adapter, "_read_resource", AsyncMock(side_effect=TimeoutError)
    ) as read:
        await adapter.resolve_read_capabilities(channel, "spaces/AAA")
        await adapter.resolve_read_capabilities(channel, "spaces/BBB")
        await adapter.resolve_read_capabilities(channel, "spaces/AAA")
    assert read.await_count == 2
    adapter.invalidate_token_cache(channel.id)
