# Workflow Runner Core

A conversational AI agent platform where users create custom AI agents, run them in isolated Docker environments, and interact through persistent chat sessions. Agents can be shared, scheduled, triggered by email/webhooks, and exposed via A2A and MCP protocols.

**Stack:** FastAPI + PostgreSQL | React + TypeScript + TanStack | Docker isolation | SQLModel ORM

---

## Glossary

| Term | Definition |
|------|-----------|
| **Agent** | User-defined AI assistant with custom prompts, credentials, and SDK configuration |
| **Agent Environment** | Runtime instance (Docker container or remote server) where an agent executes |
| **Session** | Persistent chat conversation between a user and an agent environment |
| **Message** | Single communication unit within a session (user or agent) |
| **Activity** | Logged event or summary of agent actions within a session |
| **Credential** | Encrypted API key or service account used by agents (e.g., Gmail, Odoo) |
| **AI Credential** | LLM provider API key (Claude, OpenAI, etc.) for agent runtime |
| **Knowledge Source** | Git-based repository of documentation agents can query via RAG |
| **Agent Plugin** | Marketplace capability that extends agent functionality |
| **Input Task** | User-submitted task that goes through refinement before agent execution |
| **Task Trigger** | Automated rule (CRON, webhook, date) that creates tasks for an agent |
| **Agent Share** | Clone-based sharing of an agent with another user, including credential requirements |
| **Guest Share** | Token-based limited access to an agent for unauthenticated users |
| **Handover** | Agent-to-agent task delegation within the platform |
| **Workspace** | Isolation boundary for user's agents, sessions, and resources |
| **AI Function** | LLM utility for text generation, classification, extraction with multi-provider cascade fallback |
| **Building Mode** | Agent environment state for configuration and development |
| **Conversation Mode** | Agent environment state for executing tasks and chat |
| **A2A** | Agent-to-Agent protocol for cross-platform agent communication |
| **MCP** | Model Context Protocol - exposes agents as tool servers to external LLM clients |
| **MCP Connector** | Configuration that connects an agent environment to an external MCP server |

---

## Domain Map

