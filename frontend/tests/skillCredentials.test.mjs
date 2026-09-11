import assert from "node:assert/strict"
import test from "node:test"

import {
  countSlotsNeedingSetup,
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
