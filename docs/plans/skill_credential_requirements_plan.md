# Skill Credential Requirements — Implementation Plan

Status: Phases 1–3 committed as `793782a3`. Phase 4 (§10) done except the manual dev-stack scenario — seam review answered, D17 fixed, docs swept, full suite green (4616/0). Current state, test counts and Phase 4 notes: **§15**.
Date: 2026-09-10
Input: `docs/plans/skill_credential_requirements_design.md` (the architecture brief)
Feature name: `skill-credential-requirements`

## How to use this plan

- The plan has four phases (§7–§10). A `cinna-core-manager` run implements **one** phase. It reads
  **§0–§6 and its own phase section**, and nothing else is required. Every file, signature,
  migration and test the phase needs is listed there.
- **Phases 1–3 SKIP documentation.** Do not edit `docs/**`, do not run `make docs-registry`. The one
  exception is `BUILDING_AGENT.md` (Phase 1). It is a **prompt shipped into the container**, i.e.
  product code, not documentation. All feature docs are updated in Phase 4 (§10).
- Before starting a phase, check its **Prerequisites** block. If a prerequisite is not met (for
  example the Phase 1 migration is not applied), stop and report. Do not re-implement an earlier
  phase.
- Line numbers below were verified against the tree on 2026-09-10. They drift. Locate code by the
  **symbol name**, and use the line only as a hint.

---

## 0. Overview

A catalog skill can declare, in its `SKILL.md` frontmatter, the credential **slots** its scripts need.
Each slot is a `Credential.service_uri` value plus a `CredentialType`. The feature then works end to end:

- **Publish** resolves each slot against the publishing agent's linked credentials. It freezes a
  bundle-shaped `required_credential_specs` list onto the immutable `SkillPackageRevision`.
- **Install and upgrade** run one provisioning chokepoint, `CredentialProvisioner`, extracted from
  bundle install. For each slot it does one of the following:
  - shares and links the publisher's credential (`CredentialShare.source="skill_install"`);
  - links the installer's own credential that matches the slot;
  - materialises a template;
  - creates a placeholder.
  It never fails the install.
- **Status**: the Addons row turns amber (`credential_missing`) with per-slot `credential_issues`. The
  catalog shows what a skill requires. The deletion-impact gate counts skill installs.
- **Container**: every `credentials.json` entry carries a top-level `service_uri` and `is_placeholder`.
  The `cinna_api` SDK gains `by_slot` / `require_slot` / `agent_api_session`, so scripts find a
  credential by slot and fail with a message that says how to fix it.

```
 SKILL.md (credentials: [{slot,type}])
        │  parse_skill_dir → SkillEntry.credentials          [Phase 1]
        ▼
 publish_from_agent ── SkillCredentialRequirements.resolve_for_publish
        │               └─ build_spec (shared with bundle publish)
        ▼
 SkillPackageRevision.required_credential_specs (JSON)     [Phase 1]
        │  parse_credential_spec (single reader)
        ├──────────────► catalog projections (required_credentials)      [Phase 1]
        ├──────────────► install-preview / install / upgrade             [Phase 2]
        │                 └─ CredentialProvisioner.provision (SKILL_INSTALL_POLICY)
        │                      ├─ CredentialShare(source="skill_install") + AgentCredentialLink
        │                      ├─ link own slot credential (find_slot_match)
        │                      ├─ template materialise
        │                      └─ placeholder(name=slot, service_uri=slot)
        ├──────────────► SkillSlotIndex → Addons credential_missing + gate exclusion [Phase 2]
        └──────────────► deletion impact skill_pbp_usages                 [Phase 2]
                                   │
 AgentCredentialLink rows ─► prepare_credentials_for_environment
        credentials.json entry {id,name,type,notes,service_uri,is_placeholder,credential_data} [Phase 1]
                                   │
 container script ─► cinna_api credentials.require_slot("erp-public-api") / agent_api_session(...) [Phase 1]
```

---

## 1. Citation verification (brief → code, checked 2026-09-10)

| Brief citation | Verified location | Result |
|---|---|---|
| `credential_spec.py:19` `ParsedCredentialSpec` | `backend/app/services/bundles/credential_spec.py:20` (decorator on :19) | OK. The fields match the brief. |
| `CredentialsService.find_match_for_spec` `:2140` | `backend/app/services/credentials/credentials_service.py:2140` | OK. Tier 0a/0b `service_uri` runs first (:2215–2249). The docstring says **"Suggestion-only — never auto-commits"**, and this matters for D3. |
| `PublishService.resolve_provided_by` `:710` | `backend/app/services/bundles/publish_service.py:710` | OK. It also reads `publish_settings["credential_overrides"]` by credential **name**, which is bundle-only (see D4). |
| `_collect_credential_specs` `:745` | `publish_service.py:748` | **Drifted** (:748). |
| `_template_payload_for` (no line) | `publish_service.py:1208` | Located. |
| `_validate_publisher_provides` (no line) | `publish_service.py:1425` | Located. |
| `InstallService._setup_install_credentials` `:724` | `backend/app/services/bundles/install_service.py:724` | OK. It is `async`, but its body never awaits. Its only caller is `:528`. |
| `_try_link_publisher_credential` `:992` | `install_service.py:992` | OK. |
| `_materialise_template_credential` `:926` | `install_service.py:926` | OK. |
| `InstallReadinessGate` `:76` | `backend/app/services/bundles/install_readiness_gate.py:76` | OK. |
| `InstallGateDispatcher` fires `INSTALL_SETUP_REQUIRED` | `backend/app/services/bundles/install_gate_dispatcher.py:39` | OK, with a **premise correction** below. |
| setup-credentials page `routes/installs.py:341` | `backend/app/api/routes/installs.py:341` (GET list), `:430` (PUT fill) | OK. There is **no dedicated setup page**: `_build_setup_url` (`install_readiness_gate.py:383`) points at `/agent/{id}#credentials`. |
| `owner_identity_token` minted per install owner | `backend/app/services/agent_api/agent_api_identity_service.py:97` `build_owner_identity_block`, header `IDENTITY_HEADER = "X-Cinna-Caller-Identity"` (:44), injected in `prepare_credentials_for_environment` (`credentials_service.py:1457–1480`) only when ≥1 `agent_api` credential is linked | OK. |
| `SkillPackageRevision.frontmatter` `models/skills/skill_package_revision.py:16` | class at :16, `frontmatter` column at :51 | OK. |
| `SkillCatalogService.install_into_agent` `:1859` | `backend/app/services/skills/skill_catalog_service.py:1859` | OK. It is **sync** and commits the link itself. |
| `upgrade_link` `:1940` | `skill_catalog_service.py:1940` | OK. Called from `LLMPluginService.upgrade_agent_plugin` (`backend/app/services/plugins/llm_plugin_service.py:2067`), route `POST /llm-plugins/agents/{agent_id}/plugins/{link_id}/upgrade` (`backend/app/api/routes/llm_plugins.py:437`). |
| `publish_preview` `:529` | `skill_catalog_service.py:529` | OK. |
| `publish_from_agent` (no line) | `skill_catalog_service.py:258` (`async`) | Located. |
| route `POST /agents/{id}/skills/install` `routes/skills.py:539` | `backend/app/api/routes/skills.py:539` (`agent_router`) | OK. |
| `AddonsService._settle_status` `addons_service.py:429` | **`backend/app/services/agents/addons_service.py:429`** | **Path corrected.** There is no `services/addons/` directory. |
| env accessor `core/cinna_api/credentials.py:27` | `backend/app/env-templates/app_core_base/core/cinna_api/credentials.py:27` (`_Credentials`); `get` :52, `by_type` :63, `all_by_type` :73 | OK. |
| `get_deletion_impact` Tier 2 scans bundle revisions' specs | `credentials_service.py:1845`. Tier 2 is driven by `list_bundle_usages` (:3049), which is **bundles only** | OK. The skill gap is confirmed. |
| `service_uri` injected only for `api_token` (`:215`) | `credentials_service.py:213–219` | OK. |
| `AGENT_ENV_ALLOWED_FIELDS` `:164` | The dict starts at `credentials_service.py:92`. The `agent_api` whitelist line is :164 | OK (the brief cited the `agent_api` line). |
| parser `skill_manifest.py:443` `parse_frontmatter` | `backend/app/services/agents/skill_manifest.py:443`. The vendored copy is `backend/app/env-templates/app_core_base/core/server/skill_manifest.py`, **identical today** (`diff` clean), guarded by `backend/tests/unit/test_skill_manifest.py:54` | OK. |
| `connect_agent_api` ownership gate `agent_api_token_service.py:210` | `backend/app/services/agent_api/agent_api_token_service.py:210` | OK. |

### Premise corrections (these change the design; see §2)

1. **The readiness gate does not "nag", it blocks.** `InstallGateDispatcher.check` has **no
   bundle guard**. It runs `InstallReadinessGate.check` for **any** agent at four places:
   - chat (`backend/app/services/sessions/session_service.py:1882` → `:2028`, before env activation);
   - MCP (`backend/app/mcp/request_handler.py:111`);
   - A2A (`backend/app/services/a2a/a2a_request_handler.py:296`);
   - webhooks (`backend/app/services/agents/agent_webhook_service.py:594`).

   When it trips, pending messages are marked sent and never reach the LLM. If skill provisioning
   creates a placeholder on a user's own agent, every channel of that agent would be refused until
   the placeholder is filled. → **D1**.
2. **"The first sync already carries the credential" is not what plugin sync does.**
   `LLMPluginService.sync_plugins_to_agent_environments` (`llm_plugin_service.py:2595`) pushes only
   the plugin manifest. Credentials reach running environments through
   `CredentialsService.sync_credentials_to_agent_environments` (`credentials_service.py:1591`).
   Phase 2 must call it explicitly.
3. **The "old container keeps the unknown block as text" risk is slightly off.** The current parser
   turns `- slot: x` into the **string** `"slot: x"` and drops the continuation lines, because
   `items` wins over `nested`. The conclusion still holds: the host parse at publish is
   authoritative.
4. **`classify_credential_category` says a shared credential is never "automatic".** The rule is in
   its docstring (`credentials_service.py:2894`) and in a comment at
   `backend/app/services/credentials/credential_share_service.py:245–250`. The brief's
   `skill_install → Automatic` deliberately breaks that rule. → **D6**.
5. **There are two catalog-skill install entry points in the frontend, not one:**
   `frontend/src/components/Catalog/AddSkillToAgentDialog.tsx`, and
   `frontend/src/components/Agents/Addons/AddAddonDialog.tsx:182`. Both call
   `SkillsService.installAgentSkill`.
6. **Alembic head** on 2026-09-10 is `d7b41e0c9a35`
   (`add_agent_plugin_link_repository_snapshot`).

---

## 2. Decisions and deviations from the brief

| # | Decision | Why |
|---|---|---|
| **D1** | **Credentials provisioned for catalog skills do not trip the install readiness gate.** The gate drops any missing item whose credential is linked *because a catalog skill spec on that agent requires it* and is not claimed by the agent's bundle revision specs. The alert comes from three places instead: the Addons row (`credential_missing`, a **warning**), the install response and preview, and the container SDK (`require_slot` raises a message naming the slot and the fix). **CONFIRMED by the team lead on 2026-09-10: implement this non-blocking default (§8.6 stays in).** Alternative (the brief as literally written): drop step 2.6 and reword `_format_user_message` for non-bundle agents. Then every agent carrying an unconfigured skill is blocked on all channels, building mode included. | Premise correction 1. The brief classifies the condition as a *warning*. A hard block on every channel would make it an agent-wide error. A skill is one capability among many on a user-built agent, unlike a bundle, whose specs are the agent's contract. Bundle gate verdicts are unchanged (I10). |
| **D2** | The `CredentialProvisioner.provision` signature carries a `ProvisionPolicy` (which includes `share_source`) and a `PublisherBoundary`. It does not take a bare `share_source` and `publisher_user_id`. | The code shows five behavioural differences between bundle and skill provisioning: auto-match by slot, placeholder name, placeholder notes and slot stamping, template notes fallback, and user selections. A second nuance: the bundle trust check runs only when the bundle row exists, and then compares against `bundle.publisher_user_id` **even when it is NULL**. `publisher_user_id: UUID | None` cannot express both cases. `PublisherBoundary | None` can. |
| **D3** | Skill install auto-links only through the **`service_uri` tiers** (owned, then shared) via a new `CredentialsService.find_slot_match`, which is extracted from `find_match_for_spec`'s tier 0. The name tiers and the type-only fallback are never used to auto-commit. | `find_match_for_spec` is suggestion-only. Its type-only tier would silently link, for example, the user's only `agent_api` connection to a **different producer**. |
| **D4** | Publish derivation uses only the credential's consent flags. It never uses bundle `publish_settings.credential_overrides`. It also requires the matched credential to be **owned by the publisher** for `publisher` / `template`. A credential shared *to* the publisher resolves to `provided_by="user"` with reason `not_owned`. | A received share cannot be re-shared. The install-time trust boundary (owner == package publisher) would otherwise make every install degrade (brief, Risks). |
| **D5** | Uninstall deletes a released placeholder `Credential` row when it is still a placeholder **and** no agent links it any more. The brief only said "unlink". | An empty placeholder that nothing links is clutter on the Credentials page, with no value. Real credentials and shares are never touched. |
| **D6** | `classify_credential_category`: a **shared** credential with `share_source == "skill_install"` → `"automatic"` (per the brief). The docstring rule list and the comment at `credential_share_service.py:245` are updated. The Automatic tab description copy changes in Phase 3. | Brief §4. This is the first shared credential that lands on Automatic, so record it as a deliberate exception. |
| **D7** | Skill install takes **no per-slot user selections** in this MVP. Resolution is automatic (D3). The user can re-link on the agent's Credentials tab afterwards. The install dialogs show a read-only **install preview** from a new endpoint. | Keeps the install a three-field dialog. Selection UI can be added later on the same provisioner (`user_selections` already exists for bundles). |
| **D8** | A skill cannot declare `mcp_provider` as a slot type. | `mcp_provider` is never written to `credentials.json`, so a script could never consume it. |
| **D9** | `producer_agent_id` is added to a spec dict **by the skill publish caller only** (for `agent_api` slots). `build_spec` does not emit it. `ParsedCredentialSpec` reads it as an optional field. | Keeps the bundle revision JSON byte-identical (I1). |
| **D10** | The parser recognises `- key: value` as a mapping item only when the colon is followed by whitespace or end of line. | `- http://host/x` and `- Bash(git:*)` must stay scalars. |
| **D11** | Besides `service_uri`, every real `credentials.json` entry also carries a top-level `is_placeholder: bool`. | Without it `require_slot` cannot tell an unfilled slot from a filled one. For example, an empty `api_token` placeholder still yields `http_header_value: "Bearer "`. The flag is non-secret and type-agnostic, like `service_uri`. |
| **D12** | Skill publish never freezes a secret into `template_data`. An `agent_api` slot is never `template` (owned + `allow_sharing` → `publisher`, otherwise `user`/`not_shareable`). Any other type resolves to `template` only when no field named in `CredentialsService.SENSITIVE_FIELDS` for that type would survive `_template_payload_for` (force-private types and the per-type allowlist already strip them; otherwise the field must be in `template_private_fields`). Else `user` with reason `template_would_leak_secret`. **Ruled by the team lead on 2026-09-10 (code review S2).** Bundle `_template_payload_for` is unchanged (I1); fixing it for bundles is §13. | `_template_payload_for` force-privates only OAuth / service-account data, and allowlists only `ssh_key`. A template-shared `api_token` / `agent_api` / password credential would otherwise freeze its live secret into an immutable revision visible to every catalog viewer, and Phase 2 copies `template_data` into every installer's credential. |
| **D13** | A declaration without `description` falls back to the matched credential's `notes` only when `provided_by` is `publisher` or `template`. A `user` resolution uses the declaration's description or `None`. **Approved by the team lead on 2026-09-10 (code review S1).** | Notes are exposed only when the owner consented to provide the credential. Otherwise a private credential's free-text notes would be published in `required_credentials`. |
| **D14** | Placeholder credentials (`is_placeholder=True`) are never publish candidates. A slot linked only to placeholders resolves to `user` / `no_linked_credential`. **Approved by the team lead on 2026-09-10 (code review S4).** | A shared unfilled placeholder would hand installers an empty credential they cannot edit. |
| **D15** | **Bundle-claim rule (Phase 2, R1).** A credential linked to an agent counts as claimed by the agent's bundle revision when (a) its id is a spec's `publisher_credential_id`, (b) its name is a spec name or `"<name> (placeholder)"`, or (c) its type is that of a bundle spec that no linked credential answers through (a) or (b). One function, `credential_provisioner.bundle_claimed_credential_ids`, feeds `release_skill_slots` and `SkillSlotIndex`. The gate's own item enrichment is unchanged. **Phase 2 manager ruling, accepted by the coordinator on 2026-09-10.** | Install-form `use_existing` picks and manual re-links are never recorded, so (c) is the only way to see them. Over-claiming only restores pre-D1 behaviour on a bundle agent (the skill credential stays gated, and its placeholder is kept on uninstall). Under-claiming would drop a bundle blocker (I10). |
| **D16** | **D12 checks stored secret keys, not only env-shaped ones (Phase 2).** Per type, the secret set is `CredentialsService.SENSITIVE_FIELDS[type] ∪ _STORED_SECRET_FIELDS_BY_TYPE[type]` (`skill_credential_requirements.py`). A type that is not force-private and that neither map classifies never resolves to `template`. `tests/unit/test_skill_credential_secret_fields_coverage.py` fails when a new `CredentialType` is left unclassified. **Phase 2 ruling, code review clean.** | `SENSITIVE_FIELDS` names env-shaped fields (`api_token` → the computed `http_header_value`), but `_template_payload_for` copies the **stored** keys. So a template marked private only on `http_header_value` froze the raw `api_token` into the revision and every installer's credential (I6). Bundle publish is unchanged (I1, §13). Consequence: an `api_token` slot reaches `template` only when both `api_token` and `http_header_value` are private, which the UI picker cannot express (D17). |
| **D17** | **Interim `api_token` copy (Phase 3).** For an `api_token` slot, the S1 `template_would_leak_secret` sentence and its label drop "mark its secret fields private" and only say to turn sharing on. The real fix is in the backend: D16 treats the computed `http_header_value` as stripped when the stored `api_token` is private. Once it lands, revert the `api_token` copy in `frontend/src/utils/skillCredentials.ts`. **Phase 3 manager ruling. The backend follow-up is open (§15).** | Without it the UI tells publishers to do something the picker cannot do. A frontend-only fix (also saving `http_header_value` as private) was rejected: `template_private_fields` is shown verbatim to bundle installers (`InstallServiceCredentialItem.tsx`), so the hidden entry would surface as a raw field name and inflate the "fill in N private fields" count. |

