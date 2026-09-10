# Skill Credential Requirements — Architecture Design Brief

Status: design brief (input to `skill_credential_requirements_plan.md`)
Date: 2026-09-10

## Problem

A catalog skill is prompt text plus scripts, and those scripts need a credential
to do anything useful. Today nothing ties the two together: the skill can only
grope for a credential by name or type at runtime, install time knows nothing
about the requirement, and the only way a second user gets the credential is a
manual share by email.

Target scenario:

- a producer agent `erp-public-api` exposes a narrowed Agent REST API in front
  of the real ERP credential;
- a skill `erp-public-data` is published to the catalog with `visibility=public`;
- any internal user installs the skill into one of their agents and it works
  immediately — the agent-api connection is provisioned and linked, the
  producer still sees which user is calling (identity + scopes);
- when a required credential cannot be resolved, the user is told where and how
  to fix it (never a silent failure inside the container).

Constraints: secrets never live in the skill folder (the filename secret gate
stays), the trust boundary stays "credential owner decides who receives it",
and per-user attribution/scopes on the producer keep working.

## Key insight: a skill package is a small bundle

Bundles already solved this end to end. Reuse that vocabulary and pipeline;
do not invent a skill-specific one.

| Need | Existing solution to build on |
|------|-------------------------------|
| Spec vocabulary | `backend/app/services/bundles/credential_spec.py:19` `ParsedCredentialSpec` — `name, type, provided_by ∈ {user, publisher, template}, publisher_credential_id, template_data, template_private_fields, service_uri` |
| Slot identity | `Credential.service_uri` (non-secret slot id) + `CredentialsService.find_match_for_spec` (`credentials_service.py:2140`), tiers 0a owned / 0b shared before name matching |
| Publish-time derivation | `PublishService.resolve_provided_by` (`publish_service.py:710`), `_collect_credential_specs` (`:745`), `_template_payload_for`, `_validate_publisher_provides` |
| Install-time provisioning | `InstallService._setup_install_credentials` (`install_service.py:724`), `_try_link_publisher_credential` (`:992`, share-on-install `CredentialShare.source="bundle_install"`), `_materialise_template_credential` (`:926`) — degrade-not-fail |
| The alert | `InstallReadinessGate` (`install_readiness_gate.py:76`) walks `AgentCredentialLink` rows for ANY agent: placeholder → `needs_setup`, foreign credential without share → `publisher_broken`; `InstallGateDispatcher` fires `INSTALL_SETUP_REQUIRED` on inbound messages; setup-credentials page exists (`routes/installs.py:341`) |
| Per-user identity on a shared token | `owner_identity_token` block minted per install owner on every credential sync; scopes resolved live from `agent_api_access_grant` |
| Skill catalog seams | `SkillPackageRevision.frontmatter` (`models/skills/skill_package_revision.py:16`); `SkillCatalogService.install_into_agent` (`skill_catalog_service.py:1859`), `upgrade_link` (`:1940`), `publish_preview` (`:529`), `publish_from_agent`; route `POST /agents/{id}/skills/install` (`routes/skills.py:539`) |
| Row status vocabulary | `AddonsService._settle_status` (`addons_service.py:429`) |
| Env-side accessor | `backend/app/env-templates/app_core_base/core/cinna_api/credentials.py:27` (`get`, `by_type`, `all_by_type`; reads fresh each call) |
| Deletion blast radius | `CredentialsService.get_deletion_impact` Tier 2 scans bundle revisions' specs |

Two gaps in the existing code that the design must close:

1. **`service_uri` does not reach `credentials.json` except for `api_token`.** It
   is injected into `credential_data` only for that type
   (`credentials_service.py:215`) and the per-type whitelist
   `AGENT_ENV_ALLOWED_FIELDS` (`:164`) strips it for `agent_api`. A script in
   the container cannot find a credential by slot today.
2. **The frontmatter parser** (`backend/app/services/agents/skill_manifest.py:443`
   `parse_frontmatter`) supports one level of nested mapping and sequences of
   scalars only. A block sequence of mappings is not parseable. The parser is
   vendored twice (backend + env-core `server/skill_manifest.py`); both copies
   must stay identical.

## Design

### 1. Declaration in `SKILL.md` frontmatter

Top-level `credentials:` block sequence, one entry per slot:

```yaml
---
name: erp-public-data
description: Query public ERP data (customers, orders) via the erp-public-api agent.
version: 1.0.0
credentials:
  - slot: erp-public-api
    type: agent_api
    description: Read-only connection to the erp-public-api producer agent
---
```

- Precedent: `version` is already a platform-interpreted key beyond the Agent
  Skills standard; both engines ignore unknown keys.
- `slot` **is** `Credential.service_uri`. `type` is a `CredentialType` value.
  `description` optional. (Optional later: `required: false`.)
- Parser gains exactly one capability: block sequence whose items are flat
  mappings (`- key: value` + indented continuation lines). Mirror in both
  vendored copies.
- Validation joins the issue vocabulary: new **error** code
  `invalid_credentials` (unknown type, bad slot shape, duplicate slot). An
  invalid declaration is excluded from projection like any other error, so the
  card refuses before publish does (same discipline as `secrets`).
