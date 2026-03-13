import { useCallback, useRef } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus } from "lucide-react"
import "react-grid-layout/css/styles.css"
import "react-resizable/css/styles.css"

import type { UserDashboardPublic, AgentPublic } from "@/client"
import { DashboardsService } from "@/client"
import { Button } from "@/components/ui/button"

import { DashboardBlock } from "./DashboardBlock"

import { ResponsiveGridLayout, useContainerWidth, type Layout } from "react-grid-layout"

const BREAKPOINTS = { lg: 1200, md: 996, sm: 768, xs: 480 }
const COLS = { lg: 12, md: 8, sm: 4, xs: 2 }
const DEBOUNCE_MS = 300

interface DashboardGridProps {
  dashboard: UserDashboardPublic
  agents: AgentPublic[]
  isEditMode: boolean
  showAddBlock: boolean
  onCloseAddBlock: () => void
  onRequestAddBlock: () => void
}

export function DashboardGrid({
  dashboard,
  agents,
  isEditMode,
  onRequestAddBlock,
}: DashboardGridProps) {
  const queryClient = useQueryClient()
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const { containerRef, width } = useContainerWidth() as { containerRef: React.RefObject<HTMLDivElement>; width: number }

  const updateLayoutMutation = useMutation({
    mutationFn: (layout: Layout) =>
      DashboardsService.updateBlockLayout({
        dashboardId: dashboard.id,
        requestBody: layout.map((l) => ({
          block_id: l.i,
          grid_x: l.x,
          grid_y: l.y,
          grid_w: l.w,
          grid_h: l.h,
        })),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboard.id] })
    },
  })

  const handleLayoutChange = useCallback(
    (currentLayout: Layout) => {
      if (!isEditMode) return
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
      debounceTimer.current = setTimeout(() => {
        updateLayoutMutation.mutate(currentLayout)
      }, DEBOUNCE_MS)
    },
    [isEditMode, updateLayoutMutation]
  )

  const agentMap = new Map(agents.map((a) => [a.id, a]))
  const blocks = dashboard.blocks ?? []

  const gridLayout: Layout = blocks.map((block) => ({
    i: block.id,
    x: block.grid_x,
    y: block.grid_y,
    w: block.grid_w,
    h: block.grid_h,
    minW: 2,
    minH: 2,
    isDraggable: isEditMode,
    isResizable: isEditMode,
  }))

  if (blocks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-center p-8">
        <div className="rounded-full bg-muted p-6 mb-4">
          <Plus className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold mb-1">No blocks yet</h3>
        <p className="text-sm text-muted-foreground mb-4">
          Add agent blocks to create your monitoring dashboard
        </p>
        <Button onClick={onRequestAddBlock}>
          <Plus className="mr-2 h-4 w-4" />
          Add Your First Block
        </Button>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto" ref={containerRef as React.Ref<HTMLDivElement>}>
      {width > 0 && (
      <ResponsiveGridLayout
        width={width}
        layouts={{ lg: gridLayout, md: gridLayout, sm: gridLayout, xs: gridLayout }}
        breakpoints={BREAKPOINTS}
        cols={COLS}
        rowHeight={120}
        dragConfig={{ enabled: isEditMode, handle: ".drag-handle", bounded: false, threshold: 3 }}
        resizeConfig={{ enabled: isEditMode, handles: ["se"] }}
        onLayoutChange={handleLayoutChange}
        margin={[8, 8]}
        containerPadding={[16, 16]}
      >
        {blocks.map((block) => (
          <div key={block.id} className="relative">
            {isEditMode && (
              <div className="drag-handle absolute left-0 right-8 top-0 h-8 cursor-grab z-10 opacity-0 hover:opacity-100 bg-primary/10 rounded-tl-lg transition-opacity" />
            )}
            <DashboardBlock
              block={block}
              agent={agentMap.get(block.agent_id)}
              dashboardId={dashboard.id}
              isEditMode={isEditMode}
            />
          </div>
        ))}
      </ResponsiveGridLayout>
      )}
    </div>
  )
}
