"""
App MCP OAuth flow tests — covering the per-connector-registered client fallbacks.

The core issue being tested: MCP clients that register via DCR without sending
`resource` end up in the per-connector `MCPOAuthClient` table. Downstream steps
(authorize, consent, token exchange) must still route them to App MCP paths
via fallback lookups.

Scenarios:
  1. Protected resource metadata for App MCP paths returns 200 (was returning 404)
     — both "mcp/app/mcp" and "app/mcp" path forms
  2. Per-connector paths still work (regression check)
  3. Authorize with App MCP resource URL routes to App MCP consent (302)
  4. Authorize without resource but with AppMCPOAuthClient client_id routes to App MCP
  5. Consent info shows client_name from per-connector table when client registered there
  6. Full OAuth flow: DCR without resource → authorize with app MCP resource
     → consent → token exchange
"""
import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.background_tasks import drain_tasks
from tests.utils.mcp import (
    MCP_BASE_URL,
    approve_consent,
    create_mcp_connector,
    generate_pkce_pair,
    get_protected_resource_metadata,
    register_oauth_client_without_resource,
)

# The App MCP resource URL (always rooted at MCP_BASE_URL/app/mcp)
APP_MCP_RESOURCE = f"{MCP_BASE_URL}/app/mcp"


# ── Module fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def patch_mcp_server_base_url():
    """Set MCP_SERVER_BASE_URL to the test base URL so is_app_mcp_resource() works correctly.

    is_app_mcp_resource() and get_protected_resource_metadata() both read
    settings.MCP_SERVER_BASE_URL at runtime. Without this patch they would
    compare against the production tunnel URL from .env.
    """
    with patch("app.core.config.settings.MCP_SERVER_BASE_URL", MCP_BASE_URL):
        yield


@pytest.fixture(autouse=True)
def patch_oauth_create_session(db):
    """Patch create_session in oauth_routes so OAuth DB calls use the test transaction."""
    from tests.utils.db_proxy import NonClosingSessionProxy

    factory = lambda: NonClosingSessionProxy(db)

    with patch("app.mcp.oauth_routes.create_session", factory):
        yield

# Redirect URI used throughout tests
_REDIRECT_URI = "http://localhost:3000/callback"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _register_app_mcp_client(
    client: TestClient,
    client_name: str = "Test App MCP Client",
    redirect_uris: list[str] | None = None,
    resource: str = APP_MCP_RESOURCE,
) -> dict:
    """Register an OAuth client for the App MCP Server (with resource)."""
    data = {
        "client_name": client_name,
        "redirect_uris": redirect_uris or [_REDIRECT_URI],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "resource": resource,
    }
    r = client.post("/mcp/oauth/register", json=data)
    assert r.status_code == 201, f"App MCP client registration failed: {r.text}"
    return r.json()


def _start_app_mcp_authorize(
    client: TestClient,
    oauth_client_id: str,
    resource: str = APP_MCP_RESOURCE,
    redirect_uri: str = _REDIRECT_URI,
    code_challenge: str = "",
    scope: str = "mcp:tools",
    state: str = "test-state-app-mcp",
    follow_redirects: bool = False,
) -> tuple[int, str]:
    """Hit /mcp/oauth/authorize and return (status_code, location_header)."""
    r = client.get(
        "/mcp/oauth/authorize",
        params={
            "response_type": "code",
            "client_id": oauth_client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "resource": resource,
        },
        follow_redirects=follow_redirects,
    )
    return r.status_code, r.headers.get("location", "")


def _extract_nonce(location: str) -> str:
    """Extract `nonce` query param from a consent redirect URL."""
    assert "nonce=" in location, f"No nonce in redirect URL: {location}"
    return location.split("nonce=")[1].split("&")[0]


def _exchange_app_mcp_code(
    client: TestClient,
    auth_code: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    redirect_uri: str = _REDIRECT_URI,
    code_verifier: str = "",
) -> dict:
    """Exchange an App MCP auth code for tokens."""
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
        "code_verifier": code_verifier,
        "resource": APP_MCP_RESOURCE,
    }
    r = client.post("/mcp/oauth/token", data=data)
    assert r.status_code == 200, f"App MCP token exchange failed: {r.text}"
    return r.json()


