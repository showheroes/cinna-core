import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
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

import { TasksService } from "@/client"
import { cn } from "@/lib/utils"
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover"

interface SubtaskProgressChipProps {
  total: number
  completed: number
  taskId: string
  className?: string
}

const statusIcons: Record<string, React.ReactNode> = {
  new: <Sparkles className="h-3 w-3 text-gray-500" />,
  refining: <Edit className="h-3 w-3 text-purple-500" />,
  open: <Circle className="h-3 w-3 text-gray-500" />,
  in_progress: <Play className="h-3 w-3 text-blue-500" />,
  running: <Play className="h-3 w-3 text-blue-500" />,
  blocked: <Clock className="h-3 w-3 text-amber-500" />,
  pending_input: <Clock className="h-3 w-3 text-amber-500" />,
  completed: <CheckCircle2 className="h-3 w-3 text-green-500" />,
  error: <AlertCircle className="h-3 w-3 text-red-500" />,
  cancelled: <Ban className="h-3 w-3 text-red-500" />,
  archived: <Archive className="h-3 w-3 text-gray-400" />,
}

function formatRelativeDate(dateStr: string) {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  if (diffMins < 1) return "just now"
  if (diffMins < 60) return `${diffMins}m ago`
  const diffHours = Math.floor(diffMins / 60)
  if (diffHours < 24) return `${diffHours}h ago`
  const diffDays = Math.floor(diffHours / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export function SubtaskProgressChip({ total, completed, taskId, className }: SubtaskProgressChipProps) {
  if (total <= 0) return null

  const percentage = total > 0 ? Math.round((completed / total) * 100) : 0
  const allDone = completed >= total

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={(e) => e.stopPropagation()}
          className={cn(
            "inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded border text-xs cursor-pointer hover:opacity-80 transition-opacity",
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
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-80 p-0"
        align="end"
        onClick={(e) => e.stopPropagation()}
      >
        <SubtaskList taskId={taskId} />
      </PopoverContent>
    </Popover>
  )
}

function SubtaskList({ taskId }: { taskId: string }) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ["subtasks", taskId],
    queryFn: () => TasksService.listSubtasks({ id: taskId }),
  })

  const subtasks = data?.data ?? []

  if (isLoading) {
    return (
      <div className="p-3 text-xs text-muted-foreground text-center">
        Loading subtasks...
      </div>
    )
  }

  if (subtasks.length === 0) {
    return (
      <div className="p-3 text-xs text-muted-foreground text-center">
        No subtasks
      </div>
    )
  }

  return (
    <div className="max-h-64 overflow-y-auto divide-y">
      {subtasks.map((st) => (
        <button
          key={st.id}
          type="button"
          onClick={() =>
            navigate({ to: "/task/$taskId", params: { taskId: st.short_code || st.id } })
          }
          className="w-full flex items-start gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
        >
          <span className="mt-0.5 shrink-0">
            {statusIcons[st.status] ?? <Circle className="h-3 w-3 text-gray-500" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              {st.short_code && (
                <span className="text-[10px] font-mono text-muted-foreground shrink-0">
                  {st.short_code}
                </span>
              )}
              <span className="text-xs font-medium truncate">
                {st.title || st.current_description}
              </span>
            </div>
            <span
              className="text-[10px] text-muted-foreground"
              title={new Date(st.updated_at).toLocaleString()}
            >
              {formatRelativeDate(st.updated_at)}
            </span>
          </div>
        </button>
      ))}
    </div>
  )
}
