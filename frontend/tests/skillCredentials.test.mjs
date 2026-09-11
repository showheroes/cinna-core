import assert from "node:assert/strict"
import test from "node:test"
import {
  hasPluginSyncIssues,
  pluginInstallSyncWarning,
} from "../src/utils/pluginSync.ts"
import {
  countSlotsNeedingSetup,
  credentialTypeLabel,
  producerAgentFact,
  publishOpenLabel,
  publishReasonSentence,
  requirementsSummary,
  skillImpactSentence,
  slotOutcomeCopy,
  slotOutcomeStatus,
  slotOutcomeSummary,
} from "../src/utils/skillCredentials.ts"

// These helpers drive both install dialogs' rows, success-close and setup panel.
for (const outcome of [
  "already_linked",
  "linked_existing",
  "linked_publisher",
]) {
  test(`${outcome}: an unusable credential keeps setup visible`, () => {
    const item = { slot: "erp", outcome, needs_setup: true }
    assert.equal(countSlotsNeedingSetup([item]), 1)
    assert.match(
      slotOutcomeCopy(item).short({ slot: item.slot }),
      /needs setup/,
    )
    for (const phase of ["preview", "installed"]) {
      const status = slotOutcomeStatus(item, phase)
      assert.equal(status.tone, "warning")
      assert.match(status.label, /Credentials tab/)
      assert.match(slotOutcomeSummary([item], phase), /setup/)
      assert.doesNotMatch(slotOutcomeSummary([item], phase), /Ready/)
    }
  })

  test(`${outcome}: a usable credential is ready`, () => {
    const item = { slot: "erp", outcome, needs_setup: false }
    assert.equal(countSlotsNeedingSetup([item]), 0)
    for (const phase of ["preview", "installed"]) {
      assert.equal(slotOutcomeStatus(item, phase).tone, "on")
      assert.equal(
        slotOutcomeSummary([item], phase),
        "Ready to use on this agent.",
      )
    }
  })
}

test("new placeholders and templates need setup; old responses keep outcome defaults", () => {
  const items = [
    "template_materialised",
    "placeholder_created",
    "publisher_unavailable",
  ].map((outcome) => ({ slot: "erp", outcome }))
  for (const needs_setup of [undefined, true]) {
    const provisions = items.map((item) => ({ ...item, needs_setup }))
    assert.equal(countSlotsNeedingSetup(provisions), 3)
    for (const item of provisions) {
      assert.equal(slotOutcomeStatus(item, "preview").tone, "warning")
      assert.equal(slotOutcomeStatus(item, "installed").tone, "warning")
    }
  }
  assert.equal(countSlotsNeedingSetup([{ outcome: "linked_existing" }]), 0)
})

test("mixed readiness counts only the slots that still need action", () => {
  const items = [
    { outcome: "linked_existing", needs_setup: true },
    { outcome: "already_linked", needs_setup: false },
    { outcome: "placeholder_created", needs_setup: true },
  ]
  assert.equal(countSlotsNeedingSetup(items), 2)
  assert.equal(
    slotOutcomeSummary(items, "preview"),
    "2 need setup after install.",
  )
  assert.equal(
    slotOutcomeSummary(items, "installed"),
    "2 credentials need setup before the skill can use them.",
  )
})

test("install success does not hide unsupported or partially failed environment syncs", () => {
  for (const result of [
    { failed_syncs: 1 },
    { unsupported_syncs: 1 },
    { partial_failures: true },
  ]) {
    assert.equal(hasPluginSyncIssues({ success: true, ...result }), true)
    // Needs-setup and ready installs both retain the environment warning.
    for (const needs_setup of [true, false]) {
      const report = {
        ...result,
        credential_provisioning: [{ outcome: "linked_existing", needs_setup }],
      }
      assert.equal(hasPluginSyncIssues(report), true)
      assert.equal(
        countSlotsNeedingSetup(report.credential_provisioning),
        Number(needs_setup),
      )
    }
  }
  assert.equal(hasPluginSyncIssues({}), false)
  assert.equal(
    hasPluginSyncIssues({
      failed_syncs: 0,
      unsupported_syncs: 0,
      partial_failures: false,
    }),
    false,
  )
  assert.match(pluginInstallSyncWarning("ERP"), /ERP installed, but/)
  assert.match(pluginInstallSyncWarning("ERP"), /agent's Addons tab/)
})

test("catalog requirements distinguish publisher, template and user setup", () => {
  assert.equal(requirementsSummary(undefined), null)
  assert.equal(requirementsSummary([]), null)
  assert.equal(
    requirementsSummary([{ provided_by: "publisher" }]),
    "1 credential, provided by the publisher",
  )
  assert.equal(
    requirementsSummary([{ provided_by: "template" }]),
    "1 credential, you provide it",
  )
  assert.equal(
    requirementsSummary([{}, { provided_by: "user" }]),
    "2 credentials, you provide them",
  )
  assert.equal(
    requirementsSummary([
      { provided_by: "publisher" },
      { provided_by: "template" },
    ]),
    "2 credentials, 1 from you",
  )
})

test("publisher remedies remain actionable for templates and missing names", () => {
  assert.match(
    publishReasonSentence("template_would_leak_secret", "ERP"),
    /Mark its secret fields private/,
  )
  assert.match(
    publishOpenLabel("template_would_leak_secret", "ERP"),
    /mark its secret fields private/,
  )
  assert.match(
    publishReasonSentence("not_shareable", ""),
    /Sharing is off on the credential/,
  )
  assert.equal(
    publishOpenLabel("not_shareable", ""),
    "Open the credential to turn sharing on (new tab)",
  )
  assert.match(
    publishReasonSentence("not_owned", null),
    /Only credentials you own/,
  )
  assert.match(
    publishReasonSentence("no_linked_credential", null),
    /installers bring their own/,
  )
  assert.equal(producerAgentFact("ERP"), "Backed by agent ERP")
  assert.equal(producerAgentFact(""), null)
  assert.equal(producerAgentFact(null), null)
  assert.equal(credentialTypeLabel("agent_api"), "Agent REST API")
  assert.equal(credentialTypeLabel("future_type"), "future_type")
})

test("skill impact copy names real active installs with accurate plurals", () => {
  assert.equal(
    skillImpactSentence(1, 1, "disable"),
    "Provided by the publisher in 1 published skill with 1 active install. Disabling sharing leaves those installs without it.",
  )
  assert.equal(
    skillImpactSentence(2, 3, "delete"),
    "Provided by the publisher in 2 published skills with 3 active installs. Deleting it leaves those installs without it.",
  )
  for (const action of ["disable", "delete"]) {
    assert.equal(
      skillImpactSentence(1, 0, action),
      "Provided by the publisher in 1 published skill.",
    )
  }
})
