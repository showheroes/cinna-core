"""
MCP OAuth integration tests — full user-scenario tests.

Covers the complete OAuth 2.1 flow for MCP integration:
  - AS metadata discovery
  - Dynamic Client Registration (DCR)
  - Authorization → consent → code exchange → token issuance
  - Token refresh
  - Token revocation
  - PKCE verification
  - Error cases: expired nonce, wrong credentials, cross-connector tokens,
    DCR limit enforcement, email ACL on consent
"""
import hashlib
import uuid
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.mcp import (
    MCP_BASE_URL,
    approve_consent,
    create_mcp_connector,
    exchange_auth_code,
    generate_pkce_pair,
    get_as_metadata,
    get_consent_info,
    refresh_access_token,
    register_oauth_client,
    revoke_token,
    run_full_oauth_flow,
    start_authorize,
)
from tests.utils.user import create_random_user_with_headers


# ── Helpers ──────────────────────────────────────────────────────────────────


def _setup_agent_with_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_name: str = "MCP OAuth Agent",
    connector_name: str = "OAuth Connector",
    mode: str = "conversation",
    allowed_emails: list[str] | None = None,
    max_clients: int = 10,
) -> tuple[dict, dict]:
    """Create agent + connector. Returns (agent, connector)."""
    agent = create_agent_via_api(client, token_headers, name=agent_name)
    drain_tasks()
    agent = get_agent(client, token_headers, agent["id"])
    connector = create_mcp_connector(
        client, token_headers, agent["id"],
        name=connector_name, mode=mode,
        allowed_emails=allowed_emails or [],
        max_clients=max_clients,
    )
    return agent, connector


# ── Tests ────────────────────────────────────────────────────────────────────


def test_as_metadata_endpoint(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    AS metadata returns correct endpoints and supported features:
      1. Fetch /.well-known/oauth-authorization-server
      2. Verify issuer, all endpoint URLs, and supported features
    """
    metadata = get_as_metadata(client)

    assert metadata["issuer"] == f"{MCP_BASE_URL}/oauth"
    assert metadata["authorization_endpoint"] == f"{MCP_BASE_URL}/oauth/authorize"
    assert metadata["token_endpoint"] == f"{MCP_BASE_URL}/oauth/token"
    assert metadata["registration_endpoint"] == f"{MCP_BASE_URL}/oauth/register"
    assert metadata["revocation_endpoint"] == f"{MCP_BASE_URL}/oauth/revoke"
    assert "code" in metadata["response_types_supported"]
    assert "authorization_code" in metadata["grant_types_supported"]
    assert "refresh_token" in metadata["grant_types_supported"]
    assert "S256" in metadata["code_challenge_methods_supported"]
    assert "mcp:tools" in metadata["scopes_supported"]


def test_full_oauth_flow_without_pkce(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full OAuth flow end-to-end (no PKCE):
      1. Create agent + connector
      2. Register OAuth client (DCR)
      3. Start authorization → get nonce (302 redirect)
      4. Fetch consent info → verify agent/connector/client details
      5. Approve consent → get auth code in redirect URL
      6. Exchange auth code for access + refresh tokens
      7. Verify token response fields
    """
    # ── Phase 1: Setup ────────────────────────────────────────────────────
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="OAuth Full Flow Agent",
        connector_name="Full Flow Connector",
    )
    connector_id = connector["id"]

    # ── Phase 2: Register OAuth client ────────────────────────────────────
    oauth_client = register_oauth_client(
        client, connector_id, client_name="Claude Desktop",
    )
    assert "client_id" in oauth_client
    assert "client_secret" in oauth_client
    assert oauth_client["client_name"] == "Claude Desktop"
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    # ── Phase 3: Start authorization ──────────────────────────────────────
    nonce = start_authorize(
        client, oauth_client_id, connector_id,
        scope="mcp:tools",
        state="my-state-123",
    )
    assert len(nonce) > 10  # Reasonable nonce length

    # ── Phase 4: Fetch consent info ───────────────────────────────────────
    consent = get_consent_info(client, nonce)
    assert consent["agent_name"] == "OAuth Full Flow Agent"
    assert consent["connector_name"] == "Full Flow Connector"
    assert consent["connector_mode"] == "conversation"
    assert consent["client_name"] == "Claude Desktop"
    assert "mcp:tools" in consent["scopes"]

    # ── Phase 5: Approve consent ──────────────────────────────────────────
    approval = approve_consent(client, superuser_token_headers, nonce)
    redirect_url = approval["redirect_url"]

    assert redirect_url.startswith("http://localhost:3000/callback?")
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    assert "code" in params
    assert params["state"] == ["my-state-123"]
    auth_code = params["code"][0]

    # ── Phase 6: Exchange code for tokens ─────────────────────────────────
    tokens = exchange_auth_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        connector_id,
    )
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 3600
    assert tokens["scope"] == "mcp:tools"


