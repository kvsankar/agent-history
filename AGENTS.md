# Supported Coding Agents

This document compares the AI coding agents supported by `cagelens` and explains how they work with this tool.

## Quick Comparison

| Feature | Claude Code | Codex CLI | Gemini CLI | Pi | Copilot CLI | VS Code Copilot |
|---------|-------------|-----------|------------|----|-------------|-----------------|
| **Developer** | Anthropic | OpenAI | Google | Pi | GitHub | GitHub |
| **Session Format** | JSONL | JSONL | JSON / JSONL | JSONL | JSONL | JSONL |
| **Storage Location** | `~/.claude/projects/` | `~/.codex/sessions/` | `~/.gemini/tmp/` | `~/.pi/agent/sessions/` | `~/.copilot/session-state/` | VS Code `workspaceStorage/` |
| **Organization** | By workspace path | By date (YYYY/MM/DD) | By project hash | By workspace path | By session ID | By workspace hash |
| **Workspace ID** | Encoded path | Extracted from session | SHA-256 of path | Session `cwd` or encoded path | `workspace.yaml` or event `cwd` | `workspace.json` folder URI |
| **Built-in Export** | None | None | `/chat share` | `pi agent session export` | None | None |
| **Token Tracking** | Per-message | Per-turn | Per-message | Per-message when present | Output tokens when present | Output tokens in transcript; richer OTel data when enabled |
| **Reasoning/Thoughts** | Not stored | Not stored | Stored | Stored when present | Stored when present | Stored when present |

## Storage Locations

### Claude Code

```
~/.claude/projects/
└── -home-user-myproject/           # Encoded workspace path
    ├── <uuid>.jsonl                # Main conversation
    └── agent-<id>.jsonl            # Task subagent sessions
```

- **Workspace naming**: Path encoded with dashes (e.g., `/home/user/myproject` → `-home-user-myproject`)
- **Session files**: UUID-named JSONL files
- **Subagents**: Separate files prefixed with `agent-`

### Codex CLI

```
~/.codex/sessions/
└── 2025/12/15/                     # Date-based organization
    └── rollout-<timestamp>.jsonl   # Session file
```

- **Workspace naming**: Extracted from `cwd` field in session metadata
- **Session files**: Timestamp-prefixed JSONL files
- **Date organization**: Sessions grouped by YYYY/MM/DD folders

### Gemini CLI

```
~/.gemini/tmp/
└── <sha256-hash>/                  # Hash of project path
    └── chats/
        └── session-<id>.json       # Session file (single JSON)
```

- **Workspace naming**: SHA-256 hash of absolute project path
- **Session files**: JSON files (not JSONL) containing full session
- **Hash index**: `cagelens` maintains a hash→path index for readable display

### Pi

```
~/.pi/agent/sessions/
└── --home-user-myproject--/        # Encoded workspace path
    └── <session-id>.jsonl          # Session file
```

- **Workspace naming**: Read from the session `cwd` header when available; otherwise decoded from the workspace folder
- **Session files**: JSONL files with a `session` header and `message` entries
- **Tool calls**: Assistant tool calls and tool execution results are preserved

### Copilot CLI

```
~/.copilot/session-state/
└── <session-id>/
    ├── events.jsonl               # Event stream transcript
    └── workspace.yaml             # Workspace metadata
```

- **Workspace naming**: Read from `workspace.yaml` `cwd`; falls back to
  `session.start.data.context.cwd`
- **Session files**: `events.jsonl` event streams
- **Tool calls**: `tool.execution_start` and `tool.execution_complete` are preserved
- **Subagents**: `agentId`, `subagent.started`, and `subagent.completed` are preserved

### VS Code Copilot

```
<VS Code user data>/User/workspaceStorage/
└── <workspace-hash>/
    ├── workspace.json
    └── GitHub.copilot-chat/
        └── transcripts/
            └── <session-id>.jsonl
```

- **Workspace naming**: Read from sibling `workspace.json` folder URI
- **Session files**: JSONL transcript event streams
- **Tool calls**: `tool.execution_start` and `tool.execution_complete` are preserved
- **Additional state**: `chatSessions`, `chatEditingSessions`, and
  `agent-traces.db` may be used as future enrichment sources

## How cagelens Works with Each Agent

### Listing Sessions (`session list`)

```bash
# All agents (auto-detect)
cagelens session list /home/user/myproject

# Specific agent
cagelens --agent claude session list /home/user/myproject
cagelens --agent codex session list /home/user/myproject
cagelens --agent gemini session list /home/user/myproject
cagelens --agent pi session list /home/user/myproject
cagelens --agent copilot-cli session list /home/user/myproject
cagelens --agent copilot-vscode session list /home/user/myproject
```

