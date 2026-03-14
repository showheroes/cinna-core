import { useState } from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Plus, Trash2 } from "lucide-react"

import type { UserDashboardBlockPublic, UserDashboardBlockPromptActionPublic } from "@/client"
import { DashboardsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import useCustomToast from "@/hooks/useCustomToast"

const editBlockSchema = z.object({
  view_type: z.enum(["webapp", "latest_session", "latest_tasks"]),
  title: z.string().max(255).optional().or(z.literal("")),
  show_border: z.boolean(),
  show_header: z.boolean(),
})

type EditBlockFormData = z.infer<typeof editBlockSchema>

interface EditBlockDialogProps {
  block: UserDashboardBlockPublic
  dashboardId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface PendingAction {
  // null id = new (not yet saved)
  id: string | null
  prompt_text: string
  label: string
  sort_order: number
  // Track if this is being deleted (for UX)
  isDeleting?: boolean
}

export function EditBlockDialog({ block, dashboardId, open, onOpenChange }: EditBlockDialogProps) {
  const queryClient = useQueryClient()
  const { showErrorToast } = useCustomToast()

  const form = useForm<EditBlockFormData>({
    resolver: zodResolver(editBlockSchema),
    defaultValues: {
      view_type: (block.view_type as "webapp" | "latest_session" | "latest_tasks") || "latest_session",
      title: block.title ?? "",
      show_border: block.show_border,
      show_header: block.show_header,
    },
  })

  // Local state for prompt actions (reflects current saved state + any new unsaved rows)
  const [savedActions, setSavedActions] = useState<UserDashboardBlockPromptActionPublic[]>(
    block.prompt_actions ?? []
  )
  // New actions being composed (not yet saved)
  const [newActions, setNewActions] = useState<PendingAction[]>([])

  const updateBlockMutation = useMutation({
    mutationFn: (data: EditBlockFormData) =>
      DashboardsService.updateBlock({
        dashboardId,
        blockId: block.id,
        requestBody: {
          view_type: data.view_type,
          title: data.title || null,
          show_border: data.show_border,
          show_header: data.show_header,
        },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboardId] })
      onOpenChange(false)
    },
  })

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

  const deleteActionMutation = useMutation({
    mutationFn: (actionId: string) =>
      DashboardsService.deletePromptAction({
        dashboardId,
        blockId: block.id,
        actionId,
      }),
    onSuccess: (_data, actionId) => {
      setSavedActions((prev) => prev.filter((a) => a.id !== actionId))
      queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboardId] })
    },
    onError: () => {
      showErrorToast("Failed to delete prompt action.")
    },
  })

  const onSubmit = (data: EditBlockFormData) => {
    updateBlockMutation.mutate(data)
  }

  const handleAddNewAction = () => {
    const nextSort = (savedActions.length + newActions.length)
    setNewActions((prev) => [...prev, { id: null, prompt_text: "", label: "", sort_order: nextSort }])
  }

  const handleNewActionChange = (idx: number, field: "prompt_text" | "label", value: string) => {
    setNewActions((prev) =>
      prev.map((a, i) => (i === idx ? { ...a, [field]: value } : a))
    )
  }

  const handleSaveNewAction = (idx: number) => {
    const action = newActions[idx]
    if (!action.prompt_text.trim()) return
    createActionMutation.mutate(
      {
        prompt_text: action.prompt_text.trim(),
        label: action.label.trim() || null,
        sort_order: action.sort_order,
      },
      {
        onSuccess: (created) => {
          setSavedActions((prev) => [...prev, created])
          setNewActions((prev) => prev.filter((_, i) => i !== idx))
          queryClient.invalidateQueries({ queryKey: ["userDashboard", dashboardId] })
        },
      }
    )
  }

  const handleDiscardNewAction = (idx: number) => {
    setNewActions((prev) => prev.filter((_, i) => i !== idx))
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Block</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="view_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>View Type</FormLabel>
                  <Select onValueChange={field.onChange} defaultValue={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select view type" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="latest_session">Latest Session</SelectItem>
                      <SelectItem value="latest_tasks">Latest Tasks</SelectItem>
                      <SelectItem value="webapp">Web App</SelectItem>
                    </SelectContent>
                  </Select>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="title"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Custom Title (optional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Defaults to agent name"
                      {...field}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="show_border"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-lg border p-3">
                  <FormLabel className="mb-0">Show border</FormLabel>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="show_header"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between rounded-lg border p-3">
                  <FormLabel className="mb-0">Show header</FormLabel>
                  <FormControl>
                    <Switch
                      checked={field.value}
                      onCheckedChange={field.onChange}
                    />
                  </FormControl>
                </FormItem>
              )}
            />

            <Separator />

            {/* Prompt Actions section */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <FormLabel className="text-sm font-medium">Prompt Actions</FormLabel>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-7 text-xs"
                  onClick={handleAddNewAction}
                >
                  <Plus className="h-3.5 w-3.5 mr-1" />
                  Add
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Action buttons appear on hover in view mode. Clicking one starts a new agent session with the prompt text.
              </p>

              {/* Saved actions */}
              {savedActions.map((action) => (
                <div
                  key={action.id}
                  className="flex items-start gap-2 rounded-lg border p-3 bg-muted/30"
                >
                  <div className="flex-1 space-y-1.5">
                    <p className="text-xs font-medium text-muted-foreground">
                      {action.label || <span className="italic">No label</span>}
                    </p>
                    <p className="text-xs text-foreground line-clamp-2">{action.prompt_text}</p>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0 text-muted-foreground hover:text-destructive"
                    disabled={deleteActionMutation.isPending}
                    onClick={() => deleteActionMutation.mutate(action.id)}
                    title="Delete prompt action"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              ))}

              {/* New (unsaved) actions */}
              {newActions.map((action, idx) => (
                <div key={idx} className="rounded-lg border p-3 space-y-2 bg-background">
                  <FormItem>
                    <FormLabel className="text-xs">Button Label (optional)</FormLabel>
                    <Input
                      placeholder="e.g. Check emails"
                      value={action.label}
                      onChange={(e) => handleNewActionChange(idx, "label", e.target.value)}
                      className="h-7 text-xs"
                    />
                  </FormItem>
                  <FormItem>
                    <FormLabel className="text-xs">Prompt Text</FormLabel>
                    <Textarea
                      placeholder="e.g. Check my emails and update status"
                      value={action.prompt_text}
                      onChange={(e) => handleNewActionChange(idx, "prompt_text", e.target.value)}
                      className="text-xs min-h-[60px] resize-none"
                    />
                  </FormItem>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 text-xs"
                      disabled={!action.prompt_text.trim() || createActionMutation.isPending}
                      onClick={() => handleSaveNewAction(idx)}
                    >
                      Save
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => handleDiscardNewAction(idx)}
                    >
                      Discard
                    </Button>
                  </div>
                </div>
              ))}

              {savedActions.length === 0 && newActions.length === 0 && (
                <p className="text-xs text-muted-foreground py-1">No prompt actions configured.</p>
              )}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={updateBlockMutation.isPending}>
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}
