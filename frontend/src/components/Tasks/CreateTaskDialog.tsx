import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"

import { TasksService, AgentsService, AgenticTeamsService } from "@/client"
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
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useWorkspace from "@/hooks/useWorkspace"

interface CreateTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (taskId: string) => void
  defaultTeamId?: string
}

const PRIORITY_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "normal", label: "Normal" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
]

export function CreateTaskDialog({
  open,
  onOpenChange,
  onCreated,
  defaultTeamId,
}: CreateTaskDialogProps) {
  const queryClient = useQueryClient()
  const { activeWorkspaceId } = useWorkspace()
  const [title, setTitle] = useState("")
  const [description, setDescription] = useState("")
  const [selectedAgentId, setSelectedAgentId] = useState<string>("")
  const [selectedTeamId, setSelectedTeamId] = useState<string>(defaultTeamId ?? "")
  const [selectedNodeId, setSelectedNodeId] = useState<string>("")
  const [priority, setPriority] = useState<string>("normal")

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setTitle("")
      setDescription("")
      setSelectedAgentId("")
      setSelectedTeamId(defaultTeamId ?? "")
      setSelectedNodeId("")
      setPriority("normal")
    }
  }, [open, defaultTeamId])

  // When team changes, reset node assignment
  useEffect(() => {
    setSelectedNodeId("")
    setSelectedAgentId("")
  }, [selectedTeamId])

  const { data: agentsData } = useQuery({
    queryKey: ["agents", activeWorkspaceId],
    queryFn: ({ queryKey }) => {
      const [, workspaceId] = queryKey
      return AgentsService.readAgents({
        skip: 0,
        limit: 100,
        userWorkspaceId: (workspaceId as string) ?? "",
      })
    },
    enabled: open,
  })

  const { data: teamsData } = useQuery({
    queryKey: ["agenticTeams"],
    queryFn: () => AgenticTeamsService.listAgenticTeams(),
    enabled: open,
  })

  const { data: chartData } = useQuery({
    queryKey: ["agenticTeamChart", selectedTeamId],
    queryFn: () => AgenticTeamsService.getAgenticTeamChart({ teamId: selectedTeamId }),
    enabled: open && !!selectedTeamId,
  })

  const teamNodes = chartData?.nodes ?? []

  const createMutation = useMutation({
    mutationFn: (data: InputTaskCreate) => TasksService.createTask({ requestBody: data }),
    onSuccess: (task) => {
      queryClient.invalidateQueries({ queryKey: ["tasks"] })
      onOpenChange(false)
      onCreated?.(task.id)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!title.trim()) return

    const payload: InputTaskCreate = {
      original_message: description.trim() || title.trim(),
      title: title.trim(),
      priority: priority !== "normal" ? priority : undefined,
      user_workspace_id: activeWorkspaceId || undefined,
    }

    if (selectedTeamId) {
      payload.team_id = selectedTeamId
      if (selectedNodeId) {
        payload.assigned_node_id = selectedNodeId
        // Derive agent from node
        const node = teamNodes.find((n) => n.id === selectedNodeId)
        if (node) payload.selected_agent_id = node.agent_id
      }
    } else if (selectedAgentId) {
      payload.selected_agent_id = selectedAgentId
    }

    createMutation.mutate(payload)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>Create New Task</DialogTitle>
          <DialogDescription>
            Create a task and optionally assign it to an agent or team member.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="task-title">
              Title <span className="text-destructive">*</span>
            </Label>
            <Input
              id="task-title"
              placeholder="What needs to be done?"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              autoFocus
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="task-description">Description</Label>
            <Textarea
              id="task-description"
              placeholder="Optional: additional context or details..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="resize-none"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* Team selection */}
            <div className="space-y-2">
              <Label>Team</Label>
              <Select
                value={selectedTeamId || "none"}
                onValueChange={(v) => setSelectedTeamId(v === "none" ? "" : v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="No team" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">No team</SelectItem>
                  {teamsData?.data.map((team) => (
                    <SelectItem key={team.id} value={team.id}>
                      {team.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Priority */}
            <div className="space-y-2">
              <Label>Priority</Label>
              <Select value={priority} onValueChange={setPriority}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {PRIORITY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Assignee: team node or standalone agent */}
          {selectedTeamId ? (
            <div className="space-y-2">
              <Label>Assign to team member</Label>
              <Select
                value={selectedNodeId || "none"}
                onValueChange={(v) => setSelectedNodeId(v === "none" ? "" : v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Unassigned" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unassigned</SelectItem>
                  {teamNodes.map((node) => (
                    <SelectItem key={node.id} value={node.id}>
                      {node.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : (
            <div className="space-y-2">
              <Label>Assign to agent</Label>
              <Select
                value={selectedAgentId || "none"}
                onValueChange={(v) => setSelectedAgentId(v === "none" ? "" : v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Unassigned" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Unassigned</SelectItem>
                  {agentsData?.data.map((agent) => (
                    <SelectItem key={agent.id} value={agent.id}>
                      {agent.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {createMutation.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(createMutation.error as Error).message || "Failed to create task"}
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!title.trim() || createMutation.isPending}>
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
