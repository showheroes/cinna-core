import { LayoutDashboard, Check, Plus } from "lucide-react"
import { Link as RouterLink, useRouterState, useNavigate } from "@tanstack/react-router"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { DashboardsService } from "@/client"
import { cn } from "@/lib/utils"
import useCustomToast from "@/hooks/useCustomToast"

export const SidebarDashboardSwitcher = () => {
  const { isMobile, setOpenMobile } = useSidebar()
  const router = useRouterState()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const currentPath = router.location.pathname
  const { showErrorToast } = useCustomToast()

  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [newName, setNewName] = useState("")

  const { data: dashboards } = useQuery({
    queryKey: ["userDashboards"],
    queryFn: () => DashboardsService.listDashboards(),
  })

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      DashboardsService.createDashboard({ requestBody: { name, description: null } }),
    onSuccess: (newDashboard) => {
      queryClient.invalidateQueries({ queryKey: ["userDashboards"] })
      setShowCreateDialog(false)
      setNewName("")
      navigate({ to: "/dashboards/$dashboardId", params: { dashboardId: newDashboard.id } })
    },
    onError: () => showErrorToast("Failed to create dashboard"),
  })

  const currentDashboardMatch = currentPath.match(/^\/dashboards\/([^/]+)$/)
  const currentDashboardId = currentDashboardMatch?.[1]
  const activeDashboard = dashboards?.find((d) => d.id === currentDashboardId)

  const activeName = activeDashboard?.name || "Dashboards"

  const handleMenuClose = () => {
    if (isMobile) {
      setOpenMobile(false)
    }
  }

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!newName.trim()) return
    createMutation.mutate(newName.trim())
  }

  return (
    <>
      <SidebarMenuItem>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton tooltip="Dashboards">
              <LayoutDashboard className="size-4 text-muted-foreground" />
              <span>{activeName}</span>
              <span className="sr-only">Switch dashboard</span>
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            side={isMobile ? "top" : "right"}
            align="end"
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56"
          >
            {/* User dashboards */}
            {dashboards && dashboards.length > 0 ? (
              dashboards.map((dashboard) => {
                const isActive = currentDashboardId === dashboard.id
                return (
                  <DropdownMenuItem asChild key={dashboard.id}>
                    <RouterLink
                      to="/dashboards/$dashboardId"
                      params={{ dashboardId: dashboard.id }}
                      onClick={handleMenuClose}
                      className={cn(
                        "flex items-center justify-between cursor-pointer",
                        isActive && "bg-accent"
                      )}
                    >
                      <div className="flex items-center truncate">
                        <LayoutDashboard className="mr-2 h-4 w-4 shrink-0" />
                        <span className="truncate">{dashboard.name}</span>
                      </div>
                      {isActive && <Check className="h-4 w-4 shrink-0" />}
                    </RouterLink>
                  </DropdownMenuItem>
                )
              })
            ) : (
              <DropdownMenuItem disabled className="text-muted-foreground text-sm">
                No dashboards yet
              </DropdownMenuItem>
            )}

            <DropdownMenuSeparator />

            {/* Add dashboard */}
            <DropdownMenuItem onClick={() => setShowCreateDialog(true)}>
              <Plus className="mr-2 h-4 w-4" />
              New Dashboard
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>

      <Dialog open={showCreateDialog} onOpenChange={setShowCreateDialog}>
        <DialogContent className="sm:max-w-[425px]">
          <form onSubmit={handleCreateSubmit}>
            <DialogHeader>
              <DialogTitle>Create Dashboard</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label htmlFor="dashboard-name">Name</Label>
                <Input
                  id="dashboard-name"
                  placeholder="e.g., Agent Overview"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  autoFocus
                  required
                />
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setShowCreateDialog(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={!newName.trim() || createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