- `SkillEntry` gains a parsed `credentials: list[dict]` (always present, empty
  = none declared) so the index, the bundle `skills_summary` consumers and the
  publish path read one shape.

### 2. Publish derives `required_credential_specs` onto the revision

- New JSON column `required_credential_specs` on `SkillPackageRevision`
  (alembic migration; `'[]'::json` server default). Same dict schema as
  `AgentBundleRevision.required_credential_specs` so `parse_credential_spec`
  is the single reader.
- In `SkillCatalogService.publish_from_agent`, for each declared slot look up
  the **publishing agent's linked credential** with `type == spec.type AND
  service_uri == slot` (the credential the publisher tested the skill with).
  Resolution:
  - match found, `allow_sharing=True` → `provided_by="publisher"`,
    `publisher_credential_id` stamped (the erp-public-data case);
  - match found, `allow_template_sharing=True` → `provided_by="template"`
    with the non-private payload via the existing template helper;
  - no match, or match not shareable → `provided_by="user"` — **not a
    refusal** (a generic "github" skill legitimately ships with the consumer
    bringing their own token).
  - `name` of the spec = the slot; `service_uri` = the slot; `description`
    from the declaration (fallback credential notes).
  - For `agent_api` specs also record `producer_agent_id` (from the
    credential data) so the catalog can say "backed by agent X" and a later
    phase can offer per-installer minting.
- Extract the per-credential spec builder out of
  `PublishService._collect_credential_specs` into
  `credential_spec.build_spec(session, credential, provided_by, *, name=None,
  service_uri=None, description=None) -> dict` used by BOTH bundle publish and
  skill publish — one schema, one writer.
- `SkillPublishPreview` gains `credentials: [{slot, type, provided_by,
  credential_name | None, producer_agent_id | None}]` so the Share dialog shows
  the resolved provisioning before the press. `SkillPackageRevisionPublic` /
  `SkillPackageDetailPublic` expose the specs (never `template_data` private
  fields; `publisher_credential_id` is fine — it is an id, not a secret).

### 3. Install resolves each slot through one provisioning chokepoint

Extract the branch logic of `_setup_install_credentials`,
`_try_link_publisher_credential`, `_materialise_template_credential` into a new
service `backend/app/services/credentials/credential_provisioner.py`:

```python
class CredentialProvisioner:
    @staticmethod
    def provision(
        session, *, agent: Agent, specs: list[ParsedCredentialSpec],
        publisher_user_id: uuid.UUID | None,
        share_source: Literal["bundle_install", "skill_install"],
        user_selections: dict | None = None,
    ) -> ProvisionReport   # per spec: linked | placeholder_created | template_materialised | publisher_broken
```

`InstallService` keeps a thin wrapper (bundle behaviour byte-for-byte
unchanged, existing bundle tests must pass untouched).
`SkillCatalogService.install_into_agent` and `upgrade_link` call it after the
link is created and **before** the plugin sync, so the first sync already
carries the credential. Per mode:

- **publisher** → share-on-install with `CredentialShare.source="skill_install"`
  (new value) + `AgentCredentialLink`. Trust boundary as bundles: credential
  owner must equal the **skill package publisher**, `allow_sharing` still
  true; otherwise degrade to placeholder and report `publisher_broken`.
  Installer == publisher needs no share.
- **user** → `find_match_for_spec(service_uri=slot, type)`; link a hit;
  otherwise create a placeholder `Credential(type, name=slot,
  service_uri=slot, is_placeholder=True, owner=installer, workspace=agent's)`
  and link it. The readiness gate then nags in chat and the setup page lets
  the user fill it — "if not found, alert the user" for free.
- **template** → materialise as bundles do.
- Idempotent on reinstall/upgrade (never a second link, never a second
  placeholder for the same slot). Upgrade re-runs provisioning for specs added
  by the new revision.
- Uninstall (ordinary plugin delete on a `source=catalog` link) unlinks only
  credentials that are **still placeholders** for this skill's slots; real
  credentials stay (slots may be shared across skills).

### 4. Status surfaces

- `AddonsService._settle_status`: new code `credential_missing` (**warning**),
  evaluated after `not_materialized`/`unverified` and before skill-level
  warnings: any spec of the link whose linked credential is a placeholder, or
  whose share is gone / credential missing. Carried on the row as
  `credential_issues: [{slot, type, reason}]` so the client can deep-link to
  the Credentials tab.
- Catalog grid card + package page: "Requires: erp-public-api (provided by
  publisher)" — one line per spec.
- `classify_credential_category`: `share.source == "skill_install"` → the
  **Automatic** tab (it is made of the same automatic `agent_api` material).
- `get_deletion_impact` Tier 2 + the disable-sharing blast radius must also
  count skill revisions whose specs reference the credential as publisher-
  provided (`skill_pbp_usages`), otherwise deleting the connection silently
  breaks every skill install.
- Readiness-gate chat copy: verify it reads sensibly on a plain agent that
  merely carries a skill (the copy currently says "install").

