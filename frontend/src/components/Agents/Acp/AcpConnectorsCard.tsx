import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, Waypoints } from "lucide-react"
import { useState } from "react"
import { type ACPConnectorPublic, AcpConnectorsService } from "@/client"
import { PreviewList } from "@/components/Common/PreviewList"
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
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import useCustomToast from "@/hooks/useCustomToast"
import { getErrorMessage } from "@/utils"
import { AcpConnectionDetails } from "./AcpConnectionDetails"
import { AcpConnectorForm } from "./AcpConnectorForm"
import { AcpConnectorRow } from "./AcpConnectorRow"
import { AcpTokensDialog } from "./AcpTokensDialog"

type View =
  | { kind: "create" }
  | { kind: "edit" | "details" | "tokens"; connector: ACPConnectorPublic }

export function AcpConnectorsCard({ agentId }: { agentId: string }) {
  const [view, setView] = useState<View | null>(null)
  const [showAll, setShowAll] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<ACPConnectorPublic | null>(
    null,
  )
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryKey = ["acp-connectors", agentId]
  const query = useQuery({
    queryKey,
    queryFn: () => AcpConnectorsService.listAcpConnectors({ agentId }),
  })
  const toggle = useMutation({
    mutationFn: (connector: ACPConnectorPublic) =>
      AcpConnectorsService.updateAcpConnector({
        agentId,
        connectorId: connector.id,
        requestBody: { is_active: !connector.is_active },
      }),
    onSuccess: (connector) => {
      queryClient.invalidateQueries({ queryKey })
      showSuccessToast(
        connector.is_active
          ? "ACP connector enabled"
          : "ACP connector disabled",
      )
    },
    onError: (error) =>
      showErrorToast(getErrorMessage(error, "Could not update connector")),
  })
  const remove = useMutation({
    mutationFn: (connectorId: string) =>
      AcpConnectorsService.deleteAcpConnector({ agentId, connectorId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
      setDeleteTarget(null)
      showSuccessToast("ACP connector deleted")
    },
    onError: (error) =>
      showErrorToast(getErrorMessage(error, "Could not delete connector")),
  })
  const open = (next: View) => {
    setShowAll(false)
    setView(next)
  }
  const copy = async (value: string) => {
    try {
      await navigator.clipboard.writeText(value)
      showSuccessToast("ACP endpoint copied")
    } catch {
      showErrorToast("Could not copy ACP endpoint")
    }
  }
  const connectors = [...(query.data?.data || [])].sort(
    (a, b) =>
      Number(b.is_active) - Number(a.is_active) ||
      b.created_at.localeCompare(a.created_at),
  )
  const renderRow = (connector: ACPConnectorPublic) => (
    <AcpConnectorRow
      connector={connector}
      pending={
        toggle.isPending && toggle.variables?.id === connector.id
          ? "Updating…"
          : remove.isPending && remove.variables === connector.id
            ? "Deleting…"
            : undefined
      }
      onCopy={() => connector.acp_server_url && copy(connector.acp_server_url)}
      onDetails={() => open({ kind: "details", connector })}
      onTokens={() => open({ kind: "tokens", connector })}
      onEdit={() => open({ kind: "edit", connector })}
      onToggle={() => toggle.mutate(connector)}
      onDelete={() => setDeleteTarget(connector)}
    />
  )
  const listProps = {
    items: connectors,
    getKey: (item: ACPConnectorPublic) => item.id,
    renderItem: renderRow,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    onRetry: () => {
      query.refetch()
    },
    errorFallback: "Could not load ACP connectors",
    empty: (
      <p className="text-sm text-muted-foreground">
        Add a connector to let an external ACP app use this agent.
      </p>
    ),
  }
  return (
    <>
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex min-w-0 items-center gap-2">
              <Waypoints className="h-5 w-5 shrink-0" />
              ACP Connectors
            </CardTitle>
            <Button size="sm" onClick={() => open({ kind: "create" })}>
              <Plus className="h-4 w-4" />
              Add connector
            </Button>
          </div>
          <CardDescription>
            Connect external apps to this agent with Agent Client Protocol.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <PreviewList
            {...listProps}
            total={query.data?.count}
            onShowAll={() => setShowAll(true)}
          />
        </CardContent>
      </Card>
      <Sheet open={showAll} onOpenChange={setShowAll}>
        <SheetContent className="w-full sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>ACP Connectors</SheetTitle>
            <SheetDescription>
              {query.data?.count || 0} connectors
            </SheetDescription>
          </SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4 pr-2">
            <PreviewList
              {...listProps}
              previewCount={Math.max(connectors.length, 1)}
            />
            <Button className="mt-4" onClick={() => open({ kind: "create" })}>
              Add connector
            </Button>
          </div>
        </SheetContent>
      </Sheet>
      {view?.kind === "create" && (
        <AcpConnectorForm agentId={agentId} onClose={() => setView(null)} />
      )}
      {view?.kind === "edit" && (
        <AcpConnectorForm
          agentId={agentId}
          connector={view.connector}
          onClose={() => setView(null)}
        />
      )}
      {view?.kind === "details" && (
        <AcpConnectionDetails
          connector={view.connector}
          onClose={() => setView(null)}
        />
      )}
      {view?.kind === "tokens" && (
        <AcpTokensDialog
          agentId={agentId}
          connector={view.connector}
          onClose={() => setView(null)}
        />
      )}
      <AlertDialog
        open={!!deleteTarget}
        onOpenChange={(isOpen) =>
          !isOpen && !remove.isPending && setDeleteTarget(null)
        }
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle className="break-words">
              Delete {deleteTarget?.name}?
            </AlertDialogTitle>
            <AlertDialogDescription>
              Connected apps lose access. Existing conversations remain in
              Cinna.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={remove.isPending}>
              Cancel
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              disabled={remove.isPending}
              onClick={(event) => {
                event.preventDefault()
                if (deleteTarget) remove.mutate(deleteTarget.id)
              }}
            >
              {remove.isPending ? "Deleting…" : "Delete connector"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}
