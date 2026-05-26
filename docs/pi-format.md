# Pi Session Format

Pi stores coding-agent sessions as JSONL under:

```text
~/.pi/agent/sessions/
└── --home-user-myproject--/
    └── <timestamp>_<id>.jsonl
```

`agent-history` reads the session `cwd` from the file when available. If the
file does not include a usable workspace path, it falls back to decoding the
workspace directory name.

## File Structure

Pi session files are newline-delimited JSON. The first relevant record is usually
a session header, followed by message records.

```jsonl
{"type":"session","id":"session-id","cwd":"/home/user/myproject","version":"..."}
{"type":"message","message":{"role":"user","content":"..."}}
{"type":"message","message":{"role":"assistant","content":[...]}}
```

The format can include:

- `session` entries with session ID, workspace, version, and timestamps.
- `message` entries with user, assistant, tool, or execution content.
- Assistant tool-call blocks.
- Tool result and bash execution messages.
- Thinking/reasoning blocks when Pi records them.
- Token usage metadata when present.

## Normalization

`agent-history` maps Pi records into the same session/message model used for
Claude Code, Codex CLI, and Gemini CLI:

- user and assistant messages become conversation turns;
- tool calls and tool results are preserved for markdown and HTML exports;
- bash commands and outputs are rendered as tool actions;
- thinking blocks are retained for full-trace HTML detail;
- token, model, and version metadata are captured when Pi provides them.

## Workspace Matching

Pi workspaces are matched by readable path when `cwd` is present. Otherwise,
`agent-history` decodes wrapped workspace folder names such as:

```text
--home-user-projects-myapp--  ->  /home/user/projects/myapp
```

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `PI_CODING_AGENT_SESSION_DIR` | Override Pi session directory |
| `PI_CODING_AGENT_DIR` | Override Pi agent config directory |
| `PI_SESSIONS_DIR` | Compatibility/test override for session directory |

## Limitations

Pi is open source, but its persisted session format may evolve. `agent-history`
keeps unknown fields in trace/detail data where practical and treats missing
optional metadata as absent rather than invalid.
