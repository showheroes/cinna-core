import { useState } from "react"
import { formatDistanceToNow } from "date-fns"
import type { MessagePublic } from "@/client"
import ReactMarkdown from "react-markdown"
import { StreamEventRenderer } from "./StreamEventRenderer"
import { MessageActions } from "./MessageActions"
import { AnswerQuestionsModal } from "./AnswerQuestionsModal"
import { Info } from "lucide-react"

interface MessageBubbleProps {
  message: MessagePublic
  onSendAnswer?: (content: string, answersToMessageId: string) => void
}

export function MessageBubble({ message, onSendAnswer }: MessageBubbleProps) {
  const [showAnswerModal, setShowAnswerModal] = useState(false)

  const isUser = message.role === "user"
  const isSystem = message.role === "system"

  if (isSystem) {
    return (
      <div className="flex justify-center my-4">
        <div className="bg-muted text-muted-foreground text-sm px-4 py-2 rounded-full max-w-md text-center">
          {message.content}
        </div>
      </div>
    )
  }

  // Extract metadata for display
  const model = message.message_metadata?.model as string | undefined
  const totalCost = message.message_metadata?.total_cost_usd as number | undefined
  const durationMs = message.message_metadata?.duration_ms as number | undefined
  const numTurns = message.message_metadata?.num_turns as number | undefined
  const streamingEvents = (message.message_metadata?.streaming_events || []) as any[]

  // Extract and deduplicate questions from AskUserQuestion tool calls
  const extractQuestions = () => {
    const questions: any[] = []
    const seen = new Set<string>()

    streamingEvents.forEach((event) => {
      if (event.type === "tool" && event.tool_name === "AskUserQuestion") {
        const toolQuestions = event.metadata?.tool_input?.questions || []
        toolQuestions.forEach((q: any) => {
          if (!seen.has(q.question)) {
            seen.add(q.question)
            questions.push(q)
          }
        })
      }
    })

    return questions
  }

  const questions = extractQuestions()
  const hasQuestions = message.tool_questions_status === "unanswered" && questions.length > 0

  // Handle answer submission
  const handleAnswerSubmit = (answers: string, messageId: string) => {
    if (onSendAnswer) {
      onSendAnswer(answers, messageId)
    }
  }

  // Format UTC timestamp - handle invalid dates
  let formattedTime = "Just now"
  let utcTimestamp = ""

  try {
    if (message.timestamp) {
      // Handle timestamp - it might already have 'Z' from optimistic updates
      const timestampStr = typeof message.timestamp === 'string'
        ? (message.timestamp.endsWith('Z') ? message.timestamp : message.timestamp + 'Z')
        : message.timestamp

      const date = new Date(timestampStr)
      if (!isNaN(date.getTime())) {
        formattedTime = formatDistanceToNow(date, { addSuffix: true })
        utcTimestamp = date.toUTCString()
      }
    }
  } catch (error) {
    console.error("Error formatting timestamp:", error, message.timestamp)
  }

  const durationSec = durationMs ? (durationMs / 1000).toFixed(2) : null

  return (
    <>
      <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-2`}>
        <div className="max-w-[70%]">
          <div
            className={`rounded-lg px-4 py-3 ${
              isUser
                ? "bg-primary text-primary-foreground"
                : "bg-muted text-foreground"
            }`}
          >
            <div className="space-y-2">
              {isUser ? (
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              ) : (
                <StreamEventRenderer events={streamingEvents} />
              )}
              <div className="flex items-center justify-between gap-2">
                <p
                  className={`text-xs ${
                    isUser ? "text-primary-foreground/70" : "text-muted-foreground"
                  }`}
                >
                  {formattedTime}
                </p>
                {!isUser && (model || totalCost || durationSec || numTurns) && (
                  <div
                    className="cursor-help"
                    title={[
                      `UTC Time: ${utcTimestamp}`,
                      model ? `Model: ${model}` : null,
                      totalCost ? `Cost: $${totalCost.toFixed(6)} USD` : null,
                      durationSec ? `Duration: ${durationSec}s` : null,
                      numTurns ? `Turns: ${numTurns}` : null,
                    ]
                      .filter(Boolean)
                      .join('\n')}
                  >
                    <Info className="w-3.5 h-3.5 text-muted-foreground/40 hover:text-muted-foreground/70 transition-colors" />
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Message Actions - Outside bubble, aligned right, within same width container */}
          {!isUser && hasQuestions && (
            <MessageActions
              message={message}
              onAnswerQuestions={() => setShowAnswerModal(true)}
            />
          )}
        </div>
      </div>

      {/* Answer Questions Modal */}
      {!isUser && hasQuestions && (
        <AnswerQuestionsModal
          open={showAnswerModal}
          onOpenChange={setShowAnswerModal}
          questions={questions}
          messageId={message.id}
          onSubmit={handleAnswerSubmit}
        />
      )}
    </>
  )
}
