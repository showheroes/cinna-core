import { useState, useEffect } from "react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import useWorkspace from "@/hooks/useWorkspace"
import { WORKSPACE_ICONS } from "@/config/workspaceIcons"
import { cn } from "@/lib/utils"

interface CreateWorkspaceModalProps {
  open: boolean
  onClose: () => void
}

export function CreateWorkspaceModal({ open, onClose }: CreateWorkspaceModalProps) {
  const [workspaceName, setWorkspaceName] = useState("")
  const [selectedIcon, setSelectedIcon] = useState<string>("folder-kanban")
  const { createWorkspaceMutation } = useWorkspace()

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!open) {
      setWorkspaceName("")
      setSelectedIcon("folder-kanban")
    }
  }, [open])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!workspaceName.trim()) return

    try {
      await createWorkspaceMutation.mutateAsync({
        name: workspaceName.trim(),
        icon: selectedIcon
      })
      onClose()
    } catch (error) {
      // Error is handled by the mutation's onError callback
      console.error("Failed to create workspace:", error)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[425px]">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Create New Workspace</DialogTitle>
            <DialogDescription>
              Create a workspace to organize your agents, credentials, and sessions.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-4 py-4">
            <div className="grid gap-2">
              <Label htmlFor="workspace-name">Workspace Name</Label>
              <Input
                id="workspace-name"
                placeholder="e.g., Financial Data, Email Management"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                autoFocus
                required
              />
            </div>

            <div className="grid gap-2">
              <Label>Icon</Label>
              <div className="grid grid-cols-5 gap-2">
                {WORKSPACE_ICONS.map((iconOption) => {
                  const IconComponent = iconOption.icon
                  return (
                    <button
                      key={iconOption.name}
                      type="button"
                      onClick={() => setSelectedIcon(iconOption.name)}
                      className={cn(
                        "flex items-center justify-center p-3 rounded-md border-2 transition-colors",
                        selectedIcon === iconOption.name
                          ? "border-primary bg-primary/10"
                          : "border-muted hover:border-muted-foreground/50"
                      )}
                      title={iconOption.label}
                    >
                      <IconComponent className="h-5 w-5" />
                    </button>
                  )
                })}
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={!workspaceName.trim() || createWorkspaceMutation.isPending}
            >
              {createWorkspaceMutation.isPending ? "Creating..." : "Create Workspace"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
