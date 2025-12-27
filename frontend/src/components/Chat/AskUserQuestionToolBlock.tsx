import { useState } from "react"
import { MessageCircle } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

interface AskUserQuestionToolBlockProps {
  questions?: any[]
}

export function AskUserQuestionToolBlock({ questions }: AskUserQuestionToolBlockProps) {
  const [showDebugModal, setShowDebugModal] = useState(false)

  if (!questions || questions.length === 0) {
    return null
  }

  const questionCount = questions.length

  return (
    <>
      <div
        className="flex items-start gap-2 text-sm bg-slate-100 dark:bg-slate-800 border border-border rounded px-3 py-2 cursor-pointer hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
        onClick={() => setShowDebugModal(true)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            setShowDebugModal(true)
          }
        }}
        title="Click to view debug details"
      >
        <MessageCircle className="h-4 w-4 text-muted-foreground mt-0.5 flex-shrink-0" />
        <div className="flex-1 min-w-0 flex items-center justify-between">
          <div className="font-medium text-foreground/90">
            {questionCount} {questionCount === 1 ? "question" : "questions"} received
          </div>
        </div>
      </div>

      <Dialog open={showDebugModal} onOpenChange={setShowDebugModal}>
        <DialogContent className="sm:max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>AskUserQuestion Tool Call Details</DialogTitle>
            <DialogDescription>
              Debug view of the raw tool call parameters
            </DialogDescription>
          </DialogHeader>
          <pre className="text-xs bg-slate-100 dark:bg-slate-900 p-4 rounded overflow-x-auto">
            {JSON.stringify({ questions }, null, 2)}
          </pre>
        </DialogContent>
      </Dialog>
    </>
  )
}