def test_full_oauth_flow_with_pkce(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full OAuth flow with PKCE (S256):
      1. Create agent + connector
      2. Register OAuth client
      3. Generate PKCE pair (code_verifier + code_challenge)
      4. Start authorize with code_challenge
      5. Approve consent → get auth code
      6. Exchange with correct code_verifier → success
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="PKCE Agent",
    )
    connector_id = connector["id"]

    # Register client
    oauth_client = register_oauth_client(client, connector_id)
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    # Generate PKCE pair
    code_verifier, code_challenge = generate_pkce_pair()

    # Authorize with code_challenge
    nonce = start_authorize(
        client, oauth_client_id, connector_id,
        code_challenge=code_challenge,
    )

    # Approve consent
    approval = approve_consent(client, superuser_token_headers, nonce)
    auth_code = approval["redirect_url"].split("code=")[1].split("&")[0]

    # Exchange with correct code_verifier
    tokens = exchange_auth_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        connector_id, code_verifier=code_verifier,
    )
    assert "access_token" in tokens
    assert "refresh_token" in tokens


def test_pkce_wrong_verifier_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    PKCE with wrong code_verifier is rejected:
      1. Start OAuth flow with PKCE
      2. Approve consent → get auth code
      3. Exchange with wrong code_verifier → 400
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Bad PKCE Agent",
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    _, code_challenge = generate_pkce_pair()
    nonce = start_authorize(
        client, oauth_client_id, connector_id,
        code_challenge=code_challenge,
    )
    approval = approve_consent(client, superuser_token_headers, nonce)
    auth_code = approval["redirect_url"].split("code=")[1].split("&")[0]

    # Exchange with WRONG code_verifier
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": "http://localhost:3000/callback",
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
        "code_verifier": "wrong-verifier-that-does-not-match",
        "resource": resource,
    })
    assert r.status_code == 400
    assert "code_verifier" in r.json()["detail"].lower()


def test_token_refresh_flow(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Token refresh:
      1. Complete full OAuth flow → get access + refresh tokens
      2. Use refresh token to get a new access token
      3. Verify new access token is different from original
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Refresh Agent",
    )
    connector_id = connector["id"]

    flow = run_full_oauth_flow(client, superuser_token_headers, connector_id)
    original_access = flow["access_token"]

    # Refresh
    new_tokens = refresh_access_token(
        client, flow["refresh_token"],
        flow["oauth_client_id"], flow["oauth_client_secret"],
    )
    assert "access_token" in new_tokens
    assert new_tokens["access_token"] != original_access
    assert new_tokens["token_type"] == "bearer"
    assert new_tokens["expires_in"] == 3600


def test_token_revocation(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Token revocation:
      1. Complete full OAuth flow → get tokens
      2. Revoke access token → 200 (per RFC 7009)
      3. Revoke refresh token → 200
      4. Try to refresh with revoked refresh token → 400
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Revoke Agent",
    )
    connector_id = connector["id"]

    flow = run_full_oauth_flow(client, superuser_token_headers, connector_id)

    # Revoke access token
    status = revoke_token(client, flow["access_token"])
    assert status == 200

    # Revoke refresh token
    status = revoke_token(client, flow["refresh_token"])
    assert status == 200

    # Try to refresh with revoked token → 400
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "refresh_token",
        "refresh_token": flow["refresh_token"],
        "client_id": flow["oauth_client_id"],
        "client_secret": flow["oauth_client_secret"],
    })
    assert r.status_code == 400
    assert "revoked" in r.json()["detail"].lower()


