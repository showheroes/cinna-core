import { useState } from "react"
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { TasksService, AgentsService } from "@/client"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
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
  const [selectedAgentId, setSelectedAgentId] = useState<string | undefined>(undefined)

  const { data: agentsData } = useQuery({
    queryKey: ["agents", activeWorkspaceId],
    queryFn: ({ queryKey }) => {
      const [, workspaceId] = queryKey
      return AgentsService.readAgents({
        skip: 0,
        limit: 100,
        userWorkspaceId: workspaceId ?? "",
      })
    },
    enabled: open,
  })

  const createMutation = useMutation({
    mutationFn: (data: InputTaskCreate) => TasksService.createTask({ requestBody: data }),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
      setMessage("")
      setSelectedAgentId(undefined)
      onOpenChange(false)
      onCreated?.(task.id)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!message.trim()) return

    createMutation.mutate({
      original_message: message.trim(),
      selected_agent_id: selectedAgentId || undefined,
      user_workspace_id: activeWorkspaceId || undefined,
    })
  }

  const agents = agentsData?.data || []

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

          <div className="space-y-2">
            <Label htmlFor="agent">Agent (Optional)</Label>
            <Select value={selectedAgentId} onValueChange={setSelectedAgentId}>
              <SelectTrigger>
                <SelectValue placeholder="Select an agent to handle this task" />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => (
                  <SelectItem key={agent.id} value={agent.id}>
                    {agent.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-xs text-muted-foreground">
              You can select or change the agent later during refinement.
            </p>
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
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
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
