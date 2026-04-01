import { memo } from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import { Bot, Crown, MoreVertical, Trash2, Star } from "lucide-react"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { AgenticTeamNodePublic } from "@/client"

// Map ui_color_preset values to Tailwind bg classes
const COLOR_MAP: Record<string, string> = {
  slate: "bg-slate-100 dark:bg-slate-800",
  blue: "bg-blue-100 dark:bg-blue-900/40",
  green: "bg-green-100 dark:bg-green-900/40",
  red: "bg-red-100 dark:bg-red-900/40",
  purple: "bg-purple-100 dark:bg-purple-900/40",
  orange: "bg-orange-100 dark:bg-orange-900/40",
  yellow: "bg-yellow-100 dark:bg-yellow-900/40",
  pink: "bg-pink-100 dark:bg-pink-900/40",
  indigo: "bg-indigo-100 dark:bg-indigo-900/40",
  cyan: "bg-cyan-100 dark:bg-cyan-900/40",
}

function getColorClass(preset: string | null | undefined): string {
  if (!preset) return COLOR_MAP.slate
  return COLOR_MAP[preset] ?? COLOR_MAP.slate
}

export interface AgenticTeamNodeData extends AgenticTeamNodePublic, Record<string, unknown> {
  isEditMode?: boolean
  onSetLead?: (nodeId: string) => void
  onDelete?: (nodeId: string) => void
}

export const AgenticTeamChartNode = memo(
  ({ data, id }: NodeProps) => {
    const nodeData = data as unknown as AgenticTeamNodeData
    const colorClass = getColorClass(nodeData.agent_ui_color_preset)

    return (
      <div
        className={cn(
          "rounded-lg border shadow-sm min-w-[140px] max-w-[200px] select-none",
          colorClass,
          nodeData.isEditMode
            ? "border-dashed border-muted-foreground/50 cursor-move"
            : "border-border",
          nodeData.is_lead && "ring-2 ring-yellow-400 dark:ring-yellow-500",
        )}
      >
        {/* Handles for connections */}
        <Handle
          type="target"
          position={Position.Top}
          className={cn(
            "!w-2 !h-2",
            nodeData.isEditMode ? "!bg-muted-foreground/50" : "!bg-transparent !border-0",
          )}
        />

        <div className="p-3 relative">
          {/* Lead badge */}
          {nodeData.is_lead && (
            <div
              className="absolute -top-2 -right-2 bg-yellow-400 dark:bg-yellow-500 rounded-full p-0.5"
              title="Team lead"
            >
              <Crown className="h-3 w-3 text-white" />
            </div>
          )}

          <div className="flex items-start justify-between gap-1">
            <div className="flex items-center gap-2 min-w-0">
              <Bot className="h-4 w-4 shrink-0 text-muted-foreground" />
              <span className="text-sm font-medium truncate">{nodeData.name}</span>
            </div>

            {/* Edit mode kebab menu */}
            {nodeData.isEditMode && (
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-5 w-5 shrink-0 -mr-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MoreVertical className="h-3 w-3" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      nodeData.onSetLead?.(id)
                    }}
                  >
                    <Star className="mr-2 h-4 w-4" />
                    {nodeData.is_lead ? "Unset Lead" : "Set as Lead"}
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    onClick={(e) => {
                      e.stopPropagation()
                      nodeData.onDelete?.(id)
                    }}
                    className="text-destructive focus:text-destructive"
                  >
                    <Trash2 className="mr-2 h-4 w-4" />
                    Remove Node
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            )}
          </div>
        </div>

        <Handle
          type="source"
          position={Position.Bottom}
          className={cn(
            "!w-2 !h-2",
            nodeData.isEditMode ? "!bg-muted-foreground/50" : "!bg-transparent !border-0",
          )}
        />
      </div>
    )
  },
)

AgenticTeamChartNode.displayName = "AgenticTeamChartNode"
