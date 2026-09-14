"""``GoogleChatAdapter`` keeps the quoted message's snapshot — bounded, and never authority.

Quote-aware channel routing, Phase 1
(``docs/plans/channel_quote_aware_routing_plan.md`` §5.1, §7). Google sends
``message.quotedMessageMetadata.quotedMessageSnapshot`` with the quoted
message's ``text`` and ``sender`` (a display *name*, not a User). The adapter
now keeps both on ``ChannelInboundMessage`` so the router and the agent can see
what a short follow-up ("can u?") refers to.

What is pinned here, and why each is a separate property:

- **Absent means today.** No snapshot — or no metadata at all — must parse to
  exactly what it parsed to before the feature, field for field.
- **The same-space rule is inherited.** A snapshot is read only beside an id
  ``_same_space_quote`` accepted; a cross-space or malformed id carries no
  snapshot either, and a ``FORWARD`` quote carries none.
- **Bounded.** Text and author are clamped, and the author is one line.
- **Total.** A payload shape the parser does not expect costs the snapshot,
  never the message.
- **The park/flush round trip keeps it,** since a message parked behind an
  auto-install is rebuilt from JSON at flush.

This is a new file rather than an addition to
``test_channel_conversation_adapter.py`` on purpose (plan §0). The end-to-end
path — a quoted webhook reaching the classifier prompt and the agent's context
— is covered in
``tests/api/server_channels/server_channels_quoted_context_test.py``.
"""
from __future__ import annotations

import copy
import json
from dataclasses import fields
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.models import ChannelThreadBinding
from app.services.server_channels.adapters.base import (
    QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS,
    QUOTED_SNAPSHOT_MAX_CHARS,
    ChannelInboundMessage,
)
from app.services.server_channels.adapters.google_chat import GoogleChatAdapter
from app.services.server_channels.channel_inbound_service import ChannelInboundService

QUOTE_ID = "spaces/AAA/messages/earlier"
QUOTE_TEXT = "would be fun to hear a dad joke"


def _event(
    *,
    metadata: Any = None,
    sender_type: str = "HUMAN",
    text: str = "can u?",
) -> dict:
    message: dict[str, Any] = {
        "name": "spaces/AAA/messages/now",
        "text": text,
        "argumentText": text,
        "createTime": "2026-01-01T00:00:00Z",
        "thread": {"name": "spaces/AAA/threads/BBB"},
        "threadReply": True,
        "sender": {
            "type": sender_type,
            "name": "users/123",
            "email": "ann@example.org",
            "displayName": "Ann",
        },
    }
    if metadata is not None:
        message["quotedMessageMetadata"] = metadata
    return {
        "type": "MESSAGE",
        "space": {
            "name": "spaces/AAA",
            "spaceType": "SPACE",
            "spaceThreadingState": "THREADED_MESSAGES",
        },
        "message": message,
    }


def _metadata(**snapshot: Any) -> dict:
    return {"name": QUOTE_ID, "quoteType": "REPLY", "quotedMessageSnapshot": snapshot}


def _parse(event: dict) -> ChannelInboundMessage:
    return GoogleChatAdapter()._parse_event(event)


def _fields_without(parsed: ChannelInboundMessage, *excluded: str) -> dict:
    """Every dataclass field except ``raw`` (the event itself) and ``excluded``."""
    skip = {"raw", *excluded}
    return {f.name: getattr(parsed, f.name) for f in fields(parsed) if f.name not in skip}


# ---------------------------------------------------------------------------
# Capture
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("quote_type", [None, "QUOTE_TYPE_UNSPECIFIED", "REPLY"])
def test_a_same_space_reply_quote_with_a_snapshot_fills_text_and_author(quote_type):
    metadata = {
        "name": QUOTE_ID,
        "quotedMessageSnapshot": {"text": f"  {QUOTE_TEXT}\n ", "sender": "Bob Smith"},
    }
    if quote_type is not None:
        metadata["quoteType"] = quote_type

    parsed = _parse(_event(metadata=metadata))

    assert parsed.event_kind == "message"
    assert parsed.quoted_message_id == QUOTE_ID
    # Stripped, not otherwise rewritten.
    assert parsed.quoted_message_text == QUOTE_TEXT
    assert parsed.quoted_message_author == "Bob Smith"
    # The sender's own words are untouched by the quote.
    assert parsed.text == "can u?"


