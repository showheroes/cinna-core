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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { AgentsService } from "@/client"

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

  const { data: agentsData } = useQuery({
    queryKey: ["allAgents"],
    queryFn: () => AgentsService.readAgents({ limit: 200 }),
    enabled: open,
  })

  const availableAgents = (agentsData?.data ?? []).filter(
    (a) => !existingAgentIds.includes(a.id),
  )

  const selectedAgent = availableAgents.find((a) => a.id === selectedAgentId)

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
              <Label htmlFor="agent-select">Agent</Label>
              <Select
                value={selectedAgentId}
                onValueChange={setSelectedAgentId}
              >
                <SelectTrigger id="agent-select">
                  <SelectValue placeholder="Select an agent..." />
                </SelectTrigger>
                <SelectContent>
                  {availableAgents.length === 0 ? (
                    <SelectItem value="__empty__" disabled>
                      All your agents are already in this team
                    </SelectItem>
                  ) : (
                    availableAgents.map((agent) => (
                      <SelectItem key={agent.id} value={agent.id}>
                        {agent.name}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
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
              disabled={!selectedAgentId || selectedAgentId === "__empty__" || isPending}
            >
              {isPending ? "Adding..." : "Add Node"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
