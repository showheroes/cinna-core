import { useState, useCallback } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { Plus, Bot, Search, X, ClipboardList } from "lucide-react"

import { TasksService } from "@/client"
import type { InputTaskPublicExtended } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { TaskShortCodeBadge } from "@/components/Tasks/TaskShortCodeBadge"
import { TaskPriorityBadge } from "@/components/Tasks/TaskPriorityBadge"
import { SubtaskProgressChip } from "@/components/Tasks/SubtaskProgressChip"
import { CreateTaskDialog } from "@/components/Tasks/CreateTaskDialog"
import { cn } from "@/lib/utils"
import useWorkspace from "@/hooks/useWorkspace"
import { useMultiEventSubscription, EventTypes } from "@/hooks/useEventBus"

interface TaskBoardProps {
  teamId?: string
}

const INBOX_STATUSES = ["new", "refining"]
const BOARD_COLUMNS = [
  { key: "open", label: "Open" },
  { key: "in_progress", label: "In Progress" },
  { key: "blocked", label: "Blocked" },
  { key: "completed", label: "Completed" },
] as const

function TaskCard({ task }: { task: InputTaskPublicExtended }) {
  const navigate = useNavigate()

  const handleClick = () => {
    if (task.short_code) {
      navigate({ to: "/tasks/$shortCode", params: { shortCode: task.short_code } })
    } else {
      navigate({ to: "/task/$taskId", params: { taskId: task.id } })
    }
  }

  const displayTitle = task.title || task.current_description

  return (
    <div
      onClick={handleClick}
      className="group p-3 rounded-lg border bg-card cursor-pointer transition-all hover:shadow-sm hover:border-border/80 space-y-2"
    >
      {/* Short code + priority row */}
      <div className="flex items-center justify-between gap-2">
        {task.short_code ? (
          <TaskShortCodeBadge
            shortCode={task.short_code}
            status={task.status}
            onClick={handleClick}
          />
        ) : (
          <span className="text-xs text-muted-foreground font-mono">—</span>
        )}
        <TaskPriorityBadge priority={task.priority || "normal"} />
      </div>

      {/* Title */}
      <p className="text-sm font-medium line-clamp-2 leading-snug">
        {displayTitle}
      </p>

      {/* Footer row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          {task.agent_name ? (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground truncate">
              <Bot className="h-3 w-3 shrink-0" />
              <span className="truncate">{task.agent_name}</span>
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">Unassigned</span>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {(task.subtask_count ?? 0) > 0 && (
            <SubtaskProgressChip
              total={task.subtask_count ?? 0}
              completed={task.subtask_completed_count ?? 0}
            />
          )}
          {task.team_name && (
            <span className="text-xs text-muted-foreground bg-muted px-1.5 py-0.5 rounded truncate max-w-[80px]">
              {task.team_name}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}

function TaskCardSkeleton() {
  return (
    <div className="p-3 rounded-lg border bg-card space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-12" />
      </div>
      <Skeleton className="h-4 w-full" />
      <Skeleton className="h-3 w-3/4" />
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-10" />
      </div>
    </div>
  )
}

function BoardColumnSkeleton({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center justify-between px-1">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <Skeleton className="h-3 w-4" />
      </div>
      <div className="flex flex-col gap-2">
        <TaskCardSkeleton />
        <TaskCardSkeleton />
        <TaskCardSkeleton />
      </div>
    </div>
  )
}

function BoardColumn({
  label,
  tasks,
}: {
  label: string
  tasks: InputTaskPublicExtended[]
}) {
  return (
    <div className="flex flex-col gap-2 min-w-0">
      <div className="flex items-center justify-between px-1">
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
        <span className="text-xs text-muted-foreground tabular-nums">{tasks.length}</span>
      </div>
      <div className="flex flex-col gap-2 min-h-[120px]">
        {tasks.map((task) => (
          <TaskCard key={task.id} task={task} />
        ))}
        {tasks.length === 0 && (
          <div className="rounded-lg border border-dashed p-4 text-center text-xs text-muted-foreground">
            No tasks
          </div>
        )}
      </div>
    </div>
  )
}

export function TaskBoard({ teamId }: TaskBoardProps) {
  const { activeWorkspaceId } = useWorkspace()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const [priorityFilter, setPriorityFilter] = useState<string>("all")

  const { data, isLoading } = useQuery({
    queryKey: ["tasks", "board", activeWorkspaceId, teamId],
    queryFn: ({ queryKey }) => {
      const [, , workspaceId, tid] = queryKey
      return TasksService.listTasks({
        rootOnly: true,
        userWorkspaceId: (workspaceId as string) ?? "",
        teamId: (tid as string) || undefined,
        limit: 200,
      })
    },
  })

  // Subscribe to task real-time events and invalidate board query
  const handleTaskBoardEvent = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["tasks", "board"] })
  }, [queryClient])

  useMultiEventSubscription(
    [
      EventTypes.TASK_STATUS_CHANGED,
      EventTypes.TASK_SUBTASK_CREATED,
      EventTypes.SUBTASK_COMPLETED,
    ],
    handleTaskBoardEvent,
  )

  const handleCreated = (taskId: string) => {
    navigate({ to: "/task/$taskId", params: { taskId } })
  }

  const allTasks = data?.data ?? []

  // Apply filters
  const filteredTasks = allTasks.filter((task) => {
    if (priorityFilter !== "all" && task.priority !== priorityFilter) return false
    if (searchQuery) {
      const query = searchQuery.toLowerCase()
      const titleMatch = (task.title || task.current_description || "").toLowerCase().includes(query)
      const codeMatch = (task.short_code || "").toLowerCase().includes(query)
      if (!titleMatch && !codeMatch) return false
    }
    return true
  })

  const inboxTasks = filteredTasks.filter((t) => INBOX_STATUSES.includes(t.status))
  const tasksByStatus = Object.fromEntries(
    BOARD_COLUMNS.map((col) => [
      col.key,
      filteredTasks.filter((t) => t.status === col.key),
    ])
  )

  const clearFilters = () => {
    setSearchQuery("")
    setPriorityFilter("all")
  }

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[160px] max-w-xs">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
          <Input
            placeholder="Search tasks..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-8 h-8 text-sm"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
        <Select value={priorityFilter} onValueChange={setPriorityFilter}>
          <SelectTrigger className="h-8 w-[120px] text-sm">
            <SelectValue placeholder="Priority" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All priorities</SelectItem>
            <SelectItem value="urgent">Urgent</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="normal">Normal</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto">
          <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            New Task
          </Button>
        </div>
      </div>

      {/* Loading skeleton */}
      {isLoading ? (
        <div className={cn("grid gap-4 flex-1", "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4")}>
          {BOARD_COLUMNS.map((col) => (
            <BoardColumnSkeleton key={col.key} label={col.label} />
          ))}
        </div>
      ) : allTasks.length === 0 ? (
        /* Global empty state — no tasks at all */
        <div className="flex flex-col items-center justify-center py-16 gap-4 text-center flex-1">
          <div className="rounded-full bg-muted p-4">
            <ClipboardList className="h-8 w-8 text-muted-foreground" />
          </div>
          <div className="space-y-1">
            <p className="text-base font-medium">No tasks yet</p>
            <p className="text-sm text-muted-foreground">
              Create your first task to get started
            </p>
          </div>
          <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            Create Task
          </Button>
        </div>
      ) : filteredTasks.length === 0 ? (
        /* Filtered empty state */
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-center flex-1">
          <p className="text-sm font-medium">No tasks match your filters</p>
          <Button variant="outline" size="sm" onClick={clearFilters}>
            Clear filters
          </Button>
        </div>
      ) : (
        <>
          {/* Inbox section (new + refining tasks) */}
          {inboxTasks.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  Inbox
                </span>
                <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded-full tabular-nums">
                  {inboxTasks.length}
                </span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
                {inboxTasks.map((task) => (
                  <TaskCard key={task.id} task={task} />
                ))}
              </div>
            </div>
          )}

          {/* Kanban board */}
          <div className={cn("grid gap-4 flex-1", "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4")}>
            {BOARD_COLUMNS.map((col) => (
              <BoardColumn
                key={col.key}
                label={col.label}
                tasks={tasksByStatus[col.key] ?? []}
              />
            ))}
          </div>
        </>
      )}

      <CreateTaskDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={handleCreated}
        defaultTeamId={teamId}
      />
    </div>
  )
}
