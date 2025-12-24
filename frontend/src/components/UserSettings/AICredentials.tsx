import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { UsersService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import useCustomToast from "@/hooks/useCustomToast"

export function AICredentialsSettings() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [anthropicKey, setAnthropicKey] = useState("")

  // Get current status
  const { data: status } = useQuery({
    queryKey: ["aiCredentialsStatus"],
    queryFn: () => UsersService.getAiCredentialsStatus(),
  })

  // Update mutation
  const updateMutation = useMutation({
    mutationFn: (key: string) =>
      UsersService.updateAiCredentials({
        requestBody: { anthropic_api_key: key }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      setAnthropicKey("")
      showSuccessToast("AI credentials updated successfully")
    },
    onError: () => {
      showErrorToast("Failed to update AI credentials")
    },
  })

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: () => UsersService.deleteAiCredentials(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      showSuccessToast("AI credentials deleted successfully")
    },
    onError: () => {
      showErrorToast("Failed to delete AI credentials")
    },
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle>AI Services Credentials</CardTitle>
        <CardDescription>
          Manage your API keys for AI services. These are used by your agents in build mode.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="anthropic-key">Anthropic API Key</Label>
          <div className="flex gap-2">
            <Input
              id="anthropic-key"
              type="password"
              placeholder={status?.has_anthropic_api_key ? "••••••••••••••••" : "sk-ant-..."}
              value={anthropicKey}
              onChange={(e) => setAnthropicKey(e.target.value)}
            />
            <Button
              onClick={() => updateMutation.mutate(anthropicKey)}
              disabled={!anthropicKey || updateMutation.isPending}
            >
              {status?.has_anthropic_api_key ? "Update" : "Save"}
            </Button>
            {status?.has_anthropic_api_key && (
              <Button
                variant="destructive"
                onClick={() => deleteMutation.mutate()}
                disabled={deleteMutation.isPending}
              >
                Delete
              </Button>
            )}
          </div>
          <p className="text-sm text-muted-foreground">
            Get your API key from{" "}
            <a
              href="https://console.anthropic.com/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline"
            >
              Anthropic Console
            </a>
          </p>
        </div>
      </CardContent>
    </Card>
  )
}
