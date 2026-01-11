import { MessageCircle, Wrench, Tag, User, Globe, FolderCode } from "lucide-react"
import { useState, useEffect } from "react"

import type { LLMPluginMarketplacePluginPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { LoadingButton } from "@/components/ui/loading-button"

interface InstallPluginModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  plugin: LLMPluginMarketplacePluginPublic | null
  onInstall: (conversationMode: boolean, buildingMode: boolean) => void
  isLoading: boolean
}

export function InstallPluginModal({
  open,
  onOpenChange,
  plugin,
  onInstall,
  isLoading,
}: InstallPluginModalProps) {
  const [conversationMode, setConversationMode] = useState(true)
  const [buildingMode, setBuildingMode] = useState(true)

  // Reset state when dialog opens with a new plugin
  useEffect(() => {
    if (open) {
      setConversationMode(true)
      setBuildingMode(true)
    }
  }, [open])

  if (!plugin) return null

  const isRemote = plugin.source_type === "url"

  const handleInstall = () => {
    if (!conversationMode && !buildingMode) {
      // At least one mode should be enabled
      return
    }
    onInstall(conversationMode, buildingMode)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Install Plugin</DialogTitle>
          <DialogDescription>
            Configure how this plugin will be used with your agent.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4 py-4">
          {/* Plugin Info */}
          <div className="space-y-2">
            <div className="flex items-start justify-between">
              <div>
                <h4 className="font-semibold">{plugin.name}</h4>
                <div className="flex flex-wrap items-center gap-1 mt-1">
                  {plugin.version && (
                    <Badge variant="secondary" className="text-xs">
                      v{plugin.version}
                    </Badge>
                  )}
                  {plugin.category && (
                    <Badge variant="outline" className="text-xs">
                      <Tag className="mr-1 h-3 w-3" />
                      {plugin.category}
                    </Badge>
                  )}
                  {isRemote ? (
                    <Badge
                      variant="outline"
                      className="text-xs bg-blue-50 text-blue-700 border-blue-200"
                    >
                      <Globe className="mr-1 h-3 w-3" />
                      Remote
                    </Badge>
                  ) : (
                    <Badge
                      variant="outline"
                      className="text-xs bg-gray-50 text-gray-700 border-gray-200"
                    >
                      <FolderCode className="mr-1 h-3 w-3" />
                      Local
                    </Badge>
                  )}
                </div>
              </div>
            </div>
            {plugin.description && (
              <p className="text-sm text-muted-foreground">
                {plugin.description}
              </p>
            )}
            {plugin.author_name && (
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <User className="h-3 w-3" />
                <span>{plugin.author_name}</span>
              </div>
            )}
            {plugin.marketplace_name && (
              <p className="text-xs text-muted-foreground">
                From marketplace: {plugin.marketplace_name}
              </p>
            )}
          </div>

          {/* Mode Selection */}
          <div className="space-y-3 pt-2 border-t">
            <Label className="text-sm font-medium">Enable for:</Label>
            <div className="space-y-3">
              <div className="flex items-start space-x-3">
                <Checkbox
                  id="conversation-mode"
                  checked={conversationMode}
                  onCheckedChange={(checked) =>
                    setConversationMode(checked as boolean)
                  }
                />
                <div className="grid gap-1.5 leading-none">
                  <Label
                    htmlFor="conversation-mode"
                    className="flex items-center gap-2 font-normal cursor-pointer"
                  >
                    <MessageCircle className="h-4 w-4 text-muted-foreground" />
                    Conversation Mode
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Plugin will be available during regular chat conversations
                  </p>
                </div>
              </div>
              <div className="flex items-start space-x-3">
                <Checkbox
                  id="building-mode"
                  checked={buildingMode}
                  onCheckedChange={(checked) =>
                    setBuildingMode(checked as boolean)
                  }
                />
                <div className="grid gap-1.5 leading-none">
                  <Label
                    htmlFor="building-mode"
                    className="flex items-center gap-2 font-normal cursor-pointer"
                  >
                    <Wrench className="h-4 w-4 text-muted-foreground" />
                    Building Mode
                  </Label>
                  <p className="text-xs text-muted-foreground">
                    Plugin will be available during code building sessions
                  </p>
                </div>
              </div>
            </div>
            {!conversationMode && !buildingMode && (
              <p className="text-xs text-destructive">
                At least one mode must be enabled
              </p>
            )}
          </div>
        </div>
        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <LoadingButton
            onClick={handleInstall}
            loading={isLoading}
            disabled={!conversationMode && !buildingMode}
          >
            Install Plugin
          </LoadingButton>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
