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

**Integration Point**: `frontend/src/routes/_layout/session/$sessionId.tsx`
- "App" button in session header (line 162-170)
- Button toggles panel visibility state (`envPanelOpen`)
- Button variant changes to "secondary" when panel is open
- Panel rendered within message list container to avoid covering footer

### Navigation Structure

**Dropdown Menu** (full-width button with expand/shrink toggle):
- **Files**: Environment-generated files (CSV, JSON, TXT, etc.) - **Default selection**
- **Scripts**: Python/executable scripts created by agents
- **Logs**: Agent execution logs, error logs, debug logs
- **Docs**: Generated documentation (Markdown files)

**Layout**: Dropdown selector (flex-1) + Expand/Shrink button (Maximize2/Minimize2 icons)
- No visual separator between menu and content list
- Dropdown width adjusts to panel size (352px / 720px)
- Files selected by default

## Business Logic

### Panel State Management

Panel visibility is controlled by a boolean state in the session component. The "App" button serves as the sole toggle mechanism—there is no close button within the panel itself. This design ensures users can quickly show/hide the panel without context switching.

### Section Navigation

All sections (Files, Scripts, Logs, Docs) are accessed through a single dropdown menu to conserve space and maintain a clean interface. The dropdown button always displays the currently active section and uses a "secondary" variant to indicate it's an interactive control. This unified navigation pattern provides consistent access to all panel features without visual clutter.

### Data Flow

**Current Implementation** (stub data):
Each section uses hardcoded stub arrays (STUB_FILES, STUB_SCRIPTS, STUB_LOGS, STUB_DOCS) to demonstrate UI patterns. Data follows a tree structure supporting nested folders:

**Tree Item Structure:**
```typescript
interface FileItem {
  type: "file"
  name: string
  fileType: string  // csv, json, txt, py, log, md, etc.
  size: string
  modified: string
}

interface FolderItem {
  type: "folder"
  name: string
  size: string
  modified: string
  children: TreeItem[]  // Array of files or folders
}

type TreeItem = FileItem | FolderItem
```

**Example Tree:**
```
Files
├── employee_report_2025.csv (file, 2.3 MB)
├── data/ (folder, 2.8 MB)
│   ├── customer_transactions_q4.json (file, 456 KB)
│   ├── sales_data_processed_dec.csv (file, 1.2 MB)
│   └── archive/ (nested folder, 1.1 MB)
│       ├── legacy_customer_data_2024.json (file, 234 KB)
│       └── vendor_bills_backup_nov_2024.csv (file, 890 KB)
├── processing_output_log.txt (file, 12 KB)
└── reports/ (folder, 1.8 MB)
    ├── quarterly_summary_metadata.json (file, 8 KB)
    └── vendor_bills_report_company_jan_2025.csv (file, 1.8 MB)
```

**Future Implementation** (API-driven):
- Files section: `GET /api/v1/sessions/{session_id}/environment/files`
- Scripts section: `GET /api/v1/sessions/{session_id}/environment/scripts`
- Logs section: `GET /api/v1/sessions/{session_id}/environment/logs`
- Docs section: `GET /api/v1/sessions/{session_id}/environment/docs`

Each endpoint will return a tree structure representing the full hierarchy of session-specific environment artifacts generated during agent execution. The entire tree is loaded initially, and folder expansion/collapse is handled client-side.

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
- **Files**: Download individual file
- **Folders**: Download entire folder (compressed archive)
- Button uses `e.stopPropagation()` to prevent folder expansion on click

Future API: `GET /api/v1/sessions/{session_id}/environment/download/{item_id}`

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
- Default: FileText (gray)

Method: `getFileIcon(fileType)` in EnvironmentPanel component
Component: `TreeItemRenderer` handles recursive rendering of tree structure

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

The dropdown menu is extensible for additional sections beyond the current four. Future candidates:
- **Terminal**: Interactive CLI access
- **Metrics/Analytics**: Performance and usage statistics
- **Database**: Query results and database snapshots
- **API Requests**: HTTP request history and responses
- **Environment Variables**: View and manage env vars
- **Artifacts**: Specialized outputs (charts, visualizations, exports)

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
- Main component: `EnvironmentPanel` - Manages panel state, section selection, and width mode
- Sub-component: `TreeItemRenderer` - Recursive component for rendering tree structure
- State: `activeTab`, `expandedFolders`, `isWidePanelMode`, `moreMenuOpen`
- Rendering: Conditional rendering based on item type (file vs folder)

**Key Features:**
1. **Expandable panel**: Toggle between 384px and 768px width with smooth transition
2. **Progressive disclosure**: Extensions, sizes, download buttons appear on hover
3. **Compact layout**: py-1 px-2 padding, single-line items
4. **Tooltips**: Full filename and modified date on hover
5. **Path-based folder keys**: Prevents duplicate name conflicts (`data/archive`)
6. **Event isolation**: `e.stopPropagation()` for download buttons on folders

**Visual Design:**
- Meta info dimming: `text-muted-foreground/60`
- Hover animations: `opacity-0 group-hover:opacity-100 transition-opacity`
- Smooth width transition: `transition-all duration-200`
- Icon color coding: CSV (green), JSON (blue), TXT (gray), PY (purple), LOG (yellow), MD (indigo)
