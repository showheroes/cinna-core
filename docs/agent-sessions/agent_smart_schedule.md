# Agent Smart Scheduler

## Overview

The **Agent Smart Scheduler** allows users to configure multiple automatic execution schedules per agent using natural language instead of manually crafting CRON expressions. Users can type phrases like "every workday in the morning at 7" and an AI function converts this to a proper CRON string with timezone awareness.

Each agent can have **multiple schedules**, each with its own timing, description, and optional custom prompt. This enables agents that perform different actions on different cadences (e.g., collect data snapshots daily, produce a weekly summary).

## User Experience Flow

### 1. Scheduler Configuration UI

**Location**: Agent Config Tab → "Schedules" card (side by side with Handovers)

**Component**: `frontend/src/components/Agents/AgentSchedulesCard.tsx`

The Schedules card follows the same pattern as MCP Connectors — a card with a list of items and create/edit dialogs.

**Card Layout**:
- **Header**: CalendarClock icon + "Schedules" title + description + "New" button
- **Content**: List of schedule rows, each showing:
  - Name (bold), description (muted), next execution time
  - Badges: enabled/disabled, "Custom prompt" if prompt is set
  - Action buttons: edit, toggle enabled/disabled, delete with confirmation

### 2. Creating a Schedule

```
1. User clicks "New" button in Schedules card header
2. Create dialog opens with:
   a. Name input (required) — e.g., "Daily data collection"
   b. Timing input + "Generate" button (AI CRON generation)
   c. Prompt textarea (optional — leave empty to use agent's entrypoint prompt)
3. User types timing: "every workday in the morning at 7"
4. User clicks "Generate"
5. AI processes input with user's timezone (from browser)
   - Returns: CRON string and refined description
6. Backend calculates next execution time
7. Preview displays:
   - Description: "Every weekday at 7:00 AM, Central European Time"
   - Next execution: "Monday, March 3, 2026 at 7:00 AM CET"
8. User clicks "Create" to save
9. New AgentSchedule record is created in database
```

### 3. Editing a Schedule

```
1. User clicks edit (pencil) button on a schedule row
2. Edit dialog opens pre-populated with current values:
   a. Name input
   b. Current schedule info display (description, next execution)
   c. Timing input + "Generate" button (to change timing)
   d. Prompt textarea (pre-populated)
3. User can change name, prompt, and/or regenerate timing
4. User clicks "Save"
```

### 4. Toggling and Deleting

- **Toggle**: Click power button to enable/disable without deleting
- **Delete**: Click trash button → confirmation dialog → permanently removed

### 5. Visual Layout

