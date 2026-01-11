import { Plus, Tag, FolderCode, Globe } from "lucide-react"

import type { LLMPluginMarketplacePluginPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"

interface PluginCardProps {
  plugin: LLMPluginMarketplacePluginPublic
  onInstall: () => void
}

function truncateDescription(
  description: string | null,
  maxLength: number = 100
): string {
  if (!description) return "No description available"
  if (description.length <= maxLength) return description
  return description.substring(0, maxLength) + "..."
}

export function PluginCard({ plugin, onInstall }: PluginCardProps) {
  const isRemote = plugin.source_type === "url"

  return (
    <Card>
      <CardHeader className="pb-0">
        <div className="flex items-baseline gap-1.5">
          <CardTitle className="text-base truncate">{plugin.name}</CardTitle>
          {plugin.marketplace_name && (
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              from {plugin.marketplace_name}
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1">
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
      </CardHeader>
      <CardContent className="pt-0 space-y-3">
        <CardDescription className="text-sm line-clamp-3">
          {truncateDescription(plugin.description, 150)}
        </CardDescription>
        <Button size="sm" onClick={onInstall} className="w-full">
          <Plus className="mr-2 h-4 w-4" />
          Install
        </Button>
      </CardContent>
    </Card>
  )
}
