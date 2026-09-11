"""Readiness-gate D1 exclusion for skill-provisioned credentials (I10).

The install readiness gate (``InstallReadinessGate``) never lets a catalog
skill's unconfigured credential block an agent's chat/MCP/A2A/webhook
channels (D1) -- the alert lives on the Addons row instead
(``agents_skill_credentials_install_test.py`` scenarios 4, 6, 7). This file
covers the interaction with a BUNDLE install, whose own verdict must stay
unchanged (I10): ``SkillSlotIndex.skill_provisioned_credential_ids()`` drops
a credential from the gate's ``missing`` list only when a catalog skill spec
needs it AND the agent's bundle revision does not also claim it.

See docs/plans/skill_credential_requirements_plan.md §2 (D1), §3 (I10),
§8.5 (``SkillSlotIndex``, ``bundle_claimed_credential_ids``), §8.6, §8.9.

Scenarios (plan §8.9, gate file):
  1. A bundle-install agent that also carries a catalog skill: the bundle
     spec's own placeholder still trips ``needs_setup`` (I10 unchanged), but
     the skill-only placeholder never appears in ``missing`` (D1).
  2. Over-claim by design (coordinator ruling on
     ``credential_provisioner.bundle_claimed_credential_ids`` rule (c)):
     when the bundle spec's own placeholder is unlinked and replaced with an
     unrelated SAME-TYPE credential, the bundle spec becomes "unaccounted" by
     type and claims every linked credential of that type -- including a
     same-type skill-only placeholder, which then stays blocking instead of
     being D1-excluded. Deliberate: under-claiming would silently drop a real
     bundle blocker from the gate.
  3. The copy after that skill is uninstalled: the claim keeps the placeholder
     (D15), so the setup page must stop saying an installed skill requires it.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.bundle import install_bundle, make_bundle_public, publish_bundle
from tests.utils.credential import (
    create_random_credential,
    get_agent_credentials,
    link_credential_to_agent,
    unlink_credential_from_agent,
    update_credential,
)
from tests.utils.skill_catalog import (
    install_skill,
    list_agent_plugins,
    make_agent_with_env,
    make_developer,
    patched_skill_storage,
    publish_skill,
    uninstall_agent_plugin,
    write_skill_with_credentials,
)

API = settings.API_V1_STR


@pytest.fixture(autouse=True)
def skill_storage(tmp_path: Path):
    with patched_skill_storage(tmp_path / "skill-storage") as root:
        yield root


def _setup_status(client: TestClient, headers: dict[str, str], agent_id: str) -> dict:
    r = client.get(f"{API}/agents/{agent_id}/setup-status", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _setup_credentials(
    client: TestClient, headers: dict[str, str], agent_id: str,
) -> list[dict]:
    r = client.get(f"{API}/agents/{agent_id}/setup-credentials", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _publish_pbu_bundle(
    client: TestClient, superuser_headers: dict[str, str], agent_name: str,
) -> tuple[dict, dict]:
    """A publisher with a non-shareable ("PBU") credential in a public bundle.

    Returns ``(bundle_cred, fresh_agent)``.
    """
    pub, pub_headers = make_developer(client, superuser_headers)
    agent_id, _ = make_agent_with_env(client, pub_headers, agent_name)
    cred = create_random_credential(client, pub_headers, credential_type="api_token")
    update_credential(client, pub_headers, cred["id"], allow_sharing=False)
    link_credential_to_agent(client, pub_headers, agent_id, cred["id"])

    fresh = publish_bundle(client, pub_headers, agent_id)
    make_bundle_public(client, pub_headers, fresh["bundle_uuid"])
    return cred, fresh


# ---------------------------------------------------------------------------
# Scenario 1: bundle placeholder still blocks; skill-only placeholder does not
# ---------------------------------------------------------------------------


def test_bundle_placeholder_still_blocks_skill_placeholder_does_not(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """
    1. Publisher A publishes a bundle with a non-shareable credential.
    2. Consumer C installs it -> a bundle placeholder -> needs_setup, naming
       the bundle spec alone.
    3. C also installs a catalog skill declaring a slot nothing satisfies ->
       a SEPARATE skill-only placeholder is created and linked.
    4. setup-status stays needs_setup, but ``missing`` still names only the
       bundle spec -- the skill placeholder never appears (D1).
    """
    bundle_cred, fresh = _publish_pbu_bundle(
        client, superuser_token_headers, "Gate-Bundle-Publisher",
    )

    consumer, consumer_headers = make_developer(client, superuser_token_headers)
    install = install_bundle(client, consumer_headers, fresh["bundle_id"])
    install_id = install["id"]

    baseline = _setup_status(client, consumer_headers, install_id)
    assert baseline["status"] == "needs_setup"
    assert len(baseline["missing"]) == 1
    # A "user"-provided spec (non-shareable) carries no publisher_credential_id
    # in the frozen spec, so the gate's spec_lookup cannot resolve it by id and
    # falls back to the placeholder credential's own name (the bundle policy's
    # "<name> (placeholder)" convention) -- the same fallback I2 pins for
    # bundle installs, unchanged here.
    assert baseline["missing"][0]["spec_name"] == f"{bundle_cred['name']} (placeholder)"

    skill_pub, skill_pub_headers = make_developer(client, superuser_token_headers)
    skill_agent, skill_env = make_agent_with_env(
        client, skill_pub_headers, "Gate-Skill-Publisher",
    )
    write_skill_with_credentials(
        skill_env, "gate-skill", [{"slot": "gate-skill-slot", "type": "odoo"}],
    )
    revision = publish_skill(
        client, skill_pub_headers, skill_agent, "gate-skill", visibility="public",
    )
    install_skill(client, consumer_headers, install_id, revision["package_id"])

    after = _setup_status(client, consumer_headers, install_id)
    assert after["status"] == "needs_setup"
    assert len(after["missing"]) == 1, (
        f"the skill-only placeholder must not appear (D1): {after['missing']}"
    )
    assert after["missing"][0]["spec_name"] == f"{bundle_cred['name']} (placeholder)"


# ---------------------------------------------------------------------------
# Scenario 2: over-claim by design
# ---------------------------------------------------------------------------


def test_overclaim_unaccounted_bundle_spec_claims_same_type_skill_placeholder(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    bundle_cred, fresh = _publish_pbu_bundle(
        client, superuser_token_headers, "Overclaim-Bundle-Publisher",
    )

    consumer, consumer_headers = make_developer(client, superuser_token_headers)
    install = install_bundle(client, consumer_headers, fresh["bundle_id"])
    install_id = install["id"]

    # Unlink the bundle placeholder and link an unrelated SAME-TYPE credential
    # -- the bundle spec is now "unaccounted" by type (rule c).
    installed_creds = get_agent_credentials(client, consumer_headers, install_id)["data"]
    bundle_placeholder = next(c for c in installed_creds if c["is_placeholder"] is True)
    unlink_credential_from_agent(client, consumer_headers, install_id, bundle_placeholder["id"])
    replacement = create_random_credential(client, consumer_headers, credential_type="api_token")
    link_credential_to_agent(client, consumer_headers, install_id, replacement["id"])

    # A catalog skill declaring an api_token slot nothing satisfies -> its own
    # placeholder, the SAME type as the now-unaccounted bundle spec.
    skill_pub, skill_pub_headers = make_developer(client, superuser_token_headers)
    skill_agent, skill_env = make_agent_with_env(
        client, skill_pub_headers, "Overclaim-Skill-Publisher",
    )
    write_skill_with_credentials(
        skill_env, "overclaim-skill", [{"slot": "overclaim-slot", "type": "api_token"}],
    )
    revision = publish_skill(
        client, skill_pub_headers, skill_agent, "overclaim-skill", visibility="public",
    )
    install_skill(client, consumer_headers, install_id, revision["package_id"])

    status = _setup_status(client, consumer_headers, install_id)
    assert status["status"] == "needs_setup", (
        "the unaccounted bundle spec over-claims the same-type skill "
        "placeholder by design, so it must still block setup"
    )
    spec_names = {item["spec_name"] for item in status["missing"]}
    assert "overclaim-slot" in spec_names, status["missing"]


# ---------------------------------------------------------------------------
# Scenario 3: the copy on a placeholder whose skill is gone
# ---------------------------------------------------------------------------


def test_kept_placeholder_stops_claiming_a_skill_requires_it(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """Uninstalling the skill keeps the claimed placeholder -- and the block.

    The row's notes were stamped at install time ("Required by an installed
    skill"), which stops being true the moment the skill is uninstalled while
    the bundle claim keeps the row alive. The agent stays blocked with an empty
    Addons tab, so the setup page is the only place that can explain it: it must
    say no skill needs it any more, and how to clear the block.
    """
    bundle_cred, fresh = _publish_pbu_bundle(
        client, superuser_token_headers, "Stale-Copy-Bundle-Publisher",
    )

    consumer, consumer_headers = make_developer(client, superuser_token_headers)
    install = install_bundle(client, consumer_headers, fresh["bundle_id"])
    install_id = install["id"]

    installed_creds = get_agent_credentials(client, consumer_headers, install_id)["data"]
    bundle_placeholder = next(c for c in installed_creds if c["is_placeholder"] is True)
    unlink_credential_from_agent(
        client, consumer_headers, install_id, bundle_placeholder["id"],
    )
    replacement = create_random_credential(
        client, consumer_headers, credential_type="api_token",
    )
    link_credential_to_agent(client, consumer_headers, install_id, replacement["id"])

    skill_pub, skill_pub_headers = make_developer(client, superuser_token_headers)
    skill_agent, skill_env = make_agent_with_env(
        client, skill_pub_headers, "Stale-Copy-Skill-Publisher",
    )
    write_skill_with_credentials(
        skill_env, "stale-copy-skill", [{"slot": "stale-slot", "type": "api_token"}],
    )
    revision = publish_skill(
        client, skill_pub_headers, skill_agent, "stale-copy-skill", visibility="public",
    )
    install_skill(client, consumer_headers, install_id, revision["package_id"])

    while_installed = _setup_credentials(client, consumer_headers, install_id)
    stale_row = next(row for row in while_installed if row["name"] == "stale-slot")
    assert "installed skill" in (stale_row["description"] or "")

    link = next(
        plugin
        for plugin in list_agent_plugins(client, consumer_headers, install_id)
        if plugin["snapshot_plugin_name"] == "stale-copy-skill"
    )
    uninstall_agent_plugin(client, consumer_headers, install_id, link["id"])

    assert _setup_status(client, consumer_headers, install_id)["status"] == "needs_setup", (
        "the claimed placeholder is kept on uninstall (D15), so the block stays"
    )
    after = _setup_credentials(client, consumer_headers, install_id)
    kept_row = next(row for row in after if row["name"] == "stale-slot")
    description = kept_row["description"] or ""
    assert "No installed skill requires this any more" in description, description
    assert "unlink it on the Credentials tab" in description, description
