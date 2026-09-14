import { KeyRound, Upload } from "lucide-react"

import type { AddonPublic } from "@/client"
import { RowFlag } from "@/components/Common/ListRow"
import { Badge } from "@/components/ui/badge"
import { addonCredentialSlots } from "@/utils/addons"
import { credentialTypeLabel } from "@/utils/skillCredentials"

interface AddonBadgesProps {
  addon: AddonPublic
}

/**
 * **Local** — the one origin badge a local skill's row carries.
 *
 * A list that merges four origins has no unmarked default, and a local skill
 * carries neither a marketplace nor an author, so without this the row built in
 * this agent is the one row with nothing on it. It occupies the slot `author`
 * fills on every other source's row — the same question, answered for the one
 * source that has no author to name — which is what keeps the row inside the
 * two-badge exception §2 already grants rather than past it.
 *
 * "Published" is deliberately **not** a second badge here: see
 * {@link AddonPublishedFlag}.
 */
export function AddonLocalBadge({ addon }: AddonBadgesProps) {
  if (addon.source !== "local") return null
  return (
    <Badge variant="outline" className="h-5">
      Local
    </Badge>
  )
}

/**
 * **Published** — "this one of mine is in the catalog", as a flag rather than a
 * badge.
 *
 * It is a passive per-row fact the user reads and cannot click, which is what
 * §2 "Row flags" describes: one glyph, a required tooltip, an `sr-only` label,
 * and no cost to the name's width. A third `Badge` would have put the row past
 * the two the guidelines allow it, on the title line that is contested space
 * either way — and the word itself is not lost, because `AddonDetailDialog`
 * still spells it out beside the package id.
 *
 * Rendered in the flags cluster next to the update flag, so a local row's
 * right-hand side reads the same way every other row's does.
 */
export function AddonPublishedFlag({ addon }: AddonBadgesProps) {
  if (addon.source !== "local" || !addon.published_package_id) return null
  return <RowFlag icon={Upload} label="Published to the skills catalog" />
}

/**
 * **Needs credentials** — the row's skills declare credential slots, named in
 * the tooltip with their types.
 *
 * A passive fact, so a flag (§2 "Row flags") and muted: for a local or
 * marketplace skill the slots are declared, not checked. It turns `warning`
 * only on a catalog row with `credential_issues` — the one case the server
 * knows a slot is not usable — which is when §2 lets a flag carry colour. The
 * `KeyRound` glyph is the one the package card's Credentials fact uses, so the
 * same requirement reads the same in the catalog and on the agent.
 */
export function AddonCredentialsFlag({ addon }: AddonBadgesProps) {
  const slots = addonCredentialSlots(addon)
  if (slots.length === 0) return null

  const noun = `${slots.length} ${slots.length === 1 ? "credential" : "credentials"}`
  const names = slots
    .map((slot) => `${slot.slot} (${credentialTypeLabel(slot.type)})`)
    .join(", ")
  const unusable = addon.credential_issues?.length ?? 0

  return unusable > 0 ? (
    <RowFlag
      icon={KeyRound}
      tone="warning"
      // "Not usable", not "not set up": the reasons include a publisher who
      // stopped sharing, which nobody on this agent failed to set up.
      label={`Needs ${noun}, ${unusable} not usable — ${names}`}
    />
  ) : (
    <RowFlag icon={KeyRound} label={`Needs ${noun} — ${names}`} />
  )
}
