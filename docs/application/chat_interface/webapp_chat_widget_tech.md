# Webapp Chat Widget — Technical Reference

## File Locations

- `frontend/src/components/Webapp/WebappChatWidget.tsx` — Self-contained widget component: FAB, chat panel, message rendering, streaming, caching, page context, action forwarding
- `frontend/src/routes/webapp/$webappToken.tsx` — Webapp viewer route: auth flow, embed support, delegates to WebappChatWidget
- `frontend/src/services/eventService.ts` — Socket.IO client used for WebSocket subscriptions (shared with session page)
- `frontend/src/components/Chat/MessageBubble.tsx` — Reused for message rendering inside widget
- `frontend/src/components/Chat/StreamingMessage.tsx` — Reused for live streaming display
- `frontend/src/components/Chat/StreamEventRenderer.tsx` — Reused for per-event type rendering
- `backend/app/api/routes/webapp_chat.py` — Public webapp chat endpoints (session CRUD, messages, streaming, interrupt)

## Component Architecture

`WebappChatWidget` is a single self-contained component (not using `useSessionStreaming` hook). It manages:

### State
- `isOpen: boolean` — Panel visibility
- `sessionId: string | null` — Active session, from cache or API
- `messages: MessagePublic[]` — Message list, from cache or API
- `streamingEvents: StreamEvent[]` — Live events from WebSocket
- `isStreaming: boolean` — Local streaming flag
- `isSending: boolean` — Message send in progress
- `hasUnread: boolean` — FAB badge indicator
- `inputValue: string` — Textarea content
- `error: string | null` — Error banner text

### Refs
- `lastKnownSeqRef` — Highest seen `event_seq` for deduplication
- `streamSubscriptionRef` — EventService subscription ID for stream events
- `streamRoomRef` — Current WebSocket room name
- `sessionStatusSubRef` — EventService subscription ID for status changes
- `needsBackgroundVerifyRef` — Flag for cache-restored sessions needing verify
- `backgroundVerifyDoneRef` — Guard preventing duplicate background verify
- `cacheRestoredRef` — Guard preventing duplicate cache restore
- `messagesEndRef` — Auto-scroll target
- `textareaRef` — Input focus management

## Cache Implementation

### Functions
- `getCacheKey(webappToken)` — Returns `webapp_chat_{webappToken}`
- `readCache(webappToken)` — Reads and validates JSON from localStorage, returns `WebappChatCache | null`
- `writeCache(webappToken, sessionId, messages)` — Writes `{ sessionId, messages, cachedAt }` to localStorage
- `clearCache(webappToken)` — Removes cache entry

### Restore Flow (Mount)
1. `useEffect` on `[webappToken]` — reads cache once via `cacheRestoredRef` guard
2. If cached: sets `sessionId`, `messages`, `needsBackgroundVerifyRef = true`, shows unread badge
3. `useEffect` on `[sessionId]` — when `needsBackgroundVerifyRef` is true, calls `loadExistingSession(true)`
4. Background verify: fetches session from API silently (no spinner), updates messages if found, preserves cache on failure

### Persist Flow
- `useEffect` on `[sessionId, messages, webappToken]` — writes cache on every change

## Page Context Collection

### `collectIframeContext(iframeRef)`
- Sends `postMessage({ type: "request_page_context" })` to `iframeRef.current.contentWindow`
- Listens for `page_context_response` message with matching `event.source`
- Timeout: `PAGE_CONTEXT_TIMEOUT_MS = 500`
- Returns `Record<string, unknown> | null`

### `buildPageContext(iframeRef)`
- Captures `window.getSelection()`, truncates to `MAX_SELECTED_TEXT_CHARS = 2000`
- Calls `collectIframeContext()` for iframe microdata
- Builds JSON payload: `{ selected_text?, page: { url, title }, microdata? }`
- Returns `string | undefined` (undefined when no context available)

### Send Integration
- `handleSend()` runs `Promise.all([ensureSession(), buildPageContext(iframeRef)])` concurrently
- Adds `page_context` to request body only when present

## Streaming Implementation

### Status Subscription
- `useEffect` on `[sessionId, isOpen]` — subscribes to `session_interaction_status_changed`
- On "running"/"pending_stream": `setIsStreaming(true)`
- On "" (empty): `setIsStreaming(false)`, clear events, refresh messages, set unread badge if closed

### Event Subscription
- `useEffect` on `[sessionId, isStreaming]` — when streaming active:
  - Subscribes to room `session_{sessionId}_stream` via `eventService.subscribeToRoom()`
  - Subscribes to `stream_event` events
  - `stream_completed` → stop streaming, refresh messages
  - `webapp_action` → forward to iframe via `postMessage`
  - Other events → deduplicate by `event_seq`, append to `streamingEvents`

### Cleanup
- `useEffect` cleanup on unmount: unsubscribes from all event subscriptions and rooms

## API Helper

`chatFetch(path, options)` — Wrapper around `fetch()`:
- Prepends `{VITE_API_URL}/api/v1` to path
- Adds JWT from `localStorage.getItem("webapp_access_token")`
- Adds `Content-Type: application/json` header
- Throws on non-ok response with status + body text

## UI Layout

### FAB (Collapsed)
- Fixed position: `bottom-4 right-4 z-50`
- Size: `h-12 w-12 rounded-full`
- Unread badge: `absolute -top-1 -right-1 h-3 w-3 rounded-full bg-destructive`

### Panel (Expanded)
- Fixed position: `bottom-4 right-4 z-50`
- Size: `w-[460px] max-w-[calc(100vw-2rem)]`, height: `min(600px, calc(100vh-6rem))`
- Layout: flex column with header (shrink-0), messages (flex-1 overflow-y-auto), error (optional), input (shrink-0)
- Header: agent name, mode badge (blue=conversation, orange=building), close button
- Input: auto-growing textarea (36px → 100px), send/stop button

### `conversationModeUi` Derivation
- `chatMode === "conversation"` → `"compact"`
- `chatMode === "building"` → `"detailed"`
