# GitHub Copilot Local Format Study

<!-- doc-meta
doc_role: research
audience: contributor
lifecycle: current
content_type: findings
surface: integration
canonicality: supporting
-->

This note records the local and public evidence for adding GitHub Copilot
history support to `cagelens`.

## Summary

GitHub Copilot should be treated as two local agent surfaces:

- **Copilot CLI**: terminal agent sessions under `.copilot/session-state/`.
- **VS Code Copilot**: VS Code extension sessions under `workspaceStorage`.

They share some event names, but they are different persisted surfaces. Do not
force them through one storage parser. Normalize after source-specific parsing.

## Public Evidence

Public repositories have independently implemented Copilot history readers:

- `github/copilot-cli` is the public Copilot CLI repository. The installed
  package ships a `schemas/session-events.schema.json` file.
- `getagentseal/codeburn` reads `~/.copilot/session-state/`, VS Code
  `GitHub.copilot-chat/transcripts/`, and optionally
  `globalStorage/github.copilot-chat/agent-traces.db`.
- `russmckendrick/tokenuse` defines separate constants for
  `.copilot/session-state/events.jsonl` and
  `GitHub.copilot-chat/transcripts`.
- `allee-ai/AI_OS` imports VS Code Copilot transcript events into its own
  conversation tables.
- `git-ai-project/git-ai` discovers VS Code transcript streams, infers
  workspaces from sibling `workspace.json`, and treats OTel traces as a
  separate stream.
- Upstream VS Code Copilot source includes OpenTelemetry support and an
  `exportAgentTracesDB` command for `agent-traces.db`.

## Local Evidence

Observed WSL Copilot CLI:

```text
/home/sankar/.copilot/session-state/<session-id>/events.jsonl
/home/sankar/.copilot/session-state/<session-id>/workspace.yaml
/home/sankar/.copilot/session-store.db
```

Observed Windows Copilot CLI:

```text
/mnt/c/Users/kvsan/.copilot/session-state/<session-id>/events.jsonl
/mnt/c/Users/kvsan/.copilot/session-state/<session-id>/workspace.yaml
/mnt/c/Users/kvsan/.copilot/session-store.db
```

Observed Windows VS Code Copilot:

```text
/mnt/c/Users/kvsan/AppData/Roaming/Code/User/workspaceStorage/<hash>/workspace.json
/mnt/c/Users/kvsan/AppData/Roaming/Code/User/workspaceStorage/<hash>/GitHub.copilot-chat/transcripts/<session-id>.jsonl
/mnt/c/Users/kvsan/AppData/Roaming/Code/User/workspaceStorage/<hash>/chatSessions/<session-id>.jsonl
/mnt/c/Users/kvsan/AppData/Roaming/Code/User/workspaceStorage/<hash>/chatEditingSessions/<session-id>/state.json
```

## Copilot CLI Format

The CLI package schema describes event records with:

- `id`
- `timestamp`
- `parentId`
- `agentId`
- `type`
- `data`

Important event types observed locally:

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

`agentId` is absent for the root agent and present for sub-agent instances.
`parentId` links events into the chronological event chain.

## VS Code Copilot Format

VS Code Copilot transcript JSONL files use similar event names, but they live
under VS Code workspace storage and are not the same source as Copilot CLI.

The sibling `workspace.json` maps the opaque workspace-storage hash back to the
workspace folder URI. This is the preferred workspace identity source.

`chatSessions/*.jsonl` files are VS Code incremental patch streams. They can
contain richer UI/request state, but they are not the same as the Copilot
transcript event stream. Use them only as optional enrichment.

`agent-traces.db` is best suited for usage statistics because it can carry
input, output, and cache token counts. It is not sufficient by itself for a
human-readable session export.

## Design Decision

Implement two agent backends:

| Backend | Primary source | Role |
|---------|----------------|------|
| `copilot-cli` | `.copilot/session-state/*/events.jsonl` | CLI transcript export, listing, stats, lineage-ready events |
| `copilot-vscode` | `workspaceStorage/*/GitHub.copilot-chat/transcripts/*.jsonl` | VS Code transcript export/listing; optional stats enrichment later |

Keep VS Code `chatSessions`, `chatEditingSessions`, debug logs, and OTel DB as
secondary sources. They should not block basic transcript support.

## Implementation Notes

- Parse event JSONL defensively. Unknown event types should be preserved in raw
  payload metadata where useful and otherwise skipped.
- For message counts, count visible `user.message` and `assistant.message`
  events only.
- For Markdown/HTML export, represent `tool.execution_start` as tool calls and
  `tool.execution_complete` as tool results.
- For workspace matching:
  - Copilot CLI: prefer `workspace.yaml` `cwd`, then `session.start.data.context.cwd`.
  - VS Code Copilot: prefer sibling `workspace.json` `folder`, then
    `session.start.data.context.cwd` if present.
- Do not read arbitrary sidecar files referenced by events unless they are
  explicitly confined to the session directory.
