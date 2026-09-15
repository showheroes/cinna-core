"""Exercise recipient selection and context receipts against an isolated DB."""

import asyncio
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlmodel import Session, create_engine, select

from app.models import ChannelThreadBinding, ChannelThreadIngestLog, User
from app.services.server_channels.adapters import email
from app.services.server_channels.adapters.base import ChannelSendError
from app.services.server_channels.channel_conversation_context_service import (
    ChannelConversationContextService as ContextService,
)
from app.services.server_channels.channel_reply_policy import ChannelReplyPolicy
from tests.unit.test_channel_conversation_context import _inputs, _ref


@pytest.fixture
def receipt_db():
    # Only these tables are needed; unrelated user/agent FKs are not enforced
    # in this SQLite fixture. Selection, uniqueness and receipt writes are real.
    engine = create_engine("sqlite://")
    ChannelThreadBinding.__table__.create(engine)
    ChannelThreadIngestLog.__table__.create(engine)
    with Session(engine, expire_on_commit=False) as db:
        yield db
    engine.dispose()


def _binding(db, channel_id, root="<root@example.org>"):
    binding = ChannelThreadBinding(
        server_channel_id=channel_id, thread_key=root, scope_key=root,
        user_id=uuid4(), agent_id=uuid4(), session_id=uuid4(), status="active",
        last_external_message_id=f"<{uuid4()}@example.org>",
    )
    db.add(binding)
    db.commit()
    return binding


def test_email_replies_select_the_originating_asker_and_refuse_ambiguous_legacy(receipt_db):
    db = receipt_db
    channel = SimpleNamespace(id=uuid4(), channel_type="email", config={
        email._CFG_FROM_ADDRESS: "bot@example.org",
        email._CFG_OUTGOING_SERVER: str(uuid4()),
    })
    bindings = [_binding(db, channel.id), _binding(db, channel.id)]
    users = dict(zip([b.user_id for b in bindings], ["alice@example.org", "bob@example.org"], strict=True))
    queued = []

    class DeliveryDB:
        def exec(self, statement):
            return db.exec(statement)

        def get(self, model, key):
            return SimpleNamespace(email=users[key]) if model is User else None

        def add(self, entry):
            queued.append(entry)

        def commit(self):
            pass

    @contextmanager
    def delivery_session():
        yield DeliveryDB()

    adapter = email.EmailChannelAdapter()
    with patch("app.core.db.create_session", delivery_session):
        for binding in bindings:
            target = ChannelReplyPolicy.resolve_binding(binding, channel)
            asyncio.run(adapter.send_message(channel, target, "Private answer"))
            assert queued[-1].recipient == users[binding.user_id]
            assert queued[-1].session_id == binding.session_id
            assert queued[-1].agent_id == binding.agent_id
            assert queued[-1].in_reply_to == binding.last_external_message_id

        with pytest.raises(ChannelSendError, match="Ambiguous"):
            asyncio.run(adapter.send_message(channel, bindings[0].thread_key, "Legacy answer"))
        target = replace(target, binding_id=str(uuid4()))
        with pytest.raises(ChannelSendError, match="No thread binding"):
            asyncio.run(adapter.send_message(channel, target, "Stale binding"))
        assert len(queued) == 2

        db.delete(bindings[1])
        db.commit()
        asyncio.run(adapter.send_message(channel, bindings[0].thread_key, "Unique legacy answer"))
        assert queued[-1].recipient == users[bindings[0].user_id]


def test_new_session_reset_keeps_a_clarify_answer_receipt_and_clears_every_other_row(receipt_db):
    """A clarify-answer receipt is written before the original's session exists;
    the reset that session triggers must keep it, or a redelivered answer reaches
    the agent. The API half is `server_channels_routing_clarification_test.py`'s
    redelivery tests."""
    from app.models.server_channels.channel_thread_ingest_log import (
        CHANNEL_INGEST_SOURCE_CLARIFY_REPLY,
    )

    db = receipt_db
    binding = _binding(db, uuid4())
    db.add(ChannelThreadIngestLog(
        binding_id=binding.id, external_message_id="live-turn", source="live", char_count=5,
    ))
    db.add(ChannelThreadIngestLog(
        binding_id=binding.id, external_message_id="quoted-turn", source="quoted", char_count=9,
    ))
    db.add(ChannelThreadIngestLog(
        binding_id=binding.id, external_message_id="the-answer",
        source=CHANNEL_INGEST_SOURCE_CLARIFY_REPLY,
    ))
    db.commit()

    ContextService.reset_for_new_session(db=db, binding=binding)

    rows = db.exec(select(ChannelThreadIngestLog)).all()
    assert [(row.external_message_id, row.source) for row in rows] == [
        ("the-answer", CHANNEL_INGEST_SOURCE_CLARIFY_REPLY)
    ]