```
┌─────────────────────────────────────────────────────────────┐
│ 🕐 Schedules                                          [New] │
│ Schedule execution times for this agent with different      │
│ prompts and cadences                                        │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Daily data collection    [Enabled] [Custom prompt]  ✏⚡🗑│ │
│ │ Every weekday at 7:00 AM, CET                          │ │
│ │ 🕐 Next: Monday, March 3, 2026 at 7:00 AM CET         │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Weekly summary           [Enabled]                  ✏⚡🗑│ │
│ │ Every Friday at 5:00 PM, CET                           │ │
│ │ 🕐 Next: Friday, March 7, 2026 at 5:00 PM CET         │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Hourly monitoring        [Disabled]                 ✏⚡🗑│ │
│ │ Every hour from 9 AM to 5 PM, Mon-Fri                  │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

## Business Rules

### Frequency Constraints

**Minimum execution interval: 30 minutes**

This prevents:
- Excessive API usage
- Server overload
- Unintentional infinite loops
- Cost escalation

**Valid examples**:
- ✅ "every hour"
- ✅ "every 30 minutes"
- ✅ "every day at 9 AM"
- ✅ "every Monday at 3 PM"

**Invalid examples**:
- ❌ "every 5 minutes" (too frequent)
- ❌ "every minute" (too frequent)
- ❌ "every 15 minutes" (too frequent)

### Timezone Handling

**User timezone is passed from browser to API for CRON conversion only — it is NOT stored.**

- Frontend extracts timezone: `Intl.DateTimeFormat().resolvedOptions().timeZone`
- Example values: `"America/New_York"`, `"Europe/Berlin"`, `"Asia/Tokyo"`
- AI function interprets schedule in user's timezone
- CRON string is converted to UTC before storage
- Timezone is provided transiently in create/update requests for conversion
- Next execution time is displayed in user's browser timezone

**Example**:
```
User input: "every day at 7 AM"
User timezone: "Europe/Berlin" (UTC+1)
CRON stored: "0 6 * * *" (6 AM UTC = 7 AM CET)
Display: "Every day at 7:00 AM, Central European Time"
```

### Schedule-Specific Prompts

Each schedule can have its own **prompt** field:
- If `prompt` is set: that prompt is used as the starting message when the schedule fires
- If `prompt` is null: the agent's `entrypoint_prompt` is used as fallback
- If both are null: "Start scheduled execution." is used as final fallback

This enables different actions on different cadences:
```
Agent: "Market Analyst"
├── Schedule: "Daily data collection" (prompt: "Collect today's market data snapshots")
└── Schedule: "Weekly summary" (prompt: "Produce a weekly market summary report")
```

### Cloned Agents and Scheduler

**Key Principle**: Each clone has independent scheduler configuration from its parent.

**Clone Owner Capabilities**:
- Clone owners (both "user" and "builder" modes) can create, edit, and delete their own schedules
- Scheduler UI is always available in the Configuration tab for clone owners
- Clone's schedules are completely independent from parent's schedules

**Behavior During Agent Sharing**:
- When an agent is shared/cloned, scheduler configurations are **NOT copied** to the clone
- The clone starts with **no schedules** configured
- Clone owner must set up their own schedules if needed

**Behavior During Push Updates**:
- When the parent agent owner pushes updates to clones, **scheduler configs are NOT synced**
- Push updates only sync workspace files (scripts, docs, knowledge)
- Each clone's scheduler configuration remains completely independent

## AI Function Specification

### Function Name
`generate_agent_schedule`

### Input

**Parameters**:
```python
{
    "natural_language": str,  # User's natural language input
    "timezone": str,          # IANA timezone (e.g., "Europe/Berlin")
}
```

### Output

**Success Response**:
```json
{
    "success": true,
    "description": "Every weekday at 7:00 AM, Central European Time",
    "cron_string": "0 7 * * 1-5"
}
```

**Note**: The CRON string from the AI is in **local time**. The backend converts it to UTC before storing. The backend also calculates `next_execution` from the UTC CRON string.

**Error Response**:
```json
{
    "success": false,
    "error": "Execution frequency too high: minimum interval is 30 minutes."
}
```

### Implementation

**File**: `backend/app/agents/schedule_generator.py`

Uses the provider manager for cascade LLM selection. Loads prompt template from `backend/app/agents/prompts/schedule_generator_prompt.md`.

## Backend Implementation

### Architecture Overview

**Component Responsibilities**:

1. **AI Function** (`backend/app/agents/schedule_generator.py`)
   - Converts natural language to CRON string (in local time)
   - Returns: `{ success, description, cron_string }` OR `{ success: false, error }`
   - Does NOT calculate next execution time

2. **Scheduler Service** (`backend/app/services/agent_scheduler_service.py`)
   - Converts CRON from local time to UTC
   - Calculates next execution time from UTC CRON string
   - Full multi-schedule CRUD: create, list, get, update, delete
   - Business logic layer between API and database

3. **API Routes** (`backend/app/api/routes/agents.py`)
   - `POST /{id}/schedules/generate` — AI CRON generation (stateless)
   - `POST /{id}/schedules` — Create schedule
   - `GET /{id}/schedules` — List all schedules
   - `PUT /{id}/schedules/{schedule_id}` — Update schedule
   - `DELETE /{id}/schedules/{schedule_id}` — Delete schedule

4. **Background Scheduler** (`backend/app/services/agent_schedule_scheduler.py`)
   - Polls every minute for due schedules
   - Creates sessions and sends messages using schedule-specific or agent entrypoint prompt
   - Updates execution times after each run

5. **Database Model** (`AgentSchedule`)
   - Stores schedule configuration per agent
   - Tracks execution times
   - Many-to-one relationship with Agent

### Data Flow

**Creating a schedule**:
```
User types "every workday at 7 AM" + name + optional prompt
  ↓
Frontend → POST /api/v1/agents/{id}/schedules/generate
  ↓
AI Function → Returns { description, cron_string } (local time)
  ↓
Backend converts CRON to UTC, calculates next_execution
  ↓
Frontend displays preview → User clicks "Create"
  ↓
Frontend → POST /api/v1/agents/{id}/schedules
  ↓
Service converts CRON to UTC, creates AgentSchedule record
```

**Schedule execution** (background):
```
Background scheduler polls every minute
  ↓
