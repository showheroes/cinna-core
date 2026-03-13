import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Globe, MessageSquare, ClipboardList } from "lucide-react"

import { AgentsService, DashboardsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import { getColorPreset } from "@/utils/colorPresets"
import useCustomToast from "@/hooks/useCustomToast"

interface AddBlockDialogProps {
  dashboardId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ViewType = "latest_session" | "latest_tasks" | "webapp"

const VIEW_TYPES: { value: ViewType; label: string; icon: React.ElementType; description: string }[] = [
  { value: "latest_session", label: "Latest Session", icon: MessageSquare, description: "Shows the most recent session for this agent" },
  { value: "latest_tasks", label: "Latest Tasks", icon: ClipboardList, description: "Shows recent tasks" },
  { value: "webapp", label: "Web App", icon: Globe, description: "Embeds the agent's web app" },
]

export function AddBlockDialog({ dashboardId, open, onOpenChange }: AddBlockDialogProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()
  const [selectedAgentId, setSelectedAgentId] = useState<string>("")
  const [viewType, setViewType] = useState<ViewType>("latest_session")

  // Fetch all agents without workspace filter
  const { data: agentsData, isLoading: agentsLoading } = useQuery({
    queryKey: ["allAgents"],
    queryFn: () => AgentsService.readAgents({ limit: 200 }),
    enabled: open,
  })

  const agents = agentsData?.data ?? []
  const selectedAgent = agents.find((a) => a.id === selectedAgentId)
  const webappNotEnabled = viewType === "webapp" && selectedAgent && !selectedAgent.webapp_enabled

  const addBlockMutation = useMutation({
    mutationFn: () =>
      DashboardsService.addBlock({
        dashboardId,
        requestBody: {
          agent_id: selectedAgentId,
          view_type: viewType,
          title: null,
          show_border: true,
          grid_x: 0,
          grid_y: 0,
          grid_w: 2,
          grid_h: 2,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboardId] })
      onOpenChange(false)
      setSelectedAgentId("")
      setViewType("latest_session")
    },
    onError: (error: { body?: { detail?: string } }) => {
      showErrorToast(error.body?.detail || "Failed to add block")
    },
  })

  const handleAdd = () => {
    if (!selectedAgentId) return
    addBlockMutation.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add Block</DialogTitle>
        </DialogHeader>

        <div className="space-y-5">
          {/* Agent picker */}
          <div className="space-y-2">
            <Label>Agent</Label>
            <Select value={selectedAgentId} onValueChange={setSelectedAgentId} disabled={agentsLoading}>
              <SelectTrigger>
                <SelectValue placeholder={agentsLoading ? "Loading agents..." : "Select an agent"} />
              </SelectTrigger>
              <SelectContent>
                {agents.map((agent) => {
                  const colorPreset = getColorPreset(agent.ui_color_preset)
                  return (
                    <SelectItem key={agent.id} value={agent.id}>
                      <div className="flex items-center gap-2">
                        <span className={`h-2 w-2 rounded-full shrink-0 ${colorPreset.badgeBg} bg-current`} />
                        {agent.name}
                      </div>
                    </SelectItem>
                  )
                })}
              </SelectContent>
            </Select>
          </div>

          {/* View type selection */}
          <div className="space-y-2">
            <Label>View Type</Label>
            <RadioGroup
              value={viewType}
              onValueChange={(v) => setViewType(v as ViewType)}
              className="space-y-2"
            >
              {VIEW_TYPES.map(({ value, label, icon: Icon, description }) => {
                const isDisabled = value === "webapp" && selectedAgent && !selectedAgent.webapp_enabled

                return (
                  <Tooltip key={value} delayDuration={0}>
                    <TooltipTrigger asChild>
                      <div
                        className={`flex items-center gap-3 rounded-lg border p-3 transition-colors cursor-pointer ${
                          viewType === value ? "border-primary bg-accent" : "hover:bg-muted/50"
                        } ${isDisabled ? "opacity-50 cursor-not-allowed" : ""}`}
                        onClick={() => !isDisabled && setViewType(value)}
                      >
                        <RadioGroupItem value={value} id={value} disabled={!!isDisabled} />
                        <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                        <div className="flex-1 min-w-0">
                          <Label htmlFor={value} className="text-sm font-medium cursor-pointer">
                            {label}
                          </Label>
                          <p className="text-xs text-muted-foreground">{description}</p>
                        </div>
                      </div>
                    </TooltipTrigger>
                    {isDisabled && (
                      <TooltipContent>
                        Web App is not enabled for this agent. Enable it in agent settings first.
                      </TooltipContent>
                    )}
                  </Tooltip>
                )
              })}
            </RadioGroup>
          </div>

          {webappNotEnabled && (
            <p className="text-xs text-destructive">
              Web App is not enabled for this agent.
            </p>
          )}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleAdd}
            disabled={!selectedAgentId || !!webappNotEnabled || addBlockMutation.isPending}
          >
            Add Block
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
