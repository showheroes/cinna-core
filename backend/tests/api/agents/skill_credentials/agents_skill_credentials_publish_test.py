"""Skill credential slot declarations resolve at publish (Phase 1).

A catalog skill declares the credential slots its scripts need in its
``SKILL.md`` frontmatter (``credentials: [{slot, type, description}]``).
Publish resolves each slot against the publishing agent's linked credentials
and freezes the result onto the immutable revision (``required_credential_specs``
/ ``required_credentials``). See docs/plans/skill_credential_requirements_plan.md
§2 (D9-D14), §3 (I1, I6, I12), §4 (C1-C3), §7.7.

Scenarios (plan §7.11):
  1. The resolution matrix across the five consent shapes an ``api_token``
     slot can be in, including the two D12 template outcomes.
  2. A credential shared *to* the publisher (not owned) -> ``not_owned``.
  3. Immutability: flipping sharing and republishing changes only the new
     revision.
  4. An invalid ``credentials:`` block previews empty and refuses publish.
  5. An ``agent_api`` slot records ``producer_agent_id``, and D12 rule 1: an
     ``agent_api`` credential with only template sharing never resolves to
     ``template``.
  6. D13: the description fallback to a credential's notes applies only to
     ``publisher`` / ``template`` resolutions, and a declared description
     always wins.
  7. D14: a slot linked only to a placeholder credential is never a publish
     candidate, even when the placeholder's owner turns sharing on.

Unit tests for the ``credentials:`` frontmatter parser itself live in
``tests/unit/test_skill_manifest.py``. Unit tests for the container SDK
(``by_slot`` / ``require_slot`` / ``agent_api_session``) live in
``tests/unit/test_cinna_api_credentials_slots.py``.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import update_agent
from tests.utils.bundle import install_bundle, publish_bundle_and_make_public
from tests.utils.credential import (
    create_random_credential,
    get_agent_credentials,
    get_credential,
    link_credential_to_agent,
    set_credential_sharing,
    share_credential_via_api,
    update_credential,
)
from tests.utils.skill_catalog import (
    error_code,
    get_skill_package,
    make_agent_with_env,
    make_developer,
    patched_skill_storage,
    preview_skill_publish,
    publish_skill,
    write_skill,
)

API = settings.API_V1_STR


@pytest.fixture(autouse=True)
def skill_storage(tmp_path: Path):
    with patched_skill_storage(tmp_path / "skill-storage") as root:
        yield root


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _skill_frontmatter(name: str, credentials_yaml: str) -> str:
    return (
        f"name: {name}\n"
        f"description: Exercises declared credential slots.\n"
        f"credentials:\n{credentials_yaml}"
    )


def _credential_by_slot(entries: list[dict], slot: str) -> dict:
    match = next((e for e in entries if e["slot"] == slot), None)
    assert match is not None, f"no entry for slot {slot!r} in {entries!r}"
    return match


def _assert_no_template_secrets(node) -> None:
    """No response anywhere carries a template payload (I6)."""
    if isinstance(node, dict):
        assert "template_data" not in node
        assert "template_private_fields" not in node
        for value in node.values():
            _assert_no_template_secrets(value)
    elif isinstance(node, list):
        for item in node:
            _assert_no_template_secrets(item)


# ---------------------------------------------------------------------------
# Scenario 1: the resolution matrix
# ---------------------------------------------------------------------------


def test_publish_resolves_credential_slots_per_consent_matrix(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """
    A skill declares five ``api_token`` slots, one per consent shape:
      - owned + allow_sharing                              -> publisher
      - owned + template sharing, EVERY stored secret field marked private
        (``api_token`` and the computed ``http_header_value``)  -> template (D12)
      - owned + template sharing, secret field NOT private  -> user / template_would_leak_secret (D12)
      - owned, not shareable at all                         -> user / not_shareable
      - no linked credential                                -> user / no_linked_credential

    The same resolution shows up identically in the preview, the publish
    response, and the package detail's frozen revision (C2/C3). No response
    anywhere carries ``template_data`` / ``template_private_fields`` (I6).
    """
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "Matrix-Agent")

    def _linked_cred(slot: str, **flags) -> str:
        cred = create_random_credential(client, dev_headers, credential_type="api_token")
        update_credential(client, dev_headers, cred["id"], service_uri=slot, **flags)
        link_credential_to_agent(client, dev_headers, agent_id, cred["id"])
        return cred["id"]

    _linked_cred("slot-publisher", allow_sharing=True)
    _linked_cred(
        "slot-template",
        allow_template_sharing=True,
        # D12 security fix: the STORED secret key (``api_token``) must be
        # marked private too, not only the computed ``http_header_value``
        # SENSITIVE_FIELDS names -- marking only the latter used to leak the
        # raw token into template_data. See the dedicated regression test
        # below (scenario 8) for the full leak/fix matrix.
        template_private_fields=["api_token", "http_header_value"],
    )
    _linked_cred("slot-template-leak", allow_template_sharing=True)
    _linked_cred("slot-not-shareable")
    # "slot-no-credential" is declared below but nothing is linked to it.

    credentials_block = (
        "  - slot: slot-publisher\n    type: api_token\n"
        "  - slot: slot-template\n    type: api_token\n"
        "  - slot: slot-template-leak\n    type: api_token\n"
        "  - slot: slot-not-shareable\n    type: api_token\n"
        "  - slot: slot-no-credential\n    type: api_token\n"
    )
    write_skill(
        env_id, "matrix-skill",
        frontmatter=_skill_frontmatter("matrix-skill", credentials_block),
    )

    expected = {
        "slot-publisher": ("publisher", None),
        "slot-template": ("template", None),
        "slot-template-leak": ("user", "template_would_leak_secret"),
        "slot-not-shareable": ("user", "not_shareable"),
        "slot-no-credential": ("user", "no_linked_credential"),
    }

    # ── Preview ──────────────────────────────────────────────────────────
    preview = preview_skill_publish(client, dev_headers, agent_id, "matrix-skill")
    assert len(preview["credentials"]) == 5
    for slot, (provided_by, reason) in expected.items():
        entry = _credential_by_slot(preview["credentials"], slot)
        assert entry["provided_by"] == provided_by, slot
        assert entry["reason"] == reason, slot
    _assert_no_template_secrets(preview)

    # ── Publish ──────────────────────────────────────────────────────────
    revision = publish_skill(client, dev_headers, agent_id, "matrix-skill")
    _assert_no_template_secrets(revision)
    required = revision["required_credentials"]
    assert len(required) == 5
    for slot, (provided_by, _reason) in expected.items():
        assert _credential_by_slot(required, slot)["provided_by"] == provided_by

    # ── Package detail: the frozen revision agrees ──────────────────────
    package = get_skill_package(client, dev_headers, revision["package_id"])
    _assert_no_template_secrets(package)
    detail_required = package["revisions"][0]["required_credentials"]
    assert len(detail_required) == 5
    for slot, (provided_by, _reason) in expected.items():
        assert _credential_by_slot(detail_required, slot)["provided_by"] == provided_by


# ---------------------------------------------------------------------------
# Scenario 2: not_owned
# ---------------------------------------------------------------------------


def test_credential_shared_to_publisher_resolves_not_owned(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """D4: a share received by the publisher cannot be re-shared. A slot whose
    only linked candidate is owned by somebody else always resolves to
    ``user`` / ``not_owned``, and the non-owned match is never named."""
    owner, owner_headers = make_developer(client, superuser_token_headers)
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "NotOwned-Agent")

    cred = create_random_credential(client, owner_headers, credential_type="api_token")
    update_credential(
        client, owner_headers, cred["id"], service_uri="shared-slot", allow_sharing=True,
    )
    share_credential_via_api(client, owner_headers, cred["id"], dev["email"])
    link_credential_to_agent(client, dev_headers, agent_id, cred["id"])

    write_skill(
        env_id, "not-owned-skill",
        frontmatter=_skill_frontmatter(
            "not-owned-skill", "  - slot: shared-slot\n    type: api_token\n"
        ),
    )

    preview = preview_skill_publish(client, dev_headers, agent_id, "not-owned-skill")
    entry = _credential_by_slot(preview["credentials"], "shared-slot")
    assert entry["provided_by"] == "user"
    assert entry["reason"] == "not_owned"
    assert entry["credential_id"] is None

    revision = publish_skill(client, dev_headers, agent_id, "not-owned-skill")
    required = _credential_by_slot(revision["required_credentials"], "shared-slot")
    assert required["provided_by"] == "user"


# ---------------------------------------------------------------------------
# Scenario 3: immutability
# ---------------------------------------------------------------------------


def test_republish_after_flipping_sharing_leaves_prior_revision_unchanged(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """Revisions are immutable (I12): flipping a credential's consent and
    republishing changes only the NEW revision's frozen requirement."""
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "Immutable-Agent")

    cred = create_random_credential(client, dev_headers, credential_type="api_token")
    update_credential(client, dev_headers, cred["id"], service_uri="flip-slot")
    link_credential_to_agent(client, dev_headers, agent_id, cred["id"])

    write_skill(
        env_id, "flip-skill",
        frontmatter=_skill_frontmatter(
            "flip-skill", "  - slot: flip-slot\n    type: api_token\n"
        ),
    )

    rev1 = publish_skill(client, dev_headers, agent_id, "flip-skill")
    assert _credential_by_slot(rev1["required_credentials"], "flip-slot")["provided_by"] == "user"

    set_credential_sharing(client, dev_headers, cred["id"], True)
    rev2 = publish_skill(client, dev_headers, agent_id, "flip-skill", version="2.0.0")
    assert (
        _credential_by_slot(rev2["required_credentials"], "flip-slot")["provided_by"]
        == "publisher"
    )

    package = get_skill_package(client, dev_headers, rev1["package_id"])
    revisions_by_number = {r["revision_number"]: r for r in package["revisions"]}
    assert (
        _credential_by_slot(
            revisions_by_number[1]["required_credentials"], "flip-slot"
        )["provided_by"]
        == "user"
    )
    assert (
        _credential_by_slot(
            revisions_by_number[2]["required_credentials"], "flip-slot"
        )["provided_by"]
        == "publisher"
    )


