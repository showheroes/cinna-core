import { useState, useEffect } from "react"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { Loader2, AlertTriangle, Info, RefreshCw } from "lucide-react"

import { AiCredentialsService, EnvironmentsService } from "@/client"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Card, CardContent } from "@/components/ui/card"
import useCustomToast from "@/hooks/useCustomToast"

interface AffectedEnvironmentsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  credentialId: string
  credentialName: string
}

export function AffectedEnvironmentsDialog({
  open,
  onOpenChange,
  credentialId,
  credentialName,
}: AffectedEnvironmentsDialogProps) {
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // Selection state - track selected environment IDs
  const [selectedEnvIds, setSelectedEnvIds] = useState<Set<string>>(new Set())
  const [rebuildingEnvIds, setRebuildingEnvIds] = useState<Set<string>>(new Set())

  // Fetch affected environments (only when dialog is open)
  const { data, isLoading, error } = useQuery({
    queryKey: ["affectedEnvironments", credentialId],
    queryFn: () =>
      AiCredentialsService.getAffectedEnvironments({
        credentialId,
      }),
    enabled: open,
  })

  // Auto-select all environments when data loads
  useEffect(() => {
    if (data?.environments) {
      setSelectedEnvIds(new Set(data.environments.map((env) => env.environment_id)))
    }
  }, [data])

  // Rebuild mutation (for individual or batch)
  const rebuildMutation = useMutation({
    mutationFn: async (environmentId: string) => {
      return EnvironmentsService.rebuildEnvironment({
        id: environmentId,
      })
    },
    onSuccess: (_, environmentId) => {
      // Remove from rebuilding set
      setRebuildingEnvIds((prev) => {
        const next = new Set(prev)
        next.delete(environmentId)
        return next
      })

      // Invalidate environments list to refresh statuses
      queryClient.invalidateQueries({ queryKey: ["environments"] })
    },
    onError: (error: Error, environmentId) => {
      // Remove from rebuilding set
      setRebuildingEnvIds((prev) => {
        const next = new Set(prev)
        next.delete(environmentId)
        return next
      })

      showErrorToast(`Failed to rebuild environment: ${error.message}`)
    },
  })

  // Handle individual rebuild
  const handleRebuildOne = (environmentId: string) => {
    setRebuildingEnvIds((prev) => new Set(prev).add(environmentId))
    rebuildMutation.mutate(environmentId)
  }

  // Handle batch rebuild
  const handleRebuildSelected = async () => {
    if (selectedEnvIds.size === 0) return

    const envIdsToRebuild = Array.from(selectedEnvIds)
    setRebuildingEnvIds(new Set(envIdsToRebuild))

    // Execute all rebuilds in parallel using Promise.allSettled
    const results = await Promise.allSettled(
      envIdsToRebuild.map((envId) =>
        EnvironmentsService.rebuildEnvironment({ id: envId })
      )
    )

    // Count successes and failures
    const succeeded = results.filter((r) => r.status === "fulfilled").length
    const failed = results.filter((r) => r.status === "rejected").length

    // Clear rebuilding state
    setRebuildingEnvIds(new Set())

    // Show result toast
    if (failed === 0) {
      showSuccessToast(
        `Successfully started rebuild for ${succeeded} environment${succeeded > 1 ? "s" : ""}`
      )
    } else {
      showErrorToast(
        `${succeeded} succeeded, ${failed} failed. Check console for details.`
      )
      // Log errors to console for debugging
      results.forEach((result, idx) => {
        if (result.status === "rejected") {
          console.error(`Failed to rebuild ${envIdsToRebuild[idx]}:`, result.reason)
        }
      })
    }

    // Invalidate environments list
    queryClient.invalidateQueries({ queryKey: ["environments"] })
  }

  // Toggle individual selection
  const toggleSelection = (environmentId: string) => {
    setSelectedEnvIds((prev) => {
      const next = new Set(prev)
      if (next.has(environmentId)) {
        next.delete(environmentId)
      } else {
        next.add(environmentId)
      }
      return next
    })
  }

  // Toggle select all
  const toggleSelectAll = () => {
    if (selectedEnvIds.size === data?.environments.length) {
      // Deselect all
      setSelectedEnvIds(new Set())
    } else {
      // Select all
      setSelectedEnvIds(new Set(data?.environments.map((env) => env.environment_id)))
    }
  }

  const hasRunningEnvironments = data?.environments.some((env) => env.status === "running")

  // Get status badge variant
  const getStatusVariant = (status: string) => {
    switch (status) {
      case "running":
        return "default"
      case "suspended":
        return "secondary"
      case "stopped":
        return "outline"
      case "error":
        return "destructive"
      default:
        return "secondary"
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[80vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>Environments Using "{credentialName}"</DialogTitle>
          <DialogDescription>
            {isLoading
              ? "Loading affected environments..."
              : error
              ? "Failed to load environments"
              : data && data.count > 0
              ? `${data.count} environment${data.count > 1 ? "s" : ""} use${
                  data.count === 1 ? "s" : ""
                } this credential. Rebuild them to apply the updated credentials.`
              : "No environments currently use this credential."}
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto space-y-4 py-4">
          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          )}

          {/* Error state */}
          {error && (
            <Alert variant="destructive">
              <AlertDescription>
                {(error as Error).message || "Failed to load affected environments"}
              </AlertDescription>
            </Alert>
          )}

          {/* Empty state */}
          {data && data.count === 0 && (
            <div className="text-center py-8 text-muted-foreground">
              <Info className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="text-sm">
                No environments are using this credential yet.
                <br />
                You can safely update or delete it without any impact.
              </p>
            </div>
          )}

          {/* Data loaded with environments */}
          {data && data.count > 0 && (
            <>
              {/* Warning for running environments */}
              {hasRunningEnvironments && (
                <Alert>
                  <AlertTriangle className="h-4 w-4" />
                  <AlertDescription>
                    Some environments are currently running. Rebuilding will interrupt active
                    sessions.
                  </AlertDescription>
                </Alert>
              )}

              {/* Shared users alert */}
              {data.shared_with_users.length > 0 && (
                <Alert>
                  <Info className="h-4 w-4" />
                  <AlertDescription>
                    <strong>Shared with:</strong>{" "}
                    {data.shared_with_users.map((u) => u.email).join(", ")}
                    <br />
                    <span className="text-xs text-muted-foreground">
                      These users may also have environments using this credential.
                    </span>
                  </AlertDescription>
                </Alert>
              )}

              {/* Selection bar */}
              <div className="flex items-center justify-between p-3 bg-muted rounded-lg">
                <div className="flex items-center space-x-2">
                  <Checkbox
                    id="select-all"
                    checked={
                      selectedEnvIds.size === data.environments.length &&
                      data.environments.length > 0
                    }
                    onCheckedChange={toggleSelectAll}
                  />
                  <label
                    htmlFor="select-all"
                    className="text-sm font-medium cursor-pointer"
                  >
                    Select All ({selectedEnvIds.size} of {data.environments.length})
                  </label>
                </div>
                <Button
                  onClick={handleRebuildSelected}
                  disabled={selectedEnvIds.size === 0 || rebuildingEnvIds.size > 0}
                  size="sm"
                >
                  {rebuildingEnvIds.size > 0 ? (
                    <>
                      <Loader2 className="h-3 w-3 mr-2 animate-spin" />
                      Rebuilding...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="h-3 w-3 mr-2" />
                      Rebuild Selected
                    </>
                  )}
                </Button>
              </div>

              {/* Environment list */}
              <div className="space-y-2">
                {data.environments.map((env) => {
                  const isSelected = selectedEnvIds.has(env.environment_id)
                  const isRebuilding = rebuildingEnvIds.has(env.environment_id)

                  return (
                    <Card
                      key={env.environment_id}
                      className={`${
                        isSelected ? "border-primary" : ""
                      } transition-colors`}
                    >
                      <CardContent className="p-4">
                        <div className="flex items-start space-x-3">
                          {/* Checkbox */}
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={() => toggleSelection(env.environment_id)}
                            className="mt-1"
                          />

                          {/* Environment info */}
                          <div className="flex-1 space-y-1">
                            <div className="flex items-center gap-2">
                              <h4 className="text-sm font-medium">{env.agent_name}</h4>
                              <Badge variant={getStatusVariant(env.status)}>
                                {env.status}
                              </Badge>
                            </div>
                            <p className="text-xs text-muted-foreground">
                              Instance: {env.environment_name}
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Usage: <span className="font-medium">{env.usage}</span>
                            </p>
                            <p className="text-xs text-muted-foreground">
                              Owner: {env.owner_email}
                            </p>
                          </div>

                          {/* Individual rebuild button */}
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleRebuildOne(env.environment_id)}
                            disabled={isRebuilding}
                          >
                            {isRebuilding ? (
                              <>
                                <Loader2 className="h-3 w-3 mr-1 animate-spin" />
                                Rebuilding
                              </>
                            ) : (
                              <>
                                <RefreshCw className="h-3 w-3 mr-1" />
                                Rebuild
                              </>
                            )}
                          </Button>
                        </div>
                      </CardContent>
                    </Card>
                  )
                })}
              </div>
            </>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false)
              if (rebuildingEnvIds.size > 0) {
                showSuccessToast("Rebuilds will continue in background")
              }
            }}
          >
            {rebuildingEnvIds.size > 0 ? "Close (rebuilds continue)" : "Close"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
