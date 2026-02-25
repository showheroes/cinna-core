# App Environment Panel Widget

## Purpose

The App Environment Panel provides users access to environment-generated artifacts during agent sessions. When agents execute tasks that produce files, scripts, logs, or documentation, users need a dedicated interface to browse and download these outputs without interrupting the conversation flow.

## User Story

A user runs an agent that generates a data report. The agent processes data and creates CSV/JSON files organized in folders within the environment. Upon completion, the agent notifies the user that files are ready. The user clicks the "App" button in the session header, the environment panel slides in from the right, defaults to the Files section, and displays the folder structure. The user expands the "reports" folder by clicking on it, revealing the generated files inside, then clicks the download button on the desired report. The panel remains sticky, allowing the user to scroll through messages while keeping the panel open, or toggle it closed when not needed. To view logs, the user clicks the dropdown menu at the top of the panel and selects "Logs".

## Architecture

### Components

**Main Component**: `frontend/src/components/Environment/EnvironmentPanel.tsx`
- Sticky right-side panel overlaying the message area
- Does not cover the message input footer
- Width: 384px (default) or 768px (expanded mode)
- Toggle expand/shrink button for switching panel width
- Controlled visibility via `isOpen` prop

**Subcomponents**:
- `TabHeader.tsx` - Dropdown navigation menu with panel width toggle. Accepts `hideCredentials` prop for guest mode.
- `WorkspaceTabContent.tsx` - Reusable tab content wrapper for workspace sections. Passes `isGuest` to `TreeItemRenderer`.
- `CredentialsTabContent.tsx` - Credentials share/unshare UI with checkbox list
- `TreeItemRenderer.tsx` - Recursive tree rendering for files, folders, and SQLite databases. Accepts `isGuest` prop to use guest-compatible file viewer URLs and disable owner-only features (database viewer).
- `StateComponents.tsx` - Loading, error, empty, and no-environment states
- `FileIcon.tsx` - Type-specific file icons

**Utilities**:
- `types.ts` - TypeScript interfaces (FileItem, FolderItem, TreeItem, DatabaseTableItem, SQLite types)
- `utils.ts` - Formatting and conversion functions

**Integration Points**:
- **Authenticated sessions**: `frontend/src/routes/_layout/session/$sessionId.tsx` — "App" button in session header toggles panel visibility (`envPanelOpen`). Button variant changes to "secondary" when panel is open. Panel rendered within message list container to avoid covering footer.
- **Guest sessions**: `frontend/src/routes/guest/$guestShareToken.tsx` — same "App" button in `GuestChatHeader`. Panel detects guest mode via `useGuestShare()` hook and adapts behavior accordingly. See [Guest Sessions](../agent_guest_sessions.md).

### Navigation Structure

**Dropdown Menu** (full-width button with expand/shrink toggle):
- **Files**: Environment-generated files (CSV, JSON, TXT, SQLite, etc.) - **Default selection**
- **Scripts**: Python/executable scripts created by agents
- **Logs**: Agent execution logs, error logs, debug logs
- **Docs**: Generated documentation (Markdown files)
- **Uploads**: User-uploaded files
- **Credentials**: Manage credentials shared with the agent (hidden for guest users)

**Layout**: Dropdown selector (flex-1) + Expand/Shrink button (Maximize2/Minimize2 icons)
- No visual separator between menu and content list
- Dropdown width adjusts to panel size (352px / 720px)
- Files selected by default

## Business Logic

### Panel State Management

Panel visibility is controlled by a boolean state in the session component. The "App" button serves as the sole toggle mechanism—there is no close button within the panel itself. This design ensures users can quickly show/hide the panel without context switching.

### Section Navigation

All sections (Files, Scripts, Logs, Docs, Uploads, Credentials) are accessed through a single dropdown menu to conserve space and maintain a clean interface. The dropdown button always displays the currently active section and uses a "secondary" variant to indicate it's an interactive control. Workspace sections (Files through Uploads) share the tree-based file browser, while Credentials has its own dedicated UI.

### Data Flow

