import type { CredentialBundleUsage } from "@/client"
import { ListRowGroup } from "@/components/Common/ListRow"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { BundleUsageRow } from "./CredentialUsageRows"

interface CredentialBundleUsagesSheetProps {
  /** Every bundle that ships this credential as a publisher credential. */
  usages: CredentialBundleUsage[]
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * The "Show all (N)" destination for the Sharing card's "Used in Bundles"
 * list (S6c), by reference to `Catalog/AllSkillRevisionsSheet`.
 *
 * A Sheet rather than a route (P5's route-vs-Sheet test): the list needs no
 * search, sort or pagination, and a usage has no lifecycle here — its one
 * control opens the bundle in a new tab.
 */
export function CredentialBundleUsagesSheet({
  usages,
  open,
  onOpenChange,
}: CredentialBundleUsagesSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>Used in bundles</SheetTitle>
          <SheetDescription>
            {usages.length} bundle{usages.length === 1 ? "" : "s"} that ship
            this credential as a fully shared publisher credential
          </SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <ListRowGroup>
            {usages.map((usage) => (
              <BundleUsageRow key={usage.bundle_uuid} usage={usage} />
            ))}
          </ListRowGroup>
        </div>
      </SheetContent>
    </Sheet>
  )
}
