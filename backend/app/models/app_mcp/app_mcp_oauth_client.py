import uuid
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import JSON


class AppMCPOAuthClient(SQLModel, table=True):
    """Dynamic Client Registration records for the app-level MCP server.

    Mirrors MCPOAuthClient but without connector_id — scoped to the
    app-level endpoint (/mcp/app/mcp) rather than a specific connector.
    """

    __tablename__ = "app_mcp_oauth_client"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    client_id: str = Field(unique=True, index=True)
    client_secret_hash: str
    client_name: str = Field(default="")
    redirect_uris: list = Field(default_factory=list, sa_column=Column(JSON))
    grant_types: list = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        sa_column=Column(JSON),
    )
    response_types: list = Field(
        default_factory=lambda: ["code"],
        sa_column=Column(JSON),
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppMCPOAuthClientPublic(SQLModel):
    id: uuid.UUID
    client_id: str
    client_name: str
    redirect_uris: list[str]
    grant_types: list[str]
    response_types: list[str]
    created_at: datetime
