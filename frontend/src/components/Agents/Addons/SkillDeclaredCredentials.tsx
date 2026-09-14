import type { SkillCredentialDeclarationPublic } from "@/client"
import { SkillCredentialSlotRow } from "@/components/Catalog/SkillCredentialSlotRow"
import { ListRowGroup } from "@/components/Common/ListRow"
import { Label } from "@/components/ui/label"

interface SkillDeclaredCredentialsProps {
  /** The slots the skill's `SKILL.md` declares. Renders nothing when empty. */
  credentials: SkillCredentialDeclarationPublic[]
  /** This surface's answer for every slot — "Linked to this agent", … */
  summary: string
}

/**
 * The credentials one skill needs, as the slot rows the install dialogs and
 * the package card's Sheet already use — the destination of the row's key
 * flag in Details.
 *
 * Read-only and unjudged: only a catalog install's slots are checked
 * server-side (`credential_issues`), so for every other source the list states
 * what the skill declares rather than colouring a dot it cannot back up. A
 * catalog row that *does* carry issues keeps its own issue list instead.
 *
 * Shared by `AddonDetailDialog` (a row that is one skill) and
 * `SkillDetailDialog` (one skill of a plugin).
 */
export function SkillDeclaredCredentials({
  credentials,
  summary,
}: SkillDeclaredCredentialsProps) {
  if (credentials.length === 0) return null
  return (
    <div className="space-y-1.5">
      <Label>Credentials</Label>
      <ListRowGroup>
        {credentials.map((credential) => (
          <SkillCredentialSlotRow
            key={`${credential.type}:${credential.slot}`}
            slot={credential.slot}
            type={credential.type}
            description={credential.description}
            summary={summary}
          />
        ))}
      </ListRowGroup>
    </div>
  )
}
