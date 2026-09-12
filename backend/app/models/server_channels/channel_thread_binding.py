"""One (channel, scope, asker) binding pins an agent and session.

A threaded conversation uses its native thread as scope; a flat conversation
uses its room/space. Each asker is independently routed and authorized.
``user_id`` is the asker, while identity-routed sessions belong to the identity
owner. Deleting a failed binding lets that asker route and backfill afresh.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Text, UniqueConstraint
from sqlmodel import Column, Field, SQLModel

# Binding status values. Plain constants (not an Enum) to match the codebase's
# status-string convention and keep the column a bare varchar.
CHANNEL_BINDING_PENDING_INSTALL = "pending_install"
CHANNEL_BINDING_ACTIVE = "active"
CHANNEL_BINDING_FAILED = "failed"

CHANNEL_BINDING_STATUSES = (
    CHANNEL_BINDING_PENDING_INSTALL,
    CHANNEL_BINDING_ACTIVE,
    CHANNEL_BINDING_FAILED,
)


class ChannelThreadBinding(SQLModel, table=True):
    """Binds one external channel thread to one platform session."""

    __tablename__ = "channel_thread_binding"
    __table_args__ = (
        UniqueConstraint(
            "server_channel_id",
            "scope_key",
            "user_id",
            name="uq_channel_thread_binding_scope",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    server_channel_id: uuid.UUID = Field(
        foreign_key="server_channel.id", ondelete="CASCADE"
    )
    # Native thread is an address, not the session identity.
    thread_key: str = Field(max_length=512)
    scope_key: str = Field(max_length=512, index=True)
    conversation_key: str | None = Field(default=None, max_length=512, index=True)
    conversation_kind: str | None = Field(default=None, max_length=16)
    last_reply_mode: str | None = Field(default=None, max_length=24)
    history_backfilled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    # Full address of the current notice/turn, including quote timestamp and
    # asker attribution. Resume and repair must patch the same destination.
    reply_target: dict | None = Field(
        default=None, sa_column=Column(JSON, nullable=True)
    )
    # The live asker; never the identity owner or a historical message author.
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    # Uninstalling the agent cascades the binding away ⇒ next message re-routes.
    # On an identity thread that is the *identity owner's* agent, so the owner
    # deleting it ends the thread as surely as a revocation would.
    agent_id: uuid.UUID = Field(foreign_key="agent.id", ondelete="CASCADE")
    # NULL while pending_install, or after the session was deleted.
    session_id: uuid.UUID | None = Field(
        default=None, foreign_key="session.id", ondelete="SET NULL", index=True
    )
    status: str = Field(default=CHANNEL_BINDING_PENDING_INSTALL, max_length=32)
    # Messages parked while the environment builds:
    # [{"text": str, "external_message_id": str | None, "received_at": str}]
    #
    # Plain JSON column: ``binding.pending_messages.append(...)`` is NOT
    # dirty-tracked and the commit silently drops the parked message. Assign a
    # new list, or call
    # ``sqlalchemy.orm.attributes.flag_modified(binding, "pending_messages")``
    # before committing — the convention used across this codebase.
    pending_messages: list = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    # Webhook redelivery dedup — channels re-send on a slow ack.
    last_external_message_id: str | None = Field(default=None, max_length=255)
    # The thread's live *status notice*: the single progress message the
    # pipeline posts, rewrites in place as the work advances (routing →
    # installing → working), and deletes once the agent's real reply lands.
    #
    # NULL means "no notice is outstanding", which is the resting state of
    # every thread between turns and the permanent state of every transport
    # that cannot edit and delete its own messages (see
    # ``ChannelCapabilities.supports_status_notice`` — those post each notice
    # separately and have nothing to remember).
    #
    # It holds a transport-native message id, not a platform one, and it is
    # written only by ``ChannelOutboundService``'s status helpers. Cleared
    # rather than left stale on every terminal outcome: a notice id that
    # outlives its message would make the next turn patch a message that is
    # gone, and the *fallback* for a failed patch is to post a fresh notice —
    # so a stale id costs an extra round trip, never a lost update.
    status_message_id: str | None = Field(default=None, max_length=255)
    last_error: str | None = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
