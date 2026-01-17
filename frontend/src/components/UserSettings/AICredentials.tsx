import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Trash2, AlertCircle, MessageCircle, Wrench, Plus, Pencil, Star, Key } from "lucide-react"
import { UsersService, AiCredentialsService, AICredentialPublic, AICredentialType } from "@/client"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Alert, AlertDescription } from "@/components/ui/alert"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useCustomToast from "@/hooks/useCustomToast"
import { AICredentialDialog } from "./AICredentialDialog"

// SDK options
const SDK_OPTIONS = [
  { id: "claude-code/anthropic", name: "Anthropic Claude", requiredType: "anthropic" as AICredentialType },
  { id: "claude-code/minimax", name: "MiniMax M2", requiredType: "minimax" as AICredentialType },
  { id: "google-adk-wr/openai-compatible", name: "OpenAI Compatible", requiredType: "openai_compatible" as AICredentialType },
]

// Type display names
const TYPE_DISPLAY_NAMES: Record<AICredentialType, string> = {
  anthropic: "Anthropic",
  minimax: "MiniMax",
  openai_compatible: "OpenAI Compatible",
}

function getSDKDisplayName(sdkId: string | null | undefined): string {
  const sdk = SDK_OPTIONS.find(s => s.id === sdkId)
  return sdk?.name || "Anthropic Claude"
}

function getTypeDisplayName(type: AICredentialType): string {
  return TYPE_DISPLAY_NAMES[type] || type
}

export function AICredentialsSettings() {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // Dialog state
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingCredential, setEditingCredential] = useState<AICredentialPublic | null>(null)

  // Get current status (for SDK preferences and has_* flags)
  const { data: status } = useQuery({
    queryKey: ["aiCredentialsStatus"],
    queryFn: () => UsersService.getAiCredentialsStatus(),
  })

  // Get list of named credentials
  const { data: credentialsList, isLoading: isLoadingCredentials } = useQuery({
    queryKey: ["aiCredentialsList"],
    queryFn: () => AiCredentialsService.listAiCredentials(),
  })

  // Delete credential mutation
  const deleteMutation = useMutation({
    mutationFn: (credentialId: string) =>
      AiCredentialsService.deleteAiCredential({ credentialId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsList"] })
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      showSuccessToast("AI credential deleted successfully")
    },
    onError: () => {
      showErrorToast("Failed to delete AI credential")
    },
  })

  // Set default mutation
  const setDefaultMutation = useMutation({
    mutationFn: (credentialId: string) =>
      AiCredentialsService.setAiCredentialDefault({ credentialId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsList"] })
      queryClient.invalidateQueries({ queryKey: ["aiCredentialsStatus"] })
      showSuccessToast("Default credential updated")
    },
    onError: () => {
      showErrorToast("Failed to set default credential")
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

  // Check if we have a default credential for a given type
  const hasDefaultForType = (type: AICredentialType): boolean => {
    return credentialsList?.data.some(c => c.type === type && c.is_default) ?? false
  }

  // Check if required API key is available for a given SDK
  const hasRequiredKey = (sdkId: string): boolean => {
    const sdk = SDK_OPTIONS.find(s => s.id === sdkId)
    if (!sdk) return false
    return hasDefaultForType(sdk.requiredType)
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
    return `Missing default credential for: ${warnings.join(", ")}`
  }

  const missingKeyWarning = getMissingKeyWarning()

  const handleAddCredential = () => {
    setEditingCredential(null)
    setDialogOpen(true)
  }

  const handleEditCredential = (credential: AICredentialPublic) => {
    setEditingCredential(credential)
    setDialogOpen(true)
  }

  const credentials = credentialsList?.data || []

  return (
    <div className="space-y-6">
      {/* Top Row - Credentials List and SDK Preferences */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Named Credentials Card */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>AI Credentials</CardTitle>
                <CardDescription>
                  Manage named API credentials for AI providers.
                </CardDescription>
              </div>
              <Button onClick={handleAddCredential} size="sm">
                <Plus className="h-4 w-4 mr-2" />
                Add
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {isLoadingCredentials ? (
              <p className="text-sm text-muted-foreground">Loading credentials...</p>
            ) : credentials.length === 0 ? (
              <div className="text-sm text-muted-foreground py-6 text-center">
                <Key className="h-8 w-8 mx-auto mb-2 opacity-50" />
                <p>No credentials yet</p>
                <p className="text-xs mt-1">Add your first AI credential to get started</p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {credentials.map((cred) => (
                  <div
                    key={cred.id}
                    className="flex items-center justify-between px-3 py-2 border rounded-lg"
                  >
                    {/* Left: name and default badge */}
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium text-sm truncate">{cred.name}</span>
                      {cred.is_default && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Star className="h-3.5 w-3.5 text-amber-500 shrink-0 fill-amber-500" />
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              Default credential
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                    </div>
                    {/* Right: type info and actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      <TooltipProvider>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <span className="text-xs text-muted-foreground cursor-help">
                              {getTypeDisplayName(cred.type)}
                            </span>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="text-xs">
                            {cred.type === "openai_compatible" && cred.base_url ? (
                              <div>
                                <div>{cred.base_url}</div>
                                {cred.model && <div>Model: {cred.model}</div>}
                              </div>
                            ) : (
                              getTypeDisplayName(cred.type)
                            )}
                          </TooltipContent>
                        </Tooltip>
                      </TooltipProvider>
                      {!cred.is_default && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-7 w-7"
                                onClick={() => setDefaultMutation.mutate(cred.id)}
                                disabled={setDefaultMutation.isPending}
                              >
                                <Star className="h-3.5 w-3.5" />
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              Set as default
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => handleEditCredential(cred)}
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7"
                        onClick={() => deleteMutation.mutate(cred.id)}
                        disabled={deleteMutation.isPending}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" />
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
                      {!hasRequiredKey(sdk.id) && " (no default)"}
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
                      {!hasRequiredKey(sdk.id) && " (no default)"}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Info about defaults */}
            <div className="text-xs text-muted-foreground pt-2 border-t">
              <p>
                When you set a credential as default, it will be automatically used for new environments
                with the matching SDK type.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Add/Edit Credential Dialog */}
      <AICredentialDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        credential={editingCredential}
      />
    </div>
  )
}