| Behavior | Claude | Codex | Gemini | Pi | Copilot CLI | VS Code Copilot |
|----------|--------|-------|--------|----|-------------|-----------------|
| Pattern matching | On encoded path | On workspace path | On path or hash | On session `cwd` or encoded path | On workspace `cwd` | On `workspace.json` folder URI |
| Date filtering | File mtime | File mtime | File mtime | File mtime | File mtime | File mtime |
| Message count | From JSONL | From JSONL | From JSON/JSONL | From JSONL | From JSONL event stream | From JSONL transcript |

### Exporting Sessions (`session export`)

```bash
# Export to markdown
cagelens session export /home/user/myproject -o ./output

# Agent-specific export
cagelens --agent gemini session export /home/user/myproject -o ./output
cagelens --agent pi session export /home/user/myproject -o ./output
cagelens --agent copilot-cli session export /home/user/myproject -o ./output
cagelens --agent copilot-vscode session export /home/user/myproject -o ./output
```

| Feature | Claude | Codex | Gemini | Pi | Copilot CLI | VS Code Copilot |
|---------|--------|-------|--------|----|-------------|-----------------|
| Output format | Markdown | Markdown | Markdown | Markdown | Markdown | Markdown |
| Metadata | Full (UUIDs, tokens, etc.) | Basic (workspace, timestamps) | Full (tokens, thoughts) | Session header, timestamps, model/tokens when present | Event IDs, timestamps, model/output tokens when present | Event IDs, timestamps, model/output tokens when present |
| Tool calls | Preserved | Preserved | Preserved | Preserved | Preserved | Preserved |
| Reasoning steps | N/A | N/A | Included | Included when present | Included when present | Included when present |

### Statistics (`stats`)

```bash
# Sync and show stats
cagelens stats --sync
cagelens stats --by tool
cagelens stats --by model
```

| Metric | Claude | Codex | Gemini | Pi | Copilot CLI | VS Code Copilot |
|--------|--------|-------|--------|----|-------------|-----------------|
| Token counts | Input/output/cache | Input/output | Input/output/thoughts | Input/output/cache when present | Output when present | Output when present |
| Tool usage | Full tracking | Full tracking | Full tracking | Parsed from messages | Parsed from tool events | Parsed from tool events |
| Model info | Yes | Yes | Yes | Yes when present | Yes when present | Yes when present |
| Work time | Calculated | Calculated | Calculated | Calculated | Calculated | Calculated |

## Agent-Specific Features

### Claude Code

- **Subagent tracking**: Task tool spawns separate agent sessions linked by parent ID
- **Cache tokens**: Tracks cache creation and read tokens
- **Git integration**: Records git branch in session metadata
- **Version tracking**: Stores Claude Code version

### Codex CLI

- **Incremental indexing**: `cagelens` maintains session→workspace index for O(1) lookups
- **Date-based scanning**: Only scans new date folders since last run
- **CLI version**: Stores Codex CLI version in sessions

### Gemini CLI

- **Reasoning/thoughts**: Captures model's reasoning steps with subjects and descriptions
- **Hash→path index**: `cagelens` progressively learns hash→path mappings
- **Built-in export**: Gemini has `/chat share` command (we provide more features)
- **Bulk indexing**: Use `gemini-index` command to scan directories

### Copilot CLI

- **Event stream**: Reads `events.jsonl` from `.copilot/session-state`
- **Subagent event preservation**: Preserves `agentId`, `subagent.started`, and
  `subagent.completed`
- **Workspace metadata**: Uses `workspace.yaml` before falling back to event `cwd`
- **Scope**: Initial support covers local, WSL, and Windows filesystem sources;
  SSH remote Copilot discovery is not implemented yet

### VS Code Copilot

- **Transcript stream**: Reads `GitHub.copilot-chat/transcripts/*.jsonl`
- **Workspace metadata**: Uses sibling `workspace.json` folder URI
- **Optional enrichment**: `chatSessions`, `chatEditingSessions`, and OTel
  `agent-traces.db` are documented future enrichment sources
- **Scope**: Initial support covers local, WSL, and Windows filesystem sources;
  SSH remote Copilot discovery is not implemented yet

## Workspace Identification

### Claude Code
Direct path encoding - workspace is immediately identifiable:
```
-home-user-projects-myapp  →  /home/user/projects/myapp
```

### Codex CLI
Workspace extracted from session's `cwd` field:
```jsonl
{"type":"session_meta","payload":{"cwd":"/home/user/myapp"}}
```

### Gemini CLI
SHA-256 hash requires index lookup:
```
abc123def456...  →  (index lookup)  →  /home/user/myapp
```