---

## 3. Cross-phase invariants (every phase must preserve these; Phase 4 verifies them)

- **I1 — The bundle publish output is byte-identical.** After the `build_spec` extraction,
  `PublishService._collect_credential_specs` emits the same dict for every credential: the same
  keys, **in the same insertion order**, the same values, and no `producer_agent_id` key.
- **I2 — Bundle install behaviour is byte-for-byte unchanged after the `CredentialProvisioner`
  extraction.** That covers:
  - the same rows;
  - the placeholder name `"<name> (placeholder)"` and notes `"Placeholder for required bundle credential."`;
  - the template notes fallback `"Created from bundle template."`;
  - the same 422 detail text for `use_existing` on a publisher spec;
  - the same `last_update_status="degraded"` semantics;
  - share `source="bundle_install"`, first-writer-wins.

  **Every existing test under `backend/tests/api/agents/bundles/`,
  `backend/tests/api/agents/bundles_install/` and `backend/tests/api/credentials/` passes with no
  edit to those test files.**
- **I3 — The two parser copies are byte-identical:** `backend/app/services/agents/skill_manifest.py`
  and `backend/app/env-templates/app_core_base/core/server/skill_manifest.py`. Edit the backend copy,
  then copy it over. `tests/unit/test_skill_manifest.py` asserts this. The module stays stdlib-only.
- **I4 — `service_uri` (and `is_placeholder`) are top-level, type-agnostic fields** of every real
  `credentials.json` entry. The `AGENT_ENV_ALLOWED_FIELDS` whitelist never filters them and
  `SENSITIVE_FIELDS` never redacts them. The existing `api_token` in-`credential_data` copy of
  `service_uri` stays. The synthetic `current_user` / `owner_identity_token` entries are unchanged.
- **I5 — `find_match_for_spec` returns exactly what it returns today** for every input. Its tier 0
  delegates to `find_slot_match`.
- **I6 — Secrets never enter a skill folder or a revision.** The filename secret gate is untouched.
  Declarations carry only slot, type and description. Template specs go through
  `PublishService._template_payload_for`, which strips private fields. No public schema exposes
  `template_data`, `template_private_fields` or credential data.
- **I7 — The trust boundary is unchanged.** A `skill_install` share is created only when the
  credential's owner **equals the package publisher** and `allow_sharing` is true at install time.
  The installer's identity at the producer stays per-install-owner (`owner_identity_token`).
- **I8 — Skill provisioning never fails an install for a per-slot reason** (degrade-not-fail). An
  unexpected exception aborts the whole install atomically. The link and the provisioning commit in
  one transaction.
- **I9 — Provisioning is idempotent.** There is never a second `AgentCredentialLink` for the same
  (agent, credential); the composite primary key enforces this. There is never a second skill
  placeholder for the same (owner, type, slot), because `find_slot_match` runs before any placeholder
  is created. `CredentialShare.source` is first-writer-wins.
- **I10 — The readiness gate's verdict for bundle installs is unchanged.** The D1 exclusion removes
  only credentials that are skill-provisioned **and** not claimed by the agent's bundle revision specs.
- **I11 — `AddonsService` stays read-only**, and the credential half costs a constant number of
  queries per build (no N+1).
- **I12 — Revisions stay immutable.** `required_credential_specs` is written once, at insert.

---

## 4. Shared contracts (the vocabulary every phase uses)

### C1. `SKILL.md` declaration

```yaml
---
name: erp-public-data
description: Query public ERP data via the erp-public-api agent.
credentials:
  - slot: erp-public-api
    type: agent_api
    description: Read-only connection to the erp-public-api producer agent
---
```

Validation rules (implemented once, in `skill_manifest.py`):

| Rule | Detail |
|---|---|
| Absent key, or empty value (`credentials:` alone parses to `""`) | Valid. Zero declarations. |
| Value type | Must be a list whose items are all dicts. Otherwise invalid. |
| `slot` | `str`, stripped, 1–255 chars, matches `SKILL_CREDENTIAL_SLOT_RE = ^[A-Za-z0-9][A-Za-z0-9._:/@+\-]*$` |
| `type` | `str` in `SKILL_CREDENTIAL_TYPES` = every `CredentialType` value **except** `mcp_provider` (D8) |
| `description` | Optional. `str`, ≤ 1024 chars (`MAX_DESCRIPTION_LENGTH`). |
| Duplicates | The same `slot` twice (exact, case-sensitive) is invalid, whatever the type. |
| Count | ≤ `MAX_SKILL_CREDENTIALS = 20` |
| Unknown item keys | Ignored (forward-compatible, e.g. a later `required: false`). |
| Normalised form | `{"slot": str, "type": str, "description": str \| None}` |
| Issue | **error** code `invalid_credentials`. Message `"The credentials block in SKILL.md is invalid: <first problem>."` The skill is excluded from projection and refused at publish (`skill_invalid`), like any other error. |

### C2. Revision spec dict (`SkillPackageRevision.required_credential_specs[i]`)

This is the same schema as `AgentBundleRevision.required_credential_specs`, written by
`credential_spec.build_spec`. Keys, in emission order:

`name` (= slot) · `type` · `allow_sharing` · `allow_template_sharing` · `description` · `provided_by`
(`user|publisher|template`) · `publisher_credential_id` (str | null) · `service_uri` (= slot) ·
[`template_data`, `template_private_fields`, only when `provided_by="template"`] ·
[`producer_agent_id` (str), only for `type="agent_api"` when the matched credential carries one, and
appended by the skill caller (D9)].

`parse_credential_spec` is the single reader. It gains
`ParsedCredentialSpec.producer_agent_id: uuid.UUID | None = None`, read tolerantly (old JSON → `None`).
**The slot of a parsed spec is `parsed.service_uri or parsed.name`.**

### C3. Public projections (Pydantic, no secrets)

- `SkillCredentialDeclarationPublic { slot: str, type: str, description: str | None }`: what a
  skill's index entry declares.
- `SkillCredentialRequirementPublic { slot, type, description, provided_by, publisher_credential_id: UUID | None, producer_agent_id: UUID | None }`:
  what a published revision requires.
- `SkillPublishCredentialPreview { slot, type, description, provided_by, credential_id: UUID | None, credential_name: str | None, producer_agent_id: UUID | None, reason: str | None }`.
  `reason` explains a `user` resolution: `no_linked_credential` | `not_shareable` | `not_owned` | `template_would_leak_secret` (D12).
  `credential_*` refers to the **publisher's own** matched credential.
- `SkillCredentialProvisionPublic { slot, type, description, provided_by, outcome: SlotOutcome, credential_id: UUID | None, credential_name: str | None }`.
  `credential_name` is filled only for credentials the installer owns or already has a share on. It
  is never filled for a publisher credential before the share exists.
- `AddonCredentialIssuePublic { slot: str, type: str, reason: "not_linked" | "not_configured" | "access_revoked" }`
- `CredentialSkillUsage { package_uuid: UUID, package_id: str, display_name: str, revision_numbers: list[int] }`

### C4. `SlotOutcome` (install report and install preview use one enum)

| Value | Meaning |
|---|---|
| `already_linked` | This agent already links a credential that satisfies the slot. Nothing to do. |
| `linked_publisher` | The publisher's credential is shared (`skill_install`, or no share when installer == publisher) and linked. |
| `linked_existing` | A credential the installer owns, or has a share on, carries this slot and is linked (D3). It may itself be a placeholder from an earlier install. |
| `template_materialised` | A placeholder is created from the publisher's template and linked. |
| `placeholder_created` | An empty placeholder is created (`name=slot`, `service_uri=slot`) and linked. |
| `publisher_unavailable` | A `provided_by="publisher"` spec could not be satisfied (credential gone, sharing off, owner ≠ publisher), and no own slot credential exists. A placeholder is created. The report is `degraded`. |

### C5. Addons status

The new row `status_code` is `credential_missing`, with `status="warning"`. It carries
`credential_issues: list[AddonCredentialIssuePublic]`.

### C6. `credentials.json` entry (real credentials)

`{ "id", "name", "type", "notes", "service_uri": str | null, "is_placeholder": bool, "credential_data": {…whitelisted…} }`

### C7. Container SDK (`core/cinna_api/credentials.py`)

- `credentials.by_slot(slot: str) -> dict | None`
- `credentials.require_slot(slot: str) -> dict`, which raises `CredentialMissing`
- `credentials.agent_api_session(slot: str) -> AgentApiSession` (a `requests.Session` subclass)
- `class CredentialMissing(Exception)`, with attributes `slot: str` and `reason: "not_linked" | "not_configured"`.

  `str(exc)` is stable:
  - not_linked: `credential_missing: no credential for slot '<slot>' is linked to this agent. Fix: open the agent's Credentials tab and link a credential whose service URI (slot) is '<slot>'.`
  - not_configured: `credential_missing: the credential for slot '<slot>' is linked but not filled in yet. Fix: open the agent's Credentials tab and complete it.`

---

## 5. Architecture overview

### New and changed backend units

| Unit | Kind | Phase |
|---|---|---|
| `skill_manifest.py` (both copies) | parser + validation + `SkillEntry.credentials` | 1 |
| `SkillPackageRevision.required_credential_specs` + migration | column | 1 |
| `credential_spec.build_spec` | extracted single writer | 1 |
| `services/skills/skill_credential_requirements.py` → `SkillCredentialRequirements` | publish derivation, spec projections; `SkillSlotIndex` (Phase 2) | 1, 2 |
| `CredentialsService.get_agent_credentials_with_data` + README render | top-level `service_uri` / `is_placeholder` | 1 |
| `core/cinna_api/credentials.py` | slot helpers | 1 |
| `CredentialsService.find_slot_match` | extracted tier 0 | 2 |
| `services/credentials/credential_provisioner.py` → `CredentialProvisioner` | provisioning chokepoint | 2 |
| `SkillCatalogService.install_into_agent` / `upgrade_link` / `install_preview`; `LLMPluginService.uninstall_plugin_link` | wiring | 2 |
| `AddonsService` + `InstallReadinessGate` | status + D1 exclusion | 2 |
| `classify_credential_category`, `get_deletion_impact` | skill awareness | 2 |

### Handoffs (what one step writes, what the next one reads)

| Writer | Artifact | Readers |
|---|---|---|
| `parse_skill_dir` (host, at publish/preview) | `SkillEntry.credentials` (C1 normalised) | `SkillCredentialRequirements.resolve_for_publish` |
| `SkillCredentialRequirements.build_specs` → `build_spec` | `revision.required_credential_specs` (C2) | `parse_credential_spec` → provisioner, `SkillSlotIndex`, `specs_to_public`, deletion impact |
| `CredentialProvisioner.provision` | `CredentialShare(source="skill_install")`, `AgentCredentialLink`, placeholder `Credential(service_uri=slot, is_placeholder=True)` | `find_slot_match` (idempotency), `SkillSlotIndex` (status, gate), `classify_credential_category`, `release_skill_slots` |
| `get_agent_credentials_with_data` | `credentials.json` C6 | SDK C7 |

---

## 6. Security architecture

- **No secret travels in a skill.** The declaration holds slot/type/description only. The existing
  filename secret gate (`validate_tree`, `skill_contains_secrets`) is untouched.
- **Consent is the credential owner's.** A `publisher` spec needs a credential **owned** by the
  publisher with `allow_sharing=True`, both at publish (D4) and at install (I7). A `template` spec
  needs `allow_template_sharing=True`. The payload goes through `_template_payload_for`, which
  enforces private fields, `_TEMPLATE_FORCE_PRIVATE_TYPES` and the per-type allowlist.
- **Audience.** Only users the package visibility already admits can install (`get_package` 404s
  otherwise), so only they can receive a `skill_install` share. Revoking a `users` grant stops new
  installs. Existing shares persist until the credential owner revokes them, the same as bundles.
- **Identity at the producer.** A shared `agent_api` connection token is used from the installer's
  container. The proxy attributes calls through the separately minted `owner_identity_token` of the
  **installer**, and scopes come from `agent_api_access_grant`. Nothing here changes. Known
  trade-offs, as for bundles: a shared rate budget, and no per-installer token revocation (per-user
  revocation is deleting that user's `CredentialShare`).
- **External keys** (`agent_api`, `kind="external"`) can never be `allow_sharing` true
  (`assert_sharing_allowed`), so they can never be publisher-provided. They are also never synced
  into a container.
- **Top-level `service_uri` / `is_placeholder`** are non-secret identifiers or flags. They bypass the
  whitelist on purpose (I4). `service_uri` is user-editable free text, so the README render must
  JSON-encode it (it already renders via `json.dumps`).
- **Exposure in public schemas.** `publisher_credential_id` and `producer_agent_id` are ids, not
  secrets (brief). No credential name of the publisher is shown to non-share-holders (C3).
- **Authorization of new routes.** `install-preview` uses the same gates as install: `_get_agent`
  (owner-only, 404 for others) and `SkillCatalogService.get_package` (visibility 404).
- **Rate limiting:** none added. The preview is a read of the same cost as the install context.

---

## 7. Phase 1 — Foundation (backend + env-core)

### Prerequisites
- Tree at or after commit `f2664d3a`. Docker services up.
- Run `docker compose exec backend alembic heads` and confirm the single head. It was `d7b41e0c9a35`
  on 2026-09-10. If it moved, use the new head as `down_revision`.

### Scope
Parser extension (both copies), `invalid_credentials` validation, `SkillEntry.credentials`;
`required_credential_specs` column plus migration; `build_spec` extraction; publish derivation,
preview and public schemas; top-level `service_uri` / `is_placeholder` in the env payload plus the
README; SDK `by_slot` / `require_slot` / `agent_api_session`; `BUILDING_AGENT.md` guidance.
**SKIP `docs/**`.**

### 7.1 Parser: block sequence of flat mappings
File: `backend/app/services/agents/skill_manifest.py`. When done, copy the whole file byte-identically
to `backend/app/env-templates/app_core_base/core/server/skill_manifest.py` (I3).

- Add module constant `_ITEM_KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:\s+(.*))?$")`. It matches
  only when the colon is followed by whitespace or end of line (D10).
- In `parse_frontmatter`, "Empty value" branch (currently :507–535):
  - Keep a `current_item: dict | None = None`.
  - A child line starting `"- "` whose remainder matches `_ITEM_KEY_RE`: start a new dict item
    `{key: _coerce_scalar(value or "")}`, append it to `items`, and set `current_item` to it.
  - A child line starting `"- "` whose remainder does not match: append the scalar exactly as today
    and set `current_item = None`.
  - An indented non-dash line matching the existing key regex **while `current_item` is not None**:
    set `current_item[key] = _coerce_scalar(value)`.
  - A non-dash line when `current_item is None`: goes to `nested`, exactly as today.
  - Items stay flat. No flow sequences or deeper nesting inside an item (values are scalars).
- Update the module docstring section "How the frontmatter parser diverges from real YAML" with one
  bullet. It states the item-mapping rule, the whitespace-after-colon condition, that values inside
  an item are scalars, and the behaviour change (a pre-existing `- key: value` item that used to
  parse as the string `"key: value"` now parses as a one-key mapping).

### 7.2 Validation + `SkillEntry.credentials`
Same file, then copy (I3).

- Constants (under "Contract constants"):
  - `SKILL_CREDENTIAL_SLOT_RE`, `MAX_SLOT_LENGTH = 255`, `MAX_SKILL_CREDENTIALS = 20`.
  - `SKILL_CREDENTIAL_TYPES: frozenset[str]`, listing `email_imap, email_smtp, odoo, gmail_oauth,
    gmail_oauth_readonly, gdrive_oauth, gdrive_oauth_readonly, gcalendar_oauth,
    gcalendar_oauth_readonly, google_service_account, api_token, ssh_key, agent_api`. Add a comment:
    vendored mirror of `CredentialType` minus `mcp_provider` (D8), guarded by a unit test.
- `ISSUE_MESSAGES["invalid_credentials"] = "The credentials block in SKILL.md is invalid."` (in the
  errors group).
- New public function
  `parse_credential_declarations(raw: Any) -> tuple[list[dict[str, Any]], str | None]`.
  It implements C1 and returns `(normalised, first_problem_sentence_or_None)`. On a problem the list
  is `[]`.
- `parse_skill_dir`:
  - `_fail(code)` → `_fail(code, message: str = "")`, passing `message` to `SkillIssue`.
  - After the `description_too_long` check, call `parse_credential_declarations(frontmatter.get("credentials"))`.
    On a problem, return `_fail("invalid_credentials", f"The credentials block in SKILL.md is invalid: {problem}.")`.
  - Pass `credentials=normalised` into the returned `SkillEntry`.
  - Add `invalid_credentials` to the docstring's error-code list.
- `SkillEntry`: new field `credentials: list[dict[str, Any]] = field(default_factory=list)`, after
  `secret_paths`. `to_dict` always adds `"credentials": [dict(c) for c in self.credentials]`.

### 7.3 env-core index model
File: `backend/app/env-templates/app_core_base/core/server/models.py` (`class SkillEntry`, ~:304).
Add `class SkillCredentialDeclaration(BaseModel): slot: str; type: str; description: str | None = None`
and the field `credentials: list[SkillCredentialDeclaration] = []`. This keeps
`GET /config/skills` shape-identical to `SkillEntry.to_dict()`, since
`agent_env_service.py:2793` already serialises `to_dict()`.

### 7.4 Backend index cache + public schema
- `backend/app/services/agents/agent_skills_service.py`, `get_cached_entries` (~:271): pass
  `credentials=` built tolerantly from `row.get("credentials")`. Keep only dict items with str
  `slot` and `type`; otherwise use `[]`. A pre-feature cache row has no key and yields `[]`. Verify
  that `_normalise_entries` does not strip the key, and extend it if it does.
- `backend/app/models/agents/agent_skills.py`: add `SkillCredentialDeclarationPublic` (C3) and
  `SkillEntryPublic.credentials: list[SkillCredentialDeclarationPublic] = []`.
- `AgentSkillsService.entry_to_public`: map `credentials`.

### 7.5 Column + migration
- `backend/app/models/skills/skill_package_revision.py`: add
  `required_credential_specs: list = Field(default_factory=list, sa_column=Column(JSON, nullable=False, server_default=text("'[]'::json")))`.
  Copy the definition shape from `AgentBundleRevision.required_credential_specs`
  (`backend/app/models/bundles/agent_bundle_revision.py:110`). The comment says "names, types,
  provisioning mode; never secret values (template private fields are stripped at publish)".
- Migration: `make migration`, then hand-edit to
  `backend/app/alembic/versions/<12-hex>_add_skill_package_revision_required_credential_specs.py`.
  - `down_revision = 'd7b41e0c9a35'` (or the verified head).
  - `upgrade`: `op.add_column('skill_package_revision', sa.Column('required_credential_specs', sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")))`.
  - `downgrade`: `op.drop_column('skill_package_revision', 'required_credential_specs')`. Warn in the
    docstring that downgrading loses the frozen provisioning of every published revision.
    Reinstalling then treats every slot as absent (no provisioning).
  - The docstring explains why the default is `[]` (existing revisions declared nothing).
- `make migrate`.

### 7.6 `build_spec` extraction (single writer)
File: `backend/app/services/bundles/credential_spec.py`.

- New function:
  `build_spec(session: Session, *, credential: Credential | None, credential_type: str, provided_by: Literal["user","publisher","template"], name: str, service_uri: str | None, description: str | None) -> dict`
  - Emits exactly the keys and order of today's `_collect_credential_specs` body
    (`publish_service.py:775–794`):
    - `allow_sharing` / `allow_template_sharing` come from `credential`, or `False` when it is `None`;
    - `publisher_credential_id` is `str(credential.id)` iff `provided_by == "publisher"`;
    - when `provided_by == "template"`, it appends `template_data`, `template_private_fields` from
      `PublishService._template_payload_for(session, credential)` (a lazy import to avoid the cycle;
      that module already imports this one).
  - `provided_by in ("publisher", "template")` with `credential is None` → `ValueError`.
  - Update the module docstring: now the single writer **and** the single reader of the spec schema.
- `ParsedCredentialSpec`: add the last field `producer_agent_id: uuid.UUID | None = None`.
  `parse_credential_spec` reads `spec.get("producer_agent_id")` tolerantly, like
  `publisher_credential_id`.
- `backend/app/services/bundles/publish_service.py`, `_collect_credential_specs`: the loop body
  becomes `build_spec(session, credential=cred, credential_type=<cred.type value>, provided_by=PublishService.resolve_provided_by(cred, install), name=cred.name, service_uri=cred.service_uri, description=cred.notes or None)`.
  **I1**: diff the emitted dicts in the bundle regression tests.

### 7.7 Publish derivation, preview, public schemas
New file `backend/app/services/skills/skill_credential_requirements.py`:

- `@dataclass(frozen=True) class SkillCredentialResolution: slot: str; type: str; description: str | None; provided_by: Literal[...]; credential: Credential | None; reason: str | None; producer_agent_id: uuid.UUID | None`
- `class SkillCredentialRequirements` (static methods):
  - `resolve_for_publish(session, *, agent: Agent, publisher: User, declarations: list[dict]) -> list[SkillCredentialResolution]` (read-only):
    - Load the agent's linked credentials in **one** query (`AgentCredentialLink` join `Credential`
      where `agent_id == agent.id`).
    - Per declaration, candidates = linked credentials with `type == CredentialType(decl["type"])`
      and `service_uri == decl["slot"]`, ordered by id desc.
    - Owned by `publisher.id`, if any:
      - one with `allow_sharing` → `publisher`;
      - else one with `allow_template_sharing` → `template`;
      - else `user` with reason `not_shareable` (the credential is still returned for the preview name).
      - Placeholders are excluded from candidates (D14); `agent_api` is never `template`, and `template` requires no leaking secret field, else `user`/`template_would_leak_secret` (D12).
    - Only non-owned candidates → `user`, reason `not_owned`, `credential=None`.
    - No candidates → `user`, reason `no_linked_credential`.
    - `description = decl.get("description") or (owned_match.notes if provided_by in ("publisher", "template") else None)`. A `user` resolution never falls back to notes (D13).
    - For `agent_api` with an owned match: decrypt (`CredentialsService.decrypt_credential_data`) and
      read `producer_agent_id` tolerantly (a bad UUID → `None`). A decrypt failure → `None`, never an
      error.
  - `build_specs(session, resolutions) -> list[dict]`:
    - Per resolution, call `build_spec(session, credential=res.credential if res.provided_by != "user" else None, credential_type=res.type, provided_by=res.provided_by, name=res.slot, service_uri=res.slot, description=res.description)`.
    - Then, if `res.type == "agent_api"` and `res.producer_agent_id`, set
      `spec["producer_agent_id"] = str(...)` (D9).
    - A `ValueError` from `_template_payload_for` propagates.
  - `to_publish_preview(resolutions) -> list[SkillPublishCredentialPreview]` (C3).
  - `specs_to_public(raw_specs: list | None) -> list[SkillCredentialRequirementPublic]`: via
    `parse_credential_spec`; slot = `parsed.service_uri or parsed.name`; skips unparseable entries.
