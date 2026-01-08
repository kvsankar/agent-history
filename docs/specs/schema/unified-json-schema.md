# Unified NDJSON Schema for Agent History

This document describes the normalized NDJSON format used by `--json` export, providing a consistent, streamable structure across all supported AI coding assistants (Claude Code, Codex CLI, Gemini CLI).

## Design Principles

1. **Union approach**: Include ALL fields from ALL agents; agent-specific fields are optional
2. **Streamable**: NDJSON allows line-by-line processing without loading entire file
3. **Lossless**: Preserve all meaningful information from source formats
4. **Semantic coherence**: Related concepts unified under consistent naming
5. **Source fidelity**: Preserve original identifiers alongside derived values

## File Format

- **Format**: NDJSON (Newline Delimited JSON)
- **Extension**: `.ndjson`
- **Encoding**: UTF-8
- **Structure**: One JSON object per line

```
Line 1: Header (export metadata)
Line 2: Session record
Line 3: Session record
...
Line N: Session record
```

---

## Schema Overview

### Line Types

| Type | Description | Count |
|------|-------------|-------|
| `header` | Export metadata | Exactly 1 (first line) |
| `session` | Complete session with messages | 0 or more |

---

## Header Record

```json
{
  "type": "header",
  "schema_version": "2.0",
  "export_timestamp": "2025-12-27T10:30:00Z",
  "exporter_version": "1.0.0",
  "agent_types": ["claude-code", "codex", "gemini"],
  "homes": ["local", "wsl:Ubuntu", "remote:vm01"],
  "workspaces": ["myproject", "api-server"],
  "session_count": 42
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"header"` |
| `schema_version` | string | Yes | Schema version (semver) |
| `export_timestamp` | string | Yes | ISO 8601 timestamp of export |
| `exporter_version` | string | Yes | agent-history CLI version |
| `agent_types` | array | Yes | Agent types included: `claude-code`, `codex`, `gemini` |
| `homes` | array | Yes | Source homes included |
| `workspaces` | array | Yes | Workspace names included |
| `session_count` | int | Yes | Total sessions in file |

**Versioning:** `schema_version` is currently `2.0`. Increment this when backward-incompatible changes are introduced and document changes below.

### Version History

| Version | Notes |
|---------|-------|
| 2.0 | Current unified schema (header + session lines) |

---

## Session Record

