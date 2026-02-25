import { useState } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Copy, Check, Trash2, Plus, Link2, Users } from "lucide-react"

import type {
  AgentGuestSharePublic,
  AgentGuestShareCreate,
} from "@/client"
import { GuestSharesService } from "@/client"
import useCustomToast from "@/hooks/useCustomToast"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Badge } from "@/components/ui/badge"
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip"

interface GuestShareCardProps {
  agentId: string
}

type ExpirationOption = {
  label: string
  hours: number
}

const EXPIRATION_OPTIONS: ExpirationOption[] = [
  { label: "1 hour", hours: 1 },
  { label: "24 hours", hours: 24 },
  { label: "7 days", hours: 168 },
  { label: "30 days", hours: 720 },
]

function getShareStatus(share: AgentGuestSharePublic): "active" | "expired" | "revoked" {
  if (share.is_revoked) return "revoked"
  if (new Date(share.expires_at) < new Date()) return "expired"
  return "active"
}

function formatRelativeExpiry(expiresAt: string): string {
  const now = new Date()
  const expiry = new Date(expiresAt)
  const diffMs = expiry.getTime() - now.getTime()

  if (diffMs <= 0) return "Expired"

  const diffMinutes = Math.floor(diffMs / (1000 * 60))
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays > 0) return `${diffDays}d remaining`
  if (diffHours > 0) return `${diffHours}h remaining`
  return `${diffMinutes}m remaining`
}

