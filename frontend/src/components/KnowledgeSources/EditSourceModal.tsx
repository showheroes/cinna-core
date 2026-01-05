import { useForm } from "react-hook-form"
import { useQuery } from "@tanstack/react-query"

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
import { Textarea } from "@/components/ui/textarea"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import useCustomToast from "@/hooks/useCustomToast"
import { KnowledgeSourcesService, SshKeysService, UserWorkspacesService } from "@/client"
import type {
  AIKnowledgeGitRepoPublic,
  Body_update_knowledge_source_api_v1_knowledge_sources__source_id__put as UpdateSourceData,
} from "@/client"
import { Loader2 } from "lucide-react"
import { useState } from "react"

interface EditSourceModalProps {
  source: AIKnowledgeGitRepoPublic
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function EditSourceModal({ source, open, onOpenChange, onSuccess }: EditSourceModalProps) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [isSubmitting, setIsSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors },
  } = useForm<UpdateSourceData>({
    defaultValues: {
      name: source.name,
      description: source.description || "",
      branch: source.branch,
      ssh_key_id: source.ssh_key_id || undefined,
      workspace_access_type: source.workspace_access_type as "all" | "specific",
      workspace_ids: [],
    },
  })

  const workspaceAccessType = watch("workspace_access_type")
  const selectedWorkspaceIds = watch("workspace_ids") || []

  // Load SSH keys
  const { data: sshKeys } = useQuery({
    queryKey: ["ssh-keys"],
    queryFn: () => SshKeysService.readSshKeys(),
  })

  // Load workspaces
  const { data: workspaces } = useQuery({
    queryKey: ["user-workspaces"],
    queryFn: () => UserWorkspacesService.listUserWorkspaces(),
  })

  const handleWorkspaceToggle = (workspaceId: string) => {
    const currentIds = selectedWorkspaceIds || []
    if (currentIds.includes(workspaceId)) {
      setValue(
        "workspace_ids",
        currentIds.filter((id) => id !== workspaceId)
      )
    } else {
      setValue("workspace_ids", [...currentIds, workspaceId])
    }
  }

  const onSubmit = async (data: UpdateSourceData) => {
    setIsSubmitting(true)
    try {
      await KnowledgeSourcesService.updateKnowledgeSource({
        sourceId: source.id,
        requestBody: {
          ...data,
          workspace_ids: data.workspace_access_type === "specific" ? data.workspace_ids : undefined,
        },
      })
      showSuccessToast("Changes have been saved")
      onSuccess()
    } catch (error: any) {
      showErrorToast(error.message || "Failed to update knowledge source")
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Knowledge Source</DialogTitle>
          <DialogDescription>Update your knowledge source configuration</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <Input
              id="name"
              placeholder="My Documentation"
              {...register("name", { required: "Name is required" })}
            />
            {errors.name && (
              <p className="text-sm text-destructive">{errors.name.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              placeholder="Description of your knowledge source"
              {...register("description")}
            />
          </div>

          <div className="space-y-2">
            <Label>Git URL</Label>
            <Input
              value={source.git_url}
              disabled
              className="bg-muted"
            />
            <p className="text-xs text-muted-foreground">
              Git URL cannot be changed. Create a new source if you need a different repository.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="branch">Branch</Label>
            <Input
              id="branch"
              placeholder="main"
              {...register("branch")}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ssh_key_id">SSH Key (for private repos)</Label>
            <Select
              value={watch("ssh_key_id") || "none"}
              onValueChange={(value) =>
                setValue("ssh_key_id", value === "none" ? undefined : value)
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="None (for public repos)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None (for public repos)</SelectItem>
                {sshKeys?.data?.map((key) => (
                  <SelectItem key={key.id} value={key.id}>
                    {key.name} ({key.fingerprint.substring(0, 16)}...)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label>Workspace Access</Label>
            <RadioGroup
              value={workspaceAccessType}
              onValueChange={(value) => setValue("workspace_access_type", value as "all" | "specific")}
            >
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="all" id="all" />
                <Label htmlFor="all" className="font-normal">
                  All workspaces
                </Label>
              </div>
              <div className="flex items-center space-x-2">
                <RadioGroupItem value="specific" id="specific" />
                <Label htmlFor="specific" className="font-normal">
                  Specific workspaces
                </Label>
              </div>
            </RadioGroup>
          </div>

          {workspaceAccessType === "specific" && (
            <div className="space-y-2">
              <Label>Select Workspaces</Label>
              <div className="border rounded-md p-4 space-y-2 max-h-48 overflow-y-auto">
                {workspaces?.data?.map((workspace) => (
                  <div key={workspace.id} className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      id={`workspace-${workspace.id}`}
                      checked={selectedWorkspaceIds.includes(workspace.id)}
                      onChange={() => handleWorkspaceToggle(workspace.id)}
                      className="rounded border-gray-300"
                    />
                    <Label
                      htmlFor={`workspace-${workspace.id}`}
                      className="font-normal cursor-pointer"
                    >
                      {workspace.name}
                    </Label>
                  </div>
                ))}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
