import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { AlertCircle, ArrowLeft } from "lucide-react"

import { TasksService } from "@/client"
import { TaskDetail } from "@/components/Tasks/TaskDetail"
import { Skeleton } from "@/components/ui/skeleton"
import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/_layout/tasks/$shortCode")({
  component: TaskDetailPage,
})

function TaskDetailSkeleton() {
  return (
    <div className="flex flex-col gap-0 h-full overflow-y-auto">
      {/* Header skeleton */}
      <div className="flex items-start gap-3 px-6 py-4 border-b bg-card/50">
        <Skeleton className="h-8 w-8 shrink-0 rounded-md" />
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Skeleton className="h-5 w-16" />
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-5 w-14" />
          </div>
          <Skeleton className="h-6 w-2/3" />
        </div>
      </div>

      {/* Metadata skeleton */}
      <div className="px-6 py-4 border-b space-y-3">
        <div className="grid grid-cols-2 gap-x-6 gap-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-4 w-36" />
          <Skeleton className="h-4 w-28" />
        </div>
      </div>

      {/* Comment thread skeleton */}
      <div className="flex-1 px-6 py-4 space-y-4">
        <Skeleton className="h-3 w-16" />
        {[1, 2, 3].map((i) => (
          <div key={i} className="flex items-start gap-2.5 py-2">
            <Skeleton className="h-7 w-7 rounded-full shrink-0" />
            <div className="flex-1 min-w-0 space-y-2">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-3 w-16" />
              </div>
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function TaskDetailPage() {
  const { shortCode } = Route.useParams()
  const navigate = useNavigate()

  const { data: task, isLoading, error } = useQuery({
    queryKey: ["task", shortCode],
    queryFn: () => TasksService.getTaskDetailByCode({ shortCode }),
  })

  if (isLoading) {
    return <TaskDetailSkeleton />
  }

  if (error || !task) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-12 gap-4">
        <AlertCircle className="h-10 w-10 text-destructive" />
        <div className="text-center space-y-1">
          <p className="font-medium">Task not found</p>
          <p className="text-sm text-muted-foreground">
            {error
              ? "Failed to load task. It may have been deleted."
              : `No task with code "${shortCode}" exists.`}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => navigate({ to: "/tasks" })}>
          <ArrowLeft className="h-4 w-4 mr-1.5" />
          Back to Tasks
        </Button>
      </div>
    )
  }

  return <TaskDetail task={task} shortCode={shortCode} />
}
