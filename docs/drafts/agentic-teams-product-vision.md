# AgenticTeams — Product Vision & Long-Term Roadmap

## The Vision

AgenticTeams is a **communication orchestration layer** where the boundary between human and AI
workers becomes fluid. Users define teams as directed graphs — nodes are workers (agents today,
humans and services tomorrow), connections are handover channels with intelligent routing rules.
Teams don't just describe structure — they *execute*, producing observable, auditable, optimizable
work sessions.

The ideal end state: **the best environment where people and agents communicate efficiently
following the same goal** — regardless of language, timezone, or whether the worker is carbon
or silicon.

---

## Who This Is For

**Primary audience**: SMB businesses worldwide (5–500 employees) who are adopting AI agents but
need structure around how agents collaborate with each other and with humans.

**Key personas**:
- **Operations Manager** — wants to automate multi-step workflows without coding
- **Business Owner** — wants visibility into what AI is doing, how much it costs, and whether it's working
- **Team Lead** — wants to define how work flows between their human team and AI assistants
- **IT Administrator** — wants governance, audit trails, and budget controls

**Why SMBs specifically**: Enterprise has custom orchestration platforms. Individual users have
single-agent tools. SMBs sit in the gap — they need multi-agent coordination but can't build it
themselves. AgenticTeams is the product that fills this gap with a visual, no-code interface.

---

## Evolution Phases

### Phase 1: Blueprint (MVP — Current)

**What it is**: A visual org-chart builder for agent teams.

**Core value**: Users can see and design how their agents relate to each other. The chart is a
static blueprint — it defines structure but doesn't execute.

**Capabilities**:
- CRUD for agentic teams (name, icon)
- Agent nodes with name, color (from agent), lead designation
- Directed connections with handover prompts
- View/edit mode toggle
- Auto-arrange (top-down hierarchy, lead at top)
- Settings card alongside Workspaces
- Sidebar navigation

**What users learn**: "This is how my agents could work together."

**Success metric**: Users create teams with 3+ nodes and configure connection prompts.

---

### Phase 2: Execution Engine

**What it is**: Teams that actually run. A task enters through the lead node, flows through
connections, and produces a result.

**Core value**: The chart becomes a living workflow. Users invoke a team, watch it work, and
get results.

**Capabilities**:

#### Team Invocation
- "Run this team on this task" — via API, via chat, via dashboard action
- Lead node receives the task input
- Each connection fires according to its prompt, passing context forward
- Terminal nodes (no outgoing connections) produce the final output
- Multiple terminal nodes = aggregated output

#### Execution Sessions
- Each "run" produces a session — a persistent record of the full execution
- Session contains: input task, per-node conversation history, per-connection message transfers,
  timestamps, token counts, final output
- Sessions are viewable, searchable, and replayable
- Session list page per team: `/agentic-teams/{id}/sessions`

#### Execution Trace Overlay
- Real-time visualization on the chart: active node pulses, completed nodes show checkmark,
  connections animate as messages flow through them
- Click any node during execution to see its live conversation
- Click any connection to see the exact message that was handed over
- After completion: trace becomes a static audit view of the full run

#### Parallel vs Sequential Execution
- Connection metadata gains `execution_mode: "sequential" | "parallel"`
- Sequential (default): connections fire one at a time in defined order
- Parallel: all outgoing connections from a node fire simultaneously; the next node waits for
  all parallel branches to complete before proceeding
- Example: "Get legal review AND technical review in parallel, then synthesize"

#### Error Handling
- Node failure: configurable behavior — retry, skip, escalate to owner, halt team
- Connection timeout: configurable per connection — if target node doesn't respond in X time,
  take fallback action
- Circuit breaker: if a node fails N times in a row, temporarily disable and notify owner

**Data model additions**:
- `agentic_team_session` table: team_id, input, output, status, started_at, completed_at,
  total_tokens, total_cost
