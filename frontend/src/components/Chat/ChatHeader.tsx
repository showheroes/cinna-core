import { Button } from "@/components/ui/button"
import { ArrowLeft } from "lucide-react"
import type { SessionPublic } from "@/client"

interface ChatHeaderProps {
  session: SessionPublic
  onModeSwitch: () => void
  onBack: () => void
}

export function ChatHeader({ session, onModeSwitch, onBack }: ChatHeaderProps) {
  const isBuilding = session.mode === "building"

  return (
    <div className="border-b px-6 py-3 bg-background shrink-0">
      <div className="flex items-center justify-between gap-4 max-w-7xl mx-auto">
        <div className="flex items-center gap-3 min-w-0">
          <Button variant="ghost" size="sm" onClick={onBack} className="shrink-0">
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="text-base font-semibold truncate">
              {session.title || "Untitled Session"}
            </h1>
            <p className="text-xs text-muted-foreground">
              <span className={`inline-block w-2 h-2 rounded-full mr-1.5 ${
                isBuilding ? "bg-orange-500" : "bg-blue-500"
              }`} />
              {isBuilding ? "Building Mode" : "Conversation Mode"}
            </p>
          </div>
        </div>

        <div className="shrink-0">
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
    </div>
  )
}
