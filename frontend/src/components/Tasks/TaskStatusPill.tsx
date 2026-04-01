import { cn } from "@/lib/utils"

interface TaskStatusPillProps {
  status: string
  className?: string
}

function getStatusConfig(status: string): { label: string; className: string } {
  switch (status) {
    case "new":
      return { label: "New", className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" }
    case "open":
      return { label: "Open", className: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" }
    case "refining":
      return { label: "Refining", className: "bg-purple-100 text-purple-700 dark:bg-purple-900/40 dark:text-purple-300" }
    case "in_progress":
    case "running":
      return { label: "In Progress", className: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" }
    case "blocked":
    case "pending_input":
      return { label: "Blocked", className: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" }
    case "completed":
      return { label: "Completed", className: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" }
    case "error":
      return { label: "Error", className: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" }
    case "cancelled":
      return { label: "Cancelled", className: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300" }
    case "archived":
      return { label: "Archived", className: "bg-muted text-muted-foreground" }
    default:
      return { label: status, className: "bg-muted text-muted-foreground" }
  }
}

export function TaskStatusPill({ status, className }: TaskStatusPillProps) {
  const { label, className: statusClassName } = getStatusConfig(status)

  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold",
        statusClassName,
        className
      )}
    >
      {label}
    </span>
  )
}