def test_revoke_nonexistent_token_returns_200(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """RFC 7009: revoking a nonexistent token always returns 200."""
    status = revoke_token(client, "nonexistent-token-value")
    assert status == 200


def test_dcr_limit_enforcement(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    DCR limit enforcement:
      1. Create connector with max_clients=2
      2. Register 2 clients → success
      3. Register 3rd client → 429
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="DCR Limit Agent",
        max_clients=2,
    )
    connector_id = connector["id"]

    # Register up to the limit
    register_oauth_client(client, connector_id, client_name="Client 1")
    register_oauth_client(client, connector_id, client_name="Client 2")

    # Third should fail
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    r = client.post("/mcp/oauth/register", json={
        "client_name": "Client 3",
        "redirect_uris": ["http://localhost:3000/callback"],
        "resource": resource,
    })
    assert r.status_code == 429
    assert "maximum" in r.json()["detail"].lower()


def test_dcr_inactive_connector_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    DCR on inactive connector:
      1. Create connector
      2. Deactivate connector
      3. Attempt DCR → 404
    """
    from tests.utils.mcp import update_mcp_connector

    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Inactive DCR Agent",
    )
    connector_id = connector["id"]
    agent_id = agent["id"]

    # Deactivate
    update_mcp_connector(
        client, superuser_token_headers, agent_id, connector_id,
        is_active=False,
    )

    # Attempt DCR → 404
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    r = client.post("/mcp/oauth/register", json={
        "client_name": "Fail Client",
        "redirect_uris": ["http://localhost:3000/callback"],
        "resource": resource,
    })
    assert r.status_code == 404


def test_dcr_invalid_resource_url(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """DCR with invalid resource URL returns 400."""
    r = client.post("/mcp/oauth/register", json={
        "client_name": "Bad Resource Client",
        "redirect_uris": ["http://localhost:3000/callback"],
        "resource": "http://evil.com/not-a-real-resource",
    })
    assert r.status_code == 400


def test_authorize_unknown_client_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Authorization with an unknown client_id returns 400.
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Unknown Client Agent",
    )
    connector_id = connector["id"]
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"

    r = client.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": "nonexistent-client-id",
            "redirect_uri": "http://localhost:3000/callback",
            "scope": "mcp:tools",
            "resource": resource,
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_consent_nonce_expired(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Consent with a nonexistent nonce returns 404.
    """
    r = client.get(f"{settings.API_V1_STR}/mcp/consent/nonexistent-nonce")
    assert r.status_code == 404


def test_consent_nonce_reuse_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Consent nonce can only be used once:
      1. Complete authorization → get nonce
      2. Approve once → success
      3. Try to approve again → 400 (already used)
      4. Try to get consent info again → 400 (already used)
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Nonce Reuse Agent",
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    nonce = start_authorize(client, oauth_client["client_id"], connector_id)

    # First approval → success
    approve_consent(client, superuser_token_headers, nonce)

    # Second approval → 400
    r = client.post(
        f"{settings.API_V1_STR}/mcp/consent/{nonce}/approve",
        headers=superuser_token_headers,
    )
    assert r.status_code == 400
    assert "already used" in r.json()["detail"].lower()

    # Get info also rejects used nonce
    r = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r.status_code == 400


def test_auth_code_reuse_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Auth code can only be exchanged once:
      1. Complete flow up to code exchange → success
      2. Try to exchange same code again → 400
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Code Reuse Agent",
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    nonce = start_authorize(client, oauth_client["client_id"], connector_id)
    approval = approve_consent(client, superuser_token_headers, nonce)
    auth_code = approval["redirect_url"].split("code=")[1].split("&")[0]

    # First exchange → success
    exchange_auth_code(
        client, auth_code, oauth_client["client_id"], oauth_client["client_secret"],
        connector_id,
    )

    # Second exchange → 400
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": "http://localhost:3000/callback",
        "client_id": oauth_client["client_id"],
        "client_secret": oauth_client["client_secret"],
        "resource": resource,
    })
    assert r.status_code == 400
    assert "already used" in r.json()["detail"].lower()


