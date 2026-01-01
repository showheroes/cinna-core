import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Header, status, Depends
from pydantic import BaseModel

from app.api.deps import SessionDep
from app.models import AgentEnvironment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


async def verify_agent_auth_token(
    session: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
    x_agent_env_id: Annotated[str | None, Header()] = None
) -> AgentEnvironment:
    """
    Verify the Authorization header and X-Agent-Env-Id header match a valid environment.

    This validates that:
    1. The environment ID exists in the database
    2. The auth token matches the environment's stored token
    3. The environment belongs to a valid agent

    Args:
        session: Database session
        authorization: Authorization header value (e.g., "Bearer <token>")
        x_agent_env_id: Environment ID header

    Returns:
        The verified AgentEnvironment object

    Raises:
        HTTPException: If authentication fails
    """
    # Validate Authorization header is present
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header"
        )

    # Validate X-Agent-Env-Id header is present
    if not x_agent_env_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Agent-Env-Id header"
        )

    # Parse Authorization header (format: "Bearer <token>")
    try:
        scheme, token = authorization.split(" ", 1)
        if scheme.lower() != "bearer":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication scheme. Expected 'Bearer'"
            )

        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Authorization header format. Expected 'Bearer <token>'"
        )

    # Parse environment ID
    try:
        env_id = uuid.UUID(x_agent_env_id)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid environment ID format"
        )

    # Look up environment in database
    environment = session.get(AgentEnvironment, env_id)
    if not environment:
        logger.warning(f"Authentication failed: Environment {env_id} not found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid environment ID"
        )

    # Verify token matches the environment's auth token
    stored_token = environment.config.get("auth_token")
    if not stored_token or stored_token != token:
        logger.warning(f"Authentication failed: Token mismatch for environment {env_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token"
        )

    logger.info(f"Successfully authenticated environment {env_id}")
    return environment


class KnowledgeQueryRequest(BaseModel):
    """Request model for querying integration knowledge."""
    query: str


class KnowledgeQueryResponse(BaseModel):
    """Response model for knowledge queries."""
    content: str
    source: str | None = None


@router.post("/query")
async def query_knowledge(
    request: KnowledgeQueryRequest,
    environment: Annotated[AgentEnvironment, Depends(verify_agent_auth_token)]
) -> KnowledgeQueryResponse:
    """
    Query the integration knowledge base.

    This endpoint is called by agent environments to get guidance on
    building integrations with various systems (ERP, CRM, etc.).

    Currently returns a stub response. Will be implemented with proper
    knowledge database later.

    Args:
        request: Query request with search string
        environment: Authenticated environment (injected by dependency)

    Returns:
        Knowledge response with guidance text
    """
    logger.info(f"Knowledge query from environment {environment.id}: {request.query}")

    # Stub implementation - always return "write it in python"
    return KnowledgeQueryResponse(
        content="write it in python",
        source="stub"
    )
