# Non-LLM to LLM Context Bridging — Technical Reference

## Purpose

When a user (or A2A client) invokes a slash command, the backend handles it without an LLM call and stores a user + system message pair. The LLM never sees the command output — it is invisible context. This feature closes that gap.

Before each LLM turn, the backend collects all eligible command pairs (user invocation + system output) that occurred since the previous agent message and prepends a `<prior_commands>` XML block to the user message content. After inclusion, each system message is marked so it is not re-included on subsequent turns.

This applies to all callers — UI, A2A, MCP — because all flow through `SessionStreamProcessor`.

---

## Architecture

```
SessionStreamProcessor._process_inner()
    │
    │  collect_pending_batches()
    │      └─ MessageService.build_non_llm_prefix(db, session_id)
    │              ├─ find boundary seq (MAX sequence_number WHERE role='agent')
    │              ├─ query eligible command system messages since boundary
    │              │     (role='system', command=true, no forwarded_to_llm_at)
    │              ├─ filter by handler.include_in_llm_context
    │              ├─ fetch paired user invocation via answers_to_message_id FK
    │              ├─ format as <prior_commands> XML with size caps
    │              └─ return (prefix_text | None, list[included_system_msg_ids])
    │      result[0]["_included_command_ids"] = included_ids  ← attached to first batch
    │
    │  step 5b: mark_command_messages_as_forwarded(db, included_command_ids)
    │      (runs before streaming begins)
    │
    └─ stream to agent-env with prefix prepended to first LLM batch content
```

### Injection Order Within `_process_inner`

1. Collect pending messages → `collect_pending_batches` builds `concatenated_content` per LLM batch and prepends the `<prior_commands>` block.
2. Recovery context injection — prepended after the prior-commands block (more recent structural context).
3. Webapp context injection.
4. Step 5b: mark forwarded messages.
5. Stream to agent-env.

---

## `<prior_commands>` Format

```xml
<prior_commands>
  <command name="/run:check" at="2026-04-19T10:12:33Z">
    <invocation>/run:check</invocation>
    <output>
...system message content (truncated if over per-block cap)...
    </output>
  </command>
  <command name="/files" at="2026-04-19T10:14:01Z">
    <invocation>/files</invocation>
    <output>
...
    </output>
  </command>
</prior_commands>
```

- **Ordering**: chronological by `sequence_number` (oldest first).
- **`name` attribute**: from `message_metadata["command_name"]` on the system message.
- **`at` attribute**: ISO 8601 UTC timestamp from `message.timestamp`.
- **`invocation`**: the user message `content` (raw slash command text).
- **`output`**: the system message `content` field — the canonical compiled output. For `/run:*` this is the final markdown block (invocation header + accumulated stdout/stderr + exit code line). Do not attempt to reconstruct from `streaming_events`.

---

## `include_in_llm_context` Per Handler

**File:** `backend/app/services/agents/command_service.py`

```python
class CommandHandler(ABC):
    include_in_llm_context: bool = True
```

| Handler | `include_in_llm_context` | Reason |
|---------|--------------------------|--------|
| `FilesCommandHandler` | `True` | File listing is useful LLM context |
| `FilesAllCommandHandler` | `True` | Same; per-block size cap handles large output |
| `AgentStatusCommandHandler` | `True` | Status information is actionable context |
| `WebappCommandHandler` | `False` | Just a URL; no information the LLM needs to act on |
| `SessionRecoverCommandHandler` | `False` | Meta-command; recovery context injected separately |
| `SessionResetCommandHandler` | `False` | Meta-command; no content value |
| `RebuildEnvCommandHandler` | `False` | Infrastructure operation; output is a notification, not content |
| `RunCommandHandler` | `True` | Core motivation — stdout/stderr of shell commands |

If a handler cannot be found in the registry (e.g., removed after messages were created), the default is `False` (safe: do not include unknown command output).

---

## Key Methods

### `MessageService.build_non_llm_prefix`

**File:** `backend/app/services/sessions/message_service.py`

```python
@staticmethod
def build_non_llm_prefix(
    db: Session,
    session_id: UUID,
) -> tuple[str | None, list[UUID]]:
```

**Returns:** `(prefix_text_or_none, list_of_included_system_message_ids)`

**Algorithm:**
1. Find boundary: `MAX(sequence_number) WHERE role='agent'`. If no agent messages, boundary is `-1` (includes all command pairs since session start).
2. Query eligible command system messages: `role='system'`, `sequence_number > boundary`, `message_metadata->>'command' = 'true'`, no `forwarded_to_llm_at` key.
3. For each candidate:
   - Skip if handler has `include_in_llm_context=False`.
   - Skip if `streaming_in_progress=True` (command still executing — picked up on next LLM turn).
   - Fetch paired user invocation via `answers_to_message_id` FK (fallback to `sequence_number - 1`).
   - Build `<command>` XML block with per-block size cap.
   - Stop adding if total budget would be exceeded.
4. Wrap blocks in `<prior_commands>`.
5. Return `(block, included_system_ids)`.

### `MessageService.mark_command_messages_as_forwarded`

**File:** `backend/app/services/sessions/message_service.py`

```python
@staticmethod
def mark_command_messages_as_forwarded(
    db: Session,
    message_ids: list[UUID],
) -> None:
```

Sets `message_metadata["forwarded_to_llm_at"] = <iso_ts>` on each row using `flag_modified` pattern, then commits. Uses bulk fetch (`WHERE id IN (...)`).

