import { createFileRoute, useNavigate } from "@tanstack/react-router"
import { useState } from "react"
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import {
  ArrowLeft,
  GitBranch,
  Check,
  X,
  Clock,
  AlertCircle,
  RefreshCw,
  Edit,
  Key,
  BookOpen,
} from "lucide-react"

import { KnowledgeSourcesService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Switch } from "@/components/ui/switch"
import { Skeleton } from "@/components/ui/skeleton"
import useCustomToast from "@/hooks/useCustomToast"
import { EditSourceModal } from "@/components/KnowledgeSources/EditSourceModal"

export const Route = createFileRoute("/_layout/knowledge-source/$sourceId")({
  component: KnowledgeSourceDetailPage,
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

function KnowledgeSourceDetailPage() {
  const { sourceId } = Route.useParams()
  const navigate = useNavigate()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const queryClient = useQueryClient()
  const [isEditModalOpen, setIsEditModalOpen] = useState(false)

  const { data: source, isLoading: isLoadingSource } = useQuery({
    queryKey: ["knowledge-source", sourceId],
    queryFn: () => KnowledgeSourcesService.getKnowledgeSource({ sourceId }),
  })

  const { data: articles, isLoading: isLoadingArticles } = useQuery({
    queryKey: ["knowledge-articles", sourceId],
    queryFn: () => KnowledgeSourcesService.listKnowledgeArticles({ sourceId }),
    enabled: !!source && source.is_enabled,
  })

  const toggleEnabledMutation = useMutation({
    mutationFn: (enabled: boolean) =>
      enabled
        ? KnowledgeSourcesService.enableKnowledgeSource({ sourceId })
        : KnowledgeSourcesService.disableKnowledgeSource({ sourceId }),
    onSuccess: (_, enabled) => {
      showSuccessToast(
        enabled
          ? "Source is now active and available for queries"
          : "Source is now inactive"
      )
      queryClient.invalidateQueries({ queryKey: ["knowledge-source", sourceId] })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to update source")
    },
  })

  const checkAccessMutation = useMutation({
    mutationFn: () => KnowledgeSourcesService.checkKnowledgeSourceAccess({ sourceId }),
    onSuccess: (result) => {
      if (result.accessible) {
        showSuccessToast(result.message)
      } else {
        showErrorToast(result.message)
      }
      queryClient.invalidateQueries({ queryKey: ["knowledge-source", sourceId] })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to check access")
    },
  })

  const refreshMutation = useMutation({
    mutationFn: () => KnowledgeSourcesService.refreshKnowledgeSource({ sourceId }),
    onSuccess: (result) => {
      showSuccessToast(result.message)
      queryClient.invalidateQueries({ queryKey: ["knowledge-source", sourceId] })
      queryClient.invalidateQueries({ queryKey: ["knowledge-articles", sourceId] })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to refresh knowledge")
    },
  })

  if (isLoadingSource) {
    return (
      <div className="container mx-auto p-6 space-y-6">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-64 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    )
  }

  if (!source) {
    return (
      <div className="container mx-auto p-6">
        <Card>
          <CardContent className="py-12 text-center">
            <AlertCircle className="mx-auto h-12 w-12 text-muted-foreground" />
            <h3 className="mt-4 text-lg font-semibold">Knowledge source not found</h3>
            <Button className="mt-4" onClick={() => navigate({ to: "/knowledge-sources" })}>
              <ArrowLeft className="mr-2 h-4 w-4" />
              Back to Sources
            </Button>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button
            variant="ghost"
            size="icon"
            onClick={() => navigate({ to: "/knowledge-sources" })}
          >
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-3xl font-bold">{source.name}</h1>
            {source.description && (
              <p className="text-muted-foreground mt-1">{source.description}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            checked={source.is_enabled}
            onCheckedChange={(checked) => toggleEnabledMutation.mutate(checked)}
            disabled={toggleEnabledMutation.isPending}
          />
          <span className="text-sm font-medium">
            {source.is_enabled ? "Enabled" : "Disabled"}
          </span>
        </div>
      </div>

      {/* Configuration Card */}
      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <Label>Git URL</Label>
              <p className="text-sm font-mono mt-1">{source.git_url}</p>
            </div>
            <div>
              <Label>Branch</Label>
              <div className="flex items-center gap-1 mt-1">
                <GitBranch className="h-3 w-3" />
                <span className="text-sm">{source.branch}</span>
              </div>
            </div>
            <div>
              <Label>SSH Key</Label>
              <div className="flex items-center gap-1 mt-1">
                {source.ssh_key_id ? (
                  <>
                    <Key className="h-3 w-3" />
                    <span className="text-sm">Configured</span>
                  </>
                ) : (
                  <span className="text-sm text-muted-foreground">None (public repo)</span>
                )}
              </div>
            </div>
            <div>
              <Label>Status</Label>
              <div className="mt-1">
                <StatusBadge status={source.status} />
              </div>
            </div>
            <div>
              <Label>Workspace Access</Label>
              <Badge variant="outline" className="mt-1">
                {source.workspace_access_type === "all" ? "All Workspaces" : "Specific"}
              </Badge>
            </div>
            <div>
              <Label>Last Sync</Label>
              <p className="text-sm text-muted-foreground mt-1">
                {source.last_sync_at
                  ? new Date(source.last_sync_at).toLocaleString()
                  : "Never"}
              </p>
            </div>
          </div>

          {source.status_message && (
            <div className="p-3 bg-muted rounded-md">
              <p className="text-sm">{source.status_message}</p>
            </div>
          )}

          <div className="flex gap-2 pt-4">
            <Button variant="outline" onClick={() => setIsEditModalOpen(true)}>
              <Edit className="mr-2 h-4 w-4" />
              Edit Configuration
            </Button>
            <Button
              variant="outline"
              onClick={() => checkAccessMutation.mutate()}
              disabled={checkAccessMutation.isPending}
            >
              {checkAccessMutation.isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Checking...
                </>
              ) : (
                <>
                  <Check className="mr-2 h-4 w-4" />
                  Check Access
                </>
              )}
            </Button>
            <Button
              onClick={() => refreshMutation.mutate()}
              disabled={refreshMutation.isPending || !source.is_enabled}
            >
              {refreshMutation.isPending ? (
                <>
                  <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Refreshing...
                </>
              ) : (
                <>
                  <RefreshCw className="mr-2 h-4 w-4" />
                  Refresh Knowledge
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Articles Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Articles ({source.article_count})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!source.is_enabled ? (
            <div className="text-center py-12">
              <AlertCircle className="mx-auto h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-semibold">Source is disabled</h3>
              <p className="text-sm text-muted-foreground mt-2">
                Enable this source to view articles
              </p>
            </div>
          ) : isLoadingArticles ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : !articles || articles.length === 0 ? (
            <div className="text-center py-12">
              <BookOpen className="mx-auto h-12 w-12 text-muted-foreground" />
              <h3 className="mt-4 text-lg font-semibold">No articles yet</h3>
              <p className="text-sm text-muted-foreground mt-2">
                Click "Refresh Knowledge" to extract articles from the repository
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Title</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Tags</TableHead>
                  <TableHead>Features</TableHead>
                  <TableHead>Embedding Model</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {articles.map((article) => (
                  <TableRow key={article.id}>
                    <TableCell className="font-medium">{article.title}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {article.description}
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {article.tags.map((tag, idx) => (
                          <Badge key={idx} variant="secondary" className="text-xs">
                            {tag}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {article.features.map((feature, idx) => (
                          <Badge key={idx} variant="outline" className="text-xs">
                            {feature}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell>
                      {article.embedding_model ? (
                        <Badge variant="secondary">
                          {article.embedding_model}
                        </Badge>
                      ) : (
                        <span className="text-xs text-muted-foreground">None</span>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(article.updated_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {isEditModalOpen && (
        <EditSourceModal
          source={source}
          open={isEditModalOpen}
          onOpenChange={setIsEditModalOpen}
          onSuccess={() => {
            queryClient.invalidateQueries({ queryKey: ["knowledge-source", sourceId] })
            setIsEditModalOpen(false)
          }}
        />
      )}
    </div>
  )
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="text-sm font-medium text-muted-foreground">{children}</div>
}
