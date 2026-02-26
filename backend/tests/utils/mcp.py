"""Helpers for MCP integration tests."""
import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, UTC

from fastapi.testclient import TestClient

from app.core.config import settings

MCP_BASE_URL = "http://localhost:8000/mcp"


# ── Connector CRUD helpers ───────────────────────────────────────────────────


def create_mcp_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    name: str = "Test MCP Connector",
    mode: str = "conversation",
    allowed_emails: list[str] | None = None,
    max_clients: int = 10,
) -> dict:
    """Create an MCP connector via POST /agents/{id}/mcp-connectors."""
    data = {
        "name": name,
        "mode": mode,
        "allowed_emails": allowed_emails or [],
        "max_clients": max_clients,
    }
    r = client.post(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors",
        headers=token_headers,
        json=data,
    )
    assert r.status_code == 200, f"Create MCP connector failed: {r.text}"
    return r.json()


def list_mcp_connectors(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
) -> dict:
    """List MCP connectors via GET /agents/{id}/mcp-connectors."""
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors",
        headers=token_headers,
    )
    assert r.status_code == 200, f"List MCP connectors failed: {r.text}"
    return r.json()


def get_mcp_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    connector_id: str,
) -> dict:
    """Get a specific MCP connector via GET /agents/{id}/mcp-connectors/{cid}."""
    r = client.get(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=token_headers,
    )
    assert r.status_code == 200, f"Get MCP connector failed: {r.text}"
    return r.json()


def update_mcp_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    connector_id: str,
    **fields,
) -> dict:
    """Update an MCP connector via PUT /agents/{id}/mcp-connectors/{cid}."""
    r = client.put(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=token_headers,
        json=fields,
    )
    assert r.status_code == 200, f"Update MCP connector failed: {r.text}"
    return r.json()


def delete_mcp_connector(
    client: TestClient,
    token_headers: dict[str, str],
    agent_id: str,
    connector_id: str,
) -> dict:
    """Delete an MCP connector via DELETE /agents/{id}/mcp-connectors/{cid}."""
    r = client.delete(
        f"{settings.API_V1_STR}/agents/{agent_id}/mcp-connectors/{connector_id}",
        headers=token_headers,
    )
    assert r.status_code == 200, f"Delete MCP connector failed: {r.text}"
    return r.json()


# ── OAuth flow helpers ───────────────────────────────────────────────────────


def register_oauth_client(
    client: TestClient,
    connector_id: str,
    client_name: str = "Test MCP Client",
    redirect_uris: list[str] | None = None,
) -> dict:
    """Register an OAuth client via POST /mcp/oauth/register."""
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    data = {
        "client_name": client_name,
        "redirect_uris": redirect_uris or ["http://localhost:3000/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "resource": resource,
    }
    r = client.post("/mcp/oauth/register", json=data)
    assert r.status_code == 201, f"OAuth client registration failed: {r.text}"
    return r.json()


def get_as_metadata(client: TestClient) -> dict:
    """Get OAuth AS metadata via GET /mcp/oauth/.well-known/oauth-authorization-server."""
    r = client.get("/mcp/oauth/.well-known/oauth-authorization-server")
    assert r.status_code == 200, f"AS metadata fetch failed: {r.text}"
    return r.json()


def start_authorize(
    client: TestClient,
    oauth_client_id: str,
    connector_id: str,
    redirect_uri: str = "http://localhost:3000/callback",
    code_challenge: str = "",
    scope: str = "mcp:tools",
    state: str = "test-state-123",
) -> str:
    """
    Hit the OAuth /authorize endpoint and extract the nonce from the redirect.

    Returns the nonce string. Uses allow_redirects=False to capture the 302.
    """
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
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
        follow_redirects=False,
    )
    assert r.status_code == 302, f"OAuth authorize did not redirect: {r.status_code} {r.text}"
    location = r.headers["location"]
    # Extract nonce from redirect URL: .../mcp-consent?nonce=<nonce>
    assert "nonce=" in location, f"No nonce in redirect URL: {location}"
    nonce = location.split("nonce=")[1].split("&")[0]
    return nonce


def get_consent_info(
    client: TestClient,
    nonce: str,
) -> dict:
    """Get consent page info via GET /api/v1/mcp/consent/{nonce}."""
    r = client.get(f"{settings.API_V1_STR}/mcp/consent/{nonce}")
    assert r.status_code == 200, f"Get consent info failed: {r.text}"
    return r.json()


def approve_consent(
    client: TestClient,
    token_headers: dict[str, str],
    nonce: str,
) -> dict:
    """Approve OAuth consent via POST /api/v1/mcp/consent/{nonce}/approve."""
    r = client.post(
        f"{settings.API_V1_STR}/mcp/consent/{nonce}/approve",
        headers=token_headers,
    )
    assert r.status_code == 200, f"Consent approval failed: {r.text}"
    return r.json()


