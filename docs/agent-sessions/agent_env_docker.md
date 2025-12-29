# Docker Agent Environments - Build Architecture

## Overview

Agent environments run in isolated Docker containers with a dual-layer architecture: **core** (system files) and **workspace** (user files). This separation enables updating system code without losing user data.

## Core Concepts

### Two-Layer Architecture

**Core Layer** (`/app/core/`)
- System code (FastAPI server, SDK manager, API routes)
- Baked into Docker image during build
- Updated via rebuild operation
- Immutable at runtime

**Workspace Layer** (`/app/workspace/`)
- User-generated content (scripts, files, docs, credentials, databases, logs)
- Integration knowledge base (updated during rebuilds, user files preserved)
- Mounted as Docker volume
- Persists across rebuilds and restarts
- Writable by agent at runtime

**Template Files** (`/app/`)
- Static configuration files (BUILDING_AGENT_EXAMPLE.md, AGENT_EXAMPLE.md, etc.)
- Copied to instance during initialization
- Not updated during rebuilds

### Why This Separation?

**Problem**: Updating system code (bug fixes, new features) required destroying and recreating environments, losing all user work.

**Solution**: Separate system code (core) from user data (workspace). System updates only affect core layer; workspace remains untouched.

## File Structure

### Template Directory
```
backend/app/env-templates/python-env-advanced/
├── app/
│   ├── core/                          # System code (baked into image)
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI entry point
│   │   └── server/                    # API server code (modular architecture)
│   │       ├── routes.py              # HTTP endpoints
│   │       ├── models.py              # Pydantic request/response models
│   │       ├── sdk_manager.py         # SDK session orchestration
│   │       ├── prompt_generator.py    # System prompt generation
│   │       ├── agent_env_service.py   # Business logic (file operations)
│   │       └── sdk_utils.py           # Logging, debugging, formatting
│   │
│   ├── workspace/                     # User data (volume mounted)
│   │   ├── scripts/                   # Agent-created Python scripts
│   │   │   └── README.md              # Scripts catalog (maintained by agent)
│   │   ├── files/                     # Uploaded/generated files
│   │   ├── docs/                      # Workflow documentation
│   │   │   ├── WORKFLOW_PROMPT.md     # Conversation mode system prompt
│   │   │   └── ENTRYPOINT_PROMPT.md   # Trigger message examples
│   │   ├── credentials/               # API keys, tokens (encrypted)
│   │   ├── databases/                 # SQLite/other local DBs
│   │   ├── knowledge/                 # Integration knowledge base
│   │   │   ├── odoo-erp/              # Example: Odoo integration docs
│   │   │   │   ├── general_info.md    # API guides, best practices
│   │   │   │   └── vendor_bills.md    # Data schemas, field definitions
│   │   │   └── [other-topics]/        # Additional integration topics
│   │   ├── logs/                      # Execution logs, session dumps
│   │   └── workspace_requirements.txt # Agent-installed Python packages (persists across rebuilds)
│   │
│   ├── BUILDING_AGENT_EXAMPLE.md      # Template for building mode prompt
│   └── ENTRYPOINT_EXAMPLE.md          # Template for trigger message (deprecated)
│
├── Dockerfile                         # Image definition
├── docker-compose.template.yml        # Container configuration template
└── pyproject.toml                     # Python dependencies
```

### Instance Directory
```
backend/data/environments/{env_id}/
├── app/
│   ├── core/                          # Copied from template, baked into image
│   ├── workspace/                     # User data, volume mounted
│   ├── BUILDING_AGENT.md              # Instance-specific (from template)
│   └── .env                           # Environment variables
├── docker-compose.yml                 # Generated from template
└── .env                               # Docker compose variables
```

## Core Server Architecture

### Modular Design (Refactored)

The core server follows a **modular architecture** with clear separation of concerns:

**modules**:
- **routes.py**: HTTP API endpoints, request validation, response formatting
- **sdk_manager.py**: SDK session orchestration, streaming coordination (~ 220 lines, down from 600)
- **prompt_generator.py**: System prompt generation for building/conversation modes
- **agent_env_service.py**: Business logic for workspace file operations
- **sdk_utils.py**: Logging, debugging, message formatting utilities
- **models.py**: Pydantic request/response models

**Benefits**:
- **Testability**: Each module can be tested independently
- **Maintainability**: Changes isolated to relevant modules
- **Extensibility**: Easy to add new SDKs or prompt strategies
- **Clarity**: Clear module boundaries and responsibilities

**Key Changes from Previous Architecture**:
- Prompt loading extracted to `PromptGenerator` (was in `sdk_manager.py`)
- Business logic moved to `AgentEnvService` (was in `routes.py`)
- Debugging utilities extracted to `sdk_utils.py` (was in `sdk_manager.py`)
- SDK manager now focused on orchestration only

