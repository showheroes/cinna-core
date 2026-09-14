"""``service_uri`` / ``is_placeholder`` — env-sync top-level fields (I4).

Every real ``credentials.json`` entry carries a top-level ``service_uri``
(the slot a skill finds its credential by) and ``is_placeholder``, outside
``credential_data`` so the ``AGENT_ENV_ALLOWED_FIELDS`` whitelist and the
``SENSITIVE_FIELDS`` redaction (which act on ``credential_data`` only) can
never drop or mask them. See
docs/plans/skill_credential_requirements_plan.md §4 (C6), §7.8.

Follows the env-capture pattern of
``tests/api/credentials/test_ssh_key_credential_env_sync.py``.

Covers:
  a) An ``api_token`` and an ``odoo`` credential with ``service_uri`` linked
     to an agent: every real ``credentials_json`` entry has top-level
     ``service_uri`` and ``is_placeholder``.
  b) ``api_token`` ``credential_data`` still carries its in-data
     ``service_uri`` copy (unchanged, pre-existing behaviour).
  c) The README text contains the ``service_uri`` values and the "Slots"
     section, including how to check for the slot helpers and the rebuild
     remedy, because a pre-helper container receives the same README.
  d) A credential with no ``service_uri`` has ``"service_uri": null``.
  e) Synthetic entries (e.g. ``current_user``) are never given
     ``service_uri`` / ``is_placeholder`` keys.
  f) ``is_placeholder`` is ``false`` for a real, filled credential.
"""
from fastapi.testclient import TestClient

from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.credential import (
    create_random_credential,
    link_credential_to_agent,
    real_credentials_json,
    update_credential,
)


def _create_agent_with_shared_adapter(
    client: TestClient,
    headers: dict[str, str],
    patch_environment_adapter,
) -> tuple[dict, EnvironmentTestAdapter]:
    """Create agent, drain env-init tasks, then install a shared adapter for inspection."""
    agent = create_agent_via_api(client, headers)
    drain_tasks()
    agent = get_agent(client, headers, agent["id"])
    assert agent["active_environment_id"] is not None

    shared_adapter = EnvironmentTestAdapter()
    patch_environment_adapter.get_adapter = lambda env: shared_adapter
    return agent, shared_adapter


def test_service_uri_and_is_placeholder_are_top_level_on_every_real_entry(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    An ``api_token`` and an ``odoo`` credential, both with a ``service_uri``
    slot, linked to an agent:
      1. Every real ``credentials_json`` entry carries top-level
         ``service_uri`` and ``is_placeholder: false``.
      2. ``api_token``'s ``credential_data`` still carries its own in-data
         ``service_uri`` copy (unchanged behaviour, I4 says it "stays").
      3. The README documents both slots and the "Slots" section.
      4. A credential with no ``service_uri`` set carries ``null``.
    """
    # ── Phase 1: Create credentials, one with a slot, one without ────────
    api_token_cred = create_random_credential(
        client, superuser_token_headers, credential_type="api_token"
    )
    api_token_cred = update_credential(
        client, superuser_token_headers, api_token_cred["id"],
        service_uri="erp-public-api",
    )
    assert api_token_cred["service_uri"] == "erp-public-api"

    odoo_cred = create_random_credential(
        client, superuser_token_headers, credential_type="odoo"
    )
    odoo_cred = update_credential(
        client, superuser_token_headers, odoo_cred["id"], service_uri="odoo-billing",
    )
    assert odoo_cred["service_uri"] == "odoo-billing"

    # No service_uri set on this one.
    bare_cred = create_random_credential(
        client, superuser_token_headers, credential_type="email_smtp"
    )
    assert bare_cred.get("service_uri") is None

    # ── Phase 2: Create agent + shared adapter ────────────────────────────
    agent, shared_adapter = _create_agent_with_shared_adapter(
        client, superuser_token_headers, patch_environment_adapter
    )
    agent_id = agent["id"]

    # ── Phase 3: Link all three credentials → env sync fires ─────────────
    link_credential_to_agent(client, superuser_token_headers, agent_id, api_token_cred["id"])
    link_credential_to_agent(client, superuser_token_headers, agent_id, odoo_cred["id"])
    link_credential_to_agent(client, superuser_token_headers, agent_id, bare_cred["id"])

    env_data = shared_adapter.credentials_set
    assert env_data, "Adapter must have received credentials"

    # ── Phase 4: Every real entry carries top-level service_uri + is_placeholder
    creds_json = real_credentials_json(env_data)
    assert len(creds_json) == 3

    by_id = {entry["id"]: entry for entry in creds_json}
    assert by_id[api_token_cred["id"]]["service_uri"] == "erp-public-api"
    assert by_id[api_token_cred["id"]]["is_placeholder"] is False
    assert by_id[odoo_cred["id"]]["service_uri"] == "odoo-billing"
    assert by_id[odoo_cred["id"]]["is_placeholder"] is False

    # Phase 4d: no service_uri set → explicit null, not an absent key.
    bare_entry = by_id[bare_cred["id"]]
    assert "service_uri" in bare_entry
    assert bare_entry["service_uri"] is None
    assert bare_entry["is_placeholder"] is False

    # ── Phase 5: api_token's credential_data still carries its own copy ──
    api_token_entry = by_id[api_token_cred["id"]]
    assert api_token_entry["credential_data"]["service_uri"] == "erp-public-api"

    # ── Phase 6: synthetic entries never get service_uri / is_placeholder ─
    all_entries = env_data.get("credentials_json", [])
    synthetic_entries = [e for e in all_entries if e["id"] not in by_id]
    assert synthetic_entries, "expected at least the synthetic current_user entry"
    for entry in synthetic_entries:
        assert "service_uri" not in entry
        assert "is_placeholder" not in entry

    # ── Phase 7: README documents the slots ───────────────────────────────
    readme = env_data.get("credentials_readme", "")
    assert readme, "credentials_readme must be non-empty"
    assert "erp-public-api" in readme
    assert "odoo-billing" in readme
    assert "## Slots (service_uri)" in readme
    assert "require_slot" in readme
    # A pre-helper container receives this README too, so it says how to
    # check for the helpers and what to do without them.
    assert "hasattr(credentials, 'require_slot')" in readme
    assert "cinna agent rebuild-env" in readme
    assert "is_placeholder" in readme
