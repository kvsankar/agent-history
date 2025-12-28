# Context Compaction, Clearing, Interruption, and Rejection Analysis

Analysis of how Claude Code, Codex CLI, and Gemini CLI handle context window compaction, summarization, explicit context clearing, user/system interruptions, and edit/tool rejections.

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

### Interruptions

| Agent | How Recorded | Field/Marker | In Session File? |
|-------|--------------|--------------|------------------|
| Claude Code | User message | `[Request interrupted by user]` | Yes |
| Codex CLI | Content text | "aborted", "cancelled" in text | Yes |
| Gemini CLI | Info message | `type: "info"`, `content: "Request cancelled."` | Yes |

**Key Finding:** Unlike context clearing, interruptions ARE recorded in session files. Each agent uses a different approach.

### Rejections (Edit/Tool Declined)

| Agent | How Recorded | Key Field | User Reason Captured? |
|-------|--------------|-----------|----------------------|
| Claude Code | tool_result with `is_error: true` | Content contains "user doesn't want to proceed" | Yes |
| Codex CLI | Unknown | Not found in samples | Unknown |
| Gemini CLI | Unknown | No explicit rejection field | Unknown |

**Key Finding:** Claude Code explicitly captures rejections with distinguishable markers. User's stated reason is preserved in full.

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

## Interruptions

Interruptions occur when a user stops an ongoing operation (Ctrl+C, Escape) or when system issues halt execution (network, rate limits).

### Types of Interruptions

| Type | Trigger | Example |
|------|---------|---------|
| **User interrupts response** | Escape key, Ctrl+C | User stops assistant mid-generation |
| **User interrupts tool** | Ctrl+C during execution | User stops long-running Bash command |
| **User interrupts agent** | Escape during subagent | User cancels Task tool execution |
| **System interruption** | Network, timeout | Rate limiting, connection loss |

### Claude Code - User Message Marker

**How it works:** Interruptions are recorded as a special user message.

**Format:**
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [{"type": "text", "text": "[Request interrupted by user]"}]
  },
  "uuid": "3a7fb54f-a20b-4e93-92f1-21b64b16a22e",
  "parentUuid": "3120cb4d-5b73-4863-b297-e5a516755c44",
  "timestamp": "2025-11-13T16:46:19.955Z"
}
```

**Key Characteristics:**
- No dedicated `interrupted` field
- Recorded as literal text `[Request interrupted by user]`
- `parentUuid` links to the interrupted assistant message
- Timestamp captures exact interruption moment
- Often followed by `file-history-snapshot` (preserving file state)

**Tool Interruption Context:**
```
1. Assistant message with stop_reason: "tool_use"
2. Tool result for completed tools
3. Interruption message: [Request interrupted by user]
4. File-history snapshot
```

**Stop Reasons (from assistant messages):**

| `stop_reason` | Meaning |
|---------------|---------|
| `end_turn` | Normal completion |
| `tool_use` | Stopped to execute tool |
| `max_tokens` | Hit token limit |
| (absent after interruption) | Response was cut short |

### Codex CLI - Embedded in Content

**How it works:** Codex embeds interruption information in message content text.

**Example:**
```json
{
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "assistant",
    "content": [{
      "type": "output_text",
      "text": "Because we hit rate limiting and the transfer aborted, the rename never happened..."
    }]
  }
}
```

**Key Characteristics:**
- No dedicated interruption field
- Information embedded in content text ("aborted", "cancelled")
- Partial downloads preserved with `.download` suffix (rsync `--partial`)
- Must parse content text to detect interruptions

**Indicators Found:**
- "aborted" - Transfer/operation stopped
- "rate limiting" - API limits hit
- `.download` temporary files - Incomplete transfers

### Gemini CLI - Dedicated Info Message

**How it works:** Gemini uses explicit `info` type messages for cancellations.

**Format:**
```json
{
  "id": "afc23b55-d0d7-4e36-8e1c-a2bb96c39187",
  "timestamp": "2025-12-23T05:21:32.429Z",
  "type": "info",
  "content": "Request cancelled."
}
```

**Key Characteristics:**
- Dedicated `type: "info"` (not user/assistant)
- Clear content: `"Request cancelled."`
- Cleanest representation of the three agents
- No ambiguity - message type indicates system event

**Typical Flow:**
```json
{"type": "user", "content": "..."},
{"type": "gemini", "content": "...", "toolCalls": [...]},
{"type": "info", "content": "Request cancelled."},
{"type": "user", "content": "New request after interruption..."}
```

### Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Recording Method** | User message | Content text | Info message type |
| **Explicit Field** | No | No | Yes (`type: info`) |
| **Marker Text** | `[Request interrupted by user]` | "aborted", "cancelled" | `Request cancelled.` |
| **Parent Link** | Yes (`parentUuid`) | No | No |
| **Reason Recorded** | No (always "by user") | Inferred from context | No |
| **Partial State** | File-history snapshots | `.download` temp files | Not observed |
| **Structured** | Semi (special text) | No (parse content) | Yes (dedicated type) |

### Detecting Interruptions

**Claude Code:**
```python
def is_interruption(msg):
    if msg.get('type') == 'user':
        content = msg.get('message', {}).get('content', [])
        for block in content:
            if block.get('text') == '[Request interrupted by user]':
                return True
    return False