def exchange_auth_code(
    client: TestClient,
    auth_code: str,
    oauth_client_id: str,
    oauth_client_secret: str,
    connector_id: str,
    redirect_uri: str = "http://localhost:3000/callback",
    code_verifier: str = "",
) -> dict:
    """Exchange auth code for tokens via POST /mcp/oauth/token (form-encoded)."""
    resource = f"{MCP_BASE_URL}/{connector_id}/mcp"
    data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": redirect_uri,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
        "code_verifier": code_verifier,
        "resource": resource,
    }
    r = client.post("/mcp/oauth/token", data=data)
    assert r.status_code == 200, f"Token exchange failed: {r.text}"
    return r.json()


def refresh_access_token(
    client: TestClient,
    refresh_token: str,
    oauth_client_id: str,
    oauth_client_secret: str,
) -> dict:
    """Refresh an access token via POST /mcp/oauth/token (form-encoded)."""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
    }
    r = client.post("/mcp/oauth/token", data=data)
    assert r.status_code == 200, f"Token refresh failed: {r.text}"
    return r.json()


def revoke_token(
    client: TestClient,
    token: str,
    oauth_client_id: str = "",
    oauth_client_secret: str = "",
) -> int:
    """Revoke a token via POST /mcp/oauth/revoke (form-encoded). Returns HTTP status code."""
    data = {
        "token": token,
        "client_id": oauth_client_id,
        "client_secret": oauth_client_secret,
    }
    r = client.post("/mcp/oauth/revoke", data=data)
    return r.status_code


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier + code_challenge (S256) pair."""
    import base64
    code_verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def run_full_oauth_flow(
    client: TestClient,
    token_headers: dict[str, str],
    connector_id: str,
    client_name: str = "Test MCP Client",
    use_pkce: bool = False,
) -> dict:
    """Run the complete OAuth flow from DCR to token exchange.

    Returns a dict with keys: oauth_client_id, oauth_client_secret,
    access_token, refresh_token, scope, nonce, auth_code.
    """
    code_verifier, code_challenge = generate_pkce_pair() if use_pkce else ("", "")

    # Step 1: Register OAuth client
    oauth_client = register_oauth_client(client, connector_id, client_name=client_name)
    oauth_client_id = oauth_client["client_id"]
    oauth_client_secret = oauth_client["client_secret"]

    # Step 2: Start authorize → get nonce
    nonce = start_authorize(
        client, oauth_client_id, connector_id,
        code_challenge=code_challenge,
    )

    # Step 3: Approve consent
    approval = approve_consent(client, token_headers, nonce)
    redirect_url = approval["redirect_url"]
    auth_code = redirect_url.split("code=")[1].split("&")[0]

    # Step 4: Exchange code for tokens
    tokens = exchange_auth_code(
        client, auth_code, oauth_client_id, oauth_client_secret,
        connector_id, code_verifier=code_verifier,
    )

    return {
        "oauth_client_id": oauth_client_id,
        "oauth_client_secret": oauth_client_secret,
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "scope": tokens.get("scope", ""),
        "nonce": nonce,
        "auth_code": auth_code,
    }


# ── Root-level well-known endpoint helpers ────────────────────────────────────


def get_as_metadata_root_level(
    client: TestClient,
    path: str = "",
) -> dict:
    """Get OAuth AS metadata via root-level well-known URL (RFC 8414).

    Args:
        path: Optional issuer path suffix (e.g. "mcp/oauth"). If empty,
              hits the exact path /.well-known/oauth-authorization-server.
    """
    if path:
        url = f"/.well-known/oauth-authorization-server/{path}"
    else:
        url = "/.well-known/oauth-authorization-server"
    r = client.get(url)
    assert r.status_code == 200, f"Root-level AS metadata fetch failed: {r.text}"
    return r.json()


def get_protected_resource_metadata(
    client: TestClient,
    connector_id: str,
) -> dict:
    """Get OAuth Protected Resource Metadata via root-level well-known URL (RFC 9728).

    Fetches: /.well-known/oauth-protected-resource/mcp/{connector_id}/mcp
    """
    r = client.get(f"/.well-known/oauth-protected-resource/mcp/{connector_id}/mcp")
    assert r.status_code == 200, f"Protected resource metadata fetch failed: {r.text}"
    return r.json()


def register_oauth_client_without_resource(
    client: TestClient,
    client_name: str = "Test MCP Client",
    redirect_uris: list[str] | None = None,
) -> dict:
    """Register an OAuth client via DCR without a resource URL.

    Some MCP clients (e.g. Claude Desktop) don't send the `resource`
    field during DCR. The client is registered globally.
    """
    data = {
        "client_name": client_name,
        "redirect_uris": redirect_uris or ["http://localhost:3000/callback"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    }
    r = client.post("/mcp/oauth/register", json=data)
    assert r.status_code == 201, f"OAuth client registration (no resource) failed: {r.text}"
    return r.json()
