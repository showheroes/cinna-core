"""
Tests for the default_ai_functions_sdk user preference.

Covers:
  1. New users get "system" as the default value
  2. Valid values ("system", "personal:anthropic") are accepted and persisted (personal: prefix for user credentials)
  3. Invalid values are rejected with HTTP 400
  4. The preference is returned in GET /users/me

Tests for the default_ai_functions_credential_id user preference.

Covers:
  5. Successfully setting a valid Anthropic API key credential — 200, persisted
  6. Auto-clearing credential_id when switching SDK to "system"
  7. Setting a non-existent UUID — 404
  8. Setting another user's credential — 404
  9. Setting a non-Anthropic credential — 400 with "Only Anthropic credentials"
  10. Setting an OAuth token credential — 400 with "OAuth tokens cannot be used"
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.user import create_random_user_with_headers


def test_default_ai_functions_sdk_full_lifecycle(
    client: TestClient,
) -> None:
    """
    Full lifecycle for the default_ai_functions_sdk user preference:
      1. New user is created — default value is "system"
      2. Update to "personal:anthropic" — accepted, persisted
      3. Update back to "system" — accepted, persisted
      4. Invalid value is rejected with HTTP 400
      5. None/unset does not clear the value (partial update semantics)
    """
    user, headers = create_random_user_with_headers(client)

    # ── Phase 1: New user has default "system" ─────────────────────────
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["default_ai_functions_sdk"] == "system", (
        f"Expected 'system' for new user, got {data['default_ai_functions_sdk']!r}"
    )

    # ── Phase 2: Update to "personal:anthropic" ────────────────────────────────
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "personal:anthropic"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["default_ai_functions_sdk"] == "personal:anthropic"

    # Verify persistence via GET
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["default_ai_functions_sdk"] == "personal:anthropic"

    # ── Phase 3: Update back to "system" ─────────────────────────────
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "system"},
    )
    assert r.status_code == 200
    assert r.json()["default_ai_functions_sdk"] == "system"

    # ── Phase 4: Invalid value is rejected ───────────────────────────
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "openai"},
    )
    assert r.status_code == 400
    detail = r.json().get("detail", "")
    assert "invalid" in detail.lower() or "ai functions sdk" in detail.lower(), (
        f"Expected error message about invalid SDK, got: {detail!r}"
    )

    # Verify value was not changed despite the failed update
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["default_ai_functions_sdk"] == "system"

    # ── Phase 5: Omitting the field does not clear the value ─────────
    # First set to anthropic, then do an unrelated update without the field
    client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "personal:anthropic"},
    )
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"full_name": "Test User"},
    )
    assert r.status_code == 200
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["default_ai_functions_sdk"] == "personal:anthropic", (
        "Unrelated PATCH should not clear default_ai_functions_sdk"
    )


def test_ai_functions_sdk_invalid_values(
    client: TestClient,
) -> None:
    """
    Verify several invalid values are all rejected with HTTP 400.

    This is a focused validation test — invalid values cannot be part of the
    main lifecycle because they leave no side-effects.
    """
    _, headers = create_random_user_with_headers(client)

    # Only non-empty invalid strings are rejected — empty string is treated as "not provided"
    invalid_values = ["openai", "gemini", "system2", "ANTHROPIC", "System", "anthropic"]
    for value in invalid_values:
        r = client.patch(
            f"{settings.API_V1_STR}/users/me",
            headers=headers,
            json={"default_ai_functions_sdk": value},
        )
        assert r.status_code == 400, (
            f"Expected 400 for value {value!r}, got {r.status_code}: {r.text}"
        )


def test_ai_functions_sdk_unauthenticated(
    client: TestClient,
) -> None:
    """Unauthenticated requests to update user preferences are rejected."""
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        json={"default_ai_functions_sdk": "personal:anthropic"},
    )
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# default_ai_functions_credential_id tests
# ---------------------------------------------------------------------------


def test_default_ai_functions_credential_id_full_lifecycle(
    client: TestClient,
) -> None:
    """
    Full lifecycle for the default_ai_functions_credential_id user preference:
      1. Create a user and a valid Anthropic API key credential
      2. Pin the credential via PATCH /users/me — 200, credential_id persisted
      3. Verify the credential_id is returned in GET /users/me
      4. Switch SDK to "system" — credential_id is auto-cleared to null
      5. Verify credential_id is null after SDK switch to "system"
      6. Pin credential again, then attempt to set a non-existent UUID — 404
      7. Attempt to set another user's credential — 404
      8. Attempt to set a non-Anthropic credential — 400
      9. Attempt to set an OAuth token credential — 400
    """
    _, headers = create_random_user_with_headers(client)

    # ── Phase 1: Create a valid Anthropic API key credential ──────────────
    cred = create_random_ai_credential(
        client,
        headers,
        credential_type="anthropic",
        api_key="sk-ant-api03-valid-key-for-ai-functions",
    )
    cred_id = cred["id"]

    # ── Phase 2: Pin the credential ───────────────────────────────────────
    # First set SDK to personal:anthropic so the credential pin is not cleared
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "personal:anthropic"},
    )
    assert r.status_code == 200

    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_credential_id": cred_id},
    )
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    data = r.json()
    assert data["default_ai_functions_credential_id"] == cred_id

    # ── Phase 3: Verify persistence via GET ───────────────────────────────
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["default_ai_functions_credential_id"] == cred_id

    # ── Phase 4: Switch SDK to "system" — credential_id is auto-cleared ──
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_sdk": "system"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["default_ai_functions_sdk"] == "system"
    # The credential_id must have been cleared automatically
    assert data["default_ai_functions_credential_id"] is None, (
        "Switching to 'system' SDK should auto-clear default_ai_functions_credential_id"
    )

    # ── Phase 5: Verify cleared state via GET ─────────────────────────────
    r = client.get(f"{settings.API_V1_STR}/users/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["default_ai_functions_credential_id"] is None

    # ── Phase 6: Non-existent credential UUID → 404 ───────────────────────
    ghost_id = str(uuid.uuid4())
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_credential_id": ghost_id},
    )
    assert r.status_code == 404, (
        f"Expected 404 for non-existent credential, got {r.status_code}: {r.text}"
    )
    assert "not found" in r.json().get("detail", "").lower()

    # ── Phase 7: Another user's credential → 404 ─────────────────────────
    _, other_headers = create_random_user_with_headers(client)
    other_cred = create_random_ai_credential(
        client,
        other_headers,
        credential_type="anthropic",
        api_key="sk-ant-api03-other-user-key",
    )
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_credential_id": other_cred["id"]},
    )
    assert r.status_code == 404, (
        f"Expected 404 for another user's credential, got {r.status_code}: {r.text}"
    )
    assert "not found" in r.json().get("detail", "").lower()

    # ── Phase 8: Non-Anthropic credential → 400 ──────────────────────────
    minimax_cred = create_random_ai_credential(
        client,
        headers,
        credential_type="minimax",
        api_key="mm-test-key-not-anthropic",
    )
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_credential_id": minimax_cred["id"]},
    )
    assert r.status_code == 400, (
        f"Expected 400 for non-Anthropic credential, got {r.status_code}: {r.text}"
    )
    detail = r.json().get("detail", "")
    assert "anthropic" in detail.lower(), (
        f"Expected 'Anthropic' in error detail, got: {detail!r}"
    )

    # ── Phase 9: OAuth token credential → 400 ────────────────────────────
    oauth_cred = create_random_ai_credential(
        client,
        headers,
        credential_type="anthropic",
        api_key="sk-ant-oat01-this-is-an-oauth-token",
    )
    r = client.patch(
        f"{settings.API_V1_STR}/users/me",
        headers=headers,
        json={"default_ai_functions_credential_id": oauth_cred["id"]},
    )
    assert r.status_code == 400, (
        f"Expected 400 for OAuth token credential, got {r.status_code}: {r.text}"
    )
    detail = r.json().get("detail", "")
    assert "oauth" in detail.lower(), (
        f"Expected 'OAuth' in error detail, got: {detail!r}"
    )
