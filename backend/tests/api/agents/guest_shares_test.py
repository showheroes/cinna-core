"""
Integration test: guest share link CRUD lifecycle.

Tests the full user story for managing guest share links:
  1. User creates an agent
  2. User creates a guest share link → verify response includes token, share_url
  3. User lists guest shares → verify shares returned with session_count
  4. User gets a single guest share → verify correct data
  5. User deletes a guest share → verify deletion
  6. Another user cannot manage another user's agent's guest shares
  7. Listing returns empty for agent with no shares

Only environment adapter is stubbed (via conftest autouse fixtures).
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api
from tests.utils.background_tasks import drain_tasks
from tests.utils.guest_share import (
    create_guest_share,
    delete_guest_share,
    get_guest_share,
    list_guest_shares,
    setup_guest_share_agent,
)
from tests.utils.user import create_random_user_with_headers

API = settings.API_V1_STR


# ── Tests ────────────────────────────────────────────────────────────────


def test_guest_share_full_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full CRUD lifecycle for a single guest share:
      1. Create agent + guest share → verify one-time token and share_url
      2. List guest shares → verify it appears with session_count=0
      3. Get guest share by ID → verify fields
      4. Delete guest share
      5. Verify it's gone (list empty + GET 404)
    """
    # ── Phase 1: Create agent + guest share ────────────────────────────────

    agent, created = setup_guest_share_agent(
        client, superuser_token_headers,
        name="Guest Share Lifecycle Agent",
        share_label="Test Share Link",
        expires_in_hours=48,
    )
    agent_id = agent["id"]
    share_id = created["id"]

    assert "token" in created, "Raw token must be returned on creation"
    assert len(created["token"]) > 0, "Token must be non-empty"
    assert "share_url" in created, "Share URL must be returned on creation"
    assert created["token"] in created["share_url"], "Share URL must contain the token"
    assert "/guest/" in created["share_url"], "Share URL must contain /guest/ path"
    assert created["label"] == "Test Share Link"
    assert created["is_revoked"] is False
    assert created["token_prefix"] is not None
    assert len(created["token_prefix"]) == 8
    assert created["agent_id"] == agent_id
    assert created["session_count"] == 0
    assert "expires_at" in created
    assert "created_at" in created

    # ── Phase 2: List guest shares → share is present ─────────────────────

    shares = list_guest_shares(client, superuser_token_headers, agent_id)
    assert len(shares) == 1
    assert shares[0]["id"] == share_id
    assert shares[0]["label"] == "Test Share Link"
    assert shares[0]["session_count"] == 0
    # List endpoint should NOT expose the raw token, but SHOULD include share_url
    assert "token" not in shares[0] or shares[0].get("token") is None
    assert shares[0].get("share_url") is not None
    assert "/guest/" in shares[0]["share_url"]

    # ── Phase 3: Get guest share by ID ────────────────────────────────────

    fetched = get_guest_share(client, superuser_token_headers, agent_id, share_id)
    assert fetched["id"] == share_id
    assert fetched["label"] == "Test Share Link"
    assert fetched["is_revoked"] is False
    assert fetched["agent_id"] == agent_id
    assert fetched["session_count"] == 0
    assert fetched["token_prefix"] == created["token_prefix"]

    # ── Phase 4: Delete guest share ───────────────────────────────────────

    result = delete_guest_share(client, superuser_token_headers, agent_id, share_id)
    assert "message" in result

    # ── Phase 5: Verify guest share is gone ───────────────────────────────

    shares = list_guest_shares(client, superuser_token_headers, agent_id)
    assert len(shares) == 0

    # GET by ID should 404
    r = client.get(
        f"{API}/agents/{agent_id}/guest-shares/{share_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


def test_multiple_guest_shares(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    User creates multiple guest shares with different labels,
    lists them, deletes one, and verifies the remaining set.
    """
    # ── Setup ─────────────────────────────────────────────────────────────

    agent = create_agent_via_api(client, superuser_token_headers, name="Multi-Share Agent")
    drain_tasks()
    agent_id = agent["id"]

    # ── Create shares ─────────────────────────────────────────────────────

    s1 = create_guest_share(client, superuser_token_headers, agent_id, label="Share 1", expires_in_hours=24)
    s2 = create_guest_share(client, superuser_token_headers, agent_id, label="Share 2", expires_in_hours=48)
    s3 = create_guest_share(client, superuser_token_headers, agent_id, expires_in_hours=72)

    # ── Verify all three appear in the list ───────────────────────────────

    shares = list_guest_shares(client, superuser_token_headers, agent_id)
    assert len(shares) == 3
    share_ids = {s["id"] for s in shares}
    assert {s1["id"], s2["id"], s3["id"]} == share_ids

    # ── Delete one, verify the rest remain ────────────────────────────────

    delete_guest_share(client, superuser_token_headers, agent_id, s2["id"])

    shares = list_guest_shares(client, superuser_token_headers, agent_id)
    assert len(shares) == 2
    remaining_ids = {s["id"] for s in shares}
    assert s2["id"] not in remaining_ids
    assert {s1["id"], s3["id"]} == remaining_ids


def test_guest_share_not_found_for_wrong_agent(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    A guest share created for agent A cannot be accessed via agent B's URL.
    """
    # ── Create two agents ─────────────────────────────────────────────────

    agent_a = create_agent_via_api(client, superuser_token_headers, name="Agent A")
    agent_b = create_agent_via_api(client, superuser_token_headers, name="Agent B")
    drain_tasks()

    # ── Create share on agent A ───────────────────────────────────────────

    share = create_guest_share(client, superuser_token_headers, agent_a["id"], label="agent-a-share")

    # ── Try to access via agent B's URL → 404 ────────────────────────────

    r = client.get(
        f"{API}/agents/{agent_b['id']}/guest-shares/{share['id']}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404

    # ── Agent B's list should be empty ────────────────────────────────────

    shares_b = list_guest_shares(client, superuser_token_headers, agent_b["id"])
    assert len(shares_b) == 0

    # ── Agent A's list should have the share ──────────────────────────────

    shares_a = list_guest_shares(client, superuser_token_headers, agent_a["id"])
    assert len(shares_a) == 1
    assert shares_a[0]["id"] == share["id"]


def test_delete_nonexistent_guest_share_returns_404(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deleting a guest share that doesn't exist returns 404.
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="404 Agent")
    drain_tasks()

    fake_share_id = str(uuid.uuid4())
    r = client.delete(
        f"{API}/agents/{agent['id']}/guest-shares/{fake_share_id}",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404


def test_other_user_cannot_see_or_manage_guest_shares(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    User B cannot list, get, or delete guest shares on an agent owned by user A.
      1. User A (superuser) creates agent + guest share
      2. User B tries to list/get/delete → denied
      3. User A still has full access
    """
    # ── Phase 1: User A creates agent + guest share ───────────────────────

    agent, share = setup_guest_share_agent(
        client, superuser_token_headers,
        name="Owner Agent",
        share_label="owner-only-share",
    )
    agent_id = agent["id"]
    share_id = share["id"]

    # ── Phase 2: Create user B ────────────────────────────────────────────

    _, user_b_headers = create_random_user_with_headers(client)

    # ── Phase 3: User B cannot list/get/delete guest shares ───────────────

    r = client.get(f"{API}/agents/{agent_id}/guest-shares/", headers=user_b_headers)
    assert r.status_code == 404

    r = client.get(f"{API}/agents/{agent_id}/guest-shares/{share_id}", headers=user_b_headers)
    assert r.status_code == 404

    r = client.delete(f"{API}/agents/{agent_id}/guest-shares/{share_id}", headers=user_b_headers)
    assert r.status_code == 404

    # ── Phase 4: User A still has full access ─────────────────────────────

    shares = list_guest_shares(client, superuser_token_headers, agent_id)
    assert len(shares) == 1
    assert shares[0]["id"] == share_id
    assert shares[0]["label"] == "owner-only-share"


def test_empty_guest_shares_list(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Listing guest shares for an agent with no shares returns empty list.
    """
    agent = create_agent_via_api(client, superuser_token_headers, name="Empty Shares Agent")
    drain_tasks()

    shares = list_guest_shares(client, superuser_token_headers, agent["id"])
    assert len(shares) == 0


def test_guest_share_without_label(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Creating a guest share without a label succeeds with label=None.
    """
    agent, created = setup_guest_share_agent(
        client, superuser_token_headers,
        name="No Label Agent",
        expires_in_hours=12,
    )

    assert created["label"] is None
    assert "token" in created
    assert "share_url" in created

    # Verify via GET
    fetched = get_guest_share(client, superuser_token_headers, agent["id"], created["id"])
    assert fetched["label"] is None
