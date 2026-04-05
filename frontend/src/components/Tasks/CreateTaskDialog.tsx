import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, Bot, X, Crown } from "lucide-react"

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
import { Switch } from "@/components/ui/switch"
import { cn } from "@/lib/utils"
import { getWorkspaceIcon } from "@/config/workspaceIcons"
import { getColorPreset } from "@/utils/colorPresets"
import useWorkspace from "@/hooks/useWorkspace"

interface CreateTaskDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: (taskId: string) => void
  defaultTeamId?: string
}

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
  const [autoExecute, setAutoExecute] = useState(true)

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setTitle("")
      setDescription("")
      setSelectedAgentId("")
      setSelectedTeamId(defaultTeamId ?? "")
      setSelectedNodeId("")
      setAutoExecute(true)
    }
  }, [open, defaultTeamId])

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

  // When team changes, auto-select the team lead
  useEffect(() => {
    if (!selectedTeamId) {
      setSelectedNodeId("")
      setSelectedAgentId("")
      return
    }
    const leadNode = teamNodes.find((n) => n.is_lead)
    if (leadNode) {
      setSelectedNodeId(leadNode.id)
      setSelectedAgentId(leadNode.agent_id)
    } else {
      setSelectedNodeId("")
      setSelectedAgentId("")
    }
  }, [selectedTeamId, teamNodes])

  const teams = teamsData?.data ?? []
  const agents = agentsData?.data ?? []
  const hasTeams = teams.length > 0

  // When a team is selected, show only agents in that team (via nodes)
  // When no team, show all agents
  const displayAgents = selectedTeamId
    ? teamNodes
        .map((node) => ({
          id: node.agent_id,
          nodeId: node.id,
          name: node.name,
          colorPreset: node.agent_ui_color_preset,
          isLead: node.is_lead,
        }))
        .sort((a, b) => (a.isLead === b.isLead ? 0 : a.isLead ? -1 : 1))
    : agents.map((agent) => ({
        id: agent.id,
        nodeId: null as string | null,
        name: agent.name,
        colorPreset: agent.ui_color_preset,
        isLead: false,
      }))

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
      auto_execute: autoExecute,
      user_workspace_id: activeWorkspaceId || undefined,
    }

    if (selectedTeamId) {
      payload.team_id = selectedTeamId
      if (selectedNodeId) {
        payload.assigned_node_id = selectedNodeId
        const node = teamNodes.find((n) => n.id === selectedNodeId)
        if (node) payload.selected_agent_id = node.agent_id
      }
    } else if (selectedAgentId) {
      payload.selected_agent_id = selectedAgentId
    }

    createMutation.mutate(payload)
  }

  const handleAgentSelect = (agentId: string, nodeId: string | null) => {
    if (selectedTeamId && nodeId) {
      const isSame = selectedNodeId === nodeId
      setSelectedNodeId(isSame ? "" : nodeId)
      setSelectedAgentId(isSame ? "" : agentId)
    } else {
      setSelectedAgentId((prev) => (prev === agentId ? "" : agentId))
    }
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

          {/* Team badges */}
          {hasTeams && (
            <div className="space-y-2">
              <Label>Team</Label>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  className={cn(
                    "cursor-pointer px-3 py-1.5 text-sm rounded-md transition-all flex items-center gap-1.5 bg-muted text-muted-foreground hover:bg-muted/80",
                    !selectedTeamId && "ring-2 ring-foreground/30"
                  )}
                  onClick={() => setSelectedTeamId("")}
                >
                  <X className="h-3.5 w-3.5" />
                  None
                </button>
                {teams.map((team) => {
                  const isSelected = selectedTeamId === team.id
                  const Icon = getWorkspaceIcon(team.icon)
                  return (
                    <button
                      type="button"
                      key={team.id}
                      className={cn(
                        "cursor-pointer px-3 py-1.5 text-sm rounded-md transition-all flex items-center gap-1.5 bg-muted text-foreground hover:bg-muted/80",
                        isSelected && "ring-2 ring-foreground/30"
                      )}
                      onClick={() => setSelectedTeamId(isSelected ? "" : team.id)}
                    >
                      <Icon className="h-3.5 w-3.5" />
                      {team.name}
                    </button>
                  )
                })}
              </div>
            </div>
          )}

          {/* Agent badges */}
          <div className="space-y-2">
            <Label>{selectedTeamId ? "Assign to team member" : "Assign to agent"}</Label>
            <div className="flex flex-wrap gap-2">
              {displayAgents.length > 0 ? (
                displayAgents.map((agent) => {
                  const preset = getColorPreset(agent.colorPreset)
                  const isSelected = selectedTeamId
                    ? selectedNodeId === agent.nodeId
                    : selectedAgentId === agent.id
                  return (
                    <button
                      type="button"
                      key={agent.nodeId ?? agent.id}
                      className={cn(
                        "cursor-pointer px-3 py-1.5 text-sm rounded-md transition-all flex items-center gap-1.5",
                        preset.badgeBg,
                        preset.badgeText,
                        preset.badgeHover,
                        isSelected && preset.badgeOutline
                      )}
                      onClick={() => handleAgentSelect(agent.id, agent.nodeId)}
                    >
                      {agent.isLead ? (
                        <Crown className="h-3.5 w-3.5" />
                      ) : (
                        <Bot className="h-3.5 w-3.5" />
                      )}
                      {agent.name}
                    </button>
                  )
                })
              ) : (
                <p className="text-sm text-muted-foreground">
                  {selectedTeamId ? "No agents in this team" : "No agents available"}
                </p>
              )}
            </div>
          </div>

          {createMutation.error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(createMutation.error as Error).message || "Failed to create task"}
              </AlertDescription>
            </Alert>
          )}

          <DialogFooter className="flex items-center !justify-between">
            <div className="flex items-center gap-2">
              <Switch
                id="auto-execute"
                checked={autoExecute}
                onCheckedChange={setAutoExecute}
                disabled={!selectedAgentId}
              />
              <Label
                htmlFor="auto-execute"
                className={cn("text-sm font-normal cursor-pointer", !selectedAgentId && "text-muted-foreground")}
                title={!selectedAgentId ? "Select an agent to enable auto-execution" : undefined}
              >
                Execute
              </Label>
            </div>
            <div className="flex gap-2">
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
            </div>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
