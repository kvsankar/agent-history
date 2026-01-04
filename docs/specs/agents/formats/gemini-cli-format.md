# Gemini CLI Session Format

This document describes the session storage format used by Google's Gemini CLI, verified from actual session files.

> **Status**: Verified - format confirmed from source code and actual session files (December 2025).

## Table of Contents

1. [Overview](#overview)
2. [Storage Locations](#storage-locations)
3. [Session File Format](#session-file-format)
4. [Message Types](#message-types)
5. [Tool Calls](#tool-calls)
6. [Data Captured](#data-captured)
7. [Built-in Export Options](#built-in-export-options)
8. [Comparison with Claude/Codex](#comparison-with-claudecodex)
9. [Implementation Considerations](#implementation-considerations)
10. [Sources](#sources)

---

## Overview

Gemini CLI is Google's open-source AI coding assistant for the terminal. It supports:
- 1M token context window
- Built-in tools (Google Search, file operations, shell commands, web fetching)
- MCP (Model Context Protocol) server extensibility
- Automatic session management (as of v0.20.0+)

---

## Storage Locations

### Session Storage

Sessions are stored in project-specific directories:

```
~/.gemini/tmp/<project_hash>/chats/
```

Where `<project_hash>` is a SHA-256 hash of the project's root path.

**File naming pattern:** `session-YYYY-MM-DDTHH-MM-<session_id_prefix>.json`

Example: `session-2025-12-03T06-35-477739d0.json`

### Checkpoints (Manual Saves)

Checkpoints from `/chat save <tag>` are stored in:

```
~/.gemini/tmp/<project_hash>/checkpoints/
```

### User Input Log

A separate file tracks user inputs:

```
~/.gemini/tmp/<project_hash>/logs.json
```

### Configuration

```
~/.gemini/settings.json          # User settings
./.gemini/settings.json          # Project settings
~/.gemini/GEMINI.md              # Global context file
```

---

## Session File Format

Sessions are stored as **single JSON files** (not JSONL).

### Top-Level Structure

```json
{
  "sessionId": "477739d0-1b78-4aa7-9116-02d08c952344",
  "projectHash": "8876362f5a5f00ff0d93bf9c95efa883e60cbd44bfa1db1f77ad4280aeab35a6",
  "startTime": "2025-12-03T06:35:37.302Z",
  "lastUpdated": "2025-12-03T06:38:32.429Z",
  "messages": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `sessionId` | string | UUID identifying the session |
| `projectHash` | string | SHA-256 hash of project root path |
| `startTime` | string | ISO 8601 timestamp of session start |
| `lastUpdated` | string | ISO 8601 timestamp of last update |
| `messages` | array | Array of message objects |
| `summary` | string | Optional session summary (generated on demand) |

---

## Message Types

### User Message

```json
{
  "id": "553d877e-dd47-42b6-ae51-84d990c8ae10",
  "timestamp": "2025-12-03T06:35:37.302Z",
  "type": "user",
  "content": "User's message here"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID for this message |
| `timestamp` | string | ISO 8601 timestamp |
| `type` | string | `"user"`, `"info"`, `"error"`, or `"warning"` |
| `content` | string/PartListUnion | The message content |

**Note:** The `type` field can also be `"info"`, `"error"`, or `"warning"` for system messages.

### Gemini Message

```json
{
  "id": "d0d8eed9-9936-4c96-97c1-eb7541b05b2a",
  "timestamp": "2025-12-03T06:35:51.334Z",
  "type": "gemini",
  "content": "Model response here...",
  "thoughts": [...],
  "tokens": {...},
  "model": "gemini-2.5-pro",
  "toolCalls": [...]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | UUID for this message |
| `timestamp` | string | ISO 8601 timestamp |
| `type` | string | Always `"gemini"` |
| `content` | string | The model's response text |
| `thoughts` | array | Optional reasoning/thinking steps |
| `tokens` | object | Token usage statistics |
| `model` | string | Model name (e.g., `"gemini-2.5-pro"`) |
| `toolCalls` | array | Optional tool calls made by the model |

### Thoughts Array

When present, contains the model's reasoning steps:

```json
{
  "thoughts": [
    {
      "subject": "Considering Code Review Scope",
      "description": "I'm currently focused on the scope of the code review...",
      "timestamp": "2025-12-03T06:35:40.321Z"
    }
  ]
}
```

### Token Usage

```json
{
  "tokens": {
    "input": 2678,
    "output": 591,
    "cached": 0,
    "thoughts": 874,
    "tool": 0,
    "total": 4143
  }
}
```

| Field | Description |
|-------|-------------|
| `input` | Input tokens consumed |
| `output` | Output tokens generated |
| `cached` | Tokens served from cache |
| `thoughts` | Tokens used for reasoning |
| `tool` | Tokens used for tool calls |
| `total` | Total tokens for this turn |

---

## Tool Calls

Tool calls are embedded in Gemini messages as a `toolCalls` array:

```json
{
  "toolCalls": [
    {
      "id": "codebase_investigator-1764743737251-810082eb3c63c",
      "name": "codebase_investigator",
      "args": {
        "objective": "Review the codebase for bugs..."
      },
      "result": [...],
      "status": "success",
      "timestamp": "2025-12-03T06:38:32.431Z",
      "displayName": "Codebase Investigator Agent",
      "description": "The specialized tool for codebase analysis...",
      "renderOutputAsMarkdown": true
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique identifier for this tool call |
| `name` | string | Tool name (e.g., `"shell"`, `"read_file"`) |
| `args` | object | Arguments passed to the tool |
| `result` | array | Tool execution results |
| `status` | string | `"success"` or error status |
| `timestamp` | string | When the tool call completed |
| `displayName` | string | Human-readable tool name |
| `description` | string | Tool description |
| `resultDisplay` | string | Formatted result for display |
| `renderOutputAsMarkdown` | boolean | Whether to render output as markdown |

### Tool Result Structure

```json
{
  "result": [
    {
      "functionResponse": {
        "id": "codebase_investigator-1764743737251-810082eb3c63c",
        "name": "codebase_investigator",
        "response": {
          "output": "Tool output here..."
        }
      }
    }
  ]
}
```

---

## Data Captured

| Data | Description |
|------|-------------|
| Session ID | UUID identifying the conversation |
| Project Hash | SHA-256 of project path (for organization) |
| Timestamps | Start time, last update, per-message timestamps |
| User Messages | Full user input text |
| Model Responses | Complete model output |
| Reasoning | Thinking/reasoning steps with subjects and descriptions |
| Tool Calls | Tool name, arguments, results, and status |
| Token Usage | Detailed breakdown per message |
| Model Name | Which Gemini model was used |

---

## Built-in Export Options

### `/chat share` Command

Exports current conversation to file:

```bash
/chat share conversation.md   # Markdown format
/chat share conversation.json # JSON format
```

### `/chat save` Command

Saves checkpoint for later resumption:

```bash
/chat save my-checkpoint
```

### Session Browser

The `/resume` command opens an interactive session browser for:
- Browsing past sessions chronologically
- Searching by ID or content
- Previewing message counts and summaries
- Restoring full conversation context

### JSON Output Mode

For scripting, use CLI flags:

```bash
gemini --output-format json         # Structured JSON output
gemini --output-format stream-json  # Real-time newline-delimited JSON
```

---

## Comparison with Claude/Codex

| Aspect | Claude Code | Codex CLI | Gemini CLI |
|--------|-------------|-----------|------------|
| **Location** | `~/.claude/projects/<workspace>/` | `~/.codex/sessions/YYYY/MM/DD/` | `~/.gemini/tmp/<hash>/chats/` |
| **Format** | JSONL | JSONL | JSON (full file) |
| **Organization** | By workspace path | By date | By project hash |
| **Message Type Field** | `type: "user"/"assistant"` | `payload.role` | `type: "user"/"gemini"` |
| **Content Field** | `content` array | `content` array | `content` string |
| **Session ID** | UUID in filename/records | In `session_meta` | In root `sessionId` |
| **Tool Calls** | In message content | Separate `response_item` | In message `toolCalls` |
| **Token Usage** | In assistant message | In `turn_context` | In message `tokens` |
| **Reasoning** | Not stored | Not stored | In message `thoughts` |
| **Built-in Export** | None | None | `/chat share` |

### Key Differences

1. **File Format**: Gemini uses single JSON files; Claude/Codex use JSONL (one JSON per line).

2. **Role Names**: Gemini uses `"gemini"` for model responses; Claude/Codex use `"assistant"`.

3. **Content Structure**: Gemini stores content as direct strings; Claude/Codex use arrays of content blocks.

4. **Reasoning/Thoughts**: Gemini explicitly stores reasoning steps; Claude/Codex do not.

5. **Project Identification**: Gemini uses SHA-256 hashes of project paths; Claude uses encoded paths; Codex uses dates.

---

## Implementation Considerations

### To Add Gemini Support

1. **Parse JSON (not JSONL)**: Load entire file as JSON object
2. **Handle Hashed Paths**: Scan all `~/.gemini/tmp/*/chats/` directories
3. **Map Type Names**: Convert `"gemini"` → `"assistant"` for unified display
4. **Extract Workspace**: Project hash obscures original path (may need external mapping)
5. **Handle Thoughts**: Optionally display reasoning steps in export

### Environment Variable

Following the pattern of `CLAUDE_PROJECTS_DIR` and `CODEX_SESSIONS_DIR`:

```python
GEMINI_SESSIONS_DIR = os.environ.get("GEMINI_SESSIONS_DIR") or Path.home() / ".gemini" / "tmp"
```

### Challenges

1. **Project Hash**: Cannot reverse SHA-256 to get original project path
2. **JSON vs JSONL**: Different parsing approach needed
3. **Workspace Display**: Need strategy for displaying hashed project names meaningfully
4. **Format Evolution**: Gemini CLI is actively developed; format may change

### Potential Solutions for Project Hash

1. **Scan for GEMINI.md**: Check if project has `.gemini/` directory to map hash → path
2. **Use CWD heuristic**: Compare current directory hash to find matching project
3. **Display hash prefix**: Show first 8 chars of hash as identifier
4. **Build mapping file**: Cache hash → path mappings on first discovery

---

## Sources

- [Gemini CLI GitHub Repository](https://github.com/google-gemini/gemini-cli)
- [chatRecordingService.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/chatRecordingService.ts) - Source of truth for session format
- [Session Management Documentation](https://geminicli.com/docs/cli/session-management/)
- [Configuration Documentation](https://google-gemini.github.io/gemini-cli/docs/get-started/configuration.html)
- Actual session files from `~/.gemini/tmp/*/chats/` (verified December 2025)

---

## Changelog

- **2025-12-13**: Full implementation complete (21 unit tests, 10 E2E tests)
- **2025-12-13**: Verified format from actual session files; updated all documentation
- **2025-12-13**: Initial research documentation
