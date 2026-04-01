import { memo, useState } from "react"
import {
  getBezierPath,
  EdgeLabelRenderer,
  type EdgeProps,
} from "@xyflow/react"
import { Pencil, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import { cn } from "@/lib/utils"

export interface AgenticTeamEdgeData extends Record<string, unknown> {
  isEditMode?: boolean
  enabled?: boolean
  onEdit?: (edgeId: string) => void
  onDelete?: (edgeId: string) => void
}

export const AgenticTeamChartEdge = memo(
  ({
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    markerEnd,
  }: EdgeProps) => {
    const edgeData = data as unknown as AgenticTeamEdgeData | undefined
    const isEditMode = edgeData?.isEditMode ?? false
    const isEnabled = edgeData?.enabled ?? true
    const [hovering, setHovering] = useState(false)
    const [popoverOpen, setPopoverOpen] = useState(false)

    const [edgePath, labelX, labelY] = getBezierPath({
      sourceX,
      sourceY,
      sourcePosition,
      targetX,
      targetY,
      targetPosition,
    })

    return (
      <>
        {/* Visible edge path */}
        <path
          id={id}
          d={edgePath}
          fill="none"
          strokeWidth={2}
          stroke="hsl(var(--muted-foreground))"
          strokeDasharray={isEnabled ? undefined : "6 3"}
          markerEnd={markerEnd}
          className="react-flow__edge-path"
        />

        {/* Invisible thick hover zone (edit mode only) */}
        {isEditMode && (
          <path
            d={edgePath}
            fill="none"
            strokeWidth={16}
            stroke="transparent"
            onMouseEnter={() => setHovering(true)}
            onMouseLeave={() => {
              if (!popoverOpen) setHovering(false)
            }}
            className="cursor-pointer"
          />
        )}

        {/* Midpoint hover button (edit mode only) */}
        {isEditMode && (
          <EdgeLabelRenderer>
            <div
              style={{
                position: "absolute",
                transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
                pointerEvents: "all",
              }}
              className="nodrag nopan"
              onMouseEnter={() => setHovering(true)}
              onMouseLeave={() => {
                if (!popoverOpen) setHovering(false)
              }}
            >
              <Popover
                open={popoverOpen}
                onOpenChange={(open) => {
                  setPopoverOpen(open)
                  if (!open) setHovering(false)
                }}
              >
                <PopoverTrigger asChild>
                  <Button
                    variant="secondary"
                    size="icon"
                    className={cn(
                      "h-6 w-6 rounded-full transition-opacity shadow-sm",
                      hovering || popoverOpen ? "opacity-100" : "opacity-0",
                    )}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-1" align="center">
                  <div className="flex gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 text-xs"
                      onClick={() => {
                        edgeData?.onEdit?.(id)
                        setPopoverOpen(false)
                      }}
                    >
                      <Pencil className="mr-1.5 h-3.5 w-3.5" />
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-8 text-xs text-destructive hover:text-destructive"
                      onClick={() => {
                        edgeData?.onDelete?.(id)
                        setPopoverOpen(false)
                      }}
                    >
                      <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                      Delete
                    </Button>
                  </div>
                </PopoverContent>
              </Popover>
            </div>
          </EdgeLabelRenderer>
        )}
      </>
    )
  },
)

AgenticTeamChartEdge.displayName = "AgenticTeamChartEdge"
