"""Coverage guard for the D12 stored-secret map (reviewer finding N1).

``SkillCredentialRequirements._template_leaking_secret_fields`` (D12 / I6)
decides whether a template-shared credential may resolve to ``template`` by
checking its STORED ``credential_data`` secret keys
(``_STORED_SECRET_FIELDS_BY_TYPE``), not only
``CredentialsService.SENSITIVE_FIELDS`` — which is env-shaped and, for
``api_token``, names only the *computed* ``http_header_value``, never the
*stored* ``api_token`` key the credential is actually created with. Missing
that stored key for even one credential type is exactly the shape of the
leak the coordinator flagged against an earlier version of
``agents_skill_credentials_install_test.py`` (a template-shared ``api_token``
marked private only on ``http_header_value`` still shipped its raw token in
``template_data``).

This file is a pure module-constant assertion (no DB, no client) per
`tests/unit/README.md` ("Assertions about module-level constants"). It does
not re-test the leak/fix behavior itself -- that is covered end to end by
``tests/api/agents/skill_credentials/agents_skill_credentials_publish_test.py::
test_template_private_fields_must_cover_the_stored_secret_key`` and
``agents_skill_credentials_install_test.py::
test_template_materialised_carries_non_private_fields``. It exists so a new
``CredentialType`` that forgets to declare its stored secret keys fails loud,
here, instead of silently defaulting to "leak everything" or "template never
available" the next time someone adds a type.
"""
from app.models.credentials.credential import CredentialType
from app.services.bundles.publish_service import PublishService
from app.services.skills.skill_credential_requirements import (
    _STORED_SECRET_FIELDS_BY_TYPE,
)


def test_every_non_force_private_type_declares_its_stored_secret_keys() -> None:
    """Every ``CredentialType`` that isn't force-private must have an entry.

    A force-private type (OAuth, service account) drops its whole payload at
    publish regardless of ``template_private_fields``
    (``PublishService._TEMPLATE_FORCE_PRIVATE_TYPES``), so it never consults
    the stored-secret map. Every other type must be classified, or
    ``_template_leaking_secret_fields`` cannot tell a real secret from a safe
    field for it.
    """
    all_types = {member.value for member in CredentialType}
    force_private = PublishService._TEMPLATE_FORCE_PRIVATE_TYPES
    expected = all_types - force_private
    actual = set(_STORED_SECRET_FIELDS_BY_TYPE)

    missing = expected - actual
    extra = actual - expected
    assert actual == expected, (
        "A credential type is not classified in "
        "SkillCredentialRequirements._STORED_SECRET_FIELDS_BY_TYPE. "
        f"Missing (not force-private, no stored-secret entry): {sorted(missing)}. "
        f"Extra (force-private or unknown, should not have an entry): {sorted(extra)}. "
        "A new CredentialType must declare its STORED credential_data secret "
        "key(s) there -- CredentialsService.SENSITIVE_FIELDS names the "
        "ENV-shaped (computed) secret instead, which is a different set: for "
        "api_token it lists only 'http_header_value', never the stored "
        "'api_token' key the leak was made of."
    )


def test_api_token_stored_secret_map_includes_the_raw_token_field() -> None:
    """Regression anchor for the leak: the raw stored ``api_token`` key must
    be in its own type's stored-secret set, not only the computed
    ``http_header_value`` ``SENSITIVE_FIELDS`` names."""
    assert "api_token" in _STORED_SECRET_FIELDS_BY_TYPE["api_token"]