def test_no_snapshot_leaves_both_fields_none_and_changes_nothing_else():
    with_snapshot = _event(metadata=_metadata(text=QUOTE_TEXT, sender="Bob"))
    without_snapshot = copy.deepcopy(with_snapshot)
    del without_snapshot["message"]["quotedMessageMetadata"]["quotedMessageSnapshot"]

    a = _parse(with_snapshot)
    b = _parse(without_snapshot)

    assert b.quoted_message_id == QUOTE_ID
    assert b.quoted_message_text is None
    assert b.quoted_message_author is None
    # Every other field is identical: the snapshot adds two fields and nothing
    # else, so an event without one parses exactly as before.
    assert _fields_without(a, "quoted_message_text", "quoted_message_author") == (
        _fields_without(b, "quoted_message_text", "quoted_message_author")
    )


@pytest.mark.parametrize("metadata", [None, "a string", ["a", "list"], 42])
def test_no_or_non_object_metadata_parses_as_an_unquoted_message(metadata):
    """No ``quotedMessageMetadata``, or one that is not an object, is no quote.

    The non-object shapes used to be read with ``(x or {}).get`` and would
    raise on a string; the quote is optional context and must never cost the
    message carrying it.
    """
    parsed = _parse(_event(metadata=metadata))
    plain = _parse(_event())

    assert parsed.event_kind == "message"
    assert parsed.quoted_message_id is None
    assert parsed.quoted_message_text is None
    assert parsed.quoted_message_author is None
    assert _fields_without(parsed) == _fields_without(plain)


@pytest.mark.parametrize(
    "quoted_name",
    [
        "spaces/OTHER/messages/earlier",  # another space
        "spaces/AAA/threads/earlier",  # not a message
        "spaces/AAA/messages/has space",  # malformed id
        "not-a-resource-name",
        "",
        42,
        None,
    ],
)
def test_a_cross_space_or_malformed_id_carries_no_snapshot(quoted_name):
    metadata = {
        "name": quoted_name,
        "quoteType": "REPLY",
        "quotedMessageSnapshot": {"text": QUOTE_TEXT, "sender": "Bob"},
    }
    parsed = _parse(_event(metadata=metadata))

    assert parsed.quoted_message_id is None
    assert parsed.quoted_message_text is None
    assert parsed.quoted_message_author is None


@pytest.mark.parametrize("quote_type", ["FORWARD", "SOMETHING_GOOGLE_ADDS_LATER"])
def test_a_forward_or_unknown_quote_type_carries_no_snapshot(quote_type):
    """Forwards are cross-space by nature; an unknown type fails closed.

    The id rule is independent of the type, so the same-space id survives —
    only the snapshot is withheld.
    """
    metadata = {
        "name": QUOTE_ID,
        "quoteType": quote_type,
        "quotedMessageSnapshot": {"text": QUOTE_TEXT, "sender": "Bob"},
    }
    parsed = _parse(_event(metadata=metadata))

    assert parsed.quoted_message_id == QUOTE_ID
    assert parsed.quoted_message_text is None
    assert parsed.quoted_message_author is None


# ---------------------------------------------------------------------------
# Bounds
# ---------------------------------------------------------------------------


def test_text_over_the_limit_is_clamped_with_an_ellipsis():
    long_text = "j" * (QUOTED_SNAPSHOT_MAX_CHARS * 5)
    parsed = _parse(_event(metadata=_metadata(text=long_text, sender="Bob")))

    assert len(parsed.quoted_message_text) == QUOTED_SNAPSHOT_MAX_CHARS
    assert parsed.quoted_message_text.endswith("…")
    assert parsed.quoted_message_text[:-1] == "j" * (QUOTED_SNAPSHOT_MAX_CHARS - 1)

    exact = "k" * QUOTED_SNAPSHOT_MAX_CHARS
    at_limit = _parse(_event(metadata=_metadata(text=exact, sender="Bob")))
    assert at_limit.quoted_message_text == exact


