import { useQuery } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { MessageSquare, MessageCircle, Wrench, Clock } from "lucide-react"

import { SessionsService } from "@/client"
import { AnimatedPlaceholder } from "@/components/Common/AnimatedPlaceholder"
import { RelativeTime } from "@/components/Common/RelativeTime"
import { Skeleton } from "@/components/ui/skeleton"

interface LatestSessionViewProps {
  agentId: string
}

export function LatestSessionView({ agentId }: LatestSessionViewProps) {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ["dashboardBlockSessions", agentId],
    queryFn: () =>
      SessionsService.listSessions({
        agentId,
        limit: 10,
        orderBy: "last_message_at",
        orderDesc: true,
      }),
    refetchInterval: 30000,
  })

  if (isLoading) {
    return (
      <div className="p-3 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-3 w-full" />
      </div>
    )
  }

  const sessions = data?.data || []

  if (sessions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full p-4 text-center">
        <MessageSquare className="h-8 w-8 text-muted-foreground mb-2" />
        <p className="text-sm text-muted-foreground">No sessions yet</p>
      </div>
    )
  }

  const handleSessionClick = (sessionId: string) => {
    navigate({
      to: "/session/$sessionId",
      params: { sessionId },
      search: { initialMessage: undefined, fileIds: undefined, fileObjects: undefined, pageContext: undefined },
    })
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto p-1">
      <div className="space-y-0.5">
        {sessions.map((session) => (
          <button
            key={session.id}
            onClick={() => handleSessionClick(session.id)}
            className="w-full text-left px-3 py-2 rounded-md hover:bg-accent transition-colors"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  {session.mode === "building" ? (
                    <Wrench className="h-3.5 w-3.5 text-orange-500 shrink-0" />
                  ) : (
                    <MessageCircle className="h-3.5 w-3.5 text-blue-500 shrink-0" />
                  )}
                  <p className="text-sm text-foreground truncate">
                    {session.title ? session.title : <AnimatedPlaceholder className="text-xs" />}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1 text-xs text-muted-foreground shrink-0">
                <Clock className="h-3 w-3" />
                <RelativeTime timestamp={session.last_message_at || session.created_at} />
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
