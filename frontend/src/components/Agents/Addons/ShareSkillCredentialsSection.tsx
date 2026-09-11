import type { SkillPublishCredentialPreview } from "@/client"
import { SkillCredentialSlotRow } from "@/components/Catalog/SkillCredentialSlotRow"
import { ListRowGroup } from "@/components/Common/ListRow"
import { NewTabIconLink } from "@/components/Common/NewTabIconLink"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import {
  PROVIDED_BY_PUBLISHER_COPY,
  producerAgentFact,
  publishOpenLabel,
  publishReasonSentence,
  slotProvidedBy,
} from "@/utils/skillCredentials"

interface ShareSkillCredentialsSectionProps {
  /** Slots the skill's SKILL.md declares — sizes the loading skeleton. */
  declarationCount: number
  isLoading: boolean
  /** The publish preview's per-slot resolution, once it has landed. */
  items: SkillPublishCredentialPreview[] | undefined
}

/**
 * "Before I publish, show me what installers will get for each credential this
 * skill needs, and why" — S1, placed by `ShareSkillDialog` between Visibility
 * and Advanced.
 *
 * Read-only, and in the **publisher's** words (`PROVIDED_BY_PUBLISHER_COPY`):
 * the reader is the publisher, so "From the publisher" would be the wrong
 * voice. The one control per row opens the publisher's matched credential in a
 * **new tab**, so the drafted release notes stay put; the preview query
 * refetches on window focus, so coming back re-resolves the rows. The host
 * hides this block when the preview failed — its own alert is the same query.
 */
export function ShareSkillCredentialsSection({
  declarationCount,
  isLoading,
  items,
}: ShareSkillCredentialsSectionProps) {
  if (!isLoading && (items?.length ?? 0) === 0) return null

  return (
    <div className="space-y-1.5">
      <Label>Credentials</Label>
      {isLoading || !items ? (
        Array.from({ length: declarationCount }, (_, index) => (
          <Skeleton key={index} className="h-[44px] w-full" />
        ))
      ) : (
        <ListRowGroup>
          {items.map((item) => (
            <PublishCredentialRow key={item.slot} item={item} />
          ))}
        </ListRowGroup>
      )}
      <p className="text-xs text-muted-foreground">
        Installers receive a credential only if you own it and its sharing is
        on; otherwise they bring their own.
      </p>
    </div>
  )
}

function PublishCredentialRow({
  item,
}: {
  item: SkillPublishCredentialPreview
}) {
  const providedBy =
    PROVIDED_BY_PUBLISHER_COPY[slotProvidedBy(item.provided_by)]

  return (
    <SkillCredentialSlotRow
      slot={item.slot}
      type={item.type}
      description={item.description}
      summary={providedBy.short}
      facts={[
        item.credential_name && `Matched ${item.credential_name}`,
        producerAgentFact(item.producer_agent_name),
        item.reason && publishReasonSentence(item.reason, item.credential_name),
      ]}
      action={
        item.credential_id ? (
          <NewTabIconLink
            label={publishOpenLabel(item.reason, item.credential_name)}
            linkOptions={{
              to: "/credential/$credentialId",
              params: { credentialId: item.credential_id },
            }}
          />
        ) : undefined
      }
    />
  )
}
