import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { TasksService } from "@/client"
import type { InputTaskCreate } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import useWorkspace from "@/hooks/useWorkspace"

interface CreateTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (taskId: string) => void
}

export function CreateTaskDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateTaskDialogProps) {
  const queryClient = useQueryClient()
  const { activeWorkspaceId } = useWorkspace()
  const [message, setMessage] = useState("")

  const createMutation = useMutation({
    mutationFn: (data: InputTaskCreate) => TasksService.createTask({ requestBody: data }),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
      setMessage("")
      onOpenChange(false)
      onCreated?.(task.id)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return

    createMutation.mutate({
      original_message: message.trim(),
      user_workspace_id: activeWorkspaceId || undefined,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Create New Task</DialogTitle>
          <DialogDescription>
            Enter your task request. You can refine it with AI assistance before execution.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="message">Task Description</Label>
            <Textarea
              id="message"
              placeholder="Describe what you want to accomplish..."
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              rows={4}
              className="resize-none"
            />
          </div>

          {createMutation.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(createMutation.error as Error).message || "Failed to create task"}
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button
              type="submit"
              disabled={!message.trim() || createMutation.isPending}
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Creating...
                </>
              ) : (
                "Create Task"
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
