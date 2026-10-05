import { useQuery } from "@tanstack/react-query"
import { Loader2 } from "lucide-react"
import { useState } from "react"
import { useForm } from "react-hook-form"
import type {
  ApiError,
  AIKnowledgeGitRepoCreate as CreateSourceData,
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

import { AccessLevelRadioGroup } from "./accessLevel"

interface AddSourceModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function AddSourceModal({
  open,
  onOpenChange,
  onSuccess,
}: AddSourceModalProps) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isCheckingAccess, setIsCheckingAccess] = useState(false)
  const [accessCheckResult, setAccessCheckResult] = useState<{
    accessible: boolean
    message: string
  } | null>(null)
  const [createdSourceId, setCreatedSourceId] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    reset,
    formState: { errors },
  } = useForm<CreateSourceData>({
    defaultValues: {
      name: "",
      description: "",
      git_url: "",
      branch: "main",
      ssh_key_id: undefined,
      access_level: "private",
    },
  })

  // Load SSH keys
  const { data: sshKeys } = useQuery({
    queryKey: ["ssh-keys"],
    queryFn: () => SshKeysService.readSshKeys(),
  })

  const onSubmit = async (data: CreateSourceData) => {
    setIsSubmitting(true)
    try {
      const response = await KnowledgeSourcesService.createKnowledgeSource({
        requestBody: data,
      })
      setCreatedSourceId(response.id)
      showSuccessToast(
        "Knowledge source created. You can now check access and refresh knowledge",
      )
      // Don't close yet - allow user to check access
    } catch (error) {
      handleError.bind(showErrorToast)(error as ApiError)
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleCheckAccess = async () => {
    if (!createdSourceId) return

    setIsCheckingAccess(true)
    try {
      const result = await KnowledgeSourcesService.checkKnowledgeSourceAccess({
        sourceId: createdSourceId,
      })
      setAccessCheckResult(result)
      if (result.accessible) {
        showSuccessToast(result.message)
      } else {
        showErrorToast(result.message)
      }
    } catch (error) {
      handleError.bind(showErrorToast)(error as ApiError)
    } finally {
      setIsCheckingAccess(false)
    }
  }

  const handleClose = () => {
    reset()
    setCreatedSourceId(null)
    setAccessCheckResult(null)
    onOpenChange(false)
    if (createdSourceId) {
      onSuccess()
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Add Knowledge Source</DialogTitle>
          <DialogDescription>
            Connect a Git repository containing your knowledge articles
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="name">Name *</Label>
            <Input
              id="name"
              placeholder="My Documentation"
              {...register("name", { required: "Name is required" })}
              disabled={!!createdSourceId}
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
              disabled={!!createdSourceId}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="git_url">Git URL *</Label>
            <Input
              id="git_url"
              placeholder="git@github.com:user/repo.git or https://github.com/user/repo.git"
              {...register("git_url", { required: "Git URL is required" })}
              disabled={!!createdSourceId}
            />
            {errors.git_url && (
              <p className="text-sm text-destructive">
                {errors.git_url.message}
              </p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="branch">Branch</Label>
            <Input
              id="branch"
              placeholder="main"
              {...register("branch")}
              disabled={!!createdSourceId}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ssh_key_id">SSH Key (for private repos)</Label>
            <Select
              value={watch("ssh_key_id") || "none"}
              onValueChange={(value) =>
                setValue("ssh_key_id", value === "none" ? undefined : value)
              }
              disabled={!!createdSourceId}
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
            <Label>Access</Label>
            <AccessLevelRadioGroup
              idPrefix="add-source-access"
              value={watch("access_level") || "private"}
              onChange={(level) => setValue("access_level", level)}
              disabled={!!createdSourceId}
            />
            <p className="text-xs text-muted-foreground">
              For Shared, pick the users on the source page after it is created.
            </p>
          </div>

          {createdSourceId && accessCheckResult && (
            <div
              className={`p-4 rounded-md ${
                accessCheckResult.accessible
                  ? "bg-green-50 dark:bg-green-900/20"
                  : "bg-red-50 dark:bg-red-900/20"
              }`}
            >
              <p
                className={`text-sm ${
                  accessCheckResult.accessible
                    ? "text-green-800 dark:text-green-300"
                    : "text-red-800 dark:text-red-300"
                }`}
              >
                {accessCheckResult.message}
              </p>
            </div>
          )}

          <DialogFooter className="gap-2">
            {!createdSourceId ? (
              <>
                <Button type="button" variant="outline" onClick={handleClose}>
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Create Source
                </Button>
              </>
            ) : (
              <>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleCheckAccess}
                  disabled={isCheckingAccess}
                >
                  {isCheckingAccess && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  Check Access
                </Button>
                <Button type="button" onClick={handleClose}>
                  Done
                </Button>
              </>
            )}
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
