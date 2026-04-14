"""
App MCP OAuth Auth Code models — mirrors MCPAuthCode/MCPAuthRequest
but for the app-level MCP server (no connector_id).
"""
import uuid
from datetime import datetime, UTC
from sqlmodel import SQLModel, Field


class AppMCPAuthCode(SQLModel, table=True):
    """Authorization code for the App MCP OAuth flow (no connector_id)."""

    __tablename__ = "app_mcp_auth_code"

    code: str = Field(primary_key=True)
    client_id: str = Field(index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", ondelete="CASCADE")
    redirect_uri: str
    code_challenge: str = Field(default="")
    code_challenge_method: str = Field(default="S256")
    scope: str = Field(default="")
    resource: str = Field(default="")
    expires_at: datetime
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AppMCPAuthRequest(SQLModel, table=True):
    """Pending OAuth authorization request for the App MCP Server (no connector_id)."""

    __tablename__ = "app_mcp_auth_request"

    nonce: str = Field(primary_key=True)
    client_id: str
    redirect_uri: str
    code_challenge: str = Field(default="")
    code_challenge_method: str = Field(default="S256")
    scope: str = Field(default="")
    state: str = Field(default="")
    resource: str = Field(default="")
    expires_at: datetime
    used: bool = Field(default=False)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
