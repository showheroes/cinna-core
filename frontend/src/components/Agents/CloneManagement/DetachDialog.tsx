import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2, AlertTriangle } from "lucide-react"

import { AgentSharesService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"

interface DetachDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  agentId: string
  onDetached: () => void
}

export function DetachDialog({
  open,
  onOpenChange,
  agentId,
  onDetached,
}: DetachDialogProps) {
  const queryClient = useQueryClient()

  const detachMutation = useMutation({
    mutationFn: () => AgentSharesService.detachClone({ agentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] })
      queryClient.invalidateQueries({ queryKey: ["agent", agentId] })
      onDetached()
      onOpenChange(false)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Detach from Parent</DialogTitle>
          <DialogDescription>
            Make this agent independent?
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-muted-foreground">
            After detaching, this agent will become a regular independent agent that you fully own.
          </p>

          <div className="text-sm space-y-2">
            <p><strong>What happens:</strong></p>
            <ul className="list-disc list-inside text-muted-foreground">
              <li>No more updates from the parent agent</li>
              <li>You gain full control to modify everything</li>
              <li>You can share this agent with others</li>
              <li>All your data is preserved</li>
            </ul>
          </div>

          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              This action cannot be undone. You won't be able to reconnect to the parent.
            </AlertDescription>
          </Alert>

          {detachMutation.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(detachMutation.error as Error).message || "Failed to detach"}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => detachMutation.mutate()} disabled={detachMutation.isPending}>
            {detachMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Detaching...
              </>
            ) : (
              "Detach"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
