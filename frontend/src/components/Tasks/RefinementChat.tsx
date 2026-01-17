import { useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Send, Loader2, User, Bot } from "lucide-react"

import { TasksService } from "@/client"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { cn } from "@/lib/utils"
import { RelativeTime } from "@/components/Common/RelativeTime"

export interface RefinementHistoryItem {
  role: "user" | "ai"
  content: string
  timestamp: string
}

interface RefinementChatProps {
  taskId: string
  history: RefinementHistoryItem[]
  onRefined?: (newDescription: string) => void
}

export function RefinementChat({ taskId, history, onRefined }: RefinementChatProps) {
  const queryClient = useQueryClient()
  const [comment, setComment] = useState("")

  const refineMutation = useMutation({
    mutationFn: (userComment: string) =>
      TasksService.refineTask({
        id: taskId,
        requestBody: { user_comment: userComment },
      }),
    onSuccess: (result) => {
      if (result.success && result.refined_description) {
        queryClient.invalidateQueries({ queryKey: ["task", taskId] })
        onRefined?.(result.refined_description)
      }
      setComment("")
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!comment.trim() || refineMutation.isPending) return
    refineMutation.mutate(comment.trim())
  }

  return (
    <div className="flex flex-col h-full">
      {/* Chat history */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {history.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p className="text-sm">No refinement history yet.</p>
            <p className="text-xs mt-1">
              Send a message to start refining this task with AI assistance.
            </p>
          </div>
        ) : (
          history.map((item, index) => (
            <div
              key={index}
              className={cn(
                "flex gap-3",
                item.role === "user" ? "flex-row-reverse" : ""
              )}
            >
              <div
                className={cn(
                  "flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center",
                  item.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                {item.role === "user" ? (
                  <User className="h-4 w-4" />
                ) : (
                  <Bot className="h-4 w-4" />
                )}
              </div>
              <div
                className={cn(
                  "flex-1 max-w-[80%] rounded-lg px-3 py-2",
                  item.role === "user"
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                )}
              >
                <p className="text-sm whitespace-pre-wrap">{item.content}</p>
                <RelativeTime
                  timestamp={item.timestamp}
                  className={cn(
                    "text-xs mt-1 block",
                    item.role === "user"
                      ? "text-primary-foreground/70"
                      : "text-muted-foreground"
                  )}
                />
              </div>
            </div>
          ))
        )}

        {refineMutation.isPending && (
          <div className="flex gap-3">
            <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-muted">
              <Bot className="h-4 w-4" />
            </div>
            <div className="bg-muted rounded-lg px-3 py-2">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="h-4 w-4 animate-spin" />
                Refining...
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t">
        <div className="flex gap-2">
          <Textarea
            placeholder="Add details, ask for changes, or request clarification..."
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            className="resize-none"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault()
                handleSubmit(e)
              }
            }}
          />
          <Button
            type="submit"
            size="icon"
            disabled={!comment.trim() || refineMutation.isPending}
            className="flex-shrink-0 h-auto"
          >
            {refineMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Send className="h-4 w-4" />
            )}
          </Button>
        </div>
        {refineMutation.error && (
          <p className="text-xs text-destructive mt-2">
            {(refineMutation.error as Error).message || "Failed to refine task"}
          </p>
        )}
      </form>
    </div>
  )
}
