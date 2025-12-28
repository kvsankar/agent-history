# Context Compaction and Clearing Analysis

Analysis of how Claude Code, Codex CLI, and Gemini CLI handle context window compaction, summarization, and explicit context clearing.

## Summary

### Compaction

| Agent | Compaction | Storage | Summary Content |
|-------|------------|---------|-----------------|
| Claude Code | Yes (dual-layer) | Inline + separate `.md` files | Full structured Markdown |
| Codex CLI | Yes (inline) | Inline in JSONL | Markdown in `payload.message` |
| Gemini CLI | No | N/A | Uses `thoughts` for reasoning |

### Context Clearing (`/clear`)

| Agent | Clears Context | New Session? | Where Recorded |
|-------|----------------|--------------|----------------|
| Claude Code | Yes (`/clear`) | No (same sessionId) | `~/.claude/history.jsonl` only |
| Codex CLI | Yes (`/clear`) | No (same session) | `~/.codex/history.jsonl` only |
| Gemini CLI | Unknown | N/A | No telemetry file found |

**Critical Finding:** `/clear` commands are **NOT recorded in session files**. They only appear in telemetry/history files, making context clearing invisible when analyzing session data alone.

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

## Context Clearing (`/clear` Command)

Context clearing is fundamentally different from compaction:
- **Compaction**: Summarizes old messages, keeps continuity
- **Clearing**: Wipes context entirely, fresh start within same session

### Claude Code - Telemetry-Only Recording

**Key Discovery:** `/clear` commands are stored in `~/.claude/history.jsonl`, NOT in session files.

**Location:** `~/.claude/history.jsonl`

**Format:**
```json
{
  "display": "/clear ",
  "sessionId": "9d6909e3-aaea-454d-ab21-15c939e865b1",
  "timestamp": 1762870614075
}
```

**What Happens on `/clear`:**
1. Context window is wiped
2. Same `sessionId` continues (no new session file)
3. Entry added to `history.jsonl`
4. Session `.jsonl` file has NO marker
5. CLAUDE.md and project files are re-read
6. Session memory/summaries may be preserved

**Evidence:** Found **46 `/clear` commands** in sample `history.jsonl` data.

**Implication:** Analyzing session `.jsonl` files alone cannot detect when context was cleared. Messages before and after `/clear` appear continuous.

### Codex CLI - Similar Pattern

**Location:** `~/.codex/history.jsonl`

**Behavior:**
- `/clear` recorded in telemetry file
- Same session continues
- No markers in rollout files

**Evidence:** Found **1 `/clear` command** in sample data.

### Gemini CLI - No Clear Mechanism Found

- No `history.jsonl` equivalent discovered
- No `/clear` command pattern found
- May use different UX for context management

### Distinguishing Clear vs. New Session

| Scenario | Session ID | How to Detect |
|----------|------------|---------------|
| User closes terminal, reopens | New ID | Different session file |
| User runs `/clear` | Same ID | Only via `history.jsonl` cross-reference |
| Auto-compaction | Same ID | `compact_boundary` marker in session file |

### What `/clear` Preserves vs. Clears

**Preserved:**
- Project files (CLAUDE.md, codebase)
- Session memory (accumulated learnings)
- Session ID

**Cleared:**
- Conversation history
- Message context
- Tool use history

See: [Claude Code Context Guide](https://www.arsturn.com/blog/beyond-prompting-a-guide-to-managing-context-in-claude-code)

### Known Issues with `/clear`

Per [GitHub issues](https://github.com/anthropics/claude-code/issues/2538):
- Context may appear to return after subsequent prompts
- "Context left until auto-compact" percentage may not reset
- No undo - clearing is permanent

---

## Comparative Analysis

### Feature Comparison

| Feature | Claude Code | Codex CLI | Gemini CLI |
|---------|-------------|-----------|------------|
| **Compaction** | Yes (2-layer) | Yes (inline) | No |
| **Summary Storage** | Separate `.md` file | In JSONL `payload.message` | N/A |
| **Token Tracking** | Yes (`preTokens`) | No | N/A |
| **Message Linking** | `logicalParentUuid` | `replacement_history` | N/A |
| **Trigger Info** | Yes (`trigger: auto`) | No | N/A |
| **Context Clearing** | `/clear` in telemetry | `/clear` in telemetry | Unknown |
| **Clear in Session File** | No | No | N/A |
| **Organization** | By workspace | By date | By project hash |
| **Resume Strategy** | New session file | Append to same file | New session |

### Architectural Differences

1. **Claude Code** uses UUID linking (`logicalParentUuid`) to maintain conversation flow across compaction boundaries

2. **Codex CLI** treats compaction as a first-class event type, allowing seamless integration into the event stream

3. **Gemini CLI** uses structured `thoughts` for extended reasoning rather than explicit compaction

4. Claude's session-memory approach is most transparent - users can read full context offline

5. Codex's approach is most integrated - compaction fits naturally into the rollout event model

---

## Implications for Unified Schema

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
  },
  "context_clears": [
    {
      "after_message_index": 42,
      "timestamp": "2025-12-27T10:30:00Z"
    }
  ]
}
```

### Field Mapping - Compaction

| Unified Field | Claude Code | Codex CLI |
|---------------|-------------|-----------|
| `after_message_index` | Derived from `logicalParentUuid` | Position in stream |
| `trigger` | `compactMetadata.trigger` | N/A (always implicit) |
| `pre_tokens` | `compactMetadata.preTokens` | N/A |
| `summary` | From `session-memory/summary.md` | `payload.message` |
| `replaced_message_indices` | N/A | From `replacement_history` |

### Field Mapping - Context Clearing

| Unified Field | Claude Code | Codex CLI |
|---------------|-------------|-----------|
| `after_message_index` | Derived by matching `history.jsonl` timestamp to session messages | Same approach |
| `timestamp` | From `history.jsonl` entry | From `history.jsonl` entry |

**Note:** Context clearing requires cross-referencing telemetry files (`history.jsonl`) with session files. This is optional enrichment - session data is complete without it.

---

## Open Questions

### Compaction

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

### Context Clearing

4. **Should we include context clears in unified export?**
   - Pro: Complete picture of session flow
   - Con: Requires parsing additional telemetry files
   - Con: Not available for all agents

5. **How to represent "invisible" clears?**
   - Session files have no markers
   - Cross-referencing is imprecise (timestamp matching)
   - Should we add a confidence score?

6. **Is context clearing equivalent to a logical session boundary?**
   - User intent is "fresh start"
   - But session ID and file continue
   - Should unified schema treat post-clear as separate logical session?

---

## Data Locations Reference

```
Claude Code:
  Session files:     ~/.claude/projects/<workspace>/<session>.jsonl
  Session memory:    ~/.claude/projects/<workspace>/<session>/session-memory/summary.md
  Telemetry/history: ~/.claude/history.jsonl  (contains /clear commands)

Codex CLI:
  Session files:     ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
  Telemetry/history: ~/.codex/history.jsonl  (contains /clear commands)

Gemini CLI:
  Session files:     ~/.gemini/tmp/<project-hash>/chats/session-*.json
  Telemetry/history: (not found)
```
