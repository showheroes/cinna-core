# Building Mode System Prompt

## Overview

When an agent environment runs in **building mode**, it uses a specialized system prompt that instructs the agent to create reusable Python scripts and applications for workflow automation. This prompt combines Claude Code's preset system prompt with custom instructions specific to script development.

## Prompt Architecture

The building mode system prompt is composed of three layers:

1. **Claude Code Preset** (`preset: "claude_code"`)
   - Official Claude Code system prompt with all standard tools and capabilities
   - Provides base functionality for file operations, code editing, and bash commands

2. **BUILDING_AGENT.md** (Static Template)
   - Custom instructions for the building agent role
   - Defines workspace structure (`./scripts/`, `./files/`)
   - Specifies development guidelines (use `uv` for packages, maintain scripts catalog)
   - Located at: `backend/app/env-templates/python-env-advanced/app/BUILDING_AGENT_EXAMPLE.md`

3. **scripts/README.md** (Dynamic Context)
   - Catalog of existing scripts in the workspace
   - Loaded at runtime if file exists and is not empty
   - Provides agent with awareness of what scripts already exist

4. **docs/WORKFLOW_PROMPT.md** (Dynamic Context)
   - System prompt for conversation mode agent
   - Loaded at runtime and included in building mode prompt
   - Agent updates this as workflow capabilities evolve

5. **docs/ENTRYPOINT_PROMPT.md** (Dynamic Context)
   - Trigger message for workflow execution
   - Loaded at runtime and included in building mode prompt
   - Agent defines concise command to start the workflow

## Workflow Documentation Prompts

The building agent maintains two key documentation files that define how the completed workflow will be used:

### 1. WORKFLOW_PROMPT.md (System Prompt for Conversation Mode)

**Purpose**: Comprehensive system prompt for the conversation mode agent that will execute the workflow.

**Location**: `{instance_dir}/app/docs/WORKFLOW_PROMPT.md`

**Template**: `backend/app/env-templates/python-env-advanced/app/docs/WORKFLOW_PROMPT.md`

**Content**:
- Agent's role and responsibilities
- Available scripts, APIs, and data sources
- Execution flow and decision-making guidelines
- Database schemas and file formats
- Error handling patterns

**Loading**: `sdk_manager.py::_load_workflow_prompt()` - included in building mode system prompt

**Sync**: `MessageService.sync_agent_prompts_from_environment()` - synced to backend Agent model after building sessions

### 2. ENTRYPOINT_PROMPT.md (Trigger Message)

**Purpose**: Concise user message (1-2 sentences) that triggers workflow execution.

**Location**: `{instance_dir}/app/docs/ENTRYPOINT_PROMPT.md`

**Template**: `backend/app/env-templates/python-env-advanced/app/docs/ENTRYPOINT_PROMPT.md`

**Content**:
- Short, actionable command (e.g., "Collect from my mailbox unread emails, detect invoices, and give summary")
- NOT a system prompt - this is a user message
- Used for scheduled workflow execution
- Can include parameters or configuration

**Loading**: `sdk_manager.py::_load_entrypoint_prompt()` - included in building mode system prompt

**Sync**: `MessageService.sync_agent_prompts_from_environment()` - synced to backend Agent model after building sessions

### Bidirectional Sync

**From Environment → Backend** (automatic):
- Triggered after building mode sessions complete
- `messages.py` route calls `MessageService.sync_agent_prompts_from_environment()`
- Reads prompts via `docker_adapter.py::get_agent_prompts()` (calls `/config/agent-prompts`)
- Updates `Agent.workflow_prompt` and `Agent.entrypoint_prompt` fields

**From Backend → Environment** (manual):
- User edits prompts in backend UI
- Calls `agents.py::sync_agent_prompts()` route
- Pushes via `docker_adapter.py::set_agent_prompts()` (calls `/config/agent-prompts`)
- Updates files in `{instance_dir}/app/docs/`

### Building Agent Instructions

The building agent sees both prompts in its system prompt and is instructed to:
- Update `WORKFLOW_PROMPT.md` as scripts and capabilities are developed
- Fill in `ENTRYPOINT_PROMPT.md` with a concise trigger message
- Keep both files current as the workflow evolves

**Reference**: `BUILDING_AGENT_EXAMPLE.md` section "Workflow Documentation"

## File Locations

### Template Files (Version Controlled)

- **BUILDING_AGENT_EXAMPLE.md**: `backend/app/env-templates/python-env-advanced/app/BUILDING_AGENT_EXAMPLE.md`
  - Template for building agent instructions
  - Copied to `BUILDING_AGENT.md` during environment initialization

