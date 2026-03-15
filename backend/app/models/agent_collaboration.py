import uuid
from datetime import datetime, UTC
from typing import TYPE_CHECKING
from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy import JSON


if TYPE_CHECKING:
    from app.models.agent import Agent
    from app.models.session import Session
    from app.models.input_task import InputTask
    from app.models.user import User


class AgentCollaboration(SQLModel, table=True):
    """
    Coordinator-initiated multi-agent collaboration.

    A coordinator agent creates this record when dispatching subtasks to multiple
    agents simultaneously. Results from all subtasks are collected via auto-feedback
    and the collaboration is marked complete when all subtasks finish.

    Relationship: One AgentCollaboration → Many CollaborationSubtask
    """

    __tablename__ = "agent_collaboration"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None)

    # Status: pending, in_progress, completed, error
    status: str = Field(default="in_progress", max_length=50)

    # The agent that created and coordinates this collaboration
    coordinator_agent_id: uuid.UUID = Field(foreign_key="agent.id", ondelete="CASCADE")

    # The coordinator's source session (where create_collaboration was called)
    source_session_id: uuid.UUID | None = Field(
        default=None, foreign_key="session.id", ondelete="SET NULL"
    )

    # Shared findings accumulated by participants via post_finding tool
    shared_context: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Owner (same as coordinator agent owner)
    owner_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    subtasks: list["CollaborationSubtask"] = Relationship(
        back_populates="collaboration",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


class CollaborationSubtask(SQLModel, table=True):
    """
    A single subtask within an AgentCollaboration.

    One subtask per target agent. Tracks the InputTask, Session, and completion
    status for each dispatched agent. When all subtasks complete, the parent
    AgentCollaboration transitions to "completed".
    """

    __tablename__ = "collaboration_subtask"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    collaboration_id: uuid.UUID = Field(
        foreign_key="agent_collaboration.id", ondelete="CASCADE"
    )

    # Target agent receiving the subtask
    target_agent_id: uuid.UUID = Field(foreign_key="agent.id", ondelete="CASCADE")

    # The message/instructions sent to the target agent
    task_message: str

    # Status: pending, running, completed, needs_input, error
    status: str = Field(default="pending", max_length=50)

    # Summary from agent when completing/reporting state
    result_summary: str | None = Field(default=None)

    # Linked InputTask created for this subtask
    input_task_id: uuid.UUID | None = Field(
        default=None, foreign_key="input_task.id", ondelete="SET NULL"
    )

    # The session created for this subtask's execution
    session_id: uuid.UUID | None = Field(
        default=None, foreign_key="session.id", ondelete="SET NULL"
    )

    # Ordering of subtasks within the collaboration (for display)
    order: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Relationships
    collaboration: AgentCollaboration = Relationship(
        back_populates="subtasks",
        sa_relationship_kwargs={"lazy": "joined"},
    )


# --- Schema models (no table=True) ---


class CollaborationSubtaskCreate(SQLModel):
    """Data for creating a single subtask within a new collaboration."""

    target_agent_id: uuid.UUID
    task_message: str
    order: int = 0


class CollaborationSubtaskPublic(SQLModel):
    """Public representation of a collaboration subtask."""

    id: uuid.UUID
    collaboration_id: uuid.UUID
    target_agent_id: uuid.UUID
    target_agent_name: str | None = None
    task_message: str
    status: str
    result_summary: str | None
    input_task_id: uuid.UUID | None
    session_id: uuid.UUID | None
    order: int
    created_at: datetime
    updated_at: datetime


class AgentCollaborationCreate(SQLModel):
    """Request to create a new agent collaboration."""

    coordinator_agent_id: uuid.UUID
    source_session_id: uuid.UUID | None = None
    title: str
    description: str | None = None
    subtasks: list[CollaborationSubtaskCreate]


class AgentCollaborationPublic(SQLModel):
    """Public response model for AgentCollaboration with subtask details."""

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    coordinator_agent_id: uuid.UUID
    source_session_id: uuid.UUID | None
    shared_context: dict
    owner_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    subtasks: list[CollaborationSubtaskPublic] = []


class PostFindingRequest(SQLModel):
    """Request to post a finding to the collaboration shared context."""

    finding: str
    # Optional: session ID of the posting agent, used to resolve agent identity.
    # When called from agent-env, pass source_session_id to attribute the finding
    # to the correct agent instead of the coordinator.
    source_session_id: str | None = None


class PostFindingResponse(SQLModel):
    """Response after posting a finding."""

    success: bool
    findings: list[str] = []
    error: str | None = None


class CreateCollaborationRequest(SQLModel):
    """
    Request body for POST /agents/collaborations/create (called from agent-env).

    Uses environment auth token rather than user JWT.
    """

    title: str
    description: str | None = None
    subtasks: list[dict]
    source_session_id: str


class CreateCollaborationResponse(SQLModel):
    """Response from collaboration creation."""

    success: bool
    collaboration_id: str | None = None
    subtask_count: int = 0
    message: str | None = None
    error: str | None = None