def test_a_multi_line_author_is_collapsed_to_one_line_and_clamped():
    parsed = _parse(
        _event(metadata=_metadata(text=QUOTE_TEXT, sender="  Bob\n\t Smith\r\n  "))
    )
    assert parsed.quoted_message_author == "Bob Smith"

    long_author = "Bob " + "x" * (QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS * 3) + "\nsecond line"
    clamped = _parse(_event(metadata=_metadata(text=QUOTE_TEXT, sender=long_author)))
    assert len(clamped.quoted_message_author) == QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS
    assert clamped.quoted_message_author.endswith("…")
    assert "\n" not in clamped.quoted_message_author


@pytest.mark.parametrize("bad_text", [None, 123, {"a": 1}, ["x"], "", "   \n\t "])
def test_non_string_or_blank_text_gives_no_snapshot_even_with_an_author(bad_text):
    snapshot: dict[str, Any] = {"sender": "Bob"}
    if bad_text is not None:
        snapshot["text"] = bad_text
    parsed = _parse(_event(metadata={"name": QUOTE_ID, "quotedMessageSnapshot": snapshot}))

    assert parsed.quoted_message_id == QUOTE_ID
    assert parsed.quoted_message_text is None
    # The author is a label for the text; without the text it means nothing.
    assert parsed.quoted_message_author is None


@pytest.mark.parametrize("bad_author", [None, 7, {"name": "users/1"}, "", "   "])
def test_a_non_string_or_blank_author_keeps_the_text_and_drops_the_label(bad_author):
    snapshot: dict[str, Any] = {"text": QUOTE_TEXT}
    if bad_author is not None:
        snapshot["sender"] = bad_author
    parsed = _parse(_event(metadata={"name": QUOTE_ID, "quotedMessageSnapshot": snapshot}))

    assert parsed.quoted_message_text == QUOTE_TEXT
    assert parsed.quoted_message_author is None


# ---------------------------------------------------------------------------
# Totality
# ---------------------------------------------------------------------------


