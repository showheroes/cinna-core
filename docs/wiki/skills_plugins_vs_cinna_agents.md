# Why Cinna Agents? Skills & Plugins vs. Cinna Agents

Traditional LLM platforms offer **skills** and **plugins** — lightweight function calls that extend what a chatbot can do in a single turn. Cinna takes a fundamentally different approach: instead of bolting capabilities onto a chat interface, it gives each agent a **persistent, isolated runtime** with its own credentials, files, schedules, and integrations.

This article compares the two approaches across dimensions that matter most to SMB companies looking for practical, scalable AI automation.

---

## The Core Difference

| | Skills / Plugins | Cinna Agents |
|---|---|---|
| **Mental model** | Tool attached to a chatbot | Autonomous worker with its own desk, files, and access |
| **Lifecycle** | Exists only during the chat turn that calls it | Runs persistently — even when nobody is chatting |
| **Who drives** | The user must prompt every action | The agent can act on schedules, emails, webhooks, or other agents |

---

## Point-by-Point Comparison

| Capability | Skills / Plugins | Cinna Agents |
|---|---|---|
| **Credential management** | API keys configured per plugin or via platform-level OAuth connections. No per-plugin access control — a plugin either has the key or it doesn't. No sharing between users, no audit trail, no automatic propagation when a key rotates. | Encrypted vault with per-agent whitelisting — each agent sees only the credentials it needs. OAuth auto-refresh, credential sharing between team members, redaction in logs, and automatic rebuild propagation when a key changes. |
| **Runtime environment** | Ephemeral sandbox (if any). Code runs inside the LLM vendor's infrastructure with no user control over dependencies, packages, or OS-level tools. | Dedicated Docker container per agent. Full control over installed packages, scripts, and system tools. Multiple image templates available. |
| **Persistence** | Stateless. Every invocation starts from scratch — no memory of previous runs, no saved files, no local database. | Persistent workspace. Files, databases, scripts, and generated artifacts survive across sessions. Blue-green deployment for safe rollbacks. |
| **Multi-step workflows** | Modern LLMs can chain multiple tool calls, but the user must be in an active chat session driving the interaction. There is no way for a plugin workflow to run unattended or resume after the session closes. | Agents run autonomous multi-step workflows independently of any chat session. Building mode for developing scripts, conversation mode for execution. Workflows survive disconnects and can be triggered externally. |
| **Scheduling & triggers** | Not supported. Requires external CRON services, Zapier, or custom infrastructure to trigger any automated action. | Built-in CRON schedules (natural language input), email triggers, webhook triggers, date-based triggers — all configured in the UI, no external tooling. |
| **Email automation** | Not available. Connecting email requires building a custom integration pipeline outside the LLM platform. | Native IMAP/SMTP integration. Agents receive, process, and reply to emails autonomously. Configurable per-agent with mail server management in Settings. |
| **Security & isolation** | Plugins share the LLM's security boundary. No isolation between plugins, no control over what data a plugin can access. | Each agent runs in an isolated Docker environment. Credential whitelisting controls exactly which secrets an agent can see. Security event logging for audit. |
| **Custom knowledge** | Requires setting up a separate RAG pipeline (vector database, ingestion, retrieval service) or embedding knowledge directly into plugin prompts. No built-in versioning or sync — knowledge drifts as source material changes. | Git-based knowledge sources with article indexing and vector search (RAG) built into the platform. Knowledge auto-syncs with your repositories. Public and private sources, available to agents without any external infrastructure. |
| **Sharing & collaboration** | Plugins are personal. Sharing a workflow means exporting prompts and hoping the other person has the same plugins installed. | Clone-based agent sharing with credential requirement mapping. Guest access via shareable tokens. Push updates to shared agents. Team workspaces for organization. |
| **Team coordination** | No native concept. Multi-agent workflows require custom code and external orchestration. | Agentic teams with visual org-chart builder. Directed handover topology, auto-generated handover prompts, team-scoped task routing with short-code IDs. |
| **Integration protocols** | Plugins consume tools — they call external APIs. But an agent built as a plugin cannot itself be called by other systems. Interoperability depends on the host platform's support. | Bidirectional by design. Agents consume external tools via MCP connectors and are themselves exposed as A2A and MCP servers — any external system or LLM client can call them over standard protocols. |
| **Webhooks & external APIs** | Must be coded into each plugin separately. No unified webhook infrastructure. | Built-in webhook triggers and A2A endpoints. Any external system can push tasks to agents via standard HTTP. |
| **Data dashboards** | Not possible. Plugins cannot serve UI. Visualizing results means copying data to another tool. | Agent Webapp feature. Agents build and serve lightweight HTML/CSS/JS dashboards directly from their workspace. Shareable via public URLs with optional chat widgets. |
| **Monitoring & observability** | Chat history only. No activity logs, no event streams, no operational visibility. | Activity feeds, session summaries, real-time WebSocket events, security event logging, and customizable user dashboards with per-agent monitoring blocks. |
| **Task management** | Some tools offer basic task tracking (e.g., Claude Code tasks, Cursor tasks), but it is vendor-locked to that specific tool, limited in flexibility, and disconnected from other systems. No cross-agent delegation or automated triggers. | Structured input tasks with AI refinement, status tracking, comments, attachments, short-code IDs, subtask delegation across agents, status history, and automated triggers (CRON, webhook, date). Tool-agnostic and integrated into the full agent lifecycle. |
| **File management** | Upload/download within chat context. No persistent workspace, no quota management. | Full file workspace per agent. Upload, download, browse, edit. Storage quota enforcement and garbage collection. Remote database viewer for SQLite files. |
| **Development workflow** | Write plugin code externally, deploy, test in chat. No in-platform development tooling. | Building mode with larger context window for developing scripts and configuring integrations in-place. CLI integration for local development with AI coding tools. |

---

## What This Means for SMBs

### The plugin approach works when...

- You need a quick, one-off chatbot enhancement (e.g., "look up weather," "translate this text")
- The task is stateless and self-contained within a single prompt-response cycle
- A human is always present to drive the conversation and review each step

### Cinna agents are the better fit when...

- **Your workflows span hours or days** — An agent processing incoming support emails, updating a CRM, and generating weekly reports cannot be a plugin. It needs persistence, scheduling, and credentials that outlive a chat session.

- **You need real automation, not assisted chat** — Plugins require a human in the loop for every step. Cinna agents can receive an email, run a script, update a dashboard, and notify a team member — all without anyone opening a chat window.

- **You manage sensitive credentials** — SMBs juggle API keys for accounting software, CRMs, cloud services, and email. Cinna's encrypted vault with per-agent whitelisting is a security and operational step up from pasting keys into plugin configurations.

- **Your team needs to collaborate on AI workflows** — Sharing a plugin means sharing a prompt. Sharing a Cinna agent means sharing a fully configured worker — with its credentials mapped, knowledge loaded, and integrations wired.

- **You need agents that talk to each other** — A sales agent that hands qualified leads to an onboarding agent, which triggers a billing agent — this kind of coordination requires structured handover, not plugin chains.

---

## Summary

Plugins extend a chatbot. Cinna agents replace manual workflows.

For SMBs moving beyond "ask the AI a question" toward "let the AI handle it," Cinna provides the runtime, persistence, security, and coordination that plugins were never designed to offer — without requiring a platform engineering team to glue it all together.