### Session Modes

**Building Mode**:
- **Model**: Claude Sonnet (default) - better code generation
- **System Prompt**: Claude Code preset + comprehensive docs
- **Purpose**: Develop workflows, create scripts, configure integrations

**Conversation Mode**:
- **Model**: Claude Haiku - faster and cheaper
- **System Prompt**: Workflow-specific instructions (no preset)
- **Purpose**: Execute tasks using pre-built workflows

**SDK Support**:
- Current: `agent_sdk="claude"` (Claude SDK via ClaudeAgentOptions)
- Future: Can add OpenAI, Google, etc.

### Integration Knowledge Base

**Purpose**: Provide agents with integration-specific documentation without bloating system prompts

**Location**: `/app/workspace/knowledge/` (workspace, persists across rebuilds)

**Organization**:
- Topic-based subdirectories (e.g., `odoo-erp/`, `salesforce/`, `stripe/`)
- Markdown files containing API guides, data schemas, best practices
- Minimal footprint: Only topic folder names included in prompts

**Prompt Integration**:
- `PromptGenerator._get_knowledge_topics()` scans for topic folders
- Returns comma-separated list (e.g., "odoo-erp, salesforce, stripe")
- Added to both building and conversation mode prompts
- Agent reads specific files on-demand when needed

**Rebuild Behavior**:
- Template knowledge files are synced to environment (add/update only)
- User-created knowledge files are preserved
- No deletions during rebuild
- Enables distributing new integration docs to all environments

**Example**:
```
workspace/knowledge/
├── odoo-erp/
│   ├── general_info.md      # Connection methods, architecture
│   ├── vendor_bills.md       # Field schemas, workflows
│   └── sales_orders.md       # Operations, best practices
└── custom-integration/       # User-created, won't be deleted
    └── api_notes.md
```

### Python Dependencies

**Two-Layer System**: Template dependencies (system-level) + Workspace dependencies (integration-specific)

**Template Dependencies** (`pyproject.toml`):
- Pre-installed packages: `fastapi`, `uvicorn`, `pydantic`, `httpx`, `requests`, `claude-agent-sdk`
- Baked into Docker image during build
- Updated via environment rebuild

**Workspace Dependencies** (`workspace/workspace_requirements.txt`):
- Integration-specific packages: `odoo-rpc-client`, `salesforce-api`, `stripe`, etc.
- Installed by agent using `uv pip install <package>`
- Added to `workspace_requirements.txt` for persistence
- Auto-installed on container startup (after health check)
- **Persists across rebuilds**

**Installation Flow**:
1. Agent runs: `uv pip install <package>` (immediate use)
2. Agent adds to: `workspace_requirements.txt` (persistence)
3. On next start/rebuild: Auto-installed via `DockerEnvironmentAdapter.install_custom_packages()`

**Implementation**: `backend/app/services/adapters/docker_adapter.py::install_custom_packages()`

## Operations

### Environment Creation

**Entry Point**: `backend/app/services/environment_lifecycle.py::create_environment_instance()`

**Process**:
1. Copy entire template → instance directory
2. Create `BUILDING_AGENT.md` from `BUILDING_AGENT_EXAMPLE.md`
3. Generate `docker-compose.yml` (replace variables: `ENV_ID`, `AGENT_ID`, `HOST_INSTANCE_DIR`)
4. Generate `.env` files (ports, auth tokens, resource limits)
5. Build Docker image via `DockerEnvironmentAdapter.initialize()`
   - Copies `app/core` into image (Dockerfile line 50)
   - Installs Python dependencies
   - Sets CMD to run `core/main.py`

**Result**: Stopped environment ready to start

### Environment Start

**Entry Point**: `backend/app/services/environment_lifecycle.py::start_environment()`

**Process**:
1. Run `docker-compose up -d`
2. Mount volumes:
   - `{instance_dir}/app/core:/app/core` (read-only in practice)
   - `{instance_dir}/app/workspace:/app/workspace` (read-write)
3. Wait for health check at `/health` endpoint
4. **Install workspace dependencies** from `workspace_requirements.txt` (if exists)
5. Sync prompts to `workspace/docs/` via `DockerEnvironmentAdapter.set_agent_prompts()`
6. Update database status to `running`

**Note**: Core files are both baked into image AND volume-mounted for easier development. Production could use image-only.

### Environment Rebuild

**Entry Point**: `backend/app/services/environment_lifecycle.py::rebuild_environment()`

**Purpose**: Update core system files and knowledge base from template while preserving workspace data

