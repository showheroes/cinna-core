import { useNavigate } from "@tanstack/react-router"
import { cn } from "@/lib/utils"

interface TaskShortCodeBadgeProps {
  shortCode: string
  status?: string
  onClick?: () => void
  className?: string
  /** When false, renders a plain non-interactive span. Use on pages that already
   *  display the task being referenced (e.g. the task detail header) to avoid
   *  a same-page navigation no-op. Defaults to true. */
  clickable?: boolean
}

function getStatusColorClass(status?: string): string {
  switch (status) {
    case "in_progress":
    case "running":
      return "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300 border-blue-200 dark:border-blue-800"
    case "completed":
      return "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300 border-green-200 dark:border-green-800"
    case "blocked":
    case "pending_input":
      return "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300 border-amber-200 dark:border-amber-800"
    case "error":
    case "cancelled":
      return "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300 border-red-200 dark:border-red-800"
    case "new":
    case "open":
    case "refining":
    default:
      return "bg-muted text-muted-foreground border-border"
  }
}

export function TaskShortCodeBadge({
  shortCode,
  status,
  onClick,
  className,
  clickable = true,
}: TaskShortCodeBadgeProps) {
  const navigate = useNavigate()

  const sharedClassName = cn(
    "inline-flex items-center px-1.5 py-0.5 rounded border text-xs font-mono font-medium",
    getStatusColorClass(status),
    className
  )

  if (!clickable) {
    return <span className={sharedClassName}>{shortCode}</span>
  }

  const handleClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    if (onClick) {
      onClick()
    } else {
      navigate({ to: "/tasks/$shortCode", params: { shortCode } })
    }
  }

  return (
    <button
      onClick={handleClick}
      className={cn(sharedClassName, "transition-opacity hover:opacity-80")}
    >
      {shortCode}
    </button>
  )
}
