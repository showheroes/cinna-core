import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Label } from "@/components/ui/label"
import { Input } from "@/components/ui/input"
import { AgentsService, UsersService, AiCredentialsService } from "@/client"
import type { AgentEnvironmentCreate, AICredentialPublic } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import { Plus, Pencil, MessageCircle, Wrench, Save } from "lucide-react"

// Environment template options
const ENV_TEMPLATE_OPTIONS = [
  { value: "python-env-advanced", label: "Python", description: "Lightweight Python environment based on slim image" },
  { value: "general-env", label: "General Purpose", description: "Full Debian environment, supports installing system packages (ffmpeg, etc.)" },
]

// SDK Engine options — engine only, not coupled to credential type
const SDK_ENGINE_OPTIONS = [
  { value: "claude-code", label: "Claude Code", description: "Anthropic's CLI agent SDK" },
  { value: "opencode", label: "OpenCode", description: "Multi-provider open-source agent (75+ providers)" },
  { value: "google-adk-wr", label: "Google ADK (simplified)", description: "Google Agent Development Kit" },
]

// Compatibility matrix: which credential types each SDK engine supports
const SDK_CREDENTIAL_COMPATIBILITY: Record<string, string[]> = {
  "claude-code": ["anthropic", "minimax"],
  "opencode": ["anthropic", "openai", "openai_compatible", "google"],
  "google-adk-wr": ["openai_compatible", "google"],
}

// Suggested models per credential type (for model override hints)
const SUGGESTED_MODELS: Record<string, string[]> = {
  anthropic: ["claude-opus-4", "claude-sonnet-4-5", "claude-haiku-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "o3", "o4-mini"],
  google: ["gemini-2.5-pro", "gemini-2.5-flash"],
  openai_compatible: [],
  minimax: [],
}

// Default SDK full ID per engine (for when "Default" credential is selected)
const DEFAULT_SDK_FOR_ENGINE: Record<string, string> = {
  "claude-code": "claude-code/anthropic",
  "opencode": "opencode/anthropic",
  "google-adk-wr": "google-adk-wr/openai-compatible",
}

// Type display names for resolved default indicator
const TYPE_DISPLAY_NAMES: Record<string, string> = {
  anthropic: "Anthropic",
  minimax: "MiniMax",
  openai_compatible: "OpenAI Compatible",
  openai: "OpenAI",
  google: "Google AI",
}

// Sentinel value for "use default credential" selection
const USE_DEFAULT_SENTINEL = "__default__"

function composeSDKId(engine: string, credential: AICredentialPublic | null): string {
  if (credential) {
    return `${engine}/${credential.type}`
  }
  return DEFAULT_SDK_FOR_ENGINE[engine] ?? `${engine}/anthropic`
}

function getCompatibleCredentials(engine: string, credentials: AICredentialPublic[]): AICredentialPublic[] {
  const compatible = SDK_CREDENTIAL_COMPATIBILITY[engine] ?? []
  return credentials.filter((c) => compatible.includes(c.type))
}

function extractEngine(sdkId: string | null | undefined): string {
  if (!sdkId) return "claude-code"
  return sdkId.includes("/") ? sdkId.split("/")[0] : sdkId
}

function getEngineLabel(engine: string): string {
  return SDK_ENGINE_OPTIONS.find((o) => o.value === engine)?.label ?? engine
}

// ============= SDK Mode Edit Dialog (for env creation) =============

interface EnvModeEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: "conversation" | "building"
  engine: string
  credentialId: string
  modelOverride: string
  credentials: AICredentialPublic[]
  onSave: (engine: string, credentialId: string, modelOverride: string) => void
}

