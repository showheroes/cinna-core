# Auto-Scroll & Streaming Display — Technical Reference

## File Locations

- `frontend/src/components/Chat/MessageList.tsx` — Scroll management, zone splitting, scroll-down button
- `frontend/src/components/Chat/StreamingMessage.tsx` — Live streaming event display with pulsing loader
- `frontend/src/components/Chat/StreamEventRenderer.tsx` — Per-event type rendering
- `frontend/src/components/Webapp/WebappChatWidget.tsx` — Simplified always-scroll implementation
- `frontend/src/hooks/useSessionStreaming.ts` — Streaming state, event accumulation, `sendMessage()`, `stopMessage()`
- `frontend/src/routes/_layout/session/$sessionId.tsx` — Dynamic polling intervals, WebSocket status listener

## MessageList Scroll Implementation

### Refs and State

- `scrollContainerRef: RefObject<HTMLDivElement>` — The scrollable container div (`overflow-y-auto`)
- `messagesEndRef: RefObject<HTMLDivElement>` — Invisible div at the very end of the message list
- `userHasScrolled: boolean` — Tracks whether user has manually scrolled away from bottom
- `showScrollButton: boolean` — Controls visibility of floating scroll-down button

### `scrollToBottom()`

Calls `messagesEndRef.current?.scrollIntoView({ behavior: "smooth" })` and resets `userHasScrolled = false`.

### `handleScroll()`

Attached to `scrollContainerRef` via `onScroll`. Reads:
- `scrollTop`, `scrollHeight`, `clientHeight` from scroll container
- `isNearBottom = scrollHeight - scrollTop - clientHeight < 100`
- Updates both `showScrollButton` and `userHasScrolled` based on `!isNearBottom`

### Auto-Scroll Effects

1. Mount effect: `useEffect(() => scrollToBottom(), [])` — initial scroll on render
2. Content effect: `useEffect(() => { if (!userHasScrolled) scrollToBottom() }, [messages, streamingEvents, userHasScrolled])` — scroll on new content only when stuck to bottom

### Scroll-Down Button

Rendered as absolute-positioned `Button` in bottom-right corner (`absolute bottom-4 right-4`), shown when `showScrollButton` is true. Uses `ArrowDown` lucide icon, `rounded-full shadow-lg` styling.

## Zone Split Implementation

In `MessageList.tsx`, the rendering logic inside a self-invoking function:

1. If `!isStreaming`: flat render of all messages as `MessageBubble[]`
2. If `isStreaming`:
   - `streamingMsg = messages.find(m => m.message_metadata?.streaming_in_progress)`
   - `streamingSeq = streamingMsg?.sequence_number ?? Infinity`
   - `beforeStreaming = messages.filter(m => !streaming_in_progress && seq < streamingSeq)`
   - `afterStreaming = messages.filter(m => !streaming_in_progress && seq > streamingSeq)`
   - Renders: `beforeStreaming.map(MessageBubble)` → `StreamingMessage` → `afterStreaming.map(MessageBubble)`

## WebappChatWidget Scroll

Simpler implementation without user-scroll tracking:

- `messagesEndRef` at end of messages div
- `scrollToBottom()` wrapped in `useCallback` (stable reference)
- Effect: `useEffect(() => scrollToBottom(), [messages, streamingEvents, scrollToBottom])` — always scrolls

## Streaming State Derivation

`useSessionStreaming.ts`:
- `isStreaming` is NOT local state — derived from `session.interaction_status`:
  - `"running"` or `"pending_stream"` → true
  - `""` → false
- Frontend subscribes to `session_interaction_status_changed` WebSocket events for instant detection
- Session query also polls at 3s during streaming as fallback

`WebappChatWidget.tsx`:
- `isStreaming` IS local state — set from `session.interaction_status` on load and from WebSocket events
- Updated via `session_interaction_status_changed` event subscription

## Dynamic Polling Configuration

In `frontend/src/routes/_layout/session/$sessionId.tsx`:

- Session query: `refetchInterval: isSessionStreaming ? 3000 : 10000`
- Messages query: `refetchInterval: isSessionStreaming ? 2000 : undefined`

WebSocket `session_interaction_status_changed` handler calls `queryClient.invalidateQueries()` for immediate refresh.
