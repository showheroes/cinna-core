# Tool Call Rendering — Technical Reference

## File Locations

### Dispatcher

- `frontend/src/components/Chat/ToolCallBlock.tsx` — Central dispatcher: imports all specialized blocks, matches `toolName.toLowerCase()` + required input fields, delegates rendering. Handles compact mode branching for Read, Edit, Bash tools inline

### Specialized Tool Blocks

- `frontend/src/components/Chat/ReadToolBlock.tsx` — Displays `file_path` from tool input
- `frontend/src/components/Chat/WriteToolBlock.tsx` — Displays `file_path` and `content`
- `frontend/src/components/Chat/EditToolBlock.tsx` — Displays `file_path` with `old_string` → `new_string` comparison
- `frontend/src/components/Chat/BashToolBlock.tsx` — Displays `command` in a styled block
- `frontend/src/components/Chat/CompactBashBlock.tsx` — Compact variant of BashToolBlock, used when `conversationModeUi === "compact"`
- `frontend/src/components/Chat/GlobToolBlock.tsx` — Displays `pattern` for file matching
- `frontend/src/components/Chat/WebSearchToolBlock.tsx` — Displays `query` text
- `frontend/src/components/Chat/WebFetchToolBlock.tsx` — Displays `url` as clickable link with optional `prompt` subtitle
- `frontend/src/components/Chat/TodoWriteToolBlock.tsx` — Renders `todos[]` array with status checkmarks (pending/in_progress/completed)
- `frontend/src/components/Chat/AskUserQuestionToolBlock.tsx` — Shows count of `questions[]`, opens debug modal on click
- `frontend/src/components/Chat/KnowledgeQueryToolBlock.tsx` — Shows `query` + optional `article_ids` list
- `frontend/src/components/Chat/AgentHandoverToolBlock.tsx` — Shows `target_agent_name`/`target_agent_id` + `task_message`, differentiates direct handover from inbox task
- `frontend/src/components/Chat/UpdateSessionStateToolBlock.tsx` — Shows `state` (completed/needs_input/error) + `summary`
- `frontend/src/components/Chat/WebappActionBlock.tsx` — Shows action name + data payload (rendered in StreamEventRenderer, not ToolCallBlock dispatcher)

### Supporting Components

- `frontend/src/components/Chat/MarkdownRenderer.tsx` — Used by default renderer for markdown-like tool input values
- `frontend/src/components/Chat/StreamEventRenderer.tsx` — Routes `type === "tool"` events to ToolCallBlock, routes `type === "webapp_action"` directly to WebappActionBlock

## Data Flow

### During Streaming

```
WebSocket stream_event (type: "tool")
  → useSessionStreaming handler
  → streamingEvents state update
  → MessageList passes to StreamingMessage
  → StreamingMessage renders StreamEventRenderer
  → StreamEventRenderer checks event.type === "tool"
  → ToolCallBlock receives: toolName=event.tool_name, toolInput=event.metadata.tool_input, conversationModeUi
```

### In Persisted Messages

```
MessageBubble receives message
  → Extracts streaming_events from message.message_metadata.streaming_events
  → Passes to StreamEventRenderer
  → Same dispatch path as streaming
```

## Props Interface

`ToolCallBlockProps`:
- `toolName: string` — Tool identifier, lowercased for matching
- `toolInput?: Record<string, any>` — Structured tool parameters
- `conversationModeUi?: string` — `"detailed"` (default) or `"compact"`

## Extending with New Tool Blocks

1. Create `frontend/src/components/Chat/YourToolBlock.tsx` with appropriate props <!-- nocheck -->
2. Import in `frontend/src/components/Chat/ToolCallBlock.tsx`
3. Add condition before the default renderer: `if (toolNameLower === "newtool" && toolInput?.required_field) { return <NewToolBlock ... /> }`
4. For compact mode support: check `isCompact` and return simplified JSX or a dedicated compact component
5. Unrecognized tools always fall through to the default JSON renderer — the new block is purely an enhancement

## Styling Conventions

- Tool blocks use `text-sm` sizing with muted foreground colors
- Icons from `lucide-react` at `h-3.5 w-3.5` to `h-4 w-4`
- Background: `bg-slate-100 dark:bg-slate-800` for default, specialized blocks may vary
- Code/path values: `font-mono bg-muted px-1 py-0.5 rounded text-xs`
- Compact blocks: inline-flex layout, minimal vertical space
