import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import field_validator
from sqlalchemy import CheckConstraint, DateTime
from sqlmodel import Column, Field, SQLModel

ACPMode = Literal["conversation", "building"]


class ACPConnectorBase(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    mode: ACPMode = "conversation"
    is_active: bool = True
    max_connections: int = Field(default=10, ge=1, le=100)

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name must not be blank")
        return value


class ACPConnectorCreate(ACPConnectorBase):
    pass


class ACPConnectorUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    mode: ACPMode | None = None
    is_active: bool | None = None
    max_connections: int | None = Field(default=None, ge=1, le=100)

    @field_validator("name", "mode", "is_active", "max_connections", mode="before")
    @classmethod
    def disallow_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Field cannot be null")
        return value

    @field_validator("name")
    @classmethod
    def nonblank_name(cls, value: str) -> str:
        return ACPConnectorBase.nonblank_name(value)


class ACPConnector(SQLModel, table=True):
    __tablename__ = "acp_connector"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('conversation', 'building')", name="ck_acp_connector_mode"
        ),
        CheckConstraint(
            "max_connections BETWEEN 1 AND 100", name="ck_acp_connector_max_connections"
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_id: uuid.UUID = Field(foreign_key="agent.id", ondelete="CASCADE", index=True)
    owner_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    name: str = Field(max_length=255)
    mode: str = Field(default="conversation", max_length=32)
    is_active: bool = True
    max_connections: int = 10
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ACPConnectorPublic(ACPConnectorBase):
    id: uuid.UUID
    agent_id: uuid.UUID
    owner_id: uuid.UUID
    acp_server_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ACPConnectorsPublic(SQLModel):
    data: list[ACPConnectorPublic]
    count: int