Finds schedules where next_execution <= now AND enabled = true
  ↓
For each due schedule:
  message = schedule.prompt OR agent.entrypoint_prompt OR fallback
  ↓
Creates session, sends message, updates last/next execution
```

### Database Schema

**Model**: `backend/app/models/agent_schedule.py`

```python
class AgentSchedule(SQLModel, table=True):
    __tablename__ = "agent_schedule"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    agent_id: uuid.UUID = Field(foreign_key="agent.id", ondelete="CASCADE")

    # Schedule identity
    name: str  # User-friendly label (e.g., "Daily data collection")

    # Schedule configuration
    cron_string: str  # CRON expression in UTC
    description: str  # Human-readable description from AI
    enabled: bool = Field(default=True)

    # Schedule-specific prompt (null = use agent's entrypoint_prompt)
    prompt: str | None = Field(default=None, sa_type=Text)

    # Execution tracking
    last_execution: datetime | None = Field(default=None)
    next_execution: datetime

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Relationship
    agent: "Agent" = Relationship(back_populates="schedules")
```

**Key changes from original single-schedule model**:
- Added `name: str` — required user-friendly label
- Added `prompt: str | None` — schedule-specific prompt (TEXT column)
- Removed `timezone: str` — timezone is transient, used only during CRON conversion

### Scheduler Service

**File**: `backend/app/services/agent_scheduler_service.py`

**Methods**:

| Method | Signature | Description |
|--------|-----------|-------------|
| `convert_local_cron_to_utc` | `(cron_string, timezone) → str` | Convert local CRON to UTC |
| `calculate_next_execution` | `(cron_string) → datetime` | Next run from UTC CRON |
| `create_schedule` | `(session, agent_id, name, cron_string, timezone, description, prompt, enabled) → AgentSchedule` | Create new schedule |
| `get_agent_schedules` | `(session, agent_id) → list[AgentSchedule]` | List all, ordered by created_at |
| `get_schedule_by_id` | `(session, schedule_id) → AgentSchedule | None` | Get single schedule |
| `update_schedule` | `(session, schedule_id, **fields) → AgentSchedule` | Partial update; recalculates next_execution if cron_string changes |
| `delete_schedule` | `(session, schedule_id) → bool` | Delete by schedule ID |
| `get_all_enabled_schedules` | `(session) → list[AgentSchedule]` | All enabled schedules (for background runner) |
| `update_execution_time` | `(session, schedule_id, last_execution) → None` | Update after execution |

### API Endpoints

**Routes in** `backend/app/api/routes/agents.py`:

| Method | Path | Purpose | Request Body | Response |
|--------|------|---------|--------------|----------|
| POST | `/{id}/schedules/generate` | AI CRON generation (stateless) | `ScheduleRequest` | `ScheduleResponse` |
| POST | `/{id}/schedules` | Create schedule | `CreateScheduleRequest` | `AgentSchedulePublic` |
| GET | `/{id}/schedules` | List all schedules | — | `AgentSchedulesPublic` |
| PUT | `/{id}/schedules/{schedule_id}` | Update schedule | `UpdateScheduleRequest` | `AgentSchedulePublic` |
| DELETE | `/{id}/schedules/{schedule_id}` | Delete schedule | — | `Message` |

All endpoints verify agent ownership. PUT/DELETE also verify `schedule.agent_id == id`.

### Request/Response Models

```python
class ScheduleRequest(SQLModel):
    """Request for AI generation (stateless)."""
    natural_language: str
    timezone: str

class ScheduleResponse(SQLModel):
    """Response from AI schedule generation."""
    success: bool
    description: str | None = None
    cron_string: str | None = None
    next_execution: str | None = None  # ISO 8601, calculated by backend
    error: str | None = None

class CreateScheduleRequest(SQLModel):
    """Request to create a new schedule."""
    name: str
    cron_string: str
    timezone: str  # For CRON conversion, not stored
    description: str
    prompt: str | None = None
    enabled: bool = True

class UpdateScheduleRequest(SQLModel):
    """Partial update. All fields optional."""
    name: str | None = None
    cron_string: str | None = None
    timezone: str | None = None  # Required when cron_string changes
    description: str | None = None
    prompt: str | None = None
    enabled: bool | None = None

