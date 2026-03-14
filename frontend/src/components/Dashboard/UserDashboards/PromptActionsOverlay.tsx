import { useState } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Loader2 } from "lucide-react"

import type { UserDashboardBlockPromptActionPublic } from "@/client"
import { SessionsService, MessagesService } from "@/client"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import useCustomToast from "@/hooks/useCustomToast"

interface PromptActionsOverlayProps {
  actions: UserDashboardBlockPromptActionPublic[]
  agentId: string
  isVisible: boolean
}

/**
 * Displays prompt action buttons over a dashboard block on hover (view mode only).
 * Clicking a button creates a new agent session and sends the prompt as the first message.
 * The button becomes a clickable spinner that navigates to the session page.
 */
export function PromptActionsOverlay({ actions, agentId, isVisible }: PromptActionsOverlayProps) {
  const navigate = useNavigate()
  const { showErrorToast } = useCustomToast()

  // Maps actionId -> sessionId for in-flight or completed sessions
  const [activeSessions, setActiveSessions] = useState<Record<string, string>>({})
  // Maps actionId -> true while the session creation request is in flight
  const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({})

  if (!actions.length) return null

  const getDisplayLabel = (action: UserDashboardBlockPromptActionPublic): string => {
    if (action.label) return action.label
    const text = action.prompt_text
    return text.length > 28 ? text.slice(0, 26) + "…" : text
  }

  const handleActionClick = async (action: UserDashboardBlockPromptActionPublic) => {
    if (pendingActions[action.id] || activeSessions[action.id]) return

    setPendingActions((prev) => ({ ...prev, [action.id]: true }))
    try {
      // 1. Create a new session in conversation mode
      const session = await SessionsService.createSession({
        requestBody: { agent_id: agentId, mode: "conversation" },
      })

      // 2. Send the prompt as the first message (fire-and-forget stream)
      MessagesService.sendMessageStream({
        sessionId: session.id,
        requestBody: { content: action.prompt_text },
      }).catch(() => {
        // Stream errors are non-fatal here; the session is already created
      })

      // 3. Mark this action as having an active session
      setActiveSessions((prev) => ({ ...prev, [action.id]: session.id }))
    } catch {
      showErrorToast("Failed to start session. Please try again.")
    } finally {
      setPendingActions((prev) => {
        const next = { ...prev }
        delete next[action.id]
        return next
      })
    }
  }

  const handleSpinnerClick = (sessionId: string) => {
    navigate({
      to: "/session/$sessionId",
      params: { sessionId },
      search: { initialMessage: undefined, fileIds: undefined, fileObjects: undefined },
    })
  }

  return (
    <div
      className={cn(
        "absolute inset-x-0 bottom-0 flex flex-wrap gap-1.5 p-2",
        "bg-background/85 backdrop-blur-sm border-t border-border/50",
        "transition-opacity duration-150",
        isVisible ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none",
      )}
    >
      {actions.map((action) => {
        const sessionId = activeSessions[action.id]
        const isPending = pendingActions[action.id]

        if (sessionId) {
          // Show spinner that navigates to session page
          return (
            <button
              key={action.id}
              type="button"
              title="Click to open session"
              aria-label={`Open session for: ${action.prompt_text}`}
              onClick={() => handleSpinnerClick(sessionId)}
              className={cn(
                "flex items-center justify-center h-6 w-6 rounded-full",
                "bg-primary/10 hover:bg-primary/20 text-primary",
                "transition-colors cursor-pointer",
              )}
            >
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            </button>
          )
        }

        return (
          <Button
            key={action.id}
            type="button"
            variant="outline"
            size="sm"
            title={action.prompt_text}
            aria-label={action.prompt_text}
            disabled={isPending}
            onClick={() => handleActionClick(action)}
            className="h-6 text-xs px-2 py-0 rounded-full"
          >
            {isPending ? (
              <Loader2 className="h-3 w-3 animate-spin" />
            ) : (
              getDisplayLabel(action)
            )}
          </Button>
        )
      })}
    </div>
  )
}
