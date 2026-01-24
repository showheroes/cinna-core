import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import { ArrowLeft, ListTodo } from "lucide-react"
import type { SessionPublic } from "@/client"
import { OpenAPI } from "@/client"
import { AnimatedPlaceholder } from "@/components/Common/AnimatedPlaceholder"
import { SubTasksPanel } from "./SubTasksPanel"

interface ChatHeaderProps {
  session: SessionPublic
  onModeSwitch: () => void
  onBack: () => void
}

async function fetchSubTasksCount(sessionId: string): Promise<number> {
  const token = typeof OpenAPI.TOKEN === "function"
    ? await OpenAPI.TOKEN({} as any)
    : OpenAPI.TOKEN || ""

  const response = await fetch(`${OpenAPI.BASE}/api/v1/tasks/by-source-session/${sessionId}`, {
    headers: {
      "Authorization": `Bearer ${token}`,
      "Content-Type": "application/json",
    },
  })

  if (!response.ok) return 0
  const data = await response.json()
  return data.count || 0
}

export function ChatHeader({ session, onModeSwitch, onBack }: ChatHeaderProps) {
  const isBuilding = session.mode === "building"
  const [showSubTasks, setShowSubTasks] = useState(false)

  // Query sub-task count for badge
  const { data: subTaskCount = 0 } = useQuery({
    queryKey: ["subTasksCount", session.id],
    queryFn: () => fetchSubTasksCount(session.id),
    refetchInterval: 15000,
  })

  return (
    <div className="border-b px-6 py-3 bg-background shrink-0 relative">
      <div className="flex items-center justify-between gap-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="sm" onClick={onBack} className="shrink-0">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold truncate">
              {session.title ? session.title : <AnimatedPlaceholder />}
            </h1>
            <p className="text-xs text-muted-foreground">
              <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
                isBuilding ? "bg-orange-500" : "bg-blue-500"
              }`} />
              {isBuilding ? "Building Mode" : "Conversation Mode"}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {subTaskCount > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowSubTasks(!showSubTasks)}
              className="gap-1.5 relative"
            >
              <ListTodo className="h-4 w-4" />
              <span className="text-xs">{subTaskCount}</span>
            </Button>
          )}
          <Button
            variant={isBuilding ? "outline" : "default"}
            size="sm"
            onClick={onModeSwitch}
            className={`gap-2 ${
              isBuilding
                ? "border-orange-500 text-orange-700 dark:text-orange-400 hover:bg-orange-50 dark:hover:bg-orange-950/20"
                : "bg-blue-500 hover:bg-blue-600 text-white"
            }`}
          >
            Switch Mode
          </Button>
        </div>
      </div>

      {/* Sub-tasks panel overlay */}
      {showSubTasks && (
        <SubTasksPanel
          sessionId={session.id}
          onClose={() => setShowSubTasks(false)}
        />
      )}
    </div>
  )
}