```json
{
  "type": "session",
  "session": { ... },
  "messages": [ ... ],
  "graph": { ... }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | Yes | Always `"session"` |
| `session` | object | Yes | Session metadata |
| `messages` | array | Yes | Array of message objects |
| `graph` | object | No | Fork/branch info (only if conversation has branches) |

---

## Session Object

```json
{
  "id": "abc123-def456",
  "agent": "claude-code",
  "workspace": "/home/user/myproject",
  "workspace_encoded": "-home-user-myproject",
  "started_at": "2025-12-27T09:00:00Z",
  "ended_at": "2025-12-27T10:30:00Z",
  "source": {
    "type": "local",
    "host": null,
    "path": "/home/user/.claude/projects/-home-user-myproject/abc123.jsonl"
  },
  "is_agent_session": true,
  "parent_session_id": "parent-123",
  "slug": "silly-humming-cocke",
  "instructions": null,
  "model_provider": null,
  "cli_version": "2.0.75",
  "git": {
    "branch": "main",
    "commit_hash": "0e3689a"
  },
  "summary": null
}
```

### Session Fields

| Field | Type | Required | Agent | Description |
|-------|------|----------|-------|-------------|
| `id` | string | Yes | All | Unique session identifier |
| `agent` | string | Yes | All | `claude-code`, `codex`, or `gemini` |
| `workspace` | string | No | All | Human-readable workspace path (derived, may be null if unknown) |
| `workspace_encoded` | string | No | All | Raw identifier from source (null for Codex) |
| `started_at` | string | Yes | All | First message timestamp (ISO 8601) |
| `ended_at` | string | Yes | All | Last message timestamp (ISO 8601) |
| `source.type` | string | Yes | All | `local`, `wsl`, `windows`, `remote` |
| `source.host` | string | No | All | Remote hostname or WSL distro name |
| `source.path` | string | Yes | All | Original file path |
| `is_agent_session` | bool | No | Claude | Only present if `true` (sub-agent task) |
| `parent_session_id` | string | No | Claude | Parent session ID (only if `is_agent_session`) |
| `slug` | string | No | Claude | Human-readable session name |
| `instructions` | string | No | Codex | Full agent instructions from AGENTS.md |
| `model_provider` | string | No | Codex | Model provider (e.g., "openai") |
| `cli_version` | string | No | Claude, Codex | CLI version string |
| `git.branch` | string | No | Claude, Codex | Git branch at session start |
| `git.commit_hash` | string | No | Codex | Git commit hash at session start |
| `summary` | string | No | Claude, Gemini | Session summary |

### Workspace Fields

Two workspace fields provide both source fidelity and human readability:

| Field | Description | Claude | Codex | Gemini |
|-------|-------------|--------|-------|--------|
| `workspace` | Human-readable path (derived) | Decoded from directory name | From `cwd` | From hash index lookup (or null) |
| `workspace_encoded` | Raw source identifier | Directory name (e.g., `-home-user-myproject`) | `null` | SHA-256 hash |

### Git Branch Changes

> **Note**: `session.git.branch` reflects the branch at session start. `messages[].metadata.git_branch` reflects the branch at each message, which may differ if the user switches branches mid-session.

### Sub-Agent Sessions

The `is_agent_session` and `parent_session_id` fields are optional and only present for Claude sub-agent sessions. Currently only Claude supports native sub-agent sessions; Codex and Gemini have this feature in development.

---

## Message Object

```json
{
  "index": 1,
  "uuid": "msg-uuid-123",
  "parent_uuid": "msg-uuid-122",
  "role": "assistant",
  "timestamp": "2025-12-27T09:00:05Z",
  "content": [ ... ],
  "metadata": { ... }
}
```

| Field | Type | Required | Agent | Description |
|-------|------|----------|-------|-------------|
| `index` | int | Yes | All | 1-based message index |
| `uuid` | string | No | Claude, Gemini | Unique message ID |
| `parent_uuid` | string | No | Claude | Parent message ID (for fork tracking) |
| `role` | string | Yes | All | `user`, `assistant`, `system` |
| `timestamp` | string | No | All | ISO 8601 message timestamp |
| `content` | array | Yes | All | Content blocks (see below) |
| `metadata` | object | No | All | Context metadata (see below) |

### Role Normalization

| Agent | Source Value | Unified Value |
|-------|--------------|---------------|
| Claude | `user` | `user` |
| Claude | `assistant` | `assistant` |
| Claude | `system` | `system` |
| Codex | `user` | `user` |
| Codex | `assistant` | `assistant` |
| Gemini | `user` | `user` |
| Gemini | `gemini` | `assistant` |
| Gemini | `info` / `error` / `warning` | `system` |

---

## Message Metadata

Metadata provides context for the message. It is **only present when context changes** from the previous message (or on the first message).

> **Rule**: Metadata present = context changed (or first message). Absent = same context as previous message.

```json
{
  "cwd": "/home/user/myproject",
  "git_branch": "main",
  "cli_version": "2.0.75",
  "user_type": "external",
  "is_meta": false,
  "request_id": "req_abc123",
  "approval_policy": "on-request",
  "sandbox_policy": {
    "type": "workspace-write",
    "network_access": false
  },
  "effort": "high",
  "model": {
    "name": "claude-sonnet-4-5-20250929",
    "stop_reason": "end_turn",
    "stop_sequence": null,
    "context_window": null
  },
  "token_usage": {
    "input_tokens": 1500,
    "output_tokens": 350,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 1200,
    "reasoning_tokens": 0,
    "tool_tokens": 0,
    "total_tokens": 1850
  },
  "service_tier": "standard",
  "synthetic": false
}
```

| Field | Type | Agent | Description |
|-------|------|-------|-------------|
| `cwd` | string | Claude, Codex | Working directory |
| `git_branch` | string | Claude, Codex | Git branch (may change mid-session) |
| `cli_version` | string | Claude, Codex | CLI version |
| `user_type` | string | Claude | User type identifier |
| `is_meta` | bool | Claude | System/meta message indicator |
| `request_id` | string | Claude | API request ID |
| `approval_policy` | string | Codex | Tool approval policy |
| `sandbox_policy` | object | Codex | Sandbox configuration |
| `effort` | string | Codex | Effort level |
| `model.name` | string | All | Model identifier |
| `model.stop_reason` | string | Claude | `end_turn`, `tool_use`, `max_tokens` |
| `model.stop_sequence` | string | Claude | Stop sequence if triggered |
| `model.context_window` | int | Codex | Model context window size |
| `token_usage.*` | int | All | Token counts (see below) |
| `service_tier` | string | Claude | API service tier |
| `synthetic` | bool | All | `true` if message was generated during normalization |

### Token Usage Fields

| Field | Agent | Description |
|-------|-------|-------------|
| `input_tokens` | All | Input tokens consumed |
| `output_tokens` | All | Output tokens generated |
| `cache_creation_tokens` | Claude | Tokens written to cache |
| `cache_read_tokens` | All | Tokens read from cache |
| `reasoning_tokens` | Codex, Gemini | Tokens for reasoning/thinking |
| `tool_tokens` | Gemini | Tokens for tool calls |
| `total_tokens` | Codex, Gemini | Total tokens (explicit) |

---

## Content Blocks

Content is an array of typed blocks. Each block has a `type` field.

### Text Block

```json
{
  "type": "text",
  "text": "Hello, how can I help?"
}
```

### Reasoning Block (Unified)

All reasoning/thinking content uses a unified `reasoning` type with a `format` field to indicate the source structure.

```json
// Claude (format: "thinking")
{
  "type": "reasoning",
  "format": "thinking",
  "text": "Let me analyze this step by step...",
  "signature": "EtoECkYIChgCKkCPLjvF..."
}

