import { FileText, Info } from "lucide-react"
import type { ReactNode } from "react"

import type { SkillEntryPublic } from "@/client"
import { SkillContentBody } from "@/components/Agents/SkillContentBody"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"

interface SkillDocumentTabsProps {
  agentId: string
  skill: SkillEntryPublic
  /** The dialog's flags, credentials and facts — everything but the document. */
  children: ReactNode
}

/**
 * The segmented control §2 "Page toolbar" names for section navigation: the
 * current tab in `--primary`, never shadcn's raised `bg-background` tile, which
 * on the dark skin is darker than its own track and reads as a hole. The
 * `dark:` overrides are needed because the primitive sets its own `dark:`
 * active background and text colour, which would otherwise win there — the
 * hover colour included, which is why it is restated under `dark:` too.
 */

/**
 * A tab panel is a Tab stop in Radix, and the primitive's `outline-none` would
 * leave it with no visible focus at all.
 */
const PANEL_FOCUS_CLASS =
  "rounded-md focus-visible:ring-[3px] focus-visible:ring-ring/50"
const TRIGGER_CLASS =
  "h-auto flex-none rounded-md px-3 py-1.5 text-muted-foreground dark:text-muted-foreground data-[state=inactive]:hover:text-foreground dark:data-[state=inactive]:hover:text-foreground data-[state=inactive]:hover:bg-none data-[state=active]:bg-primary data-[state=active]:text-primary-foreground data-[state=active]:shadow-xs dark:data-[state=active]:border-transparent dark:data-[state=active]:bg-primary dark:data-[state=active]:text-primary-foreground"

/**
 * A skill's detail dialog body as two tabs at the top: **Details**, then
 * **SKILL.md**.
 *
 * The dialog used to stack the facts and the rendered `SKILL.md` in one
 * scroll, so every open was a dozen fact lines over a page of prose, and the
 * facts had to be scrolled back to. The catalog's package route splits the
 * same two things into two cards side by side; a dialog has no second column,
 * so here they are two tabs.
 *
 * Radix unmounts the inactive tab, and that is load-bearing: the `SKILL.md`
 * read goes through the container and wakes a suspended agent, so it happens
 * when the reader asks for the document rather than on every open. The Content
 * fact in Details is read host-side and never wakes anything.
 *
 * Shared by `AddonDetailDialog` (a row that is one skill) and
 * `SkillDetailDialog` (one skill of a plugin).
 */
export function SkillDocumentTabs({
  agentId,
  skill,
  children,
}: SkillDocumentTabsProps) {
  return (
    <Tabs defaultValue="details" className="min-w-0 gap-4">
      <TabsList className="h-auto gap-1 rounded-lg border bg-muted/50 p-1">
        <TabsTrigger value="details" className={TRIGGER_CLASS}>
          <Info className="h-3.5 w-3.5" />
          Details
        </TabsTrigger>
        <TabsTrigger value="skill-md" className={TRIGGER_CLASS}>
          <FileText className="h-3.5 w-3.5" />
          SKILL.md
        </TabsTrigger>
      </TabsList>
      {/* The dialog body's own spacing and shrink rule, restated one level
          down: `DialogContent`'s `gap-4` and `[&>*]:min-w-0` reach only its
          direct children, which is now the `Tabs` root. */}
      <TabsContent
        value="details"
        className={`flex min-w-0 flex-col gap-4 [&>*]:min-w-0 ${PANEL_FOCUS_CLASS}`}
      >
        {children}
      </TabsContent>
      <TabsContent value="skill-md" className={`min-w-0 ${PANEL_FOCUS_CLASS}`}>
        <SkillContentBody agentId={agentId} skill={skill} />
      </TabsContent>
    </Tabs>
  )
}
