# VS Code Copilot Session Format

<!-- doc-meta
doc_role: spec
audience: contributor
lifecycle: current
content_type: api
surface: integration
canonicality: primary
-->

> **Status**: Initial support target based on local inspection and public
> third-party parsers. See
> [copilot-local-formats-2026-06-19.md](../../../research/copilot-local-formats-2026-06-19.md).

VS Code Copilot stores extension state under VS Code workspace storage:

```text
<vscode-user-data>/User/workspaceStorage/
└── <workspace-hash>/
    ├── workspace.json
    ├── GitHub.copilot-chat/
    │   └── transcripts/
    │       └── <session-id>.jsonl
    ├── chatSessions/
    │   └── <session-id>.jsonl
    └── chatEditingSessions/
        └── <session-id>/state.json
```

The transcript JSONL file is the primary conversation source.

## Workspace Storage Roots

Default roots:

| Platform | Roots |
|----------|-------|
| macOS | `~/Library/Application Support/Code/User/workspaceStorage`, `~/Library/Application Support/Code - Insiders/User/workspaceStorage` |
| Linux | `~/.config/Code/User/workspaceStorage`, `~/.config/Code - Insiders/User/workspaceStorage`, `~/.vscode-server/data/User/workspaceStorage` |
| Windows | `%APPDATA%/Code/User/workspaceStorage`, `%APPDATA%/Code - Insiders/User/workspaceStorage` |

For WSL reading Windows data, the Windows root is reachable through the mounted
Windows home, for example:

```text
/mnt/c/Users/<user>/AppData/Roaming/Code/User/workspaceStorage
```

## Transcript Events

VS Code Copilot transcript files are newline-delimited JSON event streams.
Common event types include:

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
- `session.shutdown`
- `session.resume`
- `system.notification`

These events resemble Copilot CLI events but are not treated as the same
storage format. Parse them through a dedicated `copilot-vscode` backend.

## Workspace Matching

Use this order:

1. Sibling `workspace.json` `folder` URI.
2. `session.start.data.context.cwd`, if present.
3. Workspace-storage hash directory as a fallback.

`workspace.json` folder values are file URIs and must be decoded before
matching.

## Optional Sources

`chatSessions/*.jsonl` is a VS Code incremental patch stream. It can be used
as a future enrichment source for request details, raw tool output, and UI
state, but the transcript file remains the first implementation target.

`chatEditingSessions/*/state.json` can contain edit checkpoints and file state.
It is not required for session list, basic export, or basic stats.

`globalStorage/github.copilot-chat/agent-traces.db` can provide better token
accounting when OpenTelemetry DB export is enabled. It should be implemented as
a stats enrichment source, not as the primary transcript source.

## Message Normalization

| VS Code Copilot event | Normalized role |
|-----------------------|-----------------|
| `user.message` | `user` |
| `assistant.message` | `assistant` |
| `system.message` / `system.notification` | `system` |
| `tool.execution_start` | `tool` call |
| `tool.execution_complete` | `tool` result |

Unknown events must not abort parsing.

## Limitations

No public canonical schema for the VS Code transcript file has been found.
Fixtures and parser tests are required before expanding support beyond the
observed event shapes.

Local, WSL, and Windows filesystem sources are supported. SSH remote VS Code
Copilot discovery is not implemented yet.