**Building the Gemini index:**
```bash
# Progressive learning (automatic)
# Index updates when you run cagelens from a Gemini project directory

# Bulk indexing
cagelens gemini-index --add ~/projects    # Scan for .gemini/ folders
```

### Copilot CLI
Workspace extracted from `workspace.yaml`:
```yaml
cwd: /home/user/myapp
```

### VS Code Copilot
Workspace extracted from `workspace.json`:
```json
{"folder": "file:///home/user/myapp"}
```

## Environment Variables

Override default storage locations for testing or custom setups:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLAUDE_PROJECTS_DIR` | `~/.claude/projects/` | Claude Code sessions |
| `CODEX_SESSIONS_DIR` | `~/.codex/sessions/` | Codex CLI sessions |
| `GEMINI_SESSIONS_DIR` | `~/.gemini/tmp/` | Gemini CLI sessions |
| `PI_SESSIONS_DIR` / `PI_CODING_AGENT_SESSION_DIR` | `~/.pi/agent/sessions/` | Pi sessions |
| `COPILOT_CLI_SESSIONS_DIR` / `COPILOT_SESSIONS_DIR` | `~/.copilot/session-state/` | Copilot CLI sessions |
| `COPILOT_VSCODE_WORKSPACE_STORAGE_DIR` | VS Code user `workspaceStorage` | VS Code Copilot transcripts |

## Data Captured by Each Agent

### Message Content

| Data | Claude | Codex | Gemini | Pi | Copilot CLI | VS Code Copilot |
|------|--------|-------|--------|----|-------------|-----------------|
| User messages | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Assistant responses | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tool calls (name, args) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Tool results | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Reasoning/thoughts | ❌ | ❌ | ✅ | ✅ when present | ✅ when present | ✅ when present |

### Metadata

| Data | Claude | Codex | Gemini | Pi | Copilot CLI | VS Code Copilot |
|------|--------|-------|--------|----|-------------|-----------------|
| Session ID | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Timestamps | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Working directory | ✅ | ✅ | ✅ (as hash) | ✅ | ✅ | ✅ |
| Model name | ✅ | ✅ | ✅ | ✅ when present | ✅ when present | ✅ when present |
| Token usage | ✅ | ✅ | ✅ | ✅ when present | Partial | Partial |
| Git branch | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ |
| Agent/CLI version | ✅ | ✅ | ❌ | ✅ when present | ✅ when present | Extension-dependent |

## Limitations and Considerations

### Claude Code
- No built-in export command
- Subagent sessions require parent UUID to link

### Codex CLI
- Date-based storage makes workspace filtering slower (mitigated by indexing)
- No git integration in session metadata

### Gemini CLI
- Hash-based storage obscures workspace paths (mitigated by hash index)
- Single JSON files (not streaming JSONL)
- Format may change as Gemini CLI evolves

### Copilot CLI
- JSONL transcript token data may include output tokens only.
- SSH remote command support is not implemented yet.

### VS Code Copilot
- Transcript format is empirical; no public canonical schema has been found.
- `agent-traces.db` is a future stats enrichment source, not the primary transcript source.
- SSH remote command support is not implemented yet.

## Recommended Workflows

### Multi-Agent Development

If you use multiple coding agents, `cagelens` unifies them:

```bash
# List all sessions from all agents
cagelens session list /home/user/myproject

# Export everything
cagelens session export /home/user/myproject -o ./backup

# Stats across all agents
cagelens stats --sync
cagelens stats --by tool
```

### Gemini-Specific Setup

For best experience with Gemini CLI:

```bash
# Run once to index all your Gemini projects
cagelens gemini-index --add ~/projects

# Now workspace names display as paths instead of hashes
cagelens --agent gemini session list --aw
```

### Cross-Machine Sync

```bash
# Sync from remote machines
cagelens stats --sync --ah -r user@workstation

# Export from all sources
cagelens session export --project myproject --ah -o ./consolidated
```

## See Also

- [usage.md](docs/user/usage.md) - Full command reference
- [claude-code-format.md](docs/specs/agents/formats/claude-code-format.md) - Claude Code session format details
- [codex-cli-format.md](docs/specs/agents/formats/codex-cli-format.md) - Codex CLI session format details
- [gemini-cli-format.md](docs/specs/agents/formats/gemini-cli-format.md) - Gemini CLI session format details
- [copilot-cli-format.md](docs/specs/agents/formats/copilot-cli-format.md) - Copilot CLI session format details
- [copilot-vscode-format.md](docs/specs/agents/formats/copilot-vscode-format.md) - VS Code Copilot transcript details
- [TESTING.md](TESTING.md) - Test matrix and Windows runner guidance