- `agentic_team_session_event` table: session_id, node_id, connection_id, event_type, content,
  timestamp
- `execution_mode` field on `agentic_team_connection`
- `timeout_seconds` field on `agentic_team_connection`
- `on_failure` field on `agentic_team_node` (enum: retry, skip, escalate, halt)

**Success metric**: Users run teams 5+ times/week with >80% successful completions.

---

### Phase 3: Human-in-the-Loop

**What it is**: Human nodes join the graph alongside agent nodes. The team becomes a true
hybrid workforce.

**Core value**: SMBs can model their actual workflow — 3 humans + 5 agents working together,
with the system handling routing, notifications, and waiting.

**Capabilities**:

#### Human Node Types
- `node_type: "human"` — a person who receives tasks and responds
- Human nodes have a **channel**: how they receive and respond to handovers
  - Email — receives task via email, replies to complete
  - Slack — receives as Slack DM or channel message
  - WhatsApp — receives as WhatsApp message (via integration)
  - SMS — for simple approve/reject decisions
  - In-app notification — for users who are already in the platform
- Channel is configurable per human node
- Human node stores: `name`, `email`, `channel_type`, `channel_config`

#### Async Execution
- Agent-to-agent handovers are near-instant
- Agent-to-human handovers are async — the system sends the message and waits
- Human-to-agent handovers are triggered when the human responds
- Session status becomes: `running`, `waiting_for_human`, `completed`, `failed`, `timed_out`
- The execution trace shows "waiting for [Human Name] via [Channel]" with elapsed time

#### Availability & Scheduling
- Human nodes have **working hours**: Mon–Fri 9–5 in their timezone
- Human nodes have **availability status**: available, busy, OOO (with return date)
- If a human is unavailable when a handover reaches them:
  - Queue the message (default)
  - Route to a backup human node (if configured)
  - Escalate to the team owner
- Timezone stored per human node — the system converts "respond within 2 hours" to
  "2 business hours in their timezone"

#### Reminders & Escalation
- If a human hasn't responded within the connection's timeout:
  - Send a reminder (configurable: 1 reminder, 2 reminders, etc.)
  - After all reminders exhausted: escalate (notify team owner, route to backup, or halt)
- Escalation chain: configurable per human node — "if John doesn't respond in 4 hours,
  send to Sarah; if Sarah doesn't respond in 2 hours, notify the owner"

#### Approval Gates
- Special human node subtype: `node_type: "human"`, `role: "approver"`
- Receives output from previous node + structured approve/reject UI
- Approve → execution continues to next node
- Reject → execution follows the feedback connection (backward edge) back to the producer
  with the rejection reason
- Approval history tracked in session events

**Data model additions**:
- Extend `agentic_team_node`: `email`, `channel_type`, `channel_config` (JSON),
  `timezone`, `working_hours` (JSON), `availability_status`, `backup_node_id` (FK, nullable)
- Extend `agentic_team_connection`: `reminder_count`, `reminder_interval_minutes`
- New table `agentic_team_node_availability`: node_id, status, ooo_until, updated_at

**Success metric**: 40%+ of active teams include at least one human node.

---

### Phase 4: Connection Intelligence

**What it is**: Connections evolve from simple prompt strings into intelligent routing rules
with conditions, transforms, and feedback loops.

**Core value**: Teams handle complex, branching workflows — not just linear pipelines.

**Capabilities**:

#### Conditional Routing
- Connections gain `condition` field (expression or natural language)
- "If the output sentiment is negative, route to the escalation agent"
- "If the document type is 'invoice', route to the finance agent; otherwise route to the
  general agent"
- Multiple outgoing connections from a node can have different conditions — first matching
  condition fires (priority order)
- Fallback connection: `condition: null` — fires if no other condition matches

