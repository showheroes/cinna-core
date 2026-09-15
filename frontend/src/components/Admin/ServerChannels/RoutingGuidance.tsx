import { Fragment, type ReactNode } from "react"

import { GUIDANCE_REPLY_HEADING, guidanceKindLead } from "./routingCopy"
import { type RoutingStage, resolveOptionNames } from "./routingStages"

/**
 * Guidance — the router answering the sender instead of routing — as the
 * tuning card shows it. Two pieces, both read-only:
 *
 * - `RoutingGuidanceReply`: the exact text a simulated sender would have been
 *   shown. Only `POST /admin/routing/simulate` carries it (`guidance_reply`);
 *   a stored trace does not, and nothing here reconstructs it from `stages`.
 * - `StageGuidanceLines`: the id-only stage facts (`options`,
 *   `guidance_options`) with names resolved from the decision's candidates.
 */

/**
 * `**bold**` → `<strong>`, everything else as text nodes. Never HTML: the
 * reply is Google Chat markdown, and the only markup it uses besides line
 * breaks, `- ` bullets and `1. ` numbers is the bold around a name (the
 * backend strips markup out of names and descriptions before composing).
 * Bullets and numbers already read as plain text under `whitespace-pre-wrap`.
 */
function renderBold(text: string): ReactNode[] {
  // With one capturing group, odd indices are the bold runs.
  return text.split(/\*\*([^*\n]+)\*\*/g).map((part, index) =>
    index % 2 === 1 ? (
      <strong key={index} className="font-semibold">
        {part}
      </strong>
    ) : (
      <Fragment key={index}>{part}</Fragment>
    ),
  )
}

export function RoutingGuidanceReply({
  reply,
}: {
  reply: string | null | undefined
}) {
  // Null (or empty) means the decision routed, parked, found nothing to say,
  // or guidance is off — there is no reply to show, so nothing is shown.
  if (!reply) return null
  return (
    <div className="space-y-1">
      <p className="text-xs font-medium text-muted-foreground">
        {GUIDANCE_REPLY_HEADING}
      </p>
      <p className="rounded bg-muted/50 px-2 py-1.5 text-xs whitespace-pre-wrap break-words">
        {renderBold(reply)}
      </p>
    </div>
  )
}

export function StageGuidanceLines({
  stage,
  names,
}: {
  stage: RoutingStage
  /** Candidate names by `ref_id`, across the whole decision. */
  names: Map<string, string>
}) {
  const tied = resolveOptionNames(stage.options, names)
  const listed = resolveOptionNames(stage.guidance_options, names)
  const kind = stage.guidance_kind

  // A clarifying question over exactly the classifier's tie says the same
  // thing twice; keep the line that says what the sender saw. Compared by id,
  // not by resolved name: two candidates can share a name.
  const refIds = (options: RoutingStage["options"]) =>
    (options ?? []).map((option) => option.ref_id ?? "").join("\n")
  const tiedIsAsked =
    kind === "clarify" &&
    refIds(stage.options) === refIds(stage.guidance_options)
  const showTied = tied.length > 0 && !tiedIsAsked

  if (!showTied && !kind) return null

  return (
    <div className="space-y-0.5">
      {showTied && (
        <p className="text-xs break-words">
          <span className="text-muted-foreground">Tied candidates:</span>{" "}
          {tied.join(", ")}
        </p>
      )}
      {kind && (
        <p className="text-xs break-words">
          <span className="text-muted-foreground">
            {guidanceKindLead(kind, listed.length > 0)}
            {listed.length > 0 && ":"}
          </span>
          {listed.length > 0 && ` ${listed.join(", ")}`}
        </p>
      )}
    </div>
  )
}