**API Integration**:
Panel fetches workspace data from backend proxy endpoints that communicate with agent environment containers:
- Workspace tree: `GET /api/v1/environments/{env_id}/workspace/tree` — Auth: `CurrentUserOrGuest`
- Returns: `WorkspaceTreeResponse` with root nodes (files, scripts, logs, docs, uploads)
- File download: `GET /api/v1/environments/{env_id}/workspace/download/{path}` — Auth: `CurrentUserOrGuest`
- File view: `GET /api/v1/environments/{env_id}/workspace/view-file/{path}` — Auth: `CurrentUserOrGuest`
- Database tables: `GET /api/v1/environments/{env_id}/workspace/database/{path}/tables` — Auth: `CurrentUser` (owner-only)
- Environment details: `GET /api/v1/environments/{env_id}` — Auth: `CurrentUser` (skipped for guests)
- Agent credentials: `GET /api/v1/agents/{agent_id}/credentials` — Auth: `CurrentUser` (skipped for guests)
- All credentials: `GET /api/v1/credentials` — Auth: `CurrentUser` (skipped for guests)
- Cache: 5 seconds (React Query `staleTime`)
- Loading states: Managed via `useQuery` hook (loading, error, success)

**Tree Structure** (`types.ts`):
- `FileItem` - Represents individual files with name, type, size, modified date
- `FolderItem` - Represents folders with children array
- `TreeItem` - Union type of FileItem or FolderItem

**Data Conversion** (`utils.ts`):
- `convertFileNodeToTreeItem()` - Transforms API response (`FileNode`) to UI tree structure
- `formatFileSize()` - Converts bytes to human-readable format (B, KB, MB, GB)
- `formatDate()` - Formats ISO timestamps to localized date strings
- `getFileExtension()` - Extracts file extension for icon selection

**Download Flow**:
- User clicks download button → `handleDownload(filePath)` triggered
- Axios interceptor sets `responseType: 'blob'` for download requests
- Backend endpoint: `GET /api/v1/environments/{env_id}/workspace/download/{path}`
- Files: Streamed directly with original filename
- Folders: Streamed as ZIP archive
- Browser download triggered via blob URL creation

### Folder Navigation

**Compact Layout** (py-1 px-2 padding):

**Folders:**
- Chevron (ChevronRight/Down) + Folder icon (Folder/FolderOpen, blue) + Name
- On hover: Size appears (dimmed, right-aligned) + Download button
- Modified date: Icon title tooltip
- Full name: Text title tooltip (when truncated)
- Indentation: `12px * level`

**Files:**
- Icon + Basename + Extension (hover-only, dimmed) + Size (hover-only, dimmed) + Download (hover)
- Modified date: Icon title tooltip
- Full name: Text title tooltip
- Extension hidden by default, fades in on hover
- Indentation: `12px * level + 24px`

**Interaction:**
- Folders: Click name area to expand/collapse, click download button to download folder
- Files: Hover to reveal extension, size, and download button
- State persists across section switches

### Download Functionality

Both files and folders display download button on hover (opacity-0 → group-hover:opacity-100):
- **Files**: Download individual file directly
- **Folders**: Download entire folder as ZIP archive
- Button uses `e.stopPropagation()` to prevent folder expansion on click
- Implementation: `handleDownload()` in `EnvironmentPanel.tsx`
- API: `GET /api/v1/environments/{env_id}/workspace/download/{path}`

### SQLite Database Browser

SQLite files (`.sqlite`, `.db`) are expandable to reveal their tables and views:

**Interaction:**
- Click SQLite file → expands/collapses like a folder
- On first expand: fetches table list via `GET /api/v1/environments/{env_id}/workspace/database/{path}/tables`
- Re-fetches fresh data on each expand
- Click table/view → opens `/environment/{envId}/database?path=...&table=...` in new tab

**Display:**
- Tables: Table2 icon (blue)
- Views: Table2 icon (purple)
- Loading state: Spinner with "Loading tables..."
- Error state: "Error loading tables"
- Empty state: "No tables found"

