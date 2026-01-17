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
} from "lucide-react"

type TaskStatus =
  | "new"
  | "refining"
  | "ready"
  | "running"
  | "pending_input"
  | "completed"
  | "error"
  | "archived"

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
    className: "bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400",
  },
  refining: {
    label: "Refining",
    icon: <Edit className="h-3 w-3" />,
    className: "bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400",
  },
  ready: {
    label: "Ready",
    icon: <CheckCircle2 className="h-3 w-3" />,
    className: "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400",
  },
  running: {
    label: "Running",
    icon: <Play className="h-3 w-3" />,
    className: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
  },
  pending_input: {
    label: "Pending Input",
    icon: <Clock className="h-3 w-3" />,
    className: "bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400",
  },
  completed: {
    label: "Completed",
    icon: <CheckCircle2 className="h-3 w-3" />,
    className: "bg-slate-100 text-slate-700 dark:bg-slate-900/30 dark:text-slate-400",
  },
  error: {
    label: "Error",
    icon: <AlertCircle className="h-3 w-3" />,
    className: "bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400",
  },
  archived: {
    label: "Archived",
    icon: <Archive className="h-3 w-3" />,
    className: "bg-gray-100 text-gray-700 dark:bg-gray-900/30 dark:text-gray-400",
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
