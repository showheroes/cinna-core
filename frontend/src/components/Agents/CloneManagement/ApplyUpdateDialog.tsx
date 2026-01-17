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

interface ApplyUpdateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  agentId: string
  onApplied: () => void
}

export function ApplyUpdateDialog({
  open,
  onOpenChange,
  agentId,
  onApplied,
}: ApplyUpdateDialogProps) {
  const queryClient = useQueryClient()

  const applyMutation = useMutation({
    mutationFn: () => AgentSharesService.applyUpdate({ agentId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] })
      queryClient.invalidateQueries({ queryKey: ["agent", agentId] })
      onApplied()
      onOpenChange(false)
    },
  })

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Apply Update</DialogTitle>
          <DialogDescription>
            Apply the latest changes from the parent agent?
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="text-sm space-y-2">
            <p><strong>What will be updated:</strong></p>
            <ul className="list-disc list-inside text-muted-foreground">
              <li>Prompts and system messages</li>
              <li>Scripts and automation logic</li>
              <li>Knowledge base files</li>
            </ul>
          </div>

          <Alert>
            <AlertTriangle className="h-4 w-4" />
            <AlertDescription>
              Your sessions, files, and personal data will NOT be affected.
            </AlertDescription>
          </Alert>

          {applyMutation.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(applyMutation.error as Error).message || "Failed to apply update"}
              </AlertDescription>
            </Alert>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={() => applyMutation.mutate()} disabled={applyMutation.isPending}>
            {applyMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Applying...
              </>
            ) : (
              "Apply Update"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
