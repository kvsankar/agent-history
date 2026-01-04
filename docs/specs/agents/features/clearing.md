# Context Clearing Analysis

How Claude Code, Codex CLI, and Gemini CLI handle explicit context clearing (`/clear` command).

## Summary

| Agent | Clears Context | New Session? | Where Recorded |
|-------|----------------|--------------|----------------|
| Claude Code | Yes (`/clear`) | No (same sessionId) | `~/.claude/history.jsonl` only |
| Codex CLI | Yes (`/clear`) | No (same session) | `~/.codex/history.jsonl` only |
| Gemini CLI | Yes (`/clear`) | Yes (new sessionId) | `~/.gemini/tmp/<hash>/logs.json` |

**Critical Finding:** `/clear` commands are **NOT recorded in session files**. They only appear in telemetry/history files, making context clearing invisible when analyzing session data alone.

---

## Context Clearing vs Compaction

Context clearing is fundamentally different from compaction:
- **Compaction**: Summarizes old messages, keeps continuity
- **Clearing**: Wipes context entirely, fresh start within same session

---

## Claude Code - Telemetry-Only Recording

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

---

## Codex CLI - Similar Pattern

**Location:** `~/.codex/history.jsonl`

**Behavior:**
- `/clear` recorded in telemetry file
- Same session continues
- No markers in rollout files

**Evidence:** Found **1 `/clear` command** in sample data.

---

## Gemini CLI - Per-Project Logs

**How it works:** Gemini stores logs in a per-project `logs.json` file. Unlike Claude/Codex, `/clear` creates a new session.

**Location:** `~/.gemini/tmp/<project-hash>/logs.json`

**Format:**
```json
[
  {
    "sessionId": "fecfd795-48f8-4ce2-8a6d-1edf31fdb480",
    "messageId": 5,
    "type": "user",
    "message": "/clear",
    "timestamp": "2025-11-07T11:34:04.247Z"
  },
  {
    "sessionId": "8733670b-84da-48f9-8a1b-55fe0f31b6f4",
    "messageId": 0,
    "type": "user",
    "message": "Starting with README.md...",
    "timestamp": "2025-11-07T12:24:30.962Z"
  }
]
```

**Key Differences from Claude/Codex:**
- `/clear` creates a **new sessionId** (not same session)
- Logs are per-project (in project hash directory), not global
- `messageId` provides direct message indexing
- Next message after `/clear` has `messageId: 0` (new session)

---

## Distinguishing Clear vs. New Session

| Scenario | Claude/Codex | Gemini | How to Detect |
|----------|--------------|--------|---------------|
| User closes terminal, reopens | New session ID | New session ID | Different session file |
| User runs `/clear` | Same session ID | **New session ID** | Claude/Codex: `history.jsonl`; Gemini: `logs.json` |
| Auto-compaction | Same session ID | N/A | `compact_boundary` marker (Claude only) |

**Note:** Gemini differs from Claude/Codex - `/clear` creates a completely new session rather than continuing the same session.

---

## What `/clear` Preserves vs. Clears

**Preserved:**
- Project files (CLAUDE.md, codebase)
- Session memory (accumulated learnings)
- Session ID

**Cleared:**
- Conversation history
- Message context
- Tool use history

See: [Claude Code Context Guide](https://www.arsturn.com/blog/beyond-prompting-a-guide-to-managing-context-in-claude-code)

---

## Known Issues with `/clear`

Per [GitHub issues](https://github.com/anthropics/claude-code/issues/2538):
- Context may appear to return after subsequent prompts
- "Context left until auto-compact" percentage may not reset
- No undo - clearing is permanent

---

## Schema Implications

### Proposed Schema Addition

```json
{
  "type": "session",
  "session": {...},
  "messages": [...],
  "context_clears": [
    {
      "after_message_index": 42,
      "timestamp": "2025-12-27T10:30:00Z"
    }
  ]
}
```

### Field Mapping

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `after_message_index` | Derived by matching `history.jsonl` timestamp to session messages | Same approach | From `logs.json` messageId |
| `timestamp` | From `history.jsonl` entry | From `history.jsonl` entry | From `logs.json` timestamp |

**Note:** Context clearing requires cross-referencing telemetry files with session files. This is optional enrichment - session data is complete without it.

---

## Open Questions

1. **Should we include context clears in unified export?**
   - Pro: Complete picture of session flow
   - Con: Requires parsing additional telemetry files
   - All three agents now have telemetry files identified

2. **How to represent "invisible" clears?**
   - Session files have no markers
   - Cross-referencing is imprecise (timestamp matching)
   - Should we add a confidence score?

3. **Is context clearing equivalent to a logical session boundary?**
   - User intent is "fresh start"
   - But session ID and file continue
   - Should unified schema treat post-clear as separate logical session?

---

## Data Locations

```
Claude Code:
  Session files:     ~/.claude/projects/<workspace>/<session>.jsonl
  Telemetry/history: ~/.claude/history.jsonl  (contains /clear commands)

Codex CLI:
  Session files:     ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
  Telemetry/history: ~/.codex/history.jsonl  (contains /clear commands)

Gemini CLI:
  Session files:     ~/.gemini/tmp/<project-hash>/chats/session-*.json
  Telemetry/history: ~/.gemini/tmp/<project-hash>/logs.json  (contains /clear commands)
```
