import type { ReactNode } from "react"

import { ListRow, RowInfo, type RowStatus } from "@/components/Common/ListRow"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { credentialTypeLabel } from "@/utils/skillCredentials"

interface SkillCredentialSlotRowProps {
  /** The user-typed slot id (a `service_uri`), up to 255 characters. */
  slot: string
  type: string
  description?: string | null
  /** A health state (install outcome, addon issue). Omit on read-only lists. */
  status?: RowStatus
  /** The surface's answer for this slot: what installers get, what is wrong. */
  summary: string
  /** Further facts for the row's `RowInfo`, after the description. */
  facts?: Array<string | false | null | undefined>
  /** At most one inline control. */
  action?: ReactNode
}

/**
 * One credential slot of a catalog skill — the same row wherever the slot
 * appears (Share skill, Add skill to agent, the Add addon wizard, the package
 * card's Credentials Sheet, the addon detail dialog), so a slot reads the same
 * before an install and after it (§2 "The same entity, before and after").
 *
 * The meta line earns its height: it is each surface's answer, and a slot that
 * needs setup says so in words there rather than through the dot's colour
 * alone.
 *
 * The slot is a user-typed id, so it truncates, with the full value in a
 * tooltip on a **non-focusable** span: a focusable trigger would put a tooltip
 * on the first-focus path of the dialogs this row lives in (R18). Composed
 * title by reference to `SkillRevisionFilesSheet`'s path row.
 */
export function SkillCredentialSlotRow({
  slot,
  type,
  description,
  status,
  summary,
  facts,
  action,
}: SkillCredentialSlotRowProps) {
  // Filtered here rather than left to `RowInfo`: `ListRow` draws the flags
  // cluster whenever `flags` is set, and an element that renders nothing still
  // counts as set.
  const infoFacts = [description || null, ...(facts ?? [])].filter(
    (fact): fact is string => !!fact,
  )

  return (
    <ListRow
      status={status}
      title={
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="block truncate font-mono">{slot}</span>
          </TooltipTrigger>
          <TooltipContent side="top" className="max-w-xs break-all text-xs">
            {slot}
          </TooltipContent>
        </Tooltip>
      }
      meta={`${credentialTypeLabel(type)} · ${summary}`}
      flags={infoFacts.length > 0 ? <RowInfo facts={infoFacts} /> : undefined}
    >
      {action}
    </ListRow>
  )
}
