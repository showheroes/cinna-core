# AskUserQuestion Tool Widget

## Overview

The AskUserQuestion tool widget enables LLM agents to ask structured questions to users during a conversation and receive formatted answers. The system automatically detects when questions are asked, presents them in an interactive modal, and maintains the question-answer state across page refreshes.

## Architecture

### Backend Components

**Database Schema** (`backend/app/models/session.py`)
- `tool_questions_status`: Tracks question state (null | "unanswered" | "answered")
- `answers_to_message_id`: Foreign key linking answer messages to their question messages

**Message Service** (`backend/app/services/message_service.py`)
- `detect_ask_user_question_tool()`: Scans streaming events for AskUserQuestion tool calls
- `create_message()`: Extended to handle question status and answer linking
- Automatic status update: When a message with `answers_to_message_id` is created, the referenced message status changes to "answered"

**Streaming Handler** (`backend/app/services/message_service.py:stream_message_with_events`)
- Detects AskUserQuestion tool in streaming events
- Automatically sets `tool_questions_status = "unanswered"` on agent messages containing questions

### Frontend Components

**Tool Block** (`frontend/src/components/Chat/AskUserQuestionToolBlock.tsx`)
- Compact display showing question count
- Clickable to view debug details
- Styled with subtle slate background to differentiate from message content

**Message Actions** (`frontend/src/components/Chat/MessageActions.tsx`)
- Positioned below message bubble, aligned left
- "Answer Questions" button appears only when `tool_questions_status === "unanswered"`
- Hidden once questions are answered

**Answer Modal** (`frontend/src/components/Chat/AnswerQuestionsModal.tsx`)
- Progress indicator showing answered/unanswered questions (only displayed when multiple questions present)
- Support for single-select (radio) and multi-select (checkbox) questions
- Custom text input option for every question
- Visual highlighting: selected answers highlighted, unselected faded
- "(Recommended)" options highlighted with star icon
- "Send Answers" button disabled until all questions answered

**Message Integration** (`frontend/src/components/Chat/MessageBubble.tsx`)
- Extracts questions from `message_metadata.streaming_events`
- Deduplicates questions by exact text matching (handles duplicate tool calls)
- Renders MessageActions component below bubble
- Manages AnswerQuestionsModal state

**Streaming Hook** (`frontend/src/hooks/useMessageStream.ts`)
- Extended `sendMessage()` to accept optional `answersToMessageId` parameter
- Optimistic UI updates: immediately marks questions as "answered" before server confirmation
- Includes `answers_to_message_id` in API request body

## User Flow

1. **Agent asks questions**: LLM calls AskUserQuestion tool with structured questions
2. **Detection**: Backend detects tool call and sets `tool_questions_status = "unanswered"`
3. **Display**: Frontend shows compact question block in message and "Answer Questions" button below bubble
4. **User interaction**: Click button to open modal with all questions
5. **Answer**: User selects/enters answers for each question (progress tracked visually)
6. **Submit**: Formatted answer message sent with `answers_to_message_id` linking to original question message
7. **Status update**: Backend updates original message status to "answered", button disappears

## Question Deduplication

**Problem**: LLM may call AskUserQuestion multiple times in a single response

**Solution** (`MessageBubble.tsx:extractQuestions()`):
- Iterate through all streaming events
- Collect all questions from AskUserQuestion tool calls
- Deduplicate by exact question text using Set
- Keep only first occurrence of each unique question

## Answer Format

Answers are formatted as structured text with clear labeling and bullet points:

**Single-select questions:**
```
Question text here?
Answer: Selected option label
```

**Multi-select questions:**
```
Question text here?
Answers:
- Selected option 1
- Selected option 2
- Custom answer: User's custom text
```

**Custom answers:**
- Single-select: Prefixed with "Custom answer: "
- Multi-select: Added as bullet point with "Custom answer: " prefix

**Spacing:**
- Questions separated by blank lines for readability
- Each answer on its own line for multi-select

## Optimistic UI Updates

**Strategy** (`useMessageStream.ts`):
1. User submits answers
2. Immediately update message status to "answered" in React Query cache
3. Close modal and hide action button
4. Send request to backend
5. Backend confirms update in response
6. Cache refreshes with server state

**Benefits**:
- Instant UI feedback
- Smooth user experience
- No flickering or state inconsistencies

## State Persistence

**Database**: `tool_questions_status` stored in PostgreSQL
**Refresh behavior**: Status survives page refreshes
**Message linking**: `answers_to_message_id` creates audit trail of Q&A flow

## Styling Philosophy

**Tool Blocks**: Subtle slate background (`bg-slate-100 dark:bg-slate-800`)
- More prominent than plain text but less than main message
- Clear visual distinction without distraction

**Action Button**: Outside bubble, left-aligned
- Separates actions from message content
- Consistent with message flow direction

**Modal**: Full-featured UI
- Progress tracking
- Visual feedback on selection
- Accessibility (keyboard navigation, ARIA roles)

## Key Design Decisions

1. **Status outside bubble**: Actions don't clutter message content
2. **Automatic detection**: No manual flagging by agent needed
3. **Deduplication**: Handles LLM calling tool multiple times gracefully
4. **Optimistic updates**: Instant feedback despite async operations
5. **Compact tool block**: Questions visible but not overwhelming
6. **Custom input always available**: Users not forced into predefined answers
7. **Foreign key relationship**: Maintains data integrity and enables Q&A tracing

## Related Files

- Backend: `backend/app/models/session.py`, `backend/app/services/message_service.py`, `backend/app/api/routes/messages.py`
- Frontend: `frontend/src/components/Chat/AskUserQuestionToolBlock.tsx`, `frontend/src/components/Chat/AnswerQuestionsModal.tsx`, `frontend/src/components/Chat/MessageActions.tsx`, `frontend/src/components/Chat/MessageBubble.tsx`, `frontend/src/hooks/useMessageStream.ts`
- Migration: `backend/app/alembic/versions/bfbae71690bb_add_tool_questions_status_and_answers_.py`