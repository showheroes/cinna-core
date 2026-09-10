import type { SkillCredentialRequirementPublic } from "@/client"
import { ListRowGroup } from "@/components/Common/ListRow"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { PROVIDED_BY_COPY, slotProvidedBy } from "@/utils/skillCredentials"
import { SkillCredentialSlotRow } from "./SkillCredentialSlotRow"

interface SkillRevisionCredentialsSheetProps {
  /** The shown revision's `required_credentials`. */
  requirements: SkillCredentialRequirementPublic[]
  /** How the shown revision is named, for the description line. */
  revisionLabel: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * "What does this skill need from me before I install it?" — the destination
 * of the Package card's Credentials fact (S4b).
 *
 * A Sheet off a fact, like the Content and Version facts beside it: a door
 * costs the card no height (§2 "A card under a document"). Skeleton by
 * reference to `SkillRevisionFilesSheet`. Read-only — what a slot resolves to
 * on a particular agent is the install dialog's question, not the catalog's.
 */
export function SkillRevisionCredentialsSheet({
  requirements,
  revisionLabel,
  open,
  onOpenChange,
}: SkillRevisionCredentialsSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Credentials</SheetTitle>
          <SheetDescription>
            What installing {revisionLabel} needs. The publisher's credentials
            are shared with you on install; you fill in the rest on the agent.
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <ListRowGroup>
            {requirements.map((requirement) => {
              const providedBy = slotProvidedBy(requirement.provided_by)
              const copy = PROVIDED_BY_COPY[providedBy]
              return (
                <SkillCredentialSlotRow
                  key={requirement.slot}
                  slot={requirement.slot}
                  type={requirement.type}
                  description={requirement.description}
                  summary={copy.short}
                  // The sentence adds something only for a template ("you add
                  // the secret"); for the other two it is the meta line again.
                  facts={[providedBy === "template" && copy.sentence]}
                />
              )
            })}
          </ListRowGroup>
        </div>
      </SheetContent>
    </Sheet>
  )
}
