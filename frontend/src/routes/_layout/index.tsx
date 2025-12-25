import { createFileRoute, Link } from "@tanstack/react-router"
import { useEffect } from "react"

import useAuth from "@/hooks/useAuth"
import { CreateSession } from "@/components/Sessions/CreateSession"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { MessageCircle } from "lucide-react"
import { usePageHeader } from "@/routes/_layout"

export const Route = createFileRoute("/_layout/")({
  component: Dashboard,
  head: () => ({
    meta: [
      {
        title: "Dashboard - FastAPI Cloud",
      },
    ],
  }),
})

function Dashboard() {
  const { user: currentUser } = useAuth()
  const { setHeaderContent } = usePageHeader()

  useEffect(() => {
    setHeaderContent(
      <div className="min-w-0">
        <h1 className="text-lg font-semibold truncate">
          Hi, {currentUser?.full_name || currentUser?.email} 👋
        </h1>
        <p className="text-xs text-muted-foreground">Welcome back!</p>
      </div>
    )
    return () => setHeaderContent(null)
  }, [setHeaderContent, currentUser])

  return (
    <div className="p-6 md:p-8 overflow-y-auto">
      <div className="mx-auto max-w-7xl">
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>Quick Start</CardTitle>
              <CardDescription>
                Start a new conversation with your agent
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <CreateSession variant="default" className="w-full" />
              <Link to="/sessions">
                <Button variant="outline" className="w-full gap-2">
                  <MessageCircle className="h-4 w-4" />
                  View All Sessions
                </Button>
              </Link>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
