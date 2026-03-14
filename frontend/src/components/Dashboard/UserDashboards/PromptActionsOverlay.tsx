import { useState, type RefObject } from "react"
import { useNavigate } from "@tanstack/react-router"
import { Loader2 } from "lucide-react"

import type { UserDashboardBlockPromptActionPublic } from "@/client"
import { DashboardsService, SessionsService } from "@/client"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import useCustomToast from "@/hooks/useCustomToast"
import { buildPageContext } from "@/utils/webappContext"

interface PromptActionsOverlayProps {
  actions: UserDashboardBlockPromptActionPublic[]
  agentId: string
  blockId: string
  dashboardId: string
  isVisible: boolean
  /**
   * Ref to the webapp iframe in this block, if the block view type is "webapp".
   * When provided, page context (schema.org microdata + selected text) is
   * collected from the iframe before navigating, and forwarded to the session
   * page via the `pageContext` search param so it is attached to the first
   * message. This mirrors the same context collection used by WebappChatWidget.
   */
  iframeRef?: RefObject<HTMLIFrameElement | null>
}

/**
 * Displays prompt action buttons over a dashboard block on hover (view mode only).
 *
 * Clicking a button:
 * 1. Checks whether a recent session exists for this block (last message within 12h).
 *    - If yes: reuses that session, navigating to it with `initialMessage` so the
 *      prompt is sent as a new message in the existing conversation.
 *    - If no: creates a new session tagged with `dashboard_block_id`, then navigates
 *      to it the same way.
 * 2. Collects page context from the webapp iframe (if the block is a webapp view)
 *    using the same postMessage mechanism as WebappChatWidget — schema.org microdata
 *    plus any selected text. Context collection has a 500ms timeout and fails silently.
 * 3. Navigates to the session page with `initialMessage` (the prompt text) and
 *    `pageContext` (the collected context JSON string, if any). The session page
 *    forwards pageContext alongside the first message send so the backend can
 *    store it in message_metadata and inject it into the agent's context.
 */
export function PromptActionsOverlay({
  actions,
  agentId,
  blockId,
  dashboardId,
  isVisible,
  iframeRef,
}: PromptActionsOverlayProps) {
  const navigate = useNavigate()
  const { showErrorToast } = useCustomToast()

  // Maps actionId -> true while session lookup/creation is in flight
  const [pendingActions, setPendingActions] = useState<Record<string, boolean>>({})

  if (!actions.length) return null

  const getDisplayLabel = (action: UserDashboardBlockPromptActionPublic): string => {
    if (action.label) return action.label
    const text = action.prompt_text
    return text.length > 28 ? text.slice(0, 26) + "…" : text
  }

  const handleActionClick = async (action: UserDashboardBlockPromptActionPublic) => {
    if (pendingActions[action.id]) return

    setPendingActions((prev) => ({ ...prev, [action.id]: true }))
    try {
      // Resolve the session and collect page context concurrently.
      // Context collection has a short timeout and fails silently — the session
      // is always navigated to even if context collection fails.
      const [resolvedSession, pageContext] = await Promise.all([
        resolveSession(agentId, blockId, dashboardId),
        buildPageContext(iframeRef),
      ])

      navigate({
        to: "/session/$sessionId",
        params: { sessionId: resolvedSession.id },
        search: {
          initialMessage: action.prompt_text,
          fileIds: undefined,
          fileObjects: undefined,
          pageContext,
        },
      })
    } catch {
      showErrorToast("Failed to start session. Please try again.")
      setPendingActions((prev) => {
        const next = { ...prev }
        delete next[action.id]
        return next
      })
    }
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
        const isPending = pendingActions[action.id]

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

/**
 * Resolve the session to use for a prompt action click.
 *
 * Checks for a recent session on this block (last message within 12h).
 * If one exists, reuses it. Otherwise creates a new session tagged with
 * the block ID so future prompt action clicks can find and reuse it.
 */
async function resolveSession(
  agentId: string,
  blockId: string,
  dashboardId: string,
): Promise<{ id: string }> {
  try {
    const recent = await DashboardsService.getBlockLatestSession({
      dashboardId,
      blockId,
    })
    // A recent session with activity in the last 12h exists — reuse it
    return { id: recent.id }
  } catch {
    // 404 (or any network error) means no recent session — create a fresh one
    const session = await SessionsService.createSession({
      requestBody: {
        agent_id: agentId,
        mode: "conversation",
        dashboard_block_id: blockId,
      },
    })
    return { id: session.id }
  }
}
