import uuid
from datetime import UTC, datetime

from pydantic import field_validator
from sqlalchemy import DateTime
from sqlmodel import Column, Field, SQLModel


class ACPToken(SQLModel, table=True):
    __tablename__ = "acp_token"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    connector_id: uuid.UUID = Field(
        foreign_key="acp_connector.id", ondelete="CASCADE", index=True
    )
    token_hash: str = Field(max_length=64, unique=True, index=True)
    prefix: str = Field(max_length=16)
    label: str = Field(max_length=255)
    revoked: bool = False
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_used_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )


class ACPTokenCreate(SQLModel):
    label: str = Field(min_length=1, max_length=255)
    expires_in_days: int = Field(default=90, ge=1, le=365)

    @field_validator("label")
    @classmethod
    def nonblank_label(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Label must not be blank")
        return value


class ACPTokenPublic(SQLModel):
    id: uuid.UUID
    connector_id: uuid.UUID
    prefix: str
    label: str
    revoked: bool
    expires_at: datetime
    created_at: datetime
    last_used_at: datetime | None


class ACPTokenCreated(ACPTokenPublic):
    """The bearer token is returned only when it is minted."""

    token: str


class ACPTokensPublic(SQLModel):
    data: list[ACPTokenPublic]
    count: int