**Process**:
1. Check if environment is running → stop if needed
2. Delete old core directory: `{instance_dir}/app/core`
3. Copy fresh core from template: `{template_dir}/app/core` → `{instance_dir}/app/core`
4. Update knowledge files from template: `{template_dir}/app/workspace/knowledge` → `{instance_dir}/app/workspace/knowledge`
   - **Add/Update only**: New and updated knowledge files from template are copied
   - **Preserve user files**: User-created knowledge files not in template are kept
   - **No deletions**: Existing knowledge files are never deleted
5. Rebuild Docker image via `DockerEnvironmentAdapter.rebuild()`
   - Runs `docker-compose build` (uses cache for speed)
   - New core files baked into image
6. Restart container if it was running before
7. Update status to `running` or `stopped`

**Preserved**:
- All workspace data (scripts, files, docs, credentials, databases, logs)
- User-created knowledge files (not in template)
- **Workspace dependencies** (`workspace_requirements.txt`)
- Docker volumes
- Environment configuration
- Agent prompts

**Updated**:
- Core server code (modular architecture)
- API routes and request handling
- SDK manager orchestration
- Prompt generation logic
- Business logic services
- Utility functions
- Docker image layers
- **Template dependencies** (pyproject.toml packages)
- Knowledge base files from template (add/update only, no deletions)

## Docker Configuration

### Dockerfile

**Location**: `backend/app/env-templates/python-env-advanced/Dockerfile`

**Key Steps**:
- Install system dependencies (curl, git, Node.js for Claude Code)
- Install uv package manager
- Install Claude Code CLI globally
- Copy `pyproject.toml` and install **template dependencies** (system-level packages)
- **Copy `app/core` into image** (line 50)
- Set CMD to run `fastapi run core/main.py`

**Note**: Workspace dependencies (`workspace_requirements.txt`) are installed after container startup, not during image build.

**Environment Variables**:
- `PYTHONPATH=/app` (enables `import core.server.routes`)
- `CLAUDE_CODE_WORKSPACE=/app/workspace` (agent works in workspace)

### docker-compose.template.yml

**Location**: `backend/app/env-templates/python-env-advanced/docker-compose.template.yml`

**Volume Mounts**:
- `${HOST_INSTANCE_DIR}/app/core:/app/core` - Core files (system code)
- `${HOST_INSTANCE_DIR}/app/workspace:/app/workspace` - Workspace files (user data)

**Networks**:
- `agent-bridge` (shared with backend for HTTP communication)
- `agent-env-${ENV_ID}` (isolated network for this environment)

**Variables** (substituted during creation):
- `${ENV_ID}`, `${AGENT_ID}`, `${ENV_VERSION}`, `${AGENT_PORT}`, `${AGENT_AUTH_TOKEN}`

## API Endpoints

**Rebuild**: `POST /api/v1/environments/{id}/rebuild`
- Route: `backend/app/api/routes/environments.py::rebuild_environment()`
- Service: `backend/app/services/environment_service.py::rebuild_environment()`
- Lifecycle: `backend/app/services/environment_lifecycle.py::rebuild_environment()`
- Adapter: `backend/app/services/adapters/docker_adapter.py::rebuild()`

## Database Schema

**Status Values**: `stopped`, `creating`, `building`, `initializing`, `starting`, `running`, `rebuilding`, `error`, `deprecated`

**Model**: `backend/app/models/environment.py::AgentEnvironment`

**Rebuild Status Flow**:
1. `running` or `stopped` → trigger rebuild
2. `rebuilding` → during rebuild operation
3. `running` (if was running) or `stopped` (if was stopped) → after rebuild

## Implementation References

**Environment Lifecycle Manager**:
- `backend/app/services/environment_lifecycle.py`
- Methods: `create_environment_instance()`, `start_environment()`, `stop_environment()`, `rebuild_environment()`

**Docker Adapter**:
- `backend/app/services/adapters/docker_adapter.py`
- Methods: `initialize()`, `start()`, `stop()`, `rebuild()`

**Base Adapter Interface**:
- `backend/app/services/adapters/base.py::EnvironmentAdapter.rebuild()`

**Frontend**:
- Component: `frontend/src/components/Environments/EnvironmentCard.tsx`
- Action: Rebuild button with confirmation dialog

## Benefits

1. **Zero Data Loss**: Workspace preserved across system updates
2. **Fast Updates**: Rebuild only updates core, uses Docker cache
3. **Version Control**: Core code tracks template version
4. **Isolation**: Each environment has independent workspace
5. **Flexibility**: Can rebuild multiple times without risk
6. **Development**: Core updates tested without recreating environments
7. **Knowledge Distribution**: Integration knowledge base updates distributed to all environments via rebuild, while preserving user customizations
8. **Dependency Management**: Two-layer system allows template dependency updates via rebuild while preserving agent-installed workspace dependencies