- `backend/app/services/skills/skill_catalog_service.py`, `publish_from_agent`:
  - **Inside the lock, after the grant-visibility check (step 5) and before `_resolve_package`**:
    every refusal still runs before the first write. Compute
    `resolutions = resolve_for_publish(session, agent=agent, publisher=user, declarations=entry.credentials)`
    and `specs = build_specs(session, resolutions)`.
  - Map a `ValueError` to `SkillCatalogError("credential_template_unreadable", <message>)`, and add
    that code to `STATUS_BY_CODE` in `backend/app/services/skills/exceptions.py` as **409**.
  - Pass `required_credential_specs=specs` to the `SkillPackageRevision(...)` constructor.
- `publish_preview`: `credentials = to_publish_preview(resolve_for_publish(...))` when
  `entry.error is None`, else `[]`.
- `backend/app/models/skills/schemas.py`:
  - add `SkillCredentialRequirementPublic` and `SkillPublishCredentialPreview` (C3);
  - `SkillPublishPreview.credentials: list[SkillPublishCredentialPreview] = []`;
  - `SkillPackageRevisionPublic.required_credentials: list[SkillCredentialRequirementPublic] = []`.
  - `SkillPackageEntry` / `SkillPackageDetailPublic` inherit through `latest_revision` / `revisions`.
- `SkillCatalogService.revision_to_public` (~:1398): add
  `required_credentials=SkillCredentialRequirements.specs_to_public(revision.required_credential_specs)`.
- Keep the imports in `skill_credential_requirements.py` one-way. It may import `credential_spec`,
  `CredentialsService`, models. Nothing in `bundles/` imports it.

### 7.8 Env payload: top-level `service_uri` + `is_placeholder`
File: `backend/app/services/credentials/credentials_service.py`.

- `get_agent_credentials_with_data` (:180): each dict becomes
  `{"id", "name", "type", "notes", "service_uri": cred.service_uri, "is_placeholder": bool(cred.is_placeholder), "credential_data"}`.
  Keep the `api_token` in-data `service_uri` injection (:215–219).
  - Verified consumers: `prepare_credentials_for_environment` (:1338), which uses `copy.deepcopy`
    and filters only `credential_data`, so it preserves the keys; and
    `improvement_request_service.py:349` → `secret_scrubber.collect_credential_secrets`, which reads
    only `type` / `credential_data`, so it is unaffected.
- `generate_credentials_readme` (:777): add `service_uri` and `is_placeholder` to each
  `credentials_for_display` item (same order as C6). Add a short section after the JSON block:
  - `## Slots (service_uri)`;
  - one sentence saying a slot is a non-secret id a skill uses to find its credential;
  - one line showing `credentials.require_slot("<slot>")`;
  - one line saying `is_placeholder: true` means linked but not filled in.
- Update the comment above `AGENT_ENV_ALLOWED_FIELDS["api_token"]` to note the type-agnostic
  top-level copy.

### 7.9 Container SDK
File: `backend/app/env-templates/app_core_base/core/cinna_api/credentials.py` (stays importable
without network; `requests` is imported lazily).

- Module constants `_SYNTHETIC_TYPES = frozenset({"current_user", "<OWNER_IDENTITY_TYPE value>"})`.
  **Read the literal from `AgentApiIdentityService.OWNER_IDENTITY_TYPE`
  (`backend/app/services/agent_api/agent_api_identity_service.py`) and the `current_user` type from
  `user_details_service.build_current_user_block`. Do not guess.** The unit test in §7.11 asserts
  the mirror.
- `class CredentialMissing(Exception)`: `__init__(self, slot: str, reason: str)`; `__str__` is the
  C7 text.
- `_Credentials.by_slot(slot) -> dict | None`: the first non-synthetic entry whose top-level
  `service_uri == slot` (read fresh).
- `_Credentials.require_slot(slot) -> dict`:
  - `None` → `CredentialMissing(slot, "not_linked")`;
  - `entry.get("is_placeholder") is True` → `CredentialMissing(slot, "not_configured")`;
  - otherwise the entry.
- `_Credentials.agent_api_session(slot) -> AgentApiSession`:
  - Run `require_slot`. The type must be `agent_api`, else `ValueError` naming the actual type.
  - Build the session:
    - `base_url` / `spec_url` / `token` come from `credential_data`;
    - `headers["Authorization"] = f"Bearer {token}"`;
    - if an `owner_identity_token` entry exists, set
      `headers[entry.credential_data["header"]] = entry.credential_data["token"]`.
  - `AgentApiSession(requests.Session)` exposes `.base_url` and `.spec_url`. It overrides
    `request(method, url, *args, **kwargs)` to join a relative `url` onto `base_url` with exactly one
    `/`; absolute `http(s)://` URLs pass through.
  - Define the subclass lazily (first call) so importing the module never imports `requests`.
- `core/cinna_api/__init__.py`: export `CredentialMissing` (add to `__all__` and the docstring's
  usage block).
- **Import-path verification (required, record the result in the phase report).**
  - Scripts run with `uv run python …` under `/app/.venv`, which already has `fastapi` and
    `requests` (`backend/app/env-templates/general-env/pyproject.toml`). The env sets
    `PYTHONPATH=/app` (`general-env/Dockerfile:78`).
  - Confirm which import resolves for a workspace script: `from core.cinna_api import credentials,
    CredentialMissing`, or bare `from cinna_api import …` (which needs `/app/core` on `sys.path`, as
    `harvest.py` arranges for the producer). Document the one that works in §7.10.
  - Also confirm that importing `core.cinna_api` does not import the env-core server
    (`core/__init__.py`).

### 7.10 `BUILDING_AGENT.md`
File: `backend/app/env-templates/app_core_base/core/prompts/BUILDING_AGENT.md`. Add a subsection
`### Skills that need a credential` inside `## Agent Skills (/app/workspace/skills/)` (~:605), after
`### The SKILL.md contract`. Content:

- the `credentials:` block from C1 and its rules in one list (slot = the credential's service URI;
  allowed types; no `mcp_provider`);
- that tokens never go in the skill folder;
- how scripts consume a slot (`require_slot`, `agent_api_session`), using the verified import path;
- the SKILL.md body convention: *"If a script fails with `credential_missing`, stop and relay its
  message to the user verbatim — it names the slot and where to fix it. Do not guess another
  credential."*;
- what publishing does with each slot (owned + sharing on → installers receive it; template;
  otherwise installers bring their own).

Note for the phase report: environments must be **rebuilt** to receive the new SDK and parser, since
`/app/core` is a per-environment template copy. Pre-feature containers keep working without the
helpers.

### 7.11 Tests (Phase 1)
Read `backend/tests/README.md` and `backend/tests/api/agents/README.md` first.

- **New topic group** `backend/tests/api/agents/skill_credentials/` with `__init__.py`. Add a row to
  the group table in `backend/tests/api/agents/README.md`. `core/` already holds 17 files, over the
  README's ~12 split threshold. This feature adds ≥ 3 files.
- `backend/tests/unit/test_skill_manifest.py` (extend, unit):
  - a sequence of mapping items with continuation lines;
  - `- http://x/y` and `- Bash(git:*)` stay scalars;
  - mixed scalar and mapping items;
  - existing nested-mapping and scalar-list fixtures unchanged;
  - `invalid_credentials` for: non-list, scalar items, missing slot, bad slot (whitespace), slot
    > 255, unknown type, `mcp_provider`, duplicate slot, > 20 items, non-str description;
  - a valid block → `SkillEntry.credentials` normalised and present in `to_dict()`;
  - an empty `credentials:` → `[]`;
  - `SKILL_CREDENTIAL_TYPES == {t.value for t in CredentialType} - {"mcp_provider"}`;
  - the byte-identity test keeps passing.
- `backend/tests/unit/test_cinna_api_credentials_slots.py` (new, unit):
  - monkeypatch `core.cinna_api.credentials._CREDENTIALS_PATH` to a tmp file;
  - `by_slot` hit and miss, synthetic entries ignored;
  - `require_slot` reasons and the exact message prefix `credential_missing:`;
  - `agent_api_session` headers (Bearer + identity header from the synthetic entry) and relative-URL
    join, asserted on a `PreparedRequest` or a patched `requests.Session.request`, with no network;
  - `_SYNTHETIC_TYPES` includes `AgentApiIdentityService.OWNER_IDENTITY_TYPE`.

  Cross-reference the API test file per the README convention.
- `backend/tests/api/agents/skill_credentials/agents_skill_credentials_publish_test.py` (API-only).
  Use `tests/utils/skill_catalog.py` (`make_developer`, `make_agent_with_env`, `write_skill(frontmatter=…)`,
  `publish_skill`, `get_skill_package`) and `tests/utils/credential.py` (`create_random_credential`,
  `update_credential` for `service_uri`, `link_credential_to_agent`, `set_credential_sharing`).
  Scenarios:
  1. **Resolution matrix via preview and publish.** One skill declares four `api_token` slots:
     - owned + `allow_sharing` → `publisher`;
     - owned + template sharing → `template`;
     - owned, not shareable → `user`/`not_shareable`;
     - no linked credential → `user`/`no_linked_credential`.

     `GET …/publish-preview` returns `credentials` accordingly. Publish, then
     `GET /skills/packages/{id}` → `revisions[0].required_credentials` matches. The response JSON
     contains no `template_data` / `template_private_fields` key anywhere.
  2. **`not_owned`.** A credential shared *to* the publisher and linked with the slot → `user`/`not_owned`.
  3. **Immutability.** Flip sharing, republish: the new revision reflects the new `provided_by`, and
     revision 1 is unchanged.
  4. **Invalid declaration.** Preview returns 200 with `credentials == []`. Publish is refused with
     code `skill_invalid`, and its message mentions the credentials block.
  5. **`agent_api` slot records `producer_agent_id`.** Build the connection the way
     `tests/api/agents/bundles/agents_bundles_pbp_agent_api_test.py` does.
- `backend/tests/api/credentials/test_credential_service_uri_env_sync.py` (API-only). Follow the
  env-capture pattern of `tests/api/credentials/test_ssh_key_credential_env_sync.py` and
  `tests/utils/credential.real_credentials_json`:
  - an `api_token` and an `odoo` credential with `service_uri` linked to an agent: every real
    `credentials_json` entry has top-level `service_uri` and `is_placeholder`;
  - `api_token` `credential_data` still carries its in-data `service_uri`;
  - the README text contains the `service_uri` values and the "Slots" section;
  - a credential with no `service_uri` has `"service_uri": null`.

### 7.12 Regression runs (must be green)
`tests/unit/test_skill_manifest.py`, `tests/unit/test_cinna_api_credentials_slots.py`,
`tests/api/agents/skill_credentials/`, `tests/api/agents/bundles/`,
`tests/api/agents/bundles_install/`, `tests/api/agents/core/`, `tests/api/credentials/`.
**No edits to the existing bundle/credentials test files (I1, I2).**

### 7.13 Client regeneration
`source ./backend/.venv/bin/activate && make gen-client`. Commit the regenerated `frontend/src/client/`
with the phase. No frontend code changes in this phase.

### Definition of done (Phase 1)
_Met on 2026-09-10 (see §15)._
- [x] Both parser copies identical. The unit suite is green.
- [x] Migration applied. `alembic heads` shows one head.
- [x] Publishing a skill with a `credentials:` block writes C2 specs. Preview and package detail
      expose C3 shapes.
- [x] Bundle publish specs byte-identical (I1). All bundle/credentials suites green, untouched.
- [x] `credentials.json` entries carry top-level `service_uri` + `is_placeholder` (I4). The README
      documents slots.
- [x] SDK helpers exist, are unit-tested, and the import path is verified and documented in
      `BUILDING_AGENT.md`.
- [x] Client regenerated. `docs/**` untouched.

---

## 8. Phase 2 — Provisioning (backend)

### Prerequisites
Phase 1 DoD met: `SkillPackageRevision.required_credential_specs` exists,
`SkillCredentialRequirements` exists, `ParsedCredentialSpec.producer_agent_id` exists. **The team
lead has confirmed D1** (non-blocking). If the lead chose the blocking alternative, skip §8.6 and
apply its alternative note.

### Scope
`find_slot_match`; `CredentialProvisioner` extraction with the bundle suites green and untouched;
skill install, upgrade and uninstall wiring; credential sync; `install-preview` endpoint;
`SkillSlotIndex`; `credential_missing` row status; gate exclusion (D1); `skill_install` classifier;
deletion-impact skill awareness. **SKIP `docs/**`.**

### 8.1 `CredentialsService.find_slot_match`
File: `backend/app/services/credentials/credentials_service.py`.

- New
  `find_slot_match(session, *, user_id: uuid.UUID, credential_type: CredentialType, service_uri: str) -> Credential | None`.
  It holds exactly the tier-0 bodies currently inline in `find_match_for_spec` (:2219–2249): owned
  newest first, then shared through `CredentialShare`, newest first. An empty `service_uri` → `None`.
- `find_match_for_spec` tier 0 → `if service_uri: match = find_slot_match(...); if match: return match`
  (I5). Mention it in the docstring.

### 8.2 `CredentialProvisioner`
New file `backend/app/services/credentials/credential_provisioner.py`. It is **sync** and never
commits (it uses `session.flush()`).

