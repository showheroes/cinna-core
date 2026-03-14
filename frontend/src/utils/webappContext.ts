/**
 * Shared utilities for collecting webapp page context from an iframe.
 *
 * Used by:
 * - WebappChatWidget (public webapp share chat)
 * - PromptActionsOverlay (dashboard block prompt actions)
 *
 * Context is collected via postMessage to the webapp iframe, which must include
 * context-bridge.js. The bridge responds with schema.org microdata, page URL/title,
 * and any selected text. The result is passed as `page_context` on message payloads
 * so the backend can inject it into the agent's conversation context.
 */

import type { RefObject } from "react"

const MAX_SELECTED_TEXT_CHARS = 2_000
const PAGE_CONTEXT_TIMEOUT_MS = 500

/**
 * Collect schema.org microdata from the webapp iframe via postMessage.
 *
 * Sends a "request_page_context" message to the iframe's contentWindow and
 * waits up to PAGE_CONTEXT_TIMEOUT_MS ms for a "page_context_response" reply.
 * Returns null silently on timeout or if no iframe is available — the message
 * will still send, just without page context.
 */
export async function collectIframeContext(
  iframeRef?: RefObject<HTMLIFrameElement | null>
): Promise<Record<string, unknown> | null> {
  const iframe = iframeRef?.current
  // Capture contentWindow into a narrowed non-nullable local so closures below
  // can reference it safely without repeated null checks.
  const contentWindow = iframe?.contentWindow
  if (!contentWindow) return null

  return new Promise((resolve) => {
    const timer = setTimeout(() => {
      window.removeEventListener("message", handler)
      resolve(null)
    }, PAGE_CONTEXT_TIMEOUT_MS)

    function handler(event: MessageEvent) {
      if (
        !event.data ||
        event.data.type !== "page_context_response" ||
        event.source !== contentWindow
      ) {
        return
      }
      clearTimeout(timer)
      window.removeEventListener("message", handler)
      resolve(event.data.context ?? null)
    }

    window.addEventListener("message", handler)
    contentWindow.postMessage({ type: "request_page_context" }, "*")
  })
}

/**
 * Build the page_context string to attach to a chat message.
 *
 * Combines the user's current text selection with schema.org microdata
 * scraped from the webapp iframe. Returns undefined if both are absent
 * so the field can be omitted from the request body entirely.
 */
export async function buildPageContext(
  iframeRef?: RefObject<HTMLIFrameElement | null>
): Promise<string | undefined> {
  const rawSelection = window.getSelection()?.toString() ?? ""
  const selectedText = rawSelection.slice(0, MAX_SELECTED_TEXT_CHARS)

  const iframeContext = await collectIframeContext(iframeRef)

  if (!selectedText && !iframeContext) return undefined

  const payload: Record<string, unknown> = {}
  if (selectedText) payload.selected_text = selectedText
  if (iframeContext) {
    payload.page = {
      url: (iframeContext as any).url ?? "",
      title: (iframeContext as any).title ?? "",
    }
    const microdata = (iframeContext as any).microdata
    if (Array.isArray(microdata) && microdata.length > 0) {
      payload.microdata = microdata
    }
  }

  return Object.keys(payload).length > 0
    ? JSON.stringify(payload)
    : undefined
}