### 5. Env side

- Emit `service_uri` as a **top-level** field of every `credentials.json`
  entry next to `id/name/type/notes` (type-agnostic, bypasses the per-type
  whitelist since it is non-secret by definition). Keep the `api_token`
  in-data copy for compatibility. README render lists it and documents the
  slot convention.
- `cinna_api.credentials` gains `by_slot(slot) -> dict | None`,
  `require_slot(slot) -> dict` (raises `CredentialMissing` with a stable
  message naming the slot and the fix: "link a credential with slot X on the
  agent's Credentials tab"), and `agent_api_session(slot)` returning a
  `requests.Session` pre-configured with the Bearer token and the
  `X-Cinna-Caller-Identity` header from the `owner_identity` entry.
- `BUILDING_AGENT.md` authoring guidance: how to declare `credentials:`, how
  scripts consume a slot, and the SKILL.md body convention "if the script
  reports `credential_missing`, tell the user how to fix it".
- New SDK code ⇒ environment rebuild (documented pattern; pre-feature
  containers keep working — they just lack the helpers).

### 6. The "everyone" scenario, end to end

1. Producer owner enables agent-api on `erp-public-api`, writes
   `policy.yaml`, optionally enables identity + scopes.
2. On the skill-building agent: Connect Agent API → stamp
   `service_uri=erp-public-api` on the connection credential → enable
   sharing on it.
3. Author `skills/erp-public-data/` with the `credentials:` block; publish
   with `visibility=public`.
4. Any internal user installs from the catalog; provisioning shares the
   connection and links it. The consumer container gets `{base_url, token,
   service_uri}` plus its own `owner_identity_token`, so the producer sees
   which user is calling and their live scopes.
5. Revocation per user = the `CredentialShare` row; for all = deleting the
   connection (deletion-impact gate now counts skill installs).

Security: no secret enters the skill folder; the publisher's credential is
shared only to users the package visibility already admits; identity stays per
install owner; the shared token keeps the documented trade-offs (shared rate
budget, no per-token revocation).

## Alternatives considered

- **Per-installer token minting** (`provided_by="connect"`): producer gets a
  connect policy (owner / allowlist / anyone), the ownership gate in
  `connect_agent_api` (`agent_api_token_service.py:210`) relaxes to that
  policy, provisioning mints each installer their own connection. Better
  isolation, closes a documented bundle gap. Deferred: a new producer-side
  authorization concept before the simple path exists. Fits later as a fourth
  mode both bundles and skills get.
- **Instruction only** (SKILL.md tells the model to look for a credential and
  ask): zero build, silent failure, no install-time link, no sharing. Rejected.
- **Sidecar manifest file**: keeps the parser untouched but splits the skill's
  contract across two files. Rejected.

## Refactors that earn their keep

1. `CredentialProvisioner` extracted from `InstallService` (bundles + skills).
2. `credential_spec.build_spec(...)` extracted from
   `PublishService._collect_credential_specs` (one writer, one reader).
3. Type-agnostic top-level `service_uri` in the env payload.
4. Parser: block sequence of flat mappings, in both vendored copies.

## Risks & open questions

- Publisher ≠ producer owner: a received share cannot be re-shared, so
  `provided_by="publisher"` requires the skill publisher to own the connection
  credential. Same boundary as bundles; Share dialog copy must say so.
- Old containers: a pre-extension env-core parser keeps the unknown block as
  text; the host parse at publish is authoritative. No rebuild needed for the
  declaration, only for the SDK helper.
- Drift (sharing toggled after publish) — same as bundles; later phase can
  reuse the drift endpoint shape.
- Two skills declaring the same slot resolve to the same credential — desired.
- A bundle that carries a catalog skill picks the linked credential up through
  the ordinary bundle `_collect_credential_specs` — documented, no special
  case.

## Suggested phasing

1. **Foundation (backend + env-core):** parser extension (both copies) +
   `invalid_credentials` validation + `SkillEntry.credentials`;
   `required_credential_specs` column + migration; `build_spec` extraction;
   publish derivation + preview + public schemas; top-level `service_uri` in
   env payload + README; SDK `by_slot` / `require_slot` /
   `agent_api_session`; BUILDING_AGENT.md guidance.
2. **Provisioning (backend):** `CredentialProvisioner` extraction with bundle
   tests green; wire skill install + upgrade + uninstall rule;
   `CredentialShare.source="skill_install"` + classifier; deletion-impact +
   disable-sharing awareness; `credential_missing` row status +
   `credential_issues`; gate copy check.
3. **UI (frontend):** Share dialog provisioning summary; install dialog
   showing slots + resolved provisioning / suggested matches; catalog
   "Requires" line; addons row status with deep link to the Credentials tab;
   credential detail page "Used in skills" disclosure.
4. **Seam review + docs sweep:** one whole-feature review across the three
   phases (handoffs: what publish writes → what install reads → what the
   status projection reads → what the container reads), then docs.
5. **Later (out of scope now):** `provided_by="connect"` per-installer
   minting; drift detection for skill-provided credentials.