- **scripts/README.md Template**: `backend/app/env-templates/python-env-advanced/app/scripts/README.md`
  - Initial empty catalog template
  - Agent maintains this file as scripts are created

### Instance Files (Per Environment)

- **BUILDING_AGENT.md**: `{instance_dir}/app/BUILDING_AGENT.md`
  - Created from BUILDING_AGENT_EXAMPLE.md during environment setup
  - Can be customized per environment

- **scripts/README.md**: `{instance_dir}/app/scripts/README.md`
  - Dynamically maintained catalog of scripts
  - Updated by agent whenever scripts are created/modified/removed

## Implementation Flow

### 1. Environment Creation

**File**: `backend/app/services/environment_lifecycle.py`

**Method**: `create_environment_instance()`

**Step 3**: `_setup_building_agent_prompt()`
- Copies `BUILDING_AGENT_EXAMPLE.md` → `BUILDING_AGENT.md` to instance directory
- Ensures each environment has its own copy that can be customized

### 2. SDK Manager Initialization

**File**: `backend/app/env-templates/python-env-advanced/app/server/sdk_manager.py`

**Method**: `__init__()`
- Calls `_load_building_agent_prompt()` to read `BUILDING_AGENT.md` into memory
- Stores content in `self.building_agent_prompt` for reuse across requests

### 3. Runtime Prompt Assembly

**File**: `backend/app/env-templates/python-env-advanced/app/server/sdk_manager.py`

**Method**: `send_message_stream()` with `use_building_mode=True`

**Prompt Construction Logic**:
1. Start with base `building_prompt = self.building_agent_prompt`
2. Call `_load_scripts_readme()` to append existing scripts catalog if available
3. Call `_load_workflow_prompt()` to append current workflow system prompt if available
4. Call `_load_entrypoint_prompt()` to append current trigger message if available
5. Create `SystemPromptPreset`:
   ```python
   {
       "type": "preset",
       "preset": "claude_code",
       "append": building_prompt  # BUILDING_AGENT.md + dynamic context
   }
   ```

### 4. Request Routing

**File**: `backend/app/env-templates/python-env-advanced/app/server/routes.py`

**Endpoints**: `/chat` and `/chat/stream`

**Logic**:
- When `request.mode == "building"`, pass `use_building_mode=True` to SDK manager
- Does NOT use `_workflow_prompt` (that's for conversation mode)
- Only uses explicit `request.system_prompt` if provided (for overrides)

## Key Features

### Dynamic Context Awareness

The agent knows about existing scripts because `scripts/README.md` is loaded fresh on each request. This means:
- Agent sees what scripts were created in previous sessions
- Can update/modify existing scripts intelligently
- Avoids recreating scripts that already exist
- Can maintain the catalog accurately

### Catalog Maintenance Requirement

The prompt explicitly requires the agent to:
- Update `./scripts/README.md` whenever creating/modifying/removing scripts
- Use a specific format (Purpose, Usage, Key arguments, Output)
- Keep descriptions SHORT and ACTIONABLE

### Workspace Organization

The prompt enforces strict organization:
- **All scripts** → `./scripts/`
- **All output files** → `./files/`
- **All packages** → installed via `uv`

## Example Assembled Prompt

When building mode is activated with existing scripts:

```
[Claude Code Preset System Prompt]

[Content from BUILDING_AGENT.md]
- Role definition
- Workspace structure
- Development guidelines
- Script catalog format
- Common tasks

---

## Existing Scripts in Workspace

The following is the current contents of `./scripts/README.md` which catalogs all existing scripts in this workspace:

```markdown
# Scripts Catalog

## process_data.py
**Purpose**: Process CSV data and generate summary statistics
**Usage**: `python scripts/process_data.py --input data.csv --output summary.json`
**Key arguments**: `--input` (required), `--output` (required)
**Output**: JSON file saved to ./files/
```

**Important**: When you create, modify, or remove scripts, you MUST update this file to keep it accurate.
```

## Benefits

1. **Consistency**: All script development follows the same patterns
2. **Context Preservation**: Agent knows about existing work across sessions
3. **Self-Documenting**: Scripts catalog provides built-in documentation
4. **Reusability**: Scripts are designed for workflow automation from the start
5. **Maintainability**: Clear structure and documentation requirements

## Future Enhancements

Potential improvements to the building prompt system:

- Load and include `requirements.txt` in prompt if it exists
- Include recent error logs to help debug failing scripts
- Add workspace statistics (file counts, script usage metrics)
- Support for multi-language environments (not just Python)