#### Transform Prompts
- `pre_handover_prompt` field on connections
- Applied to the message BEFORE it reaches the target node
- Use cases:
  - Summarize: "Condense the previous output to key bullet points"
  - Translate: "Translate to Spanish before handing over"
  - Extract: "Extract only the action items from the report"
  - Format: "Convert the raw data into a structured JSON report"
- Transform is executed by a lightweight LLM call — cost tracked separately

#### Feedback Connections (Backward Edges)
- Connections that create cycles in the graph (reviewer → author)
- Must have `max_iterations` to prevent infinite loops (default: 3)
- Use case: "The editor reviews the draft. If it needs revision, send back to the writer
  with feedback. Maximum 3 revision rounds."
- Iteration count tracked in session events
- After max iterations: proceed to next node regardless, or halt with notification

#### Priority & SLA
- `priority` field on connections: `low`, `normal`, `high`, `urgent`
- `sla_minutes` field: expected completion time for the handover
- SLA tracking: if a node takes longer than the SLA, flag in the execution trace
- SLA breach notifications to team owner
- Priority affects queue ordering when multiple tasks are pending for the same node

**Data model additions**:
- Evolve `connection_prompt` (TEXT) → `connection_config` (JSONB):
  ```json
  {
    "handover_prompt": "...",
    "pre_handover_prompt": "...",
    "condition": "...",
    "execution_mode": "sequential",
    "priority": "normal",
    "sla_minutes": 60,
    "max_iterations": 3,
    "timeout_seconds": 3600,
    "reminder_count": 2,
    "reminder_interval_minutes": 30
  }
  ```
- Migration: move existing `connection_prompt` values into `connection_config.handover_prompt`
- Keep backward-compatible API: `connection_prompt` field in API still works, maps to
  `connection_config.handover_prompt`

**Success metric**: 30%+ of connections use conditions or transforms.

---

### Phase 5: Shared Context & Knowledge

**What it is**: Teams share context, knowledge, and artifacts — not just messages.

**Core value**: Every node in a team has access to the same project brief, reference documents,
and accumulated knowledge. No more duplicating instructions across agents.

**Capabilities**:

#### Team Context (Shared Scratchpad)
- Each team has a `context` — a structured document that all nodes can read and write during
  execution
- Context is initialized when a team run starts (can be pre-filled by the user or empty)
- Any node can append to context: "Key finding: the customer's contract expires in 30 days"
- Context is passed as system context to every node in the team (not in the handover message
  itself — available as background knowledge)
- Context persists within a session but resets between sessions (unless configured otherwise)

#### Team Knowledge Base
- Each team can have attached knowledge sources (documents, URLs, databases)
- Shared across all agent nodes — no need to configure knowledge per agent separately
- Agent nodes in a team get: their own agent instructions + team knowledge base
- Knowledge base management UI: upload documents, add URLs, configure refresh schedules
- RAG integration: relevant knowledge chunks injected into agent context automatically

#### Artifact Passing
- Connections can pass structured artifacts, not just text messages
- Artifact types: file (PDF, image, CSV), structured data (JSON), code, report
- Artifacts attached to session events — viewable and downloadable in execution trace
- Example: "The research agent produces a report artifact → the editor agent receives it →
  the designer agent receives the final version and produces a presentation artifact"

#### Cross-Session Memory
- Optional: team can accumulate memory across sessions
- "Remember that this client prefers formal language" — persists across all future runs
- Memory management UI: view, edit, delete accumulated team memories
- Privacy control: team memory stays within the team, not shared with other teams

**Data model additions**:
- `agentic_team.default_context` (JSONB, nullable) — pre-filled context template
- `agentic_team_session.context` (JSONB) — accumulated context for this run
- `agentic_team_knowledge_source` table: team_id, source_type, source_config, created_at
- `agentic_team_session_artifact` table: session_id, event_id, artifact_type, storage_path,
  metadata
- `agentic_team_memory` table: team_id, content, created_at, source_session_id

---

### Phase 6: Templates & Marketplace

