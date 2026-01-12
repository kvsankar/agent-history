# Unified NDJSON Schema (Current Implementation)

This document describes the NDJSON emitted by `session export --json` in v2. The export writes **one NDJSON file per session**.

## File Format

- **Format:** NDJSON (newline-delimited JSON)
- **Extension:** `.ndjson`
- **Encoding:** UTF-8
- **Structure:**
  1. Header record
  2. Message records (one per message)
  3. Session summary record

### Example
```json
{"type":"header","schema_version":"2.0","agent":"claude","session_file":"550e8400.jsonl","workspace":"/home/user/myproject"}
{"type":"message","timestamp":"2025-01-03T10:15:00Z","role":"user","content":"Hello"}
{"type":"message","timestamp":"2025-01-03T10:15:05Z","role":"assistant","content":"Hi there"}
{"type":"session","agent":"claude","session_id":"","message_count":2,"workspace":"/home/user/myproject","forks":{"fork_points":["fa1-fork"],"branches":[{"fork_uuid":"fa1-fork","fork_timestamp":"2025-12-10T09:00:10.000Z","fork_type":"assistant","branches":[{"uuid":"fu2a-fork","timestamp":"2025-12-10T09:00:20.000Z","type":"user"}]}]}}
```

---

## Header Record

```json
{
  "type": "header",
  "schema_version": "2.0",
  "agent": "claude",
  "session_file": "550e8400.jsonl",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "workspace": "/home/user/myproject"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"header"` |
| `schema_version` | string | Yes | Schema version (currently `2.0`) |
| `agent` | string | Yes | Agent type: `claude`, `codex`, `gemini` |
| `session_file` | string | Yes | Source filename or path (from session metadata) |
| `session_id` | string | No | Session id if present in metadata |
| `workspace` | string | No | Human-readable workspace when available |

---

## Message Record

```json
{
  "type": "message",
  "timestamp": "2025-01-03T10:15:05Z",
  "role": "assistant",
  "content": "Hello",
  "model": "claude-3-5-sonnet",
  "tokens": {"input": 12, "output": 34, "cached": 0},
  "tool_calls": [{"name": "Read", "id": "toolu_01", "input": {"path": "README.md"}}]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"message"` |
| `timestamp` | string | No | ISO 8601 timestamp if present |
| `role` | string | Yes | Normalized role: `user`, `assistant`, `system` |
| `content` | string | Yes | Text content (tool results are serialized into content) |
| `model` | string | No | Claude model name if present |
| `tokens` | object | No | Claude usage totals (`input`, `output`, `cached`) |
| `tool_calls` | array | No | Claude tool use blocks (name/id/input) |

Notes:
- Codex and Gemini currently emit only `timestamp`, `role`, and `content`.
- `tokens.cached` corresponds to Claude cache read tokens when present.

---

## Session Record

```json
{
  "type": "session",
  "agent": "claude",
  "session_id": "",
  "message_count": 127,
  "workspace": "/home/user/myproject"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"session"` |
| `agent` | string | Yes | Agent type: `claude`, `codex`, `gemini` |
| `session_id` | string | Yes | Session id or empty string if unknown |
| `message_count` | int | Yes | Number of messages in the file |
| `workspace` | string | Yes | Workspace name (human-readable when available) |
| `forks` | object | No | Fork metadata when Claude sessions branch |

---

## Notes

- NDJSON output is **per-session**, not a multi-session export file.
- The unified schema is intentionally minimal and reflects current export behavior.
- Fork metadata is only emitted for Claude sessions that include parent/uuid fields.
