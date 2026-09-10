"""Deletion-impact skill awareness: ``skill_pbp_usages`` / ``active_skill_install_count``.

``CredentialsService.get_deletion_impact`` (Phase 2 §8.8) extends the
bundle-only Tier 2 gate to catalog skills: a credential shared as
``provided_by="publisher"`` into a published skill package, with at least one
active foreign install of one of its revisions, blocks deletion (409) unless
``force=true``. See docs/plans/skill_credential_requirements_plan.md §8.8 and
§8.9. The bundle half of this gate (tiers, PBT exclusion, authorization) is
covered by ``tests/api/credentials/test_credential_deletion_impact.py`` and is
untouched here (I2) -- this file adds only the skill half.

Scenarios (plan §8.9):
  1. A publisher-provided credential in a published, publicly-installed
     catalog skill -> tier==2, ``skill_pbp_usages`` names the package,
     ``active_skill_install_count==1``. Unforced DELETE -> 409 with the same
     fields in the structured detail; ``force=true`` -> 200, credential gone.
  2. The same shape with only the PUBLISHER'S OWN install (no foreign
     install) -> tier stays below 2, unforced DELETE succeeds.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.credential import (
    create_random_credential,
    link_credential_to_agent,
    update_credential,
)
from tests.utils.skill_catalog import (
    install_skill,
    make_agent_with_env,
    make_developer,
    patched_skill_storage,
    publish_skill,
    write_skill_with_credentials,
)

API = settings.API_V1_STR


@pytest.fixture(autouse=True)
def skill_storage(tmp_path: Path):
    with patched_skill_storage(tmp_path / "skill-storage") as root:
        yield root


def _deletion_impact(client: TestClient, headers: dict[str, str], credential_id: str) -> dict:
    r = client.get(f"{API}/credentials/{credential_id}/deletion-impact", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------
# Scenario 1: PBP with a foreign install -> Tier 2
# ---------------------------------------------------------------------------


def test_skill_pbp_credential_with_foreign_install_is_tier2(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    pub, pub_headers = make_developer(client, superuser_token_headers)
    pub_agent, pub_env = make_agent_with_env(client, pub_headers, "DelImpact-Publisher")

    cred = create_random_credential(client, pub_headers, credential_type="api_token")
    update_credential(
        client, pub_headers, cred["id"], service_uri="del-impact-slot", allow_sharing=True,
    )
    link_credential_to_agent(client, pub_headers, pub_agent, cred["id"])

    write_skill_with_credentials(
        pub_env, "del-impact-skill", [{"slot": "del-impact-slot", "type": "api_token"}],
    )
    revision = publish_skill(
        client, pub_headers, pub_agent, "del-impact-skill", visibility="public",
    )
    package_uuid = revision["package_id"]
    assert revision["required_credentials"][0]["provided_by"] == "publisher"

    # ── No foreign install yet -> below Tier 2 ────────────────────────────
    # skill_pbp_usages is informational (like bundle_pbp_usages): it lists
    # every package this credential is publisher-provided in, regardless of
    # tier. Only active_skill_install_count (a foreign install) drives Tier 2.
    baseline = _deletion_impact(client, pub_headers, cred["id"])
    assert baseline["tier"] < 2
    assert len(baseline["skill_pbp_usages"]) == 1
    assert baseline["active_skill_install_count"] == 0

    # ── A foreign installer installs the skill ────────────────────────────
    con, con_headers = make_developer(client, superuser_token_headers)
    con_agent, _ = make_agent_with_env(client, con_headers, "DelImpact-Consumer")
    install_skill(client, con_headers, con_agent, package_uuid)

    impact = _deletion_impact(client, pub_headers, cred["id"])
    assert impact["tier"] == 2
    assert impact["active_skill_install_count"] == 1
    assert len(impact["skill_pbp_usages"]) == 1
    usage = impact["skill_pbp_usages"][0]
    assert usage["package_uuid"] == package_uuid
    assert usage["revision_numbers"] == [revision["revision_number"]]

    # ── Unforced DELETE -> 409 with the structured impact ─────────────────
    r = client.delete(f"{API}/credentials/{cred['id']}", headers=pub_headers)
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["tier"] == 2
    assert detail["active_skill_install_count"] == 1
    assert len(detail["skill_pbp_usages"]) == 1

    r_check = client.get(f"{API}/credentials/{cred['id']}", headers=pub_headers)
    assert r_check.status_code == 200, "credential must survive an unforced 409"

    # ── force=true -> 200, credential gone ─────────────────────────────────
    r = client.delete(f"{API}/credentials/{cred['id']}?force=true", headers=pub_headers)
    assert r.status_code == 200, r.text
    r_gone = client.get(f"{API}/credentials/{cred['id']}", headers=pub_headers)
    assert r_gone.status_code == 404


# ---------------------------------------------------------------------------
# Scenario 2: only the publisher's own install -> stays below Tier 2
# ---------------------------------------------------------------------------


def test_skill_pbp_credential_with_only_publishers_own_install_stays_below_tier2(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    pub, pub_headers = make_developer(client, superuser_token_headers)
    pub_agent, pub_env = make_agent_with_env(
        client, pub_headers, "DelImpact-SelfOnly-Publisher",
    )
    pub_agent_2, _ = make_agent_with_env(
        client, pub_headers, "DelImpact-SelfOnly-Second",
    )

    cred = create_random_credential(client, pub_headers, credential_type="api_token")
    update_credential(
        client, pub_headers, cred["id"],
        service_uri="del-impact-self-slot", allow_sharing=True,
    )
    link_credential_to_agent(client, pub_headers, pub_agent, cred["id"])

    write_skill_with_credentials(
        pub_env, "del-impact-self-skill",
        [{"slot": "del-impact-self-slot", "type": "api_token"}],
    )
    revision = publish_skill(
        client, pub_headers, pub_agent, "del-impact-self-skill", visibility="private",
    )
    package_uuid = revision["package_id"]

    # The publisher installs their own skill into a second agent -- no
    # foreign install exists.
    install_skill(client, pub_headers, pub_agent_2, package_uuid)

    impact = _deletion_impact(client, pub_headers, cred["id"])
    assert impact["tier"] < 2
    assert impact["active_skill_install_count"] == 0

    r = client.delete(f"{API}/credentials/{cred['id']}", headers=pub_headers)
    assert r.status_code == 200, r.text
