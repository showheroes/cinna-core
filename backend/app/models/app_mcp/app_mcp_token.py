import uuid
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field


class AppMCPToken(SQLModel, table=True):
    """OAuth tokens for the app-level MCP server.

    Stores SHA256 hashes of opaque bearer tokens (never the plain token).
    Mirrors MCPToken but without connector_id — scoped to user only.
    """

    __tablename__ = "app_mcp_token"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE", index=True)
    client_id: str = Field(index=True)
    token_hash: str = Field(unique=True, index=True)  # SHA256 hash of the opaque token
    token_type: str  # "access" | "refresh"
    scope: str = Field(default="")
    resource: str = Field(default="")
    expires_at: datetime
    is_revoked: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
