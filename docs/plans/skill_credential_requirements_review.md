# Skill credential requirements — independent completion review

Date: 2026-09-11

Scope: the full feature described by
`skill_credential_requirements_design.md` and
`skill_credential_requirements_plan.md`, including the implementation plan's
explicit decisions that supersede the design brief. This review checks the
current implementation independently of the historical test counts in §15.

**Verdict: complete for the supported single-worker deployment.** The blocking
template-secret issue and four readiness/reporting inconsistencies found in
this review are fixed and covered by regressions. No remaining blocker was
found within the planned Phase 1–4 scope; deployment and explicit scope limits
are recorded below.

## Findings and completed fixes

| Finding | Impact | Resolution and regression evidence |
|---|---|---|
| A stored copy of the derived `http_header_value` survived template publication when only `api_token` was private. The API accepts arbitrary credential-data keys, contrary to D17's computed-only assumption. | A second user installing the template received the publisher's header secret. | Skill `build_specs` now strips derived secret fields before inserting the immutable revision. The ordinary token-private-only workflow still works; bundle serialization is unchanged. A publish-to-install API regression failed by exposing the header before the fix. |
| Frozen publisher IDs satisfied slots even after the credential's live `service_uri` changed. | Existing Addons rows said ready and new installs linked a credential that `require_slot` could not find. | Skill provisioning and status require the frozen type and slot to match the live credential. A drifted publisher credential follows the existing unavailable/fallback path. API regression covers existing status and new preview/install. |
| Shared placeholders counted as usable in `SkillSlotIndex`. | Addons said ready while the SDK rejected the unfilled credential. | Shared and owned placeholders both report `not_configured`; an API regression checks the warning and its removal after the owner fills it. |
| An old placeholder could precede a filled replacement in linked credentials. | SDK lookup failed, or install preview still requested setup, despite a usable replacement. | SDK lookup and skill provisioning prefer filled matching credentials. Unit tests cover both payload orders; an API scenario verifies replacement readiness. |
| The catalog install dialog discarded partial plugin sync failures. | Users received a success message, or left setup without learning that the skill had not reached an environment. | Both install entry points share sync classification and warning copy. The catalog dialog retains the report through setup and warns on Done, Escape and Credentials navigation. Seven browser lifecycle tests exercise the production dialog with mocked HTTP responses. |
| Documentation overstated recovery and used an unsupported declaration example. | Users could follow an inline-map example the parser rejects, or retry an upgrade that does not reprovision an unchanged slot. | Corrected the declaration example, sharing recovery, deletion impact, uninstall retention, runtime helper contract, test map and synchronization guidance. Regenerated platform knowledge. |

## Coverage assessment

| Layer | Assessment |
|---|---|
| Declaration and projection | Implemented. Validation covers slot/type/description shape, limits, duplicates and excluded types. Backend and environment parser copies are byte-identical. |
| Storage and migration | Implemented. Immutable revision specs use non-null JSON with `[]` default. Running database and migration head both report `8f3a1d7c04e2`, including the feature migration. |
| Publishing and privacy | Implemented. Consent and ownership determine publisher/template/user modes; placeholders cannot be published as provided credentials. Public schemas omit template payloads. The stored-derived-secret gap above is fixed. |
| Provisioning and lifecycle | Implemented. Preview shares the decision logic with provisioning. Install/link writes are transactional; upgrades provision added slots only; uninstall releases unneeded placeholders while retaining real credentials and bundle claims. |
| Status and readiness | Implemented. Skill setup remains an Addons warning; bundle requirements retain their blocking gate. Slot drift and shared-placeholder inconsistencies are fixed. |
| Revocation and impact | Implemented. Both sharing-disable APIs and individual-share revocation remove recipient links and trigger synchronization. Skill publisher usages contribute to deletion impact, including installs upgraded beyond the providing revision. |
| Container payload and SDK | Implemented. All real entries carry slot and placeholder fields; slot reads are fresh; the Agent API helper supplies identity and origin-scoped request/redirect headers. Filled replacement lookup is fixed. |
| Frontend | S1–S7 pass code/composition review against the plan. Both install paths show readiness and setup remedies; catalog requirements, Addons warnings, producer facts, impact disclosures and Automatic classification are present. Changed S2 behavior has real-component browser coverage. |
| Documentation | Business and technical docs, authoring examples, integration notes and bundled platform knowledge have been synchronized with the implementation. |

## Verification

Backend regression: **2585 passed, 10 skipped**, exit 0, in 534.69 seconds.
Command, run inside the backend container:

```bash
python -m pytest tests/api/credentials tests/api/agents/skill_credentials tests/api/agents/bundles tests/api/agents/bundles_install tests/api/agents/core tests/unit tests/architecture -q --tb=short
```

This is the affected regression scope, not a rerun of every backend test.
The additional SDK freshness scenario was added after the broad run collected
tests and verified separately in the final 27-test SDK run below. Other changes
after collection were comments/import cleanup and removal of a redundant file
open mode; the final SDK run includes that cleanup.

Additional evidence:

- Both slot-drift/shared-placeholder regressions failed before their fixes;
  the install module subsequently passed 13 tests.
- The stored-derived-secret regression failed before its fix, showing the
  copied header in the consumer's credential.
- The replacement SDK regression failed before its fix for placeholder-first
  payload order.
- The final SDK suite passed **27 tests**, including setup, token refresh and
  revocation observed through fresh reads on the same accessor.
- Frontend: 12 helper tests and seven browser lifecycle tests passed;
  `npm run build` passed. Browser tests use the real dialog, router, query
  client and generated HTTP SDK with intercepted API calls, without a live
  user account or database.
- Focused Ruff and Biome checks, parser byte comparison, migration-head check,
  documentation checks and whitespace validation passed.
- Public API schemas did not change, so the generated client contract is
  unchanged.

## Deployment and scope limits

- Existing environments need rebuilding to receive the updated SDK helper.
  Backend projections work independently of the environment parser version.
- The supported Compose configuration runs one backend worker. Sequential
  provisioning is idempotent; multiple independent workers can race to create
  an owner/type/slot placeholder because that key has no transaction lock or
  uniqueness constraint. Multiworker support requires this hardening in
  addition to the repository's existing MCP worker limitation. The Dockerfile's
  standalone default of four workers should not be treated as evidence that
  multiworker operation is supported.
- Use slot names consistently for one service/type. The general SDK lookup is
  by slot; assigning the same slot to different credential types is ambiguous.
- The SDK's guarded HTTP verb methods and redirects scope credential headers
  to the producer origin. Low-level prepared-request `send()` and explicitly
  supplied per-request headers retain the documented caller-controlled behavior.
- This review ran API integration tests with environment adapters and mocked
  browser APIs. It did not repeat the historical live two-user production-like
  scenario recorded in plan §15, or certify every UI surface with screenshots.
- Published revisions remain immutable. The sanitizer protects new revisions;
  it does not rewrite previously published template payloads. A read-only
  inspection found **zero** affected existing revisions in the local
  development database; no credential values were returned.
- Plan §13 remains outside this feature: per-installer token minting, a drift
  endpoint, optional slots, per-slot install choices, local-skill warnings and
  changing bundle template publication semantics.
