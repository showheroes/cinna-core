import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import { DashboardsService } from "@/client"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableRow,
} from "@/components/ui/table"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import useCustomToast from "@/hooks/useCustomToast"
import { LayoutDashboard, Pencil, Plus, Trash2 } from "lucide-react"

function DashboardFormDialog({
  open,
  onClose,
  dashboard,
  onSubmit,
  isPending,
}: {
  open: boolean
  onClose: () => void
  dashboard?: { id: string; name: string; description: string | null } | null
  onSubmit: (name: string) => void
  isPending: boolean
}) {
  const [name, setName] = useState("")
  const isEdit = !!dashboard

  // Reset form when dialog opens
  if (open && name === "" && dashboard) {
    setName(dashboard.name)
  }

  const handleClose = () => {
    setName("")
    onClose()
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onSubmit(name.trim())
    setName("")
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEdit ? "Edit Dashboard" : "Create Dashboard"}
            </DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the dashboard name."
                : "Create a dashboard to monitor your agents at a glance."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="dashboard-name">Name</Label>
              <Input
                id="dashboard-name"
                placeholder="e.g., Agent Overview"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                required
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={!name.trim() || isPending}>
              {isPending
                ? isEdit
                  ? "Saving..."
                  : "Creating..."
                : isEdit
                  ? "Save"
                  : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function DashboardSettings() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [createOpen, setCreateOpen] = useState(false)
  const [editDashboard, setEditDashboard] = useState<{
    id: string
    name: string
    description: string | null
  } | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<{
    id: string
    name: string
  } | null>(null)

  const { data: dashboards, isLoading } = useQuery({
    queryKey: ["userDashboards"],
    queryFn: () => DashboardsService.listDashboards(),
  })

  const createMutation = useMutation({
    mutationFn: (name: string) =>
      DashboardsService.createDashboard({
        requestBody: { name, description: null },
      }),
    onSuccess: (newDashboard) => {
      queryClient.invalidateQueries({ queryKey: ["userDashboards"] })
      showSuccessToast("Dashboard created")
      setCreateOpen(false)
      navigate({
        to: "/dashboards/$dashboardId",
        params: { dashboardId: newDashboard.id },
      })
    },
    onError: () => showErrorToast("Failed to create dashboard"),
  })

  const renameMutation = useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      DashboardsService.updateDashboard({
        dashboardId: id,
        requestBody: { name },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userDashboards"] })
      showSuccessToast("Dashboard updated")
      setEditDashboard(null)
    },
    onError: () => showErrorToast("Failed to update dashboard"),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      DashboardsService.deleteDashboard({ dashboardId: id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userDashboards"] })
      showSuccessToast("Dashboard deleted")
      setDeleteTarget(null)
    },
    onError: () => showErrorToast("Failed to delete dashboard"),
  })

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Dashboards</CardTitle>
          <CardDescription>
            Monitor your agents at a glance with custom dashboards.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            New Dashboard
          </Button>

          {isLoading ? (
            <div className="text-sm text-muted-foreground">
              Loading dashboards...
            </div>
          ) : dashboards && dashboards.length > 0 ? (
            <Table>
              <TableBody>
                {dashboards.map((d) => (
                  <TableRow key={d.id} className="h-9">
                    <TableCell className="px-2 py-1">
                      <LayoutDashboard className="h-4 w-4 text-muted-foreground" />
                    </TableCell>
                    <TableCell className="px-2 py-1 font-medium text-sm">
                      {d.name}
                    </TableCell>
                    <TableCell className="px-2 py-1 text-right">
                      <div className="flex gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() =>
                            setEditDashboard({
                              id: d.id,
                              name: d.name,
                              description: d.description ?? null,
                            })
                          }
                          title="Edit"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7"
                          onClick={() =>
                            setDeleteTarget({ id: d.id, name: d.name })
                          }
                          title="Delete"
                        >
                          <Trash2 className="h-3.5 w-3.5 text-destructive" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <div className="text-sm text-muted-foreground">
              No dashboards yet. Create your first dashboard to monitor agents.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Dashboard Dialog */}
      <DashboardFormDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={(name) => createMutation.mutate(name)}
        isPending={createMutation.isPending}
      />

      {/* Edit Dashboard Dialog */}
      <DashboardFormDialog
        open={!!editDashboard}
        onClose={() => setEditDashboard(null)}
        dashboard={editDashboard}
        onSubmit={(name) =>
          editDashboard &&
          renameMutation.mutate({ id: editDashboard.id, name })
        }
        isPending={renameMutation.isPending}
      />

      {/* Delete Confirmation */}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Dashboard</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete &ldquo;{deleteTarget?.name}
              &rdquo;? All blocks will be removed. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                deleteTarget && deleteMutation.mutate(deleteTarget.id)
              }
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
