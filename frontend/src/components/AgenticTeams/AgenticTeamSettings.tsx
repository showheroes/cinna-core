import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  AgenticTeamsService,
  type AgenticTeamPublic,
} from "@/client"
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
import { WORKSPACE_ICONS, getWorkspaceIcon } from "@/config/workspaceIcons"
import { cn } from "@/lib/utils"
import { Pencil, Plus, Trash2 } from "lucide-react"

function IconSelector({
  value,
  onChange,
}: {
  value: string
  onChange: (icon: string) => void
}) {
  return (
    <div className="grid grid-cols-5 gap-2">
      {WORKSPACE_ICONS.map((iconOption) => {
        const IconComponent = iconOption.icon
        return (
          <button
            key={iconOption.name}
            type="button"
            onClick={() => onChange(iconOption.name)}
            className={cn(
              "flex items-center justify-center p-2.5 rounded-md border-2 transition-colors",
              value === iconOption.name
                ? "border-primary bg-primary/10"
                : "border-muted hover:border-muted-foreground/50",
            )}
            title={iconOption.label}
          >
            <IconComponent className="h-4 w-4" />
          </button>
        )
      })}
    </div>
  )
}

export function AgenticTeamFormDialog({
  open,
  onClose,
  team,
  onSubmit,
  isPending,
}: {
  open: boolean
  onClose: () => void
  team?: AgenticTeamPublic | null
  onSubmit: (name: string, icon: string, taskPrefix?: string) => void
  isPending: boolean
}) {
  const [name, setName] = useState("")
  const [icon, setIcon] = useState("users")
  const [taskPrefix, setTaskPrefix] = useState("")
  const isEdit = !!team

  useEffect(() => {
    if (open) {
      setName(team?.name ?? "")
      setIcon(team?.icon ?? "users")
      setTaskPrefix(team?.task_prefix ?? "")
    }
  }, [open, team])

  const handleTaskPrefixChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    // Only allow uppercase alphanumeric, max 10 chars
    const value = e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 10)
    setTaskPrefix(value)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    onSubmit(name.trim(), icon, taskPrefix || undefined)
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>
              {isEdit ? "Edit Agentic Team" : "Create Agentic Team"}
            </DialogTitle>
            <DialogDescription>
              {isEdit
                ? "Update the team name, icon, and task settings."
                : "Create a named agentic team to define agent orchestration topology."}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="team-name">Name</Label>
              <Input
                id="team-name"
                placeholder="e.g., Content Pipeline, IT Support Team"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
                required
              />
            </div>
            <div className="grid gap-2">
              <Label>Icon</Label>
              <IconSelector value={icon} onChange={setIcon} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="task-prefix">Task Prefix</Label>
              <Input
                id="task-prefix"
                placeholder="e.g., HR, OPS (leave empty for TASK)"
                value={taskPrefix}
                onChange={handleTaskPrefixChange}
                maxLength={10}
                className="font-mono uppercase"
              />
              <p className="text-xs text-muted-foreground">
                Custom prefix for task short codes in this team (e.g., HR&nbsp;→&nbsp;HR-1).
                Leave empty to use the default TASK prefix.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
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

export function AgenticTeamSettings() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [createOpen, setCreateOpen] = useState(false)
  const [editTeam, setEditTeam] = useState<AgenticTeamPublic | null>(null)
  const [deleteId, setDeleteId] = useState<string | null>(null)

  const { data: teamsData, isLoading } = useQuery({
    queryKey: ["agenticTeams"],
    queryFn: () => AgenticTeamsService.listAgenticTeams(),
  })

  const createMutation = useMutation({
    mutationFn: (data: { name: string; icon: string; task_prefix?: string }) =>
      AgenticTeamsService.createAgenticTeam({ requestBody: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agenticTeams"] })
      showSuccessToast("Agentic team created")
      setCreateOpen(false)
    },
    onError: () => showErrorToast("Failed to create agentic team"),
  })

  const updateMutation = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string
      data: { name?: string; icon?: string; task_prefix?: string | null }
    }) =>
      AgenticTeamsService.updateAgenticTeam({
        teamId: id,
        requestBody: data,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agenticTeams"] })
      showSuccessToast("Agentic team updated")
      setEditTeam(null)
    },
    onError: () => showErrorToast("Failed to update agentic team"),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      AgenticTeamsService.deleteAgenticTeam({ teamId: id }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agenticTeams"] })
      showSuccessToast("Agentic team deleted")
      setDeleteId(null)
    },
    onError: () => showErrorToast("Failed to delete agentic team"),
  })

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Agentic Teams</CardTitle>
          <CardDescription>
            Define agent orchestration teams — visual org-charts that wire agents together with handover prompts.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-1.5" />
            New Agentic Team
          </Button>

          {isLoading ? (
            <div className="text-sm text-muted-foreground">
              Loading agentic teams...
            </div>
          ) : teamsData && teamsData.data.length > 0 ? (
            <Table>
              <TableBody>
                {teamsData.data.map((team) => {
                  const Icon = getWorkspaceIcon(team.icon)
                  return (
                    <TableRow key={team.id} className="h-9">
                      <TableCell className="px-2 py-1">
                        <Icon className="h-4 w-4 text-muted-foreground" />
                      </TableCell>
                      <TableCell className="px-2 py-1 font-medium text-sm">{team.name}</TableCell>
                      <TableCell className="px-2 py-1 text-right">
                        <div className="flex gap-1 justify-end">
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => setEditTeam(team)}
                            title="Edit"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-7 w-7"
                            onClick={() => setDeleteId(team.id)}
                            title="Delete"
                          >
                            <Trash2 className="h-3.5 w-3.5 text-destructive" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          ) : (
            <div className="text-sm text-muted-foreground">
              No agentic teams yet. Create your first team to define agent orchestration topology.
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Team Dialog */}
      <AgenticTeamFormDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onSubmit={(name, icon, taskPrefix) =>
          createMutation.mutate({ name, icon, task_prefix: taskPrefix })
        }
        isPending={createMutation.isPending}
      />

      {/* Edit Team Dialog */}
      <AgenticTeamFormDialog
        open={!!editTeam}
        onClose={() => setEditTeam(null)}
        team={editTeam}
        onSubmit={(name, icon, taskPrefix) =>
          editTeam &&
          updateMutation.mutate({
            id: editTeam.id,
            data: { name, icon, task_prefix: taskPrefix ?? null },
          })
        }
        isPending={updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      <AlertDialog
        open={!!deleteId}
        onOpenChange={(open) => !open && setDeleteId(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Agentic Team</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure? This will delete the team and all its nodes and connections.
              This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteId && deleteMutation.mutate(deleteId)}
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
