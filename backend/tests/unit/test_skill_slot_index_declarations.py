"""Unit tests: ``SkillSlotIndex.issues_for_declarations``.

The Addons projection judges a skill with no pinned revision — a local skill,
a marketplace or bundle plugin's skill — on the ``(slot, type)`` pairs its
``SKILL.md`` declares. The reason table is the one catalog rows already use;
these checks pin it for declarations, including the two reasons the API cannot
reach without an install (``not_configured`` needs a placeholder,
``access_revoked`` needs stale share state).

Pure logic: the index is constructed directly from in-memory credentials. The
API-observable end is covered in
``tests/api/agents/skill_credentials/agents_skill_credentials_local_readiness_test.py``.
"""

import uuid

import pytest

from app.models.credentials.credential import Credential, CredentialType
from app.services.skills.skill_credential_requirements import SkillSlotIndex

OWNER_ID = uuid.uuid4()
SLOT = "some-token.com"


def _credential(**overrides) -> Credential:
    values = {
        "name": "Token",
        "type": CredentialType.API_TOKEN,
        "owner_id": OWNER_ID,
        "service_uri": SLOT,
        "is_placeholder": False,
        "allow_sharing": False,
    }
    values.update(overrides)
    return Credential(id=uuid.uuid4(), **values)


def _index(linked: list[Credential], shared_ids: set[uuid.UUID] | None = None):
    return SkillSlotIndex(
        owner_id=OWNER_ID,
        specs_by_link={},
        linked=linked,
        shared_ids=shared_ids or set(),
        bundle_claimed_ids=set(),
    )


def _reasons(index: SkillSlotIndex) -> list[tuple[str, str, str]]:
    return [
        (issue.slot, issue.type, issue.reason)
        for issue in index.issues_for_declarations([(SLOT, "api_token")])
    ]


def test_an_owned_filled_credential_satisfies_the_slot():
    assert _reasons(_index([_credential()])) == []


@pytest.mark.parametrize(
    "linked,expected",
    [
        pytest.param([], "not_linked", id="nothing-linked"),
        pytest.param(
            [_credential(service_uri="other-slot")], "not_linked", id="other-slot"
        ),
        # Type is part of the match, as it is for catalog specs.
        pytest.param(
            [_credential(type=CredentialType.ODOO)], "not_linked", id="other-type"
        ),
        pytest.param(
            [_credential(is_placeholder=True)], "not_configured", id="placeholder"
        ),
        pytest.param(
            [_credential(owner_id=uuid.uuid4(), allow_sharing=True)],
            "access_revoked",
            id="foreign-without-share",
        ),
    ],
)
def test_an_unusable_slot_reports_its_reason(linked, expected):
    assert _reasons(_index(linked)) == [(SLOT, "api_token", expected)]


def test_a_foreign_credential_shared_with_the_owner_satisfies_the_slot():
    foreign = _credential(owner_id=uuid.uuid4(), allow_sharing=True)
    assert _reasons(_index([foreign], shared_ids={foreign.id})) == []


def test_a_filled_credential_outranks_a_placeholder_for_the_same_slot():
    linked = [_credential(is_placeholder=True), _credential()]
    assert _reasons(_index(linked)) == []


def test_declarations_keep_their_order_and_skip_unknown_types():
    index = _index([_credential()])
    issues = index.issues_for_declarations(
        [("b-slot", "api_token"), (SLOT, "api_token"), ("a-slot", "not_a_type")]
    )
    assert [(issue.slot, issue.reason) for issue in issues] == [
        ("b-slot", "not_linked")
    ]
