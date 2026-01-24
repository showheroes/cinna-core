import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Link } from "@tanstack/react-router"
import { OpenAPI } from "@/client"
import { X, CheckCircle2, HelpCircle, AlertTriangle, Loader2, ExternalLink } from "lucide-react"
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
  status: string
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

function getStateIcon(resultState: string | null | undefined) {
  switch (resultState) {
    case "completed":
      return <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
    case "needs_input":
      return <HelpCircle className="h-4 w-4 text-amber-600 dark:text-amber-400" />
    case "error":
      return <AlertTriangle className="h-4 w-4 text-red-600 dark:text-red-400" />
    default:
      return <Loader2 className="h-4 w-4 text-blue-500 animate-spin" />
  }
}

function getStateBadge(resultState: string | null | undefined) {
  switch (resultState) {
    case "completed":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300">Completed</span>
    case "needs_input":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-300">Needs Input</span>
    case "error":
      return <span className="text-xs px-1.5 py-0.5 rounded bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300">Error</span>
    default:
      return <span className="text-xs px-1.5 py-0.5 rounded bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">Running</span>
  }
}

export function SubTasksPanel({ sessionId, onClose }: SubTasksPanelProps) {
  const queryClient = useQueryClient()

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

  const tasks = tasksResponse?.data || []

  return (
    <div className="absolute top-0 right-0 h-full w-80 bg-background border-l shadow-lg z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b">
        <h3 className="text-sm font-semibold">Sub-Tasks ({tasks.length})</h3>
        <Button variant="ghost" size="sm" onClick={onClose} className="h-6 w-6 p-0">
          <X className="h-4 w-4" />
        </Button>
      </div>

      {/* Task list */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center h-24">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : tasks.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-sm text-muted-foreground">
            No sub-tasks
          </div>
        ) : (
          <div className="divide-y">
            {tasks.map((task) => (
              <div key={task.id} className="px-4 py-3 hover:bg-muted/50 transition-colors">
                <div className="flex items-start gap-2">
                  <div className="mt-0.5 shrink-0">
                    {getStateIcon(task.result_state)}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {task.agent_name && (
                        <span className="text-xs font-medium text-muted-foreground">{task.agent_name}</span>
                      )}
                      {getStateBadge(task.result_state)}
                    </div>
                    <p className="text-sm text-foreground line-clamp-2">{task.original_message}</p>
                    {task.result_summary && (
                      <p className="text-xs text-muted-foreground mt-1 line-clamp-2 italic">
                        {task.result_summary}
                      </p>
                    )}
                    <div className="flex items-center gap-2 mt-1.5">
                      <span className="text-xs text-muted-foreground">
                        <RelativeTime timestamp={task.created_at} />
                      </span>
                      {task.session_id && (
                        <Link
                          to="/session/$sessionId"
                          params={{ sessionId: task.session_id }}
                          search={{ initialMessage: undefined, fileIds: undefined, fileObjects: undefined }}
                          className="inline-flex items-center gap-0.5 text-xs text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                        >
                          <span>View</span>
                          <ExternalLink className="h-3 w-3" />
                        </Link>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
