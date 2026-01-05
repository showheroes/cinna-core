import { createFileRoute } from "@tanstack/react-router"
import { useState, useEffect } from "react"
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Plus, BookOpen, GitBranch, Check, X, Clock, AlertCircle } from "lucide-react"

import { KnowledgeSourcesService } from "@/client"
import type { AIKnowledgeGitRepoPublic } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Switch } from "@/components/ui/switch"
import PendingItems from "@/components/Pending/PendingItems"
import useCustomToast from "@/hooks/useCustomToast"
import { AddSourceModal } from "@/components/KnowledgeSources/AddSourceModal"
import { EditSourceModal } from "@/components/KnowledgeSources/EditSourceModal"
import { usePageHeader } from "@/routes/_layout"
import { useNavigate } from "@tanstack/react-router"

export const Route = createFileRoute("/_layout/knowledge-sources")({
  component: KnowledgeSourcesPage,
  head: () => ({
    meta: [
      {
        title: "Knowledge Sources - Workflow Runner",
      },
    ],
  }),
})

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, { icon: any; className: string; label: string }> = {
    connected: {
      icon: Check,
      className: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300",
      label: "Connected",
    },
    pending: {
      icon: Clock,
      className: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300",
      label: "Pending",
    },
    error: {
      icon: AlertCircle,
      className: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300",
      label: "Error",
    },
    disconnected: {
      icon: X,
      className: "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300",
      label: "Disconnected",
    },
  }

  const variant = variants[status] || variants.disconnected
  const Icon = variant.icon

  return (
    <Badge className={variant.className} variant="outline">
      <Icon className="mr-1 h-3 w-3" />
      {variant.label}
    </Badge>
  )
}

function KnowledgeSourcesList() {
  const navigate = useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const [editingSource, setEditingSource] = useState<AIKnowledgeGitRepoPublic | null>(null)

  const { data: sources, isLoading, error } = useQuery({
    queryKey: ["knowledge-sources"],
    queryFn: () => KnowledgeSourcesService.listKnowledgeSources(),
  })

  const handleToggleEnabled = async (source: AIKnowledgeGitRepoPublic, enabled: boolean) => {
    try {
      if (enabled) {
        await KnowledgeSourcesService.enableKnowledgeSource({ sourceId: source.id })
        showSuccessToast(`${source.name} is now active`)
      } else {
        await KnowledgeSourcesService.disableKnowledgeSource({ sourceId: source.id })
        showSuccessToast(`${source.name} is now inactive`)
      }
      queryClient.invalidateQueries({ queryKey: ["knowledge-sources"] })
    } catch (error: any) {
      showErrorToast(error.message || "Failed to update source")
    }
  }

  const handleDelete = async (sourceId: string) => {
    if (!confirm("Are you sure you want to delete this knowledge source? This will also delete all associated articles.")) {
      return
    }

    try {
      await KnowledgeSourcesService.deleteKnowledgeSource({ sourceId })
      showSuccessToast("Knowledge source has been removed")
      queryClient.invalidateQueries({ queryKey: ["knowledge-sources"] })
    } catch (error: any) {
      showErrorToast(error.message || "Failed to delete source")
    }
  }

  if (isLoading) {
    return <PendingItems />
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12">
        <p className="text-destructive">
          Error loading knowledge sources: {(error as Error).message}
        </p>
      </div>
    )
  }

  if (!sources || sources.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center text-center py-12">
        <div className="rounded-full bg-muted p-4 mb-4">
          <BookOpen className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">No knowledge sources</h3>
        <p className="text-muted-foreground">Add your first knowledge source to help your agents build integrations</p>
      </div>
    )
  }

  return (
    <>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Name</TableHead>
            <TableHead>Repository</TableHead>
            <TableHead>Branch</TableHead>
            <TableHead>Status</TableHead>
            <TableHead>Enabled</TableHead>
            <TableHead>Articles</TableHead>
            <TableHead>Last Sync</TableHead>
            <TableHead>Workspace Access</TableHead>
            <TableHead className="text-right">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {sources.map((source) => (
            <TableRow
              key={source.id}
              className={!source.is_enabled ? "opacity-60" : ""}
            >
              <TableCell className="font-medium">{source.name}</TableCell>
              <TableCell className="font-mono text-xs max-w-xs truncate">{source.git_url}</TableCell>
              <TableCell>
                <div className="flex items-center gap-1">
                  <GitBranch className="h-3 w-3" />
                  <span className="text-xs">{source.branch}</span>
                </div>
              </TableCell>
              <TableCell>
                <StatusBadge status={source.status} />
              </TableCell>
              <TableCell>
                <Switch
                  checked={source.is_enabled}
                  onCheckedChange={(checked) => handleToggleEnabled(source, checked)}
                />
              </TableCell>
              <TableCell>
                <Badge variant="secondary">{source.article_count}</Badge>
              </TableCell>
              <TableCell className="text-xs text-muted-foreground">
                {source.last_sync_at
                  ? new Date(source.last_sync_at).toLocaleDateString()
                  : "Never"}
              </TableCell>
              <TableCell>
                <Badge variant="outline">
                  {source.workspace_access_type === "all" ? "All Workspaces" : "Specific"}
                </Badge>
              </TableCell>
              <TableCell className="text-right space-x-2">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => navigate({ to: "/knowledge-source/$sourceId", params: { sourceId: source.id } })}
                >
                  View
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setEditingSource(source)}
                >
                  Edit
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleDelete(source.id)}
                >
                  Delete
                </Button>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {editingSource && (
        <EditSourceModal
          source={editingSource}
          open={true}
          onOpenChange={(open) => !open && setEditingSource(null)}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["knowledge-sources"] })
            setEditingSource(null)
          }}
        />
      )}
    </>
  )
}

function KnowledgeSourcesPage() {
  const { setHeaderContent } = usePageHeader()
  const [isAddModalOpen, setIsAddModalOpen] = useState(false)
  const queryClient = useQueryClient()

  useEffect(() => {
    setHeaderContent(
      <>
        <div className="min-w-0">
          <h1 className="text-lg font-semibold truncate">Knowledge Sources</h1>
          <p className="text-xs text-muted-foreground">Manage your Git-based knowledge repositories</p>
        </div>
        <Button onClick={() => setIsAddModalOpen(true)}>
          <Plus className="mr-2 h-4 w-4" />
          Add Source
        </Button>
      </>
    )
    return () => setHeaderContent(null)
  }, [setHeaderContent])

  return (
    <div className="p-6 md:p-8 overflow-y-auto">
      <div className="mx-auto max-w-7xl">
        <KnowledgeSourcesList />
      </div>

      <AddSourceModal
        open={isAddModalOpen}
        onOpenChange={setIsAddModalOpen}
        onSuccess={() => {
          queryClient.invalidateQueries({ queryKey: ["knowledge-sources"] })
          setIsAddModalOpen(false)
        }}
      />
    </div>
  )
}