**What it is**: Pre-built team structures that users can import, customize, and share.

**Core value**: SMBs don't start from blank canvas. They pick an industry template and
customize it for their business in minutes.

**Capabilities**:

#### Built-in Templates
- Curated by the platform team
- Categories by industry:
  - **Customer Support**: Triage Agent → Specialist Agent → Quality Review → Human Escalation
  - **Content Marketing**: Research Agent → Writer Agent → Editor (Human) → SEO Agent → Publisher
  - **Sales Pipeline**: Lead Qualifier → Research Agent → Proposal Writer → Manager Approval (Human)
  - **IT Support**: Ticket Classifier → L1 Agent → L2 Agent → L3 Human Engineer
  - **Finance Operations**: Invoice Parser → Validator Agent → Approval (Human CFO) → Payment Processor
  - **HR Onboarding**: Document Collector → Background Check → Welcome Kit Generator → Manager Notification
- Each template includes: node structure, suggested connection prompts, recommended agent
  configurations, example team context

#### Import & Customize
- "Use this template" → creates a new team with the template structure
- User maps their own agents to template nodes
- Connection prompts are pre-filled but editable
- Nodes can be added, removed, or rearranged after import

#### Community Marketplace (Future)
- Users can publish their team structures (anonymized — no agent details, just structure + roles)
- Rating and review system
- "Most popular teams for [industry]"
- Revenue share model: premium templates from expert creators

#### Onboarding Wizard
- For new users: "What does your business do?" → industry selection
- "What workflow would you like to automate?" → suggested template
- "Which of your agents should fill these roles?" → agent assignment
- Result: fully configured team ready to run

**Data model additions**:
- `agentic_team_template` table: name, description, category, structure (JSONB — nodes + connections),
  is_public, creator_id, usage_count, rating
- `agentic_team.template_id` (FK, nullable) — tracks which template a team was created from

---

### Phase 7: Observability & Analytics

**What it is**: Comprehensive visibility into team performance, costs, and bottlenecks.

**Core value**: Business owners can answer: "Is my AI team working? How much does it cost?
Where are the bottlenecks?"

**Capabilities**:

#### Team Dashboard
- Per-team analytics page: `/agentic-teams/{id}/analytics`
- Key metrics:
  - Total runs (daily/weekly/monthly)
  - Success rate (% of runs completing without error)
  - Average completion time (total and per-node)
  - Cost per run (tokens + API calls + human time)
  - Most common failure points
- Time-series charts: performance trends over time
- Bottleneck identification: "Node X takes 3x longer than average — consider optimizing"

#### Cost Tracking
- Per-node cost breakdown: tokens consumed, API calls made, cost in USD
- Per-team monthly cost: aggregated across all runs
- Cost projection: "At current usage, this team will cost ~$X/month"
- Budget alerts: "This team has used 80% of its monthly budget"
- Cost comparison: "Team A costs 40% less than Team B for similar tasks"

#### Quality Metrics
- Human feedback on outputs: thumbs up/down on session results
- Error rate per node: which agents fail most often?
- Escalation frequency: how often do tasks reach human nodes?
- Revision cycles: how many feedback loops per session on average?
- SLA compliance: % of handovers completing within SLA

#### Alerting
- Configurable alerts: "Notify me if success rate drops below 70%"
- "Notify me if a session takes longer than 30 minutes"
- "Notify me if daily cost exceeds $50"
- Alert channels: email, Slack, in-app notification

**Data model additions**:
- Aggregate tables for efficient analytics queries (materialized views or pre-computed)
- `agentic_team_budget` table: team_id, monthly_limit_usd, alert_threshold_percent
- `agentic_team_alert_config` table: team_id, metric, condition, threshold, channel

---

### Phase 8: Multi-Tenancy & Collaboration

**What it is**: Multiple users in an organization can view, edit, and manage the same agentic
teams. Role-based access control ensures the right people have the right permissions.