# ---------------------------------------------------------------------------
# Scenario 4: invalid declaration
# ---------------------------------------------------------------------------


def test_invalid_credentials_block_previews_empty_and_refuses_publish(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "Invalid-Agent")

    write_skill(
        env_id, "bad-creds-skill",
        # Missing "slot" on the only entry -- invalid_credentials.
        frontmatter=_skill_frontmatter("bad-creds-skill", "  - type: api_token\n"),
    )

    preview = preview_skill_publish(client, dev_headers, agent_id, "bad-creds-skill")
    assert preview["credentials"] == []

    r = client.post(
        f"{API}/agents/{agent_id}/skills/bad-creds-skill/publish",
        headers=dev_headers,
        json={},
    )
    assert r.status_code == 422, r.text
    body = r.json()
    assert error_code(body) == "skill_invalid"
    assert "credentials block" in body["detail"]["message"]


# ---------------------------------------------------------------------------
# Scenario 5: agent_api producer_agent_id + D12 rule 1
# ---------------------------------------------------------------------------


def test_agent_api_slot_records_producer_agent_id_and_never_resolves_template(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """An ``agent_api`` slot records the producer's agent id when it resolves
    to ``publisher``. D12 rule 1: an ``agent_api`` credential with only
    template sharing on can never resolve to ``template`` -- a connection has
    no user-fillable private field to protect the token with."""
    dev, dev_headers = make_developer(client, superuser_token_headers)
    producer_id, _producer_env = make_agent_with_env(client, dev_headers, "Producer-Agent")
    update_agent(client, dev_headers, producer_id, agent_api_enabled=True)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "Connector-Agent")

    def _connect(label: str) -> dict:
        r = client.post(
            f"{API}/agents/{producer_id}/agent-api/connect",
            headers=dev_headers,
            json={"credential_label": label},
        )
        assert r.status_code == 200, r.text
        return r.json()

    shared = _connect("shared-connection")
    update_credential(
        client, dev_headers, shared["credential_id"],
        service_uri="producer-shared", allow_sharing=True,
    )
    link_credential_to_agent(client, dev_headers, agent_id, shared["credential_id"])

    template_only = _connect("template-connection")
    update_credential(
        client, dev_headers, template_only["credential_id"],
        service_uri="producer-template", allow_template_sharing=True,
    )
    link_credential_to_agent(client, dev_headers, agent_id, template_only["credential_id"])

    write_skill(
        env_id, "connector-skill",
        frontmatter=_skill_frontmatter(
            "connector-skill",
            "  - slot: producer-shared\n    type: agent_api\n"
            "  - slot: producer-template\n    type: agent_api\n",
        ),
    )

    preview = preview_skill_publish(client, dev_headers, agent_id, "connector-skill")
    shared_entry = _credential_by_slot(preview["credentials"], "producer-shared")
    assert shared_entry["provided_by"] == "publisher"
    assert shared_entry["producer_agent_id"] == producer_id

    template_entry = _credential_by_slot(preview["credentials"], "producer-template")
    assert template_entry["provided_by"] == "user"
    assert template_entry["reason"] == "not_shareable"

    revision = publish_skill(client, dev_headers, agent_id, "connector-skill")
    required = revision["required_credentials"]
    assert _credential_by_slot(required, "producer-shared")["producer_agent_id"] == producer_id
    assert _credential_by_slot(required, "producer-template")["provided_by"] == "user"