- Types:
  - `SlotOutcome = Literal[...]` (C4).
  - `@dataclass(frozen=True) class PublisherBoundary: user_id: uuid.UUID | None`
  - `@dataclass(frozen=True) class ProvisionPolicy:`
    - `share_source: Literal["bundle_install","skill_install"]`
    - `auto_link_by_slot: bool`
    - `placeholder_name_mode: Literal["suffixed","slot"]`
    - `placeholder_notes: str`
    - `placeholder_stamps_slot: bool` (sets `service_uri=slot` and `user_workspace_id=agent.user_workspace_id`)
    - `template_notes_fallback: str`
    - `honour_user_selections: bool`
  - `BUNDLE_INSTALL_POLICY = ProvisionPolicy("bundle_install", False, "suffixed", "Placeholder for required bundle credential.", False, "Created from bundle template.", True)`
  - `SKILL_INSTALL_POLICY = ProvisionPolicy("skill_install", True, "slot", "Required by an installed skill. Fill it in on the agent's Credentials tab.", True, "Created from a skill template.", False)`
  - `@dataclass class SlotProvision: spec_name: str; spec_type: str; slot: str | None; provided_by: str; description: str | None; outcome: SlotOutcome; credential_id: uuid.UUID | None`
  - `@dataclass class ProvisionReport: items: list[SlotProvision]; degraded: bool; changed: bool`
  - `class ProvisioningSelectionError(Exception)` with `spec_name` and `message`.
- `CredentialProvisioner.provision(session, *, agent: Agent, specs: list[ParsedCredentialSpec], publisher: PublisherBoundary | None, policy: ProvisionPolicy, user_selections: dict | None = None) -> ProvisionReport`
  - **Bundle policy**: reproduce today's `_setup_install_credentials` loop exactly, in the order
    template → publisher → user:
    - the `use_existing` selection rules, the owned-or-shared check and the fallback warnings;
    - the unknown-type skip;
    - the placeholder shape `name=f"{parsed.name} (placeholder)"`, `notes=policy.placeholder_notes`,
      `encrypted_data=encrypt_field(json.dumps({}))`, `is_placeholder=True`, `allow_sharing=False`;
    - the template materialisation identical to `_materialise_template_credential`;
    - the publisher link identical to `_try_link_publisher_credential`, with the trust check:
      `publisher is not None and cred.owner_id != publisher.user_id` → fail. When the bundle row
      exists this compares against `publisher.user_id` **even when it is None**.
    - The 422 case raises `ProvisioningSelectionError(spec_name, <the exact current detail text>)`.
  - **Skill policy**, per spec (slot = `parsed.service_uri or parsed.name`, type = `CredentialType(parsed.type)`;
    an unknown type is skipped):
    1. **Already linked**: the agent already links a credential with `id == parsed.publisher_credential_id`,
       or with (`type`, `service_uri == slot`) → `already_linked`.
    2. `provided_by="publisher"`: shared publisher-link routine (trust boundary, `allow_sharing`,
       first-writer-wins `CredentialShare(source=policy.share_source, access_level="read")`, no
       share when owner == agent owner, idempotent link) → `linked_publisher`. On failure set
       `degraded=True` and fall through to step 4 with `publisher_failed=True`.
    3. `provided_by="template"`: `find_slot_match` hit → link → `linked_existing`. Otherwise
       materialise (notes `parsed.description or policy.template_notes_fallback`), then set
       `user_workspace_id=agent.user_workspace_id` → `template_materialised`. A materialisation
       failure falls to step 4 and sets `degraded`.
    4. `find_slot_match(user_id=agent.owner_id, credential_type=type, service_uri=slot)` hit → link
       → `linked_existing`. Otherwise create the placeholder: `name=slot`, `service_uri=slot`,
       `notes=policy.placeholder_notes`, `user_workspace_id=agent.user_workspace_id`, owner = agent
       owner, empty encrypted data, `is_placeholder=True`, `allow_sharing=False`. Link it →
       `publisher_unavailable` if `publisher_failed`, else `placeholder_created`.
  - Every link insert goes through one `_ensure_link(session, agent_id, credential_id) -> bool
    (inserted)`. `changed` = any insert or create.
  - Per-spec failures are logged (`logger.warning`, no secrets) and never raised for the skill
    policy (I8).
- `CredentialProvisioner.preview(session, *, agent, specs, publisher, policy) -> list[SlotProvision]`
  - Read-only. Runs the skill-policy decision tree without writes: the publisher branch **checks**
    owner, sharing flag and existence, but creates nothing.
  - `credential_id` is set for `already_linked` / `linked_existing`, and for `linked_publisher` only
    when the installer already owns or has a share on it.
  - Raises `ValueError` if `policy.auto_link_by_slot` is False (bundles do not use preview).
- `CredentialProvisioner.release_skill_slots(session, *, agent: Agent, released: list[ParsedCredentialSpec], retained: list[ParsedCredentialSpec]) -> bool`
  - For each released (type, slot) not in the retained set, take linked credentials with
    `is_placeholder=True AND owner_id == agent.owner_id AND type == type AND service_uri == slot`.
    Skip any claimed by the agent's bundle revision specs (same lookup as §8.5
    `bundle_claimed_ids`).
  - Delete the `AgentCredentialLink`. If the credential now has no `AgentCredentialLink` rows and is
    still a placeholder, delete the `Credential` (D5).
  - Returns `changed`. Never touches non-placeholders or shares.

### 8.3 Bundle wrapper (I2)
File: `backend/app/services/bundles/install_service.py`.

- `_setup_install_credentials` keeps its signature and `async`. Its body:
  - `bundle = session.get(AgentBundle, install.bundle_uuid) if install.bundle_uuid else None`
  - `specs` = the parsed non-None entries of `revision.required_credential_specs`
  - `report = CredentialProvisioner.provision(session, agent=install, specs=specs, publisher=PublisherBoundary(bundle.publisher_user_id) if bundle else None, policy=BUNDLE_INSTALL_POLICY, user_selections=user_provided_data)`
  - `except ProvisioningSelectionError as e: raise HTTPException(422, detail=e.message)`
  - `session.commit()`
  - if `report.degraded`: set `install.last_update_status = "degraded"`, add, commit, refresh.

  Keep the docstring, pointing at the provisioner.
- Delete `_materialise_template_credential` and `_try_link_publisher_credential` from `InstallService`.
  Their only callers were the loop (verified). Update the comment reference in
  `backend/app/services/bundles/catalog_service.py:297` to the provisioner.
- Run `tests/api/agents/bundles_install/` and `tests/api/agents/bundles/` **before** touching skill
  wiring. They must be green with no test edits.

### 8.4 Skill install, upgrade, uninstall wiring
- `backend/app/services/skills/skill_catalog_service.py`:
  - New `@dataclass class SkillInstallResult: link: AgentPluginLink; provisioning: ProvisionReport`.
  - `install_into_agent(...) -> SkillInstallResult`. After the duplicate checks:
    - `session.add(link)`, `session.flush()`;
    - `specs` = parsed `revision.required_credential_specs`;
    - `report = CredentialProvisioner.provision(session, agent=agent, specs=specs, publisher=PublisherBoundary(package.publisher_user_id), policy=SKILL_INSTALL_POLICY)`;
    - **one** `session.commit()`, then `session.refresh(link)`.
    - Log `skill_installed … credentials=<outcome counts>`.

    Verify that the route in `backend/app/api/routes/skills.py` is the only caller (grep); update
    any other caller.
  - `upgrade_link(session, link) -> AgentPluginLink` (signature unchanged). When the revision
    changes:
    - `previous_specs` = parsed specs of the old revision (empty if it is gone);
    - `added` = latest specs whose (type, slot) is not in `previous_specs`;
    - `CredentialProvisioner.provision(..., specs=added, publisher=PublisherBoundary(package.publisher_user_id), policy=SKILL_INSTALL_POLICY)`
      before the existing commit, in one transaction with the re-pin.
  - New `install_preview(session, *, agent: Agent, package: SkillPackage, revision: SkillPackageRevision) -> SkillInstallPreview`
    → `CredentialProvisioner.preview(...)` mapped to `SkillCredentialProvisionPublic`.
- `backend/app/services/plugins/llm_plugin_service.py`:
  - New `@dataclass class PluginUninstallResult: deleted: bool; credentials_changed: bool`.
  - New `uninstall_plugin_link(session, agent_id, link_id) -> PluginUninstallResult`. For a
    `source=catalog` link with a revision:
    - released = its revision specs; retained = specs of the agent's **other** catalog links'
      revisions;
    - `CredentialProvisioner.release_skill_slots(...)`;
    - then delete the link and commit once.
  - `uninstall_plugin_from_agent` becomes a wrapper returning `.deleted` (other callers are
    unchanged).
- Routes:
  - `backend/app/api/routes/skills.py` `install_agent_skill`:
    - `result = SkillCatalogService.install_into_agent(...)`;
    - `if result.provisioning.changed: await CredentialsService.sync_credentials_to_agent_environments(session, agent.id)`;
    - then the existing plugin sync with `plugin_link=result.link`;
    - set `response.credential_provisioning = [...]` (C3 `SkillCredentialProvisionPublic`, built by
      a service helper, not in the route) and return it.
  - `backend/app/models/plugins/llm_plugin.py` `PluginSyncResponse`: add
    `credential_provisioning: list[SkillCredentialProvisionPublic] = []`. It is additive; import the
    schema from `app.models.skills.schemas`. If that creates an import cycle, define the class in
    `llm_plugin.py` and re-export it.
  - New `GET /agents/{agent_id}/skills/install-preview` on `agent_router` in `routes/skills.py`:
    - query `package_id: uuid.UUID`, `revision_number: int | None = None`;
    - response `SkillInstallPreview { package_id: UUID, revision_number: int, credentials: list[SkillCredentialProvisionPublic] }`,
      a new schema in `backend/app/models/skills/schemas.py`;
    - `_get_agent` → `get_package` → `resolve_revision` → `install_preview`;
    - `SkillCatalogError` → `http_error_for`.

    Declare it **before** any `/{agent_id}/skills/{name}` GET route that could shadow
    `install-preview` as a `name`. Check the route order.
  - `backend/app/api/routes/llm_plugins.py`:
    - upgrade route (:437): after a successful upgrade of a `source=catalog` link, call
      `await CredentialsService.sync_credentials_to_agent_environments(session, agent_id)` before
      the plugin sync.
    - uninstall route (:368): use `uninstall_plugin_link`. If `credentials_changed`, sync credentials
      before the plugin sync.

### 8.5 `SkillSlotIndex` (one read model for status, gate and release)
Add to `backend/app/services/skills/skill_credential_requirements.py`:

- `@dataclass(frozen=True) class CredentialIssue: slot: str; type: str; reason: Literal["not_linked","not_configured","access_revoked"]`
- `class SkillSlotIndex`, built by
  `SkillSlotIndex.build_for_agent(session, agent: Agent) -> SkillSlotIndex` with a **constant number
  of queries** (I11):
  1. The agent's `source=catalog` `AgentPluginLink` rows.
  2. Their `SkillPackageRevision` rows (`id IN …`) → parsed specs per link id.
  3. The agent's linked credentials (`AgentCredentialLink` join `Credential`).
  4. `CredentialShare` rows for (foreign linked credential ids, `shared_with_user_id == agent.owner_id`).
  5. When `agent.installed_revision_id` is set: the bundle revision's spec lookup, the same keys as
     `InstallReadinessGate._spec_lookup_for_install` (publisher id, `name:<name>`). Expose it as
     `bundle_claimed_ids`, computed against the linked credentials.
- Spec satisfaction (one private function, used by every method). Candidates are linked credentials
  with `id == publisher_credential_id` or (`type` match and `service_uri == slot`). The spec is
  satisfied if any candidate is:
  - owned and not a placeholder, or
  - foreign with `allow_sharing` and a share row.

  Otherwise the reason is:
  - no candidates → `not_linked`;
  - any owned placeholder → `not_configured`;
  - else `access_revoked`.
- `issues_for_link(link_id) -> list[CredentialIssue]`
- `skill_provisioned_credential_ids() -> set[uuid.UUID]`: candidates of every catalog spec, minus
  `bundle_claimed_ids`.
- `specs_for_link(link_id) -> list[ParsedCredentialSpec]` (used by uninstall retained/released).

### 8.6 Addons status + gate exclusion (D1)
- `backend/app/models/agents/addons.py`:
  - add `AddonCredentialIssuePublic` (C3);
  - `AddonPublic.credential_issues: list[AddonCredentialIssuePublic] = []`;
  - extend the `status_code` docstring with `credential_missing`.
- `backend/app/services/agents/addons_service.py`:
  - In `build`, build `SkillSlotIndex.build_for_agent(session, agent)` once, and **only** when at
    least one link has `source == catalog`.
  - For each catalog link row, set `row.credential_issues` from `issues_for_link(link.id)`.
  - `_settle_status`: insert, **after** the `not_materialized` / `unverified` block and **before**
    the skill-warning loop:
    `if row.credential_issues: row.status = STATUS_WARNING; row.status_code = "credential_missing"; return`.
    The signature is unchanged.
- `backend/app/services/bundles/install_readiness_gate.py`:
  - `GateMissingItem` gains a trailing `credential_id: uuid.UUID | None = None`, set in
    `_scan_service_credentials`. It is not serialised: `_missing_payload` and the setup-status
    response list their keys explicitly, so verify both stay unchanged.
  - At the end of `_scan_service_credentials`: **only if `items` is non-empty**, build
    `SkillSlotIndex.build_for_agent(session, install)` and drop items whose `credential_id` is in
    `skill_provisioned_credential_ids()`. This adds zero queries on the ready path.
  - Add a docstring paragraph for D1.
  - *Alternative if the lead rejects D1*: omit this step. Change `_format_user_message` so a
    non-bundle agent (`install.bundle_uuid is None`) gets "This agent needs setup before it can run.
    Open its Credentials tab…" instead of bundle wording.

### 8.7 Share source + classifier (D6)
- `backend/app/services/credentials/credentials_service.py` `classify_credential_category`:
  - for a shared credential, `share_source == "skill_install"` → `"automatic"`;
  - docstring rule list: new rule 4b; rule "Shared (not owned) credentials are never automatic"
    reworded.
- `backend/app/services/credentials/credential_share_service.py:245–250`: update the comment.
- `backend/app/models/credentials/credential_share.py` `source` comment, and the `source` comments in
  `backend/app/models/credentials/credential.py` (~:88, ~:113): add `"skill_install"`. It fits
  `varchar(20)` (13 chars), so no migration.

### 8.8 Deletion impact
- `backend/app/models/credentials/credential.py`:
  - add `CredentialSkillUsage` (C3);
  - `CredentialDeletionImpact.skill_pbp_usages: list[CredentialSkillUsage] = []` and
    `active_skill_install_count: int = 0`;
  - extend the tier docstring.
- `SkillCredentialRequirements.publisher_usages_of_credential(session, *, credential_id: uuid.UUID, publisher_user_id: uuid.UUID) -> tuple[list[CredentialSkillUsage], list[uuid.UUID]]`
  - Packages with `publisher_user_id == publisher_user_id` (one query).
  - Their revisions (one query).
  - Keep specs where parsed `provided_by == "publisher"` and `publisher_credential_id == credential_id`.
  - Group by package. Returns usages plus the matching revision ids.
- `CredentialsService.get_deletion_impact` (:1845):
  - call the method above with `requester_id`;
  - `active_skill_install_count` = count of **distinct** `Agent.id` over `AgentCredentialLink`
    (credential) join `Agent` (`owner_id != requester_id`), with EXISTS on an `AgentPluginLink`
    (`agent_id == Agent.id`, `source == catalog`, `skill_package_revision_id IN revision_ids`);
  - `tier = 2` if (bundle condition) **or** (`skill_pbp_usages and active_skill_install_count > 0`);
  - populate the new fields.

  The 409-unless-force delete path reads `tier` and needs no other change. Disable-sharing reads the
  same impact endpoint in the UI (Phase 3).

### 8.9 Tests (Phase 2), API-only, in `backend/tests/api/agents/skill_credentials/`
Add helpers to `backend/tests/utils/skill_catalog.py`:
- `get_skill_install_preview(client, headers, agent_id, package_uuid, revision_number=None, expected_status=200)`
- `write_skill_with_credentials(env_id, name, credentials: list[dict])`, which renders the C1 block
  via `write_skill(frontmatter=…)`.