**Core value**: AgenticTeams becomes an organizational tool, not just a personal one. Teams
reflect the actual company structure.

**Capabilities**:

#### Organization Layer
- New entity: `organization` — a group of users who share resources
- Users belong to organizations (many-to-many: a user can be in multiple orgs)
- Agentic teams can be owned by an organization instead of an individual
- Org-owned teams visible to all org members (based on role)

#### Role-Based Access Control
- Roles per team:
  - **Owner**: full control — CRUD nodes, connections, settings, delete team
  - **Editor**: modify nodes, connections, connection prompts — cannot delete team or change ownership
  - **Operator**: invoke team runs, view execution traces — cannot modify structure
  - **Viewer**: read-only access to chart and execution history
- Role assignment UI in team settings
- Invitation flow: invite by email → user joins org → gets team access

#### Team-of-Teams Composition
- A node in one team can reference another team (not just an agent)
- `node_type: "team"` with `referenced_team_id`
- When execution reaches a team node, it invokes the referenced team's lead node
- The referenced team runs as a sub-session, and its output becomes the node's output
- Enables hierarchical organization: "Customer Support Team" has an "Escalation Team" node
- Recursive depth limit to prevent infinite nesting

#### Shared Agent Pool
- Organizations have a shared agent pool — agents accessible to all org members
- Personal agents vs org agents distinction
- Org agents can be used in any team by any org member
- Agent permission: who can modify vs who can only use

**Data model additions**:
- `organization` table: name, plan, created_at
- `organization_member` table: org_id, user_id, role (admin/member)
- `agentic_team.organization_id` (FK, nullable) — null = personal team
- `agentic_team_member` table: team_id, user_id, role (owner/editor/operator/viewer)
- Extend `agentic_team_node`: `referenced_team_id` (FK, nullable) for team-of-teams

---

### Phase 9: Internationalization & Global Readiness

**What it is**: Full support for global SMB adoption — multilingual, multi-timezone,
multi-currency.

**Core value**: A team in Tokyo with agents that speak Japanese, a human reviewer in Berlin,
and a customer-facing agent in New York — all working together seamlessly.

**Capabilities**:

#### Multilingual Handovers
- Connection-level language configuration
- "Translate to [target language] before handover" — built-in transform
- Agent nodes configured with primary language — system auto-translates when languages differ
- Translation quality tracking — flag mistranslations for improvement

#### Timezone-Aware Execution
- Human nodes have timezone configuration
- "Business hours" defined per timezone
- SLA calculations respect business hours: "2 business hours" means 2 hours during working
  time in the human's timezone
- Team-level timezone for scheduling: "Run this team every Monday at 9 AM Tokyo time"

#### Locale-Adapted Templates
- Templates adapted per region:
  - Compliance requirements differ (GDPR in EU, CCPA in California, LGPD in Brazil)
  - Industry terminology differs
  - Currency in cost tracking matches user's locale
- Template marketplace filterable by region/language

#### RTL Support
- Chart UI supports right-to-left languages (Arabic, Hebrew)
- Node labels, connection prompts render correctly in RTL
- Auto-arrange respects reading direction

---

### Phase 10: Safety, Governance & Trust

**What it is**: Enterprise-grade safety controls that give SMB owners confidence to deploy
AI teams on real business processes.

**Core value**: "I trust my AI team because I can see what it does, control what it's allowed
to do, and prove compliance to auditors."

**Capabilities**:

#### Guardrails Per Connection
- Content rules on connections: "Never pass PII through this connection"
- Automatic PII detection and redaction before handover
- Sensitive data classification: financial data, health data, personal identifiers
- Custom rules: "Never include customer phone numbers in handovers to external agents"
- Rule violations logged in audit trail and flagged to owner

