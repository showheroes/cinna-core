import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2, Pencil, Check, X } from "lucide-react"

import type { UserDashboardBlockPublic, UserDashboardBlockPromptActionPublic } from "@/client"
import { DashboardsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import useCustomToast from "@/hooks/useCustomToast"

interface EditPromptActionsDialogProps {
  block: UserDashboardBlockPublic
  dashboardId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface NewAction {
  prompt_text: string
  label: string
}

export function EditPromptActionsDialog({
  block,
  dashboardId,
  open,
  onOpenChange,
}: EditPromptActionsDialogProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const [savedActions, setSavedActions] = useState<UserDashboardBlockPromptActionPublic[]>(
    block.prompt_actions ?? []
  )
  const [editingActionId, setEditingActionId] = useState<string | null>(null)
  const [editLabel, setEditLabel] = useState("")
  const [editPromptText, setEditPromptText] = useState("")
  const [showNewForm, setShowNewForm] = useState(false)
  const [newAction, setNewAction] = useState<NewAction>({ prompt_text: "", label: "" })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboardId] })
  }

  const createActionMutation = useMutation({
    mutationFn: (data: { prompt_text: string; label: string | null; sort_order: number }) =>
      DashboardsService.createPromptAction({
        dashboardId,
        blockId: block.id,
        requestBody: {
          prompt_text: data.prompt_text,
          label: data.label || null,
          sort_order: data.sort_order,
        },
      }),
    onError: () => {
      showErrorToast("Failed to save prompt action.")
    },
  })

  const updateActionMutation = useMutation({
    mutationFn: ({
      actionId,
      data,
    }: {
      actionId: string
      data: { prompt_text?: string; label?: string | null }
    }) =>
      DashboardsService.updatePromptAction({
        dashboardId,
        blockId: block.id,
        actionId,
        requestBody: data,
      }),
    onSuccess: (_data, variables) => {
      setSavedActions((prev) =>
        prev.map((a) =>
          a.id === variables.actionId
            ? {
                ...a,
                ...(variables.data.prompt_text !== undefined && { prompt_text: variables.data.prompt_text }),
                ...(variables.data.label !== undefined && { label: variables.data.label ?? "" }),
              }
            : a
        )
      )
      setEditingActionId(null)
      invalidate()
    },
    onError: () => {
      showErrorToast("Failed to update prompt action.")
    },
  })

  const deleteActionMutation = useMutation({
    mutationFn: (actionId: string) =>
      DashboardsService.deletePromptAction({
        dashboardId,
        blockId: block.id,
        actionId,
      }),
    onSuccess: (_data, actionId) => {
      setSavedActions((prev) => prev.filter((a) => a.id !== actionId))
      invalidate()
    },
    onError: () => {
      showErrorToast("Failed to delete prompt action.")
    },
  })

  const handleStartEdit = (action: UserDashboardBlockPromptActionPublic) => {
    setEditingActionId(action.id)
    setEditLabel(action.label || "")
    setEditPromptText(action.prompt_text)
  }

  const handleCancelEdit = () => {
    setEditingActionId(null)
  }

  const handleSaveEdit = () => {
    if (!editingActionId || !editPromptText.trim()) return
    const original = savedActions.find((a) => a.id === editingActionId)
    if (!original) return

    const data: { prompt_text?: string; label?: string | null } = {}
    if (editPromptText.trim() !== original.prompt_text) {
      data.prompt_text = editPromptText.trim()
    }
    if (editLabel.trim() !== (original.label || "")) {
      data.label = editLabel.trim() || null
    }
    if (Object.keys(data).length === 0) {
      setEditingActionId(null)
      return
    }
    updateActionMutation.mutate({ actionId: editingActionId, data })
  }

  const handleCreateNew = () => {
    if (!newAction.prompt_text.trim()) return
    createActionMutation.mutate(
      {
        prompt_text: newAction.prompt_text.trim(),
        label: newAction.label.trim() || null,
        sort_order: savedActions.length,
      },
      {
        onSuccess: (created) => {
          setSavedActions((prev) => [...prev, created])
          setNewAction({ prompt_text: "", label: "" })
          setShowNewForm(false)
          invalidate()
        },
      }
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Prompt Actions</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <p className="text-xs text-muted-foreground">
              Action buttons appear on hover. Clicking one starts a new agent session with the prompt.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="h-7 text-xs shrink-0 ml-2"
              onClick={() => setShowNewForm(true)}
              disabled={showNewForm}
            >
              <Plus className="h-3.5 w-3.5 mr-1" />
              Add
            </Button>
          </div>

          {/* Existing actions list - inline rows like WebappShareCard */}
          {savedActions.length === 0 && !showNewForm && (
            <p className="text-xs text-muted-foreground py-2">No prompt actions configured.</p>
          )}

          {savedActions.map((action) => {
            const isEditing = editingActionId === action.id

            if (isEditing) {
              return (
                <div key={action.id} className="rounded-lg border p-3 space-y-2">
                  <div className="space-y-1.5">
                    <Label className="text-xs">Label (optional)</Label>
                    <Input
                      placeholder="e.g. Check emails"
                      value={editLabel}
                      onChange={(e) => setEditLabel(e.target.value)}
                      className="h-7 text-xs"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Prompt Text</Label>
                    <Textarea
                      placeholder="e.g. Check my emails and update status"
                      value={editPromptText}
                      onChange={(e) => setEditPromptText(e.target.value)}
                      className="text-xs min-h-[60px] resize-none"
                    />
                  </div>
                  <div className="flex gap-1.5 justify-end">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6"
                      onClick={handleCancelEdit}
                    >
                      <X className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 text-green-600 hover:text-green-700"
                      disabled={!editPromptText.trim() || updateActionMutation.isPending}
                      onClick={handleSaveEdit}
                    >
                      <Check className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </div>
              )
            }

            return (
              <div
                key={action.id}
                className="flex items-center justify-between px-3 py-2 border rounded-lg"
              >
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-sm truncate block">
                    {action.label || <span className="italic text-muted-foreground">No label</span>}
                  </span>
                  <p className="text-xs text-muted-foreground line-clamp-1 mt-0.5">
                    {action.prompt_text}
                  </p>
                </div>
                <div className="flex items-center gap-0.5 ml-2 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6"
                    onClick={() => handleStartEdit(action)}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 text-destructive hover:text-destructive"
                    disabled={deleteActionMutation.isPending}
                    onClick={() => deleteActionMutation.mutate(action.id)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            )
          })}

          {/* New action form */}
          {showNewForm && (
            <div className="rounded-lg border p-3 space-y-2">
              <div className="space-y-1.5">
                <Label className="text-xs">Label (optional)</Label>
                <Input
                  placeholder="e.g. Check emails"
                  value={newAction.label}
                  onChange={(e) => setNewAction((prev) => ({ ...prev, label: e.target.value }))}
                  className="h-7 text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">Prompt Text</Label>
                <Textarea
                  placeholder="e.g. Check my emails and update status"
                  value={newAction.prompt_text}
                  onChange={(e) => setNewAction((prev) => ({ ...prev, prompt_text: e.target.value }))}
                  className="text-xs min-h-[60px] resize-none"
                />
              </div>
              <div className="flex gap-2">
                <Button
                  size="sm"
                  className="h-7 text-xs"
                  disabled={!newAction.prompt_text.trim() || createActionMutation.isPending}
                  onClick={handleCreateNew}
                >
                  Save
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={() => {
                    setShowNewForm(false)
                    setNewAction({ prompt_text: "", label: "" })
                  }}
                >
                  Discard
                </Button>
              </div>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