def _refresh_app_mcp_token(
    client: TestClient,
    refresh_token: str,
    oauth_client_id: str,
    oauth_client_secret: str,
) -> dict:
    """Refresh an App MCP access token."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
    }
    r = client.post("/mcp/oauth/token", data=data)
    assert r.status_code == 200, f"App MCP token refresh failed: {r.text}"
    return r.json()


# ── Scenario 1: Protected Resource Metadata for App MCP paths ────────────────


def test_protected_resource_metadata_app_mcp_paths(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    RFC 9728 Protected Resource Metadata returns 200 for App MCP paths:
      1. "mcp/app/mcp" path form → 200 with correct resource URL
      2. "app/mcp" path form → 200 with correct resource URL
      3. Both return the same resource and authorization_servers values
      4. Per-connector UUID path still returns 200 (regression check)
      5. Unknown/non-UUID non-app-mcp path returns 404
    """
    base = (settings.MCP_SERVER_BASE_URL or "").rstrip("/")

    # ── Phase 1: "mcp/app/mcp" path form returns 200 ───────────────────────
    r1 = client.get("/.well-known/oauth-protected-resource/mcp/app/mcp")
    assert r1.status_code == 200, (
        f"Expected 200 for mcp/app/mcp path, got {r1.status_code}: {r1.text}"
    )
    meta1 = r1.json()
    assert meta1["resource"] == f"{base}/app/mcp", (
        f"Expected resource={base}/app/mcp, got {meta1['resource']}"
    )
    assert f"{base}/oauth" in meta1["authorization_servers"]
    assert "bearer_methods_supported" in meta1

    # ── Phase 2: "app/mcp" path form also returns 200 ──────────────────────
    r2 = client.get("/.well-known/oauth-protected-resource/app/mcp")
    assert r2.status_code == 200, (
        f"Expected 200 for app/mcp path, got {r2.status_code}: {r2.text}"
    )
    meta2 = r2.json()
    assert meta2["resource"] == f"{base}/app/mcp"
    assert f"{base}/oauth" in meta2["authorization_servers"]

    # ── Phase 3: Both forms return the same resource URL ───────────────────
    assert meta1["resource"] == meta2["resource"]
    assert meta1["authorization_servers"] == meta2["authorization_servers"]

    # ── Phase 4: Per-connector UUID path still works (regression) ──────────
    # Create an agent + connector so we have a real UUID
    agent = create_agent_via_api(client, superuser_token_headers, name="PRM Regression Agent")
    drain_tasks()
    connector = create_mcp_connector(
        client, superuser_token_headers, agent["id"], name="PRM Connector"
    )
    connector_id = connector["id"]

    r_connector = client.get(
        f"/.well-known/oauth-protected-resource/mcp/{connector_id}/mcp"
    )
    assert r_connector.status_code == 200, (
        f"Per-connector path should still work, got {r_connector.status_code}: {r_connector.text}"
    )
    meta_connector = r_connector.json()
    assert connector_id in meta_connector["resource"]

    # ── Phase 5: Unknown non-UUID non-app-mcp path returns 404 ─────────────
    r_unknown = client.get("/.well-known/oauth-protected-resource/mcp/not-a-uuid/mcp")
    assert r_unknown.status_code == 404, (
        f"Expected 404 for unknown path, got {r_unknown.status_code}"
    )


# ── Scenario 2: Authorize with App MCP resource URL ──────────────────────────


