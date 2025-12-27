import { MessageSquare } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { MessagePublic } from "@/client"

interface MessageActionsProps {
  message: MessagePublic
  onAnswerQuestions: () => void
}

export function MessageActions({ message, onAnswerQuestions }: MessageActionsProps) {
  // Only show if message has unanswered questions
  if (message.tool_questions_status !== "unanswered") {
    return null
  }

  return (
    <div className="mt-2 flex gap-2 justify-end">
      <Button
        variant="outline"
        size="sm"
        className="text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950"
        onClick={onAnswerQuestions}
      >
        <MessageSquare className="h-4 w-4 mr-1.5" />
        Answer Questions
      </Button>
    </div>
  )
}
