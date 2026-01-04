# Codex CLI JSONL Format

This document describes the session storage format used by OpenAI's Codex CLI.

> **Status**: Verified - format confirmed from source code (December 2025). See [Sources](#sources) for authoritative references.

## Table of Contents

1. [File Organization](#file-organization)
2. [Record Types](#record-types)
3. [Message Content Structure](#message-content-structure)
4. [Comparison with Claude Code](#comparison-with-claude-code)

---

## File Organization

### Storage Location

Codex CLI stores session data in a date-based hierarchy:

```
~/.codex/sessions/
├── 2025/
│   ├── 01/
│   │   ├── 15/
│   │   │   └── rollout-session-id-1.jsonl
│   │   └── 16/
│   │       └── rollout-session-id-2.jsonl
│   └── 12/
│       └── 08/
│           └── rollout-2025-12-08T00-37-46-abc123.jsonl
```

### File Naming

Files follow the pattern: `rollout-<session-identifier>.jsonl`

The session identifier typically includes a timestamp and unique ID.

### Environment Variable Override

The tool supports `CODEX_SESSIONS_DIR` environment variable to override the default location (useful for testing).

---

## Record Types

Each line in a JSONL file is a JSON object with a `type` field in the root and a `payload` containing the actual data.

### `session_meta`

Session metadata, typically the first record.

```json
{
  "timestamp": "2025-12-08T00:37:46.102Z",
  "type": "session_meta",
  "payload": {
    "id": "unique-session-id",
    "timestamp": "2025-12-24T00:56:59.223Z",
    "cwd": "/home/user/project",
    "originator": "codex_cli_rs",
    "cli_version": "0.77.0",
    "instructions": "# Repository Guidelines\n\n## Project Structure...",
    "source": "cli",
    "model_provider": "openai",
    "git": {
      "commit_hash": "0e3689aea549c3d3cf87ba8d606e0802089b939d",
      "branch": "master"
    }
  }
}
```

**Session Meta Fields:**

| Field | Description |
|-------|-------------|
| `id` | Unique session identifier |
| `cwd` | Working directory |
| `originator` | Client identifier (e.g., "codex_cli_rs") |
| `cli_version` | CLI version (e.g., "0.77.0") |
| `instructions` | Full agent instructions (from AGENTS.md, etc.) |
| `source` | Session source (e.g., "cli") |
| `model_provider` | Model provider (e.g., "openai") |
| `git.commit_hash` | Current git commit |
| `git.branch` | Current git branch |

### `turn_context`

Model and context information for a turn.

```json
{
  "timestamp": "2025-12-08T00:38:00.000Z",
  "type": "turn_context",
  "payload": {
    "cwd": "/home/user/project",
    "approval_policy": "on-request",
    "sandbox_policy": {
      "type": "workspace-write",
      "network_access": false,
      "exclude_tmpdir_env_var": false,
      "exclude_slash_tmp": false
    },
    "model": "gpt-5.1-codex-max",
    "effort": "high",
    "summary": "auto"
  }
}
```

**Turn Context Fields:**

| Field | Description |
|-------|-------------|
| `approval_policy` | Tool approval policy (e.g., "on-request") |
| `sandbox_policy.type` | Sandbox type (e.g., "workspace-write") |
| `sandbox_policy.network_access` | Whether network access is allowed |
| `model` | Model identifier (e.g., "gpt-5.1-codex-max") |
| `effort` | Effort level (e.g., "high") |
| `summary` | Summary mode (e.g., "auto") |

### `response_item`

Messages, tool calls, and tool results. The `payload.type` field determines the content type.

#### User Message

```json
{
  "timestamp": "2025-12-08T00:39:54.852Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "user",
    "content": [
      {"type": "input_text", "text": "Hello, can you help me?"}
    ]
  }
}
```

#### Assistant Message

```json
{
  "timestamp": "2025-12-08T00:40:05.000Z",
  "type": "response_item",
  "payload": {
    "type": "message",
    "role": "assistant",
    "content": [
      {"type": "output_text", "text": "Of course! How can I help?"}
    ]
  }
}
```

#### Function Call (Tool Use)

```json
{
  "timestamp": "2025-12-08T00:39:59.538Z",
  "type": "response_item",
  "payload": {
    "type": "function_call",
    "name": "shell",
    "arguments": "{\"command\": \"ls -la\"}",
    "call_id": "call_abc123"
  }
}
```

Alternative types: `custom_tool_call`

#### Function Call Output (Tool Result)

```json
{
  "timestamp": "2025-12-08T00:40:00.000Z",
  "type": "response_item",
  "payload": {
    "type": "function_call_output",
    "call_id": "call_abc123",
    "output": "total 0\ndrwxr-xr-x 2 user user 40 Jan 15 10:00 ."
  }
}
```

Alternative types: `custom_tool_call_output`

#### Reasoning (Extended Thinking)

```json
{
  "timestamp": "2025-12-24T00:56:59.252Z",
  "type": "response_item",
  "payload": {
    "type": "reasoning",
    "summary": [
      {
        "type": "summary_text",
        "text": "**Preparing to explore repo files**"
      }
    ],
    "content": null,
    "encrypted_content": "gAAAAABpSi4X1CPuupBD..."
  }
}
```

**Reasoning Fields:**

| Field | Description |
|-------|-------------|
| `summary` | Array of summary_text items (visible to user) |
| `content` | Plain text reasoning (if not encrypted) |
| `encrypted_content` | Encrypted reasoning content |

#### Ghost Snapshot (Git State)

```json
{
  "timestamp": "2025-12-24T00:56:59.251Z",
  "type": "response_item",
  "payload": {
    "type": "ghost_snapshot",
    "ghost_commit": {
      "id": "dac072223e6110f2adebe4d63761120cd347fcc4",
      "parent": "b92c69c4528558916336cdd0c885c7bff3b47bf6",
      "preexisting_untracked_files": ["specs.md"],
      "preexisting_untracked_dirs": []
    }
  }
}
```

**Ghost Snapshot Fields:**

| Field | Description |
|-------|-------------|
| `ghost_commit.id` | Virtual commit ID for this state |
| `ghost_commit.parent` | Parent commit hash |
| `preexisting_untracked_files` | Untracked files present before session |
| `preexisting_untracked_dirs` | Untracked directories present before session |

### `event_msg`

Event messages for various session events. The `payload.type` field determines the event type.

#### Token Count

Token usage snapshots.

```json
{
  "timestamp": "2025-12-19T06:33:36.601Z",
  "type": "event_msg",
  "payload": {
    "type": "token_count",
    "info": {
      "total_token_usage": {
        "input_tokens": 124314,
        "cached_input_tokens": 120960,
        "output_tokens": 552,
        "reasoning_output_tokens": 384,
        "total_tokens": 124866
      },
      "last_token_usage": {
        "input_tokens": 63284,
        "cached_input_tokens": 61056,
        "output_tokens": 380,
        "reasoning_output_tokens": 256,
        "total_tokens": 63664
      },
      "model_context_window": 258400
    }
  }
}
```

Notes:
- `total_token_usage` is cumulative for the session.
- `cached_input_tokens` reflects cache read tokens.
- `reasoning_output_tokens` is counted as output in stats.

#### Agent Reasoning

Displayed reasoning text from the model.

```json
{
  "timestamp": "2025-12-24T00:56:59.252Z",
  "type": "event_msg",
  "payload": {
    "type": "agent_reasoning",
    "text": "**Preparing to explore repo files**"
  }
}
```

#### User Message Event

Records user input as an event.

```json
{
  "timestamp": "2025-12-24T00:56:59.252Z",
  "type": "event_msg",
  "payload": {
    "type": "user_message",
    "message": "Read specs.md and fix any issues",
    "images": []
  }
}
```

#### Turn Aborted (Interruption)

Records when a turn is interrupted by the user.

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

#### Context Compacted

Records when context is compacted (distinct from top-level `compacted` type).

```json
{
  "timestamp": "2025-12-24T00:56:59.252Z",
  "type": "event_msg",
  "payload": {
    "type": "context_compacted"
  }
}
```

### `compacted`

Top-level compaction record with full summary.

```json
{
  "timestamp": "2025-10-28T05:26:42.667Z",
  "type": "compacted",
  "payload": {
    "message": "**Progress + Plan Status**\n- Completed X\n- In progress Y\n\n**Outstanding TODOs**\n- Task 1\n- Task 2\n\n**Testing Gaps**\n- Need tests for...\n\n**Open quirks / setup notes**\n- Note about..."
  }
}
```

**Compacted Fields:**

| Field | Description |
|-------|-------------|
| `payload.message` | Full markdown summary of compacted context |

---

## Message Content Structure

### User Content

User messages use `input_text` type:

```json
{
  "content": [
    {"type": "input_text", "text": "User's message here"}
  ]
}
```

### Assistant Content

Assistant messages use `output_text` type:

```json
{
  "content": [
    {"type": "output_text", "text": "Assistant's response here"}
  ]
}
```

Content can also be a simple string in some cases:

```json
{
  "content": "Simple string content"
}
```

---

## Comparison with Claude Code

| Aspect | Claude Code | Codex CLI |
|--------|-------------|-----------|
| **Location** | `~/.claude/projects/<workspace>/` | `~/.codex/sessions/YYYY/MM/DD/` |
| **File Format** | JSONL | JSONL |
| **Organization** | By workspace path | By date |
| **Type Field** | Top-level `type` | Top-level `type` + `payload.type` |
| **Session ID** | UUID in filename and records | In `session_meta.payload.id` |
| **Workspace** | Directory name encodes path | Extracted from `session_meta.payload.cwd` |
| **Model Info** | In assistant message | In `turn_context.payload.model` |
| **Tool Calls** | `tool_use` in content array | `function_call` as payload type |
| **Tool Results** | `tool_result` in content array | `function_call_output` as payload type |
| **Agent Files** | `agent-*.jsonl` for subagents | Single file per session |

### Key Differences

1. **Nesting**: Codex uses a two-level type system (`type` + `payload.type`), Claude uses single-level `type`.

2. **Content Types**: Codex uses `input_text`/`output_text`, Claude uses `text`.

3. **Tool Format**:
   - Claude: Tool calls embedded in message content array
   - Codex: Tool calls as separate response_item records

4. **Metadata Location**:
   - Claude: Metadata in each record (uuid, parentUuid, sessionId, etc.)
   - Codex: Session metadata in dedicated `session_meta` record

---

## Sources

- [Codex CLI GitHub Repository](https://github.com/openai/codex)
- [rollout/recorder.rs](https://github.com/openai/codex/blob/main/codex-rs/core/src/rollout/recorder.rs) - Session recording implementation
- [protocol/protocol.rs](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/protocol.rs) - RolloutLine, SessionMeta, TurnContext types
- [protocol/models.rs](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/models.rs) - ResponseItem, ContentItem types

---

## Changelog

- **2025-12-13**: Verified format from source code; added source references
- **2025-12-13**: Initial documentation based on implementation analysis