def test_wrong_client_secret_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Token exchange with wrong client_secret returns 401.
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Bad Secret Agent",
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    nonce = start_authorize(client, oauth_client["client_id"], connector_id)
    approval = approve_consent(client, superuser_token_headers, nonce)
    auth_code = approval["redirect_url"].split("code=")[1].split("&")[0]

    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": "http://localhost:3000/callback",
        "client_id": oauth_client["client_id"],
        "client_secret": "wrong-secret",
        "resource": resource,
    })
    assert r.status_code == 401


def test_consent_email_acl_enforcement(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Email ACL on consent:
      1. Create connector with allowed_emails = [specific email]
      2. Create a different user (email not in list)
      3. Start OAuth flow → get nonce
      4. Other user tries to approve → 403
      5. Owner approves → success
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="ACL Agent",
        allowed_emails=["allowed@example.com"],
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    nonce = start_authorize(client, oauth_client["client_id"], connector_id)

    # Create a user whose email is NOT in allowed_emails
    _, other_headers = create_random_user_with_headers(client)

    # Other user tries to approve → 403
    r = client.post(
        f"{settings.API_V1_STR}/mcp/consent/{nonce}/approve",
        headers=other_headers,
    )
    assert r.status_code == 403

    # Owner approves → success
    approval = approve_consent(client, superuser_token_headers, nonce)
    assert "redirect_url" in approval


def test_consent_unauthenticated_approve_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Consent approval without authentication returns 401."""
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Unauth Consent Agent",
    )
    connector_id = connector["id"]

    oauth_client = register_oauth_client(client, connector_id)
    nonce = start_authorize(client, oauth_client["client_id"], connector_id)

    # Approve without auth headers
    r = client.post(f"{settings.API_V1_STR}/mcp/consent/{nonce}/approve")
    assert r.status_code == 401


def test_unsupported_response_type(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Authorization with unsupported response_type returns 400."""
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Bad ResponseType Agent",
    )
    connector_id = connector["id"]
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"

    r = client.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "token",  # not supported
            "client_id": "some-client",
            "redirect_uri": "http://localhost:3000/callback",
            "resource": resource,
        },
        follow_redirects=False,
    )
    assert r.status_code == 400


def test_unsupported_grant_type(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """Token endpoint with unsupported grant_type returns 400."""
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "client_credentials",
        "client_id": "some-client",
        "client_secret": "some-secret",
    })
    assert r.status_code == 400


