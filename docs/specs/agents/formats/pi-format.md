# Pi Session Format

<!-- doc-meta
doc_role: spec
audience: contributor
lifecycle: current
content_type: api
surface: integration
canonicality: primary
-->

> **Status**: Refreshed 2026-06-04 from current public Pi docs/source. Pi
> sessions are versioned tree JSONL; this page describes the supported current
> shape plus compatibility behavior. See
> [schema-refresh-2026-06-04.md](../../../analysis/schema-refresh-2026-06-04.md).

Pi stores coding-agent sessions as JSONL under:

```text
~/.pi/agent/sessions/
└── --home-user-myproject--/
    └── <timestamp>_<session-id>.jsonl
```

`cagelens` reads the session `cwd` from the file when available. If the
file does not include a usable workspace path, it falls back to decoding the
workspace directory name.

## File Structure

Pi session files are newline-delimited JSON. The first relevant record is
usually a session header, followed by message records.

```jsonl
{"type":"session","version":3,"id":"session-id","timestamp":"...","cwd":"/home/user/myproject"}
{"type":"message","message":{"role":"user","content":"..."}}
{"type":"message","message":{"role":"assistant","content":[...]}}
```

The format can include:

- `session` entries with session ID, workspace, version, and timestamps.
- tree links via `id` and `parentId`;
- `message` entries with user, assistant, tool, or execution content.
- `model_change`, `thinking_level_change`, `compaction`,
  `branch_summary`, `custom`, `custom_message`, `label`, and
  `session_info` entries.
- Assistant tool-call blocks.
- Tool result and bash execution messages.
- Thinking/reasoning blocks when Pi records them.
- Token usage metadata when present.

## Normalization

`cagelens` maps Pi records into the same session/message model used for
Claude Code, Codex CLI, and Gemini CLI:

- user and assistant messages become conversation turns;
- tool calls and tool results are preserved for Markdown and HTML exports;
- bash commands and outputs are rendered as tool actions;
- thinking blocks are retained in normalized detail data when present;
- token, model, and version metadata are captured when Pi provides them.

## Subagents and Branch Lineage

Pi core session files expose tree relationships with message `id` and
`parentId`, which `cagelens` treats as conversation branch lineage. These
records are not enough by themselves to identify a true child-agent invocation.

Public Pi docs describe extension tools and packages as the mechanism for
custom behavior. Published Pi subagent packages such as `pi-subagents` and
`pi-sub-agent` add delegation by installing an extension that registers a
`subagent` tool. Those packages can run child Pi sessions or subprocesses and
return progress, usage, final Markdown output, failure diagnostics, and
structured details, but the exact persisted shape is package-dependent.

For `cagelens`:

- Treat `id` / `parentId` as branch lineage, not subagent lineage.
- Treat normal Pi tool calls/results as timeline action spans.
- Detect Pi subagent tracks only when an extension-provided `subagent` tool
  call/result exposes enough structured child identity and completion data.
- Do not infer native Pi subagent support from branch tree entries alone.

## Workspace Matching

Pi workspaces are matched by readable path when `cwd` is present. Otherwise,
`cagelens` decodes wrapped workspace folder names such as:

```text
--home-user-projects-myapp-- -> /home/user/projects/myapp
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `PI_CODING_AGENT_SESSION_DIR` | Override Pi session directory |
| `PI_CODING_AGENT_DIR` | Override Pi agent config directory |
| `PI_SESSIONS_DIR` | cagelens compatibility/test override for session directory |

## Limitations

Pi is open source, but its persisted session format may evolve. `cagelens`
keeps unknown fields in detail data where practical and treats missing optional
metadata as absent rather than invalid.