// Codex (format: "summary")
{
  "type": "reasoning",
  "format": "summary",
  "items": [{"type": "summary_text", "text": "**Analyzing auth module**"}],
  "encrypted_content": "gAAAAABpSi4X1CPuupBD..."
}

// Gemini (format: "thoughts")
{
  "type": "reasoning",
  "format": "thoughts",
  "entries": [
    {"subject": "Code Review Scope", "description": "Analyzing the structure...", "timestamp": "2025-12-03T06:35:40Z"},
    {"subject": "Potential Issues", "description": "Looking for bug patterns...", "timestamp": "2025-12-03T06:35:50Z"}
  ]
}
```

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `format` | string | All | `"thinking"`, `"summary"`, or `"thoughts"` |
| `text` | string | thinking | Reasoning text (Claude) |
| `signature` | string | thinking | Encrypted signature (Claude, optional) |
| `items` | array | summary | Summary text items (Codex) |
| `encrypted_content` | string | summary | Encrypted content (Codex, optional) |
| `entries` | array | thoughts | Thought entries (Gemini) |
| `entries[].subject` | string | thoughts | Thought subject |
| `entries[].description` | string | thoughts | Thought description |
| `entries[].timestamp` | string | thoughts | Thought timestamp |

### Tool Use Block

```json
{
  "type": "tool_use",
  "tool_id": "toolu_01ABC",
  "tool_name": "Bash",
  "input": {
    "command": "ls -la",
    "description": "List files"
  },
  "display_name": "Shell Command",
  "description": "Execute a shell command"
}
```

| Field | Type | Required | Agent | Description |
|-------|------|----------|-------|-------------|
| `tool_id` | string | Yes | All | Unique tool call identifier |
| `tool_name` | string | Yes | All | Tool name |
| `input` | object | Yes | All | Tool input parameters |
| `display_name` | string | No | Gemini | Human-readable tool name |
| `description` | string | No | Gemini | Tool description |

### Tool Result Block

Tool results are normalized to appear in separate **user messages**, regardless of source format.

```json
{
  "type": "tool_result",
  "tool_id": "toolu_01ABC",
  "tool_name": "Bash",
  "output": "total 128\ndrwxr-xr-x ...",
  "is_error": false,
  "user_reason": null,
  "error_message": null,
  "render_as_markdown": true
}
```

| Field | Type | Required | Agent | Description |
|-------|------|----------|-------|-------------|
| `tool_id` | string | Yes | All | Matches the tool_use tool_id |
| `tool_name` | string | No | All | Tool name (for convenience) |
| `output` | string | Yes | All | Tool output content |
| `is_error` | bool | Yes | All | Whether the tool failed |
| `user_reason` | string | No | Claude | User's stated reason (if rejection) |
| `error_message` | string | No | Gemini | Detailed error message |
| `render_as_markdown` | bool | No | Gemini | Whether to render as markdown |

**Gemini Tool Result Normalization:**

Gemini embeds tool results in the same message as tool calls. During export, these are split into separate user messages:

- Original Gemini message → assistant message with `tool_use` blocks
- Synthetic user message with `tool_result` blocks
- Synthetic message UUID: `{message_uuid}-{tool_id}-result`
- Synthetic message has `metadata.synthetic: true`

**Rejection Detection:**

If `is_error: true` and `user_reason` is present, this indicates the user rejected the tool use (Claude only).

### Agent Spawn Block (Claude only)

```json
{
  "type": "agent_spawn",
  "agent_session_id": "agent-002",
  "prompt": "Research the API documentation",
  "agent_type": "Explore"
}
```

### Agent Result Block (Claude only)

```json
{
  "type": "agent_result",
  "agent_session_id": "agent-002",
  "summary": "Found 3 relevant API endpoints",
  "is_error": false
}
```

### Interruption Block

User interrupted the assistant. Appears in a `system` role message.

```json
{
  "type": "interruption",
  "reason": "user"
}
```

| Agent | Source | Normalized |
|-------|--------|------------|
| Claude | User message: `[Request interrupted by user]` | `{"type": "interruption", "reason": "user"}` |
| Codex | `event_msg` with `turn_aborted` | `{"type": "interruption", "reason": "user"}` |
| Gemini | `info` message: `Request cancelled.` | `{"type": "interruption", "reason": "user"}` |

### Compaction Block

Context was compacted/summarized. Appears in a `system` role message.

```json
// Claude (format: "boundary")
{
  "type": "compaction",
  "format": "boundary",
  "trigger": "auto",
  "pre_tokens": 155116,
  "summary": "...",
  "logical_parent_uuid": "msg-014"
}