class _RaisingDict(dict):
    """A dict whose reads explode — a snapshot object that raises on access."""

    def get(self, *_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom: snapshot read")

    def __getitem__(self, _key: Any) -> Any:
        raise RuntimeError("boom: snapshot item")


class _RaisingStr(str):
    def strip(self, *_args: Any) -> str:  # noqa: D102
        raise RuntimeError("boom: strip")


def test_a_snapshot_that_raises_on_access_gives_none_and_the_message_still_parses():
    event = _event(metadata={"name": QUOTE_ID, "quotedMessageSnapshot": _RaisingDict(text="x")})
    parsed = _parse(event)

    assert parsed.event_kind == "message"
    assert parsed.quoted_message_id == QUOTE_ID
    assert parsed.quoted_message_text is None
    assert parsed.quoted_message_author is None


@pytest.mark.parametrize(
    "message",
    [
        {"quotedMessageMetadata": _RaisingDict(name=QUOTE_ID)},
        {"quotedMessageMetadata": {"name": QUOTE_ID, "quotedMessageSnapshot": _RaisingDict()}},
        {
            "quotedMessageMetadata": {
                "name": QUOTE_ID,
                "quotedMessageSnapshot": {"text": _RaisingStr("x"), "sender": "Bob"},
            }
        },
    ],
)
def test_quoted_snapshot_is_total(message):
    assert GoogleChatAdapter._quoted_snapshot(message, QUOTE_ID) == (None, None)


def test_quoted_snapshot_needs_the_accepted_id():
    """The same-space verdict is the caller's; without it there is no snapshot."""
    message = {"quotedMessageMetadata": _metadata(text=QUOTE_TEXT, sender="Bob")}
    assert GoogleChatAdapter._quoted_snapshot(message, None) == (None, None)
    assert GoogleChatAdapter._quoted_snapshot(message, "") == (None, None)
    assert GoogleChatAdapter._quoted_snapshot(message, QUOTE_ID) == (QUOTE_TEXT, "Bob")


# ---------------------------------------------------------------------------
# Unchanged neighbours
# ---------------------------------------------------------------------------


def test_bot_and_ignored_events_are_unchanged_by_a_snapshot():
    metadata = _metadata(text=QUOTE_TEXT, sender="Bob")

    bot = _parse(_event(metadata=metadata, sender_type="BOT"))
    assert bot.event_kind == "ignored"
    assert bot.quoted_message_id is None
    assert bot.quoted_message_text is None

    empty = _parse(_event(metadata=metadata, text=""))
    assert empty.event_kind == "ignored"
    assert empty.quoted_message_text is None

    added = GoogleChatAdapter()._parse_event({"type": "ADDED_TO_SPACE"})
    assert added.event_kind == "added_to_space"
    assert added.quoted_message_text is None


def test_message_ref_for_a_fetched_message_ignores_the_snapshot():
    """``_message_ref`` builds a *fetched* message; its text is its own.

    A fetched message that itself quoted something keeps only the id of what it
    quoted, exactly as before: the snapshot belongs to the live event, and a
    fetched ref must never pick up someone else's words as its text.
    """
    message = _event()["message"]
    plain = GoogleChatAdapter()._message_ref(
        {**message, "quotedMessageMetadata": {"name": QUOTE_ID}},
        SimpleNamespace(id="quoted-snapshot-ref"),
    )
    with_snapshot = GoogleChatAdapter()._message_ref(
        {**message, "quotedMessageMetadata": _metadata(text=QUOTE_TEXT, sender="Bob")},
        SimpleNamespace(id="quoted-snapshot-ref"),
    )

    assert with_snapshot == plain
    assert with_snapshot.text == "can u?"
    assert with_snapshot.quoted_message_id == QUOTE_ID


# ---------------------------------------------------------------------------
# Parked round trip
# ---------------------------------------------------------------------------


def _binding() -> ChannelThreadBinding:
    return ChannelThreadBinding(
        server_channel_id=uuid4(),
        thread_key="spaces/AAA/threads/BBB",
        scope_key="spaces/AAA/threads/BBB",
        user_id=uuid4(),
        agent_id=uuid4(),
        status="pending_install",
        conversation_key="spaces/AAA",
        conversation_kind="group",
        pending_messages=[],
    )


def _inbound(**overrides: Any) -> ChannelInboundMessage:
    base: dict[str, Any] = {
        "event_kind": "message",
        "text": "can u?",
        "external_message_id": "spaces/AAA/messages/now",
        "external_user_id": "users/123",
        "thread_key": "spaces/AAA/threads/BBB",
        "conversation_key": "spaces/AAA",
        "conversation_kind": "group",
        "quoted_message_id": QUOTE_ID,
        "quoted_message_text": QUOTE_TEXT,
        "quoted_message_author": "Bob Smith",
    }
    base.update(overrides)
    return ChannelInboundMessage(**base)


def test_park_then_rebuild_preserves_the_snapshot():
    db = MagicMock()
    binding = _binding()

    assert ChannelInboundService._park_message(db, binding, _inbound(), text="can u?")
    db.commit.assert_called_once()

    # The queue is a JSON column: round-trip it the way the database does.
    entry = json.loads(json.dumps(binding.pending_messages[0]))
    rebuilt = ChannelInboundService._inbound_for_binding(binding, entry)

    assert rebuilt.text == "can u?"
    assert rebuilt.quoted_message_id == QUOTE_ID
    assert rebuilt.quoted_message_text == QUOTE_TEXT
    assert rebuilt.quoted_message_author == "Bob Smith"


def test_a_legacy_parked_entry_without_the_snapshot_keys_rebuilds_with_none():
    db = MagicMock()
    binding = _binding()
    ChannelInboundService._park_message(db, binding, _inbound(), text="can u?")
    entry = json.loads(json.dumps(binding.pending_messages[0]))

    # What an entry parked before this deploy looks like.
    del entry["conversation"]["quoted_message_text"]
    del entry["conversation"]["quoted_message_author"]
    legacy = ChannelInboundService._inbound_for_binding(binding, entry)
    assert legacy.quoted_message_id == QUOTE_ID
    assert legacy.quoted_message_text is None
    assert legacy.quoted_message_author is None

    # And the invariant holds on the way back in too: a snapshot without the id
    # it belongs to is dropped rather than rebuilt.
    orphan = json.loads(json.dumps(binding.pending_messages[0]))
    orphan["conversation"]["quoted_message_id"] = None
    rebuilt = ChannelInboundService._inbound_for_binding(binding, orphan)
    assert rebuilt.quoted_message_id is None
    assert rebuilt.quoted_message_text is None
    assert rebuilt.quoted_message_author is None