# ---------------------------------------------------------------------------
# Scenario 6: D13 description fallback
# ---------------------------------------------------------------------------


def test_description_fallback_applies_only_to_publisher_and_template(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """D13: a slot with no declared description falls back to the matched
    credential's notes only for ``publisher`` / ``template`` resolutions. A
    ``user`` resolution never leaks a private credential's notes, and a
    declared description always wins over the fallback."""
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "Description-Agent")

    publisher_cred = create_random_credential(client, dev_headers, credential_type="api_token")
    update_credential(
        client, dev_headers, publisher_cred["id"],
        service_uri="desc-publisher", allow_sharing=True,
        notes="Owner's private setup notes",
    )
    link_credential_to_agent(client, dev_headers, agent_id, publisher_cred["id"])

    user_cred = create_random_credential(client, dev_headers, credential_type="api_token")
    update_credential(
        client, dev_headers, user_cred["id"],
        service_uri="desc-user", notes="Owner's private setup notes",
    )
    link_credential_to_agent(client, dev_headers, agent_id, user_cred["id"])

    declared_cred = create_random_credential(client, dev_headers, credential_type="api_token")
    update_credential(
        client, dev_headers, declared_cred["id"],
        service_uri="desc-declared", allow_sharing=True,
        notes="Notes that must be overridden",
    )
    link_credential_to_agent(client, dev_headers, agent_id, declared_cred["id"])

    write_skill(
        env_id, "description-skill",
        frontmatter=_skill_frontmatter(
            "description-skill",
            "  - slot: desc-publisher\n    type: api_token\n"
            "  - slot: desc-user\n    type: api_token\n"
            "  - slot: desc-declared\n    type: api_token\n"
            "    description: Declared description wins\n",
        ),
    )

    preview = preview_skill_publish(client, dev_headers, agent_id, "description-skill")

    publisher_entry = _credential_by_slot(preview["credentials"], "desc-publisher")
    assert publisher_entry["provided_by"] == "publisher"
    assert publisher_entry["description"] == "Owner's private setup notes"

    user_entry = _credential_by_slot(preview["credentials"], "desc-user")
    assert user_entry["provided_by"] == "user"
    assert user_entry["description"] is None

    declared_entry = _credential_by_slot(preview["credentials"], "desc-declared")
    assert declared_entry["provided_by"] == "publisher"
    assert declared_entry["description"] == "Declared description wins"


