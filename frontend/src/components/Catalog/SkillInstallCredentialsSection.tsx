import { useQuery } from "@tanstack/react-query"

import type { SkillCredentialProvisionPublic } from "@/client"
import { SkillsService } from "@/client"
import { ListRowGroup } from "@/components/Common/ListRow"
import { QueryErrorAlert } from "@/components/Common/QueryErrorAlert"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  PROVIDED_BY_COPY,
  type SlotPhase,
  slotOutcomeCopy,
  slotOutcomeStatus,
  slotOutcomeSummary,
  slotProvidedBy,
} from "@/utils/skillCredentials"
import { SkillCredentialSlotRow } from "./SkillCredentialSlotRow"

/** Where the agent sits in the preview's key — named beside the builder. */
const PREVIEW_KEY_AGENT_INDEX = 1

/** The install preview's cache key (plan §9.1). */
export function skillInstallPreviewKey(
  agentId: string,
  packageId: string,
  revisionNumber: number | null,
) {
  return [
    "skills-install-preview",
    agentId,
    packageId,
    revisionNumber ?? "latest",
  ] as const
}

/** The agent a preview key was built for. */
function previewKeyAgentId(queryKey: readonly unknown[]): unknown {
  return queryKey[PREVIEW_KEY_AGENT_INDEX]
}

interface SkillProvisionRowProps {
  item: SkillCredentialProvisionPublic
  phase: SlotPhase
}

/** One slot of an install, before it (preview) or after it (report). */
export function SkillProvisionRow({ item, phase }: SkillProvisionRowProps) {
  const copy = slotOutcomeCopy(item)
  return (
    <SkillCredentialSlotRow
      slot={item.slot}
      type={item.type}
      description={item.description}
      status={slotOutcomeStatus(item, phase)}
      summary={copy.short({
        slot: item.slot,
        credentialName: item.credential_name,
      })}
      facts={[PROVIDED_BY_COPY[slotProvidedBy(item.provided_by)].sentence]}
    />
  )
}

interface SkillInstallCredentialsSectionProps {
  /** The agent being installed into; empty while none is chosen. */
  agentId: string
  /** The package's UUID. */
  packageId: string
  /** `null` means the latest revision. */
  revisionNumber: number | null
}

/**
 * "If I add this skill to *this* agent, will it work right away, and what will
 * I fill in?" — S2 (Add skill to agent) and S3 (Add addon, step 2).
 *
 * One component for both hosts: it owns the query, the states and the copy,
 * and the dialogs only place it, so the two install entry points cannot drift.
 * Read-only by design (plan D7) — nothing leaves a Create form before its
 * submit, so the rows carry no action.
 *
 * Advisory: a failed preview never blocks the install button (plan §11).
 */
export function SkillInstallCredentialsSection({
  agentId,
  packageId,
  revisionNumber,
}: SkillInstallCredentialsSectionProps) {
  // The host already reads this package (revision picker), so this is a cache
  // hit. It tells how many slots the chosen revision declares, which sizes the
  // skeleton and keeps a skill that needs nothing from flashing one.
  const { data: pkg } = useQuery({
    queryKey: ["skills-catalog", "package", packageId],
    queryFn: () => SkillsService.getSkillPackage({ packageId }),
  })
  const revision =
    revisionNumber == null
      ? pkg?.latest_revision
      : pkg?.revisions?.find((rev) => rev.revision_number === revisionNumber)
  const requiredCount = revision?.required_credentials?.length ?? 0

  const preview = useQuery({
    queryKey: skillInstallPreviewKey(agentId, packageId, revisionNumber),
    queryFn: () =>
      SkillsService.previewAgentSkillInstall({
        agentId,
        packageId,
        revisionNumber,
      }),
    enabled: !!agentId,
    // Keep the rows while a revision change refetches, so the block does not
    // collapse — but only for the same agent: another agent's "Uses your …"
    // held on screen under a newly chosen agent would be a wrong answer.
    placeholderData: (previous, previousQuery) =>
      previousQuery && previewKeyAgentId(previousQuery.queryKey) === agentId
        ? previous
        : undefined,
  })

  if (!agentId) return null

  const items = preview.data?.credentials ?? []
  let body: React.ReactNode
  if (preview.data) {
    if (items.length === 0) return null
    body = (
      <>
        <ListRowGroup>
          {items.map((item) => (
            <SkillProvisionRow key={item.slot} item={item} phase="preview" />
          ))}
        </ListRowGroup>
        <p className="text-xs text-muted-foreground">
          {slotOutcomeSummary(items, "preview")}
        </p>
      </>
    )
  } else if (preview.isError) {
    // A skill known to need nothing has nothing to warn about.
    if (pkg && requiredCount === 0) return null
    body = (
      <QueryErrorAlert
        error={preview.error}
        fallback="Couldn't check this agent's credentials"
        onRetry={() => preview.refetch()}
        compact
      />
    )
  } else {
    if (requiredCount === 0) return null
    body = Array.from({ length: requiredCount }, (_, index) => (
      <Skeleton key={index} className="h-[44px] w-full" />
    ))
  }

  return (
    <div className="space-y-1.5">
      <Label>Credentials</Label>
      {body}
    </div>
  )
}