### `CommandService.get_handler`

**File:** `backend/app/services/agents/command_service.py`

```python
@classmethod
def get_handler(cls, name: str) -> CommandHandler | None:
```

Returns the registered handler instance for a given command name, or `None` if not registered. Used by `build_non_llm_prefix` to look up `include_in_llm_context`.

---

## Size and Budget Controls

**File:** `backend/app/services/sessions/message_service.py` (module-level constants)

```python
NON_LLM_BRIDGE_MAX_PER_BLOCK_BYTES: int = 16_384   # 16 KB per command block
NON_LLM_BRIDGE_MAX_TOTAL_BYTES: int = 65_536        # 64 KB total prior_commands block
NON_LLM_BRIDGE_TRUNCATION_MARKER: str = "\n[output truncated]"
```

- Per-block: if `len(content.encode("utf-8")) > 16 KB`, truncate at byte boundary and append truncation marker.
- Total budget: if adding the next block would push the total over 64 KB, drop that block (and all subsequent ones for this turn). A warning is logged. Dropped blocks are picked up on the next LLM turn (they have not been marked).
- Empty result: returns `(None, [])` — no prefix is added, no logging noise.

**Note on ordering:** blocks are included oldest-first. When the budget fills, newer command outputs are dropped. If operational experience shows the opposite ordering is more useful (newest results are most relevant), this is a known tuning point.

---

## `message_metadata` Keys

The `forwarded_to_llm_at` key is written on system messages after inclusion:

| Key | Type | Meaning |
|-----|------|---------|
| `forwarded_to_llm_at` | `str` (ISO 8601 UTC) | Timestamp when message content was included in a `<prior_commands>` block. Absence means eligible for inclusion. |

Existing keys read (not written) by this feature:

| Key | Type | Read from | Meaning |
|-----|------|-----------|---------|
| `command` | `bool` | System messages | Primary eligibility marker |
| `command_name` | `str` | System messages | e.g., `"/files"`, `"/run:check"` |
| `streaming_in_progress` | `bool` | `/run:*` system messages | Skip if `True` |
| `answers_to_message_id` | FK | System messages | Pointer to the paired user invocation |

---

## Database Migration

**File:** `backend/app/alembic/versions/<hash>_mark_existing_command_messages_forwarded.py`

Bulk-marks all pre-deploy command system messages to prevent them flooding the first LLM turn after deployment.

**`upgrade()`:**

```sql
UPDATE message
SET message_metadata = jsonb_set(
    COALESCE(message_metadata, '{}'::jsonb),
    '{forwarded_to_llm_at}',
    to_jsonb('2026-04-19T00:00:00Z'::text),
    true
)
WHERE role = 'system'
  AND (message_metadata->>'command')::boolean = true
  AND NOT (message_metadata ? 'forwarded_to_llm_at');
```

**`downgrade()`:**

```sql
UPDATE message
SET message_metadata = message_metadata - 'forwarded_to_llm_at'
WHERE role = 'system'
  AND (message_metadata->>'command')::boolean = true
  AND message_metadata->>'forwarded_to_llm_at' = '2026-04-19T00:00:00Z';
```

Optional partial index for high-volume sessions (commented out in migration as an optional addition):

```sql
CREATE INDEX CONCURRENTLY ix_message_command_pending_forward
ON message (session_id, sequence_number)
WHERE role = 'system'
  AND (message_metadata->>'command')::boolean = true
  AND NOT (message_metadata ? 'forwarded_to_llm_at');
```

---

## Recovery Context Interaction (Edge Case)

When `recovery_pending` is set, `build_recovery_context` reads recent message history. To avoid duplication, `build_recovery_context` skips `role="system"` messages with `message_metadata["command"] == True` — those are handled by the `<prior_commands>` block. The prior-commands block is always injected before recovery context in the injection order.

---

## No Frontend Changes

The `<prior_commands>` XML block is injected into the LLM's input only — it never appears in chat history visible to the user. Existing `MessageBubble` / `MessageList` components are unaffected. Command messages rendered in the UI remain as system notification bubbles exactly as today.

---

## Error Handling and Edge Cases

| Scenario | Behavior |
|---|---|
| Handler not in registry | Message skipped and not marked; eligible again on next turn |
| `message_metadata` missing `command_name` | Warning logged; message skipped |
| `answers_to_message_id` is NULL | Fall back to `sequence_number - 1` lookup; if that also fails, use a placeholder in `<invocation>` |
| `streaming_in_progress=True` on system message | Skipped; picked up on next LLM turn after stream finalizes |
| Concurrent LLM turns without session lock | Both turns include the same pairs; second `mark` write is idempotent (key already set) |
| Stream fails before Step 5b | `forwarded_to_llm_at` never written; same pairs collected again on next turn |
| No eligible command pairs | `build_non_llm_prefix` returns `(None, [])` immediately; no block prepended |

---

## Integration Points

- **[CLI Commands](../cli_commands/cli_commands.md)** — `/run:*` is the primary motivation; `RunCommandHandler.include_in_llm_context = True`
- **[Agent Commands](agent_commands.md)** — all `CommandHandler` subclasses have the `include_in_llm_context` attribute
- **[Agent Sessions](../../application/agent_sessions/agent_sessions.md)** — bridging happens inside `SessionStreamProcessor`, before each LLM batch
- **[A2A Protocol](../../application/a2a_integration/a2a_protocol/a2a_protocol.md)** — A2A callers benefit automatically; no A2A-specific changes
