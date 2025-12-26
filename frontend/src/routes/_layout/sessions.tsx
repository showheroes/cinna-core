import { useQuery } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import { useEffect } from "react"

import { SessionsService } from "@/client"
import { SessionCard } from "@/components/Sessions/SessionCard"
import { CreateSession } from "@/components/Sessions/CreateSession"
import PendingItems from "@/components/Pending/PendingItems"
import { usePageHeader } from "@/routes/_layout"

export const Route = createFileRoute("/_layout/sessions")({
  component: SessionsList,
})

function SessionsList() {
  const { setHeaderContent } = usePageHeader()

  const {
    data: sessionsData,
    isLoading: sessionsLoading,
    error: sessionsError,
  } = useQuery({
    queryKey: ["sessions"],
    queryFn: () => SessionsService.listSessions(),
  })

  useEffect(() => {
    setHeaderContent(
      <>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">Sessions</h1>
          <p className="text-xs text-muted-foreground">Manage your conversation sessions</p>
        </div>
        <CreateSession />
      </>
    )
    return () => setHeaderContent(null)
  }, [setHeaderContent])

  if (sessionsLoading) {
    return <PendingItems />
  }

  if (sessionsError) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive">Error loading sessions</p>
      </div>
    )
  }

  const sessions = sessionsData?.data || []

  return (
    <div className="p-6 md:p-8 overflow-y-auto">
      <div className="mx-auto max-w-7xl space-y-6">
        {/* Sessions Grid */}
        {sessions.length === 0 ? (
          <div className="text-center py-12 border-2 border-dashed rounded-lg">
            <p className="text-muted-foreground mb-4">No sessions yet</p>
            <CreateSession />
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            {sessions.map((session) => (
              <SessionCard
                key={session.id}
                session={session}
                agentName={session.agent_name || "Unknown Agent"}
                agentColorPreset={session.agent_ui_color_preset}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