# ---------------------------------------------------------------------------
# Scenario 7: D14 placeholder credentials are never publish candidates
# ---------------------------------------------------------------------------


def test_placeholder_credential_is_never_a_publish_candidate(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """D14: a slot linked only to a placeholder resolves to ``user`` /
    ``no_linked_credential`` even though the placeholder is owned by the
    publisher and sharing is on.

    There is no API route that creates a placeholder credential directly (the
    public create route never accepts ``is_placeholder``), so this test
    obtains one through the pre-existing bundle install provisioning path
    (live before this feature, unrelated to it): installing a bundle whose
    only credential spec is ``provided_by="template"`` materialises a
    placeholder ``Credential`` owned by the installer, carrying the spec's
    ``service_uri``.
    """
    bundle_pub, bundle_pub_headers = make_developer(client, superuser_token_headers)
    template_agent_id, _ = make_agent_with_env(
        client, bundle_pub_headers, "Template-Source-Agent"
    )

    template_cred = create_random_credential(
        client, bundle_pub_headers, credential_type="api_token"
    )
    update_credential(
        client, bundle_pub_headers, template_cred["id"],
        service_uri="placeholder-slot", allow_template_sharing=True,
        template_private_fields=["http_header_value"],
    )
    link_credential_to_agent(
        client, bundle_pub_headers, template_agent_id, template_cred["id"]
    )

    publish_bundle_and_make_public(client, bundle_pub_headers, template_agent_id)
    fresh_agent = client.get(
        f"{API}/agents/{template_agent_id}", headers=bundle_pub_headers
    ).json()
    bundle_id = fresh_agent["bundle_id"]
    assert bundle_id is not None

    dev, dev_headers = make_developer(client, superuser_token_headers)
    install = install_bundle(client, dev_headers, bundle_id)
    install_id = install["id"]

    installed_creds = get_agent_credentials(client, dev_headers, install_id)
    # NOTE: GET /agents/{id}/credentials builds a hand-rolled projection
    # (app/api/routes/agents.py::read_agent_credentials) that does not
    # include `service_uri` at all -- a pre-existing gap unrelated to this
    # feature (GET /credentials/{id} does project it, via
    # `_credential_to_public`). Find the placeholder by `is_placeholder`
    # here (the only one on this fresh install), then confirm its
    # `service_uri` through the endpoint that actually returns it.
    placeholder = next(c for c in installed_creds["data"] if c["is_placeholder"] is True)
    placeholder_detail = get_credential(client, dev_headers, placeholder["id"])
    assert placeholder_detail["service_uri"] == "placeholder-slot"

    # The developer now owns this placeholder and turns sharing ON -- D14
    # says it must still never be offered to installers.
    set_credential_sharing(client, dev_headers, placeholder["id"], True)

    skill_agent_id, skill_env_id = make_agent_with_env(
        client, dev_headers, "Skill-From-Placeholder"
    )
    link_credential_to_agent(client, dev_headers, skill_agent_id, placeholder["id"])

    write_skill(
        skill_env_id, "placeholder-skill",
        frontmatter=_skill_frontmatter(
            "placeholder-skill", "  - slot: placeholder-slot\n    type: api_token\n"
        ),
    )

    preview = preview_skill_publish(client, dev_headers, skill_agent_id, "placeholder-skill")
    entry = _credential_by_slot(preview["credentials"], "placeholder-slot")
    assert entry["provided_by"] == "user"
    assert entry["reason"] == "no_linked_credential"


# ---------------------------------------------------------------------------
# Scenario 8 (regression): D12 must cover the STORED secret key, not only
# the computed one SENSITIVE_FIELDS names
# ---------------------------------------------------------------------------


def test_template_private_fields_must_cover_the_stored_secret_key(
    client: TestClient, superuser_token_headers: dict[str, str],
) -> None:
    """D12 / I6 regression (security fix): ``CredentialsService.SENSITIVE_FIELDS``
    names only the ENV-shaped computed secret (``http_header_value`` for
    ``api_token``), never the STORED ``credential_data`` key
    (``api_token``/``odoo``'s ``api_token``) that ``_template_payload_for``
    actually copies into ``template_data``. Marking only the computed field
    private used to leave the raw stored secret in the frozen, immutable
    revision every catalog viewer can read -- a leak the coordinator flagged
    against a live earlier version of this test. ``_template_leaking_secret_fields``
    now unions ``SENSITIVE_FIELDS`` with the stored key per type and fails
    closed:
      - ``api_token`` marked private only on ``http_header_value`` -> still
        ``user`` / ``template_would_leak_secret`` (the raw ``api_token``
        stored field is still unprotected).
      - ``api_token`` marked private on BOTH ``api_token`` and
        ``http_header_value`` -> ``template``.
      - ``odoo`` marked private on its stored secret key (``api_token``) ->
        ``template``.
    """
    dev, dev_headers = make_developer(client, superuser_token_headers)
    agent_id, env_id = make_agent_with_env(client, dev_headers, "D12-Regression-Agent")

    def _templatable_cred(credential_type: str, service_uri: str, **flags) -> str:
        cred = create_random_credential(client, dev_headers, credential_type=credential_type)
        update_credential(
            client, dev_headers, cred["id"],
            service_uri=service_uri, allow_template_sharing=True, **flags,
        )
        link_credential_to_agent(client, dev_headers, agent_id, cred["id"])
        return cred["id"]

    _templatable_cred(
        "api_token", "d12-http-header-only",
        template_private_fields=["http_header_value"],
    )
    _templatable_cred(
        "api_token", "d12-both-private",
        template_private_fields=["api_token", "http_header_value"],
    )
    _templatable_cred(
        "odoo", "d12-odoo-stored-secret",
        template_private_fields=["api_token"],
    )

    credentials_block = (
        "  - slot: d12-http-header-only\n    type: api_token\n"
        "  - slot: d12-both-private\n    type: api_token\n"
        "  - slot: d12-odoo-stored-secret\n    type: odoo\n"
    )
    write_skill(
        env_id, "d12-regression-skill",
        frontmatter=_skill_frontmatter("d12-regression-skill", credentials_block),
    )

    # ── Preview ──────────────────────────────────────────────────────────
    preview = preview_skill_publish(client, dev_headers, agent_id, "d12-regression-skill")

    leaking = _credential_by_slot(preview["credentials"], "d12-http-header-only")
    assert leaking["provided_by"] == "user"
    assert leaking["reason"] == "template_would_leak_secret"

    fully_private = _credential_by_slot(preview["credentials"], "d12-both-private")
    assert fully_private["provided_by"] == "template"

    odoo_private = _credential_by_slot(preview["credentials"], "d12-odoo-stored-secret")
    assert odoo_private["provided_by"] == "template"
    _assert_no_template_secrets(preview)

    # ── Publish: the frozen revision agrees, and never carries a secret ───
    revision = publish_skill(client, dev_headers, agent_id, "d12-regression-skill")
    _assert_no_template_secrets(revision)
    required = revision["required_credentials"]
    assert _credential_by_slot(required, "d12-http-header-only")["provided_by"] == "user"
    assert _credential_by_slot(required, "d12-both-private")["provided_by"] == "template"
    assert _credential_by_slot(required, "d12-odoo-stored-secret")["provided_by"] == "template"