| Domain | Description | Features |
|--------|-------------|----------|
| [agents](#agents) | Core agent lifecycle - creation, configuration, environments, sessions, chat, file management | 14 features |
| [tasks](#tasks) | Task submission, refinement, triggers, and scheduling | 3 features |
| [credentials](#credentials) | Credential management, encryption, AI provider keys | 1 feature |
| [application](#application) | User-facing platform features - authentication, integrations, real-time events, workspaces | 11 features |
| [knowledge](#knowledge) | Git-based knowledge sources, vector search, RAG | 1 feature |
| [sharing](#sharing) | Agent sharing, guest access, workspace collaboration | 3 features |
| [development](#development) | Backend/frontend patterns, AI functions, debugging | 4 features |

---

## Feature Registry

### agents

| Feature | Description | Docs |
|---------|-------------|------|
| agent_sessions | Core agent-session-environment lifecycle, business rules, modes | [business logic](agents/agent_sessions/agent_sessions.md) |
| agent_environments | Docker container architecture, build layers, workspace isolation | [business logic](agents/agent_environments/agent_environments.md) \| [tech](agents/agent_environments/agent_environments_tech.md) |
| agent_prompts | System prompt construction for building and conversation modes | [business logic](agents/agent_prompts/agent_prompts.md) \| [tech](agents/agent_prompts/agent_prompts_tech.md) |
| agent_commands | Slash commands executed within agent sessions (`/files`, etc.) | [business logic](agents/agent_commands/agent_commands.md) |
| session_recovery | Recovery from lost SDK connections after container rebuilds | [business logic](agents/session_recovery/session_recovery.md) |
| agent_activities | Activity feed, event logging, session summaries | [business logic](agents/agent_activities/agent_activities.md) \| [tech](agents/agent_activities/agent_activities_tech.md) |
| agent_plugins | Plugin marketplace integration, capability loading | [business logic](agents/agent_plugins/agent_plugins.md) |
| agent_schedulers | Multi-schedule CRON execution with natural language input and per-schedule prompts | [business logic](agents/agent_schedulers/agent_schedulers.md) \| [tech](agents/agent_schedulers/agent_schedulers_tech.md) |
| agent_handover | Agent-to-agent task delegation and inbox creation | [business logic](agents/agent_handover/agent_handover.md) |
| multi_sdk | Multiple AI provider support (Claude, OpenAI, MiniMax) | [business logic](agents/multi_sdk/multi_sdk.md) |
| agent_environment_core | Server-side core running inside Docker containers: HTTP API, SDK adapters, prompt generation | [business logic](agents/agent_environment_core/agent_environment_core.md) \| [tech](agents/agent_environment_core/agent_environment_core_tech.md) \| [knowledge tool](agents/agent_environment_core/knowledge_tool.md) |
| agent_environment_data_management | Environment data flow, cloning, syncing operations | [business logic](agents/agent_environment_data_management/agent_environment_data_management.md) \| [tech](agents/agent_environment_data_management/agent_environment_data_management_tech.md) |
| agent_credentials | Credential syncing to agent environments, whitelisting, redaction, OAuth refresh | [business logic](agents/agent_credentials/agent_credentials.md) \| [tech](agents/agent_credentials/agent_credentials_tech.md) \| [oauth](agents/agent_credentials/oauth_credentials.md) \| [whitelist](agents/agent_credentials/credentials_whitelist.md) \| [google SA](agents/agent_credentials/google_service_account.md) \| [sharing](agents/agent_credentials/credential_sharing.md) |
| agent_file_management | File upload/download, workspace file viewing, storage quota, garbage collection | [business logic](agents/agent_file_management/agent_file_management.md) \| [tech](agents/agent_file_management/agent_file_management_tech.md) \| [remote db viewer](agents/agent_file_management/remote_database_viewer.md) |

### tasks

| Feature | Description | Docs |
|---------|-------------|------|
| input_tasks | Task submission, vague request refinement, execution workflow | [business logic](tasks/input_tasks/input_tasks.md) |
| task_triggers | Automated triggers - CRON schedules, webhooks, date-based | [business logic](tasks/task_triggers/task_triggers.md) |
| tools_approval | Agent tool execution approval management | [business logic](tasks/tools_approval/tools_approval.md) |

### credentials

| Feature | Description | Docs |
|---------|-------------|------|
| ai_credentials | LLM provider API keys, named credentials, default selection, environment linking, sharing | [business logic](application/ai_credentials/ai_credentials.md) \| [tech](application/ai_credentials/ai_credentials_tech.md) \| [anthropic types](application/ai_credentials/anthropic_credential_types.md) \| [affected envs](application/ai_credentials/affected_environments_widget.md) |

### application

| Feature | Description | Docs |
|---------|-------------|------|
| auth | User authentication - JWT tokens, password login, Google OAuth, domain whitelist, password recovery | [business logic](application/auth/auth.md) \| [tech](application/auth/auth_tech.md) \| [google oauth](application/auth/google_oauth.md) |
| ssh_keys | User SSH key management for private Git repository access | [business logic](application/ssh_keys/ssh_keys.md) \| [tech](application/ssh_keys/ssh_keys_tech.md) |
| knowledge_sources | Git-based knowledge sources with article indexing, embeddings, and semantic search | [business logic](application/knowledge_sources/knowledge_sources.md) \| [tech](application/knowledge_sources/knowledge_sources_tech.md) |
| user_workspaces | Workspace isolation for organizing agents, credentials, sessions by context | [business logic](application/user_workspaces/user_workspaces.md) \| [tech](application/user_workspaces/user_workspaces_tech.md) |
| email_integration | Email-to-agent automation overview, access control, security model | [business logic](application/email_integration/email_integration.md) \| [tech](application/email_integration/email_integration_tech.md) |
| mail_servers | IMAP/SMTP server configuration, credential encryption, connection testing | [business logic](application/email_integration/mail_servers.md) \| [tech](application/email_integration/mail_servers_tech.md) |
| email_sessions | Session modes, processing modes, email threading, outgoing queue, session context | [business logic](application/email_integration/email_sessions.md) \| [tech](application/email_integration/email_sessions_tech.md) |
| a2a_protocol | Agent-to-Agent protocol, JSON-RPC, task-based integration | [business logic](application/a2a_integration/a2a_protocol/a2a_protocol.md) \| [tech](application/a2a_integration/a2a_protocol/a2a_protocol_tech.md) \| [v1 support](application/a2a_integration/a2a_protocol/a2a_v1_support.md) |
| a2a_access_tokens | Scoped JWT tokens for external A2A client authentication | [business logic](application/a2a_integration/a2a_access_tokens/a2a_access_tokens.md) \| [tech](application/a2a_integration/a2a_access_tokens/a2a_access_tokens_tech.md) |
| mcp_integration | Agent exposure as MCP server, OAuth 2.1, connector setup | [architecture](application/mcp_integration/agent_mcp_architecture.md) \| [implementation](application/mcp_integration/agent_mcp_connector.md) \| [setup](application/mcp_integration/mcp_connector_setup.md) |
| realtime_events | WebSocket event bus system, frontend-backend-agentenv streaming | [event bus](application/realtime_events/event_bus_system.md) \| [streaming](application/realtime_events/frontend_backend_agentenv_streaming.md) |

### knowledge

| Feature | Description | Docs |
|---------|-------------|------|
| knowledge_management | Git-based knowledge sources, article indexing, vector search | [business logic](knowledge/knowledge_management/knowledge_management.md) |

### sharing

| Feature | Description | Docs |
|---------|-------------|------|
| agent_sharing | Clone-based agent sharing, credential requirements, push updates, guest access | [business logic](agents/agent_sharing/agent_sharing.md) \| [tech](agents/agent_sharing/agent_sharing_tech.md) \| [guest sharing](agents/agent_sharing/guest_sharing.md) \| [guest tech](agents/agent_sharing/guest_sharing_tech.md) |
| workspaces | Workspace isolation, entity separation, multi-workspace support | [business logic](application/user_workspaces/user_workspaces.md) |

### development

| Feature | Description | Docs |
|---------|-------------|------|
| backend_patterns | SQLModel patterns, routes, services, CRUD, migrations | [reference](development/backend_patterns/backend_patterns.md) |
| frontend_patterns | Component patterns, hooks, TanStack conventions | [reference](development/frontend_patterns/frontend_patterns.md) |
| ai_functions | LLM utility development, multi-provider cascade fallback | [reference](development/ai_functions/ai_functions.md) |
| security | Credentials whitelist, encryption at rest, access control | [reference](development/security/security.md) |

---

## Architecture Overview

```
User ──→ Frontend (React) ──→ Backend API (FastAPI) ──→ Services ──→ PostgreSQL
                                      │
                                      ├──→ Docker Environments ──→ Agent SDK (Claude/OpenAI)
                                      ├──→ WebSocket (Socket.IO) ──→ Real-time Events
                                      ├──→ A2A Protocol ──→ External Agents
                                      ├──→ MCP Server ──→ External LLM Clients
                                      └──→ Email (IMAP/SMTP) ──→ Email Automation
```

---

*Last updated: 2026-03-02*
