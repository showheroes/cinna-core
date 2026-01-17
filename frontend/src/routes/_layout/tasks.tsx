import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useState } from "react"
import { Plus, MessageSquare, Play } from "lucide-react"

import { TasksService, AgentsService } from "@/client"
import type { InputTaskPublicExtended } from "@/client"
import PendingItems from "@/components/Pending/PendingItems"
import { usePageHeader } from "@/routes/_layout"
import { TaskStatusBadge } from "@/components/Tasks/TaskStatusBadge"
import { CreateTaskDialog } from "@/components/Tasks/CreateTaskDialog"
import { RelativeTime } from "@/components/Common/RelativeTime"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import useWorkspace from "@/hooks/useWorkspace"
import { getColorPreset } from "@/utils/colorPresets"

export const Route = createFileRoute("/_layout/tasks")({
  component: TasksList,
})

type StatusFilter = "active" | "completed" | "archived" | "all"

function TasksList() {
  const { setHeaderContent } = usePageHeader()
  const navigate = useNavigate()
  const { activeWorkspaceId } = useWorkspace()
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("active")
  const [createDialogOpen, setCreateDialogOpen] = useState(false)

  const {
    data: tasksData,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["tasks", statusFilter, activeWorkspaceId],
    queryFn: ({ queryKey }) => {
      const [, status, workspaceId] = queryKey
      return TasksService.listTasks({
        status: status as string,
        userWorkspaceId: workspaceId ?? "",
      })
    },
  })

  const { data: agentsData } = useQuery({
    queryKey: ["agents", activeWorkspaceId],
    queryFn: ({ queryKey }) => {
      const [, workspaceId] = queryKey
      return AgentsService.readAgents({
        skip: 0,
        limit: 100,
        userWorkspaceId: workspaceId ?? "",
      })
    },
  })

  useEffect(() => {
    setHeaderContent(
      <div className="flex items-center justify-between w-full gap-4">
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">Tasks</h1>
          <p className="text-xs text-muted-foreground">
            Manage and refine your incoming tasks
          </p>
        </div>
        <Button onClick={() => setCreateDialogOpen(true)} size="sm">
          <Plus className="h-4 w-4 mr-2" />
          New Task
        </Button>
      </div>
    )
    return () => setHeaderContent(null)
  }, [setHeaderContent])

  const handleTaskClick = (task: InputTaskPublicExtended) => {
    navigate({
      to: "/task/$taskId",
      params: { taskId: task.id },
    })
  }

  const handleGoToSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    navigate({
      to: "/session/$sessionId",
      params: { sessionId },
      search: { initialMessage: undefined, fileIds: undefined },
    })
  }

  const handleCreated = (taskId: string) => {
    navigate({
      to: "/task/$taskId",
      params: { taskId },
    })
  }

  // Get agent color preset by ID
  const getAgentColorPreset = (agentId: string | null | undefined) => {
    if (!agentId || !agentsData?.data) return null
    const agent = agentsData.data.find((a) => a.id === agentId)
    return agent ? getColorPreset(agent.ui_color_preset) : null
  }

  if (isLoading) {
    return <PendingItems />
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive">Error loading tasks</p>
      </div>
    )
  }

  const tasks = tasksData?.data || []

  return (
    <div className="p-6 md:p-8 overflow-y-auto h-full" key={activeWorkspaceId ?? "default"}>
      <div className="mx-auto max-w-7xl">
        <div className="flex gap-6">
          {/* Filters sidebar */}
          <div className="w-48 flex-shrink-0">
            <div className="sticky top-6 space-y-4">
              <div className="space-y-2">
                {(["active", "completed", "archived", "all"] as StatusFilter[]).map(
                  (filter) => (
                    <button
                      key={filter}
                      onClick={() => setStatusFilter(filter)}
                      className={cn(
                        "w-full text-left px-3 py-2 text-sm rounded-md transition-all capitalize",
                        statusFilter === filter
                          ? "ring-2 ring-primary text-primary font-medium"
                          : "hover:bg-muted"
                      )}
                    >
                      {filter}
                    </button>
                  )
                )}
              </div>
            </div>
          </div>

          {/* Tasks list */}
          <div className="flex-1">
            {tasks.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed rounded-lg">
                <p className="text-muted-foreground mb-4">No tasks yet</p>
                <Button onClick={() => setCreateDialogOpen(true)}>
                  <Plus className="h-4 w-4 mr-2" />
                  Create your first task
                </Button>
              </div>
            ) : (
              <div className="space-y-3">
                {tasks.map((task) => {
                  const colorPreset = getAgentColorPreset(task.selected_agent_id)

                  return (
                    <div
                      key={task.id}
                      onClick={() => handleTaskClick(task)}
                      className={cn(
                        "p-4 rounded-lg border bg-card cursor-pointer transition-all hover:bg-muted/50"
                      )}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1 min-w-0 space-y-2">
                          <div className="flex items-center gap-2 flex-wrap">
                            <TaskStatusBadge status={task.status} />
                            {task.agent_name && colorPreset && (
                              <span
                                className={cn(
                                  "inline-flex items-center px-2 py-0.5 rounded text-xs font-medium",
                                  colorPreset.badgeBg,
                                  colorPreset.badgeText
                                )}
                              >
                                {task.agent_name}
                              </span>
                            )}
                          </div>
                          <p className="text-sm line-clamp-2">
                            {task.current_description}
                          </p>
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <RelativeTime timestamp={task.created_at} />
                            {task.refinement_history &&
                              task.refinement_history.length > 0 && (
                                <span className="flex items-center gap-1">
                                  <MessageSquare className="h-3 w-3" />
                                  {task.refinement_history.length} refinements
                                </span>
                              )}
                          </div>
                        </div>

                        {task.session_id && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={(e) => handleGoToSession(e, task.session_id!)}
                          >
                            <Play className="h-4 w-4 mr-1" />
                            Go to Session
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>

      <CreateTaskDialog
        open={createDialogOpen}
        onOpenChange={setCreateDialogOpen}
        onCreated={handleCreated}
      />
    </div>
  )
}