**Types** (`types.ts`):
- `DatabaseTableItem` - Table/view entry with name, type, parent database path
- `SQLiteTableInfo`, `SQLiteColumnInfo` - Schema metadata
- `SQLiteQueryResult` - Query execution results with pagination

### Credentials Tab

> **Note**: The Credentials tab is hidden for [guest session](../agent_guest_sessions.md) users. Guests cannot view or manage agent credentials.

Quick access to manage which credentials are shared with the agent:

**Component**: `CredentialsTabContent.tsx`

**Display:**
- Lists all credentials from user's active workspace
- Checkbox indicates shared status with current agent
- Shows credential name and type label (e.g., "Gmail OAuth", "API Token")

**Supported Credential Types:**
- `email_imap` → "Email (IMAP)"
- `gmail_oauth` / `gmail_oauth_readonly` → "Gmail OAuth" / "Gmail OAuth (Read-Only)"
- `gdrive_oauth` / `gdrive_oauth_readonly` → "Google Drive OAuth" / "Google Drive OAuth (Read-Only)"
- `gcalendar_oauth` / `gcalendar_oauth_readonly` → "Google Calendar OAuth" / "Google Calendar OAuth (Read-Only)"
- `odoo` → "Odoo"
- `api_token` → "API Token"

**Actions:**
- Check → shares credential with agent (`AgentsService.addCredentialToAgent`)
- Uncheck → unshares credential (`AgentsService.removeCredentialFromAgent`)
- Success toast on share/unshare
- Loading spinner on individual item during mutation

**States:**
- Loading: Centered spinner
- Empty: "No credentials available" with guidance to create credentials

## Icons

Items are visually distinguished by type-specific icons:

**Folder Icons:**
- Folder (closed): Folder icon (blue)
- Folder (open): FolderOpen icon (blue)
- Chevron Right: Collapsed state indicator
- Chevron Down: Expanded state indicator

**File Icons:**
- CSV: FileSpreadsheet (green)
- JSON: FileJson (blue)
- TXT: FileText (gray)
- PY (Python): FileCode (purple)
- LOG: ScrollText (yellow)
- MD (Markdown): BookOpen (indigo)
- SQLite: Database icon (expandable)
- Default: FileText (gray)

**Database Table Icons:**
- Table: Table2 (blue)
- View: Table2 (purple)

Component: `FileIcon.tsx` - Type-specific icon rendering with color coding
Component: `TreeItemRenderer.tsx` - Recursive tree rendering with folder/file/database distinction

## Sticky Behavior

The panel uses absolute positioning within a relative container that encompasses only the message list area. This ensures:
- Panel overlays messages but not the input footer
- Users can scroll messages while panel is open
- Panel remains visible during scrolling
- Message input remains accessible at all times

## Future Extensibility

### Implemented Features

✅ **Expandable panel**: 2x width toggle (384px ↔ 768px)
✅ **Folder downloads**: Download entire folders as archives
✅ **Progressive disclosure**: Extension/size appear on hover
✅ **Compact single-line layout**: Efficient space usage
✅ **Tooltips**: Full names and dates on truncated items
✅ **SQLite database browser**: Expand `.sqlite` files to view/open tables
✅ **Credentials management**: Share/unshare credentials with agent directly from panel

### Planned Features

1. **Script Execution**: Run button for scripts in Scripts section
2. **CLI Terminal**: New section for direct command execution
3. **File Preview**: Inline preview for text files, JSON, CSV (modal or expandable)
4. **Real-time Updates**: WebSocket integration to auto-refresh
5. **Search/Filter**: Recursive search bar for all sections
6. **Bulk Operations**: Multi-select for batch download
7. **Context Menus**: Right-click operations (delete, rename, etc.)
8. **Drag & Drop**: Upload files to environment
9. **Breadcrumb Navigation**: Show current folder path for deep nesting

### Section Menu Expansion

The dropdown menu is extensible for additional sections. Future candidates:
- **Terminal**: Interactive CLI access
- **Metrics/Analytics**: Performance and usage statistics
- **API Requests**: HTTP request history and responses
- **Environment Variables**: View and manage env vars
- **Artifacts**: Specialized outputs (charts, visualizations, exports)

