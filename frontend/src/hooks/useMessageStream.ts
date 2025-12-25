import { useState, useCallback } from "react"
import { useQueryClient } from "@tanstack/react-query"

interface StreamEvent {
  type: "session_created" | "assistant" | "tool" | "result" | "error" | "done" | "thinking"
  content?: string
  session_id?: string
  metadata?: Record<string, any>
  error_type?: string
  tool_name?: string
}

interface UseMessageStreamOptions {
  sessionId: string
  onSuccess?: () => void
  onError?: (error: Error) => void
}

export function useMessageStream({ sessionId, onSuccess, onError }: UseMessageStreamOptions) {
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingContent, setStreamingContent] = useState("")
  const [streamingEvents, setStreamingEvents] = useState<StreamEvent[]>([])
  const queryClient = useQueryClient()

  const sendMessage = useCallback(async (content: string) => {
    setIsStreaming(true)
    setStreamingContent("")
    setStreamingEvents([])

    // Optimistically add user message to the cache immediately
    const tempUserMessageId = `temp-${Date.now()}`
    queryClient.setQueryData(["messages", sessionId], (old: any) => {
      if (!old) return old

      const newUserMessage = {
        id: tempUserMessageId,
        session_id: sessionId,
        role: "user",
        content: content,
        sequence_number: (old.data?.length || 0) + 1,
        timestamp: new Date().toISOString(),
        message_metadata: {},
      }

      return {
        ...old,
        data: [...(old.data || []), newUserMessage],
        count: (old.count || 0) + 1,
      }
    })

    try {
      const token = localStorage.getItem("access_token")
      if (!token) {
        throw new Error("Not authenticated")
      }

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/api/v1/sessions/${sessionId}/messages/stream`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Authorization": `Bearer ${token}`,
          },
          body: JSON.stringify({ content }),
        }
      )

      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Failed to send message: ${response.status} - ${errorText}`)
      }

      if (!response.body) {
        throw new Error("No response body")
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()

      let buffer = ""
      let contentParts: string[] = []
      let streamCompleted = false

      while (true) {
        const { done, value } = await reader.read()

        if (done) {
          streamCompleted = true
          break
        }

        // Decode the chunk and add to buffer
        buffer += decoder.decode(value, { stream: true })

        // Process complete SSE messages
        const lines = buffer.split("\n")
        buffer = lines.pop() || "" // Keep incomplete line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6)

            try {
              const event: StreamEvent = JSON.parse(dataStr)

              // Skip events with no content (system init, empty results, etc.)
              // But allow "tool" type even with minimal content to show tool usage
              if (!event.content || (event.content.trim() === "" && event.type !== "tool")) {
                // Still track the event but don't display it
                setStreamingEvents(prev => [...prev, event])
                continue
              }

              setStreamingEvents(prev => [...prev, event])

              // Accumulate content from assistant and tool messages
              if (event.type === "assistant") {
                contentParts.push(event.content)
                setStreamingContent(contentParts.join("\n"))
              } else if (event.type === "tool") {
                // Add tool usage as separate section
                contentParts.push(`\n---\n${event.content}\n---`)
                setStreamingContent(contentParts.join("\n"))
              }

              // Handle errors
              if (event.type === "error") {
                console.error("Stream error:", event)
                throw new Error(event.content || "Unknown stream error")
              }

              // Stream is done
              if (event.type === "done") {
                streamCompleted = true
              }
            } catch (parseError) {
              console.error("Failed to parse SSE event:", dataStr, parseError)
            }
          }
        }
      }

      // Always refresh messages after stream completes successfully
      if (streamCompleted) {
        console.log("Stream completed, refreshing messages...")

        // Small delay to ensure backend finishes writing to database
        await new Promise(resolve => setTimeout(resolve, 300))

        await queryClient.invalidateQueries({ queryKey: ["messages", sessionId] })
        onSuccess?.()
      }

      setIsStreaming(false)
      setStreamingContent("")
      setStreamingEvents([])
    } catch (error) {
      console.error("Message stream error:", error)
      setIsStreaming(false)
      setStreamingContent("")
      setStreamingEvents([])

      // Remove optimistic message and refresh from server
      try {
        await new Promise(resolve => setTimeout(resolve, 300))
        await queryClient.invalidateQueries({ queryKey: ["messages", sessionId] })
      } catch (refreshError) {
        console.error("Failed to refresh messages after error:", refreshError)
      }

      onError?.(error instanceof Error ? error : new Error(String(error)))
    }
  }, [sessionId, queryClient, onSuccess, onError])

  return {
    sendMessage,
    isStreaming,
    streamingContent,
    streamingEvents,
  }
}
