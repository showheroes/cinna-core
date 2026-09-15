"""State for the channel router's clarifying questions.

The effect half of the clarification round-trip: ``ChannelInboundService`` asks
(when ``decide`` returned ``clarify`` guidance), finds the open question for a
sender's next unbound message, claims it when that message answers, and the
pending-binding scheduler tick purges what expired. ``ChannelRoutingService``
never imports this module; the decision stays pure and learns about a choice
only as the ``chosen_ref_id`` value it is handed.

Everything this module returns is plain data (:class:`ClarificationSnapshot`),
so it can cross into a background task without an ORM row whose session is
gone.

**Only one answer wins.** :meth:`ChannelRoutingClarificationService.claim`
deletes by id and reports whether *this* call deleted the row. Two replies
racing to answer the same question both resolve, and exactly one of them
routes the original message. Asking again replaces the row and gives it a
new id, so a slow answer to the previous question cannot claim the new one.

**Files.** The original message's ``file_ids`` are stored by id and the rows
stay ``temporary``, exactly as a parked message's do (see
``ChannelInboundService._append_parked``). Expiry, cancel and a dropped
question release nothing explicitly: the 24h temp-file GC reclaims the rows,
and an answer that arrives after it filters out the ids that are gone.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session as DBSession
from sqlmodel import select

from app.models import ChannelRoutingClarification, ChannelThreadIngestLog
from app.models.server_channels.channel_thread_ingest_log import (
    CHANNEL_INGEST_SOURCE_CLARIFY_REPLY,
)
from app.services.server_channels.channel_routing_guidance import (
    ClarificationOption,
    GuidanceEntry,
)

logger = logging.getLogger(__name__)

_LOG_PREFIX = "[ChannelClarification]"

#: ``ChannelThreadIngestLog.source`` for a message that answered a routing
#: question. The receipt goes on the binding the answer created, so a webhook
#: redelivery of the answer is recognised as already handled and never reaches
#: the agent, and the conversation-context backfill does not replay it as
#: history. Kept by ``reset_for_new_session``, which runs when the original's
#: session is first created and would otherwise delete it.
RECEIPT_SOURCE_CLARIFY_REPLY = CHANNEL_INGEST_SOURCE_CLARIFY_REPLY


@dataclass(frozen=True)
class ClarificationSnapshot:
    """An open question, read into plain data."""

    id: uuid.UUID
    thread_key: str
    conversation_key: str | None
    conversation_kind: str | None
    options: tuple[ClarificationOption, ...]
    message: dict[str, Any] = field(default_factory=dict)
    status_message_id: str | None = None
    expires_at: datetime | None = None

    @property
    def option_refs(self) -> tuple[str, ...]:
        return tuple(option.ref_id for option in self.options)

    def option_number(self, ref_id: str) -> int | None:
        """The 1-based number the question showed ``ref_id`` under."""
        for number, option in enumerate(self.options, start=1):
            if option.ref_id == ref_id:
                return number
        return None

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return True
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return expires_at <= (now or datetime.now(UTC))


def _parse_options(raw: Any) -> tuple[ClarificationOption, ...]:
    """Stored options back into plain data. Total: a malformed entry is skipped."""
    if not isinstance(raw, list):
        return ()
    options: list[ClarificationOption] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        ref_id = item.get("ref_id")
        if not isinstance(ref_id, str) or not ref_id:
            continue
        name = item.get("name")
        kind = item.get("kind")
        options.append(
            ClarificationOption(
                ref_id=ref_id,
                name=name if isinstance(name, str) else "",
                kind=kind if isinstance(kind, str) else "",
            )
        )
    return tuple(options)


class ChannelRoutingClarificationService:
    """Ask, find, claim and purge clarifying questions. Commits its own writes."""

    @staticmethod
    def ask(
        db: DBSession,
        *,
        channel_id: uuid.UUID,
        scope_key: str,
        user_id: uuid.UUID,
        thread_key: str,
        conversation_key: str | None,
        conversation_kind: str | None,
        options: Sequence[GuidanceEntry],
        message: dict[str, Any],
        status_message_id: str | None,
        ttl_minutes: int,
    ) -> None:
        """Store the question, replacing any open one for the same key.

        One atomic upsert on the unique key, so two questions racing for one
        asker leave exactly one row. The replacement takes a new ``id``: a
        claim made against the previous question then misses, instead of
        consuming this one. A TTL below one minute is read as one.
        """
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "id": uuid.uuid4(),
            "server_channel_id": channel_id,
            "scope_key": scope_key,
            "user_id": user_id,
            "thread_key": thread_key,
            "conversation_key": conversation_key,
            "conversation_kind": conversation_kind,
            "options": [
                {"ref_id": entry.ref_id, "name": entry.name, "kind": entry.kind}
                for entry in options
            ],
            "message": message,
            "status_message_id": status_message_id,
            "created_at": now,
            "expires_at": now + timedelta(minutes=max(1, int(ttl_minutes))),
        }
        statement = insert(ChannelRoutingClarification).values(**values)
        statement = statement.on_conflict_do_update(
            constraint="uq_channel_routing_clarification_scope",
            set_={
                key: getattr(statement.excluded, key)
                for key in values
                if key not in ("server_channel_id", "scope_key", "user_id")
            },
        )
        db.execute(statement)
        db.commit()

    @staticmethod
    def find(
        db: DBSession,
        *,
        channel_id: uuid.UUID,
        scope_key: str,
        user_id: uuid.UUID,
    ) -> ClarificationSnapshot | None:
        """The question open for this asker in this scope, expired or not."""
        row = db.exec(
            select(ChannelRoutingClarification).where(
                ChannelRoutingClarification.server_channel_id == channel_id,
                ChannelRoutingClarification.scope_key == scope_key,
                ChannelRoutingClarification.user_id == user_id,
            )
        ).first()
        if row is None:
            return None
        return ClarificationSnapshot(
            id=row.id,
            thread_key=row.thread_key,
            conversation_key=row.conversation_key,
            conversation_kind=row.conversation_kind,
            options=_parse_options(row.options),
            message=dict(row.message) if isinstance(row.message, dict) else {},
            status_message_id=row.status_message_id,
            expires_at=row.expires_at,
        )

    @staticmethod
    def claim(db: DBSession, clarification_id: uuid.UUID) -> bool:
        """Delete the question. True only for the call that actually deleted it."""
        result = db.execute(
            delete(ChannelRoutingClarification).where(
                ChannelRoutingClarification.id == clarification_id
            )
        )
        db.commit()
        return (result.rowcount or 0) == 1

    @staticmethod
    def discard(db: DBSession, clarification_id: uuid.UUID) -> None:
        """Delete the question whether or not something else got there first."""
        ChannelRoutingClarificationService.claim(db, clarification_id)

    @staticmethod
    def purge_expired(db: DBSession, now: datetime | None = None) -> int:
        """Delete every expired question. Returns how many went."""
        result = db.execute(
            delete(ChannelRoutingClarification).where(
                ChannelRoutingClarification.expires_at <= (now or datetime.now(UTC))
            )
        )
        db.commit()
        return int(result.rowcount or 0)

    @staticmethod
    def record_reply_receipt(
        db: DBSession, binding_id: uuid.UUID, external_message_id: str
    ) -> None:
        """Mark ``external_message_id`` as handled on ``binding_id``.

        Written for the message that answered a question, once the original
        message has a binding. ``_continue_thread`` skips a message with a
        receipt, and ``process_inbound`` does not park one on a pending
        binding, so a redelivered answer is never ingested. Idempotent.
        """
        statement = (
            insert(ChannelThreadIngestLog)
            .values(
                id=uuid.uuid4(),
                binding_id=binding_id,
                external_message_id=external_message_id,
                source=RECEIPT_SOURCE_CLARIFY_REPLY,
                char_count=0,
                attachment_count=0,
                is_complete=True,
                injected_at=datetime.now(UTC),
            )
            .on_conflict_do_nothing(constraint="uq_channel_thread_ingest_log_message")
        )
        db.execute(statement)
        db.commit()

    @staticmethod
    def has_receipt(
        db: DBSession, binding_id: uuid.UUID, external_message_id: str
    ) -> bool:
        return (
            db.exec(
                select(ChannelThreadIngestLog.id).where(
                    ChannelThreadIngestLog.binding_id == binding_id,
                    ChannelThreadIngestLog.external_message_id == external_message_id,
                )
            ).first()
            is not None
        )


__all__ = [
    "RECEIPT_SOURCE_CLARIFY_REPLY",
    "ChannelRoutingClarificationService",
    "ClarificationSnapshot",
]
