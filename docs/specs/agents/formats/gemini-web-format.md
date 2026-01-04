# Gemini Web Export Format Analysis

This document describes conversation access from Gemini web (gemini.google.com).

> **Status**: Research phase - based on third-party tools and community documentation (January 2026).

## Table of Contents

1. [Export Methods](#export-methods)
2. [Third-Party Extension Format](#third-party-extension-format)
3. [Comparison with Gemini CLI](#comparison-with-gemini-cli)
4. [Implementation Considerations](#implementation-considerations)

---

## Export Methods

### Native Export Options

Google's official export options are limited:

| Method | Output | Scope |
|--------|--------|-------|
| Export to Docs | Google Doc | Single response only |
| Export to Gmail | Email draft | Single response only |
| Share link | Public URL | Entire conversation (read-only) |
| Google Takeout | Unknown | Activity data (needs investigation) |

**Limitations:**
- No native bulk JSON/JSONL export
- No "download all conversations" feature
- Single-response export only (not full conversation)
- Share links are public (privacy concern)

### Third-Party Browser Extensions

Several Chrome extensions provide JSON export:

1. **Gemini Chat Exporter** - Structured JSON output
2. **Simple Exporter for Gemini** - JSON/Markdown export
3. **AI Chat Exporter** - Multiple formats (PDF, MD, JSON, CSV)

**Caveats:**
- Rely on DOM scraping (break when Google updates UI)
- Require manual user action
- No automation/API access

### API Access

**Status**: Under investigation. Need to determine if Google provides:
- Conversation history API (similar to Gemini API for generation)
- OAuth-based access to conversation data
- Google Takeout structured format for Gemini

---

## Third-Party Extension Format

Based on [Gemini Chat Exporter](https://github.com/Louisjo/gemini-chat-exporter):

```json
{
  "export_info": {
    "timestamp": "2026-01-03T10:30:00.000Z",
    "source": "Gemini Chat Exporter v1.0.0",
    "total_chats": 5,
    "total_messages": 42
  },
  "chats": [
    {
      "id": "chat-identifier",
      "title": "Conversation Title",
      "timestamp": "2026-01-03T10:30:00.000Z",
      "url": "https://gemini.google.com/app/abc123",
      "messageCount": 10,
      "messages": [
        {
          "role": "user",
          "content": "User's question here",
          "timestamp": "2026-01-03T10:30:00.000Z",
          "word_count": 15
        },
        {
          "role": "assistant",
          "content": "Gemini's response here",
          "timestamp": "2026-01-03T10:30:30.000Z",
          "word_count": 150
        }
      ]
    }
  ]
}
```

### Key Fields

| Field | Type | Description |
|-------|------|-------------|
| `export_info` | object | Metadata about the export |
| `chats` | array | Array of conversation objects |
| `id` | string | Chat identifier (from URL or generated) |
| `title` | string | Conversation title |
| `url` | string | Original Gemini web URL |
| `messages` | array | Ordered array of messages |
| `role` | string | "user" or "assistant" |
| `word_count` | number | Word count per message |

### Notable Characteristics

- **Flat structure**: Linear message array (no tree/branching)
- **ISO timestamps**: Standard ISO 8601 format
- **Word counts**: Included per message (useful for metrics)
- **URLs preserved**: Link back to original conversation

---

## Comparison with Gemini CLI

| Aspect | Gemini Web | Gemini CLI |
|--------|------------|------------|
| **Storage** | Cloud (Google servers) | Local (`~/.gemini/sessions/`) |
| **Access** | Extension export or API | Direct file access |
| **Format** | JSON (extension-dependent) | JSON per session |
| **Structure** | Flat array | Single conversation object |
| **Timestamps** | ISO 8601 | ISO 8601 |
| **Session ID** | URL-based | Hash-based directory |
| **Workspace** | None (web-based) | Derived from cwd |
| **Tool Calls** | Limited visibility | Full tool call records |

### Key Differences

1. **No workspace concept**: Gemini web is browser-based, no local workspace tracking.

2. **Limited metadata**: Extension exports may lack model info, token counts.

3. **No tool visibility**: Web interface doesn't expose tool call details like CLI does.

4. **Reliability**: CLI format is stable; extension format depends on Google's UI.

---

## Implementation Considerations

### Extension Import Path

If supporting extension-exported JSON:

```python
def parse_gemini_web_export(json_file: Path) -> list:
    """Parse Gemini Chat Exporter JSON format."""
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    sessions = []
    for chat in data.get('chats', []):
        session = {
            'id': chat.get('id'),
            'title': chat.get('title'),
            'url': chat.get('url'),
            'messages': [
                {
                    'role': msg['role'],
                    'content': msg['content'],
                    'timestamp': msg.get('timestamp')
                }
                for msg in chat.get('messages', [])
            ]
        }
        sessions.append(session)

    return sessions
```

### Missing Information

Extension exports typically lack:
- Model name/version
- Token usage
- Tool call details
- Session/request IDs
- Thinking/reasoning content

### Google Takeout Investigation

Need to verify:
1. Is Gemini data included in Takeout?
2. What format is the data in?
3. Does it include full conversation history?
4. Is there structured JSON or just activity logs?

---

## API Access Options

### Option 1: Interactions API (Beta - December 2025)

Google released the [Interactions API](https://ai.google.dev/gemini-api/docs/interactions) in public beta, which provides server-side conversation state management.

**Key Features:**
- Single RESTful endpoint (`/interactions`)
- Server-side state via `previous_interaction_id`
- Interaction retrieval by ID

**Retrieve Interaction:**
```
GET https://generativelanguage.googleapis.com/v1beta/interactions/{interaction_id}
```

**Python SDK:**
```python
previous_interaction = client.interactions.get("<INTERACTION_ID>")
```

**Limitations:**
- **No list endpoint**: Cannot list all conversations
- Must know specific interaction ID
- Beta status: features may change
- Retention: 55 days (paid) / 1 day (free)

### Option 2: Internal Gemini Web API (Not Documented)

Similar to ChatGPT, Gemini web likely uses internal APIs. Would require:
- Network inspection to discover endpoints
- Google authentication (cookies/OAuth)
- Reverse engineering the API format

**Status**: Not investigated yet.

### Option 3: Google Takeout

May provide programmatic access, but:
- Unknown if Gemini conversations are included
- Unknown format of exported data
- Requires OAuth for automation

### Comparison with Other Web APIs

| Aspect | Claude Web | ChatGPT Web | Gemini Web |
|--------|------------|-------------|------------|
| List Sessions | Yes (`/sessions`) | Yes (`/backend-api/conversations`) | **No** |
| Get Session | Yes | Yes | Yes (Interactions API by ID) |
| Auth Method | OAuth + Org UUID | JWT + Cookies | Google OAuth / API Key |
| Official API | Internal | Internal | Interactions API (beta) |
| Native Export | No | Yes (ZIP) | No |

### Recommendation

**Gemini web is the most challenging** to support because:
1. No native bulk export
2. New Interactions API lacks list endpoint
3. Internal web API not documented
4. Third-party extensions are fragile

**Best approach for now:**
- Support third-party extension JSON import
- Monitor Interactions API for list endpoint
- Investigate Google Takeout format

---

## Sources

- [Interactions API Documentation](https://ai.google.dev/gemini-api/docs/interactions)
- [Interactions API Blog Post](https://blog.google/technology/developers/interactions-api/)
- [Gemini Chat Exporter (GitHub)](https://github.com/Louisjo/gemini-chat-exporter)
- [Simple Exporter for Gemini (Chrome Store)](https://chromewebstore.google.com/detail/simple-exporter-for-gemin/khgjgbneefjbbocjhakfamgmcjpkmoej)
- [Gemini Apps Help - Export](https://support.google.com/gemini/answer/14184041)
- [Gemini Export Guide](https://exploreaitogether.com/export-download-gemini-guide/)

---

## Changelog

- **2026-01-03**: Initial documentation based on community research
