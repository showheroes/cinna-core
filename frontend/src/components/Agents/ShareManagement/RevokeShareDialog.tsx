import { useState } from "react"
import { useMutation } from "@tanstack/react-query"
import { AlertTriangle, Loader2 } from "lucide-react"

import type { AgentSharePublic } from "@/client"
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
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"

interface RevokeShareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  share: AgentSharePublic
  agentId: string
  onRevoked: () => void
}

export function RevokeShareDialog({
  open,
  onOpenChange,
  share,
  agentId,
  onRevoked,
}: RevokeShareDialogProps) {
  const [action, setAction] = useState<"delete" | "detach">("detach")

  const revokeMutation = useMutation({
    mutationFn: () =>
      AgentSharesService.revokeShare({
        agentId,
        shareId: share.id,
        action,
      }),
    onSuccess: () => {
      onRevoked()
    },
  })

  const handleRevoke = () => {
    revokeMutation.mutate()
  }

  // Only show action choice if share was accepted (clone exists)
  const hasClone = share.status === "accepted"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Revoke Access</DialogTitle>
          <DialogDescription>
            Revoke access for {share.shared_with_email}?
          </DialogDescription>
        </DialogHeader>

        {hasClone ? (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              This user has already created a clone. Choose what happens to their agent:
            </p>

            <RadioGroup value={action} onValueChange={(v) => setAction(v as "delete" | "detach")}>
              <div className="flex items-start space-x-3 p-3 border rounded-lg">
                <RadioGroupItem value="delete" id="delete" className="mt-1" />
                <div>
                  <Label htmlFor="delete" className="font-medium text-destructive cursor-pointer">
                    Delete Clone
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    Remove the agent and all its data (sessions, files, etc.).
                    The user will lose everything.
                  </p>
                </div>
              </div>

              <div className="flex items-start space-x-3 p-3 border rounded-lg">
                <RadioGroupItem value="detach" id="detach" className="mt-1" />
                <div>
                  <Label htmlFor="detach" className="font-medium cursor-pointer">
                    Detach Clone
                  </Label>
                  <p className="text-sm text-muted-foreground">
                    The user keeps their agent but won't receive updates.
                    They become the full owner of their copy.
                  </p>
                </div>
              </div>
            </RadioGroup>

            {action === "delete" && (
              <Alert variant="destructive">
                <AlertTriangle className="h-4 w-4" />
                <AlertDescription>
                  This will permanently delete the user's clone and all their data.
                  This action cannot be undone.
                </AlertDescription>
              </Alert>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            This will cancel the pending share invitation.
          </p>
        )}

        {revokeMutation.error && (
          <Alert variant="destructive">
            <AlertDescription>
              {(revokeMutation.error as Error).message || "Failed to revoke share"}
            </AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            onClick={handleRevoke}
            disabled={revokeMutation.isPending}
          >
            {revokeMutation.isPending ? (
              <>
                <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                Revoking...
              </>
            ) : (
              "Revoke Access"
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
