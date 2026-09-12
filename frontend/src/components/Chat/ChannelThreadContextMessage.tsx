import { ChevronRight, MessagesSquare } from "lucide-react"

import type { MessagePublic } from "@/client"

function messageCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.max(0, Math.floor(value))
    : 0
}

/** The transcript is external message text, displayed literally and on demand. */
export function ChannelThreadContextMessage({
  message,
}: {
  message: MessagePublic
}) {
  const metadata = message.message_metadata
  const included = messageCount(metadata?.included_count)
  const omitted = messageCount(metadata?.omitted_count)
  const truncated = metadata?.truncated === true
  const degraded =
    typeof metadata?.degraded_reason === "string" &&
    metadata.degraded_reason.length > 0
  const summary = [
    "Thread context",
    `${included} ${included === 1 ? "message" : "messages"}`,
    ...(omitted > 0 ? [`${omitted} omitted`] : []),
    ...(truncated ? ["truncated"] : []),
    ...(degraded ? ["limited access"] : []),
  ].join(" · ")

  return (
    <div className="my-4 flex justify-center">
      <details className="group min-w-0 w-full max-w-2xl rounded-lg bg-muted/60 text-sm text-muted-foreground">
        <summary className="flex cursor-pointer list-none items-center gap-2 rounded-lg px-4 py-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring [&::-webkit-details-marker]:hidden">
          <MessagesSquare className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="min-w-0 flex-1 break-words">{summary}</span>
          <ChevronRight
            className="h-4 w-4 shrink-0 transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
        </summary>
        <div className="space-y-2 border-t border-border/50 px-4 py-3">
          {degraded && (
            <p className="break-words text-warning">
              Some earlier context could not be retrieved. The agent only sees
              the context shown here, together with messages already in this
              session.
            </p>
          )}
          {truncated && (
            <p className="break-words">
              Context was shortened to fit the reading limit. Quote the message
              you want the agent to consider if it is missing here.
            </p>
          )}
          <div className="max-h-80 overflow-y-auto pr-2 whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
            {message.content || "No earlier message text was available."}
          </div>
        </div>
      </details>
    </div>
  )
}
