import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { WebappInterfaceConfigService } from "@/client"
import type { AgentWebappInterfaceConfigUpdate } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"
import { Loader2 } from "lucide-react"

interface WebappInterfaceModalProps {
  agentId: string
  open: boolean
  onClose: () => void
}

export function WebappInterfaceModal({
  agentId,
  open,
  onClose,
}: WebappInterfaceModalProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const { data: config, isLoading } = useQuery({
    queryKey: ["webapp-interface-config", agentId],
    queryFn: () =>
      WebappInterfaceConfigService.getWebappInterfaceConfig({ agentId }),
    enabled: open,
  })

  const updateMutation = useMutation({
    mutationFn: (data: AgentWebappInterfaceConfigUpdate) =>
      WebappInterfaceConfigService.updateWebappInterfaceConfig({
        agentId,
        requestBody: data,
      }),
    onSuccess: () => {
      showSuccessToast("Interface settings updated")
      queryClient.invalidateQueries({
        queryKey: ["webapp-interface-config", agentId],
      })
    },
    onError: (error: any) => {
      showErrorToast(
        error?.body?.detail || "Failed to update interface settings"
      )
    },
  })

  const handleToggle = (field: "show_header" | "show_chat", value: boolean) => {
    updateMutation.mutate({ [field]: value })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Web App Interface</DialogTitle>
          <DialogDescription>
            Configure the appearance of your web app for all share links.
          </DialogDescription>
        </DialogHeader>

        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="webapp-show-header">Show Header</Label>
                <p className="text-xs text-muted-foreground">
                  Display the header bar with agent name at the top of the web
                  app
                </p>
              </div>
              <Switch
                id="webapp-show-header"
                checked={config?.show_header ?? true}
                onCheckedChange={(v) => handleToggle("show_header", v)}
                disabled={updateMutation.isPending}
              />
            </div>

            <div className="flex items-center justify-between">
              <div className="space-y-0.5">
                <Label htmlFor="webapp-show-chat">Show Chat</Label>
                <p className="text-xs text-muted-foreground">
                  Display a chat widget in the web app (coming soon)
                </p>
              </div>
              <Switch
                id="webapp-show-chat"
                checked={config?.show_chat ?? false}
                onCheckedChange={(v) => handleToggle("show_chat", v)}
                disabled={updateMutation.isPending}
              />
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
