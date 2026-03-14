import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"

import type { UserDashboardBlockPublic } from "@/client"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Button } from "@/components/ui/button"

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

export function EditBlockDialog({ block, dashboardId, open, onOpenChange }: EditBlockDialogProps) {
  const queryClient = useQueryClient()

  const form = useForm<EditBlockFormData>({
    resolver: zodResolver(editBlockSchema),
    defaultValues: {
      view_type: (block.view_type as "webapp" | "latest_session" | "latest_tasks") || "latest_session",
      title: block.title ?? "",
      show_border: block.show_border,
      show_header: block.show_header,
    },
  })

  const showHeader = form.watch("show_header")

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

  const onSubmit = (data: EditBlockFormData) => {
    updateBlockMutation.mutate(data)
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
              name="show_header"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between py-1">
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

            {showHeader && (
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
            )}

            <FormField
              control={form.control}
              name="show_border"
              render={({ field }) => (
                <FormItem className="flex items-center justify-between py-1">
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
