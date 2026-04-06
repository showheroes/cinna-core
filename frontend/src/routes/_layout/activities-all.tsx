import { useQuery } from "@tanstack/react-query"
import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useEffect, useState, useCallback } from "react"

import { ActivitiesService } from "@/client"
import type { ActivityPublicExtended } from "@/client"
import PendingItems from "@/components/Pending/PendingItems"
import { usePageHeader } from "@/routes/_layout"
import { getColorPreset } from "@/utils/colorPresets"
import { RelativeTime } from "@/components/Common/RelativeTime"
import {
  Bell,
  CheckCircle2,
  AlertCircle,
  ClipboardList,
  FileText,
  MessageCircle,
  AlertOctagon,
  Mail,
  XCircle,
  ChevronLeft,
  ChevronRight,
  ArrowLeft,
} from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "@/components/ui/button"

export const Route = createFileRoute("/_layout/activities-all")({
  component: AllLogsPage,
})

const PAGE_SIZE = 100

function getActivityIcon(activityType: string): { icon: React.ReactNode; colorClass: string } {
  switch (activityType) {
    case "session_completed":
    case "task_completed":
      return { icon: <CheckCircle2 className="h-3.5 w-3.5" />, colorClass: "text-green-500" }
    case "questions_asked":
    case "session_feedback_required":
      return { icon: <MessageCircle className="h-3.5 w-3.5" />, colorClass: "text-amber-500" }
    case "error_occurred":
    case "task_failed":
      return { icon: <AlertOctagon className="h-3.5 w-3.5" />, colorClass: "text-red-500" }
    case "file_created":
      return { icon: <FileText className="h-3.5 w-3.5" />, colorClass: "text-blue-500" }
    case "email_task_incoming":
    case "email_task_reply_pending":
      return { icon: <Mail className="h-3.5 w-3.5" />, colorClass: "text-purple-500" }
    case "task_blocked":
      return { icon: <AlertCircle className="h-3.5 w-3.5" />, colorClass: "text-amber-500" }
    case "task_cancelled":
      return { icon: <XCircle className="h-3.5 w-3.5" />, colorClass: "text-red-400" }
    default:
      return { icon: <Bell className="h-3.5 w-3.5" />, colorClass: "text-muted-foreground" }
  }
}

function getEntityIcon(activityType: string): React.ReactNode {
  if (activityType.startsWith("task_") || activityType.startsWith("email_task_")) {
    return <ClipboardList className="h-3 w-3 text-muted-foreground shrink-0" />
  }
  return <MessageCircle className="h-3 w-3 text-blue-500 shrink-0" />
}

function CompactLogRow({
  activity,
  onClick,
}: {
  activity: ActivityPublicExtended
  onClick: () => void
}) {
  const colorPreset = getColorPreset(activity.agent_ui_color_preset)
  const { icon, colorClass } = getActivityIcon(activity.activity_type)

  const contextParts: string[] = []
  if (activity.task_short_code) contextParts.push(activity.task_short_code)
  if (activity.task_title) contextParts.push(activity.task_title)
  else if (activity.session_title) contextParts.push(activity.session_title)

  return (
    <div
      onClick={onClick}
      className={cn(
        "flex items-center gap-2.5 px-3 py-1.5 text-sm transition-colors",
        (activity.session_id || activity.input_task_id) ? "cursor-pointer hover:bg-muted/50" : "",
      )}
    >
      <div className={cn("shrink-0", colorClass)}>{icon}</div>
      <span className="shrink-0 w-[120px] text-xs text-muted-foreground">
        <RelativeTime timestamp={activity.created_at} />
      </span>
      {activity.agent_name && (
        <span
          className={cn(
            "inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0",
            colorPreset.badgeBg,
            colorPreset.badgeText,
          )}
        >
          {activity.agent_name}
        </span>
      )}
      <span className="shrink-0 text-foreground flex items-center gap-1">
        {getEntityIcon(activity.activity_type)}
        {activity.text}
      </span>
      {contextParts.length > 0 && (
        <span className="text-xs text-muted-foreground truncate">
          {contextParts.join(" · ")}
        </span>
      )}
    </div>
  )
}

function AllLogsPage() {
  const { setHeaderContent } = usePageHeader()
  const navigate = useNavigate()
  const [page, setPage] = useState(0)

  const { data, isLoading, error } = useQuery({
    queryKey: ["activities-all-logs", page],
    queryFn: () =>
      ActivitiesService.listActivities({
        includeArchived: true,
        skip: page * PAGE_SIZE,
        limit: PAGE_SIZE,
        orderDesc: true,
      }),
    placeholderData: (prev) => prev,
  })

  const totalCount = data?.count ?? 0
  const totalPages = Math.ceil(totalCount / PAGE_SIZE)
  const activities = data?.data ?? []

  const navigateToActivity = useCallback(
    (activity: ActivityPublicExtended) => {
      if (activity.input_task_id) {
        navigate({ to: "/task/$taskId", params: { taskId: activity.input_task_id } })
      } else if (activity.session_id) {
        navigate({
          to: "/session/$sessionId",
          params: { sessionId: activity.session_id },
          search: { initialMessage: undefined, fileIds: undefined, fileObjects: undefined, pageContext: undefined },
        })
      }
    },
    [navigate],
  )

  useEffect(() => {
    setHeaderContent(
      <div className="flex items-center gap-3 w-full">
        <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/activities" })}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">All Logs</h1>
          <p className="text-xs text-muted-foreground">{totalCount} total entries</p>
        </div>
      </div>,
    )
    return () => setHeaderContent(null)
  }, [setHeaderContent, totalCount])

  if (isLoading && !data) return <PendingItems />

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive">Error loading logs</p>
      </div>
    )
  }

  return (
    <div className="p-6 md:p-8 overflow-y-auto h-full">
      <div className="mx-auto max-w-5xl space-y-4">
        {activities.length === 0 ? (
          <div className="text-center py-12 border-2 border-dashed rounded-lg">
            <p className="text-sm text-muted-foreground">No log entries</p>
          </div>
        ) : (
          <div className="border rounded-lg divide-y overflow-hidden">
            {activities.map((activity) => (
              <CompactLogRow
                key={activity.id}
                activity={activity}
                onClick={() => navigateToActivity(activity)}
              />
            ))}
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between px-1">
            <span className="text-xs text-muted-foreground">
              Page {page + 1} of {totalPages}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 0}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= totalPages - 1}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
