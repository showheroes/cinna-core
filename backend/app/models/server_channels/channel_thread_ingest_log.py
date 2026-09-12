"""External messages durably queued for one asker's channel session.

History is content, never authority. Entries are committed alongside the user
message that carries their context; deleting a binding deletes its history.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, UniqueConstraint
from sqlmodel import Field, SQLModel


class ChannelThreadIngestLog(SQLModel, table=True):
    __tablename__ = "channel_thread_ingest_log"
    __table_args__ = (
        UniqueConstraint(
            "binding_id", "external_message_id",
            name="uq_channel_thread_ingest_log_message",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    binding_id: uuid.UUID = Field(
        foreign_key="channel_thread_binding.id", ondelete="CASCADE", index=True,
    )
    external_message_id: str = Field(max_length=255)
    source: str = Field(max_length=16)
    char_count: int = Field(default=0)
    attachment_count: int = Field(default=0)
    is_complete: bool = Field(default=True)
    injected_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