def test_full_scenario_agent_mcp_enable_oauth_connect(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    End-to-end user scenario: an agent owner sets up MCP and a client connects.

      1. Create an agent
      2. Create an MCP connector in conversation mode
      3. Verify connector has mcp_server_url
      4. MCP client discovers AS metadata
      5. MCP client registers via DCR
      6. MCP client starts OAuth authorization
      7. Owner sees consent page with correct details
      8. Owner approves → redirect with auth code
      9. MCP client exchanges code for tokens (with PKCE)
      10. MCP client refreshes the access token
      11. Owner revokes the refresh token
      12. MCP client's refresh attempt fails
    """
    # ── Phase 1-2: Create agent + connector ───────────────────────────────
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Full Scenario Agent",
        connector_name="Production Connector",
        mode="conversation",
    )
    agent_id = agent["id"]
    connector_id = connector["id"]

    # ── Phase 3: Verify mcp_server_url ────────────────────────────────────
    assert connector["mcp_server_url"] == f"{MCP_BASE_URL}/{connector_id}/mcp"

    # ── Phase 4: Discover AS metadata ─────────────────────────────────────
    metadata = get_as_metadata(client)
    assert "registration_endpoint" in metadata
    assert "authorization_endpoint" in metadata

    # ── Phase 5: Register via DCR ─────────────────────────────────────────
    oauth_client = register_oauth_client(
        client, connector_id, client_name="Claude Desktop",
    )
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    # ── Phase 6: Start authorization with PKCE ────────────────────────────
    code_verifier, code_challenge = generate_pkce_pair()
    nonce = start_authorize(
        client, oauth_client_id, connector_id,
        code_challenge=code_challenge,
        scope="mcp:tools mcp:resources",
        state="session-xyz",
    )

    # ── Phase 7: Owner views consent page ─────────────────────────────────
    consent = get_consent_info(client, nonce)
    assert consent["agent_name"] == "Full Scenario Agent"
    assert consent["connector_name"] == "Production Connector"
    assert consent["client_name"] == "Claude Desktop"
    assert "mcp:tools" in consent["scopes"]
    assert "mcp:resources" in consent["scopes"]

    # ── Phase 8: Owner approves ───────────────────────────────────────────
    approval = approve_consent(client, superuser_token_headers, nonce)
    redirect_url = approval["redirect_url"]
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)
    assert params["state"] == ["session-xyz"]
    auth_code = params["code"][0]

    # ── Phase 9: Exchange code with PKCE ──────────────────────────────────
    tokens = exchange_auth_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        connector_id, code_verifier=code_verifier,
    )
    access_token = tokens["access_token"]
    refresh_token_val = tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"
    assert tokens["expires_in"] == 3600

    # ── Phase 10: Refresh access token ────────────────────────────────────
    refreshed = refresh_access_token(
        client, refresh_token_val,
        oauth_client_id, oauth_client_secret,
    )
    new_access = refreshed["access_token"]
    assert new_access != access_token

    # ── Phase 11: Owner revokes refresh token ─────────────────────────────
    status = revoke_token(client, refresh_token_val)
    assert status == 200

    # ── Phase 12: Refresh attempt fails ───────────────────────────────────
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_val,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
    })
    assert r.status_code == 400


def test_multiple_clients_same_connector(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Multiple OAuth clients on the same connector:
      1. Create agent + connector
      2. Register 2 different OAuth clients
      3. Both go through full OAuth flow independently
      4. Both get unique tokens
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Multi Client Agent",
        max_clients=5,
    )
    connector_id = connector["id"]

    # Two clients go through the full flow
    flow1 = run_full_oauth_flow(
        client, superuser_token_headers, connector_id,
        client_name="Client A",
    )
    flow2 = run_full_oauth_flow(
        client, superuser_token_headers, connector_id,
        client_name="Client B",
    )

    # Unique tokens
    assert flow1["access_token"] != flow2["access_token"]
    assert flow1["refresh_token"] != flow2["refresh_token"]
    assert flow1["oauth_client_id"] != flow2["oauth_client_id"]


def test_wrong_client_id_on_refresh_rejected(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Refresh token bound to its client — using a different client_id fails.
    """
    agent, connector = _setup_agent_with_connector(
        client, superuser_token_headers,
        agent_name="Cross Client Refresh Agent",
        max_clients=5,
    )
    connector_id = connector["id"]

    # Two clients, both complete OAuth
    flow_a = run_full_oauth_flow(
        client, superuser_token_headers, connector_id,
        client_name="Client A",
    )
    flow_b = run_full_oauth_flow(
        client, superuser_token_headers, connector_id,
        client_name="Client B",
    )

    # Try to refresh client A's token using client B's credentials → 400
    r = client.post("/mcp/oauth/token", json={
        "grant_type": "refresh_token",
        "refresh_token": flow_a["refresh_token"],
        "client_id": flow_b["oauth_client_id"],
        "client_secret": flow_b["oauth_client_secret"],
    })
    assert r.status_code == 400


def test_dcr_on_nonexistent_connector(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """DCR with a resource URL pointing to a nonexistent connector returns 404."""
    fake_id = str(uuid.uuid4())
    resource = f"{MCP_BASE_URL}/{fake_id}/mcp"
    r = client.post("/mcp/oauth/register", json={
        "client_name": "Ghost Client",
        "redirect_uris": ["http://localhost:3000/callback"],
        "resource": resource,
    })
    assert r.status_code == 404
