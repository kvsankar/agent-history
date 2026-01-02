# Supported Coding Agents

This document compares the three AI coding agents supported by `agent-history` and explains how they work with this tool.

## Quick Comparison

| Feature | Claude Code | Codex CLI | Gemini CLI |
|---------|-------------|-----------|------------|
| **Developer** | Anthropic | OpenAI | Google |
| **Session Format** | JSONL | JSONL | JSON |
| **Storage Location** | `~/.claude/projects/` | `~/.codex/sessions/` | `~/.gemini/tmp/` |
| **Organization** | By workspace path | By date (YYYY/MM/DD) | By project hash |
| **Workspace ID** | Encoded path | Extracted from session | SHA-256 of path |
| **Built-in Export** | None | None | `/chat share` |
| **Token Tracking** | Per-message | Per-turn | Per-message |
| **Reasoning/Thoughts** | Not stored | Not stored | Stored |

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
- **Hash index**: `agent-history` maintains a hash→path index for readable display

## How agent-history Works with Each Agent

### Listing Sessions (`lss`)

```bash
# All agents (auto-detect)
agent-history lss myproject

# Specific agent
agent-history --agent claude lss myproject
agent-history --agent codex lss myproject
agent-history --agent gemini lss myproject
```

| Behavior | Claude | Codex | Gemini |
|----------|--------|-------|--------|
| Pattern matching | On encoded path | On workspace path | On path or hash |
| Date filtering | File mtime | File mtime | File mtime |
| Message count | From JSONL | From JSONL | From JSON |

### Exporting Sessions (`export`)

```bash
# Export to markdown
agent-history export myproject -o ./output

# Agent-specific export
agent-history --agent gemini export myproject
```

| Feature | Claude | Codex | Gemini |
|---------|--------|-------|--------|
| Output format | Markdown | Markdown | Markdown |
| Metadata | Full (UUIDs, tokens, etc.) | Basic (workspace, timestamps) | Full (tokens, thoughts) |
| Tool calls | Preserved | Preserved | Preserved |
| Reasoning steps | N/A | N/A | Included |

### Statistics (`stats`)

```bash
# Sync and show stats
agent-history stats --sync
agent-history stats --by tool
agent-history stats --by model
```

| Metric | Claude | Codex | Gemini |
|--------|--------|-------|--------|
| Token counts | Input/output/cache | Input/output | Input/output/thoughts |
| Tool usage | Full tracking | Full tracking | Full tracking |
| Model info | Yes | Yes | Yes |
| Work time | Calculated | Calculated | Calculated |

## Agent-Specific Features

### Claude Code

- **Subagent tracking**: Task tool spawns separate agent sessions linked by parent ID
- **Cache tokens**: Tracks cache creation and read tokens
- **Git integration**: Records git branch in session metadata
- **Version tracking**: Stores Claude Code version

### Codex CLI

- **Incremental indexing**: `agent-history` maintains session→workspace index for O(1) lookups
- **Date-based scanning**: Only scans new date folders since last run
- **CLI version**: Stores Codex CLI version in sessions

### Gemini CLI

- **Reasoning/thoughts**: Captures model's reasoning steps with subjects and descriptions
- **Hash→path index**: `agent-history` progressively learns hash→path mappings
- **Built-in export**: Gemini has `/chat share` command (we provide more features)
- **Bulk indexing**: Use `gemini-index` command to scan directories

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
# Index updates when you run agent-history from a Gemini project directory

# Bulk indexing
agent-history gemini-index ~/projects    # Scan for .gemini/ folders
```

## Environment Variables

Override default storage locations for testing or custom setups:

| Variable | Default | Purpose |
|----------|---------|---------|
| `CLAUDE_PROJECTS_DIR` | `~/.claude/projects/` | Claude Code sessions |
| `CODEX_SESSIONS_DIR` | `~/.codex/sessions/` | Codex CLI sessions |
| `GEMINI_SESSIONS_DIR` | `~/.gemini/tmp/` | Gemini CLI sessions |

## Data Captured by Each Agent

### Message Content

| Data | Claude | Codex | Gemini |
|------|--------|-------|--------|
| User messages | ✅ | ✅ | ✅ |
| Assistant responses | ✅ | ✅ | ✅ |
| Tool calls (name, args) | ✅ | ✅ | ✅ |
| Tool results | ✅ | ✅ | ✅ |
| Reasoning/thoughts | ❌ | ❌ | ✅ |

### Metadata

| Data | Claude | Codex | Gemini |
|------|--------|-------|--------|
| Session ID | ✅ | ✅ | ✅ |
| Timestamps | ✅ | ✅ | ✅ |
| Working directory | ✅ | ✅ | ✅ (as hash) |
| Model name | ✅ | ✅ | ✅ |
| Token usage | ✅ | ✅ | ✅ |
| Git branch | ✅ | ❌ | ❌ |
| Agent/CLI version | ✅ | ✅ | ❌ |

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

## Recommended Workflows

### Multi-Agent Development

If you use multiple coding agents, `agent-history` unifies them:

```bash
# List all sessions from all agents
agent-history lss myproject

# Export everything
agent-history export myproject -o ./backup

# Stats across all agents
agent-history stats --sync
agent-history stats --by tool
```

### Gemini-Specific Setup

For best experience with Gemini CLI:

```bash
# Run once to index all your Gemini projects
agent-history gemini-index ~/projects

# Now workspace names display as paths instead of hashes
agent-history --agent gemini lss
```

### Cross-Machine Sync

```bash
# Sync from remote machines
agent-history stats --sync --ah -r user@workstation

# Export from all sources
agent-history export myproject --ah -o ./consolidated
```

## See Also

- [USAGE.md](USAGE.md) - Full command reference
- [CLAUDE-FORMAT.md](CLAUDE-FORMAT.md) - Claude Code session format details
- [CODEX-FORMAT.md](CODEX-FORMAT.md) - Codex CLI session format details
- [GEMINI-FORMAT.md](GEMINI-FORMAT.md) - Gemini CLI session format details