def test_new_session_refetches_history_and_quotes_without_resetting_other_askers(receipt_db):
    args = _inputs()
    db = receipt_db
    binding = _binding(db, args["channel"].id)
    other = _binding(db, args["channel"].id)
    for row in (binding, other):
        row.history_backfilled_at = datetime.now(UTC)
        db.add(ChannelThreadIngestLog(
            binding_id=row.id, external_message_id="third", source="quoted", char_count=20,
        ))
    binding.session_id = None  # State left by the session's SET NULL cascade.
    db.commit()
    last_live_id = binding.last_external_message_id
    ContextService.reset_for_new_session(db=db, binding=binding)
    assert binding.history_backfilled_at is None
    assert binding.last_external_message_id == last_live_id
    assert other.history_backfilled_at is not None
    assert [row.binding_id for row in db.exec(select(ChannelThreadIngestLog)).all()] == [other.id]

    args.update(db=db, binding=binding)
    args["adapter"].fetch_message.return_value = _ref("third", "Recovered quote")
    args["adapter"].fetch_thread_history.return_value = [_ref("prior", "Recovered history")]
    result = asyncio.run(ContextService.build_context(**args))
    assert "Recovered quote" in result.transcript
    assert "Recovered history" in result.transcript
    assert result.history_backfilled


def test_explicit_quote_upgrades_truncated_receipt_once(receipt_db):
    args = _inputs()
    db = receipt_db
    binding = _binding(db, args["channel"].id)
    args.update(db=db, binding=binding)
    args["inbound"] = replace(args["inbound"], quoted_message_id=None)
    args["adapter"].fetch_thread_history.return_value = [
        _ref("newer", "A" * 2500), _ref("older", "B" * 2000),
    ]
    first = asyncio.run(ContextService.build_context(**args))
    older = next(entry for entry in first.entries if entry.external_message_id == "older")
    assert older.char_count < 2000
    assert not older.is_complete
    ContextService.stage_ingest(
        db=db, binding_id=binding.id, context=first,
        external_message_id="live", live_char_count=10,
    )
    db.commit()

    args["inbound"] = replace(args["inbound"], quoted_message_id="older", external_message_id="next-live")
    args["adapter"].fetch_message.return_value = _ref("older", "B" * 2000)
    second = asyncio.run(ContextService.build_context(**args))
    assert "B" * 2000 in second.transcript
    reconciled, duplicate = ContextService.reconcile_context(
        db=db, binding_id=binding.id, context=second, external_message_id="next-live",
    )
    assert not duplicate
    assert reconciled.included_count == 1
    assert reconciled.entries[0].is_complete
    ContextService.stage_ingest(
        db=db, binding_id=binding.id, context=reconciled,
        external_message_id="next-live", live_char_count=10,
    )
    db.commit()
    db.expire_all()
    receipt = db.exec(select(ChannelThreadIngestLog).where(
        ChannelThreadIngestLog.external_message_id == "older",
    )).one()
    assert receipt.is_complete
    assert receipt.char_count == 2000

    # A stale partial write cannot downgrade the now-complete receipt.
    ContextService.stage_ingest(
        db=db, binding_id=binding.id, context=first,
        external_message_id="live", live_char_count=10,
    )
    db.commit()
    db.refresh(receipt)
    assert receipt.is_complete
    assert receipt.char_count == 2000

    # A concurrent copy fetched before the upgrade must not inject it again.
    reconciled, duplicate = ContextService.reconcile_context(
        db=db, binding_id=binding.id, context=second, external_message_id="third-live",
    )
    assert not duplicate
    assert reconciled.transcript is None
    args["adapter"].fetch_message.reset_mock()
    third = asyncio.run(ContextService.build_context(**args))
    args["adapter"].fetch_message.assert_not_called()
    assert third.transcript is None
