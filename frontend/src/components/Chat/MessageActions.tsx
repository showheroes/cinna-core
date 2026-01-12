import { MessageSquare, ShieldCheck, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import type { MessagePublic } from "@/client"

interface MessageActionsProps {
  message: MessagePublic
  onAnswerQuestions?: () => void
  // Tool approval props
  hasToolsNeedingApproval?: boolean
  toolsNeedingApproval?: string[]
  isApprovingTools?: boolean
  onApproveTools?: () => void
}

export function MessageActions({
  message,
  onAnswerQuestions,
  hasToolsNeedingApproval = false,
  toolsNeedingApproval = [],
  isApprovingTools = false,
  onApproveTools,
}: MessageActionsProps) {
  const hasUnansweredQuestions = message.tool_questions_status === "unanswered"

  // Don't render if no actions to show
  if (!hasUnansweredQuestions && !hasToolsNeedingApproval) {
    return null
  }

  return (
    <div className="mt-2 flex gap-2 justify-end flex-wrap">
      {/* Answer Questions button */}
      {hasUnansweredQuestions && onAnswerQuestions && (
        <Button
          variant="outline"
          size="sm"
          className="text-blue-700 dark:text-blue-300 border-blue-300 dark:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-950"
          onClick={onAnswerQuestions}
        >
          <MessageSquare className="h-4 w-4 mr-1.5" />
          Answer Questions
        </Button>
      )}

      {/* Approve Tools button */}
      {hasToolsNeedingApproval && onApproveTools && (
        <Button
          variant="outline"
          size="sm"
          className="text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950"
          onClick={onApproveTools}
          disabled={isApprovingTools}
          title={`Approve ${toolsNeedingApproval.length} tool${toolsNeedingApproval.length > 1 ? "s" : ""}: ${toolsNeedingApproval.join(", ")}`}
        >
          {isApprovingTools ? (
            <Loader2 className="h-4 w-4 mr-1.5 animate-spin" />
          ) : (
            <ShieldCheck className="h-4 w-4 mr-1.5" />
          )}
          {isApprovingTools ? "Approving..." : `Approve Tool${toolsNeedingApproval.length > 1 ? "s" : ""}`}
        </Button>
      )}
    </div>
  )
}
