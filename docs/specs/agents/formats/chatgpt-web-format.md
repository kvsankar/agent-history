# ChatGPT Web Export Format Analysis

This document describes the conversation export format from ChatGPT (chat.openai.com).

> **Status**: Research phase - based on community documentation and third-party tools (January 2026).

## Table of Contents

1. [Export Methods](#export-methods)
2. [File Format](#file-format)
3. [Record Structure](#record-structure)
4. [Comparison with Codex CLI](#comparison-with-codex-cli)
5. [Implementation Considerations](#implementation-considerations)

---

## Export Methods

### Native Export (File-Based)

OpenAI provides a data export feature:
1. Settings → Data Controls → Export Data
2. Confirm export request
3. Receive email with ZIP file containing:
   - `conversations.json` - All conversations
   - `chat.html` - Human-readable HTML version
   - Other account data

**Limitations:**
- Manual process (no automation)
- Team/Enterprise workspace conversations excluded
- Images not included in export
- No incremental export option

### API Access

**Status**: Under investigation. Need to determine if OpenAI provides:
- Conversation history API
- Session listing endpoint
- Real-time sync capability

---

## File Format

### conversations.json Structure

The export uses a tree-based mapping structure to support conversation branching (regenerations, edits).

```json
[
  {
    "id": "conversation-uuid",
    "title": "Conversation Title",
    "create_time": 1703001234.567,
    "update_time": 1703005678.901,
    "current_node": "last-message-uuid",
    "mapping": {
      "message-uuid-1": {
        "id": "message-uuid-1",
        "parent": null,
        "children": ["message-uuid-2"],
        "message": {...}
      },
      "message-uuid-2": {
        "id": "message-uuid-2",
        "parent": "message-uuid-1",
        "children": ["message-uuid-3"],
        "message": {...}
      }
    }
  }
]
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | string | Unique conversation UUID |
| `title` | string | Conversation title (auto-generated or user-set) |
| `create_time` | float | Unix timestamp (seconds with decimals) |
| `update_time` | float | Last modification timestamp |
| `current_node` | string | UUID of the last message in current branch |
| `mapping` | object | Tree structure of all messages |

---

## Record Structure

### Message Node

Each node in the `mapping` object:

```json
{
  "id": "message-uuid",
  "parent": "parent-message-uuid",
  "children": ["child-uuid-1", "child-uuid-2"],
  "message": {
    "id": "msg-uuid",
    "author": {
      "role": "user|assistant|system",
      "metadata": {}
    },
    "create_time": 1703001234.567,
    "content": {
      "content_type": "text",
      "parts": ["The message text here"]
    },
    "metadata": {
      "model_slug": "gpt-4",
      "finish_details": {
        "type": "stop",
        "stop_tokens": [100260]
      }
    },
    "end_turn": true,
    "weight": 1,
    "recipient": "all"
  }
}
```

### Author Roles

| Role | Description |
|------|-------------|
| `system` | System prompt (usually first message) |
| `user` | Human user input |
| `assistant` | ChatGPT response |

### Content Types

| Type | Description |
|------|-------------|
| `text` | Standard text content |
| `code` | Code blocks (observed in some exports) |
| `multimodal_text` | Messages with images (image data not included) |

### Metadata Fields (Assistant)

| Field | Description |
|-------|-------------|
| `model_slug` | Model identifier (e.g., "gpt-4", "gpt-4o") |
| `finish_details` | Completion information |

---

## Comparison with Codex CLI

| Aspect | ChatGPT Web | Codex CLI |
|--------|-------------|-----------|
| **Storage** | Cloud (OpenAI servers) | Local (`~/.codex/sessions/`) |
| **Access** | Manual export or API | Direct file access |
| **Format** | Single JSON array | JSONL per session |
| **Structure** | Tree (mapping) | Linear (sequential records) |
| **Timestamps** | Unix float | ISO 8601 |
| **Tool Calls** | In content parts | `function_call` records |
| **Branching** | Supported via children | Not applicable |
| **Session ID** | `id` field | `session_meta.payload.id` |
| **Model Info** | `metadata.model_slug` | `turn_context.payload.model` |

### Key Differences

1. **Tree vs Linear**: ChatGPT uses tree structure for branching conversations; Codex uses linear JSONL.

2. **Timestamps**: ChatGPT uses Unix timestamps (float seconds); Codex uses ISO 8601.

3. **Workspace**: ChatGPT has no workspace concept; Codex tracks via `cwd` in session metadata.

4. **Export Method**: ChatGPT requires manual export or API; Codex stores locally.

---

## Implementation Considerations

### Parsing the Tree Structure

To convert to linear conversation:

```python
def flatten_conversation(mapping, current_node):
    """Traverse from root to current_node following parent chain."""
    messages = []
    node = mapping.get(current_node)

    # Walk backwards to build path
    path = []
    while node:
        if node.get('message'):
            path.append(node['message'])
        parent_id = node.get('parent')
        node = mapping.get(parent_id) if parent_id else None

    # Reverse to get chronological order
    return list(reversed(path))
```

### Timestamp Conversion

```python
from datetime import datetime

# ChatGPT uses Unix float timestamps
unix_ts = 1703001234.567
dt = datetime.utcfromtimestamp(unix_ts)
iso_ts = dt.isoformat() + 'Z'  # "2023-12-19T15:27:14.567000Z"
```

### Handling Branches

The `children` array may contain multiple IDs (regenerations). Options:
- Follow only the path to `current_node` (default branch)
- Export all branches as separate conversations
- Include branch indicator in metadata

---

## API Access (Internal Backend API)

ChatGPT uses internal API endpoints similar to Claude web. These are not officially documented but can be accessed with proper authentication.

### Authentication

**Required Headers:**
```
Authorization: Bearer <access_token>
Cookie: <session_cookies>
Content-Type: application/json
```

**Token Acquisition:**
- Access token obtained from `/api/auth/session` endpoint
- Token has short TTL, can be refreshed using `session_token`
- Cookies required for some endpoints

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/session` | GET | Get session data (no auth required) |
| `/backend-api/conversations` | GET | List conversations with pagination |
| `/backend-api/conversation/{id}` | GET | Get specific conversation |
| `/backend-api/accounts/check/v4-2023-04-27` | GET | Account information |

### List Conversations

```
GET https://chat.openai.com/backend-api/conversations?offset=0&limit=28
```

**Response:**
```json
{
  "items": [
    {
      "id": "conversation-uuid",
      "title": "Conversation Title",
      "create_time": 1703001234.567,
      "update_time": 1703005678.901
    }
  ],
  "limit": 28,
  "offset": 0,
  "total": 150
}
```

Pagination: Use `offset` parameter (increments of 28 by default).

### Get Conversation

```
GET https://chat.openai.com/backend-api/conversation/{conversation_id}
```

Returns full conversation with tree-structured `mapping` object.

### Comparison with Claude Web

| Aspect | Claude Web | ChatGPT Web |
|--------|------------|-------------|
| Auth Source | macOS Keychain / manual | Browser session / cookies |
| Token Type | OAuth Bearer | JWT Bearer |
| Org Identifier | `x-organization-uuid` header | Not required |
| List Endpoint | `/sessions` | `/backend-api/conversations` |
| Get Endpoint | `/conversations/{id}` | `/backend-api/conversation/{id}` |
| Pagination | Cursor-based (TBD) | Offset-based |

### Implementation Notes

1. **Token extraction**: Need to extract from browser session or cookies
2. **Token refresh**: JWT has short TTL, need refresh mechanism
3. **Rate limiting**: Unknown, needs testing
4. **ToS consideration**: Internal API, may violate OpenAI ToS

---

## Sources

- [Everything ChatGPT - Backend API Documentation](https://github.com/terminalcommandnewsletter/everything-chatgpt)
- [ChatGPT Exporter (GitHub)](https://github.com/pionxzh/chatgpt-exporter)
- [ChatGPT Migration Tool](https://github.com/buraste/chatgpt-migration)
- [OpenAI Help - Export Data](https://help.openai.com/en/articles/7260999-how-do-i-export-my-chatgpt-history-and-data)
- [OpenAI Conversations API](https://platform.openai.com/docs/api-reference/conversations)

---

## Changelog

- **2026-01-03**: Initial documentation based on community research