```

**Codex CLI:**
```python
def is_interruption(msg):
    content = msg.get('payload', {}).get('message', {}).get('content', [])
    for block in content:
        text = block.get('text', '').lower()
        if 'aborted' in text or 'cancelled' in text:
            return True
    return False
```

**Gemini CLI:**
```python
def is_interruption(msg):
    return msg.get('type') == 'info' and 'cancelled' in msg.get('content', '').lower()
```

---

## Rejections (Edit/Tool Declined)

Rejections occur when a user declines a proposed action - refusing a file edit, declining to run a command, or selecting "No" when asked.

### Types of Rejections

| Type | Example | User Action |
|------|---------|-------------|
| **Edit rejection** | Decline file modification | User doesn't accept diff |
| **Command rejection** | Decline Bash execution | User says "no" to command |
| **Option rejection** | Select alternative | User picks different choice |
| **Permission denial** | Block tool entirely | User denies tool permission |

### Claude Code - Explicit Rejection Recording

**How it works:** Rejections are recorded as `tool_result` messages with `is_error: true` and a specific phrase.

**Format:**
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01CCX4pcawRMsHndU7hn4d8K",
        "content": "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). To tell you how to proceed, the user said:\nHold.",
        "is_error": true
      }
    ]
  },
  "uuid": "3a7fb54f-a20b-4e93-92f1-21b64b16a22e",
  "parentUuid": "3120cb4d-5b73-4863-b297-e5a516755c44",
  "timestamp": "2025-12-03T10:30:00Z"
}
```

**Key Characteristics:**
- `is_error: true` marks as rejection/error
- Content contains literal: `"The user doesn't want to proceed with this tool use. The tool use was rejected"`
- User's stated reason follows: `"To tell you how to proceed, the user said:\n[REASON]"`
- `tool_use_id` links to the rejected tool request
- Recorded as `user` message (the rejection comes from user)

**Real Examples Found:**
- `"Hold."` - User pausing
- `"Don't have to update the pre-commit code so that it's generated every time"` - User declining change
- `"Will this technique work in GitHub CI?"` - User questioning before proceeding

### Distinguishing Rejections vs Errors

Both use `is_error: true`, but content differs:

| Type | Content Pattern | Example |
|------|-----------------|---------|
| **User rejection** | `"The user doesn't want to proceed..."` | Declined edit |
| **Tool error** | Exit codes, error messages | `"Exit code 128\nfatal: ..."` |
| **Tool use error** | `"<tool_use_error>..."` | Invalid parameters |
| **Interrupted** | `"Interrupted by user"` or exit 130/137 | Ctrl+C during execution |

**Detection Code:**
```python
def is_user_rejection(content_text):
    return "The user doesn't want to proceed with this tool use" in content_text

def is_tool_error(content_text):
    return (
        content_text.startswith("Exit code") or
        "<tool_use_error>" in content_text or
        "error:" in content_text.lower()
    )
```

### What's Preserved vs Lost

**Preserved:**
- `tool_use_id` - Can link to original request
- User's exact reason/comment
- Timestamp of rejection
- Message metadata (uuid, parentUuid)

**NOT Preserved in rejection message:**
- Original tool parameters (must find in preceding assistant message)
- Proposed file content/diff that was rejected
- The change that would have been made

**To reconstruct rejected edit:**
1. Get `tool_use_id` from rejection
2. Search backward for assistant message with matching tool_use
3. Extract `input` parameters (old_string, new_string, file_path)

### Codex CLI - Limited Evidence

**Observations:**
- Main history.jsonl contains only user queries
- Session rollout files may contain rejection data
- No explicit rejection field found in samples

**Possible indicators:**
- Response text mentioning user declining
- Status fields in tool results

### Gemini CLI - No Explicit Rejection Field

**Observations:**
- Tool calls include `result` field
- No `is_error` equivalent found
- May use `status` field (needs more investigation)

**Structure:**
```json
{
  "type": "gemini",
  "toolCalls": [
    {
      "name": "edit_file",
      "args": {...},
      "result": [...]
    }
  ]
}
```

### Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Explicit rejection** | Yes | Unknown | Unknown |
| **Rejection field** | `is_error: true` + phrase | Not found | Not found |
| **User reason** | Full text captured | Unknown | Unknown |
| **Tool ID link** | Yes (`tool_use_id`) | Unknown | Yes (in toolCalls) |
| **Distinguishable** | Yes (phrase-based) | Unknown | Unknown |

### Detecting Rejections

**Claude Code:**
```python
def is_rejection(msg):
    if msg.get('type') != 'user':
        return False
    content = msg.get('message', {}).get('content', [])
    for block in content:
        if block.get('type') == 'tool_result' and block.get('is_error'):
            text = block.get('content', '')
            if "The user doesn't want to proceed" in text:
                return True
    return False

def get_rejection_reason(msg):
    content = msg.get('message', {}).get('content', [])
    for block in content:
        if block.get('type') == 'tool_result':
            text = block.get('content', '')
            if "the user said:" in text.lower():
                # Extract text after "the user said:\n"
                parts = text.split("the user said:\n", 1)
                if len(parts) > 1:
                    return parts[1].strip()
    return None

def get_rejected_tool_id(msg):
    content = msg.get('message', {}).get('content', [])
    for block in content:
        if block.get('type') == 'tool_result' and block.get('is_error'):
            return block.get('tool_use_id')
    return None
```

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
| **Interruption Recording** | User message marker | Content text | Info message type |
| **Interruption in Session** | Yes | Yes | Yes |
| **Rejection Recording** | `is_error` + phrase | Unknown | Unknown |
| **Rejection in Session** | Yes | Unknown | Unknown |
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
  ],
  "interruptions": [
    {
      "message_index": 15,
      "interrupted_message_index": 14,
      "timestamp": "2025-12-27T10:30:00Z",
      "type": "user"
    }
  ],
  "rejections": [
    {
      "message_index": 20,
      "tool_use_id": "toolu_01CCX4pcawRMsHndU7hn4d8K",
      "tool_name": "Edit",
      "reason": "Hold.",
      "timestamp": "2025-12-27T10:35:00Z"
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

### Field Mapping - Interruptions

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `message_index` | Index of interruption message | Index of message with "aborted" | Index of `type: info` message |
| `interrupted_message_index` | Derived from `parentUuid` | Previous assistant message | Previous gemini message |
| `timestamp` | From interruption message | From message timestamp | From info message |
| `type` | Always `"user"` | Inferred (`"user"`, `"system"`) | Always `"user"` |

**Note:** Interruptions are recorded in session files, unlike context clears. Detection methods vary by agent (see detection code above).

### Field Mapping - Rejections

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `message_index` | Index of rejection message | Unknown | Unknown |
| `tool_use_id` | From `tool_result.tool_use_id` | Unknown | From `toolCalls[].id` |
| `tool_name` | Lookup from original tool_use | Unknown | From `toolCalls[].name` |
| `reason` | Parsed from content after "the user said:" | Unknown | Unknown |
| `timestamp` | From rejection message | Unknown | Unknown |

**Note:** Claude Code is the only agent with explicit, parseable rejection recording. Reconstructing the rejected action requires linking `tool_use_id` back to the original assistant message.

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

### Interruptions

7. **Should we normalize interruption representation?**
   - Claude uses special text in user message
   - Codex embeds in content (requires parsing)
   - Gemini has dedicated message type
   - Unified schema could use dedicated `interruption` content block type

8. **How to handle partial tool results?**
   - Interrupted Bash may have partial stdout
   - `toolUseResult.interrupted: true` field exists in Claude Code
   - Should we preserve partial output separately?

9. **Should interruptions be content blocks or session metadata?**
   - Option A: `interruptions` array at session level (current proposal)
   - Option B: `type: "interruption"` content block in messages
   - Option C: Both (redundant but complete)

### Rejections

10. **Should we include the rejected action details?**
    - Currently only `tool_use_id` is in rejection message
    - Original tool parameters require backward search
    - Should unified schema inline the rejected action?

11. **How to distinguish rejection types?**
    - Edit rejection vs command rejection vs option rejection
    - Currently all use same `is_error: true` mechanism
    - Should we add a `rejection_type` field?

12. **Should rejected content be preserved?**
    - For Edit tool: the `old_string`/`new_string` that wasn't applied
    - For Bash: the command that wasn't run
    - Enables "what-if" analysis and rejection review

13. **How to handle Codex/Gemini rejections?**
    - Limited evidence of explicit rejection recording
    - May need to infer from response patterns
    - Should unified schema have optional/nullable rejection fields?

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
