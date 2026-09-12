import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Loader2, ShieldOff, Trash2 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import {
  type ACPConnectorPublic,
  type ACPTokenPublic,
  AcpConnectorsService,
} from "@/client"
import { CopyableValue } from "@/components/Common/CopyableValue"
import { ListRow, RowInfo } from "@/components/Common/ListRow"
import { PreviewList } from "@/components/Common/PreviewList"
import {
  formatRelativeTimestamp,
  parseTimestamp,
} from "@/components/Common/RelativeTime"
import { RowActionsMenu } from "@/components/Common/RowActionsMenu"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"
import useCustomToast from "@/hooks/useCustomToast"
import { getErrorMessage } from "@/utils"

const schema = z.object({
  label: z.string().trim().min(1, "Enter a label").max(255),
  expires_in_days: z.number().int().min(1).max(365),
})
type Values = z.infer<typeof schema>
type TokenAction = { kind: "revoke" | "delete"; token: ACPTokenPublic }

export function AcpTokensDialog({
  agentId,
  connector,
  onClose,
}: {
  agentId: string
  connector: ACPConnectorPublic
  onClose: () => void
}) {
  const [pane, setPane] = useState<"list" | "create" | "created">("list")
  const [secret, setSecret] = useState<string | null>(null)
  const [target, setTarget] = useState<TokenAction | null>(null)
  const body = useRef<HTMLDivElement>(null)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryKey = ["acp-tokens", agentId, connector.id]
  const scope = { agentId, connectorId: connector.id }
  const query = useQuery({
    queryKey,
    queryFn: () => AcpConnectorsService.listAcpTokens(scope),
  })
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { label: "", expires_in_days: 90 },
  })
  // The secret belongs only to this mounted dialog. It must never be retained
  // in the React Query mutation cache after the one-time reveal is dismissed.
  const issue = useMutation({
    mutationFn: async (requestBody: Values) => {
      const result = await AcpConnectorsService.createAcpToken({
        ...scope,
        requestBody,
      })
      setSecret(result.token)
      return result.id
    },
    gcTime: 0,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
      setPane("created")
      form.reset()
    },
    onError: (error) =>
      showErrorToast(getErrorMessage(error, "Could not issue token")),
  })
  const action = useMutation({
    mutationFn: ({ kind, token }: TokenAction) =>
      kind === "revoke"
        ? AcpConnectorsService.revokeAcpToken({
            ...scope,
            tokenId: token.id,
          }).then(() => undefined)
        : AcpConnectorsService.deleteAcpToken({
            ...scope,
            tokenId: token.id,
          }).then(() => undefined),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({ queryKey })
      setTarget(null)
      showSuccessToast(
        variables.kind === "revoke"
          ? "Access token revoked"
          : "Access token deleted",
      )
    },
    onError: (error) =>
      showErrorToast(getErrorMessage(error, "Could not update token")),
  })
  useEffect(() => {
    if (pane !== "create") body.current?.focus()
  }, [pane])
  const back = () => {
    setSecret(null)
    issue.reset()
    setPane("list")
  }
  const tokens = query.data?.data || []
  const renderToken = (token: ACPTokenPublic) => {
    const expiry = parseTimestamp(token.expires_at)
    const expired = !!expiry && expiry.getTime() <= Date.now()
    const pending = action.isPending && action.variables.token.id === token.id
    const pendingLabel =
      action.variables?.kind === "revoke" ? "Revoking…" : "Deleting…"
    return (
      <ListRow
        title={token.label}
        muted={token.revoked || expired}
        status={{
          tone: token.revoked ? "off" : expired ? "warning" : "on",
          label: token.revoked ? "Revoked" : expired ? "Expired" : "Valid",
        }}
        flags={
          <RowInfo
            facts={[
              `Prefix ${token.prefix}…`,
              `Created ${formatRelativeTimestamp(token.created_at)}`,
              `Expires ${formatRelativeTimestamp(token.expires_at)}`,
              token.last_used_at
                ? `Last used ${formatRelativeTimestamp(token.last_used_at)}`
                : "Never used",
            ]}
          />
        }
      >
        {pending ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <output className="flex h-7 w-7 items-center justify-center">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                <span className="sr-only">{pendingLabel}</span>
              </output>
            </TooltipTrigger>
            <TooltipContent>{pendingLabel}</TooltipContent>
          </Tooltip>
        ) : (
          <RowActionsMenu label={`access token ${token.label}`}>
            {!token.revoked && !expired && (
              <>
                <DropdownMenuItem
                  onSelect={() => setTarget({ kind: "revoke", token })}
                >
                  <ShieldOff />
                  Revoke token
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem
              variant="destructive"
              onSelect={() => setTarget({ kind: "delete", token })}
            >
              <Trash2 />
              Delete token
            </DropdownMenuItem>
          </RowActionsMenu>
        )}
      </ListRow>
    )
  }
  return (
    <>
      <Dialog
        open
        onOpenChange={(open) => {
          if (!open && !issue.isPending && !action.isPending) {
            setSecret(null)
            onClose()
          }
        }}
      >
        <DialogContent
          ref={body}
          tabIndex={-1}
          className="max-h-[85vh] overflow-y-auto overflow-x-hidden pr-2 sm:max-w-lg [&>*]:min-w-0"
          onOpenAutoFocus={(event) => {
            event.preventDefault()
            body.current?.focus()
          }}
        >
          <DialogHeader>
            <DialogTitle className="break-words">
              {pane === "create"
                ? "Issue token"
                : pane === "created"
                  ? "Save your token"
                  : "Access tokens"}{" "}
              — {connector.name}
            </DialogTitle>
            <DialogDescription className="break-words">
              {pane === "created"
                ? "Copy this token now. You cannot view it again after leaving this screen."
                : "Give each external app its own token so you can revoke access independently."}
            </DialogDescription>
          </DialogHeader>
          {pane === "list" && (
            <>
              <div>
                <Button
                  size="sm"
                  onClick={() => setPane("create")}
                  disabled={action.isPending}
                >
                  Issue token
                </Button>
              </div>
              <div className="max-h-[45vh] overflow-y-auto pr-2">
                <PreviewList
                  items={tokens}
                  previewCount={Math.max(tokens.length, 1)}
                  getKey={(token) => token.id}
                  renderItem={renderToken}
                  isLoading={query.isLoading}
                  isError={query.isError}
                  error={query.error}
                  onRetry={() => {
                    query.refetch()
                  }}
                  errorFallback="Could not load access tokens"
                  empty={
                    <p className="text-sm text-muted-foreground">
                      Issue a token for each app that connects to this agent.
                    </p>
                  }
                />
              </div>
            </>
          )}
          {pane === "create" && (
            <form
              className="space-y-4"
              onSubmit={form.handleSubmit((values) => issue.mutate(values))}
            >
              <fieldset disabled={issue.isPending} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="acp-token-label">Label</Label>
                  <Input
                    id="acp-token-label"
                    maxLength={255}
                    autoFocus
                    {...form.register("label")}
                    aria-invalid={!!form.formState.errors.label}
                  />
                  {form.formState.errors.label && (
                    <p className="text-sm text-destructive">
                      {form.formState.errors.label.message}
                    </p>
                  )}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="acp-token-expiry">Expires in days</Label>
                  <Input
                    id="acp-token-expiry"
                    type="number"
                    min={1}
                    max={365}
                    {...form.register("expires_in_days", {
                      valueAsNumber: true,
                    })}
                    aria-invalid={!!form.formState.errors.expires_in_days}
                  />
                  {form.formState.errors.expires_in_days && (
                    <p className="text-sm text-destructive">
                      Enter a whole number between 1 and 365.
                    </p>
                  )}
                </div>
              </fieldset>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  disabled={issue.isPending}
                  onClick={back}
                >
                  Cancel
                </Button>
                <LoadingButton type="submit" loading={issue.isPending}>
                  {issue.isPending ? "Issuing…" : "Issue token"}
                </LoadingButton>
              </DialogFooter>
            </form>
          )}
          {pane === "created" && secret && (
            <>
              <CopyableValue label="Access token" value={secret} />
              <p className="text-xs text-muted-foreground">
                Store it in the external app’s secret settings. If lost, revoke
                this token and issue another.
              </p>
              <DialogFooter>
                <Button onClick={back}>Done</Button>
              </DialogFooter>
            </>
          )}
        </DialogContent>
      </Dialog>
      <AlertDialog
        open={!!target}
        onOpenChange={(open) => !open && !action.isPending && setTarget(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="break-words">
              {target?.kind === "revoke" ? "Revoke" : "Delete"}{" "}
              {target?.token.label}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              The app using this token loses access, and a replacement token
              cannot reopen conversations this one started. This token cannot be
              restored.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={action.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={action.isPending}
              onClick={(event) => {
                event.preventDefault()
                if (target) action.mutate(target)
              }}
            >
              {action.isPending
                ? target?.kind === "revoke"
                  ? "Revoking…"
                  : "Deleting…"
                : target?.kind === "revoke"
                  ? "Revoke token"
                  : "Delete token"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