#### Budget Controls
- Hard budget limits per team: "This team cannot spend more than $100/month"
- Soft limits: warning at threshold, hard stop at limit
- Per-node limits: "This expensive agent cannot use more than $30/month"
- Budget rollover configuration: unused budget carries over or resets monthly

#### Audit Trail
- Immutable log of every action:
  - Team structure changes (who added/removed nodes, when)
  - Every execution session (full message history)
  - Every human approval/rejection (with timestamp and reason)
  - Configuration changes (connection prompts, settings)
- Export formats: JSON, CSV, PDF report
- Retention policy: configurable (default: 1 year)
- Compliance mapping: which audit entries satisfy which regulation (GDPR Article 30, SOC 2, etc.)

#### Human Override
- Any running team execution can be:
  - **Paused**: freeze execution, inspect current state
  - **Redirected**: manually change which node runs next
  - **Terminated**: stop execution with a manual output
  - **Replayed**: re-run from a specific node with modified input
- Override actions logged in audit trail
- Emergency stop: owner can halt all running sessions for a team instantly

#### Data Residency
- Storage location configuration: where session data and team configurations are stored
- Region selection: US, EU, APAC — for compliance with data residency regulations
- Cross-region teams: human nodes in different regions, data stays in configured region

---

## The "Alive" Team — The North Star

The ultimate vision is a team that doesn't just execute when invoked — it **lives**:

### Self-Optimizing
- The system analyzes execution history and suggests improvements:
  - "This connection's handover prompt fails 30% of the time. Suggested improvement: ..."
  - "Node X is a bottleneck — average wait time is 4 hours. Consider adding a parallel path."
  - "These two nodes always agree — consider merging them to save cost."
- A/B testing: "Try this alternative connection prompt for 50% of runs and measure impact"
- Auto-tuning: with owner approval, the system can automatically apply suggested improvements

### Auto-Scaling
- "Your support volume increased 3x this week — suggest adding a triage node before the
  specialist nodes"
- "This team is running 50 concurrent sessions — suggest splitting into two specialized teams"
- Dynamic node activation: enable/disable nodes based on load or time of day

### Learning from Execution
- Each team run improves the team's shared context
- "We've processed 500 invoices — here are the 12 edge cases we've learned to handle"
- Pattern recognition: "Customers who ask about pricing always follow up about contracts —
  pre-route to the contracts agent"
- Knowledge distillation: insights from human node responses feed back into agent prompts

### Proactive Teams
- Teams that don't wait for invocation — they watch for triggers:
  - Email trigger: "When a new email arrives in support@company.com, run the Support Team"
  - Webhook trigger: "When a new ticket is created in Jira, run the Triage Team"
  - Schedule trigger: "Every Monday at 9 AM, run the Weekly Report Team"
  - Event trigger: "When a customer's contract is 30 days from expiry, run the Renewal Team"
- Trigger configuration UI per team
- Trigger history: which triggers fired, what they produced

---

## Architecture Principles (Across All Phases)

### 1. Graph-First Data Model
Everything is a directed graph. Nodes and edges are the universal primitives. The execution
engine walks the graph. The UI renders the graph. Analytics query the graph. Keep this
abstraction clean — resist the temptation to add workflow-specific concepts that don't map to
nodes and edges.

### 2. Node Type Extensibility
`node_type` is the primary extensibility seam. Every new kind of participant (agent, human,
team, service, webhook) is a new node type. Node types share the same graph position, the same
connection model, the same execution interface. Type-specific behavior lives in the execution
engine, not in the data model.

### 3. Connection Config Evolution
Connections start simple (a text prompt) and evolve into rich routing rules. The migration
path: `connection_prompt` (TEXT) → `connection_config` (JSONB) with `handover_prompt` as one
field among many. Always keep backward compatibility — the simple case should stay simple.

### 4. Separation of Topology and Presentation
The graph topology (nodes, edges, types, prompts) is the domain model. Node positions (x, y)
are presentation metadata. The execution engine never reads positions. The UI never needs to
understand execution semantics. Keep these concerns separated in the data model and API.

