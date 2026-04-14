import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Bot } from "lucide-react"
import { AgentsService } from "@/client"
import { AgentSelectorDialog } from "@/components/Common/AgentSelectorDialog"
import type { AgentOption } from "@/components/Common/AgentSelectorDialog"
import { getColorPreset } from "@/utils/colorPresets"
import { cn } from "@/lib/utils"

interface AddNodeDialogProps {
  open: boolean
  onClose: () => void
  existingAgentIds: string[]
  onAdd: (agentId: string, isLead: boolean) => void
  isPending: boolean
}

export function AddNodeDialog({
  open,
  onClose,
  existingAgentIds,
  onAdd,
  isPending,
}: AddNodeDialogProps) {
  const [selectedAgentId, setSelectedAgentId] = useState<string>("")
  const [isLead, setIsLead] = useState(false)
  const [agentSelectorOpen, setAgentSelectorOpen] = useState(false)

  const { data: agentsData } = useQuery({
    queryKey: ["allAgents"],
    queryFn: () => AgentsService.readAgents({ limit: 200 }),
    enabled: open,
  })

  const allAgents = agentsData?.data ?? []
  const selectedAgent = allAgents.find((a) => a.id === selectedAgentId)
  const selectedPreset = selectedAgent ? getColorPreset(selectedAgent.ui_color_preset) : null

  const agentOptions: AgentOption[] = allAgents
    .filter((a) => !existingAgentIds.includes(a.id))
    .map((a) => ({ id: a.id, name: a.name, colorPreset: a.ui_color_preset }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!selectedAgentId) return
    onAdd(selectedAgentId, isLead)
    setSelectedAgentId("")
    setIsLead(false)
  }

  const handleClose = () => {
    setSelectedAgentId("")
    setIsLead(false)
    onClose()
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[400px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Add Agent Node</DialogTitle>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label>Agent</Label>
              <button
                type="button"
                onClick={() => setAgentSelectorOpen(true)}
                className={cn(
                  "flex items-center gap-1.5 px-3 py-2 rounded-md text-sm transition-all text-left",
                  selectedPreset
                    ? `${selectedPreset.badgeBg} ${selectedPreset.badgeText} ${selectedPreset.badgeHover}`
                    : "bg-muted text-muted-foreground hover:bg-muted/80"
                )}
              >
                <Bot className="h-4 w-4 shrink-0" />
                <span className="truncate">{selectedAgent?.name || "Select an agent..."}</span>
              </button>
              {selectedAgent && (
                <div className="text-xs text-muted-foreground">
                  Node name: <span className="font-medium">{selectedAgent.name}</span>
                </div>
              )}
            </div>
            <div className="flex items-center justify-between">
              <Label htmlFor="node-is-lead">Set as team lead</Label>
              <Switch
                id="node-is-lead"
                checked={isLead}
                onCheckedChange={setIsLead}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!selectedAgentId || isPending}
            >
              {isPending ? "Adding..." : "Add Node"}
            </Button>
          </DialogFooter>
        </form>

        <AgentSelectorDialog
          open={agentSelectorOpen}
          onOpenChange={setAgentSelectorOpen}
          onSelect={setSelectedAgentId}
          selectedAgentId={selectedAgentId}
          agents={agentOptions}
          title="Select Agent for Node"
        />
      </DialogContent>
    </Dialog>
  )
}