function EnvModeEditDialog({
  open,
  onOpenChange,
  mode,
  engine: initialEngine,
  credentialId: initialCredentialId,
  modelOverride: initialModelOverride,
  credentials,
  onSave,
}: EnvModeEditDialogProps) {
  const [engine, setEngine] = useState(initialEngine)
  const [credentialId, setCredentialId] = useState(initialCredentialId)
  const [modelOverride, setModelOverride] = useState(initialModelOverride)

  useEffect(() => {
    if (open) {
      setEngine(initialEngine)
      setCredentialId(initialCredentialId)
      setModelOverride(initialModelOverride)
    }
  }, [open, initialEngine, initialCredentialId, initialModelOverride])

  const compatible = getCompatibleCredentials(engine, credentials)
  const selectedCredential = credentials.find((c) => c.id === credentialId) ?? null
  const suggestedModels = selectedCredential
    ? (SUGGESTED_MODELS[selectedCredential.type] ?? [])
    : []

  // Resolve default credential for this engine
  const { data: resolvedDefault } = useQuery({
    queryKey: ["resolveDefaultCredential", engine],
    queryFn: () => AiCredentialsService.resolveDefaultCredential({ sdkEngine: engine }),
    enabled: open && credentialId === USE_DEFAULT_SENTINEL,
  })

  const handleEngineChange = (newEngine: string) => {
    setEngine(newEngine)
    setCredentialId(USE_DEFAULT_SENTINEL)
    setModelOverride("")
  }

  const handleSave = () => {
    onSave(engine, credentialId, modelOverride)
    onOpenChange(false)
  }

  const isConversation = mode === "conversation"
  const datalistId = isConversation ? "env-conv-models" : "env-build-models"

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {isConversation ? (
              <MessageCircle className="h-4 w-4 text-blue-500" />
            ) : (
              <Wrench className="h-4 w-4 text-orange-500" />
            )}
            {isConversation ? "Conversation Mode" : "Building Mode"}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* SDK Engine */}
          <div className="space-y-1.5">
            <Label className="text-sm">SDK Engine</Label>
            <Select value={engine} onValueChange={handleEngineChange}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select engine" />
              </SelectTrigger>
              <SelectContent>
                {SDK_ENGINE_OPTIONS.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    <div>
                      <span>{opt.label}</span>
                      <span className="ml-2 text-xs text-muted-foreground">{opt.description}</span>
                    </div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Credential */}
          <div className="space-y-1.5">
            <Label className="text-sm">AI Credential</Label>
            <Select value={credentialId} onValueChange={setCredentialId}>
              <SelectTrigger className="h-9">
                <SelectValue placeholder="Select credential" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={USE_DEFAULT_SENTINEL}>Default (use account default)</SelectItem>
                {compatible.map((cred) => (
                  <SelectItem key={cred.id} value={cred.id}>
                    {cred.name}
                    {cred.is_default && " (default)"}
                    <span className="ml-1 text-xs text-muted-foreground">({cred.type})</span>
                  </SelectItem>
                ))}
                {compatible.length === 0 && (
                  <div className="py-2 px-2 text-xs text-muted-foreground">
                    No compatible credentials
                  </div>
                )}
              </SelectContent>
            </Select>
            {credentialId === USE_DEFAULT_SENTINEL && (
              <p className="text-xs text-muted-foreground">
                {resolvedDefault
                  ? `Resolved: "${resolvedDefault.name}" (${TYPE_DISPLAY_NAMES[resolvedDefault.type] || resolvedDefault.type})`
                  : "No matching default credential"}
              </p>
            )}
          </div>

          {/* Model Override */}
          <div className="space-y-1.5">
            <Label className="text-sm">
              Model Override <span className="text-muted-foreground text-xs">(optional)</span>
            </Label>
            <Input
              list={datalistId}
              value={modelOverride}
              onChange={(e) => setModelOverride(e.target.value)}
              placeholder={isConversation ? "e.g., claude-haiku-4-5" : "e.g., claude-opus-4"}
              className="h-9"
            />
            {suggestedModels.length > 0 && (
              <datalist id={datalistId}>
                {suggestedModels.map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            )}
            <p className="text-xs text-muted-foreground">
              Leave empty to use the SDK default for this mode.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave}>
            <Save className="h-3.5 w-3.5 mr-2" />
            Apply
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ============= Main Component =============

interface AddEnvironmentProps {
  agentId: string
}

