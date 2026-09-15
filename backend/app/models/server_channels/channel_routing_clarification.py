"""A routing question the channel router asked one sender, awaiting the answer.

When the classifier answers ``clarify`` on a transport that can follow a
question up (``supports_status_notice``), the router asks the sender to choose
between two or three candidates instead of routing its best guess. This row is
the state between that question and its answer: the options offered, best pick
first, and the **original** message in the parked-message entry shape, so the
answer can route that message exactly as it arrived.

One row per ``(server_channel_id, scope_key, user_id)`` — a binding's key — so a
second asker in the same space is unaffected, and asking again replaces the
question. Not a binding: ``ChannelThreadBinding.agent_id`` is NOT NULL and every
ownership invariant reads it, while this state is not a conversation yet.

Deleted when answered, cancelled, dropped or expired
(``CHANNEL_ROUTING_CLARIFY_TTL_MINUTES``: lazily on the sender's next message,
and on the pending-binding scheduler tick). The original message's files are
held the way a parked message holds them: by id, while the rows stay
``temporary``. Nothing is released explicitly on expiry or cancel; the 24h
temp-file GC reclaims them, and an answer that arrives after the GC filters
out the ids that are gone.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, UniqueConstraint
from sqlmodel import Column, Field, SQLModel


class ChannelRoutingClarification(SQLModel, table=True):
    """One open clarifying question for one asker in one conversation scope."""

    __tablename__ = "channel_routing_clarification"
    __table_args__ = (
        UniqueConstraint(
            "server_channel_id",
            "scope_key",
            "user_id",
            name="uq_channel_routing_clarification_scope",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_channel_id: uuid.UUID = Field(
        foreign_key="server_channel.id", ondelete="CASCADE"
    )
    scope_key: str = Field(max_length=512)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    # The address the original message arrived on. Every parked entry carries
    # its own conversation fields too; these are the fallbacks a rebuilt
    # message reads, exactly as a binding's are.
    thread_key: str = Field(max_length=512)
    conversation_key: str | None = Field(default=None, max_length=512)
    conversation_kind: str | None = Field(default=None, max_length=16)
    # [{"ref_id": str, "name": str, "kind": "agent" | "identity" | "bundle"}],
    # in the order the question numbered them.
    #
    # Plain JSON column: assign a new list rather than mutating in place.
    options: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    # The original message as one parked entry
    # (``ChannelInboundService._parked_entry``) plus ``classification_text``.
    message: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    # The transport-native id of the message that asked the question (the
    # status notice the question was settled into). Kept for diagnosis; the
    # question is left standing when it is answered, so nothing rewrites it.
    status_message_id: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
