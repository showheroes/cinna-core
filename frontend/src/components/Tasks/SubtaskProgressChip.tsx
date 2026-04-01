import { cn } from "@/lib/utils"

interface SubtaskProgressChipProps {
  total: number
  completed: number
  className?: string
}

export function SubtaskProgressChip({ total, completed, className }: SubtaskProgressChipProps) {
  if (total <= 0) return null

  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0
  const allDone = completed >= total

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded border text-xs",
        allDone
          ? "bg-green-50 text-green-700 border-green-200 dark:bg-green-900/20 dark:text-green-400 dark:border-green-800"
          : "bg-muted text-muted-foreground border-border",
        className
      )}
    >
      <span className="font-medium tabular-nums">
        {completed}/{total}
      </span>
      <div className="w-10 h-1.5 bg-muted-foreground/20 rounded-full overflow-hidden">
        <div
          className={cn(
            "h-full rounded-full transition-all",
            allDone ? "bg-green-500" : "bg-primary"
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </span>
  )
}
