# Context Compaction Analysis

How Claude Code, Codex CLI, and Gemini CLI handle context window compaction and summarization.

## Summary

| Agent | Compaction | Storage | Summary Content |
|-------|------------|---------|-----------------|
| Claude Code | Yes (dual-layer) | Inline + separate `.md` files | Full structured Markdown |
| Codex CLI | Yes (inline) | Inline in JSONL | Markdown in `payload.message` |
| Gemini CLI | No | N/A | Uses `thoughts` for reasoning |

---

## Claude Code - Dual-Layer Compaction System

Claude Code uses a sophisticated two-layer approach to context compaction.

### Layer 1: Inline Compaction Markers

**Location:** `~/.claude/projects/<workspace>/<session>.jsonl`

**Message Structure:**
```json
{
  "type": "system",
  "subtype": "compact_boundary",
  "content": "Conversation compacted",
  "uuid": "db0953ca-b5ae-4e37-a85c-7884b9d2cc5e",
  "parentUuid": null,
  "logicalParentUuid": "9f8cc203-0e27-444f-88e7-b3eb9eef86d1",
  "timestamp": "2025-12-16T10:37:04.233Z",
  "isMeta": false,
  "level": "info",
  "compactMetadata": {
    "trigger": "auto",
    "preTokens": 155116
  }
}
```

**Key Fields:**

| Field | Description |
|-------|-------------|
| `subtype` | Always `"compact_boundary"` |
| `logicalParentUuid` | Links to last message before compaction |
| `compactMetadata.trigger` | How compaction was triggered (`"auto"`) |
| `compactMetadata.preTokens` | Token count before compaction (~155,000) |

### Layer 2: Session Memory Files

**Location:** `~/.claude/projects/<workspace>/<session-id>/session-memory/summary.md`

**Structure:** Full Markdown document with 10 structured sections:

1. Title
2. Current State
3. Task Specification
4. Files Modified
5. Workflow
6. Errors Encountered
7. Codebase Understanding
8. Learnings
9. Results
10. Worklog

**Characteristics:**
- Human-readable (~1,000 lines)
- Serves as both summary and documentation
- Persists across session restarts

### Summary Type Messages

Found **23 `summary` type messages** and **541 `compact_boundary` messages** in sample data.

The `summary` type appears to contain inline summary content within the JSONL stream.

---

## Codex CLI - Event-Stream Compaction

Codex CLI treats compaction as a first-class event in its rollout stream.

### Storage

**Location:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`

### Message Structure

```json
{
  "type": "compacted",
  "payload": {
    "message": "**Progress + Plan Status**\n\n- Completed X\n- In progress Y\n\n**Outstanding TODOs**\n\n- Task 1\n- Task 2\n\n**Testing Gaps**\n\n- Need tests for...\n\n**Open quirks / setup notes**\n\n- Note about..."
  },
  "replacement_history": [
    {"type": "message", "content": "..."},
    {"type": "message", "content": "..."}
  ],
  "timestamp": "2025-12-27T10:30:00Z"
}
```

**Key Fields:**

| Field | Description |
|-------|-------------|
| `type` | Always `"compacted"` |
| `payload.message` | Full Markdown summary |
| `replacement_history` | Array of original messages being replaced (optional) |

### Markdown Summary Structure

```markdown
**Progress + Plan Status**
- What's been done
- Current state

**Outstanding TODOs**
- Remaining tasks

**Testing Gaps**
- Areas needing tests

**Open quirks / setup notes**
- Environment-specific notes
```

### Characteristics

- No separate files - everything stays in the single rollout JSONL
- On session resume, new events append to same file
- Found **5 compacted records** in sample file

---

## Gemini CLI - No Compaction Found

Gemini CLI does not appear to have an explicit context compaction mechanism.

### Storage

**Location:** `~/.gemini/tmp/<project-hash>/chats/session-*.json`

### Structure

```json
{
  "id": "session-id",
  "projectHash": "sha256...",
  "startTime": "2025-12-27T10:00:00Z",
  "lastUpdated": "2025-12-27T11:00:00Z",
  "messages": [
    {
      "id": "msg-1",
      "type": "user",
      "content": "...",
      "timestamp": "..."
    },
    {
      "id": "msg-2",
      "type": "model",
      "content": "...",
      "thoughts": [
        {"subject": "Analysis", "description": "..."},
        {"subject": "Approach", "description": "..."}
      ]
    }
  ]
}
```

### Observations

- Uses `thoughts` field for extended reasoning (5+ thoughts per response)
- No `compaction`, `summary`, or `replacement_history` markers
- No compaction boundaries or token tracking
- May handle context limits server-side or via truncation

---

## Comparison

| Feature | Claude Code | Codex CLI | Gemini CLI |
|---------|-------------|-----------|------------|
| **Compaction** | Yes (2-layer) | Yes (inline) | No |
| **Summary Storage** | Separate `.md` file | In JSONL `payload.message` | N/A |
| **Token Tracking** | Yes (`preTokens`) | No | N/A |
| **Message Linking** | `logicalParentUuid` | `replacement_history` | N/A |
| **Trigger Info** | Yes (`trigger: auto`) | No | N/A |

### Architectural Differences

1. **Claude Code** uses UUID linking (`logicalParentUuid`) to maintain conversation flow across compaction boundaries

2. **Codex CLI** treats compaction as a first-class event type, allowing seamless integration into the event stream

3. **Gemini CLI** uses structured `thoughts` for extended reasoning rather than explicit compaction

4. Claude's session-memory approach is most transparent - users can read full context offline

5. Codex's approach is most integrated - compaction fits naturally into the rollout event model

---

## Schema Implications

### Proposed Schema Addition

```json
{
  "type": "session",
  "session": {...},
  "messages": [...],
  "compaction": {
    "boundaries": [
      {
        "after_message_index": 15,
        "uuid": "boundary-uuid",
        "trigger": "auto",
        "pre_tokens": 155116,
        "summary": "Full markdown summary text...",
        "replaced_message_indices": [1, 2, 3, 4, 5]
      }
    ]
  }
}
```

### Field Mapping

| Unified Field | Claude Code | Codex CLI |
|---------------|-------------|-----------|
| `after_message_index` | Derived from `logicalParentUuid` | Position in stream |
| `trigger` | `compactMetadata.trigger` | N/A (always implicit) |
| `pre_tokens` | `compactMetadata.preTokens` | N/A |
| `summary` | From `session-memory/summary.md` | `payload.message` |
| `replaced_message_indices` | N/A | From `replacement_history` |

---

## Open Questions

1. **Should compaction be a separate line type in NDJSON?**
   - Pro: Cleaner separation, streamable
   - Con: Breaks session atomicity

2. **How to handle session-memory files?**
   - Option A: Inline in session record
   - Option B: Separate `compaction_summary` line type
   - Option C: Reference by path only

3. **Token counts across agents?**
   - Only Claude Code tracks `preTokens`
   - Should we estimate for others?

---

## Data Locations

```
Claude Code:
  Session files:     ~/.claude/projects/<workspace>/<session>.jsonl
  Session memory:    ~/.claude/projects/<workspace>/<session>/session-memory/summary.md

Codex CLI:
  Session files:     ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl

Gemini CLI:
  Session files:     ~/.gemini/tmp/<project-hash>/chats/session-*.json
```
