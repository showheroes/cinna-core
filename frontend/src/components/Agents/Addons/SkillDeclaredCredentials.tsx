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
 * Read-only and unjudged here: the server checks every declared slot on the
 * row (`credential_issues`), and a row that carries issues shows its own issue
 * list instead. A plugin's single skill (`SkillDetailDialog`) states what it
 * declares; the plugin row's issues live in `AddonDetailDialog`.
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