def test_authorize_with_app_mcp_resource_routes_to_consent(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    GET /mcp/oauth/authorize with resource=<app_mcp_url> redirects to consent page:
      1. Register OAuth client in AppMCPOAuthClient (with resource)
      2. Authorize → 302 redirect to consent URL
      3. Redirect location contains nonce and app_mcp=true
      4. Consent info endpoint returns app-level metadata
    """
    # ── Phase 1: Register App MCP client ──────────────────────────────────
    oauth_client = _register_app_mcp_client(client, client_name="Authorize Test Client")
    oauth_client_id = oauth_client["client_id"]

    # ── Phase 2: Authorize → 302 redirect ─────────────────────────────────
    status, location = _start_app_mcp_authorize(
        client, oauth_client_id, resource=APP_MCP_RESOURCE
    )
    assert status == 302, f"Expected 302 redirect, got {status}"
    assert location, "Expected Location header in response"

    # ── Phase 3: Redirect URL contains nonce and app_mcp=true ─────────────
    assert "nonce=" in location, f"No nonce in redirect: {location}"
    assert "app_mcp=true" in location, f"Missing app_mcp=true in redirect: {location}"

    # ── Phase 4: Consent info returns app-level metadata ──────────────────
    nonce = _extract_nonce(location)
    r_consent = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r_consent.status_code == 200, f"Consent info failed: {r_consent.text}"
    info = r_consent.json()
    assert info["agent_name"] == "Application MCP Server"
    assert info["connector_name"] == "App MCP Server"
    assert info["client_name"] == "Authorize Test Client"


# ── Scenario 3: Authorize without resource uses AppMCPOAuthClient fallback ───


def test_authorize_without_resource_falls_back_via_app_mcp_client_id(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Authorize without resource still routes to App MCP if client_id is in AppMCPOAuthClient:
      1. Register client with resource= app_mcp → stored in AppMCPOAuthClient
      2. Authorize with resource="" (empty) → should still detect App MCP via client_id lookup
      3. 302 redirect with app_mcp=true in URL
      4. Consent info returns app-level metadata
    """
    # ── Phase 1: Register client in AppMCPOAuthClient (via resource) ──────
    oauth_client = _register_app_mcp_client(client, client_name="No Resource Auth Client")
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    # ── Phase 2: Authorize WITHOUT resource ───────────────────────────────
    status, location = _start_app_mcp_authorize(
        client, oauth_client_id, resource=""  # intentionally empty
    )
    assert status == 302, (
        f"Expected 302 even with empty resource for App MCP client, got {status}"
    )

    # ── Phase 3: Redirect still has app_mcp=true ──────────────────────────
    assert "app_mcp=true" in location, (
        f"Expected app_mcp=true in redirect even with empty resource: {location}"
    )
    assert "nonce=" in location

    # ── Phase 4: Consent info returns app-level metadata ──────────────────
    nonce = _extract_nonce(location)
    r_consent = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r_consent.status_code == 200
    info = r_consent.json()
    assert info["agent_name"] == "Application MCP Server"
    assert info["client_name"] == "No Resource Auth Client"


# ── Scenario 4: Consent info resolves client_name from per-connector table ───


def test_consent_info_resolves_client_name_from_per_connector_table(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Consent info shows client_name even when the client is registered in MCPOAuthClient
    (per-connector table) rather than AppMCPOAuthClient:
      1. Register client WITHOUT resource → stored in MCPOAuthClient (per-connector table)
      2. Authorize with App MCP resource URL → authorize detects App MCP via MCPOAuthClient
         fallback in AppMCPOAuthService.create_authorization
      3. Consent info fetches client_name from MCPOAuthClient fallback
      4. client_name is the registered value, not "Unknown Client"
    """
    # ── Phase 1: DCR without resource → stored in MCPOAuthClient ─────────
    oauth_client = register_oauth_client_without_resource(
        client, client_name="Per-Connector Registered Client"
    )
    oauth_client_id = oauth_client["client_id"]

    # ── Phase 2: Authorize with App MCP resource URL ───────────────────────
    # The client_id is NOT in AppMCPOAuthClient, but the authorize endpoint
    # must detect it as App MCP via the MCPOAuthClient fallback in
    # AppMCPOAuthService.create_authorization, triggered because the
    # authorize endpoint falls through to app_mcp path when is_app_mcp_resource(resource)=True
    status, location = _start_app_mcp_authorize(
        client, oauth_client_id, resource=APP_MCP_RESOURCE
    )
    assert status == 302, (
        f"Expected 302 for per-connector client with App MCP resource, got {status}: {location}"
    )
    assert "app_mcp=true" in location, f"Expected app_mcp=true in redirect: {location}"
    nonce = _extract_nonce(location)

    # ── Phase 3: Consent info resolves client_name from MCPOAuthClient ────
    r_consent = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r_consent.status_code == 200, f"Consent info failed: {r_consent.text}"
    info = r_consent.json()

    # ── Phase 4: client_name is resolved correctly, not "Unknown Client" ──
    assert info["client_name"] == "Per-Connector Registered Client", (
        f"Expected resolved client_name, got: {info['client_name']!r}"
    )
    assert info["agent_name"] == "Application MCP Server"


# ── Scenario 5: Full OAuth flow with App MCP resource in DCR ─────────────────


def test_full_app_mcp_oauth_flow_with_resource(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Complete App MCP OAuth flow when client registers WITH resource (happy path):
      1. DCR with app MCP resource → AppMCPOAuthClient table
      2. Authorize with PKCE and app MCP resource → 302 to consent
      3. User approves consent → auth code in redirect URL
      4. Exchange code for access + refresh tokens
      5. Refresh token → new access token
      6. Verify token structure (access_token, token_type, expires_in, scope)
    """
    code_verifier, code_challenge = generate_pkce_pair()

    # ── Phase 1: DCR with app MCP resource ────────────────────────────────
    oauth_client = _register_app_mcp_client(
        client, client_name="Full Flow Client (with resource)"
    )
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]
    assert oauth_client_id
    assert oauth_client_secret

    # ── Phase 2: Authorize → 302 to consent ───────────────────────────────
    status, location = _start_app_mcp_authorize(
        client, oauth_client_id,
        resource=APP_MCP_RESOURCE,
        code_challenge=code_challenge,
    )
    assert status == 302
    assert "app_mcp=true" in location
    nonce = _extract_nonce(location)

    # ── Phase 3: User approves consent → auth code ────────────────────────
    approval = approve_consent(client, superuser_token_headers, nonce)
    redirect_url = approval["redirect_url"]
    assert "code=" in redirect_url, f"No code in redirect URL: {redirect_url}"
    auth_code = redirect_url.split("code=")[1].split("&")[0]
    assert auth_code

    # ── Phase 4: Exchange code for tokens ─────────────────────────────────
    tokens = _exchange_app_mcp_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        code_verifier=code_verifier,
    )
    assert "access_token" in tokens
    assert tokens["token_type"] == "bearer"
    assert "expires_in" in tokens
    assert "refresh_token" in tokens

    # ── Phase 5: Refresh → new access token ───────────────────────────────
    refreshed = _refresh_app_mcp_token(
        client, tokens["refresh_token"], oauth_client_id, oauth_client_secret
    )
    assert "access_token" in refreshed
    assert refreshed["access_token"] != tokens["access_token"], (
        "Refreshed access_token should differ from original"
    )


