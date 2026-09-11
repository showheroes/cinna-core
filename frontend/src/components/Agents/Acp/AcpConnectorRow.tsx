import {
  Copy,
  Info,
  KeyRound,
  Loader2,
  MessageCircle,
  Pencil,
  Power,
  PowerOff,
  Trash2,
  Wrench,
} from "lucide-react"
import type { ACPConnectorPublic } from "@/client"
import { ListRow, RowFlag } from "@/components/Common/ListRow"
import { RowActionsMenu } from "@/components/Common/RowActionsMenu"
import { Button } from "@/components/ui/button"
import {
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu"
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip"

export function AcpConnectorRow({
  connector,
  pending,
  onCopy,
  onDetails,
  onTokens,
  onEdit,
  onToggle,
  onDelete,
}: {
  connector: ACPConnectorPublic
  pending?: string
  onCopy: () => void
  onDetails: () => void
  onTokens: () => void
  onEdit: () => void
  onToggle: () => void
  onDelete: () => void
}) {
  return (
    <ListRow
      title={connector.name}
      muted={!connector.is_active}
      status={{
        tone: connector.is_active ? "on" : "off",
        label: connector.is_active ? "Enabled" : "Disabled",
      }}
      flags={
        <RowFlag
          icon={connector.mode === "building" ? Wrench : MessageCircle}
          label={
            connector.mode === "building"
              ? "Building mode — may change the agent"
              : "Conversation mode"
          }
          tone={connector.mode === "building" ? "warning" : "neutral"}
        />
      }
    >
      <Tooltip>
        <TooltipTrigger asChild>
          <span>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              disabled={!connector.acp_server_url || !!pending}
              aria-label={`Copy ACP endpoint for ${connector.name}`}
              onClick={onCopy}
            >
              <Copy className="h-3.5 w-3.5" />
            </Button>
          </span>
        </TooltipTrigger>
        <TooltipContent>
          {connector.acp_server_url
            ? "Copy ACP endpoint"
            : "Public endpoint is not configured"}
        </TooltipContent>
      </Tooltip>
      {pending ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <output className="flex h-7 w-7 items-center justify-center">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span className="sr-only">{pending}</span>
            </output>
          </TooltipTrigger>
          <TooltipContent>{pending}</TooltipContent>
        </Tooltip>
      ) : (
        <RowActionsMenu label={`ACP connector ${connector.name}`}>
          <DropdownMenuItem onSelect={onDetails}>
            <Info />
            Connection details
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onTokens}>
            <KeyRound />
            Access tokens
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onEdit}>
            <Pencil />
            Edit connector
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onToggle}>
            {connector.is_active ? <PowerOff /> : <Power />}
            {connector.is_active ? "Disable" : "Enable"}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem variant="destructive" onSelect={onDelete}>
            <Trash2 />
            Delete connector
          </DropdownMenuItem>
        </RowActionsMenu>
      )}
    </ListRow>
  )
}
