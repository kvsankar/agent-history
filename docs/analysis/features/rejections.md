# Rejection Analysis

How Claude Code, Codex CLI, and Gemini CLI record user rejections of edits, tools, and proposed actions.

## Summary

| Agent | How Recorded | Key Field | User Reason Captured? |
|-------|--------------|-----------|----------------------|
| Claude Code | tool_result with `is_error: true` | Content contains "user doesn't want to proceed" | Yes |
| Codex CLI | **Not recorded** | Escalation request recorded, rejection not | No |
| Gemini CLI | Tool error status | `status: "error"` + `error` field | No (tool errors only) |

**Key Findings:**
- Claude Code explicitly captures rejections with distinguishable markers. User's stated reason is preserved in full.
- Codex CLI records escalation requests (`sandbox_permissions: "require_escalated"`) but NOT user rejection responses.
- Gemini CLI captures tool errors but not explicit user rejections.

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

## Codex CLI - Not Explicitly Recorded

> **Status**: Verified via pexpect testing (December 2025)

**Key Finding:** User rejections are NOT explicitly recorded in session files. Only the escalation request is recorded, not the user's response.

**Escalation Request Format (recorded):**
```json
{
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "shell_command",
    "arguments": {
      "command": "printf 'Goodbye World\\n' > test.txt",
      "sandbox_permissions": "require_escalated",
      "justification": "Need to write to test.txt but current sandbox is read-only; require escalated permissions to modify file content."
    },
    "call_id": "call_Mbwbrl6SUkeltbseyJcEhV3S"
  }
}
```

**What Happens on User Rejection:**
- The `function_call` with `sandbox_permissions: "require_escalated"` IS recorded
- If user rejects: NO `function_call_output` is recorded for that call_id
- The session ends or model adjusts behavior
- No explicit "rejected" or "denied" record type

**Contrast with Interruptions:**
Interruptions (Ctrl+C) ARE explicitly recorded:
```json
{
  "type": "event_msg",
  "payload": {
    "type": "turn_aborted",
    "reason": "interrupted"
  }
}
```

**Implications:**
- Cannot detect user rejections by looking for specific record types
- Must infer rejection by: `function_call` with `require_escalated` followed by no matching `function_call_output`
- User's rejection reason is never captured

---

## Gemini CLI - Tool Error Status

**How it works:** Gemini records tool errors using a `status` field in tool call results.

**Format:**
```json
{
  "type": "gemini",
  "toolCalls": [
    {
      "name": "edit_file",
      "args": {...},
      "result": [...],
      "status": "error",
      "error": "Failed to edit, 0 occurrences found for old_string (...). Original old_string was (...) in /path/to/file. No edits made. The exact text in old_string was not found."
    }
  ]
}
```

**Key Characteristics:**
- `status: "error"` marks failed tool execution
- `error` field contains detailed error message
- User rejections may not be distinguishable from tool failures
- More investigation needed to find explicit user rejection markers

**Observations:**
- Tool calls include `result` field
- `status` field indicates success/error
- `error` field provides detailed error message for failures

---

## Comparison

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Explicit rejection** | Yes | **No** | Partial (errors only) |
| **Rejection field** | `is_error: true` + phrase | None (not recorded) | `status: "error"` |
| **User reason** | Full text captured | Not captured | No (error message only) |
| **Tool ID link** | Yes (`tool_use_id`) | N/A | Yes (in toolCalls) |
| **Distinguishable** | Yes (phrase-based) | N/A | No (tool errors vs rejections) |
| **Escalation request** | N/A | Yes (`require_escalated`) | N/A |

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

### Gemini CLI

```python
def is_tool_error(msg):
    """Check if a Gemini message contains a tool error."""
    if msg.get('type') != 'gemini':
        return False
    for tool_call in msg.get('toolCalls', []):
        if tool_call.get('status') == 'error':
            return True
    return False

def get_tool_error(msg):
    """Get the error message from a failed tool call."""
    for tool_call in msg.get('toolCalls', []):
        if tool_call.get('status') == 'error':
            return tool_call.get('error', '')
    return None
```

**Note:** Gemini's `status: "error"` captures tool execution failures, but explicit user rejections (like declining an edit) may not be distinguishable from tool errors.

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
| `message_index` | Index of rejection message | Unknown | Index of message with error |
| `tool_use_id` | From `tool_result.tool_use_id` | Unknown | From `toolCalls[].id` |
| `tool_name` | Lookup from original tool_use | Unknown | From `toolCalls[].name` |
| `reason` | Parsed from content after "the user said:" | Unknown | From `error` field (tool error only) |
| `timestamp` | From rejection message | Unknown | From message timestamp |

**Note:** Claude Code is the only agent with explicit, parseable user rejection recording. Gemini captures tool errors but not explicit user rejections. Reconstructing the rejected action requires linking `tool_use_id` back to the original assistant message.

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
   - Codex: Limited evidence of explicit rejection recording
   - Gemini: Records tool errors (`status: "error"`) but not explicit user rejections
   - May need to infer user rejections from response patterns
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
  (Tool errors recorded with status: "error" and error field)
```