export function AddEnvironment({ agentId }: AddEnvironmentProps) {
  const [open, setOpen] = useState(false)
  const [envName, setEnvName] = useState("python-env-advanced")

  // SDK state per mode
  const [sdkEngineConversation, setSdkEngineConversation] = useState("claude-code")
  const [conversationCredentialId, setConversationCredentialId] = useState<string>(USE_DEFAULT_SENTINEL)
  const [modelOverrideConversation, setModelOverrideConversation] = useState("")

  const [sdkEngineBuilding, setSdkEngineBuilding] = useState("claude-code")
  const [buildingCredentialId, setBuildingCredentialId] = useState<string>(USE_DEFAULT_SENTINEL)
  const [modelOverrideBuilding, setModelOverrideBuilding] = useState("")

  // Mode edit dialog
  const [editingMode, setEditingMode] = useState<"conversation" | "building" | null>(null)

  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const { data: credentialsStatus } = useQuery({
    queryKey: ["aiCredentialsStatus"],
    queryFn: () => UsersService.getAiCredentialsStatus(),
  })

  const { data: aiCredentials } = useQuery({
    queryKey: ["aiCredentialsList"],
    queryFn: () => AiCredentialsService.listAiCredentials(),
  })

  const allCredentials = aiCredentials?.data ?? []

  // Resolve defaults for summary display
  const { data: resolvedConvDefault } = useQuery({
    queryKey: ["resolveDefaultCredential", sdkEngineConversation],
    queryFn: () => AiCredentialsService.resolveDefaultCredential({ sdkEngine: sdkEngineConversation }),
    enabled: conversationCredentialId === USE_DEFAULT_SENTINEL,
  })

  const { data: resolvedBuildDefault } = useQuery({
    queryKey: ["resolveDefaultCredential", sdkEngineBuilding],
    queryFn: () => AiCredentialsService.resolveDefaultCredential({ sdkEngine: sdkEngineBuilding }),
    enabled: buildingCredentialId === USE_DEFAULT_SENTINEL,
  })

  // Find selected credential objects
  const selectedConversationCredential = allCredentials.find((c) => c.id === conversationCredentialId) ?? null
  const selectedBuildingCredential = allCredentials.find((c) => c.id === buildingCredentialId) ?? null

  const resetForm = () => {
    const defaultEngineConversation = extractEngine(credentialsStatus?.default_sdk_conversation)
    const defaultEngineBuilding = extractEngine(credentialsStatus?.default_sdk_building)

    setEnvName("python-env-advanced")
    setSdkEngineConversation(defaultEngineConversation || "claude-code")
    setSdkEngineBuilding(defaultEngineBuilding || "claude-code")
    setConversationCredentialId(
      credentialsStatus?.default_ai_credential_conversation_id ?? USE_DEFAULT_SENTINEL
    )
    setBuildingCredentialId(
      credentialsStatus?.default_ai_credential_building_id ?? USE_DEFAULT_SENTINEL
    )
    setModelOverrideConversation(credentialsStatus?.default_model_override_conversation ?? "")
    setModelOverrideBuilding(credentialsStatus?.default_model_override_building ?? "")
  }

  const createMutation = useMutation({
    mutationFn: (data: AgentEnvironmentCreate) =>
      AgentsService.createAgentEnvironment({ id: agentId, requestBody: data }),
    onSuccess: () => {
      showSuccessToast("The new environment has been created successfully.")
      setOpen(false)
      resetForm()
    },
    onError: (error: any) => {
      showErrorToast(error.body?.detail || error.message || "Failed to create environment")
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["environments", agentId] })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    const convIsDefault = conversationCredentialId === USE_DEFAULT_SENTINEL
    const buildIsDefault = buildingCredentialId === USE_DEFAULT_SENTINEL

    const sdkConversation = composeSDKId(
      sdkEngineConversation,
      convIsDefault ? null : selectedConversationCredential
    )
    const sdkBuilding = composeSDKId(
      sdkEngineBuilding,
      buildIsDefault ? null : selectedBuildingCredential
    )

    const useDefaultForAll = convIsDefault && buildIsDefault

    createMutation.mutate({
      env_name: envName,
      agent_sdk_conversation: sdkConversation,
      agent_sdk_building: sdkBuilding,
      model_override_conversation: modelOverrideConversation.trim() || undefined,
      model_override_building: modelOverrideBuilding.trim() || undefined,
      use_default_ai_credentials: useDefaultForAll,
      conversation_ai_credential_id: useDefaultForAll
        ? undefined
        : (convIsDefault ? undefined : (conversationCredentialId || undefined)),
      building_ai_credential_id: useDefaultForAll
        ? undefined
        : (buildIsDefault ? undefined : (buildingCredentialId || undefined)),
    })
  }

  const handleOpenChange = (isOpen: boolean) => {
    setOpen(isOpen)
    if (isOpen && credentialsStatus) {
      const defaultEngineConversation = extractEngine(credentialsStatus.default_sdk_conversation)
      const defaultEngineBuilding = extractEngine(credentialsStatus.default_sdk_building)
      setSdkEngineConversation(defaultEngineConversation)
      setSdkEngineBuilding(defaultEngineBuilding)
      setConversationCredentialId(
        credentialsStatus.default_ai_credential_conversation_id ?? USE_DEFAULT_SENTINEL
      )
      setBuildingCredentialId(
        credentialsStatus.default_ai_credential_building_id ?? USE_DEFAULT_SENTINEL
      )
      setModelOverrideConversation(credentialsStatus.default_model_override_conversation ?? "")
      setModelOverrideBuilding(credentialsStatus.default_model_override_building ?? "")
    }
  }

  const handleModeEditSave = (
    mode: "conversation" | "building",
    engine: string,
    credentialId: string,
    modelOverride: string,
  ) => {
    if (mode === "conversation") {
      setSdkEngineConversation(engine)
      setConversationCredentialId(credentialId)
      setModelOverrideConversation(modelOverride)
    } else {
      setSdkEngineBuilding(engine)
      setBuildingCredentialId(credentialId)
      setModelOverrideBuilding(modelOverride)
    }
  }

  // Build summary for display
  const buildSummaryCredential = (credentialId: string, resolvedDefault: AICredentialPublic | null | undefined): string => {
    if (credentialId === USE_DEFAULT_SENTINEL) {
      return resolvedDefault ? `Default (${resolvedDefault.name})` : "Default"
    }
    const cred = allCredentials.find((c) => c.id === credentialId)
    return cred?.name ?? "Unknown"
  }

  return (
    <>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogTrigger asChild>
          <Button className="gap-2">
            <Plus className="h-4 w-4" />
            Add Environment
          </Button>
        </DialogTrigger>
        <DialogContent className="sm:max-w-[540px]">
          <form onSubmit={handleSubmit}>
            <DialogHeader>
              <DialogTitle>Create New Environment</DialogTitle>
              <DialogDescription>
                Create a new Docker container environment for your agent.
              </DialogDescription>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              {/* Environment Template */}
              <div className="space-y-2">
                <Label htmlFor="env-template">Environment Template</Label>
                <Select value={envName} onValueChange={setEnvName}>
                  <SelectTrigger id="env-template">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ENV_TEMPLATE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {ENV_TEMPLATE_OPTIONS.find((o) => o.value === envName)?.description}
                </p>
              </div>

              {/* Conversation Mode — summary row */}
              <div className="flex items-start justify-between gap-3 rounded-md border px-3 py-2.5">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-blue-500/10 shrink-0 mt-0.5">
                    <MessageCircle className="h-3.5 w-3.5 text-blue-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground mb-0.5">Conversation</p>
                    <p className="text-sm font-medium">{getEngineLabel(sdkEngineConversation)}</p>
                    <p className="text-xs text-muted-foreground">
                      {buildSummaryCredential(conversationCredentialId, resolvedConvDefault)}
                    </p>
                    {modelOverrideConversation && (
                      <p className="text-xs text-muted-foreground">Model: {modelOverrideConversation}</p>
                    )}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => setEditingMode("conversation")}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>

              {/* Building Mode — summary row */}
              <div className="flex items-start justify-between gap-3 rounded-md border px-3 py-2.5">
                <div className="flex items-start gap-3 min-w-0">
                  <div className="flex items-center justify-center w-7 h-7 rounded-lg bg-orange-500/10 shrink-0 mt-0.5">
                    <Wrench className="h-3.5 w-3.5 text-orange-500" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-xs text-muted-foreground mb-0.5">Building</p>
                    <p className="text-sm font-medium">{getEngineLabel(sdkEngineBuilding)}</p>
                    <p className="text-xs text-muted-foreground">
                      {buildSummaryCredential(buildingCredentialId, resolvedBuildDefault)}
                    </p>
                    {modelOverrideBuilding && (
                      <p className="text-xs text-muted-foreground">Model: {modelOverrideBuilding}</p>
                    )}
                  </div>
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 shrink-0"
                  onClick={() => setEditingMode("building")}
                >
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setOpen(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? "Creating..." : "Create Environment"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Mode edit sub-dialog */}
      {editingMode && (
        <EnvModeEditDialog
          open={!!editingMode}
          onOpenChange={(isOpen) => { if (!isOpen) setEditingMode(null) }}
          mode={editingMode}
          engine={editingMode === "conversation" ? sdkEngineConversation : sdkEngineBuilding}
          credentialId={editingMode === "conversation" ? conversationCredentialId : buildingCredentialId}
          modelOverride={editingMode === "conversation" ? modelOverrideConversation : modelOverrideBuilding}
          credentials={allCredentials}
          onSave={(engine, credentialId, modelOverride) =>
            handleModeEditSave(editingMode, engine, credentialId, modelOverride)
          }
        />
      )}
    </>
  )
}
