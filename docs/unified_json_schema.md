# Unified JSON Schema for Agent History

This document describes the normalized JSON format used by `--json` export, which provides a consistent structure across all supported AI coding assistants (Claude Code, Codex CLI, Gemini CLI).

## Design Goals

1. **Unified format**: Same schema regardless of source agent
2. **Lossless**: Preserve all meaningful information from source formats
3. **Round-trip capable**: Can reconstruct equivalent markdown from JSON
4. **Future-proof**: Extensible for new agents and features

## File Format

- Extension: `.json` (single session) or `.ndjson` (multiple sessions)
- Encoding: UTF-8
- Structure: JSON object with metadata header and messages array

## Schema

### Top-Level Structure

```json
{
  "schema_version": "1.0",
  "export_timestamp": "2025-12-27T10:30:00Z",
  "agent": "claude-code",
  "session": { ... },
  "messages": [ ... ]
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | Yes | Schema version (semver) |
| `export_timestamp` | string | Yes | ISO 8601 timestamp of export |
| `agent` | string | Yes | Source agent: `claude-code`, `codex`, `gemini` |
| `session` | object | Yes | Session-level metadata |
| `messages` | array | Yes | Array of message objects |

### Session Object

```json
{
  "id": "abc123-def456",
  "workspace": "/home/user/myproject",
  "workspace_encoded": "-home-user-myproject",
  "started_at": "2025-12-27T09:00:00Z",
  "ended_at": "2025-12-27T10:30:00Z",
  "source": {
    "type": "local",
    "host": null,
    "path": "/home/user/.claude/projects/-home-user-myproject/abc123.jsonl"
  },
  "is_agent_session": false,
  "parent_session_id": null,
  "agent_id": null
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique session identifier |
| `workspace` | string | Yes | Human-readable workspace path |
| `workspace_encoded` | string | Yes | Encoded workspace directory name |
| `started_at` | string | Yes | First message timestamp |
| `ended_at` | string | Yes | Last message timestamp |
| `source` | object | Yes | Where the session was loaded from |
| `source.type` | string | Yes | `local`, `wsl`, `windows`, `remote` |
| `source.host` | string | No | Remote hostname or WSL distro |
| `source.path` | string | Yes | Original file path |
| `is_agent_session` | bool | Yes | True if this is a sub-agent task |
| `parent_session_id` | string | No | Parent session for agent tasks |
| `agent_id` | string | No | Agent ID for agent tasks |

### Message Object

```json
{
  "index": 1,
  "uuid": "msg-uuid-123",
  "parent_uuid": "msg-uuid-122",
  "role": "user",
  "timestamp": "2025-12-27T09:00:00Z",
  "content": [ ... ],
  "metadata": { ... }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `index` | int | Yes | 1-based message index |
| `uuid` | string | No | Unique message ID (if available) |
| `parent_uuid` | string | No | Parent message ID (for graph/fork tracking) |
| `role` | string | Yes | `user`, `assistant`, `system` |
| `timestamp` | string | No | ISO 8601 message timestamp |
| `content` | array | Yes | Content blocks (see below) |
| `metadata` | object | No | Additional metadata |

### Content Blocks

Content is an array of typed blocks, supporting mixed content (text + tools):

#### Text Block

```json
{
  "type": "text",
  "text": "Hello, how can I help?"
}
```

#### Tool Use Block (Assistant requesting tool)

```json
{
  "type": "tool_use",
  "tool_id": "tool_abc123",
  "tool_name": "Bash",
  "input": {
    "command": "ls -la",
    "description": "List files"
  }
}
```

#### Tool Result Block (Result of tool execution)

```json
{
  "type": "tool_result",
  "tool_id": "tool_abc123",
  "tool_name": "Bash",
  "output": "total 128\ndrwxr-xr-x ...",
  "is_error": false
}
```

### Message Metadata

```json
{
  "cwd": "/home/user/myproject",
  "git_branch": "main",
  "agent_version": "1.0.29",
  "user_type": "external",
  "is_meta": false,
  "model": {
    "name": "claude-sonnet-4-5-20250929",
    "stop_reason": "end_turn",
    "stop_sequence": null
  },
  "token_usage": {
    "input_tokens": 1500,
    "output_tokens": 350,
    "cache_creation_tokens": 0,
    "cache_read_tokens": 1200
  },
  "request_id": "req_abc123"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `cwd` | string | Working directory |
| `git_branch` | string | Git branch name |
| `agent_version` | string | Claude Code/Codex/Gemini version |
| `user_type` | string | User type identifier |
| `is_meta` | bool | System/meta message indicator |
| `model` | object | Model info (assistant messages only) |
| `token_usage` | object | Token counts (assistant messages only) |
| `request_id` | string | API request ID |

### Conversation Graph

For sessions with forks (user went back and branched), additional graph info:

```json
{
  "schema_version": "1.0",
  "session": { ... },
  "messages": [ ... ],
  "graph": {
    "is_linear": false,
    "fork_points": [
      {
        "uuid": "msg-uuid-5",
        "index": 5,
        "branches": [
          {"uuid": "msg-uuid-6a", "index": 6},
          {"uuid": "msg-uuid-6b", "index": 7}
        ]
      }
    ],
    "active_path": ["msg-uuid-1", "msg-uuid-2", ..., "msg-uuid-10"]
  }
}
```

## Agent-Specific Mapping

### Claude Code

| Claude Code Field | Unified Field |
|-------------------|---------------|
| `uuid` | `messages[].uuid` |
| `parentUuid` | `messages[].parent_uuid` |
| `sessionId` | `session.id` |
| `agentId` | `session.agent_id` |
| `isSidechain` | `session.is_agent_session` |
| `isMeta` | `messages[].metadata.is_meta` |
| `cwd` | `messages[].metadata.cwd` |
| `message.model` | `messages[].metadata.model.name` |
| `message.stopReason` | `messages[].metadata.model.stop_reason` |
| `message.usage` | `messages[].metadata.token_usage` |

### Codex CLI

| Codex CLI Field | Unified Field |
|-----------------|---------------|
| `id` | `messages[].uuid` |
| `session.id` | `session.id` |
| `content` | `messages[].content` |
| `role` | `messages[].role` |

### Gemini CLI

| Gemini CLI Field | Unified Field |
|------------------|---------------|
| (TBD - needs investigation) | |

## Example

```json
{
  "schema_version": "1.0",
  "export_timestamp": "2025-12-27T10:30:00Z",
  "agent": "claude-code",
  "session": {
    "id": "c7e6fbcb-6a8a-4637-ab33-6075d83060a8",
    "workspace": "/home/user/myproject",
    "workspace_encoded": "-home-user-myproject",
    "started_at": "2025-12-27T09:00:00Z",
    "ended_at": "2025-12-27T09:15:00Z",
    "source": {
      "type": "local",
      "host": null,
      "path": "/home/user/.claude/projects/-home-user-myproject/c7e6fbcb.jsonl"
    },
    "is_agent_session": false,
    "parent_session_id": null,
    "agent_id": null
  },
  "messages": [
    {
      "index": 1,
      "uuid": "msg-001",
      "parent_uuid": null,
      "role": "user",
      "timestamp": "2025-12-27T09:00:00Z",
      "content": [
        {"type": "text", "text": "List files in the current directory"}
      ],
      "metadata": {
        "cwd": "/home/user/myproject",
        "git_branch": "main"
      }
    },
    {
      "index": 2,
      "uuid": "msg-002",
      "parent_uuid": "msg-001",
      "role": "assistant",
      "timestamp": "2025-12-27T09:00:05Z",
      "content": [
        {"type": "text", "text": "I'll list the files for you."},
        {
          "type": "tool_use",
          "tool_id": "tool_001",
          "tool_name": "Bash",
          "input": {"command": "ls -la"}
        }
      ],
      "metadata": {
        "model": {
          "name": "claude-sonnet-4-5-20250929",
          "stop_reason": "tool_use"
        },
        "token_usage": {
          "input_tokens": 150,
          "output_tokens": 45
        }
      }
    },
    {
      "index": 3,
      "uuid": "msg-003",
      "parent_uuid": "msg-002",
      "role": "user",
      "timestamp": "2025-12-27T09:00:06Z",
      "content": [
        {
          "type": "tool_result",
          "tool_id": "tool_001",
          "tool_name": "Bash",
          "output": "total 8\ndrwxr-xr-x 2 user user 4096 Dec 27 09:00 .\n-rw-r--r-- 1 user user  123 Dec 27 08:55 README.md",
          "is_error": false
        }
      ]
    }
  ],
  "graph": {
    "is_linear": true,
    "fork_points": [],
    "active_path": ["msg-001", "msg-002", "msg-003"]
  }
}
```

## Versioning

- Schema follows semantic versioning
- Minor version bumps: additive, backward-compatible changes
- Major version bumps: breaking changes
- `schema_version` field enables consumers to handle different versions

## Questions for Review

1. **Tool result placement**: Currently tool results appear as user messages (how Claude API works). Should we restructure to group tool_use + tool_result together?

2. **Graph representation**: Is the fork_points + active_path model sufficient, or do we need full tree structure?

3. **Agent-specific extensions**: Should we have an `extensions` field for agent-specific data that doesn't map cleanly?

4. **Compression**: For very large sessions, should we support `.json.gz`?
