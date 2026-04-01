import { cn } from "@/lib/utils"
import {
  Sparkles,
  Edit,
  CheckCircle2,
  Play,
  Clock,
  AlertCircle,
  Archive,
  Circle,
  Ban,
} from "lucide-react"

type TaskStatus =
  | "new"
  | "refining"
  | "open"
  | "in_progress"
  | "blocked"
  | "completed"
  | "error"
  | "cancelled"
  | "archived"
  // Legacy statuses for backwards compatibility
  | "running"
  | "pending_input"

interface TaskStatusBadgeProps {
  status: TaskStatus | string
  className?: string
}

const statusConfig: Record<
  TaskStatus,
  { label: string; icon: React.ReactNode; className: string }
> = {
  new: {
    label: "New",
    icon: <Sparkles className="h-3 w-3" />,
    className: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400",
  },
  refining: {
    label: "Refining",
    icon: <Edit className="h-3 w-3" />,
    className: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  open: {
    label: "Open",
    icon: <Circle className="h-3 w-3" />,
    className: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400",
  },
  in_progress: {
    label: "In Progress",
    icon: <Play className="h-3 w-3" />,
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  blocked: {
    label: "Blocked",
    icon: <Clock className="h-3 w-3" />,
    className: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
  completed: {
    label: "Completed",
    icon: <CheckCircle2 className="h-3 w-3" />,
    className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  },
  error: {
    label: "Error",
    icon: <AlertCircle className="h-3 w-3" />,
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  cancelled: {
    label: "Cancelled",
    icon: <Ban className="h-3 w-3" />,
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  archived: {
    label: "Archived",
    icon: <Archive className="h-3 w-3" />,
    className: "bg-gray-100 text-gray-500 dark:bg-gray-900/30 dark:text-gray-500",
  },
  // Legacy statuses mapped to new equivalents
  running: {
    label: "In Progress",
    icon: <Play className="h-3 w-3" />,
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  pending_input: {
    label: "Blocked",
    icon: <Clock className="h-3 w-3" />,
    className: "bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400",
  },
}

export function TaskStatusBadge({ status, className }: TaskStatusBadgeProps) {
  const config = statusConfig[status as TaskStatus] || {
    label: status,
    icon: <Circle className="h-3 w-3" />,
    className: "bg-gray-100 text-gray-700",
  }

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium",
        config.className,
        className
      )}
    >
      {config.icon}
      {config.label}
    </span>
  )
}
