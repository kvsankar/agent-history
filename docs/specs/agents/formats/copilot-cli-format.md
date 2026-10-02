# Copilot CLI Session Format

<!-- doc-meta
doc_role: spec
audience: contributor
lifecycle: current
content_type: api
surface: integration
canonicality: primary
-->

> **Status**: Initial support target based on local inspection and the public
> Copilot CLI package schema. See
> [copilot-local-formats-2026-06-19.md](../../../research/copilot-local-formats-2026-06-19.md).

Copilot CLI stores terminal-agent sessions under:

```text
~/.copilot/session-state/
└── <session-id>/
    ├── events.jsonl
    └── workspace.yaml
```

The user profile can also contain:

```text
~/.copilot/session-store.db
```

`events.jsonl` is the primary transcript source. A profile-level
`session-store.db` has been observed, but no per-session `session.db` has been
confirmed as part of the local transcript contract.

## Event Stream

Each event is newline-delimited JSON with fields such as:

```json
{
  "id": "event-id",
  "timestamp": "2026-06-18T13:55:33.966Z",
  "parentId": "previous-event-id",
  "agentId": "sub-agent-id",
  "type": "assistant.message",
  "data": {}
}
```

Important fields:

| Field | Meaning |
|-------|---------|
| `id` | Event ID |
| `timestamp` | Wall-clock event timestamp |
| `parentId` | Chronologically preceding event ID; null for the first event |
| `agentId` | Child/sub-agent instance ID; absent for the root agent |
| `type` | Event type |
| `data` | Event-specific payload |

Observed event types include:

- `session.start`
- `session.model_change`
- `session.info`
- `system.message`
- `user.message`
- `assistant.turn_start`
- `assistant.message`
- `tool.execution_start`
- `tool.execution_complete`
- `permission.requested`
- `permission.completed`
- `hook.start`
- `hook.end`
- `subagent.started`
- `subagent.completed`
- `session.shutdown`

Unknown event types must not abort parsing.

## Workspace Matching

Use this order:

1. `workspace.yaml` `cwd`
2. `session.start.data.context.cwd`
3. Session directory name as a fallback

Windows paths are kept as readable workspace strings. Cross-platform path
normalization should happen in the shared scope layer, not inside this parser.

## Message Normalization

| Copilot event | Normalized role |
|---------------|-----------------|
| `user.message` | `user` |
| `assistant.message` | `assistant` |
| `system.message` | `system` |
| `tool.execution_start` | `tool` call |
| `tool.execution_complete` | `tool` result |

`assistant.message.data.toolRequests` should be retained when present. Tool
execution start/complete events are also preserved so exports can show actual
tool I/O.

## Tokens and Stats

Copilot CLI assistant events can include `outputTokens`. Input and cache token
counts are not guaranteed in the JSONL event stream. Stats should use available
fields and leave missing token dimensions as zero/unknown according to existing
`cagelens` conventions.

## Scope

Local, WSL, and Windows filesystem sources are supported. SSH remote Copilot
CLI discovery is not implemented yet.

## Subagents

Copilot CLI events expose sub-agent identity directly:

- `agentId` marks child-agent events.
- `subagent.started` and `subagent.completed` represent lifecycle events.

The first implementation should preserve these events and avoid inventing
lineage that is not present in the stream.
