import type { ACPConnectorPublic } from "@/client"
import { CopyableValue } from "@/components/Common/CopyableValue"
import { RelativeTime } from "@/components/Common/RelativeTime"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function AcpConnectionDetails({
  connector,
  onClose,
}: {
  connector: ACPConnectorPublic
  onClose: () => void
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto overflow-x-hidden pr-2 sm:max-w-lg [&>*]:min-w-0"
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          ;(event.currentTarget as HTMLElement | null)?.focus()
        }}
      >
        <DialogHeader>
          <DialogTitle className="break-words">
            Connect to {connector.name}
          </DialogTitle>
          <DialogDescription className="break-words">
            Use Agent Client Protocol to work with this agent from an external
            application.
          </DialogDescription>
        </DialogHeader>
        {connector.acp_server_url ? (
          <CopyableValue
            label="WebSocket endpoint"
            value={connector.acp_server_url}
          />
        ) : (
          <p className="text-sm text-muted-foreground">
            Ask your server administrator to configure the public ACP endpoint.
          </p>
        )}
        <CopyableValue
          label="Session working directory"
          value="/app/workspace"
        />
        <div className="space-y-2 text-sm text-muted-foreground">
          <p className="break-words">
            Create an access token from this connector’s menu, then send it in
            the connection’s <code>Authorization: Bearer &lt;token&gt;</code>{" "}
            header.
          </p>
          <p className="break-words">
            The client connects to the agent’s hosted workspace. Local files,
            terminals, and client-provided MCP servers are not shared. Use an
            empty MCP server list.
          </p>
          <p className="break-words">
            Clients that use stdio can connect through the Cinna ACP bridge.
            WebSocket transport is experimental.
          </p>
        </div>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Mode</dt>
            <dd>
              {connector.mode === "building" ? "Building" : "Conversation"}
            </dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Connection limit</dt>
            <dd>{connector.max_connections} connections</dd>
          </div>
          <div className="flex justify-between gap-3">
            <dt className="text-muted-foreground">Created</dt>
            <dd>
              <RelativeTime timestamp={connector.created_at} showTooltip />
            </dd>
          </div>
        </dl>
      </DialogContent>
    </Dialog>
  )
}