## Guest Mode

When rendered within a [guest session](../agent_guest_sessions.md), the panel adapts its behavior to respect the guest access model. Guest mode is detected via the `useGuestShare()` hook.

**Disabled features:**
- **Credentials tab**: Hidden from dropdown menu (`TabHeader` receives `hideCredentials` prop). Guests cannot view or manage agent credentials.
- **Environment details query**: `EnvironmentsService.getEnvironment()` is skipped (uses `CurrentUser`, not guest-compatible). The SDK footer is not displayed.
- **Database viewer**: Clicking SQLite tables is disabled (database query/schema endpoints are owner-only).

**Adapted features:**
- **File viewing**: Clicking viewable files opens `/guest/file-viewer?envId=...&path=...` (a standalone route without `_layout/`) instead of `/environment/{envId}/file` (which requires the authenticated layout shell). See [File Management](../../file-management/file_management_overview.md).
- **Workspace tree**: Loads normally — backend `GET /workspace/tree` supports `CurrentUserOrGuest`.
- **File download**: Works normally — backend `GET /workspace/download/{path}` supports `CurrentUserOrGuest`.

**Prop propagation**: `isGuest` is passed from `EnvironmentPanel` → `WorkspaceTabContent` → `TreeItemRenderer` to control URL generation and feature gating.

## Design Principles

- **Non-intrusive**: Panel doesn't block core conversation features
- **Context-aware**: Only relevant when agents interact with the environment
- **Optional**: Users can complete sessions without ever opening it
- **Discoverable**: "App" button with Package icon provides clear affordance
- **Persistent**: Panel state survives scrolling and message updates within a session

## Integration Notes

The panel is session-scoped. Each session has its own isolated environment, so artifacts are tied to `session_id`. When users switch sessions, the panel automatically shows that session's environment state (once API integration is complete).

## Implementation Details

**Component Architecture:**
- `EnvironmentPanel.tsx` (main) - Panel state, data fetching, download handling, credentials mutations
- `TabHeader.tsx` - Dropdown navigation with width toggle
- `WorkspaceTabContent.tsx` - Reusable tab wrapper for workspace sections
- `CredentialsTabContent.tsx` - Credentials management UI
- `TreeItemRenderer.tsx` - Recursive tree item rendering (files, folders, SQLite)
- `StateComponents.tsx` - Loading, error, empty, no-environment states
- `FileIcon.tsx` - File type icon component
- `types.ts` - TypeScript interfaces (FileItem, FolderItem, TreeItem, DatabaseTableItem)
- `utils.ts` - Formatting utilities and API response conversion

**State Management:**
- `activeTab` - Current selected section (files/scripts/logs/docs/uploads/credentials)
- `expandedFolders` - Set of expanded folder paths (also used for SQLite files)
- `isWidePanelMode` - Panel width toggle (384px/768px)
- `databaseTables` - Record of SQLite file paths → { tables, loading, error }
- `useQuery` - React Query for workspace tree and credentials fetching
- `useMutation` - React Query for credential share/unshare operations

**Key Features:**
1. **Modular architecture**: Separated concerns into focused components
2. **API integration**: Real workspace data from environment containers
3. **Progressive disclosure**: Extensions, sizes, download buttons on hover
4. **Compact layout**: Single-line items with py-1 px-2 padding
5. **Path-based folder keys**: Prevents conflicts (`files/data/archive`)
6. **Event isolation**: `e.stopPropagation()` for download buttons
7. **Error handling**: Loading, error, empty, and no-environment states
8. **SQLite expansion**: Database files expand to show tables/views inline
9. **Credentials management**: Toggle credential sharing without leaving panel

**Visual Design:**
- Meta info dimming: `text-muted-foreground/60`
- Hover animations: `opacity-0 group-hover:opacity-100 transition-opacity`
- Smooth width transition: `transition-all duration-200`
- Icon color coding: CSV (green), JSON (blue), TXT (gray), PY (purple), LOG (yellow), MD (indigo)