**`agents_skill_credentials_install_test.py`**:
1. **Publisher-provided, end to end (the brief's §6 story on `api_token`).**
   - Publisher A publishes a public skill whose slot credential is owned and shareable.
   - Consumer B's preview → `linked_publisher`.
   - Install → `credential_provisioning[0].outcome == "linked_publisher"`.
   - B's `GET /agents/{id}/credentials` includes the credential. B's shared-credentials list shows it
     with `category == "automatic"`.
   - The captured `credentials_json` for B's env has an entry with `service_uri == slot`.
   - The Addons row status is `ok`.
   - Uninstall, then reinstall: still one share, one link.
2. **Installer is the publisher.** Install into another of A's agents → `linked_publisher`, no share row.
3. **User-provided slot match.** B owns a credential with the slot → `linked_existing`. C has a direct
   share of a slot credential → `linked_existing`.
4. **User-provided, no match.**
   - Result is `placeholder_created` (`name == slot`, `service_uri == slot`, `is_placeholder`).
   - Addons row: `status == "warning"`, `status_code == "credential_missing"`,
     `credential_issues == [{slot, type, reason: "not_configured"}]`.
   - **`GET /agents/{id}/setup-status` → `ready` (D1).**
   - Install into B's second agent → `linked_existing` with the **same** credential id (I9).
   - Fill the placeholder (`PUT /credentials/{id}`) → the row becomes `ok`.
5. **Template.** The publisher enables template sharing → `template_materialised`. The placeholder
   carries the non-private fields.
6. **Publisher unavailable at install.** The publisher disables sharing after publish → preview and
   install `publisher_unavailable`, a placeholder is created, the row shows a warning.
7. **Access revoked after install.** The publisher disables sharing → B's row reason
   `access_revoked`; `setup-status` still `ready` (D1).
8. **Upgrade adds a slot.**
   - Republish with a second declaration.
   - `POST …/plugins/{link_id}/upgrade` provisions only the new slot.
   - A slot B unlinked earlier is not re-linked.
9. **Uninstall release.**
   - Uninstalling a skill removes its placeholder link and deletes the orphan placeholder, but keeps
     a real linked credential.
   - With two installed skills sharing a slot, uninstalling one keeps the placeholder.
10. **Guards.**
    - preview on another user's agent → 404;
    - preview of an invisible package → 404;
    - unknown `revision_number` → 404.

**`agents_skill_credentials_gate_test.py`**: a bundle publisher install that also carries a catalog
skill:
- a bundle-spec placeholder still yields `needs_setup` (I10);
- a skill-only placeholder does not.

**`backend/tests/api/credentials/test_credential_deletion_impact_skills.py`**:
- Publisher-provided in a published skill with ≥ 1 foreign install → `tier == 2`, `skill_pbp_usages`
  lists the package, `active_skill_install_count == 1`.
- `DELETE` → 409 with those fields; `force=true` → 200.
- The same credential with only the publisher's own install → tier 0/1.

### 8.10 Regression runs (must be green; no edits to existing bundle/credentials tests)
`tests/api/agents/skill_credentials/`, `tests/api/agents/bundles/`, `tests/api/agents/bundles_install/`,
`tests/api/agents/core/`, `tests/api/credentials/`, `tests/api/agents/agent_api/`, and
`tests/api/agents/sessions/` (the gate runs on the chat path).

### 8.11 Client regeneration
`make gen-client`. Confirm that `SkillsService` gains the install-preview method, and note its
generated name in the phase report for Phase 3.

### Definition of done (Phase 2)
_Met on 2026-09-10 (see §15). Rulings made during the phase: D15, D16._
- [x] `CredentialProvisioner` is the only writer of install-time shares and links. The bundle suites
      are green and untouched (I2).
- [x] Skill install, upgrade and uninstall provision, sync and release per §8.4. Installs never fail
      per slot (I8). Idempotent (I9).
- [x] `install-preview` endpoint live. `PluginSyncResponse.credential_provisioning` populated on
      skill install.
- [x] Addons `credential_missing` + `credential_issues`. The gate ignores skill-provisioned
      credentials (D1) and the bundle verdicts are unchanged (I10).
- [x] `skill_install` → Automatic. Deletion impact counts skill installs.
- [x] Client regenerated. `docs/**` untouched.

---

## 9. Phase 3 — Frontend

### Prerequisites
Phase 2 DoD met and the client regenerated. **The UI Specification (§9.3) must be written by
`cinna-core-ui-designer` in DESIGN mode before any component is built.** Build with
`cinna-core-ui-developer`, review with `cinna-core-ui-designer` (REVIEW) and
`cinna-core-code-reviewer`. If a surface needs data that the API does not return, **stop and
report**. Do not change the backend in this phase. **SKIP `docs/**`.**

### 9.1 Frontend surfaces inventory (intent, data, actions, API; composition is decided in §9.3)

| # | Surface (host, file) | User intent | Data shown | Actions | API | Guidelines §4 touched |
|---|---|---|---|---|---|---|
| S1 | **Share skill dialog**: provisioning summary. Host: Addons tab row menu → `frontend/src/components/Agents/Addons/ShareSkillDialog.tsx` (exists) | "Before I publish, show me what installers will get for each credential this skill needs, and why." | Per slot from `SkillPublishPreview.credentials`: slot, type, description, provided_by, the matched credential name (publisher's own), producer agent id, reason for `user` (`no_linked_credential` / `not_shareable` / `not_owned`) | read; follow to the matched credential (`/credential/{id}`) to change its sharing. Publish is unchanged. | `SkillsService.previewAgentSkillPublish` (existing, new field) | none listed. The dialog body is data-driven (§2 Dialog body). |
| S2 | **Add skill to agent dialog**: per-slot resolution for the chosen agent. Host: catalog grid card / package page → `frontend/src/components/Catalog/AddSkillToAgentDialog.tsx` (exists) | "If I add this skill to *this* agent, will it work right away, and what will I have to fill in?" | Per slot from the install preview: slot, type, description, provided_by, outcome (C4), credential name when known; after install, the `credential_provisioning` outcomes | read the preview (refetch when agent or revision changes); install (existing); after install, go to the agent's Credentials tab when any outcome needs setup | new `SkillsService.<install-preview>` (name from the Phase 2 report); `installAgentSkill` response `credential_provisioning` | none listed |
| S3 | **Add addon wizard, catalog skill modes step**. Host: Addons tab → `frontend/src/components/Agents/Addons/AddAddonDialog.tsx` + `AddAddonModesStep.tsx` (exist) | Same as S2, from the agent side | Same as S2 (agent is fixed) | same as S2 | same as S2 | §2 "The same entity, before and after": S2 and S3 must read the same |
| S4 | **Catalog "Requires"**. Hosts: grid card `frontend/src/components/Catalog/SkillCatalogCard.tsx`, package card `frontend/src/components/Catalog/SkillPackageCard.tsx` (exist) | "What does this skill need from me before I install it?" | `latest_revision.required_credentials` (package card: the pinned revision's): slot, type, provided_by, description | read | `SkillsService.listSkillCatalog` / `getSkillPackage` (existing, new field) | §2 Badge budget and Fact labels on the card; `SkillPackageCard` fact list |
| S5 | **Addons row credential status**. Hosts: `frontend/src/components/Agents/Addons/AddonRow.tsx`, `AddonDetailDialog.tsx`, `frontend/src/utils/addons.ts` (`LINK_STATUS_COPY`, `addonRowStatus`) (exist) | "Which of my skills can't work yet, and where do I fix it?" | row `status_code == "credential_missing"`; `credential_issues[]` (slot, type, reason) in the detail dialog | open the detail; go to `/agent/{agentId}#credentials` | `AgentsService` addons read (existing, new fields) | A13/A14 (badge budget, absent facts) on `AddonRow` |
| S6 | **Credential impact: "Used in skills"**. Hosts: disable-sharing dialog in `frontend/src/components/Credentials/CredentialSharing.tsx`, delete confirm in `frontend/src/components/Credentials/DeleteCredential.tsx` (exist), on `/credential/$credentialId` | "If I turn sharing off or delete this, whose installed skills break?" | `CredentialDeletionImpact.skill_pbp_usages[]` (package display name, package id, revisions), `active_skill_install_count`, next to the existing `bundle_pbp_usages` | read; open a package at `/catalog/skills/{package uuid}`; confirm disable/delete (existing, force on 409) | `CredentialsService.getCredentialDeletionImpact` (existing, new fields) | **A10 open on `CredentialSharing.tsx`** (hand-rolled bordered `li` rows in the PBP usage list). The spec must fix it or state why it is out of scope. |
| S7 | **Credentials page Automatic tab description**. Host: `frontend/src/routes/_layout/credentials.tsx:200` (exists) | "Why is this shared credential under Automatic?" | copy only | none | none | none |

**State management**:
- New query key `["skills-install-preview", agentId, packageId, revisionNumber ?? "latest"]`,
  enabled when an agent is chosen.
- After a successful install, invalidate the existing addons, agent-credentials and credentials-list
  keys. Grep the current keys in `useAddonRowMutations.ts`, `AgentCredentialsTab.tsx` and
  `routes/_layout/credentials.tsx`; do not invent new ones.
- The S1 preview uses the dialog's existing publish-preview query.
- No context providers, no localStorage.

### 9.2 Copy and status vocabulary with business meaning (the designer may shorten, not change the meaning)

- `provided_by`:
  - `publisher` → "Provided by the publisher"
  - `template` → "Publisher's template — you add the secret"
  - `user` → "You provide it"
- S1 reasons:
  - `no_linked_credential` → "No credential with this slot is linked to this agent, so installers bring their own."
  - `not_shareable` → "Sharing is off on ‹name›, so installers bring their own. Turn sharing on to provide it."
  - `not_owned` → "‹name› belongs to someone else. Only credentials you own can be provided to installers."
  - `template_would_leak_secret` → "‹name› would ship its secret inside the published skill. Mark its secret fields private to provide it as a template, or turn sharing on."
- S2/S3 outcomes:
  - `already_linked` → "Already linked on this agent"
  - `linked_publisher` → "The publisher's credential will be shared with you and linked"
  - `linked_existing` → "Your credential ‹name› will be linked"
  - `template_materialised` → "A credential will be created from the publisher's template — fill in the secret afterwards"
  - `placeholder_created` → "An empty credential ‹slot› will be created — fill it in on the agent's Credentials tab"
  - `publisher_unavailable` → "The publisher's credential is unavailable — an empty one will be created for you to fill in"
- S5:
  - dot label for `credential_missing` → "Needs a credential — open the agent's Credentials tab."
  - reasons: `not_linked` → "Nothing linked for ‹slot›"; `not_configured` → "‹slot› is linked but not filled in"; `access_revoked` → "The publisher stopped sharing ‹slot›"
  - status tone: **warning** (`--warning`), never error.
- S6: "Provided by the publisher in N published skill(s) with M active install(s). Disabling sharing / deleting it leaves those installs without it."
- S7: "Connections created by "Connect Agent API" or "Connect MCP Provider", and credentials shared with you by skills you installed. Manage name, notes, and sharing here."
- Accessibility: the slot is a user-typed id. Render it `font-mono` and `truncate` with the full
  value in a tooltip. An outcome that needs setup must not rely on colour alone.

### 9.3 UI Specification

_Produced by `cinna-core.ui.design` on 2026-09-10 against `ui_ux_guidelines.md` (§2 through "Rendered
documents", R1–R22) and the regenerated client. Composition decisions here override §9.1 and §9.2.
Data and API decisions stay with §8. Where this spec departs from a constraint in the brief, it says so
and why._

**Data gaps:** none blocking. Two things are deliberately **not rendered** because no payload carries
them: (1) "backed by agent X" (brief §4). `producer_agent_id` is a bare id, and no name travels with it
on any catalog or preview payload. (2) Skill usages on the Sharing card body, outside its dialogs. That
would need the deletion-impact read on every page view (today it runs only while a dialog is open).

#### Surfaces

| # | Surface | Host (file · where) | Story | Placement (§2 row) | Pattern · row shape | Budget | Verification |
|---|---|---|---|---|---|---|---|
| S0 | Shared slot row + copy module | `components/Catalog/SkillCredentialSlotRow.tsx`, `utils/skillCredentials.ts` (new) | — | Row anatomy, Row height, The same entity before and after | P3 plain row, no menu | 1 line + meta, ≤ 1 inline action, 0 badges | checklist |
| S1 | Share skill › Credentials block | `Agents/Addons/ShareSkillDialog.tsx` · after Visibility (+ people), before Advanced | View (inside a Create dialog) | Disclosure depth, Dialog body | S0 rows, no dot | +1 block; rows uncapped (≤ 20, the dialog scrolls); ≤ 1 inline action | checklist |
| S2 | Add skill to agent › Credentials block + setup panel | `Catalog/AddSkillToAgentDialog.tsx` · after "Enable for", before Advanced | View (preview); the panel is the Create result | Disclosure depth, Dialog body, §6 "state that still needs action" | S0 rows with dot; P6 success panel | 5 blocks total; 0 row actions; panel: 1 list + 2 footer buttons | checklist |
| S3 | Add addon step 2 › same block + same panel | `Agents/Addons/AddAddonModesStep.tsx` · after the modes block + its Alert, before Advanced; panel in `AddAddonDialog.tsx` | same as S2 | same as S2 | same components as S2 | 4 blocks in step 2 | checklist |
| S4a | Catalog tile requirement line | `Catalog/SkillCatalogCard.tsx` · after the package-id `code`, before "Used in N of my agents" | View | Card ≤ 7 blocks, Badge budget, Absent facts | fact line on a browse tile | +1 text line (7th element), 0 badges, 0 controls | checklist |
| S4b | Package card "Credentials" fact → Sheet | `Catalog/SkillPackageCard.tsx` · fact list after Content; new `Catalog/SkillRevisionCredentialsSheet.tsx` | View | Fact labels; A card under a document (a door costs no height) | fact-as-door (the Version and Content precedent) + P5 Sheet | +1 fact; Sheet rows ≤ 20, 0 actions | checklist |
| S5a | Addons row credential warning | `utils/addons.ts` `LINK_STATUS_COPY` → `AddonRow.tsx` | View | Row state, Row flags, Badge budget | P3 row, unchanged shape | +0 badges, +0 flags | checklist |
| S5b | Addon detail › credential issues | `Agents/Addons/AddonDetailDialog.tsx` · directly under the block-2 Alert | View | Dialog body, Links in a fact list | S0 rows with dot + plain link | ≤ 20 rows, 1 link | checklist |
| S6a | Disable-sharing confirm | `Credentials/CredentialSharing.tsx` · its `Dialog` | Confirm with fetched impact | Confirmation, Dialog body | Dialog + `ListRowGroup` (fixes A10) | 2 Alerts max, 1 list; rows: 1 inline action | checklist |
| S6b | Delete confirm | `Credentials/DeleteCredential.tsx` | Confirm with fetched impact | Confirmation, Dialog body | same rows as S6a | 1 Alert, ≤ 2 lists | checklist |
| S6c | Sharing card "Used in Bundles" list (A10 fix on touch) | `Credentials/CredentialSharing.tsx` · card body | View | Row anatomy | same `BundleUsageRow` | unchanged count | checklist |
| S7 | Automatic tab copy | `routes/_layout/credentials.tsx:195,200` | copy | — | — | — | checklist |
| S8 | Token-template field help (open item b) | `Credentials/CredentialFields/ApiTokenFields.tsx` · help line under "API Token Template" | copy | Absent facts (prompt on the control that supplies it) | — | 1 sentence | checklist |

**Screenshots: none, for any surface.** Every surface is a P3 row list, a P6 success panel reused from
`ShareSkillSuccessPanel`, a fact line, or copy, in a host that already exists. There is no new route or
tab, no expand/collapse, and no list of ≥ 10 visible rows (a skill declares 1–3 slots). The S4a line is a
fixed one-line `truncate`. None of the §9 triggers applies. The dev database is unlikely to hold a
published skill with credentials, and data is never staged.

No timestamps appear on any of these surfaces (R17 n/a).

#### S0 — Shared pieces (build first)

**Copy module `frontend/src/utils/skillCredentials.ts`**, the only place S1–S6 read words from. Every
table is a `Record` keyed by the **generated union**, so a new server value fails to compile (the
`FORMAT_LABEL` precedent in `utils/addons.ts`). Wire-string fallbacks use `||`.

Exports:
- **Types:**
  - `SlotProvidedBy = NonNullable<SkillCredentialRequirementPublic["provided_by"]>`
  - `SlotOutcome = SkillCredentialProvisionPublic["outcome"]`
  - `PublishReason = NonNullable<SkillPublishCredentialPreview["reason"]>`
  - `IssueReason = AddonCredentialIssuePublic["reason"]`
- **`credentialTypeLabel(type: string): string`**
  - The map **moves here** from the unexported `credentialTypeLabels` in `Credentials/columns.tsx`, and
    `columns.tsx` imports it back. One table, so "Agent REST API" cannot drift.
  - An unknown value prints the raw type.
- **`PROVIDED_BY_COPY: Record<SlotProvidedBy, { short; sentence }>`**
  - short: `publisher` "From the publisher" · `template` "Publisher's template" · `user` "You provide it"
  - sentence: §9.2 verbatim.
- **`publishReasonSentence(reason, credentialName)`**: §9.2 S1 reasons verbatim, with ‹name› replaced by
  `credentialName || "the credential"`.
- **`publishOpenLabel(reason | null, name)`**: tooltip and `aria-label` of S1's open control:
  - `not_shareable` → "Open ‹name› to turn sharing on (new tab)"
  - `template_would_leak_secret` → "Open ‹name› to mark its secret fields private (new tab)"
  - otherwise "Open ‹name› (new tab)"
- **`SLOT_OUTCOME_COPY: Record<SlotOutcome, { needsSetup; short(p); preview(p); installed(p) }>`**, where
  `p = { slot, credentialName }`.
  - `needsSetup` is true for `template_materialised`, `placeholder_created` and `publisher_unavailable`.
  - `preview` is §9.2 verbatim.
  - `installed` is the past tense: "…was shared with you and linked", "Your credential ‹name› was linked",
    "An empty credential ‹slot› was created — fill it in on the agent's Credentials tab", …
  - `short` works in either tense:

    | Outcome | short |
    |---|---|
    | `already_linked` | "Already linked" |
    | `linked_publisher` | "Shared by the publisher" |
    | `linked_existing` | "Uses your ‹name›" |
    | `template_materialised` | "From template — needs the secret" |
    | `placeholder_created` | "Empty — needs filling in" |
    | `publisher_unavailable` | "Publisher's unavailable — needs filling in" |
- **`slotOutcomeStatus(item, phase: "preview" | "installed"): RowStatus`**
  - tone `on` when `!needsSetup`, else `warning`
  - label = the phase sentence
- **`slotOutcomeSummary(items, phase)`**:
  - no slot needs setup → "Ready to use on this agent."
  - preview → "N need(s) filling in after install."
  - installed → "N credential(s) need filling in before the skill can use them."
- **`CREDENTIAL_MISSING_LABEL`** = "Needs a credential — open the agent's Credentials tab." (§9.2 S5).
- **`ISSUE_REASON_COPY: Record<IssueReason, { short; sentence(slot) }>`**:

  | Reason | short | sentence |
  |---|---|---|
  | `not_linked` | "Nothing linked" | §9.2 verbatim |
  | `not_configured` | "Not filled in" | §9.2 verbatim |
  | `access_revoked` | "Publisher stopped sharing" | §9.2 verbatim |
- **`requirementsSummary(reqs | null | undefined): string | null`**
  - `null` when empty.
  - `template` counts as *from you*, since you add the secret.
  - Three shapes:
    - none from you: "N credential(s), provided by the publisher"
    - all from you: "N credential(s), you provide it/them"
    - mixed: "N credentials, M from you"
- **`skillImpactSentence(skills, installs, action: "disable" | "delete")`**: §9.2 S6 with real plurals
  (no "(s)").
  - The "with M active install(s)" clause is omitted when `installs === 0`.
  - The tail is "Disabling sharing leaves those installs without it." or "Deleting it leaves those
    installs without it."

**Row `SkillCredentialSlotRow`** (`components/Catalog/`; Addons already imports from Catalog). Props:
`slot`, `type`, `description?`, `status?: RowStatus`, `summary: string`, `facts?`, `action?`. It renders
`ListRow`:
- `title`: the slot in `font-mono`, truncated, with the full value in a `Tooltip` on a **non-focusable**
  `span`. That keeps it off the first-focusable path (R18). The composed-title skeleton is by reference
  to `SkillRevisionFilesSheet.tsx`'s path row.
- `meta`: `` `${credentialTypeLabel(type)} · ${summary}` `` (two facts).
- `flags`: `<RowInfo facts={[description || null, ...facts]} />`.
- children: `action`.
- **Row height:** the meta line earns its place because it *is* each surface's answer (what installers
  get, whether it will work, what is wrong). Needs-setup is written in words there, so it does not rely on
  colour alone (§9.2 accessibility).
- Always inside a `ListRowGroup`. There is no inner scroll container, so R21's `pr-2` is n/a (the dialog
  or Sheet scrolls).

#### S1 — Share skill dialog: "what installers get"
- **Intent:** before publishing, the publisher sees per slot what installers will receive, and why.
- **Absent:** `skill.credentials` (the index declarations, available at mount) is empty → render nothing.
- **Layout:** `Label` "Credentials" → `ListRowGroup` of S0 rows → `p.text-xs.text-muted-foreground`:
  "Installers receive a credential only if you own it and its sharing is on; otherwise they bring their
  own." This carries the brief's publisher ≠ owner risk.
- **Row:**
  - no dot (not a health state);
  - `summary` = `PROVIDED_BY_COPY[pb].short`;
  - `facts` = [`credential_name && "Matched ‹name›"`, `reason && publishReasonSentence(...)`].
  - Action, only when `credential_id` is set: a ghost `h-7 w-7` icon button with `ExternalLink h-3.5`
    wrapping `Link to="/credential/$credentialId" target="_blank" rel="noopener noreferrer"`.
    `Tooltip` and `aria-label` come from `publishOpenLabel`. It opens a **new tab** so the drafted release
    notes stay put. `ExternalLink` is right here: it is a bare button whose label does not say it leaves.
- **Fix loop:** the publish-preview query must refetch on window focus (the app default; do not turn it
  off). Returning from the credential tab then re-resolves the rows.
- **States:**
  - loading: one `Skeleton h-[44px]` per declaration;
  - error: the section hides, because the dialog-level `previewError` alert is the **same query** and
    already names it (Share stays enabled, as today);
  - pending: n/a (read-only).
- **Host fix:** `DialogContent` gains `overflow-x-hidden` (it already has `max-h-[85vh] overflow-y-auto …
  [&>*]:min-w-0`).

#### S2 / S3 — Install resolution (identical by construction)
- **Intent:** "If I add this skill to *this* agent, will it work right away, and what will I fill in?"
- **One component for both:** `components/Catalog/SkillInstallCredentialsSection.tsx`. Props: `agentId`,
  `packageId`, `revisionNumber: number | null`. It owns the query, the states and the copy. S2 and S3
  only place it, so they cannot drift.
- **Query:**
  - key `["skills-install-preview", agentId, packageId, revisionNumber ?? "latest"]`;
  - `SkillsService.previewAgentSkillInstall`;
  - `enabled: !!agentId`;
  - `placeholderData: keepPreviousData`, so a revision change does not collapse the block.
  - The requirement count comes from the host's cached `["skills-catalog","package",packageId]` read (the
    chosen revision's `required_credentials`).
- **Absent:** no agent chosen, the revision requires nothing, or `credentials: []` → render nothing (no
  skeleton flash). In S3 the component renders only when `selected.source === "catalog"`.
- **Layout:** `Label` "Credentials" → `ListRowGroup` → `p.text-xs.text-muted-foreground` with
  `slotOutcomeSummary(items, "preview")`.
- **Row:**
  - `status` = `slotOutcomeStatus(item, "preview")`;
  - `summary` = `SLOT_OUTCOME_COPY[o].short(p)`;
  - `facts` = [`PROVIDED_BY_COPY[pb].sentence`];
  - **0 actions**: nothing leaves a Create form before its submit.
- **States:**
  - first load: `Skeleton h-[44px]` × requirement count;
  - error: `QueryErrorAlert compact` "Couldn't check this agent's credentials" + Retry. The install button
    **stays enabled**, because the preview is advisory (§11).
  - pending: the existing `LoadingButton` ("Add to agent" / "Install").
- **Setup panel `components/Catalog/SkillInstallSetupPanel.tsx`** (P6 success panel, skeleton by
  reference to `Agents/Addons/ShareSkillSuccessPanel.tsx`):
  - **When shown:** only when the install response's `credential_provisioning` has ≥ 1 `needsSetup`
    outcome. Otherwise nothing changes (S2 toast + close; S3 `settleSync`).
  - **Placement:** it replaces the dialog's header, body and footer in place, the way Share's
    `published` swap does.
  - **Title:** "‹skill› installed". Description: `slotOutcomeSummary(items, "installed")`.
  - **Body:** every provisioning row (ready ones too, so the list matches the preview just read), with
    `phase: "installed"`.
  - **Footer:**
    - outline "Done";
    - primary `Button asChild` → `Link to="/agent/$agentId" hash="credentials"` "Open the Credentials
      tab", which also closes the dialog.
  - **Focus:** moves to that link on swap, since the submit button that held focus unmounts (R21).
  - **Other rules:**
    - S2 shows no toast when the panel shows.
    - In S3 a partial sync still reaches `onSyncResult`, but **after** the panel closes (Done, link or
      Escape). That is chained, not nested (§2 Disclosure depth).
    - Invalidation runs on success, before the swap.
- **Host fixes:**
  - S2 `DialogContent` gains `overflow-x-hidden [&>*]:min-w-0`.
  - S3 `DialogContent` becomes `max-h-[85vh] overflow-y-auto overflow-x-hidden sm:max-w-2xl [&>*]:min-w-0`
    (R18). Step 1's own `max-h-[45vh] pr-2` list is unaffected.
- **Order in both:** modes → Credentials → Advanced → install error.

#### S4a — Catalog tile
- One non-interactive `p.flex.items-center.gap-1.text-xs.text-muted-foreground`: `KeyRound h-3 w-3
  shrink-0` + `span.truncate` with `requirementsSummary(entry.latest_revision?.required_credentials)`.
  `null` → no line.
- **No tooltip:** the whole tile is `role="button"`, and a focusable trigger inside it would be a nested
  control.
- The tile becomes 7 elements (≤ 7). The file docstring's "Six elements" is updated to seven.
  `auto-rows-fr` equalises the row height, which is accepted: one `text-xs` line.
- **Siblings:** `CatalogCard` tiles are unaffected. The line reuses the "Used in" line's type scale.

#### S4b — Package card fact + Sheet
- **Fact:** label "Credentials", after "Content", shown while a revision is shown. Its data is
  `shownRevision.required_credentials`, i.e. the pinned revision, not the latest.
  - Non-empty: the value is a door `button`, skeleton by reference to the Version and Content buttons in
    the same file. It holds `requirementsSummary(...)` + `KeyRound h-3.5 w-3.5` and opens the Sheet.
  - Empty: plain value "None declared". A fact list is the one place an absence is written (§2 Absent
    facts).
- **Sheet `SkillRevisionCredentialsSheet`**, skeleton by reference to `SkillRevisionFilesSheet.tsx`
  (`side="right" w-full sm:max-w-lg`, `flex-1 overflow-y-auto px-4 pb-4`):
  - title "Credentials";
  - description "What installing ‹revision label› needs. The publisher's credentials are shared with you
    on install; you fill in the rest on the agent.";
  - rows: no dot, `summary` = `PROVIDED_BY_COPY[pb].short`, `facts` = [`PROVIDED_BY_COPY[pb].sentence`];
    0 actions, no cap.
- **A13/A14 on this card, fixed here** (§9.1 names Fact labels on this fact list):
  - "Catalog installs" value `String(n)` → "N people";
  - "Used in my agents" → label "My agents", value "N agents";
  - the reconciling paragraph ("Catalog installs counts other people…") is **removed**. The units carry
    it (§2 Fact labels: "a pair of numbers that need a sentence to reconcile them usually needs units").

#### S5a — Addons row
- `LINK_STATUS_COPY.credential_missing = CREDENTIAL_MISSING_LABEL`. The tone already comes from
  `status="warning"`. Nothing else changes on the row.
- **No `RowFlag`:** the row's one warning-toned flag slot is the update-available `ArrowUpCircle`, and a
  second amber glyph beside it would make "update" and "broken" look alike. The dot's tooltip and
  `sr-only` label carry the words, as every row state does.
- No badge (A13/A14). Disabled rows keep dimming under the warning (existing `muted`).

#### S5b — Addon detail dialog
- **When shown:** `status_code === "credential_missing"` and `credential_issues.length > 0`. It sits
  directly under the existing block-2 Alert, which keeps its label.
  - A `ListRowGroup` of S0 rows:
    - `status { tone: "warning", label: ISSUE_REASON_COPY[r].sentence(slot) }`;
    - `summary` = `ISSUE_REASON_COPY[r].short`;
    - no facts (no description on the wire).
  - Then `Button asChild variant="link" className="h-auto px-0"` → `Link to="/agent/$agentId"
    hash="credentials"` "Open the agent's Credentials tab". No glyph; the shape of the dialog's existing
    catalog link. `onClick` closes the dialog, so the close does not depend on the tab unmounting.
- **Departure from the brief ("lists `credential_issues` as facts"):** rows, not `Fact` lines. `Fact`'s
  label is `shrink-0`, and a slot is a user-typed id of up to 255 characters. As a label it pushes the
  value out; as a value it truncates the reason. The same slot already reads as this row in S1–S4 (§2
  The same entity, before and after).
- The dialog already has `max-h`, `overflow-x-hidden`, `[&>*]:min-w-0` and `onOpenAutoFocus`, so R18 is
  met as is.

#### S6 — Credential impact
- **Rows `components/Credentials/CredentialUsageRows.tsx`**, replacing every hand-rolled bordered `li`
  in `CredentialSharing.tsx` and `DeleteCredential.tsx` (A10, R16):
  - **`BundleUsageRow`** (moved out of `DeleteCredential.tsx`):
    - `ListRow icon` = `h-6 w-6 rounded-md bg-muted` tile with `Box h-3.5 w-3.5`;
    - title `display_name`;
    - meta `bundle_id` in `font-mono`, plus `` ` · ${providedByLabel}` `` when `showProvidedBy`;
    - when `publisher_install_id` is set: a ghost `h-7 w-7` `ExternalLink` icon button → `/agent/$agentId`
      hash `bundle`, **new tab**, tooltip "Open ‹name› in a new tab".
  - **`SkillUsageRow`:**
    - `GraduationCap` tile;
    - title `display_name`;
    - meta `package_id` in `font-mono`;
    - `RowInfo` ["Provided in revision(s) 1, 3"];
    - the same `ExternalLink` button → `/catalog/skills/$packageId` (`package_uuid`), new tab.
  - No dot, no menu. New tab, so a confirm is never left by navigating.
- **S6a disable-sharing `Dialog`:**
  - `DialogContent className="max-h-[85vh] overflow-y-auto overflow-x-hidden sm:max-w-md [&>*]:min-w-0"`.
  - Title names the entity: "Disable sharing for ‹name›?".
  - The share-count Alert stays.
  - Impact states:
    - loading: 2 × `Skeleton h-[44px]`, and the confirm is **disabled** so nobody confirms blind;
    - error: `QueryErrorAlert compact` "Couldn't check which bundles and skills use it" + Retry, with the
      confirm **enabled**. Revoking access must not be blocked by a failed read.
  - Loaded, with any bundle or skill usage:
    - **one** destructive Alert "Published installs lose this credential", whose description is the
      existing bundle sentence (only when `bundle_pbp_usages` is non-empty) followed by
      `skillImpactSentence(..., "disable")` (only when `skill_pbp_usages` is non-empty);
    - then **one** `ListRowGroup`: bundle rows, then skill rows.
  - Confirm: `LoadingButton` "Disable sharing". Escape and outside-click are blocked while pending.
- **S6b delete `Dialog`:**
  - Same `DialogContent` classes.
  - Loading: `Skeleton` lines replace the `Loader2` "Checking impact…" (§5: `Loader2` only on rows or in
    a `LoadingButton`).
  - Error (new): `QueryErrorAlert compact` + Retry. The non-forced Delete stays enabled; a tier-2
    credential comes back 409 and the existing handler renders its impact.
  - The tier-2 Alert composes per source:
    - the bundle sentence only when `bundle_pbp_usages` is non-empty. Today it prints unconditionally, so
      a credential at tier 2 because of skills reads "bundles with 0 active installs";
    - `skillImpactSentence(..., "delete")` only when `skill_pbp_usages` is non-empty.
  - Lists, in all tiers: "Used in bundles" (`BundleUsageRow showProvidedBy`) and, new, "Used in skills"
    (`SkillUsageRow`), each an `h4.text-sm.font-medium` + `ListRowGroup`.
  - The 409 toast becomes "…in use by a published bundle or skill. Review the impact below."
- **S6c:** the Sharing card body's "Used in Bundles" list uses `BundleUsageRow` (A10, same file).
- **Deferred, with reason:** `CredentialSharing.tsx`'s hand-rolled switch (`input.sr-only` + two
  `div`s, `bg-emerald-500`: R11, R14a) and its non-skeleton header (R15). Its grid sibling
  `CredentialTemplateSharing.tsx` carries the identical header. Fixing one card creates an R15 sibling
  mismatch, and fixing both touches a file outside S1–S7. Both are fixed together on the next touch of
  either card, and A10 stays open for them.

#### S7 — Automatic tab
- `:200` → §9.2 S7 verbatim.
- `:195` → "…the Bundle, Automatic and My Credentials tabs may be incomplete." D6 makes Automatic depend
  on the shared read too.

#### Open item a — api_token private-field picker: **out of Phase 3; needs a backend change**
- **Where the picker is:** `Credentials/CredentialTemplateSharing.tsx` (`FIELDS_BY_TYPE.api_token`,
  `togglePrivateField`).
- **Why a frontend fix is the wrong one:** a frontend-only fix *is* possible, because `update_credential`
  accepts any string list (`credentials_service.py:1790–1796`). But `template_private_fields` is copied
  verbatim into bundle revision specs and rendered by `Install/InstallServiceCredentialItem.tsx`
  (:76–94 counts it, :318–320 maps each name into the installer's private-field list). A hidden
  `http_header_value` key would inflate "fill in N private fields" and print a raw field name for every
  **bundle** installer.
- **Where the fix belongs:** `http_header_value` is computed from `api_token` at sync time and never
  stored. The D12 check should treat a computed sensitive field as stripped when its stored source
  (`api_token`) is private. That is a Phase 2 backend follow-up.
- **Interim:** S1's `template_would_leak_secret` sentence tells an `api_token` publisher to do something
  the UI cannot achieve (see the open question below).

#### Open item b — literal token in `api_token_template`: **in scope, as S8 (copy only)**
- **Where:** the warning belongs on the control where the token is typed. Append to the existing help
  line in `ApiTokenFields.tsx` (custom type only): "Never type the token itself here — use {TOKEN}. This
  field is not secret: template sharing copies it as written."
- **Not in S1:** the preview carries nothing that tells a custom template from a bearer one. A caution
  there would print on every template row, the repeated-least-informative failure of §2 Absent facts.

#### Frontend phase order (one phase, in this order)
1. **S0:** `utils/skillCredentials.ts` (+ the `credentialTypeLabel` move) and `SkillCredentialSlotRow`.
2. **S5a/S5b:** smallest; they prove the copy module.
3. **S1:** `previewAgentSkillPublish` `.credentials`.
4. **S2/S3:** `previewAgentSkillInstall`, `installAgentSkill` `.credential_provisioning`.
5. **S4a/S4b:** `listSkillCatalog` / `getSkillPackage` `.required_credentials`.
6. **S6:** `getCredentialDeletionImpact` `.skill_pbp_usages`, `.active_skill_install_count`.
7. **S7, S8:** copy.

#### Open questions (coordinator)
1. **Item a** needs a backend follow-up (the D12 computed-field mapping). Until it lands, should S1's
   `template_would_leak_secret` sentence for an `api_token` slot drop "mark its secret fields private"
   and say only "turn sharing on"? The meaning changes, so the designer cannot make that change alone.
   Ruled by coordinator 2026-09-10: type-aware copy (api_token drops the private-fields clause) until the backend D12 computed-field mapping lands.

#### Lessons for the guideline (decided here without a rule)
- **Read-only rows inside a Create form dialog:** P3 rows with no menu and no inner cap for ≤ 20
  (the dialog scrolls). §2 covers cards and selection checklists only.
- **Create dialogs that close on success:** §6 "a state that still needs action stays" has no dialog
  shape. Here that shape is a P6 success panel shown only when setup is needed.
- **Open-to-fix links from inside a form or confirm dialog go to a new tab.** Today that rule lives only
  in "Wizard step header".
- **`Fact`'s `shrink-0` label cannot hold a user-typed id:** such ids are rows.

#### Build amendments (review round 2)
_`cinna-core.ui.review` PASS on 2026-09-10 (S0–S8, checklist, no screenshots). These build deviations are
accepted and supersede the spec text above where they differ._
- **S2/S3 preview placeholder is agent-scoped**, not plain `keepPreviousData`: previous rows are kept
  across a revision change only while the agent is unchanged, so one agent's "Uses your …" never shows
  under another.
- **`hooks/useAgentTabLinkClick`**: `HashTabs` follows only `hashchange`, so a router `Link hash=` to the
  agent page already on screen would not switch tabs. S5b and the setup panel use the hook. Follow-up:
  make `HashTabs` follow the router's hash and delete the hook.
- **S1 block lives in `Agents/Addons/ShareSkillCredentialsSection.tsx`** (host was 561 lines).
- **S1 speaks in the publisher's voice**: `PROVIDED_BY_PUBLISHER_COPY` ("Shared with installers" /
  "Shared as a template" / "Installers provide it"). `PROVIDED_BY_COPY` stays for installer-facing
  surfaces. Row controls in S1 and S6 use the shared `Common/NewTabIconLink`.
- **api_token copy (Phase 3 manager ruling, D17)**: `template_would_leak_secret` and its open label drop the
  "mark its secret fields private" clause for `api_token` until the backend D12 computed-field mapping
  lands.
- **S6a/S6b**: the S6b title names the entity; Escape and outside-click are blocked while pending.
  Impact sentences and the S6a rows appear only for a source with active installs; the 409 body seeds
  the impact cache; the tier 0/1 button is "Delete credential".
- **S6c**: "Used in Bundles" is a `PreviewList` (cap 5, loading, error with Retry, hidden when loaded
  and empty), with Show all opening `Credentials/CredentialUsagesSheet.tsx` (generalised
  2026-09-11 from `CredentialBundleUsagesSheet.tsx` when the skills list gained the same door).
- **S5b is gated on `credential_issues.length > 0`**, not on `status_code`, because a link failure
  (`not_materialized`, `unverified`) outranks `credential_missing` while the slots are still unusable.
- **Partial sync on the setup panel's link path (Add addon wizard)**: the panel has a separate
  `onOpenCredentials`. Following the link unmounts the Addons tab that owns the sync-issues dialog, so
  a partial sync becomes an error toast ("‹name› installed, but it didn't reach every environment —
  check the Addons tab"). Done and Escape still chain the sync-issues dialog.
- **Copy**: fallbacks use `||` with a capitalised "The credential" at sentence start; real plurals.
  The setup panel title carries `KeyRound`. The S2/S3 preview error is hidden when the package is
  known to declare no credentials.

### 9.4 Build notes
- Types only from `@/client` (regenerated). Wire-string fallbacks use `||` (§2 Wire strings).
- Typecheck touched files only:
  `cd frontend && npx tsc --noEmit 2>&1 | grep -E "(ShareSkillDialog|AddSkillToAgentDialog|AddAddonDialog|AddAddonModesStep|SkillCatalogCard|SkillPackageCard|AddonRow|AddonDetailDialog|addons|CredentialSharing|DeleteCredential|credentials)" | head -40`.
- Put the shared outcome, provided_by and reason copy in **one** module (e.g.
  `frontend/src/utils/skillCredentials.ts`) so S1–S5 cannot drift.

### Definition of done (Phase 3)
_Met on 2026-09-10 (see §15). Ruling made during the phase: D17._
- [x] UI Specification appended (§9.3), then built. `cinna-core.ui.review` PASS on S1–S6.
- [x] Code review clean. No new `tsc` errors in touched files.
- [x] No backend or `docs/**` changes (the only docs write is §9.3 of this plan).

---

## 10. Phase 4 — Whole-feature seam review + docs sweep

### Prerequisites
Phases 1–3 DoD met (they are, see §15). **Read §15 first.** Its open items join the §10.1 checklist.
Its copy changes, new API surface and guideline lessons join the §10.2 docs table.

### 10.1 Seam review (one review across all three phases; blocking bugs historically sit at seams)
Run `cinna-core-code-reviewer` (opus) over the combined diff with this checklist. Each item needs a
file:line answer.

| Seam | Question |
|---|---|
| S-1 declaration → derivation | Does `resolve_for_publish` read only `SkillEntry.credentials` (normalised C1)? Are invalid declarations refused before any write? |
| S-2 derivation → revision JSON | Do skill specs follow C2 exactly (`name == service_uri == slot`)? Is `producer_agent_id` only on `agent_api`? Are bundle specs byte-identical (I1)? |
| S-3 revision JSON → readers | Do the provisioner, `SkillSlotIndex`, `specs_to_public` and `publisher_usages_of_credential` all go through `parse_credential_spec`, and derive the slot the same way (`service_uri or name`)? |
| S-4 provisioner writes → matchers | Is a placeholder created with `service_uri=slot` found by `find_slot_match` on the next install (I9)? Does `SkillSlotIndex` satisfaction agree with provisioner outcomes for the same state? Does `release_skill_slots` target exactly what the provisioner created? |
| S-5 preview ↔ install | Does `preview` share the decision tree with `provision`? Construct one state and compare. |
| S-6 credential rows → container | Do `service_uri` / `is_placeholder` at top level reach `credentials.json`, match `by_slot` / `require_slot` semantics, and keep the synthetic entries untouched (I4)? |
| S-7 gate ↔ bundles | On a publisher install carrying a catalog skill, is the bundle gate verdict unchanged (I10)? Is the D1 exclusion zero-cost on the ready path? |
| S-8 classifier + impact → UI | Does `skill_install` → Automatic appear in the list and on the tab copy? Are `skill_pbp_usages` rendered in both disable-sharing and delete dialogs? |
| S-9 old containers / old caches | Is a pre-feature cache row (no `credentials`) tolerated? Is `credential_missing` computed from host-side specs, independent of container version? |
| S-10 transactions | Are install link + provisioning one commit (I8)? Upgrade re-pin + provisioning one commit? Uninstall release + delete one commit? Is credential sync called only after commit? |

Then run the target scenario manually in a dev stack (brief §6), with rebuilt environments:
1. Producer `erp-public-api` has agent-api enabled with identity.
2. Connect it from the skill-building agent, stamp `service_uri=erp-public-api` on the connection
   credential, enable sharing.
3. Publish a public `erp-public-data` skill with the declaration.
4. A second user installs it into their agent. The script calls
   `credentials.agent_api_session("erp-public-api")`. The producer sees `X-Cinna-Caller-*` for the
   second user.
5. The producer owner disables sharing: the consumer row turns amber (`access_revoked`), the script
   raises `credential_missing` with the fix text, and the delete of the connection is Tier 2.

Full suite: `make test-backend` (use `ps` in the container before dispatching, per the known
docker-exec caveat).

### 10.2 Docs sweep
First run `python3 .cinna-core-kit/scripts/docs_index.py impact` on the feature diff and reconcile its
output with this list. Update the business file first, then the tech file.

| Doc | What changes |
|---|---|
| `docs/agents/agent_skills/agent_skills.md` + `agent_skills_tech.md` | `credentials:` declaration and rules; `invalid_credentials` in the issue vocabulary; publish derivation (D4) and preview; install provisioning (outcomes, idempotency, D3); upgrade adds slots; uninstall releases placeholders (D5); trust boundary; parser divergence update (D10); `required_credential_specs` column; new schemas and install-preview route |
| `docs/agents/agent_addons/agent_addons.md` + `agent_addons_tech.md` | `credential_missing` warning and its place in status precedence; `credential_issues` reasons |
| `docs/agents/agent_credentials/credential_sharing.md` + `credential_sharing_tech.md` | `CredentialShare.source="skill_install"`; categorization rule 4b (D6); deletion-impact Tier 2 by skills; `service_uri` slot section extended to skills; install-time auto-link by slot (D3) |
| `docs/agents/agent_credentials/agent_credentials.md` + `agent_credentials_tech.md` | `credentials.json` entry shape (top-level `service_uri`, `is_placeholder`, D11); README "Slots" section |
| `docs/agents/agent_credentials/credentials_whitelist.md` + `credentials_whitelist_tech.md` | why `service_uri` / `is_placeholder` bypass the whitelist (I4) |
| `docs/agents/agent_bundles/agent_bundles.md` + `agent_bundles_tech.md` | `CredentialProvisioner` extraction (bundle policy), `build_spec` single writer; readiness gate D1 exclusion |
| `docs/agents/agent_api/agent_api.md` + `agent_api_tech.md` | SDK `by_slot` / `require_slot` / `agent_api_session`; distributing a producer through a public skill (brief §6) and its revocation model |
| `docs/agents/agent_plugins/agent_plugins.md` (+ tech) | catalog install/upgrade/uninstall now provision/release credentials; `PluginSyncResponse.credential_provisioning` |
| `docs/agents/agent_environment_core/agent_environment_core.md` (+ tech) | `BUILDING_AGENT.md` skill-credential guidance; SDK helpers need an env rebuild |
| `docs/flows/credential_materialization.md` | a new path: skill publish → install share/link/placeholder → `credentials.json` slot → SDK |
| `docs/development/frontend/ui_ux_guidelines.md` | only if the Phase 3 review logged a lesson or closed/opened an A-row |

Frontmatter: add `affects` edges where a doc now depends on another (e.g. `agent_skills` →
`credential_sharing`, `agent_bundles`). If any frontmatter changed, run `make docs-registry`. Then
run `make check-docs` (green).

### Definition of done (Phase 4)
- [x] Seam checklist answered (§15). One blocking finding (D17) fixed, with a unit guard and an API
      regression case.
- [x] The manual scenario ran end to end on the local dev stack on 2026-09-11 (two users, three fresh
      environments carrying the new SDK). Results, the D15 verdict and two findings that need a
      decision: §15 "Manual scenario run".
- [x] Full backend suite green: **4616 passed, 10 skipped, 0 failed** (26 min) — the first full-suite
      run of this feature. Re-run after the D17 fix over `tests/unit` + `skill_credentials` +
      `credentials` + `bundles` + `bundles_install`: 2343 passed, 10 skipped.
- [x] Docs updated per the table. `make check-docs` green. `sync_platform_knowledge.py` re-run.

---

## 11. Error handling and edge cases

| Case | Behaviour |
|---|---|
| Declared slot type unknown to the backend (a container newer than the backend) | Host parse at publish refuses (`skill_invalid`). The provisioner skips unknown types (logged). |
| Publisher deleted (`SkillPackage.publisher_user_id` SET NULL) | `PublisherBoundary(None)` → every publisher spec fails the owner check → `publisher_unavailable` (placeholder). |
| Publisher credential deleted | `AgentCredentialLink` cascades. New installs → `publisher_unavailable`. Existing installs → row `not_linked`. Deletion was gated at Tier 2. |
| Sharing disabled after publish | Shares deleted (existing behaviour). Rows `access_revoked`. New installs `publisher_unavailable`. Re-enabling does not re-share existing installs automatically. Reinstall or upgrade to a revision adding the slot does. Documented (drift detection is out of scope). |
| Template payload undecryptable at publish | Publish refused `credential_template_unreadable` (409) before any write. |
| Two skills declare the same slot | Both resolve to the same credential (desired). Uninstalling one keeps it (retained set). |
| User manually unlinks a skill credential | The row shows `not_linked`. Upgrade does not re-link existing slots, only added ones. Reinstall does. |
| User fills the placeholder | `is_placeholder` flips on save (existing update path). The row becomes `ok` on next read. Credential sync runs through the normal credential update path. |
| Environment suspended at install | Credential sync targets running envs only. The plugin sync wakes the env, and activation prepares credentials. |
| Pre-feature container | No index `credentials`, no SDK helpers. The addons status still works (host-side specs). Rebuild to get the helpers. |
| Bundle carrying a catalog skill | The bundle publisher's `_collect_credential_specs` already snapshots the linked slot credential as an ordinary bundle spec (brief). The consumer receives it through bundle install. No special case. |
| Install preview vs install race | Preview is advisory. The install report is authoritative and returned in the response. |
| Non-owner calls install-preview | 404 (`verify_agent_access`). |

---

## 12. Integration points

- **Bundles**: shared `build_spec`, shared `CredentialProvisioner` (I1, I2).
- **Credentials**: `find_slot_match`, classifier, deletion impact, env payload, README render.
- **Agent REST API**: shared `agent_api` connections, `owner_identity_token`, and the SDK helper.
  There are no proxy changes.
- **Plugins**: install, upgrade and uninstall routes, `PluginSyncResponse`.
- **Addons**: `SkillSlotIndex` status.
- **Readiness gate**: D1 exclusion.
- **Env core**: parser, index model, SDK, `BUILDING_AGENT.md`; environments need a rebuild.
- **Client regeneration**: at the end of Phase 1 and Phase 2 (`make gen-client`).

---

## 13. Out of scope (later)

- `provided_by="connect"`: per-installer token minting with a producer connect policy (brief,
  Alternatives), for bundles and skills alike.
- Drift detection for skill-provided credentials (sharing toggled after publish), reusing the
  bundle drift endpoint shape.
- Per-slot user selections in the install dialog (D7). The provisioner already supports
  `user_selections`.
- `required: false` optional slots.
- `credential_missing` on **local** skill rows (from `SkillEntry.credentials` against linked
  credentials).
- Unlinking a publisher-shared credential on uninstall when no remaining skill needs its slot (least
  privilege). Today only placeholders are released.
- A CLI surface (`cinna skills install` printing provisioning outcomes).
- Bundle template payload leak: `PublishService._template_payload_for` does not force-private
  `api_token` / `agent_api` / password / `odoo` secrets, so a template-shared credential ships its
  secret in bundle revision JSON unless the publisher marks it private. Apply the D12 rule to bundle
  publish (changes bundle output; needs its own I1 re-baseline).

---

## 14. Summary checklist

**Backend, Phase 1**
- [x] Parser: flat-mapping block sequences, in both copies (identical)
- [x] `invalid_credentials` + `SkillEntry.credentials` + env index model + backend public entry
- [x] `skill_package_revision.required_credential_specs` column + migration (`down_revision` = verified head)
- [x] `credential_spec.build_spec`; `ParsedCredentialSpec.producer_agent_id`; bundle collector delegates
- [x] `SkillCredentialRequirements.resolve_for_publish` / `build_specs` / `to_publish_preview` / `specs_to_public`
- [x] `publish_from_agent` writes specs; `publish_preview.credentials`; `SkillPackageRevisionPublic.required_credentials`; `credential_template_unreadable` code
- [x] `get_agent_credentials_with_data` top-level `service_uri` + `is_placeholder`; README slots section

**Agent-env, Phase 1**
- [x] `cinna_api.credentials.by_slot` / `require_slot` / `agent_api_session` + `CredentialMissing` export
- [x] Import path verified; `BUILDING_AGENT.md` "Skills that need a credential"

**Backend, Phase 2**
- [x] `CredentialsService.find_slot_match` (tier-0 extraction)
- [x] `CredentialProvisioner` (+ policies, preview, release); bundle wrapper; old helpers removed
- [x] Skill install / upgrade / uninstall wiring + credential sync; `PluginSyncResponse.credential_provisioning`
- [x] `GET /agents/{agent_id}/skills/install-preview`
- [x] `SkillSlotIndex`; Addons `credential_missing` + `credential_issues`; gate D1 exclusion
- [x] `skill_install` → Automatic; deletion impact `skill_pbp_usages` + `active_skill_install_count`

**Frontend, Phase 3**
- [x] UI Specification by the designer (§9.3)
- [x] S1 Share dialog summary · S2/S3 install resolution · S4 catalog Requires · S5 Addons status · S6 impact "Used in skills" · S7 Automatic tab copy

**Testing and validation**
- [x] Parser, validation and SDK unit tests
- [x] Publish derivation matrix, immutability, invalid declaration, `agent_api` producer id (API)
- [x] Env payload `service_uri` / `is_placeholder` (API)
- [x] Install outcomes (publisher / self / slot match / placeholder / template / unavailable / revoked), idempotency, upgrade, uninstall release, preview guards (API)
- [x] Gate: skill placeholder does not block; bundle placeholder still does (API)
- [x] Deletion impact Tier 2 via skills (API)
- [x] Bundle, credentials, agent_api and sessions suites green with no test edits
- [x] Phase 4 seam review + docs sweep + `make check-docs` + full backend suite
- [ ] Phase 4 manual end-to-end scenario (needs a dev stack: two users, a producer agent, a rebuilt env)

---

## 15. Implementation status and Phase 4 handover (2026-09-10, updated 2026-09-11)

Phases 1–3 and the regenerated client are committed as `793782a3` ("skill credentials: a skill says
which credential it needs, and the install brings it"). A follow-up docs commit `e82ee6c9` closed the
two `make check-docs` "undocumented module" failures the feature shipped with, documenting
`CredentialProvisioner` in `agent_bundles_tech.md` and `skill_credential_requirements` in
`agent_skills_tech.md` ahead of this phase's sweep.

| Phase | State | Verification |
|---|---|---|
| 1 (§7) | Done | 483 tests green. Migration `562ac5a89f04` applied, single head. |
| 2 (§8) | Done; code review clean after 2 rounds | Part A gate before part B: `bundles/` + `bundles_install/` 154/0, no fixes, no test edits. Final regression re-run on the finished tree (after D16): **618/0**. unit (secret-field coverage, manifest, SDK slots) 118 · `skill_credentials/` 20 · `credentials/` 84 · `bundles/` 76 · `bundles_install/` 78 · `agents/core/` 123 · `agent_api/` 75 · `sessions/` 44. No new migration. Client regenerated: `SkillsService.previewAgentSkillInstall({agentId, packageId, revisionNumber?})`. **The full backend suite has not been run.** |
| 3 (§9) | Done; `cinna-core.ui.review` PASS (every surface 10) and code review CLEAN, each after 2 rounds | Full `tsc --noEmit` exit 0. No backend or client change. Biome is clean on 21 of 24 touched files. `ApiTokenFields.tsx`, `columns.tsx` and `routes/_layout/credentials.tsx` have the same format/import findings as at HEAD and were left alone. |
| 4 (§10) | Seam review done (§10.1 checklist answered below); one blocking finding fixed (D17); docs sweep done (§10.2, `make check-docs` green, platform knowledge re-synced) | **Full suite 4616/0** (10 skipped, 26 min) — the first full run of this feature. Post-D17 re-run of unit + `skill_credentials` + `credentials` + `bundles` + `bundles_install`: 2343/0. Manual dev-stack scenario run on 2026-09-11 (§15) |

Phase 2 test additions:
- `skill_credentials/`: install test 10, gate test 2 (including the D15 over-claim case), publish test +1 (the D16 leak regression).
- `tests/api/credentials/test_credential_deletion_impact_skills.py`: 2.
- `tests/unit/test_skill_credential_secret_fields_coverage.py`: 2.
- One setup line changed in the Phase 1 publish test: its slot-template case now marks `api_token` private as well as `http_header_value`. No existing bundle, credentials or core test was edited.

### §10.1 seam review — answers (2026-09-11)

| Seam | Verdict |
|---|---|
| S-1 declaration → derivation | **Pass.** `resolve_for_publish` reads `entry.credentials` only (`skill_catalog_service.py:406`), normalised by `parse_credential_declarations`. `publish_from_agent` refuses on any `entry.error` (`:321`), and `invalid_credentials` is an error code, so an invalid block cannot reach a write. |
| S-2 derivation → revision JSON | **Pass.** `build_specs` sets `name = service_uri = slot`; `producer_agent_id` is appended by the skill caller only, for `agent_api` only, never inside `build_spec` — bundle JSON keeps its shape and key order. |
| S-3 revision JSON → readers | **Pass.** Provisioner, `SkillSlotIndex`, `specs_to_public` and `publisher_usages_of_credential` all go through `parse_credential_spec`, and all derive the slot as `service_uri or name` (`spec_slot`, one definition). |
| S-4 provisioner writes → matchers | **Pass.** A skill placeholder is stamped `service_uri=slot`, and `find_slot_match` keeps placeholders as candidates, so the next install links rather than duplicates. `release_skill_slots` targets exactly installer-owned placeholders whose `(type, service_uri)` is released and not retained. One accepted consequence: a **partially** filled template credential is still `is_placeholder=True`, so uninstall deletes it. It is unusable as it stands, and completing it flips the flag (`update_credential`), so the loss is bounded to half-entered data. |
| S-5 preview ↔ install | **Pass.** Both call `_decide_slot`; `preview` differs only where it cannot know the future — a template whose decryption fails reports `template_materialised` and the install degrades to `placeholder_created`. |
| S-6 credential rows → container | **Pass.** `get_agent_credentials_with_data` writes `service_uri` / `is_placeholder` top-level, outside the whitelist and the redaction; the SDK's `_find_slot` skips the synthetic entries, and `require_slot` maps "no candidate" / "unfilled placeholder" to the same two reasons the status projection uses. |
| S-7 gate ↔ bundles | **Pass.** `_drop_skill_provisioned` runs only on a non-empty list, subtracts `bundle_claimed_credential_ids`, and never touches AI items (they carry no `credential_id`). |
| S-8 classifier + impact → UI | **Pass.** `skill_install` → `automatic` in `classify_credential_category`; `skill_pbp_usages` is rendered in both `CredentialSharing.tsx:187` and `DeleteCredential.tsx:120`. |
| S-9 old containers / old caches | **Pass.** `_normalise_credential_declarations` tolerates a row with no `credentials` key; every status is computed from the revision's frozen specs, never from the container. |
| S-10 transactions | **Pass.** Install (link + provisioning), upgrade (re-pin + provisioning) and uninstall (release + delete) each commit once; every credential sync happens after the commit. |

**One blocking finding, fixed: D17.** `_template_leaking_secret_fields` required the computed
`http_header_value` to be marked private, but that field is never stored — `_process_api_token_credential`
computes it at env-sync time — and the private-field picker only offers stored fields
(`CredentialTemplateSharing.tsx:83`). An `api_token` slot could therefore **never** resolve to
`template`. Fixed with `_DERIVED_SECRET_SOURCES`: a computed secret is waived exactly when its stored
source is stripped. The leak the check exists for is unaffected (marking only `http_header_value`
private still resolves to `user` / `template_would_leak_secret`). A unit test requires every derived
field to name a source that is itself a classified stored secret; the publish regression test gained
the newly reachable case; the `api_token` copy branch in `frontend/src/utils/skillCredentials.ts` is
reverted, and `publishReasonSentence` / `publishOpenLabel` lost their `type` argument.

Also removed: `SkillSlotIndex.bundle_claimed_ids`, a property with no reader outside the class.

### Open items carried into the manual scenario
1. **D15 over-claim, end to end.** On a bundle agent with a same-type bundle spec, a skill placeholder
   stays gated and is kept on uninstall. Confirm this is acceptable in the manual scenario.
2. **Single uninstall path — verified.** `LLMPluginService.uninstall_plugin_link` is the only writer:
   `session.delete` on a plugin link appears once in the whole backend, and there is no bulk-delete
   statement over `AgentPluginLink`. Still a standing invariant for future code, now recorded in
   `agent_plugins_tech.md` and `agent_skills_tech.md`.
3. **Partial-sync toast (S2/S3 setup panel link path) — verified.** `_settle_status` evaluates
   `not_materialized` / `unverified` **before** `credential_missing`, so a partially synced catalog row
   is never `ok` and the toast's assumption holds.
5. **Accepted Phase 2 deviations to re-read:**
   - uninstall's retained specs come from `specs_except_link`;
   - `SkillSlotIndex` skips its credential queries when no link declares a slot;
   - unknown spec types are skipped;
   - the upgrade route syncs credentials on every catalog upgrade, even with nothing added;
   - `active_skill_install_count` does not filter on `is_publisher_install`.
6. **Small gaps** (worked 2026-09-11 — see "Item 6" below):
   - ~~deletion impact under-counts installers who upgraded from a publisher-provided revision to a user-provided one~~ — fixed;
   - ~~`SkillSlotIndex.bundle_claimed_ids` has no reader outside the class~~ — not a gap: it is a constructor kwarg stored as `_bundle_claimed_ids` and read by `skill_provisioned_credential_ids`, which is the encapsulation working;
   - ~~`producer_agent_id` arrives without an agent name, so "backed by agent X" is not rendered~~ — fixed;
   - ~~skill usages appear only inside the Sharing card's dialogs, not on the card body~~ — fixed by un-gating the impact read (coordinator decision, below).
7. **Secrets:**
   - a literal token typed into `api_token_template` is not detected (S8 only warns) — the one
     `api_token` leak D17 does **not** close, since that field is not a secret by name;
   - bundle publish still has the stored-vs-env template leak (§13), and only known secret field names are blocked, so extra keys in free-form `credential_data` are not;
   - skill revisions published from this tree before D16 cannot be scrubbed (I12), which only matters if something was published from it.
8. **Deferred UI — completed 2026-09-11:**
   - ~~`HashTabs` should follow the router hash, after which `hooks/useAgentTabLinkClick.ts` can be deleted~~ — fixed: `HashTabs` derives its active tab from the router location and changes tabs through router navigation, so same-page `Link hash=` navigation works and the workaround hook is deleted;
   - ~~`CredentialSharing` / `CredentialTemplateSharing` still have a hand-rolled switch and header (R11, R14a, R15), so A10 stays open for them~~ — fixed together: both now use the shared `Switch` primitive and its semantic state colours; all five credential-detail two-column grids use `items-start`, so a long Sharing card cannot stretch its neighbor.

### Inputs for the §10.2 docs sweep
- **New API surface:**
  - `GET /agents/{agent_id}/skills/install-preview`;
  - `PluginSyncResponse.credential_provisioning`;
  - `AddonPublic.credential_issues` and row `status_code = "credential_missing"`;
  - share `source = "skill_install"` → Automatic tab;
  - deletion impact `skill_pbp_usages` / `active_skill_install_count` (tier 2 covers published skills with foreign installs);
  - the D1 gate exclusion with the D15 claim rule.
- **Visible copy changes:**
  - bundle usage rows read "Shared with installers" / "Shared as a template" / "Installers provide it";
  - the package card shows "N people" / "My agents · N agents", and the reconciling sentence is gone;
  - the delete button reads "Delete credential";
  - the Automatic tab has new description copy (S7);
  - the `api_token_template` help line has a warning (S8).
- **Guideline lessons for `ui_ux_guidelines.md`** (listed at the end of §9.3):
  - `HashTabs` same-page links;
  - re-check R4/R10 when fixing a list you touch;
  - an info tooltip must not repeat the meta line;
  - a block under a status Alert with varying text needs its own label.

### Manual scenario run — §10.1, local dev stack, 2026-09-11

Two users (`admin@example.com`, publisher/producer owner; `erp-consumer@example.com`, a fresh
`agent-developer`), five agents and five environments created for the run. Every environment was
created after the feature commits, so all of them carry the new `cinna_api.credentials` helpers
(the template image hash covers `Dockerfile`/`pyproject.toml`/`uv.lock` only — `app/core` is
bind-mounted per instance, so a fresh env *is* the rebuild).

**Setup.** Producer `erp-public-api` (agent `4f60f4f1`) with `agent_api/erp.py` (`/whoami`,
`/customers`, both taking the SDK `caller`) and a `policy.yaml` declaring `read_only`, a
`120/min` rate limit and an `erp.read` scope catalog; `agent_api_enabled` +
`agent_api_identity_enabled` on. Builder `erp-skill-builder` connected to it; the connection
credential stamped `service_uri=erp-public-api` with sharing on. `skills/erp-public-data/`
authored with the `credentials:` block and a script that calls
`credentials.agent_api_session("erp-public-api")`.

| Step | Result |
|---|---|
| Declaration parses in the container | `POST /skills/refresh` returns `credentials: [{slot, type, description}]`, `can_publish: true`, no error |
| Publish preview | `provided_by: "publisher"`, `credential_name: "ERP Public API"`, `producer_agent_id` set |
| Publish (`visibility=public`) | revision 1 `required_credentials[0].provided_by == "publisher"` with `publisher_credential_id` |
| Second user's catalog | package visible, `required_credentials` rendered on the entry |
| Install preview / install | `linked_publisher`; share created with `source="skill_install"`; `shared-with-me` shows `category: "automatic"` |
| Consumer `credentials.json` | one entry with top-level `service_uri: "erp-public-api"`, `is_placeholder: false`, plus the synthetic `current_user` and `owner_identity` entries |
| Script through the slot | `/whoami` → `anonymous: false`, `user_id`/`email` of the **second** user; `/customers` → `called_by: "erp-consumer@example.com"` |
| Producer scopes, live | granting `erp.read` to the second user shows up on the **next call** with no re-sync |
| Addons row | `status: "ok"` |
| Sharing off (`PATCH /credentials/{id}/sharing`) | share deleted; addons row `warning` / `credential_missing` / `reason: "access_revoked"`; `GET /setup-status` stays `ready` (D1) |
| Deletion impact | `tier: 2`, `skill_pbp_usages` names the package + revision, `active_skill_install_count: 1`; `DELETE` → 409 with the same body, `?force=true` → 200 |
| After the delete | the consumer env re-synced; `credentials.json` keeps only `current_user`; the script exits 1 with `no credential for slot 'erp-public-api' is linked to this agent. Fix: open the agent's Credentials tab and link a credential whose service URI (slot) is 'erp-public-api'.`; addons row reason flips to `not_linked` |

**D15 over-claim, end to end — confirmed, and the copy is the problem, not the rule.**
Reproduced with a published bundle carrying one `agent_api` spec (`provided_by: "user"`,
`service_uri: null`) that the installer answered with an `use_existing` pick — the case rule (c)
exists for. On that bundle agent:

- installing the skill created the placeholder `erp-public-api` (`publisher_unavailable`, because
  sharing was already off) and `GET /setup-status` returned **`needs_setup`** — the placeholder is
  claimed by the bundle's unaccounted `agent_api` spec, so the D1 exclusion does not drop it;
- the **same** placeholder row, linked into a second, non-bundle agent of the same user
  (`linked_existing`, I9), leaves that agent `ready`. One credential, two verdicts;
- uninstalling the skill kept the link (claimed), exactly as D15 says.

Where it stops reading acceptably is *after* that uninstall. The bundle agent is still blocked, and
the chat gate says:

> Setup needed before this agent can run. Open the agent's Credentials tab and fill in the missing
> values one by one.
> - erp-public-api (agent_api)

with `GET /setup-credentials` still describing the row as *"Required by an installed skill. Fill it
in on the agent's Credentials tab."* — while the Addons tab is empty. Nothing on screen explains the
block, and the one sentence that tries to is now false. While the skill **is** installed the same
block reads fine: the slot name matches the amber Addons row and the setup page's sentence is true.

**Finding (1), fixed: a revoked share did not reach the container.** Turning sharing off deleted the
`CredentialShare` and turned the Addons row amber, but `AgentCredentialLink` survived and env
materialisation is link-based (`get_agent_credentials` joins the link table only, never re-checking
access), and nothing re-synced on revocation. The consumer container kept a working token: after the
revoke — and after an env restart — the script still called the producer successfully, and the
platform kept minting a fresh `owner_identity_token` for the revoked user on every sync. Only deleting
the credential cut it off. Pre-existing and generic (bundle shares behaved the same), and it
contradicted `credential_sharing.md` ("Immediate access removal"). It is also the unfinished half of a
bug `tests/api/credentials/test_ssh_key_credential_update_share.py` had already recorded: that note
asked for a re-sync, which alone would have written the same credential straight back.

Fixed (coordinator decision, 2026-09-11): `CredentialsService.unlink_credential_from_revoked_recipients`
deletes every link to the credential on agents owned by a revoked recipient and fires the existing
`event_credential_unshared` per agent. Both revocation entry points call it —
`DELETE /credentials/{id}/shares/{share_id}` and `PATCH /credentials/{id}/sharing` — and both service
methods and their routes became async. The owner's own links are untouched. Consequences to know: a
recipient whose share is restored must re-link (a reinstall or an upgrade does it for them), and
`access_revoked` now describes only the generic `PUT /credentials/{id}` path, which still leaves share
and link in place; the `PATCH` path lands on `not_linked`. Covered by
`tests/api/credentials/test_credential_share_revocation.py` (2), the rewritten scenario 7 and a new
`PUT`-path case in `agents_skill_credentials_install_test.py` — all four fail with the fix disabled.

**The bundle half of that fix (I10).** The readiness gate walked `AgentCredentialLink` rows only, so
deleting the link on revocation silently took a bundle install's `publisher_broken` verdict with it —
`agents_bundles_install_readiness_test.py::test_gate_publisher_broken_when_sharing_revoked` caught it:
the agent read `ready` while the credential its bundle contracts for was gone. The gate gained a
spec-side pass, `_scan_unlinked_publisher_specs`: for a bundle spec with a `publisher_credential_id`
that nothing links any more, a deleted credential row is `publisher_credential_missing`, an
unreachable one (sharing off, or no share) is `publisher_credential_unshared`, and one the installer
can still reach is silent — that last case is an installer who unlinked something they can re-link,
which never blocked the agent before either. Scenario D now also asserts the link is gone, so the two
halves cannot drift apart again.

**Finding (2), fixed as copy: the post-uninstall blocked bundle agent**, above. Decision: keep the D15
claim rule (under-claiming would drop a bundle blocker, I10) and make the copy true.
`InstallService.list_setup_credentials` now compares each skill placeholder against
`SkillSlotIndex.slot_credential_ids()` — a new method with no bundle subtraction, which
`skill_provisioned_credential_ids()` is now defined in terms of — and describes a row nothing declares
any more with `ORPHANED_SKILL_PLACEHOLDER_NOTE`: "No installed skill requires this any more. It is kept
because this agent's bundle may use it — fill it in, or unlink it on the Credentials tab to clear the
setup block." The gate's own sentence is left alone: it says the agent needs setup and names the slot,
both still true, and it makes no claim about where the slot came from (D15 keeps gate enrichment
unchanged). Covered by scenario 3 in `agents_skill_credentials_gate_test.py`.

**Regression after both fixes:** `tests/api/credentials` + `tests/api/agents/skill_credentials` +
`tests/api/agents/bundles` + `tests/api/agents/bundles_install` + `tests/unit` +
`tests/api/agents/core` = **2470 passed, 10 skipped**; `tests/api/agents/sessions` +
`tests/api/agents/agent_api` + `tests/api/agents/bundles_install` = **197 passed** (the gate runs on
the chat path). `make check-docs` green, platform knowledge re-synced, client regenerated — the only
API-surface change is the `PATCH …/sharing` description.

Confirmed live and already known: the generic `PUT /credentials/{id}` turning `allow_sharing` off
leaves the shares in place (only `PATCH /credentials/{id}/sharing` deletes them) — the stale-share
trap Phase 2 guarded around. Note that once the flag has been flipped by `PUT`, the `PATCH` path can
no longer purge, because it only deletes shares when the flag was still true.

### Item 6 — the small gaps, worked 2026-09-11

**The deletion-impact under-count, fixed.** `active_skill_install_count` matched a foreign agent's
catalog install against the revisions that *still* freeze the credential as publisher-provided. But
`upgrade_link` provisions only the specs a revision **adds** (§8.4) and never releases one it dropped,
so an installer who moved to a revision where the slot became `user` keeps both the share and the
link — and still breaks when the credential is deleted. They fell out of the count, which took the
Tier-2 block with them: the unforced `DELETE` returned 200.

`publisher_usages_of_credential` now returns **every** revision id of the packages its usages name,
not only the providing ones; the EXISTS is unchanged otherwise, so a direct-share recipient who
linked the credential is still not an installer. The residual error changed direction: an installer
of an affected package who holds the credential by direct share rather than through the install now
counts. That is the safe direction — over-counting warns, under-counting deletes. `revision_numbers`
on each usage still names only where the credential *is* publisher-provided, so the dialog's list is
unchanged. Covered by scenario 3 in `test_credential_deletion_impact_skills.py`, which fails with the
fix disabled.

**"Backed by agent X", rendered.** The name is now frozen into the spec at publish beside
`producer_agent_id` (`build_specs`, from `_read_producer_agent_name`), parsed back by
`parse_credential_spec`, and carried on `SkillCredentialRequirementPublic` and
`SkillPublishCredentialPreview` — the two payloads that already carried the id. Freezing rather than
resolving at read time is what keeps a catalog listing at its current query count: `revision_to_public`
is a pure projection with no session, and resolving per revision would have made it N+1. The cost is
that a rename does not reach a published revision, which is the same immutability the rest of the spec
has (I12), and an old revision sends no name — the FE then renders no line rather than a bare id.
`utils/skillCredentials.ts` gained `producerAgentFact`, rendered as a row fact on S1 (Share skill) and
S4b (the package card's Credentials sheet). Covered by the extended scenario 5 in
`agents_skill_credentials_publish_test.py`, including the rename.

**Not extended to the install dialogs.** S2/S3 rows are built from `SkillCredentialProvisionPublic`,
which never carried `producer_agent_id` either — adding it means threading producer fields through
`SlotProvision`, which the bundle install path shares. Out of the gap as recorded; worth doing only as
its own decision.

**Skill usages on the Sharing card body — done, by un-gating the impact read.** The choice was
between un-gating `GET /credentials/{id}/deletion-impact` on every credential detail view and adding a
skill-usages endpoint mirroring the bundle one; the coordinator chose un-gating (2026-09-11), so no
API surface was added. `CredentialSharing` dropped `enabled: isDisableDialogOpen`; the body gained a
"Used in Skills" `PreviewList` over `skill_pbp_usages`, following the bundles block beside it exactly
— capped at five, hidden only once *known* to be empty, and keeping its rows through a failed
background refetch, so a failure never reads as "used in no skills".

Two knock-ons. Both dialogs that share the cache key now open with the data warm instead of on a
skeleton, and `DeleteCredential` deliberately keeps its own `enabled: isOpen`: it renders once per row
in the credentials list, where un-gating would be one request per row, while on the detail page it
reads the warm entry anyway. `CredentialBundleUsagesSheet` became `CredentialUsagesSheet`, one shell
taking title, description and row children, rather than a second near-identical file.
