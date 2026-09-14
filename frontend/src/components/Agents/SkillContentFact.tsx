import { useQuery } from "@tanstack/react-query"
import { Files } from "lucide-react"
import { useState } from "react"

import type { SkillEntryPublic } from "@/client"
import { AgentsService } from "@/client"
import { SkillRevisionFilesSheet } from "@/components/Catalog/SkillRevisionFilesSheet"
import { Skeleton } from "@/components/ui/skeleton"

interface SkillContentFactProps {
  agentId: string
  skill: SkillEntryPublic
}

/**
 * The Content fact for one skill folder in an agent's workspace — "4 files",
 * opening the list of them.
 *
 * The Package card's Content fact, pointed at the workspace instead of a
 * published snapshot: a skill is a folder, and a dialog showing `SKILL.md`
 * alone made one that carries `scripts/` and `references/` look exactly like
 * one that carries nothing. Same fact row, same Sheet, so the catalog and the
 * agent page answer "what does this skill ship" the same way. No download:
 * these are the agent's own files, not a published archive.
 *
 * Shared by `AddonDetailDialog` (a row that is one skill) and
 * `SkillDetailDialog` (one skill of a plugin), so the two cannot drift.
 */
export function SkillContentFact({ agentId, skill }: SkillContentFactProps) {
  const [filesOpen, setFilesOpen] = useState(false)
  const { data, isLoading, isError } = useQuery({
    // Under `["agent", agentId, "skills"]`, like the SKILL.md body: every path
    // that re-reads the skill index invalidates that prefix.
    queryKey: ["agent", agentId, "skills", skill.name, "files"],
    queryFn: () =>
      AgentsService.listAgentSkillFiles({ agentId, name: skill.name }),
  })

  const count = data?.count ?? 0
  const countLabel = `${count} file${count === 1 ? "" : "s"}`
  // The route resolves a name local-first, like the SKILL.md body's: on a
  // shadowed entry these are the *other* skill's files. `SkillContentBody`
  // says so under its path; this fact says whose folder it counted rather
  // than passing the number off as this entry's.
  const expectedPath = skill.path ?? `skills/${skill.name}`
  const isShadowedByAnother = !!data && data.path !== expectedPath
  const valueLabel = isShadowedByAnother
    ? `${countLabel} in ${data.path}`
    : countLabel

  return (
    <>
      <div className="flex items-baseline justify-between gap-3">
        <span className="shrink-0 text-xs text-muted-foreground">Content</span>
        {/* A failed read is a stated absence, not a vanished row; a failed
            background refetch keeps the count already in hand. */}
        {isError && !data ? (
          <span className="truncate text-sm text-muted-foreground">
            Unavailable
          </span>
        ) : isLoading || !data ? (
          <Skeleton className="h-4 w-20" />
        ) : (
          <button
            type="button"
            aria-haspopup="dialog"
            aria-label={
              isShadowedByAnother
                ? `${valueLabel}, the skill that shadows this one. Show every file`
                : `${countLabel}. Show every file`
            }
            onClick={() => setFilesOpen(true)}
            className={`flex min-w-0 items-center gap-1.5 rounded-sm text-sm underline-offset-4 outline-none hover:underline focus-visible:ring-[3px] focus-visible:ring-ring/50 ${isShadowedByAnother ? "text-warning" : ""}`}
          >
            <span className="truncate">{valueLabel}</span>
            <Files className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          </button>
        )}
      </div>

      <SkillRevisionFilesSheet
        files={data?.data ?? []}
        count={count}
        totalSizeBytes={data?.total_size_bytes ?? 0}
        truncated={data?.truncated ?? false}
        revisionLabel={null}
        open={filesOpen}
        onOpenChange={setFilesOpen}
      />
    </>
  )
}