// Codex (format: "inline")
{
  "type": "compaction",
  "format": "inline",
  "summary": "**Progress + Plan Status**\n...",
  "replaced_count": 5
}
```

| Field | Type | Format | Description |
|-------|------|--------|-------------|
| `format` | string | All | `"boundary"` (Claude) or `"inline"` (Codex) |
| `trigger` | string | boundary | How triggered (e.g., "auto") |
| `pre_tokens` | int | boundary | Token count before compaction |
| `summary` | string | All | Compaction summary |
| `logical_parent_uuid` | string | boundary | Last message before compaction |
| `replaced_count` | int | inline | Number of messages replaced |

### File Snapshot Block (Claude only)

```json
{
  "type": "file_snapshot",
  "files": [
    {"path": "/home/user/file.py", "content": "..."}
  ]
}
```

### Git Snapshot Block (Codex only)

```json
{
  "type": "git_snapshot",
  "commit_id": "dac0722...",
  "parent_commit": "b92c69c...",
  "untracked_files": ["specs.md"],
  "untracked_dirs": []
}
```

---

## Content Block Summary

| Type | Description | Claude | Codex | Gemini |
|------|-------------|--------|-------|--------|
| `text` | Regular text output | ✓ | ✓ | ✓ |
| `reasoning` | Unified reasoning (with `format` field) | ✓ | ✓ | ✓ |
| `tool_use` | Request to execute a tool | ✓ | ✓ | ✓ |
| `tool_result` | Output from tool execution | ✓ | ✓ | ✓ |
| `agent_spawn` | Create sub-agent session | ✓ | - | - |
| `agent_result` | Output from sub-agent | ✓ | - | - |
| `interruption` | User interrupted | ✓ | ✓ | ✓ |
| `compaction` | Context compacted (with `format` field) | ✓ | ✓ | - |
| `file_snapshot` | File state captured | ✓ | - | - |
| `git_snapshot` | Git state captured | - | ✓ | - |

---

## Conversation Graph

For sessions with forks (user went back and branched). Only included when conversation is not linear.

```json
{
  "graph": {
    "is_linear": false,
    "fork_points": [
      {
        "uuid": "msg-031",
        "index": 2,
        "branches": [
          {"uuid": "msg-032a", "index": 3},
          {"uuid": "msg-032b", "index": 4}
        ]
      }
    ],
    "active_path": ["msg-030", "msg-031", "msg-032b", "msg-033"]
  }
}
```

---

## Agent-Specific Field Mapping

### Session Fields

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `session.id` | `sessionId` | `session_meta.payload.id` | `sessionId` |
| `session.agent` | `"claude-code"` | `"codex"` | `"gemini"` |
| `session.workspace` | Decode directory name | `session_meta.payload.cwd` | Hash index lookup |
| `session.workspace_encoded` | Directory name | `null` | `projectHash` |
| `session.started_at` | `min(timestamp)` | `session_meta.payload.timestamp` | `startTime` |
| `session.ended_at` | `max(timestamp)` | `max(timestamp)` | `lastUpdated` |
| `session.is_agent_session` | `isSidechain` (if true) | N/A | N/A |
| `session.parent_session_id` | From agent file context | N/A | N/A |
| `session.slug` | `slug` | N/A | N/A |
| `session.instructions` | N/A | `session_meta.payload.instructions` | N/A |
| `session.model_provider` | N/A | `session_meta.payload.model_provider` | N/A |
| `session.cli_version` | `version` | `session_meta.payload.cli_version` | N/A |
| `session.git.branch` | First message `gitBranch` | `session_meta.payload.git.branch` | N/A |
| `session.git.commit_hash` | N/A | `session_meta.payload.git.commit_hash` | N/A |
| `session.summary` | `session-memory/summary.md` | N/A | `summary` |

### Message Fields

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `uuid` | `uuid` | Generated | `id` |
| `parent_uuid` | `parentUuid` | N/A | N/A |
| `role` | `message.role` | `payload.role` | `type` (normalized) |
| `timestamp` | `timestamp` | `timestamp` | `timestamp` |

### Metadata Fields

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `cwd` | `cwd` | `turn_context.payload.cwd` | N/A |
| `git_branch` | `gitBranch` | `turn_context.payload.git.branch` | N/A |
| `approval_policy` | N/A | `turn_context.payload.approval_policy` | N/A |
| `sandbox_policy` | N/A | `turn_context.payload.sandbox_policy` | N/A |
| `effort` | N/A | `turn_context.payload.effort` | N/A |
| `model.name` | `message.model` | `turn_context.payload.model` | `model` |
| `model.stop_reason` | `message.stop_reason` | N/A | N/A |
| `token_usage.*` | `message.usage.*` | `event_msg[token_count].*` | `tokens.*` |

### Content Block Mapping

| Unified Type | Claude Code | Codex CLI | Gemini CLI |
|--------------|-------------|-----------|------------|
| `text` | `content[].type="text"` | `content[].type="output_text"/"input_text"` | `content` (string) |
| `reasoning` | `type="thinking"` | `payload.type="reasoning"` | `thoughts[]` |
| `tool_use` | `content[].type="tool_use"` | `payload.type="function_call"` | `toolCalls[]` (extract) |
| `tool_result` | `content[].type="tool_result"` | `payload.type="function_call_output"` | `toolCalls[].result` (split out) |
| `interruption` | User msg `[Request interrupted...]` | `event_msg.turn_aborted` | `type="info"` cancelled |
| `compaction` | `system.subtype="compact_boundary"` | `type="compacted"` | N/A |
| `file_snapshot` | `type="file-history-snapshot"` | N/A | N/A |
| `git_snapshot` | N/A | `payload.type="ghost_snapshot"` | N/A |

### Tool Call Field Mapping

| Unified Field | Claude Code | Codex CLI | Gemini CLI |
|---------------|-------------|-----------|------------|
| `tool_id` | `id` | `call_id` | `id` |
| `tool_name` | `name` | `name` | `name` |
| `input` | `input` | `arguments` (parse JSON) | `args` |
| `output` | `tool_result.content` | `function_call_output.output` | `result[].functionResponse.response.output` |
| `is_error` | `is_error` | (infer) | `status="error"` |
| `user_reason` | Parsed from content | N/A | N/A |
| `error_message` | In content text | N/A | `error` |

---

## Complete Examples

### Claude Code Session

```json
{
  "type": "session",
  "session": {
    "id": "c7e6fbcb-6a8a-4637-ab33-6075d83060a8",
    "agent": "claude-code",
    "workspace": "/home/user/myproject",
    "workspace_encoded": "-home-user-myproject",
    "started_at": "2025-12-27T09:00:00Z",
    "ended_at": "2025-12-27T09:15:00Z",
    "source": {"type": "local", "host": null, "path": "~/.claude/projects/.../c7e6fbcb.jsonl"},
    "slug": "silly-humming-cocke",
    "cli_version": "2.0.75",
    "git": {"branch": "main"}
  },
  "messages": [
    {
      "index": 1,
      "uuid": "msg-001",
      "role": "user",
      "timestamp": "2025-12-27T09:00:00Z",
      "content": [{"type": "text", "text": "List files"}],
      "metadata": {"cwd": "/home/user/myproject", "git_branch": "main"}
    },
    {
      "index": 2,
      "uuid": "msg-002",
      "parent_uuid": "msg-001",
      "role": "assistant",
      "timestamp": "2025-12-27T09:00:05Z",
      "content": [
        {"type": "reasoning", "format": "thinking", "text": "User wants a directory listing."},
        {"type": "text", "text": "I'll list the files."},
        {"type": "tool_use", "tool_id": "toolu_001", "tool_name": "Bash", "input": {"command": "ls -la"}}
      ],
      "metadata": {"model": {"name": "claude-sonnet-4-5-20250929", "stop_reason": "tool_use"}}
    },
    {
      "index": 3,
      "uuid": "msg-003",
      "parent_uuid": "msg-002",
      "role": "user",
      "timestamp": "2025-12-27T09:00:06Z",
      "content": [
        {"type": "tool_result", "tool_id": "toolu_001", "tool_name": "Bash", "output": "README.md\nsrc/", "is_error": false}
      ]
    }
  ]
}
```

### Codex Session

```json
{
  "type": "session",
  "session": {
    "id": "rollout-2025-12-27T08-00-00-abc123",
    "agent": "codex",
    "workspace": "/home/user/api-server",
    "workspace_encoded": null,
    "started_at": "2025-12-27T08:00:00Z",
    "ended_at": "2025-12-27T08:30:00Z",
    "source": {"type": "wsl", "host": "Ubuntu", "path": "~/.codex/sessions/..."},
    "instructions": "# Repository Guidelines\n...",
    "model_provider": "openai",
    "cli_version": "0.77.0",
    "git": {"branch": "master", "commit_hash": "0e3689a"}
  },
  "messages": [
    {
      "index": 1,
      "uuid": "gen-001",
      "role": "user",
      "timestamp": "2025-12-27T08:00:00Z",
      "content": [{"type": "text", "text": "Fix the bug in auth.py"}],
      "metadata": {"cwd": "/home/user/api-server", "approval_policy": "on-request", "effort": "high"}
    },
    {
      "index": 2,
      "uuid": "gen-002",
      "role": "assistant",
      "timestamp": "2025-12-27T08:00:30Z",
      "content": [
        {"type": "reasoning", "format": "summary", "items": [{"type": "summary_text", "text": "**Analyzing auth module**"}]},
        {"type": "text", "text": "I found the issue."},
        {"type": "tool_use", "tool_id": "call_001", "tool_name": "shell", "input": {"command": "cat auth.py"}}
      ],
      "metadata": {"model": {"name": "o3"}}
    },
    {
      "index": 3,
      "uuid": "gen-003",
      "role": "user",
      "timestamp": "2025-12-27T08:00:35Z",
      "content": [
        {"type": "tool_result", "tool_id": "call_001", "output": "def authenticate():\n    ...", "is_error": false}
      ]
    },
    {
      "index": 4,
      "uuid": "gen-004",
      "role": "system",
      "timestamp": "2025-12-27T08:00:00Z",
      "content": [
        {"type": "git_snapshot", "commit_id": "dac0722", "parent_commit": "b92c69c", "untracked_files": ["specs.md"]}
      ]
    }
  ]
}
```

### Gemini Session

```json
{
  "type": "session",
  "session": {
    "id": "477739d0-1b78-4aa7-9116-02d08c952344",
    "agent": "gemini",
    "workspace": "/home/user/myproject",
    "workspace_encoded": "8876362f5a5f00ff0d93bf9c95efa883e60cbd44bfa1db1f77ad4280aeab35a6",
    "started_at": "2025-12-27T10:00:00Z",
    "ended_at": "2025-12-27T10:15:00Z",
    "source": {"type": "local", "host": null, "path": "~/.gemini/tmp/.../session.json"},
    "summary": "Reviewed codebase for bugs."
  },
  "messages": [
    {
      "index": 1,
      "uuid": "553d877e-dd47-42b6-ae51-84d990c8ae10",
      "role": "user",
      "timestamp": "2025-12-27T10:00:00Z",
      "content": [{"type": "text", "text": "Review this code for bugs"}]
    },
    {
      "index": 2,
      "uuid": "d0d8eed9-9936-4c96-97c1-eb7541b05b2a",
      "role": "assistant",
      "timestamp": "2025-12-27T10:00:30Z",
      "content": [
        {
          "type": "reasoning",
          "format": "thoughts",
          "entries": [
            {"subject": "Code Review Scope", "description": "Analyzing the codebase structure..."},
            {"subject": "Potential Issues", "description": "Looking for common bug patterns..."}
          ]
        },
        {"type": "text", "text": "I've reviewed the code and found 2 issues."},
        {"type": "tool_use", "tool_id": "read_file-123", "tool_name": "read_file", "input": {"file_path": "src/main.py"}, "display_name": "Read File"}
      ],
      "metadata": {"model": {"name": "gemini-2.5-pro"}, "token_usage": {"input_tokens": 200, "output_tokens": 150, "reasoning_tokens": 100, "total_tokens": 500}}
    },
    {
      "index": 3,
      "uuid": "d0d8eed9-9936-4c96-97c1-eb7541b05b2a-read_file-123-result",
      "role": "user",
      "timestamp": "2025-12-27T10:00:35Z",
      "content": [
        {"type": "tool_result", "tool_id": "read_file-123", "tool_name": "read_file", "output": "def main():\n    print('hello')", "is_error": false}
      ],
      "metadata": {"synthetic": true}
    }
  ]
}
```

---

## CLI Usage

```bash
# Export everything to NDJSON
./agent-history export --ah --aw --json -o ./backup

