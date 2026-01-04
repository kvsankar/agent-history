# Interruption Analysis

How Claude Code, Codex CLI, and Gemini CLI record user and system interruptions.

## Summary

| Agent | How Recorded | Field/Marker | In Session File? |
|-------|--------------|--------------|------------------|
| Claude Code | User message | `[Request interrupted by user]` | Yes |
| Codex CLI | Event message | `type: "turn_aborted"`, `reason: "interrupted"` | Yes |
| Gemini CLI | Info message | `type: "info"`, `content: "Request cancelled."` | Yes |

**Key Finding:** Unlike context clearing, interruptions ARE recorded in session files. Each agent uses a different approach.

---

## Types of Interruptions

| Type | Trigger | Example |
|------|---------|---------|
| **User interrupts response** | Escape key, Ctrl+C | User stops assistant mid-generation |
| **User interrupts tool** | Ctrl+C during execution | User stops long-running Bash command |
| **User interrupts agent** | Escape during subagent | User cancels Task tool execution |
| **System interruption** | Network, timeout | Rate limiting, connection loss |

---

## Claude Code - User Message Marker

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

---

## Codex CLI - Dedicated Event Message

**How it works:** Codex uses a dedicated `turn_aborted` event type for interruptions.

**Format:**
```json
{
  "timestamp": "2025-12-03T15:24:46.622Z",
  "type": "event_msg",
  "payload": {
    "type": "turn_aborted",
    "reason": "interrupted"
  }
}
```

**Key Characteristics:**
- Dedicated `event_msg` with `payload.type: "turn_aborted"`
- `reason` field indicates cause (`"interrupted"` for user interruption)
- Clean, structured representation
- No need to parse content text - explicit message type

**Detection:**
- Look for `type: "event_msg"` with `payload.type: "turn_aborted"`
- `reason: "interrupted"` indicates user-initiated interruption

---

## Gemini CLI - Dedicated Info Message

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

---

## Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Recording Method** | User message | Event message | Info message type |
| **Explicit Field** | No | Yes (`turn_aborted`) | Yes (`type: info`) |
| **Marker Text** | `[Request interrupted by user]` | `reason: "interrupted"` | `Request cancelled.` |
| **Parent Link** | Yes (`parentUuid`) | No | No |
| **Reason Recorded** | No (always "by user") | Yes (`reason` field) | No |
| **Partial State** | File-history snapshots | Not observed | Not observed |
| **Structured** | Semi (special text) | Yes (dedicated event) | Yes (dedicated type) |

---

## Detection Code

### Claude Code

```python
def is_interruption(msg):
    if msg.get('type') == 'user':
        content = msg.get('message', {}).get('content', [])
        for block in content:
            if block.get('text') == '[Request interrupted by user]':
                return True
    return False
```

### Codex CLI

```python
def is_interruption(msg):
    if msg.get('type') == 'event_msg':
        payload = msg.get('payload', {})
        if payload.get('type') == 'turn_aborted':
            return True
    return False

def get_interruption_reason(msg):
    if is_interruption(msg):
        return msg.get('payload', {}).get('reason', 'unknown')
    return None
```

### Gemini CLI

```python
def is_interruption(msg):
    return msg.get('type') == 'info' and 'cancelled' in msg.get('content', '').lower()
```

---

## Schema Implications

### Proposed Schema Addition

```json
{
  "type": "session",
  "session": {...},
  "messages": [...],
  "interruptions": [
    {
      "message_index": 15,
      "interrupted_message_index": 14,
      "timestamp": "2025-12-27T10:30:00Z",
      "type": "user"
    }
  ]
}
```

### Field Mapping

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `message_index` | Index of interruption message | Index of `turn_aborted` event | Index of `type: info` message |
| `interrupted_message_index` | Derived from `parentUuid` | Previous response item | Previous gemini message |
| `timestamp` | From interruption message | From event timestamp | From info message |
| `type` | Always `"user"` | From `payload.reason` | Always `"user"` |

**Note:** Interruptions are recorded in session files, unlike context clears. Detection methods vary by agent (see detection code above).

---

## Open Questions

1. **Should we normalize interruption representation?**
   - Claude uses special text in user message (`[Request interrupted by user]`)
   - Codex uses dedicated event type (`turn_aborted`)
   - Gemini uses dedicated info message type
   - Unified schema could use dedicated `interruption` content block type

2. **How to handle partial tool results?**
   - Interrupted Bash may have partial stdout
   - `toolUseResult.interrupted: true` field exists in Claude Code
   - Should we preserve partial output separately?

3. **Should interruptions be content blocks or session metadata?**
   - Option A: `interruptions` array at session level (current proposal)
   - Option B: `type: "interruption"` content block in messages
   - Option C: Both (redundant but complete)

---

## Data Locations

```
Claude Code:
  Session files:     ~/.claude/projects/<workspace>/<session>.jsonl
  (Interruptions recorded inline in session files)

Codex CLI:
  Session files:     ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
  (Interruptions as type: "event_msg" with payload.type: "turn_aborted")

Gemini CLI:
  Session files:     ~/.gemini/tmp/<project-hash>/chats/session-*.json
  (Interruptions as type: "info" messages)
```
