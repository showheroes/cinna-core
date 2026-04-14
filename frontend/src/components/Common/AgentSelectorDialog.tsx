import { useState, useEffect, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Bot, Check, Search } from "lucide-react"

import { AgentsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { cn } from "@/lib/utils"
import { getColorPreset } from "@/utils/colorPresets"

export interface AgentOption {
  id: string
  name: string
  colorPreset: string | null | undefined
}

interface AgentSelectorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSelect: (agentId: string) => void
  selectedAgentId?: string | null
  /** Pass a workspace ID to scope agents to that workspace. Omit for global. */
  workspaceId?: string | null
  /** Agent IDs to exclude from the list */
  excludeAgentIds?: string[]
  /** Override the fetched agents with a custom list (skips API call) */
  agents?: AgentOption[]
  title?: string
  /** Whether selecting an already-selected agent deselects it */
  allowDeselect?: boolean
  /** Whether to close the dialog after selection */
  closeOnSelect?: boolean
}

export function AgentSelectorDialog({
  open,
  onOpenChange,
  onSelect,
  selectedAgentId,
  workspaceId,
  excludeAgentIds,
  agents: externalAgents,
  title = "Select Agent",
  allowDeselect = false,
  closeOnSelect = true,
}: AgentSelectorDialogProps) {
  const [search, setSearch] = useState("")

  // Reset search when dialog opens
  useEffect(() => {
    if (open) setSearch("")
  }, [open])

  // Fetch agents only when no external list is provided
  const { data: agentsData } = useQuery({
    queryKey: workspaceId ? ["agents", workspaceId] : ["allAgents"],
    queryFn: () =>
      AgentsService.readAgents({
        skip: 0,
        limit: 200,
        ...(workspaceId ? { userWorkspaceId: workspaceId } : {}),
      }),
    enabled: open && !externalAgents,
  })

  const allAgents: AgentOption[] = useMemo(() => {
    const source = externalAgents ?? (agentsData?.data ?? []).map((a) => ({
      id: a.id,
      name: a.name,
      colorPreset: a.ui_color_preset,
    }))

    if (!excludeAgentIds?.length) return source
    const excludeSet = new Set(excludeAgentIds)
    return source.filter((a) => !excludeSet.has(a.id))
  }, [externalAgents, agentsData, excludeAgentIds])

  const filtered = useMemo(() => {
    if (!search.trim()) return allAgents
    const q = search.toLowerCase()
    return allAgents.filter((a) => a.name.toLowerCase().includes(q))
  }, [allAgents, search])

  const handleSelect = (agentId: string) => {
    if (allowDeselect && agentId === selectedAgentId) {
      onSelect("")
    } else {
      onSelect(agentId)
    }
    if (closeOnSelect) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>

        {/* Search input */}
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search agents..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-9"
            autoFocus
          />
        </div>

        {/* Agent cloud */}
        <div className="flex flex-wrap gap-2 max-h-[300px] overflow-y-auto">
          {filtered.map((agent) => {
            const preset = getColorPreset(agent.colorPreset)
            const isSelected = selectedAgentId === agent.id
            return (
              <button
                key={agent.id}
                type="button"
                className={cn(
                  "cursor-pointer px-4 py-2 text-sm rounded-md transition-all flex items-center gap-2",
                  preset.badgeBg,
                  preset.badgeText,
                  preset.badgeHover,
                  isSelected && preset.badgeOutline,
                )}
                onClick={() => handleSelect(agent.id)}
              >
                <Bot className="h-4 w-4" />
                {agent.name}
                {isSelected && <Check className="h-4 w-4" />}
              </button>
            )
          })}
          {filtered.length === 0 && (
            <p className="text-sm text-muted-foreground py-2">
              {allAgents.length === 0
                ? "No agents available"
                : "No agents match your search"}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
