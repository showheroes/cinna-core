import { useState, useEffect } from "react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { Switch } from "@/components/ui/switch"
import type { AgenticTeamConnectionPublic } from "@/client"

interface ConnectionEditDialogProps {
  open: boolean
  onClose: () => void
  connection: AgenticTeamConnectionPublic | null
  onSave: (connectionId: string, prompt: string, enabled: boolean) => void
  isPending: boolean
}

export function ConnectionEditDialog({
  open,
  onClose,
  connection,
  onSave,
  isPending,
}: ConnectionEditDialogProps) {
  const [prompt, setPrompt] = useState("")
  const [enabled, setEnabled] = useState(true)

  useEffect(() => {
    if (open && connection) {
      setPrompt(connection.connection_prompt)
      setEnabled(connection.enabled)
    }
  }, [open, connection])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!connection) return
    onSave(connection.id, prompt, enabled)
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[500px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Edit Connection</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            {connection && (
              <div className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">
                  {connection.source_node_name}
                </span>{" "}
                &rarr;{" "}
                <span className="font-medium text-foreground">
                  {connection.target_node_name}
                </span>
              </div>
            )}
            <div className="grid gap-2">
              <Label htmlFor="conn-prompt">Handover Prompt</Label>
              <Textarea
                id="conn-prompt"
                placeholder="Describe when and how to hand over work from the source agent to the target agent. Include trigger conditions, context to pass, and expected output format."
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={5}
                maxLength={2000}
                className="resize-none"
              />
              <div className="text-xs text-muted-foreground text-right">
                {prompt.length}/2000
              </div>
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="conn-enabled">Connection enabled</Label>
              <Switch
                id="conn-enabled"
                checked={enabled}
                onCheckedChange={setEnabled}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Saving..." : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
