import { cn } from "@/lib/utils"

interface TaskPriorityBadgeProps {
  priority: string
  className?: string
}

function getPriorityConfig(priority: string): { label: string; className: string } | null {
  switch (priority) {
    case "low":
      return {
        label: "Low",
        className: "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400 border border-gray-200 dark:border-gray-700",
      }
    case "normal":
      return null // No badge for normal priority
    case "high":
      return {
        label: "High",
        className: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300 border border-orange-200 dark:border-orange-800",
      }
    case "urgent":
      return {
        label: "Urgent",
        className: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300 border border-red-200 dark:border-red-800",
      }
    default:
      return null
  }
}

export function TaskPriorityBadge({ priority, className }: TaskPriorityBadgeProps) {
  const config = getPriorityConfig(priority)

  if (!config) return null

  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium",
        config.className,
        className
      )}
    >
      {config.label}
    </span>
  )
}
