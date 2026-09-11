import type { ReactNode } from "react"

import { ListRowGroup } from "@/components/Common/ListRow"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"

interface CredentialUsagesSheetProps {
  /** Sentence case, naming the source: "Used in bundles" / "Used in skills". */
  title: string
  /** How many, and what they have in common. */
  description: ReactNode
  open: boolean
  onOpenChange: (open: boolean) => void
  /** The rows — `BundleUsageRow`s or `SkillUsageRow`s. */
  children: ReactNode
}

/**
 * The "Show all (N)" destination for the Sharing card's usage lists (S6c), by
 * reference to `Catalog/AllSkillRevisionsSheet`.
 *
 * A Sheet rather than a route (P5's route-vs-Sheet test): the list needs no
 * search, sort or pagination, and a usage has no lifecycle here — its one
 * control opens the package in a new tab.
 *
 * One shell for both sources, so the bundles a credential backs and the skills
 * it backs cannot read differently (§2 "The same entity, before and after");
 * the caller supplies the rows, which are what actually differ.
 */
export function CredentialUsagesSheet({
  title,
  description,
  open,
  onOpenChange,
  children,
}: CredentialUsagesSheetProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-lg">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>{description}</SheetDescription>
        </SheetHeader>
        <div className="flex-1 overflow-y-auto px-4 pb-4">
          <ListRowGroup>{children}</ListRowGroup>
        </div>
      </SheetContent>
    </Sheet>
  )
}