### 5. Sessions as First-Class Citizens
Every team run produces a session. Sessions are the audit trail, the analytics source, the
debugging tool, and the learning corpus. Design sessions to be rich, queryable, and immutable.
Never mutate a completed session — append corrections as new events.

### 6. Progressive Disclosure
The MVP is a chart editor. Phase 2 adds "Run". Phase 3 adds human nodes. Each phase adds
capabilities without changing the core interaction model. A user who mastered the MVP should
find Phase 2 intuitive, not foreign. Resist the urge to redesign — extend.

---

## Competitive Landscape

| Category | Players | How AgenticTeams Differs |
|----------|---------|------------------------|
| Workflow builders | Zapier, Make, n8n | Those automate *tasks*. AgenticTeams orchestrates *workers* (agents + humans). The graph represents communication, not data flow. |
| Agent frameworks | LangGraph, CrewAI, AutoGen | Those are developer tools (code). AgenticTeams is a visual, no-code product for business users. |
| Org chart tools | Lucidchart, Miro | Those are static diagrams. AgenticTeams charts *execute*. |
| BPM tools | Camunda, ProcessMaker | Those model business processes. AgenticTeams models *teams* — the people and agents who execute processes. |
| AI agent platforms | Relevance AI, Lyzr | Those focus on individual agents. AgenticTeams focuses on *how agents work together*. |

**The unique position**: AgenticTeams is the only product that combines visual team design,
hybrid human-AI execution, and SMB-accessible simplicity. It's not a workflow tool, not an
agent builder, not an org chart — it's a **team orchestration platform**.

---

## Key Metrics by Phase

| Phase | North Star Metric | Supporting Metrics |
|-------|------------------|-------------------|
| 1. Blueprint | Teams created with 3+ nodes | Connection prompts filled, auto-arrange usage |
| 2. Execution | Weekly team runs per user | Success rate, avg completion time, sessions viewed |
| 3. Human-in-Loop | % teams with human nodes | Human response time, escalation rate |
| 4. Connection Intelligence | % connections with conditions | Routing accuracy, transform usage |
| 5. Shared Context | Context utilization per session | Knowledge base attachment rate |
| 6. Templates | Template-to-active-team conversion | Marketplace engagement, template ratings |
| 7. Observability | Dashboard daily active users | Alert configuration rate, cost awareness |
| 8. Multi-Tenancy | Org-owned teams | Collaboration rate, role diversity |
| 9. i18n | Non-English team configurations | Cross-timezone team executions |
| 10. Governance | Audit export frequency | Budget limit adoption, guardrail activation rate |

---

## Risk Register

| Risk | Impact | Mitigation |
|------|--------|------------|
| Users build teams but never run them (Phase 1 → 2 gap) | Feature becomes a diagram tool, not an orchestration platform | Ship execution MVP quickly; add "Try Run" with sample input in Blueprint phase |
| Human nodes create unpredictable latency | Teams feel slow, users abandon | Set clear SLA expectations in UI; show estimated completion time; async notification when done |
| Connection config complexity overwhelms SMB users | Adoption drops after Phase 4 | Progressive disclosure — simple prompt stays default; conditions/transforms are "advanced" options |
| Cost tracking scares users away | Users avoid running teams | Show cost *savings* vs doing it manually; offer free tier with generous limits |
| Template marketplace quality control | Bad templates damage trust | Curate initial templates in-house; community templates require review; rating system |
| Multi-tenancy security | Data leaks between org members | Strict RLS from day one; penetration testing before launch; SOC 2 compliance |
| Internationalization complexity | Poor experience for non-English users | Start with translation layer on connections (Phase 3); full i18n as dedicated phase |

---

*This document is a living product vision. It should be revisited quarterly and updated as
market conditions, user feedback, and technical capabilities evolve.*

*Last updated: 2026-04-01*
