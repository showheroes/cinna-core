import { GraduationCap } from "lucide-react"

import type { SkillEntryPublic } from "@/client"
import { SkillContentFact } from "@/components/Agents/SkillContentFact"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { formatSkillSize } from "@/utils/skills"
import { SkillDeclaredCredentials } from "./SkillDeclaredCredentials"
import { SkillDocumentTabs } from "./SkillDocumentTabs"

interface SkillDetailDialogProps {
  agentId: string
  skill: SkillEntryPublic
  /**
   * What this skill belongs to, as the dialog's subtitle: "Part of the plugin
   * chrome-devtools-mcp". A skill opened from a plugin's detail dialog has to
   * say so, or a reader two dialogs deep loses where they are.
   */
  partOf: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

function Fact({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="shrink-0 text-xs text-muted-foreground">{label}</span>
      <span className="min-w-0 truncate text-sm">{value}</span>
    </div>
  )
}

/**
 * One skill out of a plugin that ships several — why it is flagged, its
 * credentials and facts in a **Details** tab, and its `SKILL.md`, rendered, in
 * a **SKILL.md** tab (`SkillDocumentTabs`).
 *
 * Opened from the plugin's `AddonDetailDialog`, which used to swap one
 * skill's source into its own body instead. That kept to "a dialog does not
 * open a dialog" (R8) but did not survive a plugin like chrome-devtools-mcp:
 * a dozen skill rows *plus* a document pane overflowed the viewport, and the
 * pane's own scroll fought the dialog's. One skill per dialog gives the
 * document a tab of its own; the R8 exception is deliberate and the subtitle
 * says which plugin the reader came from.
 */
export function SkillDetailDialog({
  agentId,
  skill,
  partOf,
  open,
  onOpenChange,
}: SkillDetailDialogProps) {
  const issue = skill.error ?? skill.warning ?? null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-x-hidden overflow-y-auto sm:max-w-2xl [&>*]:min-w-0">
        <DialogHeader>
          <DialogTitle className="flex min-w-0 items-center gap-2">
            <GraduationCap className="h-5 w-5 shrink-0" />
            <span className="truncate">{skill.name}</span>
          </DialogTitle>
          <DialogDescription>{partOf}</DialogDescription>
        </DialogHeader>

        <SkillDocumentTabs agentId={agentId} skill={skill}>
          {issue?.message && (
            <Alert variant={skill.error ? "destructive" : "default"}>
              <AlertDescription>{issue.message}</AlertDescription>
            </Alert>
          )}

          <SkillDeclaredCredentials
            credentials={skill.credentials ?? []}
            summary="Declared in SKILL.md"
          />

          <div className="space-y-1.5">
            {skill.description && (
              <p className="text-sm break-words text-muted-foreground">
                {skill.description}
              </p>
            )}
            {skill.path && <Fact label="Path" value={skill.path} />}
            <Fact label="Size" value={formatSkillSize(skill.size_bytes)} />
            <SkillContentFact agentId={agentId} skill={skill} />
            <Fact
              label="Invocation"
              value={
                skill.user_invocable
                  ? `From chat as /${skill.name}`
                  : "Model-invoked only"
              }
            />
            {skill.has_scripts && (
              <Fact label="Scripts" value="Ships scripts the agent can run" />
            )}
          </div>
        </SkillDocumentTabs>
      </DialogContent>
    </Dialog>
  )
}
