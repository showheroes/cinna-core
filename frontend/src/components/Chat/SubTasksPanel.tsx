import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { OpenAPI, TasksService } from "@/client"
import { CheckCircle2, HelpCircle, AlertTriangle, Loader2, Play, ExternalLink } from "lucide-react"
import { Button } from "@/components/ui/button"
import { useMultiEventSubscription, EventTypes } from "@/hooks/useEventBus"
import { RelativeTime } from "@/components/Common/RelativeTime"

interface SubTasksPanelProps {
  sessionId: string
  onClose: () => void
}

interface SubTaskData {
  id: string
  original_message: string
  current_description: string
  status: string
  selected_agent_id: string | null
  agent_name: string | null
  session_id: string | null
  auto_feedback: boolean
  todo_progress: any[] | null
  created_at: string
  // Joined from session
  result_state?: string | null
  result_summary?: string | null
}

async function fetchSubTasks(sessionId: string): Promise<{ data: SubTaskData[]; count: number }> {
  const token = typeof OpenAPI.TOKEN === "function"
    ? await OpenAPI.TOKEN({} as any)
    : OpenAPI.TOKEN || ""

  const response = await fetch(`${OpenAPI.BASE}/api/v1/tasks/by-source-session/${sessionId}`, {
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  })

  if (!response.ok) {
    throw new Error(`Failed to fetch sub-tasks: ${response.status}`)
  }

  return response.json()
}

/**
 * Derive effective display state from result_state (agent-declared) and task status (lifecycle).
 * result_state takes priority when set; otherwise fall back to task status.
 */
function getEffectiveState(task: SubTaskData): string {
  if (task.result_state) return task.result_state
  switch (task.status) {
    case "completed": return "completed"
    case "error": return "error"
    case "pending_input": return "needs_input"
    case "new": return "new"
    default: return "running"
  }
}

function getStateIcon(state: string) {
  switch (state) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
    case "needs_input":
      return <HelpCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
    case "error":
      return <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" />
    case "new":
      return <div className="h-4 w-4 rounded-full border-2 border-violet-500 dark:border-violet-400" />
    default:
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
  }
}

function getStateBadge(state: string) {
  switch (state) {
    case "completed":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">Completed</span>
    case "needs_input":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">Needs Input</span>
    case "error":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">Error</span>
    case "new":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-violet-100 dark:bg-violet-900/30 text-violet-700 dark:text-violet-300">New</span>
    default:
      return <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">Running</span>
  }
}

export function SubTasksPanel({ sessionId, onClose }: SubTasksPanelProps) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const { data: tasksResponse, isLoading } = useQuery({
    queryKey: ["subTasks", sessionId],
    queryFn: () => fetchSubTasks(sessionId),
    refetchInterval: 10000, // Poll every 10 seconds
  })

  // Subscribe to session state updates for real-time refresh
  useMultiEventSubscription(
    [EventTypes.SESSION_STATE_UPDATED],
    () => {
      queryClient.invalidateQueries({ queryKey: ["subTasks", sessionId] })
    }
  )

  const executeMutation = useMutation({
    mutationFn: (taskId: string) =>
      TasksService.executeTask({ id: taskId, requestBody: {} }),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["subTasks", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["subTasksCount", sessionId] })
      if (data.session_id) {
        onClose()
        navigate({
          to: "/session/$sessionId",
          params: { sessionId: data.session_id },
          search: { initialMessage: undefined, fileIds: undefined, fileObjects: undefined },
        })
      }
    },
  })

  const tasks = tasksResponse?.data || []

  const handleTaskClick = (task: SubTaskData) => {
    if (task.session_id) {
      onClose()
      navigate({
        to: "/session/$sessionId",
        params: { sessionId: task.session_id },
        search: { initialMessage: undefined, fileIds: undefined, fileObjects: undefined },
      })
    }
  }

  return (
    <div className="absolute top-0 right-0 h-full w-80 bg-background border-l shadow-lg z-50 flex flex-col">
      {/* Task list */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2 pt-3">
        {isLoading ? (
          <div className="flex items-center justify-center h-24">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-sm text-muted-foreground">
            No sub-tasks
          </div>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              onClick={() => handleTaskClick(task)}
              className={`px-3 py-2.5 rounded-md bg-muted/40 hover:bg-muted/80 transition-colors ${
                task.session_id ? "cursor-pointer" : ""
              }`}
            >
              <div className="flex items-start gap-2">
                <div className="mt-0.5 shrink-0">
                  {getStateIcon(getEffectiveState(task))}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    {task.agent_name && (
                      <span className="text-xs font-medium text-muted-foreground">{task.agent_name}</span>
                    )}
                    {getStateBadge(getEffectiveState(task))}
                  </div>
                  <p className="text-sm text-foreground line-clamp-2">{task.original_message}</p>
                  {task.result_summary && (
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2 italic">
                      {task.result_summary}
                    </p>
                  )}
                  <div className="flex items-center justify-between mt-1.5">
                    <span className="text-xs text-muted-foreground">
                      <RelativeTime timestamp={task.created_at} />
                    </span>
                    {!task.session_id && (
                      task.selected_agent_id ? (
                        <Button
                          size="sm"
                          className="h-6 px-2 text-xs gap-1"
                          disabled={executeMutation.isPending}
                          onClick={(e) => {
                            e.stopPropagation()
                            executeMutation.mutate(task.id)
                          }}
                        >
                          {executeMutation.isPending ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Play className="h-3 w-3" />
                          )}
                          Execute
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-6 px-2 text-xs gap-1"
                          onClick={(e) => {
                            e.stopPropagation()
                            onClose()
                            navigate({ to: "/task/$taskId", params: { taskId: task.id } })
                          }}
                        >
                          <ExternalLink className="h-3 w-3" />
                          Open
                        </Button>
                      )
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