# ── Scenario 6: Full OAuth flow with per-connector registered client ──────────


def test_full_app_mcp_oauth_flow_client_registered_without_resource(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Complete App MCP OAuth flow when client registers WITHOUT resource
    (client lands in MCPOAuthClient per-connector table):
      1. DCR without resource → MCPOAuthClient table (global client)
      2. Authorize with app MCP resource URL → is_app_mcp_resource detects App MCP
         → AppMCPOAuthService.create_authorization uses MCPOAuthClient fallback → 302
      3. Consent page shows correct client_name from MCPOAuthClient
      4. User approves → auth code
      5. Token exchange: detect App MCP via AppMCPAuthCode lookup → success
      6. Refresh: detect App MCP via AppMCPToken lookup → success
    """
    code_verifier, code_challenge = generate_pkce_pair()

    # ── Phase 1: DCR without resource ─────────────────────────────────────
    oauth_client = register_oauth_client_without_resource(
        client, client_name="No-Resource Full Flow Client"
    )
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]
    assert oauth_client_id
    assert oauth_client_secret

    # ── Phase 2: Authorize with App MCP resource → 302 ────────────────────
    status, location = _start_app_mcp_authorize(
        client, oauth_client_id,
        resource=APP_MCP_RESOURCE,
        code_challenge=code_challenge,
    )
    assert status == 302, (
        f"Expected 302 for DCR-without-resource client with App MCP resource, got {status}"
    )
    assert "app_mcp=true" in location, f"Expected app_mcp=true in location: {location}"
    nonce = _extract_nonce(location)

    # ── Phase 3: Consent shows correct client_name ────────────────────────
    r_consent = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r_consent.status_code == 200
    consent_info = r_consent.json()
    assert consent_info["client_name"] == "No-Resource Full Flow Client", (
        f"Expected resolved client name, got: {consent_info['client_name']!r}"
    )
    assert consent_info["agent_name"] == "Application MCP Server"

    # ── Phase 4: User approves → auth code ────────────────────────────────
    approval = approve_consent(client, superuser_token_headers, nonce)
    redirect_url = approval["redirect_url"]
    assert "code=" in redirect_url, f"No code in redirect URL: {redirect_url}"
    auth_code = redirect_url.split("code=")[1].split("&")[0]

    # ── Phase 5: Token exchange detects App MCP via AppMCPAuthCode ─────────
    tokens = _exchange_app_mcp_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        code_verifier=code_verifier,
    )
    assert "access_token" in tokens, f"Missing access_token: {tokens}"
    assert tokens["token_type"] == "bearer"
    assert "refresh_token" in tokens, f"Missing refresh_token: {tokens}"

    # ── Phase 6: Token refresh detects App MCP via AppMCPToken ─────────────
    refreshed = _refresh_app_mcp_token(
        client, tokens["refresh_token"], oauth_client_id, oauth_client_secret
    )
    assert "access_token" in refreshed, f"Missing access_token in refresh: {refreshed}"
    assert refreshed["access_token"] != tokens["access_token"], (
        "Refreshed token should differ from original"
    )


# ── Scenario 7: Token exchange rejects invalid code/credentials ──────────────


def test_app_mcp_token_exchange_error_cases(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Token exchange rejects invalid inputs with 400:
      1. Wrong client_secret returns 400
      2. Replayed auth code returns 400
      3. Invalid (garbage) auth code returns 400
    """
    code_verifier, code_challenge = generate_pkce_pair()

    # Setup: register client, authorize, approve → get valid code
    oauth_client = _register_app_mcp_client(client, client_name="Error Cases Client")
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    status, location = _start_app_mcp_authorize(
        client, oauth_client_id,
        resource=APP_MCP_RESOURCE,
        code_challenge=code_challenge,
    )
    assert status == 302
    nonce = _extract_nonce(location)
    approval = approve_consent(client, superuser_token_headers, nonce)
    auth_code = approval["redirect_url"].split("code=")[1].split("&")[0]

    # ── Phase 1: Wrong client_secret returns 400 ──────────────────────────
    r_bad_secret = client.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": _REDIRECT_URI,
            "client_id": oauth_client_id,
            "client_secret": "wrong-secret-value",
            "code_verifier": code_verifier,
        },
    )
    assert r_bad_secret.status_code == 400, (
        f"Expected 400 for wrong secret, got {r_bad_secret.status_code}: {r_bad_secret.text}"
    )

    # ── Phase 2: Valid code exchange succeeds (consume the code) ──────────
    tokens = _exchange_app_mcp_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        code_verifier=code_verifier,
    )
    assert "access_token" in tokens

    # ── Phase 3: Replayed (already used) auth code returns 400 ────────────
    r_replay = client.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": auth_code,  # same code, already used
            "redirect_uri": _REDIRECT_URI,
            "client_id": oauth_client_id,
            "client_secret": oauth_client_secret,
            "code_verifier": code_verifier,
        },
    )
    assert r_replay.status_code == 400, (
        f"Expected 400 for replayed code, got {r_replay.status_code}: {r_replay.text}"
    )

    # ── Phase 4: Completely invalid code returns 400 ──────────────────────
    r_garbage = client.post(
        "/mcp/oauth/token",
        data={
            "grant_type": "authorization_code",
            "code": "garbage-code-that-does-not-exist",
            "redirect_uri": _REDIRECT_URI,
            "client_id": oauth_client_id,
            "client_secret": oauth_client_secret,
        },
    )
    assert r_garbage.status_code == 400, (
        f"Expected 400 for garbage code, got {r_garbage.status_code}: {r_garbage.text}"
    )
