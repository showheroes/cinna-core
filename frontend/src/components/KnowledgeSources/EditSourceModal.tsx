import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import type {
  AIKnowledgeGitRepoPublic,
  ApiError,
  AIKnowledgeGitRepoUpdate as UpdateSourceData,
} from "@/client"
import { KnowledgeSourcesService, SshKeysService } from "@/client"
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

interface EditSourceModalProps {
  source: AIKnowledgeGitRepoPublic
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function EditSourceModal({
  source,
  open,
  onOpenChange,
  onSuccess,
}: EditSourceModalProps) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [isSubmitting, setIsSubmitting] = useState(false)

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, dirtyFields },
  } = useForm<UpdateSourceData>({
    defaultValues: {
      name: source.name,
      description: source.description || "",
      branch: source.branch,
      ssh_key_id: source.ssh_key_id || undefined,
    },
  })

  // Load SSH keys
  const { data: sshKeys } = useQuery({
    queryKey: ["ssh-keys"],
    queryFn: () => SshKeysService.readSshKeys(),
  })

  // The key list holds only the current admin's keys; a source configured by
  // another admin carries an id that is not in it.
  const hasForeignKey =
    !!source.ssh_key_id &&
    sshKeys !== undefined &&
    !sshKeys.data.some((key) => key.id === source.ssh_key_id)

  const onSubmit = async (data: UpdateSourceData) => {
    setIsSubmitting(true)
    // Resending an unchanged key id resets the source to pending on the
    // backend, so the key goes out only when the user actually changed it.
    const { ssh_key_id, ...rest } = data
    const requestBody: UpdateSourceData = dirtyFields.ssh_key_id
      ? { ...rest, ssh_key_id: ssh_key_id ?? null }
      : rest
    try {
      await KnowledgeSourcesService.updateKnowledgeSource({
        sourceId: source.id,
        requestBody,
      })
      showSuccessToast("Changes have been saved")
      onSuccess()
    } catch (error) {
      handleError.bind(showErrorToast)(error as ApiError)
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Knowledge Source</DialogTitle>
          <DialogDescription>
            Update your knowledge source configuration
          </DialogDescription>
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
            <Input value={source.git_url} disabled className="bg-muted" />
            <p className="text-xs text-muted-foreground">
              Git URL cannot be changed. Create a new source if you need a
              different repository.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="branch">Branch</Label>
            <Input id="branch" placeholder="main" {...register("branch")} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ssh_key_id">SSH Key (for private repos)</Label>
            <Select
              value={watch("ssh_key_id") || "none"}
              onValueChange={(value) =>
                setValue("ssh_key_id", value === "none" ? undefined : value, {
                  shouldDirty: true,
                })
              }
            >
              <SelectTrigger>
                <SelectValue placeholder="None (for public repos)" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">None (for public repos)</SelectItem>
                {hasForeignKey && source.ssh_key_id && (
                  <SelectItem value={source.ssh_key_id} disabled>
                    Key configured by another admin
                  </SelectItem>
                )}
                {sshKeys?.data?.map((key) => (
                  <SelectItem key={key.id} value={key.id}>
                    {key.name} ({key.fingerprint.substring(0, 16)}...)
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting && (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              )}
              Save Changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
