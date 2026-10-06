"""
Agent Credential API Routes — called by scripts inside agent environments.

Authentication: scoped agent-environment token via ``AgentEnvContextDep`` (the
env's ``AGENT_AUTH_TOKEN`` as Bearer plus ``X-Agent-Env-Id``), bound to exactly
one ``(env, agent, owner)`` triple. Rejected by ``CurrentUser``.

Scope model: a credential is reachable only when it is linked to ``ctx.agent``
(``AgentCredentialLink``; shared credentials included). An unlinked or
nonexistent id returns the same 404, so the route never leaks existence. Only
Google OAuth credential types are served; ``mcp_provider`` tokens never live in
credentials.json and are refreshed by sync / sweep instead.

The response carries the access token only — never the refresh token or the
refresh bookkeeping fields.

Routes:
  POST  /agent/credentials/{credential_id}/access-token — valid access token,
        refreshed through the platform when it has less than ``min_ttl`` left;
        pushed to the agent's running envs when it differs from
        ``known_expires_at`` (the env's copy) or that is omitted
"""
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.deps import AgentEnvContextDep, SessionDep
from app.models import (
    AgentCredentialAccessTokenRequest,
    AgentCredentialAccessTokenResponse,
)
from app.services.credentials.oauth_refresh_service import (
    AgentEnvTokenError,
    OAuthRefreshService,
)

router = APIRouter(tags=["agent-credentials"])


@router.post(
    "/agent/credentials/{credential_id}/access-token",
    response_model=AgentCredentialAccessTokenResponse,
)
async def agent_credential_access_token(
    credential_id: uuid.UUID,
    body: AgentCredentialAccessTokenRequest,
    db_session: SessionDep,
    ctx: AgentEnvContextDep,
) -> Any:
    """Return an OAuth access token valid for at least ``min_ttl`` seconds.

    Errors carry ``detail = {"code", "message"}``: 404 ``credential_not_linked``,
    422 ``not_refreshable``, 409 ``reauthorization_required``,
    502 ``provider_error`` / ``refresh_in_progress`` (with ``Retry-After``),
    503 ``oauth_not_configured``.
    """
    try:
        return await OAuthRefreshService.access_token_for_env(
            db_session,
            agent_id=ctx.agent.id,
            credential_id=credential_id,
            min_ttl=body.min_ttl,
            known_expires_at=body.known_expires_at,
        )
    except AgentEnvTokenError as e:
        headers = {"Retry-After": str(e.retry_after)} if e.retry_after else None
        raise HTTPException(
            status_code=e.status,
            detail={"code": e.code, "message": e.message},
            headers=headers,
        )
