import { useState, useRef, useCallback } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { useNavigate } from "@tanstack/react-router"
import {
  ArrowLeft,
  Bot,
  User,
  Paperclip,
  Send,
  Download,
  ChevronDown,
  ChevronRight,
  Loader2,
  FileText,
  ExternalLink,
} from "lucide-react"

import { TasksService } from "@/client"
import type { InputTaskDetailPublic, TaskCommentPublic, TaskAttachmentPublic } from "@/client"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { TaskShortCodeBadge } from "@/components/Tasks/TaskShortCodeBadge"
import { TaskStatusPill } from "@/components/Tasks/TaskStatusPill"
import { TaskPriorityBadge } from "@/components/Tasks/TaskPriorityBadge"
import { SubtaskProgressChip } from "@/components/Tasks/SubtaskProgressChip"
import { RelativeTime } from "@/components/Common/RelativeTime"
import { MarkdownRenderer } from "@/components/Chat/MarkdownRenderer"
import { cn } from "@/lib/utils"
import useCustomToast from "@/hooks/useCustomToast"
import { useMultiEventSubscription, EventTypes } from "@/hooks/useEventBus"

interface TaskDetailProps {
  task: InputTaskDetailPublic
  shortCode: string
}

function formatFileSize(bytes: number | null | undefined): string {
  if (!bytes) return ""
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function CommentItem({ comment }: { comment: TaskCommentPublic }) {
  const isSystem = ["status_change", "assignment", "system"].includes(comment.comment_type)
  const isAgent = !!comment.author_agent_id

  const attachments = (comment.inline_attachments as TaskAttachmentPublic[] | undefined) ?? []

  if (isSystem) {
    return (
      <div className="flex items-start gap-2 py-1.5">
        <div className="w-5 h-5 rounded-full bg-muted flex items-center justify-center shrink-0 mt-0.5">
          <div className="w-1.5 h-1.5 rounded-full bg-muted-foreground/40" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-xs text-muted-foreground">{comment.content}</p>
        </div>
        <RelativeTime
          timestamp={comment.created_at}
          className="text-xs text-muted-foreground shrink-0"
        />
      </div>
    )
  }

  return (
    <div className="flex items-start gap-2.5 py-2">
      {/* Avatar */}
      <div
        className={cn(
          "w-7 h-7 rounded-full flex items-center justify-center shrink-0 mt-0.5",
          isAgent
            ? "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300"
            : "bg-muted text-muted-foreground"
        )}
      >
        {isAgent ? <Bot className="h-3.5 w-3.5" /> : <User className="h-3.5 w-3.5" />}
      </div>

      <div className="flex-1 min-w-0 space-y-1">
        {/* Author + timestamp */}
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium">
            {comment.author_name || (isAgent ? "Agent" : "User")}
          </span>
          {comment.author_role && (
            <span className="text-xs text-muted-foreground">({comment.author_role})</span>
          )}
          <RelativeTime
            timestamp={comment.created_at}
            className="text-xs text-muted-foreground"
          />
        </div>

        {/* Content */}
        <div className="text-sm prose prose-sm dark:prose-invert max-w-none">
          <MarkdownRenderer content={comment.content} />
        </div>

        {/* Inline attachments */}
        {attachments.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {attachments.map((att) => (
              <AttachmentChip key={att.id} attachment={att} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function AttachmentChip({ attachment }: { attachment: TaskAttachmentPublic }) {
  const handleDownload = () => {
    if (attachment.download_url) {
      window.open(attachment.download_url, "_blank")
    }
  }

  return (
    <button
      onClick={handleDownload}
      className="inline-flex items-center gap-1.5 px-2 py-1 rounded border text-xs hover:bg-muted transition-colors"
    >
      <FileText className="h-3 w-3 text-muted-foreground" />
      <span className="truncate max-w-[160px]">{attachment.file_name}</span>
      {attachment.file_size && (
        <span className="text-muted-foreground shrink-0">
          ({formatFileSize(attachment.file_size)})
        </span>
      )}
      <Download className="h-3 w-3 text-muted-foreground shrink-0" />
    </button>
  )
}

function SubtaskRow({ subtask }: { subtask: InputTaskDetailPublic }) {
  const navigate = useNavigate()

  return (
    <button
      onClick={() => {
        if (subtask.short_code) {
          navigate({ to: "/tasks/$shortCode", params: { shortCode: subtask.short_code } })
        } else {
          navigate({ to: "/task/$taskId", params: { taskId: subtask.id } })
        }
      }}
      className="w-full flex items-center gap-2 px-3 py-2 rounded-md hover:bg-muted/60 transition-colors text-left"
    >
      <TaskStatusPill status={subtask.status} className="shrink-0" />
      {subtask.short_code && (
        <span className="font-mono text-xs text-muted-foreground shrink-0">
          {subtask.short_code}
        </span>
      )}
      <span className="text-sm truncate flex-1">
        {subtask.title || subtask.current_description}
      </span>
      {subtask.agent_name && (
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground shrink-0">
          <Bot className="h-3 w-3" />
          {subtask.agent_name}
        </span>
      )}
      <ExternalLink className="h-3 w-3 text-muted-foreground shrink-0" />
    </button>
  )
}

export function TaskDetail({ task, shortCode }: TaskDetailProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [commentText, setCommentText] = useState("")
  const [subtasksExpanded, setSubtasksExpanded] = useState(true)
  const [attachmentsExpanded, setAttachmentsExpanded] = useState(true)

  const comments = (task.comments as TaskCommentPublic[] | undefined) ?? []
  const attachments = (task.attachments as TaskAttachmentPublic[] | undefined) ?? []
  const subtasks = (task.subtasks as InputTaskDetailPublic[] | undefined) ?? []

  const addCommentMutation = useMutation({
    mutationFn: (content: string) =>
      TasksService.addTaskComment({
        id: task.id,
        requestBody: { content },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task", shortCode] })
      setCommentText("")
      showSuccessToast("Comment added")
    },
    onError: () => showErrorToast("Failed to add comment"),
  })

  const uploadAttachmentMutation = useMutation({
    mutationFn: (file: File) =>
      TasksService.uploadTaskAttachment({
        id: task.id,
        formData: { file },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["task", shortCode] })
      showSuccessToast("File attached")
    },
    onError: () => showErrorToast("Failed to upload file"),
  })

  // Subscribe to real-time events for the current task and refresh on match
  const handleTaskEvent = useCallback(
    (event: { meta?: { task_id?: string; short_code?: string } }) => {
      const meta = event.meta
      if (!meta) return
      const matches =
        meta.task_id === task.id ||
        (meta.short_code && meta.short_code === task.short_code)
      if (matches) {
        queryClient.invalidateQueries({ queryKey: ["task", shortCode] })
      }
    },
    [task.id, task.short_code, shortCode, queryClient],
  )

  useMultiEventSubscription(
    [
      EventTypes.TASK_COMMENT_ADDED,
      EventTypes.TASK_STATUS_CHANGED,
      EventTypes.TASK_ATTACHMENT_ADDED,
      EventTypes.SUBTASK_COMPLETED,
      EventTypes.TASK_SUBTASK_CREATED,
    ],
    handleTaskEvent,
  )

  const handleSendComment = () => {
    if (!commentText.trim()) return
    addCommentMutation.mutate(commentText.trim())
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSendComment()
    }
  }

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      uploadAttachmentMutation.mutate(file)
      e.target.value = ""
    }
  }

  const displayTitle = task.title || task.current_description

  return (
    <div className="flex flex-col gap-0 h-full overflow-y-auto">
      {/* Header */}
      <div className="flex items-start gap-3 px-6 py-4 border-b bg-card/50">
        <Button
          variant="ghost"
          size="icon"
          onClick={() => navigate({ to: "/tasks" })}
          className="h-8 w-8 shrink-0"
        >
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1 min-w-0 space-y-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            {task.short_code && (
              <TaskShortCodeBadge shortCode={task.short_code} status={task.status} clickable={false} />
            )}
            <TaskStatusPill status={task.status} />
            <TaskPriorityBadge priority={task.priority || "normal"} />
            {task.team_name && (
              <span className="text-xs bg-muted text-muted-foreground px-2 py-0.5 rounded">
                {task.team_name}
              </span>
            )}
          </div>
          <h1 className="text-lg font-semibold leading-tight">{displayTitle}</h1>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-0 flex-1 min-h-0">
        {/* Main content */}
        <div className="flex-1 min-w-0 flex flex-col">
          {/* Metadata */}
          <div className="px-6 py-4 border-b space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-x-6 gap-y-1.5">
              {task.agent_name && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium text-foreground w-28 shrink-0">Assigned to</span>
                  <span className="inline-flex items-center gap-1">
                    <Bot className="h-3.5 w-3.5" />
                    {task.agent_name}
                    {task.assigned_node_name && (
                      <span className="text-muted-foreground">({task.assigned_node_name})</span>
                    )}
                  </span>
                </div>
              )}
              <div className="flex items-center gap-2 text-muted-foreground">
                <span className="font-medium text-foreground w-28 shrink-0">Created</span>
                <RelativeTime timestamp={task.created_at} />
              </div>
              {task.completed_at && (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <span className="font-medium text-foreground w-28 shrink-0">Completed</span>
                  <RelativeTime timestamp={task.completed_at} />
                </div>
              )}
            </div>

            {task.current_description && task.title && (
              <div className="pt-2 border-t">
                <div className="text-sm font-medium mb-1">Description</div>
                <div className="text-sm text-muted-foreground prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownRenderer content={task.current_description} />
                </div>
              </div>
            )}
          </div>

          {/* Subtasks + Attachments panels */}
          <div className="flex flex-col sm:flex-row gap-0 border-b">
            {/* Subtasks */}
            {subtasks.length > 0 && (
              <div className="flex-1 border-r">
                <button
                  onClick={() => setSubtasksExpanded((v) => !v)}
                  className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors"
                >
                  {subtasksExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <span>Subtasks</span>
                  <SubtaskProgressChip
                    total={task.subtask_count ?? subtasks.length}
                    completed={task.subtask_completed_count ?? 0}
                  />
                </button>
                {subtasksExpanded && (
                  <div className="px-2 pb-3 space-y-0.5">
                    {subtasks.map((sub) => (
                      <SubtaskRow key={sub.id} subtask={sub} />
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Attachments */}
            {attachments.length > 0 && (
              <div className="flex-1">
                <button
                  onClick={() => setAttachmentsExpanded((v) => !v)}
                  className="w-full flex items-center gap-2 px-4 py-3 text-sm font-medium hover:bg-muted/50 transition-colors"
                >
                  {attachmentsExpanded ? (
                    <ChevronDown className="h-4 w-4 text-muted-foreground" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-muted-foreground" />
                  )}
                  <Paperclip className="h-3.5 w-3.5 text-muted-foreground" />
                  <span>Attachments ({attachments.length})</span>
                </button>
                {attachmentsExpanded && (
                  <div className="px-4 pb-3 space-y-1.5">
                    {attachments.map((att) => (
                      <AttachmentChip key={att.id} attachment={att} />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Comment thread */}
          <div className="flex-1 px-6 py-4 space-y-0.5 overflow-y-auto">
            <div className="text-sm font-medium mb-3 text-muted-foreground uppercase tracking-wide text-xs">
              Activity
            </div>
            {comments.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No activity yet
              </p>
            ) : (
              <div className="space-y-0.5 divide-y divide-border/50">
                {comments.map((comment) => (
                  <CommentItem key={comment.id} comment={comment} />
                ))}
              </div>
            )}
          </div>

          {/* Comment input */}
          <div className="px-6 py-4 border-t">
            <div className="flex gap-2 items-end">
              <Textarea
                placeholder="Add a comment... (Ctrl+Enter to send)"
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                onKeyDown={handleKeyDown}
                rows={2}
                className="resize-none text-sm flex-1"
              />
              <div className="flex flex-col gap-1.5">
                <Button
                  variant="outline"
                  size="icon"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploadAttachmentMutation.isPending}
                  title="Attach file"
                  className="h-8 w-8"
                >
                  {uploadAttachmentMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Paperclip className="h-3.5 w-3.5" />
                  )}
                </Button>
                <Button
                  size="icon"
                  onClick={handleSendComment}
                  disabled={!commentText.trim() || addCommentMutation.isPending}
                  title="Send comment"
                  className="h-8 w-8"
                >
                  {addCommentMutation.isPending ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Send className="h-3.5 w-3.5" />
                  )}
                </Button>
              </div>
            </div>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              onChange={handleFileChange}
            />
          </div>
        </div>
      </div>
    </div>
  )
}
