from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class HealthCheckResponse(BaseModel):
    """Health check response model"""
    status: str  # "healthy" | "degraded" | "unhealthy"
    timestamp: datetime
    uptime: int  # Seconds since startup
    message: str | None = None


class AgentPromptsResponse(BaseModel):
    """Agent prompts from docs files"""
    workflow_prompt: str | None = None
    entrypoint_prompt: str | None = None


class AgentPromptsUpdate(BaseModel):
    """Update agent prompts in docs files"""
    workflow_prompt: str | None = None
    entrypoint_prompt: str | None = None


class ChatRequest(BaseModel):
    """Chat message request"""
    message: str
    session_id: Optional[str] = None  # External SDK session ID (for Claude SDK resumption)
    backend_session_id: Optional[str] = None  # Backend database session ID (for handover tracking)
    mode: str = "conversation"  # "building" | "conversation"
    agent_sdk: str = "claude"  # SDK to use: "claude" (more options can be added later)
    system_prompt: Optional[str] = None


class ChatResponse(BaseModel):
    """Chat message response"""
    response: str
    session_id: Optional[str] = None
    metadata: dict = {}


class CredentialsUpdate(BaseModel):
    """Update credentials in workspace"""
    credentials_json: list[dict]  # Full credentials data
    credentials_readme: str  # Redacted README for agent prompt


class FileNode(BaseModel):
    """Single file or folder node in workspace tree"""
    name: str
    type: str  # "file" | "folder"
    path: str  # Relative path from workspace root
    size: int | None = None  # Bytes (None for folders until summarized)
    modified: datetime | None = None
    children: list['FileNode'] | None = None  # Only for folders


class FolderSummary(BaseModel):
    """Summary statistics for a folder"""
    fileCount: int
    totalSize: int  # Bytes


class WorkspaceTreeResponse(BaseModel):
    """Complete workspace tree with 5 main folders"""
    files: FileNode
    logs: FileNode
    scripts: FileNode
    docs: FileNode
    uploads: FileNode
    summaries: dict[str, FolderSummary]


class AgentHandoverUpdate(BaseModel):
    """Update agent handover configuration"""
    handovers: list[dict]  # Array of {id, name, prompt} objects
    handover_prompt: str  # Prompt text to append to conversation mode system prompt


class AgentHandoverResponse(BaseModel):
    """Agent handover configuration response"""
    handovers: list[dict]
    handover_prompt: str


class FileUploadResponse(BaseModel):
    """Response for file upload endpoint"""
    path: str  # Relative path: ./uploads/document.pdf
    filename: str  # Final filename (may differ from requested if conflict)
    size: int  # File size in bytes
    message: str
