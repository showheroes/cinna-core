import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2, AlertCircle, MessageCircle, Wrench } from "lucide-react"
import { UsersService } from "@/client"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import useCustomToast from "@/hooks/useCustomToast"

// SDK options
const SDK_OPTIONS = [
  { id: "claude-code/anthropic", name: "Anthropic Claude", requiredKey: "anthropic" },
  { id: "claude-code/minimax", name: "MiniMax M2", requiredKey: "minimax" },
  { id: "google-adk-wr/openai-compatible", name: "OpenAI Compatible", requiredKey: "openai_compatible" },
]

function getSDKDisplayName(sdkId: string | null | undefined): string {
  const sdk = SDK_OPTIONS.find(s => s.id === sdkId)
  return sdk?.name || "Anthropic Claude"
}

export function AICredentialsSettings() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [anthropicKey, setAnthropicKey] = useState("")
  const [minimaxKey, setMinimaxKey] = useState("")
  // OpenAI Compatible credentials
  const [openaiCompatibleKey, setOpenaiCompatibleKey] = useState("")
  const [openaiCompatibleUrl, setOpenaiCompatibleUrl] = useState("")
  const [openaiCompatibleModel, setOpenaiCompatibleModel] = useState("")

  // Get current status
  const { data: status } = useQuery({
    queryKey: ["aiCredentialsStatus"],
    queryFn: () => UsersService.getAiCredentialsStatus(),
  })

  // Get full credentials (for non-secret values like URL and model)
  const { data: credentials } = useQuery({
    queryKey: ["aiCredentials"],
    queryFn: () => UsersService.getAiCredentials(),
  })

  // Initialize OpenAI Compatible fields when credentials are loaded
  useEffect(() => {
    if (credentials) {
      setOpenaiCompatibleUrl(credentials.openai_compatible_base_url || "")
      setOpenaiCompatibleModel(credentials.openai_compatible_model || "")
    }
  }, [credentials])

  // Update Anthropic mutation
  const updateAnthropicMutation = useMutation({
    mutationFn: (key: string) =>
      UsersService.updateAiCredentials({
        requestBody: { anthropic_api_key: key }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      setAnthropicKey("")
      showSuccessToast("Anthropic API key updated successfully")
    },
    onError: () => {
      showErrorToast("Failed to update Anthropic API key")
    },
  })

  // Update MiniMax mutation
  const updateMinimaxMutation = useMutation({
    mutationFn: (key: string) =>
      UsersService.updateAiCredentials({
        requestBody: { minimax_api_key: key }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      setMinimaxKey("")
      showSuccessToast("MiniMax API key updated successfully")
    },
    onError: () => {
      showErrorToast("Failed to update MiniMax API key")
    },
  })

  // Delete Anthropic mutation
  const deleteAnthropicMutation = useMutation({
    mutationFn: () =>
      UsersService.updateAiCredentials({
        requestBody: { anthropic_api_key: "" }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      showSuccessToast("Anthropic API key deleted successfully")
    },
    onError: () => {
      showErrorToast("Failed to delete Anthropic API key")
    },
  })

  // Delete MiniMax mutation
  const deleteMinimaxMutation = useMutation({
    mutationFn: () =>
      UsersService.updateAiCredentials({
        requestBody: { minimax_api_key: "" }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      showSuccessToast("MiniMax API key deleted successfully")
    },
    onError: () => {
      showErrorToast("Failed to delete MiniMax API key")
    },
  })

  // Update OpenAI Compatible mutation - only sends fields that have changed
  const updateOpenaiCompatibleMutation = useMutation({
    mutationFn: (data: { api_key?: string; base_url?: string; model?: string }) => {
      // Build request body with only non-empty fields to avoid overwriting existing values
      const requestBody: Record<string, string> = {}
      if (data.api_key) {
        requestBody.openai_compatible_api_key = data.api_key
      }
      if (data.base_url) {
        requestBody.openai_compatible_base_url = data.base_url
      }
      if (data.model) {
        requestBody.openai_compatible_model = data.model
      }
      return UsersService.updateAiCredentials({ requestBody })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      queryClient.invalidateQueries({ queryKey: ["aiCredentials"] })
      setOpenaiCompatibleKey("")
      showSuccessToast("OpenAI Compatible credentials updated successfully")
    },
    onError: () => {
      showErrorToast("Failed to update OpenAI Compatible credentials")
    },
  })

  // Delete OpenAI Compatible mutation
  const deleteOpenaiCompatibleMutation = useMutation({
    mutationFn: () =>
      UsersService.updateAiCredentials({
        requestBody: {
          openai_compatible_api_key: "",
          openai_compatible_base_url: "",
          openai_compatible_model: "",
        }
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      queryClient.invalidateQueries({ queryKey: ["aiCredentials"] })
      showSuccessToast("OpenAI Compatible credentials deleted successfully")
    },
    onError: () => {
      showErrorToast("Failed to delete OpenAI Compatible credentials")
    },
  })

  // Update SDK preferences mutation
  const updateSdkMutation = useMutation({
    mutationFn: (data: { default_sdk_conversation?: string; default_sdk_building?: string }) =>
      UsersService.updateUserMe({ requestBody: data }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      queryClient.invalidateQueries({ queryKey: ["currentUser"] })
      showSuccessToast("SDK preferences updated successfully")
    },
    onError: () => {
      showErrorToast("Failed to update SDK preferences")
    },
  })

  // Check if required API key is available for a given SDK
  const hasRequiredKey = (sdkId: string): boolean => {
    const sdk = SDK_OPTIONS.find(s => s.id === sdkId)
    if (!sdk) return false
    if (sdk.requiredKey === "anthropic") return status?.has_anthropic_api_key ?? false
    if (sdk.requiredKey === "minimax") return status?.has_minimax_api_key ?? false
    if (sdk.requiredKey === "openai_compatible") return status?.has_openai_compatible_api_key ?? false
    return false
  }

  // Get missing key warning for selected SDKs
  const getMissingKeyWarning = (): string | null => {
    const warnings: string[] = []
    const convSdk = status?.default_sdk_conversation || "claude-code/anthropic"
    const buildSdk = status?.default_sdk_building || "claude-code/anthropic"

    if (!hasRequiredKey(convSdk)) {
      warnings.push(`${getSDKDisplayName(convSdk)} (Conversation mode)`)
    }
    if (!hasRequiredKey(buildSdk) && buildSdk !== convSdk) {
      warnings.push(`${getSDKDisplayName(buildSdk)} (Building mode)`)
    } else if (!hasRequiredKey(buildSdk) && buildSdk === convSdk && !warnings.length) {
      warnings.push(`${getSDKDisplayName(buildSdk)} (Building mode)`)
    }

    if (warnings.length === 0) return null
    return `Missing API key for: ${warnings.join(", ")}`
  }

  const missingKeyWarning = getMissingKeyWarning()

  return (
    <div className="space-y-6">
      {/* Top Row - Cloud Services and SDK Preferences */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Cloud AI Services Card */}
        <Card>
          <CardHeader>
            <CardTitle>Cloud AI Services</CardTitle>
            <CardDescription>
              Manage your API keys for cloud AI services. These are used by your agents.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Anthropic API Key */}
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
                {anthropicKey && (
                  <Button
                    onClick={() => updateAnthropicMutation.mutate(anthropicKey)}
                    disabled={updateAnthropicMutation.isPending}
                  >
                    {status?.has_anthropic_api_key ? "Update" : "Save"}
                  </Button>
                )}
                {status?.has_anthropic_api_key && (
                  <Button
                    variant="destructive"
                    size="icon"
                    onClick={() => deleteAnthropicMutation.mutate()}
                    disabled={deleteAnthropicMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Get your API key from{" "}
                <a
                  href="https://console.anthropic.com/settings/keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  Anthropic Console
                </a>
              </p>
            </div>

            {/* MiniMax API Key */}
            <div className="space-y-2">
              <Label htmlFor="minimax-key">MiniMax API Key</Label>
              <div className="flex gap-2">
                <Input
                  id="minimax-key"
                  type="password"
                  placeholder={status?.has_minimax_api_key ? "••••••••••••••••" : "Enter MiniMax API key"}
                  value={minimaxKey}
                  onChange={(e) => setMinimaxKey(e.target.value)}
                />
                {minimaxKey && (
                  <Button
                    onClick={() => updateMinimaxMutation.mutate(minimaxKey)}
                    disabled={updateMinimaxMutation.isPending}
                  >
                    {status?.has_minimax_api_key ? "Update" : "Save"}
                  </Button>
                )}
                {status?.has_minimax_api_key && (
                  <Button
                    variant="destructive"
                    size="icon"
                    onClick={() => deleteMinimaxMutation.mutate()}
                    disabled={deleteMinimaxMutation.isPending}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </div>
              <p className="text-sm text-muted-foreground">
                Get your API key from{" "}
                <a
                  href="https://platform.minimax.io/user-center/basic-information/interface-key"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline"
                >
                  MiniMax Platform
                </a>
              </p>
            </div>
          </CardContent>
        </Card>

        {/* Default SDK Preferences Card */}
        <Card>
          <CardHeader>
            <CardTitle>Default SDK Preferences</CardTitle>
            <CardDescription>
              Select default AI SDKs for new environments. These can be overridden per environment.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Validation Warning */}
            {missingKeyWarning && (
              <Alert variant="destructive">
                <AlertCircle className="h-4 w-4" />
                <AlertDescription>{missingKeyWarning}</AlertDescription>
              </Alert>
            )}

            {/* Conversation Mode SDK */}
            <div className="flex items-center justify-between gap-4 py-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-blue-500/10">
                  <MessageCircle className="h-4 w-4 text-blue-500" />
                </div>
                <div>
                  <Label htmlFor="sdk-conversation" className="text-sm font-medium">
                    Conversation Mode
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Following predefined workflows
                  </p>
                </div>
              </div>
              <Select
                value={status?.default_sdk_conversation || "claude-code/anthropic"}
                onValueChange={(value) => updateSdkMutation.mutate({ default_sdk_conversation: value })}
                disabled={updateSdkMutation.isPending}
              >
                <SelectTrigger id="sdk-conversation" className="w-[180px]">
                  <SelectValue placeholder="Select SDK" />
                </SelectTrigger>
                <SelectContent>
                  {SDK_OPTIONS.map((sdk) => (
                    <SelectItem key={sdk.id} value={sdk.id}>
                      {sdk.name}
                      {!hasRequiredKey(sdk.id) && " (API key required)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Building Mode SDK */}
            <div className="flex items-center justify-between gap-4 py-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-orange-500/10">
                  <Wrench className="h-4 w-4 text-orange-500" />
                </div>
                <div>
                  <Label htmlFor="sdk-building" className="text-sm font-medium">
                    Building Mode
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Building workflows and integrations
                  </p>
                </div>
              </div>
              <Select
                value={status?.default_sdk_building || "claude-code/anthropic"}
                onValueChange={(value) => updateSdkMutation.mutate({ default_sdk_building: value })}
                disabled={updateSdkMutation.isPending}
              >
                <SelectTrigger id="sdk-building" className="w-[180px]">
                  <SelectValue placeholder="Select SDK" />
                </SelectTrigger>
                <SelectContent>
                  {SDK_OPTIONS.map((sdk) => (
                    <SelectItem key={sdk.id} value={sdk.id}>
                      {sdk.name}
                      {!hasRequiredKey(sdk.id) && " (API key required)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom Row - OpenAI Compatible AI Service */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <CardTitle>OpenAI Compatible AI Service</CardTitle>
            <CardDescription>
              Configure an OpenAI-compatible endpoint (e.g., Ollama, vLLM, or self-hosted models).
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Base URL */}
            <div className="space-y-2">
              <Label htmlFor="openai-compatible-url">Base URL</Label>
              <div className="flex gap-2">
                <Input
                  id="openai-compatible-url"
                  type="text"
                  placeholder="https://openai.mycompany.com/api/v1"
                  value={openaiCompatibleUrl}
                  onChange={(e) => setOpenaiCompatibleUrl(e.target.value)}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                OpenAI-compatible API endpoint URL
              </p>
            </div>

            {/* API Key */}
            <div className="space-y-2">
              <Label htmlFor="openai-compatible-key">API Key</Label>
              <div className="flex gap-2">
                <Input
                  id="openai-compatible-key"
                  type="password"
                  placeholder={status?.has_openai_compatible_api_key ? "••••••••••••••••" : "Enter API key"}
                  value={openaiCompatibleKey}
                  onChange={(e) => setOpenaiCompatibleKey(e.target.value)}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                Authentication token for the API
              </p>
            </div>

            {/* Model */}
            <div className="space-y-2">
              <Label htmlFor="openai-compatible-model">Model</Label>
              <div className="flex gap-2">
                <Input
                  id="openai-compatible-model"
                  type="text"
                  placeholder="llama3.2:latest"
                  value={openaiCompatibleModel}
                  onChange={(e) => setOpenaiCompatibleModel(e.target.value)}
                />
              </div>
              <p className="text-sm text-muted-foreground">
                Model identifier (e.g., llama3.2:latest, gpt-4)
              </p>
            </div>

            <div className="flex gap-2">
              {(openaiCompatibleKey || openaiCompatibleUrl || openaiCompatibleModel) && (
                <Button
                  onClick={() => updateOpenaiCompatibleMutation.mutate({
                    api_key: openaiCompatibleKey || undefined,
                    base_url: openaiCompatibleUrl || undefined,
                    model: openaiCompatibleModel || undefined,
                  })}
                  disabled={updateOpenaiCompatibleMutation.isPending}
                >
                  {status?.has_openai_compatible_api_key ? "Update" : "Save"}
                </Button>
              )}
              {status?.has_openai_compatible_api_key && (
                <Button
                  variant="destructive"
                  size="icon"
                  onClick={() => deleteOpenaiCompatibleMutation.mutate()}
                  disabled={deleteOpenaiCompatibleMutation.isPending}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
