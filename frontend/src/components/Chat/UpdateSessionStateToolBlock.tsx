import { MessageCircleQuestion, Info } from "lucide-react"
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip"

interface UpdateSessionStateToolBlockProps {
  state: string
  summary?: string
}

export function UpdateSessionStateToolBlock({ state, summary }: UpdateSessionStateToolBlockProps) {
  if (state === "needs_input") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="flex items-start gap-2 text-sm bg-slate-100 dark:bg-slate-800 border border-border rounded px-3 py-2 cursor-default">
            <MessageCircleQuestion className="h-4 w-4 text-amber-500 mt-0.5 flex-shrink-0" />
            <span className="text-foreground/90">Requesting feedback...</span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs">
          {summary || "Waiting for user input"}
        </TooltipContent>
      </Tooltip>
    )
  }

  return (
    <div className="flex items-start gap-2 text-sm bg-slate-100 dark:bg-slate-800 border border-border rounded px-3 py-2">
      <Info className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
      <div className="flex-1 min-w-0">
        <span className="text-foreground/90">
          State:{" "}
          <code className="font-mono bg-slate-200 dark:bg-slate-700 px-1.5 py-0.5 rounded text-xs">
            {state}
          </code>
        </span>
        {summary && (
          <p className="text-xs text-muted-foreground mt-1">{summary}</p>
        )}
      </div>
    </div>
  )
}