class AgentSchedulePublic(SQLModel):
    """Public response for a single schedule."""
    id: uuid.UUID
    agent_id: uuid.UUID
    name: str
    cron_string: str
    description: str
    enabled: bool
    prompt: str | None
    last_execution: datetime | None
    next_execution: datetime
    created_at: datetime
    updated_at: datetime

class AgentSchedulesPublic(SQLModel):
    """List response."""
    data: list[AgentSchedulePublic]
    count: int
```

### Background Scheduler

**File**: `backend/app/services/agent_schedule_scheduler.py`

Polls every minute for due schedules. The prompt fallback chain is:

```python
message = schedule.prompt or agent.entrypoint_prompt or "Start scheduled execution."
```

This means each schedule can fire with its own custom prompt, enabling different actions on different cadences from the same agent.

## Frontend Implementation

### Component: AgentSchedulesCard

**File**: `frontend/src/components/Agents/AgentSchedulesCard.tsx`

Follows the `McpConnectorsCard` pattern (same state management, dialog approach, list layout).

**Props**: `{ agentId: string }`

**Query**: `useQuery` with key `["agent-schedules", agentId]`, calls `AgentsService.listSchedules()`

**Mutations**: create, update, toggle (update with `{enabled: !current}`), delete — all invalidate the query key

**Create Dialog**:
1. Name input (required)
2. Natural language input + "Generate" button (AI CRON generation, shows preview)
3. Prompt textarea (optional, placeholder: "Leave empty to use agent's entrypoint prompt")
4. "Create" button (disabled until name + generated schedule present)

**Edit Dialog**:
1. Name input (pre-populated)
2. Current schedule info display (description, next execution)
3. Natural language input + "Generate" button (to change timing)
4. Prompt textarea (pre-populated)
5. "Save" button

### Integration in AgentConfigTab

**File**: `frontend/src/components/Agents/AgentConfigTab.tsx`

```tsx
<div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <AgentSchedulesCard agentId={agent.id} />
    <AgentHandovers agent={agent} />
</div>
```

The old `SmartScheduler` component has been removed and replaced with `AgentSchedulesCard`.

## Common Use Cases

### Example 1: Daily Data Collection + Weekly Summary

```
Agent: "Market Analyst"

Schedule 1: "Daily data collection"
  Timing: "every workday at 7 AM"
  Prompt: "Collect today's market data snapshots for all tracked symbols"
  CRON (UTC): "0 6 * * 1-5"

Schedule 2: "Weekly summary"
  Timing: "every Friday at 5 PM"
  Prompt: "Produce a weekly market summary report based on collected data"
  CRON (UTC): "0 16 * * 5"
```

### Example 2: Different Monitoring Cadences

```
Agent: "Infrastructure Monitor"

Schedule 1: "Hourly health check"
  Timing: "every hour during work hours"
  Prompt: null (uses agent's entrypoint_prompt)
  CRON (UTC): "0 8-16 * * 1-5"

Schedule 2: "Daily incident report"
  Timing: "every day at 6 PM"
  Prompt: "Generate daily incident summary and send to team"
  CRON (UTC): "0 17 * * *"
```

### Example 3: Error Cases

**Too frequent**:
```json
{
  "success": false,
  "error": "Execution frequency too high: minimum interval is 30 minutes."
}
```

**Ambiguous**:
```json
{
  "success": false,
  "error": "Cannot extract schedule: 'sometimes' is too vague. Please specify exact time or frequency."
}
```

## Key Design Principles

1. **Multi-Schedule**: Each agent can have multiple schedules with different timings and prompts
2. **User-Friendly**: Natural language input instead of complex CRON syntax
3. **Smart**: AI understands context and common phrases
4. **Transparent**: Show exactly what the AI understood with preview
5. **Safe**: Validate frequency to prevent abuse
6. **Timezone-Aware**: Handle user's local time correctly (convert to UTC for storage)
7. **Per-Schedule Prompts**: Different schedules can trigger different agent actions
8. **Individual Control**: Each schedule can be enabled/disabled or deleted independently
9. **Informative**: Show next execution time for verification

## Success Metrics

A successful implementation should allow users to:
- ✅ Create multiple schedules per agent with different cadences
- ✅ Assign custom prompts to individual schedules
- ✅ Configure each schedule in under 30 seconds
- ✅ Understand exactly when each schedule will fire
- ✅ Toggle individual schedules on/off without deleting
- ✅ Modify schedule timing, name, or prompt independently
- ✅ Avoid accidentally creating high-frequency executions
- ✅ Work in their local timezone naturally
