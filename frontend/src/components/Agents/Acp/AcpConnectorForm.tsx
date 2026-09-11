import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useForm } from "react-hook-form"
import { z } from "zod"
import {
  type ACPConnectorPublic,
  type ACPConnectorUpdate,
  AcpConnectorsService,
} from "@/client"
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
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import useCustomToast from "@/hooks/useCustomToast"
import { getErrorMessage } from "@/utils"

const schema = z.object({
  name: z.string().trim().min(1, "Enter a name").max(255),
  mode: z.enum(["conversation", "building"]),
  max_connections: z.number().int().min(1).max(100),
})
type Values = z.infer<typeof schema>

export function AcpConnectorForm({
  agentId,
  connector,
  onClose,
}: {
  agentId: string
  connector?: ACPConnectorPublic
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: connector?.name || "",
      mode: connector?.mode || "conversation",
      max_connections: connector?.max_connections || 10,
    },
  })
  const mutation = useMutation({
    mutationFn: (values: Values) => {
      if (!connector)
        return AcpConnectorsService.createAcpConnector({
          agentId,
          requestBody: values,
        })
      const requestBody: ACPConnectorUpdate = {}
      const dirty = form.formState.dirtyFields
      if (dirty.name) requestBody.name = values.name
      if (dirty.mode) requestBody.mode = values.mode
      if (dirty.max_connections)
        requestBody.max_connections = values.max_connections
      return AcpConnectorsService.updateAcpConnector({
        agentId,
        connectorId: connector.id,
        requestBody,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["acp-connectors", agentId] })
      showSuccessToast(
        connector ? "ACP connector updated" : "ACP connector created",
      )
      onClose()
    },
    onError: (error) =>
      showErrorToast(getErrorMessage(error, "Could not save ACP connector")),
  })
  const errors = form.formState.errors
  return (
    <Dialog
      open
      onOpenChange={(open) => !open && !mutation.isPending && onClose()}
    >
      <DialogContent className="max-h-[85vh] overflow-y-auto overflow-x-hidden pr-2 sm:max-w-md [&>*]:min-w-0">
        <DialogHeader>
          <DialogTitle>
            {connector ? "Edit ACP connector" : "New ACP connector"}
          </DialogTitle>
          <DialogDescription>
            Configure access for an external ACP application.
          </DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
        >
          <fieldset disabled={mutation.isPending} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="acp-name">Name</Label>
              <Input
                id="acp-name"
                maxLength={255}
                {...form.register("name")}
                aria-invalid={!!errors.name}
                aria-describedby={errors.name ? "acp-name-error" : undefined}
              />
              {errors.name && (
                <p id="acp-name-error" className="text-sm text-destructive">
                  {errors.name.message}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="acp-mode">Mode</Label>
              <Select
                value={form.watch("mode")}
                onValueChange={(value: Values["mode"]) =>
                  form.setValue("mode", value, { shouldDirty: true })
                }
                disabled={mutation.isPending}
              >
                <SelectTrigger id="acp-mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="conversation">Conversation</SelectItem>
                  <SelectItem value="building">Building</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Building mode can modify the agent. Changing mode requires
                clients to start a new conversation.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="acp-limit">Maximum connections</Label>
              <Input
                id="acp-limit"
                type="number"
                min={1}
                max={100}
                {...form.register("max_connections", { valueAsNumber: true })}
                aria-invalid={!!errors.max_connections}
                aria-describedby={
                  errors.max_connections ? "acp-limit-error" : undefined
                }
              />
              {errors.max_connections && (
                <p id="acp-limit-error" className="text-sm text-destructive">
                  Enter a whole number between 1 and 100.
                </p>
              )}
            </div>
          </fieldset>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              disabled={mutation.isPending}
              onClick={onClose}
            >
              Cancel
            </Button>
            <LoadingButton
              type="submit"
              loading={mutation.isPending}
              disabled={!!connector && !form.formState.isDirty}
            >
              {mutation.isPending
                ? connector
                  ? "Saving…"
                  : "Creating…"
                : connector
                  ? "Save changes"
                  : "Create connector"}
            </LoadingButton>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
