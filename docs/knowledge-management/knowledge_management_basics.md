# Knowledge Management - Feature Overview

## Purpose

Allows users to connect Git repositories containing documentation that agents can query during building mode. Supports both public and private repositories via SSH keys.

## Business Logic

**User Flow:**
1. User adds SSH keys (for private repos) in Settings
2. User creates Knowledge Source pointing to Git repository
3. System clones repo and extracts articles from `.ai-knowledge/settings.json`
4. Articles stored in database (content + metadata)
5. Agents query knowledge when building integrations

**Access Control:**
- Knowledge sources are user-owned
- Workspace-level permissions (all workspaces or specific ones)
- Enable/disable toggle for temporary deactivation

**Status Lifecycle:**
- `pending` → newly created, not verified
- `connected` → repository accessible, articles synced
- `error` → connection/parsing failed
- `disconnected` → SSH key removed or lost access

## Repository Format

Repositories must contain `.ai-knowledge/settings.json`:

```
my-docs-repo/
├── .ai-knowledge/
│   └── settings.json          # Required: defines articles
├── articles/
│   ├── integration-guide.md
│   └── api-reference.md
```

**settings.json structure:**
- `static_articles[]` - array of article configs
- Each article: title, description, tags, features, path (to .md file)

## Key File Locations

### Backend

**Models:**
- `backend/app/models/ssh_key.py` - SSH key storage (encrypted)
- `backend/app/models/knowledge.py` - Git sources, articles, workspace permissions

**Services:**
- `backend/app/services/ssh_key_service.py` - SSH key encryption/decryption
- `backend/app/services/git_operations.py` - Git clone/verify with SSH support
- `backend/app/services/knowledge_article_service.py` - Parse settings.json, store articles
- `backend/app/services/knowledge_source_service.py` - CRUD + check_access + refresh_knowledge

**API Routes:**
- `backend/app/api/routes/ssh_keys.py` - SSH key management (6 endpoints)
- `backend/app/api/routes/knowledge_sources.py` - Source management (10 endpoints)

**Migrations:**
- `backend/app/alembic/versions/dcbfc8267939_*.py` - SSH keys table
- `backend/app/alembic/versions/240176144d01_*.py` - Knowledge tables

### Frontend

**Pages:**
- `frontend/src/routes/_layout/settings.tsx` - SSH Keys tab
- `frontend/src/routes/_layout/knowledge-sources.tsx` - Sources list
- `frontend/src/routes/_layout/knowledge-source/$sourceId.tsx` - Source detail + articles

**Components:**
- `frontend/src/components/UserSettings/SSHKeys.tsx` - Key management
- `frontend/src/components/UserSettings/{Generate,Import,Edit}KeyModal.tsx` - Key modals
- `frontend/src/components/KnowledgeSources/{Add,Edit}SourceModal.tsx` - Source modals

**Generated API Client:**
- `frontend/src/client/sdk.gen.ts` - SshKeysService, KnowledgeSourcesService

## Database Tables

**user_ssh_keys:**
- Stores encrypted SSH keys and passphrases
- FK to users (CASCADE delete)

**ai_knowledge_git_repo:**
- Git source configuration (URL, branch, SSH key ref)
- Status tracking, workspace access type
- FK to users and ssh_keys

**ai_knowledge_git_repo_workspaces:**
- Many-to-many: sources ↔ workspaces
- Only used when access_type = 'specific'

**knowledge_articles:**
- Parsed article content and metadata
- Content hash for change detection
- Embedding fields (currently NULL, for future vector search)
- FK to git_repo (CASCADE delete)

## Core Operations

**Check Access:**
- Uses `git ls-remote` to verify repo/branch exists
- Doesn't clone (fast verification)
- Updates source status

**Refresh Knowledge:**
1. Clone repository (shallow, depth=1)
2. Parse `.ai-knowledge/settings.json`
3. For each article: read file, calculate hash, upsert if changed
4. Delete orphaned articles (removed from settings.json)
5. Update source metadata (commit hash, sync timestamp)
6. Cleanup temporary clone directory

**Article Storage:**
- Upsert based on (git_repo_id, file_path) unique constraint
- Content hash comparison skips unchanged articles
- Embeddings NOT generated yet (Phase 4)

## Security

**SSH Keys:**
- Private keys encrypted with Fernet (AES-256)
- Uses existing `encrypt_field()` / `decrypt_field()` from security.py
- Decrypted only during Git operations (in-memory)
- Temporary SSH key files (600 permissions, auto-cleanup)

**Git Operations:**
- Temporary directories for clones
- SSH key never logged or exposed in responses
- StrictHostKeyChecking disabled for ease of use

## Implementation Status

**Phase 1 (Complete):** SSH key management
**Phase 2 (Complete):** Knowledge sources UI + CRUD
**Phase 3 (Complete):** Git operations + article parsing/storage
**Phase 4 (Future):** Embedding generation (Google Gemini)
**Phase 5 (Future):** Vector search (pgvector)
**Phase 6 (Future):** Agent query integration (two-step discovery/retrieval)

## Dependencies

- `gitpython>=3.1.43` - Git operations
- `cryptography>=46.0.3` - SSH key encryption (already present)
- `pgvector>=0.4.2` - Vector storage (added, not yet used)
