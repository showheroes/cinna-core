import uuid as uuid_module
from datetime import datetime
from typing import TYPE_CHECKING, Optional
from sqlmodel import Field, Relationship, SQLModel

if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.user import User


# Share status constants
class ShareStatus:
    """Status of an agent share"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    REVOKED = "revoked"
    DELETED = "deleted"  # Clone was deleted by recipient


# Share mode constants (duplicated from agent.py for convenience)
class ShareMode:
    """Sharing mode for agent shares"""
    USER = "user"  # Read-only config, no building mode
    BUILDER = "builder"  # Editable config, building mode allowed


class AgentShareBase(SQLModel):
    """Base properties for agent shares"""
    share_mode: str  # "user" | "builder"


class AgentShare(AgentShareBase, table=True):
    """Database model for agent sharing records"""
    __tablename__ = "agent_share"

    id: uuid_module.UUID = Field(default_factory=uuid_module.uuid4, primary_key=True)
    original_agent_id: uuid_module.UUID = Field(foreign_key="agent.id", nullable=False)
    shared_with_user_id: uuid_module.UUID = Field(foreign_key="user.id", nullable=False)
    shared_by_user_id: uuid_module.UUID = Field(foreign_key="user.id", nullable=False)
    share_mode: str = Field(nullable=False)  # "user" | "builder"

    # Status tracking
    status: str = Field(default="pending")  # "pending" | "accepted" | "declined" | "revoked" | "deleted"
    shared_at: datetime = Field(default_factory=datetime.utcnow)
    accepted_at: datetime | None = Field(default=None)
    declined_at: datetime | None = Field(default=None)

    # Reference to created clone (after acceptance)
    cloned_agent_id: uuid_module.UUID | None = Field(default=None, foreign_key="agent.id")

    # Relationships
    original_agent: "Agent" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AgentShare.original_agent_id]"}
    )
    cloned_agent: Optional["Agent"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AgentShare.cloned_agent_id]"}
    )
    shared_with_user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AgentShare.shared_with_user_id]"}
    )
    shared_by_user: "User" = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[AgentShare.shared_by_user_id]"}
    )


class AgentSharePublic(AgentShareBase):
    """Public representation of a share (for API responses)"""
    id: uuid_module.UUID
    original_agent_id: uuid_module.UUID
    original_agent_name: str  # Resolved from original_agent
    share_mode: str
    status: str
    shared_at: datetime
    accepted_at: datetime | None
    shared_with_email: str  # Resolved from shared_with_user
    shared_by_email: str  # Resolved from shared_by_user
    cloned_agent_id: uuid_module.UUID | None = None


class AgentShareCreate(SQLModel):
    """Input for creating a new share"""
    shared_with_email: str
    share_mode: str  # "user" | "builder"


class AgentShareUpdate(SQLModel):
    """Input for updating share mode"""
    share_mode: str | None = None  # "user" | "builder"


class AgentSharesPublic(SQLModel):
    """List response for agent shares"""
    data: list[AgentSharePublic]
    count: int


class CredentialRequirement(SQLModel):
    """Info about a credential required for agent acceptance"""
    name: str
    type: str
    allow_sharing: bool


class PendingSharePublic(SQLModel):
    """Pending share for recipient view (includes agent details)"""
    id: uuid_module.UUID
    original_agent_id: uuid_module.UUID
    original_agent_name: str
    original_agent_description: str | None
    share_mode: str
    shared_at: datetime
    shared_by_email: str
    shared_by_name: str | None  # User's full name if available

    # Credentials info for acceptance wizard
    credentials_required: list[CredentialRequirement]


class PendingSharesPublic(SQLModel):
    """List response for pending shares"""
    data: list[PendingSharePublic]
    count: int
