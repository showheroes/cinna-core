import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Shield } from "lucide-react"

import type {
  ApiError,
  KnowledgeSourceAccessLevel,
  AIKnowledgeGitRepoPublic as KnowledgeSourceRead,
} from "@/client"
import { KnowledgeSourcesService } from "@/client"
import {
  UserAllowlistPicker,
  type UserAllowlistSelectedItem,
} from "@/components/Common/UserAllowlistPicker"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

import { ACCESS_LEVEL_OPTIONS, AccessLevelRadioGroup } from "./accessLevel"

interface KnowledgeSourceAccessCardProps {
  source: KnowledgeSourceRead
  sourceId: string
}

export function KnowledgeSourceAccessCard({
  source,
  sourceId,
}: KnowledgeSourceAccessCardProps) {
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const accessLevel: KnowledgeSourceAccessLevel =
    source.access_level || "private"
  const isShared = accessLevel === "shared"
  // Under the source's own key so every `["knowledge-source", sourceId]`
  // invalidation refreshes the share list too.
  const sharedUsersKey = ["knowledge-source", sourceId, "shared-users"]

  const invalidateSource = () => {
    queryClient.invalidateQueries({ queryKey: ["knowledge-source", sourceId] })
    queryClient.invalidateQueries({ queryKey: ["knowledge-sources"] })
  }

  const accessLevelMutation = useMutation({
    mutationFn: (level: KnowledgeSourceAccessLevel) =>
      KnowledgeSourcesService.updateKnowledgeSource({
        sourceId,
        requestBody: { access_level: level },
      }),
    onSuccess: (_, level) => {
      const option = ACCESS_LEVEL_OPTIONS.find((o) => o.value === level)
      showSuccessToast(
        option
          ? `Access set to ${option.label}: ${option.description.toLowerCase()}`
          : "Access updated",
      )
      invalidateSource()
    },
    onError: (error) => handleError.bind(showErrorToast)(error as ApiError),
  })

  const {
    data: sharedUsers,
    isLoading: isLoadingSharedUsers,
    isError: isSharedUsersError,
  } = useQuery({
    queryKey: sharedUsersKey,
    queryFn: () =>
      KnowledgeSourcesService.listKnowledgeSourceSharedUsers({ sourceId }),
    enabled: isShared,
  })

  const addUserMutation = useMutation({
    mutationFn: (userId: string) =>
      KnowledgeSourcesService.addKnowledgeSourceSharedUser({
        sourceId,
        requestBody: { user_id: userId },
      }),
    onSuccess: (share) => {
      showSuccessToast(`Shared with ${share.full_name || share.email}`)
      invalidateSource()
    },
    onError: (error) => handleError.bind(showErrorToast)(error as ApiError),
  })

  const removeUserMutation = useMutation({
    mutationFn: (userId: string) =>
      KnowledgeSourcesService.removeKnowledgeSourceSharedUser({
        sourceId,
        userId,
      }),
    onSuccess: () => {
      showSuccessToast("User removed from the share list")
      invalidateSource()
    },
    onError: (error) => handleError.bind(showErrorToast)(error as ApiError),
  })

  const selected: UserAllowlistSelectedItem[] = (sharedUsers ?? []).map(
    (u) => ({
      id: u.user_id,
      userId: u.user_id,
      fallbackLabel: u.full_name || u.email,
    }),
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Shield className="h-5 w-5" />
          Access
        </CardTitle>
        <CardDescription>
          Who can query this source through agents and knowledge search. Admins
          always have access.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AccessLevelRadioGroup
          idPrefix="source-access"
          value={accessLevel}
          onChange={(level) => {
            if (level !== accessLevel) accessLevelMutation.mutate(level)
          }}
          disabled={accessLevelMutation.isPending}
        />

        {isShared && (
          <div className="space-y-2 border-t pt-4">
            <Label className="text-sm font-medium">Shared with</Label>
            {isSharedUsersError ? (
              <p className="text-sm text-destructive" role="alert">
                Couldn't load the share list.
              </p>
            ) : isLoadingSharedUsers ? (
              <p className="text-sm text-muted-foreground">Loading users...</p>
            ) : (
              <UserAllowlistPicker
                label={null}
                selected={selected}
                onAdd={(user) => addUserMutation.mutate(user.id)}
                onRemove={(item) => removeUserMutation.mutate(item.userId)}
                isAdding={addUserMutation.isPending}
                isRemoving={removeUserMutation.isPending}
                searchPlaceholder="Search users to share with..."
                emptyHint="No users yet. Until you add someone, only admins can query this source."
              />
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