# Export specific workspace
./agent-history export myproject --json

# Export with both --source (raw) and --json (normalized)
./agent-history export myproject --source --json

# Pipe to jq for processing
./agent-history export --json | jq '.messages | length'
```

---

## Streaming Usage

```python
import json

with open("export.ndjson") as f:
    header = json.loads(f.readline())
    print(f"Schema v{header['schema_version']}, {header['session_count']} sessions")

    current_context = {}
    for line in f:
        record = json.loads(line)
        session = record["session"]

        for msg in record["messages"]:
            # Update context if metadata present
            if msg.get("metadata"):
                current_context = msg["metadata"]

            # Process message with current_context
            print(f"[{msg['role']}] {msg.get('uuid', 'no-uuid')}")
```

---

## Versioning

- Schema follows semantic versioning
- **v1.0**: Initial schema
- **v2.0**: Full union approach with:
  - Unified `reasoning` block with `format` field
  - Unified `compaction` block with `format` field
  - Tool result normalization (split for Gemini)
  - Two workspace fields (`workspace` + `workspace_encoded`)
  - Optional `is_agent_session` / `parent_session_id`
  - Metadata on context change only
  - Git info at session and message level

---

## Optional Fields Summary

| Category | Claude-only | Codex-only | Gemini-only | All Agents |
|----------|-------------|------------|-------------|------------|
| Session | `slug`, `is_agent_session`, `parent_session_id` | `instructions`, `model_provider`, `git.commit_hash` | - | `id`, `workspace`, `started_at`, `ended_at` |
| Metadata | `user_type`, `is_meta`, `request_id`, `stop_reason`, `cache_creation_tokens`, `service_tier` | `approval_policy`, `sandbox_policy`, `effort`, `context_window` | `reasoning_tokens`, `tool_tokens` | `model.name`, `input_tokens`, `output_tokens` |
| Content | `agent_spawn`, `agent_result`, `file_snapshot` | `git_snapshot` | - | `text`, `reasoning`, `tool_use`, `tool_result`, `interruption` |
