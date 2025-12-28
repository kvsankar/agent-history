# Claude Code JSONL Format Analysis

This document captures our understanding of the `.jsonl` files created by Claude Code, based on empirical analysis of actual conversation data.

> **Note**: This is reverse-engineered documentation based on observation. Claude Code's internal format may change without notice.

## Table of Contents

1. [File Organization](#file-organization)
2. [Record Types](#record-types)
3. [Timestamps](#timestamps)
4. [Session and Agent Relationships](#session-and-agent-relationships)
5. [Time Tracking Analysis](#time-tracking-analysis)
6. [Message Content Structure](#message-content-structure)
7. [Token Usage](#token-usage)

---

## File Organization

### Storage Location

Claude Code stores conversation data in:
```
~/.claude/projects/<encoded-workspace-name>/
```

Where `<encoded-workspace-name>` is the workspace path with:
- Leading `/` replaced with `-`
- All `/` replaced with `-`
- On Windows: `C:\Users\alice\project` becomes `C--Users-alice-project`

### File Types

| Pattern | Description |
|---------|-------------|
| `<uuid>.jsonl` | Main conversation session |
| `agent-<short-id>.jsonl` | Task agent (spawned by main session) |

Example:
```
~/.claude/projects/-home-alice-myproject/
├── 6c073d8e-2bb1-45cb-90bc-a28ce44da090.jsonl  (main session)
├── agent-d2969342.jsonl                         (task agent)
└── agent-8e57872d.jsonl                         (task agent)
```

---

## Record Types

Each line in a JSONL file is a JSON object with a `type` field:

### `user`

User message (human input).

```json
{
  "type": "user",
  "uuid": "abc123...",
  "parentUuid": "def456...",
  "sessionId": "6c073d8e-...",
  "timestamp": "2025-11-30T11:09:33.123Z",
  "cwd": "/home/alice/myproject",
  "gitBranch": "main",
  "version": "2.0.55",
  "message": {
    "role": "user",
    "content": "Help me fix this bug"
  }
}
```

### `assistant`

Claude's response.

```json
{
  "type": "assistant",
  "uuid": "xyz789...",
  "parentUuid": "abc123...",
  "sessionId": "6c073d8e-...",
  "timestamp": "2025-11-30T11:09:37.456Z",
  "requestId": "req_011CVc...",
  "message": {
    "id": "msg_01Pfp...",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-4-5-20250929",
    "content": [...],
    "stop_reason": "end_turn",
    "usage": {
      "input_tokens": 1234,
      "output_tokens": 567,
      "cache_creation_input_tokens": 0,
      "cache_read_input_tokens": 890
    }
  }
}
```

### `summary`

Compacted conversation history. When a conversation gets too long, Claude Code compacts older messages into summaries.

```json
{
  "type": "summary",
  "summary": "The user asked about...",
  "leafUuids": ["uuid1", "uuid2", ...]
}
```

**Important**: Summary records do NOT have timestamps.

### `file-history-snapshot`

Captures file state at a point in time (for context restoration).

```json
{
  "type": "file-history-snapshot",
  "files": [
    {"path": "/home/alice/file.py", "content": "..."}
  ]
}
```

**Important**: File history snapshots do NOT have timestamps.

### `queue-operation`

Internal queue management (observed but not fully understood).

```json
{
  "type": "queue-operation",
  "timestamp": "2025-11-01T15:35:20.123Z",
  ...
}
```

---

### Supported Record Types in agent-history

| Type | Status | Notes |
|------|--------|-------|
| `user` | ✅ Supported | User messages parsed and exported |
| `assistant` | ✅ Supported | Assistant messages parsed and exported |
| `summary` | ? Not handled | Compacted conversation summaries |
| `file-history-snapshot` | ? Not handled | File state snapshots |
| `queue-operation` | ? Not handled | Internal queue events |

## Timestamps

### Availability by Record Type

| Record Type | Has Timestamp |
|-------------|---------------|
| `user` | ✅ Always |
| `assistant` | ✅ Always |
| `summary` | ❌ Never |
| `file-history-snapshot` | ❌ Never |
| `queue-operation` | ✅ Sometimes |

### Format

ISO 8601 with milliseconds and UTC timezone:
```
2025-11-30T11:09:33.123Z
```

### What Timestamps Represent

- **User messages**: When the message was submitted (user hit Enter)
- **Assistant messages**: When Claude's response was recorded (streaming start or chunk)

### Timestamp Ordering

**Important**: Timestamps in JSONL files are NOT always in chronological order.

```
Example from session de7af46c (2759 messages):
  Message 2732: 2025-11-10T08:59:16
  Message 2733: 2025-11-07T13:11:36  ← Goes BACK in time!
```

This can happen due to:
- **Context restoration**: Old messages injected back into the conversation
- **Summary expansion**: Compacted history being restored
- **Async writes**: Messages written out of order

**Implication**: When processing timestamps, always sort them first rather than assuming file order equals chronological order.

### Gaps and Work Sessions

Conversations often span days or weeks with large gaps:

```
Example session spanning 173 hours with 6 gaps > 1 hour:

Messages 79-81:  2025-11-23T03:25:24-25 (assistant)
                 --- 2.1 hour gap ---
Messages 82-84:  2025-11-23T05:30:54-55 (user)
                 ...
Messages 247-249: 2025-11-23T08:13:14-30
                 --- 143 hour gap (6 days!) ---
Messages 250-252: 2025-11-29T07:13:53-58
```

**Pattern observed at gap boundaries:**
- End of work period: Always ends with `assistant` message
- Start of work period: Always begins with `user` message

This makes sense: you leave after Claude responds, you return and type something.

---

## Session and Agent Relationships

### Session ID

All files belonging to the same conversation share a `sessionId`:

```
Main session file: 6c073d8e-2bb1-45cb-90bc-a28ce44da090.jsonl
                   sessionId: "6c073d8e-2bb1-45cb-90bc-a28ce44da090"

Agent file:        agent-d2969342.jsonl
                   sessionId: "6c073d8e-2bb1-45cb-90bc-a28ce44da090"  (same!)
                   agentId: "d2969342"
```

### Agent Identification

Agent files have additional fields:
- `isSidechain`: `true`
- `agentId`: Short identifier (e.g., "d2969342")
- `userType`: Often "external"

### Concurrent Agents

Multiple agents can run simultaneously:

```
Session 61537990:
  agent-a0d51cb6: 16:29:31 - 16:29:35  (4 seconds)
  agent-632229be: 16:29:31 - 16:29:38  (7 seconds)  ← Same start time!
  main session:   16:30:46 - 17:15:30  (45 minutes)
```

### Timing Anomaly: Agents Before Main Session

We observed agents starting BEFORE the main session's first recorded timestamp:

```
Session 142ea155:
  Agents started:    2025-11-01T15:34:50
  Main session start: 2025-11-01T15:35:20  (30 seconds later!)
```

Possible explanations:
1. Main session's early messages were compacted (summaries don't preserve timestamps)
2. Async write behavior - agents write faster than main session
3. Session ID reuse across Claude Code restarts

**Implication**: To get true session start time, must check minimum timestamp across ALL files with same sessionId.

---

## Time Tracking Analysis

### Definitions

**Calendar Time (Wall Clock)**
- Simple: `last_timestamp - first_timestamp` of main session
- Problem: Includes all breaks, sleep, weekends
- Example: A session spanning 256 hours includes 227 hours of gaps

**Effort Time**
- Sum of actual working periods, excluding gaps
- Must define "gap threshold" (e.g., 30 minutes of inactivity = break)

**Concurrent Effort**
- When agents run in parallel, their time adds up separately
- Two agents running for 5 seconds each = 10 seconds of effort

### Work Period Detection

Work periods can be detected by analyzing gaps:

```python
# Pseudocode
threshold = 30 * 60  # 30 minutes

work_periods = []
period_start = messages[0].timestamp

for i in range(1, len(messages)):
    gap = messages[i].timestamp - messages[i-1].timestamp
    if gap > threshold:
        # End current period, start new one
        work_periods.append((period_start, messages[i-1].timestamp))
        period_start = messages[i].timestamp

# Don't forget last period
work_periods.append((period_start, messages[-1].timestamp))
```

**Edge characteristics:**
- Period END: Last message before gap is always `assistant`
- Period START: First message after gap is always `user`

### Multi-File Time Calculation

For a session with main + agents:

**Simple Approach (per-file)**
```
main_duration = main.last_ts - main.first_ts
agent1_duration = agent1.last_ts - agent1.first_ts
agent2_duration = agent2.last_ts - agent2.first_ts

total_effort = main_duration + agent1_duration + agent2_duration
```

**Complex Approach (unified timeline)**
1. Merge all timestamps from all files
2. Sort chronologically
3. Apply gap detection across unified timeline
4. Handle overlapping agents (count parallel time once for calendar, separately for effort)

### Example Calculation

```
Session with overlapping agents:

Main:   |=================45 min==================|
Agent1:     |--4s--|
Agent2:     |---7s---|

Calendar time: 45 minutes (main session span)
Simple effort: 45min + 4s + 7s = 45min 11s
Unified effort: 45min + 7s = 45min 7s (agents overlap, count longest)
```

---

## Message Content Structure

### User Message Content

Usually a simple string:
```json
{
  "message": {
    "role": "user",
    "content": "Help me fix this bug"
  }
}
```

### Assistant Message Content

Array of content blocks:

```json
{
  "message": {
    "role": "assistant",
    "content": [
      {
        "type": "text",
        "text": "I'll help you fix that bug..."
      },
      {
        "type": "tool_use",
        "id": "toolu_01ABC...",
        "name": "Read",
        "input": {
          "file_path": "/home/alice/file.py"
        }
      },
      {
        "type": "tool_result",
        "tool_use_id": "toolu_01ABC...",
        "content": "file contents here..."
      }
    ]
  }
}
```

### Tool Use Types

| Tool Name | Purpose |
|-----------|---------|
| `Read` | Read file contents |
| `Write` | Create/overwrite file |
| `Edit` | Modify existing file |
| `Bash` | Execute shell command |
| `Glob` | Find files by pattern |
| `Grep` | Search file contents |
| `Task` | Spawn sub-agent |
| `WebFetch` | Fetch URL content |
| `WebSearch` | Search the web |
| `TodoWrite` | Update task list |
| `AskUserQuestion` | Interactive prompt |

---

## Token Usage

Assistant messages include token counts:

```json
{
  "usage": {
    "input_tokens": 1234,
    "output_tokens": 567,
    "cache_creation_input_tokens": 100,
    "cache_read_input_tokens": 890
  }
}
```

### Token Types

| Field | Description |
|-------|-------------|
| `input_tokens` | Tokens in the prompt |
| `output_tokens` | Tokens in Claude's response |
| `cache_creation_input_tokens` | Tokens written to cache |
| `cache_read_input_tokens` | Tokens read from cache (saves cost) |

### Cache Efficiency

Cache hit ratio indicates prompt caching effectiveness:
```
cache_hit_ratio = cache_read / (cache_creation + cache_read)
```

High ratio (>80%) means good cache utilization - similar prompts being reused.

---

## Files Without Messages

Some JSONL files contain only metadata (no user/assistant messages):

```
d544e57d-a7f2-4ec3-8a1a-475b3ab5f6a8.jsonl:
  6 records, all type=file-history-snapshot
  No timestamps, no messages
```

These represent sessions where Claude Code was opened but no conversation occurred (only file snapshots were taken).

---

## Time Tracking Comparison

Analysis of 402 sessions comparing different time measurement approaches:

### Definitions

| Metric | Definition |
|--------|------------|
| **Calendar Time** | `max(timestamp) - min(timestamp)` across all files in session |
| **Simple Effort** | Sum of `(max - min)` per file (main + agents) |
| **Work Period Effort** | Sum of active periods, excluding gaps > 30 minutes |

### Results

```
Total sessions analyzed: 402

Calendar Time (wall clock):           101.8 days
Simple Effort (per-file sum):          83.9 days
Work Period Effort (gap-aware):        11.2 days
Time in gaps (excluded):               72.8 days

Work Period / Simple ratio: 13.3%
Simple / Calendar ratio: 82.4%
WorkPeriod / Calendar ratio: 11.0%
```

### Key Findings

1. **Simple effort is ~84% of calendar time** - The difference is due to agents running concurrently (calendar counts once, simple counts each file)

2. **Work period effort is only ~13% of simple** - Most "session time" is actually idle gaps between work periods

3. **Sessions with most gap time:**
   ```
   a4bb3a6d: 14.1d gap time (76% of simple duration), 70 work periods
   dc940738: 10.5d gap time (98% of simple duration), 5 work periods
   c7e6fbcb:  7.5d gap time (96% of simple duration), 5 work periods
   ```

4. **Gap threshold sensitivity**: Using 30-minute threshold. Shorter thresholds would count more time as "work" but might include coffee breaks.

### Recommendation

- **For billing/cost analysis**: Use "Work Period Effort" as it represents actual active time
- **For productivity metrics**: Use "Simple Effort" as it includes concurrent agent work
- **For duration display**: Use "Calendar Time" to show when the conversation spanned

---

## Summary Statistics

From analysis of real data:

| Metric | Observed Range |
|--------|----------------|
| Session span | Minutes to 442+ hours (18+ days) |
| Messages per session | 1 to 35,000+ |
| Gaps within session | 0 to 70+ work periods |
| Largest single gap | 227 hours (9+ days) |
| Agents per session | 0 to 50+ |
| Concurrent agents | Up to 2+ observed |

---

## Changelog

- **2025-11-30**: Initial documentation based on empirical analysis