export function GuestShareCard({ agentId }: GuestShareCardProps) {
  const [createDialogOpen, setCreateDialogOpen] = useState(false)
  const [shareLabel, setShareLabel] = useState("")
  const [expirationHours, setExpirationHours] = useState<string>("24")
  const [createdShareUrl, setCreatedShareUrl] = useState<string | null>(null)
  const [copiedUrl, setCopiedUrl] = useState(false)
  const [copiedShareId, setCopiedShareId] = useState<string | null>(null)

  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // Fetch guest shares
  const { data: sharesData, isLoading } = useQuery({
    queryKey: ["guest-shares", agentId],
    queryFn: () => GuestSharesService.listGuestShares({ agentId }),
  })

  // Create guest share mutation
  const createShareMutation = useMutation({
    mutationFn: (data: AgentGuestShareCreate) =>
      GuestSharesService.createGuestShare({
        agentId,
        requestBody: data,
      }),
    onSuccess: (response) => {
      showSuccessToast("Guest share link created successfully")
      setCreatedShareUrl(response.share_url)
      queryClient.invalidateQueries({ queryKey: ["guest-shares", agentId] })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to create guest share link")
    },
  })

  // Delete guest share mutation
  const deleteShareMutation = useMutation({
    mutationFn: (guestShareId: string) =>
      GuestSharesService.deleteGuestShare({ agentId, guestShareId }),
    onSuccess: () => {
      showSuccessToast("Guest share link deleted successfully")
      queryClient.invalidateQueries({ queryKey: ["guest-shares", agentId] })
    },
    onError: (error: any) => {
      showErrorToast(error.message || "Failed to delete guest share link")
    },
  })

  const handleCreateShare = () => {
    createShareMutation.mutate({
      label: shareLabel.trim() || undefined,
      expires_in_hours: Number(expirationHours),
    })
  }

  const handleCopyShareUrl = async () => {
    if (!createdShareUrl) return
    try {
      await navigator.clipboard.writeText(createdShareUrl)
      setCopiedUrl(true)
      setTimeout(() => setCopiedUrl(false), 2000)
    } catch {
      showErrorToast("Failed to copy URL")
    }
  }

  const handleCopyShareLink = async (shareUrl: string, shareId: string) => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopiedShareId(shareId)
      setTimeout(() => setCopiedShareId(null), 2000)
    } catch {
      showErrorToast("Failed to copy URL")
    }
  }

  const handleDialogClose = (open: boolean) => {
    if (!open) {
      // Reset form state when closing
      setShareLabel("")
      setExpirationHours("24")
      setCreatedShareUrl(null)
      setCopiedUrl(false)
    }
    setCreateDialogOpen(open)
  }

  const shares = sharesData?.data || []

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between">
          <div className="space-y-1.5">
            <CardTitle className="flex items-center gap-2">
              <Link2 className="h-5 w-5" />
              Guest Share Links
            </CardTitle>
            <CardDescription>
              Create shareable links for guests to chat with this agent
            </CardDescription>
          </div>
          <Dialog open={createDialogOpen} onOpenChange={handleDialogClose}>
            <DialogTrigger asChild>
              <Button size="sm">
                <Plus className="h-4 w-4 mr-1" />
                New Link
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>
                  {createdShareUrl ? "Share Link Created" : "Create Guest Share Link"}
                </DialogTitle>
                <DialogDescription>
                  {createdShareUrl
                    ? "Copy this link and share it with your guests."
                    : "Create a shareable link that allows guests to chat with this agent."}
                </DialogDescription>
              </DialogHeader>

              {createdShareUrl ? (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label>Share URL</Label>
                    <div className="flex gap-2">
                      <Input
                        value={createdShareUrl}
                        readOnly
                        className="font-mono text-xs"
                      />
                      <Button
                        variant="outline"
                        size="icon"
                        onClick={handleCopyShareUrl}
                        title="Copy URL"
                      >
                        {copiedUrl ? (
                          <Check className="h-4 w-4 text-green-500" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </Button>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      You can also copy this link later from the share list.
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="share-label">Label (optional)</Label>
                    <Input
                      id="share-label"
                      placeholder="e.g., Demo for client X"
                      value={shareLabel}
                      onChange={(e) => setShareLabel(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && !createShareMutation.isPending) {
                          e.preventDefault()
                          handleCreateShare()
                        }
                      }}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="share-expiration">Expiration</Label>
                    <Select value={expirationHours} onValueChange={setExpirationHours}>
                      <SelectTrigger id="share-expiration">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {EXPIRATION_OPTIONS.map((option) => (
                          <SelectItem key={option.hours} value={String(option.hours)}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">
                      The link will expire after this duration
                    </p>
                  </div>
                </div>
              )}

              <DialogFooter>
                {createdShareUrl ? (
                  <Button onClick={() => handleDialogClose(false)}>Done</Button>
                ) : (
                  <Button
                    onClick={handleCreateShare}
                    disabled={createShareMutation.isPending}
                  >
                    {createShareMutation.isPending ? "Creating..." : "Create Link"}
                  </Button>
                )}
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading share links...</p>
        ) : shares.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No guest share links yet. Create one to let guests chat with this agent.
          </p>
        ) : (
          <div className="space-y-1.5">
            {shares.map((share: AgentGuestSharePublic) => {
              const status = getShareStatus(share)
              return (
                <div
                  key={share.id}
                  className={`flex items-center justify-between px-3 py-2 border rounded-lg ${
                    status !== "active" ? "opacity-50 bg-muted" : ""
                  }`}
                >
                  {/* Left: label and status badge */}
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="font-medium text-sm truncate">
                      {share.label || "Untitled"}
                    </span>
                    {status === "active" && (
                      <Badge variant="default" className="text-xs shrink-0 bg-emerald-500 hover:bg-emerald-600">
                        Active
                      </Badge>
                    )}
                    {status === "expired" && (
                      <Badge variant="destructive" className="text-xs shrink-0">
                        Expired
                      </Badge>
                    )}
                    {status === "revoked" && (
                      <Badge variant="secondary" className="text-xs shrink-0">
                        Revoked
                      </Badge>
                    )}
                  </div>
                  {/* Right: token prefix, session count, expiry, and actions */}
                  <div className="flex items-center gap-2 shrink-0">
                    <span className="font-mono text-xs text-muted-foreground">
                      {share.token_prefix}...
                    </span>
                    <TooltipProvider>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <span className="flex items-center gap-1 cursor-help">
                            <Users className="h-3.5 w-3.5 text-muted-foreground" />
                            <span className="text-xs text-muted-foreground">
                              {share.session_count ?? 0}
                            </span>
                          </span>
                        </TooltipTrigger>
                        <TooltipContent side="top" className="text-xs">
                          {share.session_count === 1
                            ? "1 session created"
                            : `${share.session_count ?? 0} sessions created`}
                        </TooltipContent>
                      </Tooltip>
                    </TooltipProvider>
                    {status === "active" && (
                      <span className="text-xs text-muted-foreground">
                        {formatRelativeExpiry(share.expires_at)}
                      </span>
                    )}
                    <div className="flex items-center gap-0.5 ml-1 border-l pl-2">
                      {share.share_url && status === "active" && (
                        <TooltipProvider>
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <Button
                                variant="ghost"
                                size="icon"
                                className="h-6 w-6"
                                onClick={() => handleCopyShareLink(share.share_url!, share.id)}
                              >
                                {copiedShareId === share.id ? (
                                  <Check className="h-3.5 w-3.5 text-green-500" />
                                ) : (
                                  <Copy className="h-3.5 w-3.5" />
                                )}
                              </Button>
                            </TooltipTrigger>
                            <TooltipContent side="top" className="text-xs">
                              Copy share link
                            </TooltipContent>
                          </Tooltip>
                        </TooltipProvider>
                      )}
                      <AlertDialog>
                        <AlertDialogTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-6 w-6 text-destructive hover:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </Button>
                        </AlertDialogTrigger>
                        <AlertDialogContent>
                          <AlertDialogHeader>
                            <AlertDialogTitle>Delete Guest Share Link</AlertDialogTitle>
                            <AlertDialogDescription>
                              Are you sure you want to delete the share link
                              &ldquo;{share.label || "Untitled"}&rdquo;?
                              This action cannot be undone. The link will no longer be
                              usable, but existing sessions will continue to work.
                            </AlertDialogDescription>
                          </AlertDialogHeader>
                          <AlertDialogFooter>
                            <AlertDialogCancel>Cancel</AlertDialogCancel>
                            <AlertDialogAction
                              onClick={() => deleteShareMutation.mutate(share.id)}
                              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                            >
                              Delete
                            </AlertDialogAction>
                          </AlertDialogFooter>
                        </AlertDialogContent>
                      </AlertDialog>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
