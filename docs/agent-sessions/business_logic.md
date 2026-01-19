# Agent Sessions - Business Logic & Context

## What We're Building

A **conversational AI agent platform** where users create custom AI agents with specific capabilities, run them in isolated environments (Docker containers), and interact through persistent chat sessions.

### Core Concepts

1. **Agent** (Logical Definition) - User-defined AI assistant with custom prompts, credentials, and configuration
2. **Environment** (Runtime Instance) - Docker container or remote server where the agent actually runs
3. **Session** (Conversation) - Chat thread between user and agent with independent message history
4. **Message** - Individual communication unit within a session

### Architecture Pattern

```
User → Session → Environment → Docker Container → Google ADK Agent
```

- **Agents** are logical definitions (what the agent does)
- **Environments** are runtime instances (where/how it runs)
- **Sessions** are conversations (user interactions)
- One agent can have multiple environments (testing, production, rollback)
- One environment can host multiple sessions (shared file system, separate histories)

## User Stories

### Agent Management
- **As a user**, I want to create an agent with custom prompts and credentials
- **As a user**, I want to update my agent's configuration at any time
- **As a user**, I want to manage multiple environments for my agent (testing, production)

### Environment Management
- **As a user**, I want to start/stop agent environments
- **As a user**, I want to switch between environments (blue-green deployment)
- **As a user**, I want one environment to be "active" for creating new sessions

### Session Interaction
- **As a user**, I want to create a new conversation session with my agent
- **As a user**, I want to send messages and receive real-time responses
- **As a user**, I want to have multiple parallel sessions with the same agent

### Security & Isolation
- **As a user**, I want my agent's credentials to be encrypted and secure
- **As a user**, I want my sessions to be private (only I can access them)
- **As a user**, I want each agent to run in an isolated environment

## Functional Requirements

### Agent CRUD
- Create agent with name, description, prompts
- Link/unlink credentials to agents
- Update agent configuration (affects future environment initializations)
- Set active environment for agent
- Delete agent (cascades to environments and sessions)

### Environment Lifecycle
- Create environment for agent (specify type: docker, remote_ssh, remote_http)
- Start environment → creates Docker container, initializes agent with prompts/credentials
- Stop environment → gracefully shuts down container
- Health check → verify environment is responsive
- Activate environment → set as agent's active environment for new sessions
- Status tracking: (`stopped`, `starting`, `running`, `error`, etc)

### Session Management
- Create session → uses agent's active environment, defaults to "conversation" mode
- Switch session mode → toggle between "building" and "conversation"
- Update session metadata (title, status)
- List sessions (by user, by agent, by environment)
- Delete session

### Message Flow
- Send message to session
- Backend validates session ownership and environment status
- **If environment is suspended or stopped**: System automatically starts the environment, marks session as `pending_stream`, and processes messages once environment is running
- Route message to environment's agent (via Docker HTTP API or SSH/HTTP adapter)
- Agent processes message using Google ADK
- Store user message and agent response in database
- Return response to user
- Messages have sequence numbers for ordering

### Session Modes

**Building Mode:**
- Agent receives comprehensive development context (code examples, API docs)
- Agent can create/modify files, configure integrations, write scripts
- Used for: initial setup, adding capabilities, maintenance
- Larger context window, slower responses

**Conversation Mode:**
- Agent receives task-focused context (available tools, workspace structure)
- Agent executes pre-built workflows and scripts
- Used for: daily operations, quick tasks
- Smaller context window, faster responses, lower cost

### Authorization Rules
- Users can only access their own resources (agents, sessions, credentials), unless these resources were explicitly shared
- Sessions must belong to user's agent environment

### Data Integrity
- Cascade delete: Agent → Environments → Sessions → Messages
- Foreign key constraints enforced
- Unique constraints on message sequence per session
- One active environment per agent (enforced in business logic)

## Business Rules

1. **Agent can have multiple environments** (for versioning, testing, blue-green deployment)
2. **Only one environment can be active** at a time per agent
3. **Sessions are created against specific environment**, not agent directly
4. **Environment must be running** to create new sessions; messages to suspended/stopped environments trigger automatic environment start
5. **Messages are immutable** once created (stored for audit trail)
6. **Credentials are defined at agent level**, inherited by all environments

## Key Differentiators

1. **Environment Abstraction**: Supports Docker, SSH, HTTP (extensible to Kubernetes, cloud functions)
2. **Blue-Green Deployments**: Switch between environments instantly for rollback
3. **Session Modes**: Optimize context window and cost based on task type
4. **Shared File System**: Multiple sessions share agent's workspace (files persist across sessions)
5. **Credential Security**: Encrypted at rest, mounted during environment initialization only

## Technical Context

- **Backend**: FastAPI (Python) with PostgreSQL
- **Frontend**: React + TypeScript
- **Agent Runtime**: Google Agent Development Kit (ADK) in Python and ClaudeCode
- **Isolation**: Docker containers with mounted volumes
- **Communication**: HTTP API between backend and agent containers
- **Database**: PostgreSQL with UUID primary keys, JSON columns for flexible metadata

## Implementation Philosophy

- **Service Layer Pattern**: Business logic in service classes, not routes or models
- **Domain-Driven Structure**: Models, services, and routes grouped by domain (agents, environments, sessions, etc.)
- **Authorization at Route Level**: Validate ownership before delegating to services
- **Stub First, Implement Later**: Create data layer and API contracts before implementing Docker/agent logic
