import { useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { Loader2 } from "lucide-react"
import { SessionsService } from "@/client"
import type { MessagePublic, MessagesPublic } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface RecoverSessionModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  sessionId: string
}

/**
 * Detect if the last user message was followed only by system error messages.
 * Used for UI display only — the backend independently detects this pattern
 * and handles re-queuing the message for processing.
 */
function hasFailedUserMessage(messages: MessagePublic[]): boolean {
  if (messages.length < 2) return false

  // Walk backwards from the end: skip system error messages
  let i = messages.length - 1
  while (i >= 0 && messages[i].role === "system" && messages[i].status === "error") {
    i--
  }

  // The message at position i should be the user's failed message
  return i >= 0 && messages[i].role === "user"
}

export function RecoverSessionModal({
  open,
  onOpenChange,
  sessionId,
}: RecoverSessionModalProps) {
  const queryClient = useQueryClient()

  // Check if there's a failed user message that the backend will auto-resend
  const canAutoResend = useMemo(() => {
    const cached = queryClient.getQueryData<MessagesPublic>(["messages", sessionId])
    if (!cached?.data) return false
    return hasFailedUserMessage(cached.data)
  }, [queryClient, sessionId, open]) // eslint-disable-line react-hooks/exhaustive-deps

  const recoverMutation = useMutation({
    mutationFn: () =>
      SessionsService.recoverSession({ id: sessionId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] })
      queryClient.invalidateQueries({ queryKey: ["messages", sessionId] })
      onOpenChange(false)

      if (canAutoResend) {
        toast.success("Session recovered — resending your message...")
      } else {
        toast.success("Session recovery initiated", {
          description: "Send a message to continue the conversation with restored context.",
        })
      }
    },
    onError: () => {
      toast.error("Failed to recover session")
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Recover Session</DialogTitle>
          <DialogDescription>
            This will create a fresh AI session with a summary of the previous conversation as context.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 text-sm text-muted-foreground py-2">
          <p>What will happen:</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>A new AI session will be created</li>
            <li>Previous conversation history will be summarized as context</li>
            {canAutoResend ? (
              <li>Your last message will be automatically resent</li>
            ) : (
              <li>Send a new message to continue the conversation</li>
            )}
            <li>Recovery is partial — the AI won't have full memory of prior interactions</li>
          </ul>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="bg-amber-600 hover:bg-amber-700 dark:bg-amber-600 dark:hover:bg-amber-700 text-white"
            onClick={() => recoverMutation.mutate()}
            disabled={recoverMutation.isPending}
          >
            {recoverMutation.isPending && (
              <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
            )}
            {canAutoResend ? "Recover & Resend" : "Recover Session"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
