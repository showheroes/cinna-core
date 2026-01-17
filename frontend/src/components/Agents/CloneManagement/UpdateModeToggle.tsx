import { useMutation, useQueryClient } from "@tanstack/react-query"

import { AgentSharesService } from "@/client"
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"

interface UpdateModeToggleProps {
  agentId: string
  currentMode: string
}

export function UpdateModeToggle({ agentId, currentMode }: UpdateModeToggleProps) {
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: (mode: string) =>
      AgentSharesService.setUpdateMode({
        agentId,
        requestBody: { update_mode: mode },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent", agentId] })
    },
  })

  const isAutomatic = currentMode === "automatic"

  return (
    <div className="flex items-center justify-between p-4 border rounded-lg">
      <div>
        <Label htmlFor="update-mode" className="font-medium">
          Automatic Updates
        </Label>
        <p className="text-sm text-muted-foreground">
          {isAutomatic
            ? "Updates from the parent are applied automatically"
            : "You'll be notified when updates are available"
          }
        </p>
      </div>
      <Switch
        id="update-mode"
        checked={isAutomatic}
        onCheckedChange={(checked) =>
          mutation.mutate(checked ? "automatic" : "manual")
        }
        disabled={mutation.isPending}
      />
    </div>
  )
}
