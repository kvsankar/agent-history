# Rejection Analysis

How Claude Code, Codex CLI, and Gemini CLI record user rejections of edits, tools, and proposed actions.

## Summary

| Agent | How Recorded | Key Field | User Reason Captured? |
|-------|--------------|-----------|----------------------|
| Claude Code | tool_result with `is_error: true` | Content contains "user doesn't want to proceed" | Yes |
| Codex CLI | Unknown | Not found in samples | Unknown |
| Gemini CLI | Unknown | No explicit rejection field | Unknown |

**Key Finding:** Claude Code explicitly captures rejections with distinguishable markers. User's stated reason is preserved in full.

---

## Types of Rejections

| Type | Example | User Action |
|------|---------|-------------|
| **Edit rejection** | Decline file modification | User doesn't accept diff |
| **Command rejection** | Decline Bash execution | User says "no" to command |
| **Option rejection** | Select alternative | User picks different choice |
| **Permission denial** | Block tool entirely | User denies tool permission |

---

## Claude Code - Explicit Rejection Recording

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

---

## Distinguishing Rejections vs Errors

Both use `is_error: true`, but content differs:

| Type | Content Pattern | Example |
|------|-----------------|---------|
| **User rejection** | `"The user doesn't want to proceed..."` | Declined edit |
| **Tool error** | Exit codes, error messages | `"Exit code 128\nfatal: ..."` |
| **Tool use error** | `"<tool_use_error>..."` | Invalid parameters |
| **Interrupted** | `"Interrupted by user"` or exit 130/137 | Ctrl+C during execution |

---

## What's Preserved vs Lost

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

---

## Codex CLI - Limited Evidence

**Observations:**
- Main history.jsonl contains only user queries
- Session rollout files may contain rejection data
- No explicit rejection field found in samples

**Possible indicators:**
- Response text mentioning user declining
- Status fields in tool results

---

## Gemini CLI - No Explicit Rejection Field

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

---

## Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Explicit rejection** | Yes | Unknown | Unknown |
| **Rejection field** | `is_error: true` + phrase | Not found | Not found |
| **User reason** | Full text captured | Unknown | Unknown |
| **Tool ID link** | Yes (`tool_use_id`) | Unknown | Yes (in toolCalls) |
| **Distinguishable** | Yes (phrase-based) | Unknown | Unknown |

---

## Detection Code

### Claude Code

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

### Distinguishing Errors

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

---

## Schema Implications

### Proposed Schema Addition

```json
{
  "type": "session",
  "session": {...},
  "messages": [...],
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

### Field Mapping

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

1. **Should we include the rejected action details?**
   - Currently only `tool_use_id` is in rejection message
   - Original tool parameters require backward search
   - Should unified schema inline the rejected action?

2. **How to distinguish rejection types?**
   - Edit rejection vs command rejection vs option rejection
   - Currently all use same `is_error: true` mechanism
   - Should we add a `rejection_type` field?

3. **Should rejected content be preserved?**
   - For Edit tool: the `old_string`/`new_string` that wasn't applied
   - For Bash: the command that wasn't run
   - Enables "what-if" analysis and rejection review

4. **How to handle Codex/Gemini rejections?**
   - Limited evidence of explicit rejection recording
   - May need to infer from response patterns
   - Should unified schema have optional/nullable rejection fields?

---

## Data Locations

```
Claude Code:
  Session files:     ~/.claude/projects/<workspace>/<session>.jsonl
  (Rejections recorded inline as tool_result with is_error: true)

Codex CLI:
  Session files:     ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
  (No explicit rejection recording found)

Gemini CLI:
  Session files:     ~/.gemini/tmp/<project-hash>/chats/session-*.json
  (No explicit rejection recording found)
```
