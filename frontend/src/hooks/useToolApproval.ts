import { useState, useCallback, useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { AgentsService } from "@/client"
import type { MessagePublic } from "@/client"

interface UseToolApprovalProps {
  message: MessagePublic
  agentId: string | undefined
}

interface UseToolApprovalResult {
  /** Tools that need approval from this message */
  toolsNeedingApproval: string[]
  /** Whether there are tools needing approval */
  hasToolsNeedingApproval: boolean
  /** Whether approval is in progress */
  isApproving: boolean
  /** Whether approval was successful */
  isApproved: boolean
  /** Error message if approval failed */
  error: string | null
  /** Function to approve tools */
  approveTools: () => Promise<void>
}

/**
 * Hook for managing tool approval state and API calls.
 *
 * Detects tools needing approval from message metadata and provides
 * a function to approve them via the backend API.
 *
 * Note: The backend filters tools_needing_approval against the agent's
 * allowed_tools when returning messages, so already-approved tools
 * won't appear here even after page reload.
 */
export function useToolApproval({
  message,
  agentId,
}: UseToolApprovalProps): UseToolApprovalResult {
  const [isApproved, setIsApproved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Extract tools needing approval from message metadata
  // Backend already filters out approved tools when returning messages
  const toolsNeedingApproval = useMemo(() => {
    const metadata = message.message_metadata as Record<string, unknown> | undefined
    if (!metadata) return []

    // Get tools_needing_approval from message metadata (set by backend)
    const tools = metadata.tools_needing_approval as string[] | undefined
    return tools || []
  }, [message.message_metadata])

  const hasToolsNeedingApproval = toolsNeedingApproval.length > 0 && !isApproved

  // Mutation for approving tools
  const { mutateAsync, isPending: isApproving } = useMutation({
    mutationFn: async (tools: string[]) => {
      if (!agentId) {
        throw new Error("Agent ID is required to approve tools")
      }
      return AgentsService.addAllowedTools({
        id: agentId,
        requestBody: { tools },
      })
    },
    onSuccess: () => {
      setIsApproved(true)
      setError(null)
      // Invalidate agent queries to refresh SDK config
      if (agentId) {
        queryClient.invalidateQueries({ queryKey: ["agent", agentId] })
      }
    },
    onError: (err) => {
      const errorMessage = err instanceof Error ? err.message : "Failed to approve tools"
      setError(errorMessage)
    },
  })

  // Approve all tools needing approval
  const approveTools = useCallback(async () => {
    if (toolsNeedingApproval.length === 0) return
    setError(null)
    await mutateAsync(toolsNeedingApproval)
  }, [toolsNeedingApproval, mutateAsync])

  return {
    toolsNeedingApproval,
    hasToolsNeedingApproval,
    isApproving,
    isApproved,
    error,
    approveTools,
  }
}

export default useToolApproval
