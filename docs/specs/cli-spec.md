# CLI Specification

Command-line interface specification for `agent-history`.

## Design Principles

1. **Noun-Verb structure**: `agent-history <object> <verb> [args] [flags]`
2. **Orthogonal scopes**: Home and workspace scopes can be combined independently
3. **Sensible defaults**: No args = list, current workspace, local home
4. **Progressive disclosure**: Simple cases are simple, power features available via flags
5. **Flat output**: Tab-separated data with headers for machine parsing

## Command Aliases

Command aliases have been removed. Use the canonical command names: `home`, `ws`, `session`, `project`.

**Previously supported aliases (now removed):**
- `lsh` → Use `home list` instead
- `lsw` → Use `ws list` instead
- `lss` → Use `session list` instead
- `homes` → Use `home` instead
- `workspaces` → Use `ws` instead
- `sessions` → Use `session` instead
- `alias` → Use `project` instead

---

## Objects (Nouns)

| Object | Description | Hierarchy |
|--------|-------------|-----------|
| `home` | Data source/installation | Top level |
| `ws` | Workspace (project directory) | Within home |
| `session` | Conversation file | Within workspace |
| `project` | Named group of workspaces (cross-cutting) | Alias across homes |

### Hierarchy

```
home (local, wsl, windows, web, remote:user@host)
  └── workspace (directory with sessions)
        └── session (conversation .jsonl file)

project = cross-cutting alias that groups workspaces from any home
```

`web` homes require Claude credentials and are included by `--ah` unless excluded.

### Home Types

| Type | Description | Flag |
|------|-------------|------|
| local | Current machine (default) | (none) |
| wsl | Windows Subsystem for Linux | `--wsl` |
| windows | Windows from WSL | `--windows` |
| web | Claude.ai web sessions | `--web` |
| remote | SSH remote host | `-r user@host` |

---

## Verbs (Actions)

| Verb | Description | Applies To |
|------|-------------|------------|
| `list` | Show multiple items (default) | all |
| `show` | Show single item details | all |
| `add` | Add to collection | home, project |
| `remove` | Remove from collection | home, project |
| `export` | Convert to markdown | ws, session, project, home |
| `stats` | Show usage metrics | ws, session, project, home |

### Default Verb

When verb is omitted, `list` is assumed:
```
agent-history home          # = home list
agent-history ws            # = ws list
agent-history session       # = session list
agent-history project       # = project list
```

---

## Data Model

### What Each Command Accesses

| Command | Data Accessed | Source |
|---------|---------------|--------|
| `session list` | Session metadata (agent, home, workspace, filename, mtime, message count) | Session files (JSONL/JSON) |
| `session show` | Session summary (metadata only) | Session file or resolved scope |
| `session export` | Full conversation content (Markdown or NDJSON) | Session files (JSONL/JSON) |
| `ws list` | Aggregated workspace summary (status, counts, last modified) | Resolved scope |
| `session stats` | Aggregate metrics (counts; tokens/tools/time only after `--sync`) | Scope + metrics DB |

### Why Stats Uses a Database

Computing aggregate metrics requires parsing every message in every session file to extract:
- Token counts (input, output, cache)
- Tool usage frequency
- Model breakdown
- Time tracking (gaps between messages)

This is expensive. The metrics database (`~/.agent-history/metrics.db`) caches these computed values; they are populated only when `--sync` is used.

### Sync Behavior

Stats do **not** auto-sync. Use `--sync` to populate the metrics database:

```
session stats --sync             # Syncs local sessions, then shows stats
session stats --sync --agent codex
```

**Sync characteristics:**
- **Manual**: Requires explicit `--sync`
- **Local-only**: Syncs local agent storage, independent of scope/home selection
- **Incremental**: Only processes new/modified files (based on mtime)
- **Additive**: Deleted sessions remain in DB until `reset --db`

`--no-sync` skips the automatic metrics sync for stats.

---

## Scope Modifiers

### Home Scope (for ws and session commands)

| Flag | Description |
|------|-------------|
| (none) | Local home (default) |
| `--wsl` | WSL home |
| `--windows` | Windows home (from WSL) |
| `--web` | Claude.ai web sessions |
| `-r <user@host>` | SSH remote (repeatable) |
| `--home <name>` | Specific saved home by name (repeatable) |
| `--ah` / `--all-homes` | All configured homes |

#### Source Exclusion (with `--ah`)

| Flag | Description |
|------|-------------|
| `--no-wsl` | Skip WSL sources |
| `--no-windows` | Skip Windows sources |
| `--no-remote` | Skip SSH remotes |
| `--no-web` | Skip web sessions |
| `--local` | Local home only |

Notes:
- `--web` includes Claude web sessions; `--no-web` excludes them
- `--no-wsl`, `--no-windows`, `--no-remote` are honored with `--ah`

### Workspace Scope (for session commands)

| Argument/Flag | Description |
|---------------|-------------|
| (none) | Current workspace (from cwd) |
| `<pattern>` | Workspace name pattern (positional, repeatable) |
| `--aw` / `--all-workspaces` | All workspaces |
| `--this` | Current workspace only (override project auto-detection) |

**Pattern matching:**
- Positional patterns use exact matching when path-like (`/`, `-`, or contains `/`), otherwise substring matching
- `-n` patterns always use case-insensitive substring matching
- Multiple patterns: match any

### Project Scope

| Flag | Description |
|------|-------------|
| `--project <name>` | Use workspaces from named project (repeatable) |

Multiple `--project` flags are combined into a single scope.

**Project Auto-Detection:** When running `session`, `ws`, or `export` commands without explicit workspace arguments, if the current directory belongs to a project, the command automatically scopes to that project. Use `--this` to override and target only the current workspace.

```
# In ~/myproject (which is part of project "myproj")
session list                    # Uses project myproj (implicit)
session list --this             # Current workspace only, no project expansion
session list --project other    # Explicit project selection
```

### Cross-Home Access Guard

When accessing non-local homes (`--windows`, `--wsl`, `-r user@host`, `--home <name>`, `--ah`) from within a local workspace, all session verbs (`list`, `export`, `stats`) require either:
1. An explicit workspace pattern (`-n <pattern>`)
2. A project that ties the local workspace to remote workspaces
3. The `--aw` flag (explicitly requesting all workspaces)

**Rationale:** The same path on different machines (e.g., `/home/user/myproject` on local vs remote) may be completely unrelated codebases. Implicit path matching across homes would show misleading results.

```
# In ~/myproject (no project defined)
session list --windows              # ERROR: requires project or pattern
session list --windows -n myproject # OK: explicit pattern
session list -r vm01                # ERROR: requires project or pattern
session list -r vm01 -n myproject   # OK: explicit pattern
session list --ah                   # ERROR: requires project or pattern
session list --ah -n myproject      # OK: explicit pattern
session list --ah --aw              # OK: explicitly requesting all workspaces

# In ~/myproject (part of project "myproj" that includes remote workspaces)
session list --windows              # OK: project ties homes together
session list -r vm01                # OK: project ties homes together
session list --ah                   # OK: project ties homes together
```

**When guard is skipped:**
- Not in a local workspace (no implicit path to match)
- Using `--aw` (explicitly requesting all workspaces)
- Project exists that ties workspaces together

**Allowed examples (guard skipped):**
- Outside any workspace (e.g., in `~/`): `session list --windows --aw`
- In a workspace but explicitly all workspaces: `session list --ah --aw`
- With a project that links homes: `session list --wsl --project myproj`
- Explicit patterns without a project: `session list --windows -n myproj`

### Agent Filter

| Flag | Description |
|------|-------------|
| (none) / `--agent auto` | Auto-detect (default) |
| `--agent claude` | Claude Code sessions only |
| `--agent codex` | Codex CLI sessions only |
| `--agent gemini` | Gemini CLI sessions only |
| `--agent pi` | Pi sessions only |

Applies to all commands: `ws`, `session`, `project`, `home` (for stats/export).

### Combined Scopes

All scope modifiers are orthogonal and can be combined:
```
session list                      # current ws, local home, auto agent
session list --aw                 # all ws, local home
session list --aw --ah            # all ws, all homes
session list -n auth --ah         # pattern "auth", all homes
session list --agent codex        # codex sessions only
session list --ah --agent gemini  # gemini sessions, all homes
```

---

## Command Reference

### home

Manage data sources (local, WSL, Windows, SSH remotes).

```
home [list]                       # List all configured homes
home show <name>                  # Show home details
home add <source>                 # Add a home
home add --wsl                    # Add WSL
home add --windows                # Add Windows
home add --web                    # Add Claude.ai web home
home add user@hostname            # Add SSH remote
home remove <source>              # Remove a home
home export [name]                # Export all sessions from home(s)
home stats [name]                 # Stats for home(s)
```

### ws

Browse workspaces (project directories with sessions).

```
ws [list] [options]               # List workspaces
ws show <path>                    # Show workspace details
ws export <path> [options]        # Export sessions from workspace
ws stats <path> [options]         # Stats for workspace

Options:
  --home <name>                   # Specific home (repeatable)
  --ah, --all-homes               # All homes
  -n, --name <pattern>            # Pattern match workspace names
  -o, --output <dir>              # Output directory (for export)
```

### session

Browse and export conversation sessions.

```
session [list] [options]          # List sessions
session show <id>                 # Show session details
session export [options]          # Export sessions to markdown or NDJSON
session stats [options]           # Stats for sessions

Scope Options:
  <pattern>                       # Workspace pattern (positional, repeatable)
  --aw, --all-workspaces          # All workspaces
  --this                          # Current workspace only (override project)
  --project <name>                # Use workspaces from project
  --home <name>                   # Specific home (repeatable)
  --ah, --all-homes               # All homes
  --wsl                           # WSL home
  --windows                       # Windows home
  --web                           # Include Claude.ai web sessions
  -r <user@host>                  # SSH remote (repeatable)
  --no-wsl, --no-windows, --no-remote, --no-web  # Exclude homes when using --ah

Filter Options:
  --agent <agent>                 # Filter by agent: auto, claude, codex, gemini, pi
  --since <date>                  # Filter by start date (YYYY-MM-DD)
  --until <date>                  # Filter by end date (YYYY-MM-DD)

List Options:
  --counts                        # Include message counts (slower)

Export Options:
  -o, --output <dir>              # Output directory (default: ./ai-chats/)
  --session <id>                  # Export specific session IDs or filenames (repeatable)
  --json                          # Export NDJSON (unified schema) instead of Markdown
  --minimal                       # No metadata
  --split <lines>                 # Split long conversations
  --flat                          # No workspace subdirectories
  --source                        # Include raw source files
  --jobs <n>                      # Parallel export
  --quiet                         # Suppress per-file output
  --force                         # Re-export even if up-to-date

Stats Options:
  --sync                          # Force sync before display
  --no-sync                       # Skip auto-sync (faster, uses cached DB)
  --by <dimension>                # Group by (comma-separated): model, tool, day, workspace, home, agent
  --time                          # Time tracking mode
  --top-ws <n>                    # Limit to top N workspaces
  -H                              # Accepted but currently ignored

Output Options:
  --format <fmt>                  # Output format: table, tsv, json
```

### project

Manage named workspace groups (cross-cutting aliases).

```
project [list]                    # List all projects
project show <name>               # Show project details
project add <name> <workspace>    # Add workspace to project
project add <name> -n <pattern>   # Add by pattern
project add <name> --ah ...       # Add from all homes (local + wsl + windows + remotes + web)
project remove <name> [workspace] # Remove workspace (or entire project)
project export <name> [options]   # Export all sessions in project; accepts --agent
project stats <name> [options]    # Stats for project; accepts --agent
```

Projects are referenced with `--project` flag:
```
session list --project myproject      # List sessions from project workspaces
session export --project myproject    # Export project sessions
session stats --project myproject     # Stats for project
```

---

## Utility Commands

These are top-level commands that don't follow the noun-verb pattern:

| Command | Description |
|---------|-------------|
| `install` | Report install status (compatibility stub in v2) |
| `reset` | Reset stored data (database, config, caches) |
| `fetch` | Pre-fetch remote sessions into local cache |
| `gemini-index` | Manage Gemini CLI hash→path mappings |

```
install                           # Report install status (no filesystem changes)
install --skip-skill              # Skip skill installation
install --skip-cli                # Skip CLI installation
install --skip-settings           # Skip settings update
install --bin-dir ~/.local/bin    # Custom bin directory
install --skill-dir ~/.claude/skills/custom  # Custom skill directory

reset                             # Interactive reset (prompts for confirmation)
reset --db                        # Reset metrics database only
reset --config                    # Reset configuration only
reset --settings                  # Reset caches only

fetch --ah                         # Prefetch from all homes
fetch -r user@host                 # Prefetch from a remote host
fetch --agent codex --ah           # Prefetch Codex sessions

gemini-index                      # List hash→path mappings
gemini-index --add                # Add current directory
gemini-index --add ~/projects     # Add specific path
gemini-index --full-hash          # Show full SHA-256 hashes
```

---

## Environment Variables

Environment variables for testing, automation, and overriding default behavior.

### Configuration

| Variable | Description |
|----------|-------------|
| `AGENT_HISTORY_CONFIG_DIR` | Override config directory (`~/.agent-history/`). Bypasses migration logic. Used for test isolation. |

### Session Data Paths

| Variable | Description |
|----------|-------------|
| `AGENT_HISTORY_HOME` | Override local home directory for session discovery |
| `AGENT_HISTORY_HOME_WSL` | Override WSL home path (skips real WSL probing) |
| `AGENT_HISTORY_HOME_WINDOWS` | Override Windows home path (skips real Windows probing) |
| `CLAUDE_PROJECTS_DIR` | Override Claude Code projects directory |
| `CODEX_SESSIONS_DIR` | Override Codex CLI sessions directory |
| `GEMINI_SESSIONS_DIR` | Override Gemini CLI sessions directory |

### Usage Examples

```bash
# Test isolation: use temporary config directory
AGENT_HISTORY_CONFIG_DIR=/tmp/test-config agent-history session stats

# Testing with mock session data
AGENT_HISTORY_HOME=/tmp/mock-home agent-history session list

# Skip WSL probing in tests
AGENT_HISTORY_HOME_WSL=/tmp/mock-wsl agent-history ws --wsl
```

---

## Examples

### Basic Usage

```bash
# List all workspaces
agent-history ws

# List sessions in current workspace
agent-history session

# Export current workspace sessions
agent-history session export

# Show stats for current workspace
agent-history session stats
```

### Pattern Matching

```bash
# List workspaces matching "auth"
agent-history ws -n auth

# List sessions from workspaces matching "auth"
agent-history session -n auth

# Export sessions from matching workspaces
agent-history session export -n auth -o ./exports
```

### Multi-Home Operations

```bash
# List workspaces from all homes
agent-history ws --aw --ah

# List sessions from WSL
agent-history session --wsl --aw

# List sessions from Windows (from WSL)
agent-history session --windows --aw

# Export from multiple homes
agent-history session export --home local --home remote:vm01

# Stats across all homes
agent-history session stats --ah --aw
```

### Projects

```bash
# Create a project (auto-created on first add)
agent-history project add myproj /home/user/myproject

# Add workspace from WSL/Windows
agent-history project add myproj /home/user/myproject --wsl
agent-history project add myproj /mnt/c/Users/alice/myproject --windows

# Use the project
agent-history session list --project myproj
agent-history session export --project myproj
agent-history session stats --project myproj

# Project auto-detection (when in a project workspace)
agent-history session list              # Auto-detects project
agent-history session list --this       # Override: current workspace only
```

### Export Options

```bash
# Export with date filter
agent-history session export --since 2025-01-01 --until 2025-01-31

# Export with custom output directory
agent-history session export -o ./my-exports

# Export by session ID or filename
agent-history session export --session 550e8400-e29b-41d4 -o ./exports

# Minimal export (no metadata)
agent-history session export --minimal

# Split long conversations
agent-history session export --split 500

# Flat structure (no workspace subdirectories)
agent-history session export --flat

# Include raw source files
agent-history session export --source

# NDJSON export
agent-history session export --json

# Parallel export
agent-history session export --jobs 4

# Quiet mode (suppress per-file output)
agent-history session export --quiet

# Force re-export (ignore timestamps)
agent-history session export --force
```

### Stats Options

```bash
# Summary stats (scope only)
agent-history session stats

# Stats across scopes (no auto-sync)
agent-history session stats --aw             # All workspaces
agent-history session stats --ah             # All homes
agent-history session stats --ah --aw        # Everything

# Sync local metrics before stats
agent-history session stats --sync
agent-history session stats --sync --agent codex

# Add by_day key in JSON output
agent-history session stats --by day --format json

# Time tracking (JSON output, requires --sync)
agent-history session stats --sync --time --format json

# Limit results
agent-history session stats --top-ws 10

# Output format
agent-history session stats --format json
agent-history session stats --format tsv
```

---

## Expected Output

This section documents the output format for each command.

**Format selection:**
- Default: Table format (aligned columns, headers)
- When piped (stdout is not a terminal): TSV (tab-separated)
- `--format tsv`: Force TSV output
- `--format json`: Structured data for programmatic use

### ws list

Lists workspaces with session counts.

**Table (default):**
```
HOME    WORKSPACE                    SESSIONS  STATUS   LAST_MODIFIED
local   /home/user/projects/api           144  ok       2025-01-03 18:15
local   /home/user/projects/my-app         23  ok       2025-01-02 10:30
local   /home/user/projects/deleted        12  missing  2024-12-28 14:22
```

**With multi-home (`--ah` or `-r`):**
```
HOME              WORKSPACE                    SESSIONS  STATUS   LAST_MODIFIED
local             /home/user/projects/api           144  ok       2025-01-03 18:15
remote:vm01       /home/user/projects/api            89  ok       2025-01-02 10:30
wsl:Ubuntu        /home/user/projects/my-app         34  ok       2025-01-01 09:15
```

**Columns:**
| Column | Description |
|--------|-------------|
| HOME | Source identifier: `local`, `wsl:<distro>`, `windows`, `remote:<host>`, `web` |
| WORKSPACE | Decoded workspace path (full path, not short name) |
| SESSIONS | Number of session files in workspace (or `-` if not available) |
| STATUS | `ok` if path exists, `missing` if not, `unknown` for hashed/unresolvable paths |
| LAST MODIFIED | Timestamp of most recent session |

**TSV (`--format tsv`):**
```
HOME	WORKSPACE	SESSIONS	STATUS	LAST_MODIFIED
local	/home/user/projects/api	144	ok	2025-01-03T18:15:00
local	/home/user/projects/my-app	23	ok	2025-01-02T10:30:00
local	/home/user/projects/deleted	12	missing	2024-12-28T14:22:00
```

**JSON (`--format json`):**
```json
[
  {"home": "local", "workspace": "/home/user/projects/api", "session_count": 144, "status": "ok", "last_modified": "2025-01-03T18:15:00"},
  {"home": "local", "workspace": "/home/user/projects/my-app", "session_count": 23, "status": "ok", "last_modified": "2025-01-02T10:30:00"}
]
```

### session list

Lists sessions with metadata.

**Default (table):**
```
AGENT    HOME    WORKSPACE              FILE                                 MESSAGES  DATE
claude   local   /home/user/myproj      550e8400-e29b-41d4-a716.jsonl              127  2025-01-03
claude   local   /home/user/myproj      agent-a1b2c3d4.jsonl                        34  2025-01-03
codex    local   /home/user/other       rollout-173590.jsonl                        89  2025-01-02
```

**With `--ah` (multi-home):**
```
AGENT    HOME        WORKSPACE           FILE                               MESSAGES  DATE
claude   local       /home/user/myproj   550e8400-e29b-41d4.jsonl                127  2025-01-03
claude   wsl:Ubuntu  /home/user/myproj   6ba7b810-9dad-11d1.jsonl                 89  2025-01-02
claude   remote:vm01 /home/user/myproj   agent-a1b2c3d4.jsonl                     34  2025-01-03
```

**Notes:**
- `MESSAGES` is `0` unless `--counts` is used

### session export

Exports sessions to markdown files.

**Default output:**
```
./ai-chats/home/user/myproj/20250103181500_550e8400-e29b.md
./ai-chats/home/user/myproj/20250103174500_agent-a1b2c3d4.md
{'exported': 2, 'skipped': 0, 'failed': 0, 'output_dir': './ai-chats'}
```

**With `--quiet`:**
```
{'exported': 2, 'skipped': 0, 'failed': 0, 'output_dir': './ai-chats'}
```

**Exit codes:**
- `0`: Success (all files exported or skipped)
- `1`: Error (one or more files failed)

**Notes:**
- `--session` restricts export to specific session IDs or filenames

### session stats

Shows usage statistics.

**Summary (default):**
```
Sessions: 144  Messages: 30728

By Agent:
  claude: 140
  codex: 4

By Home:
  local: 144

By Workspace:
  /home/user/myproj: 120
  /home/user/other: 24
```

**Notes:**
- Token/tool/time breakdowns are available in `--format json` after sync (auto unless `--no-sync`)
- `--by` controls which groupings appear in table output; `by_day` is included only when requested

### home list

Lists configured homes.

**Default:**
```
HOME              TYPE      STATUS       SESSIONS
local             local     ok                 45
wsl:Ubuntu        wsl       ok                 23
remote:vm01       remote    configured         12
remote:vm02       remote    configured          0
```

### project list

Lists configured projects.

**Default:**
```
PROJECT       SOURCE                       WORKSPACE             SESSIONS
myproject     local, wsl:Ubuntu, remote:vm01 3 workspaces         45
api-work      local, remote:vm01             2 workspaces         12
```

Note: `SESSIONS` is only populated with `project list --counts`.

### project show

Shows project details.

**Default:**
```
Project: myproject

Total Sessions: 45

  local:
    /home/user/myproject (12 sessions)
  wsl:Ubuntu:
    /home/user/myproject (18 sessions)
  remote:vm01:
    /home/user/myproject (15 sessions)
```

### ws show

Shows workspace details.

**Default:**
```
HOME    WORKSPACE                 SESSIONS  STATUS  LAST_MODIFIED
local   /home/user/claude-history      144  ok      2025-01-03 18:15
```

### session show

Shows session metadata (no full conversation rendering).

**Default (table format):** raw dict rendering.

**With `--format json`:**
```json
{
  "file": "/home/user/.claude/projects/-home-user-myproject/550e8400.jsonl",
  "filename": "550e8400.jsonl",
  "message_count": 127
}
```

### home show

Shows home details.

**Default:**
```
HOME        TYPE    STATUS       SESSIONS
remote:vm01 remote  configured         12
```

### Error Output

Errors are written to stderr.

**Workspace not found:**
```
Error in workspace: Not in a recognized workspace
  Did you mean: Use --aw to list all workspaces or specify a pattern
```

**SSH connection failed:**
```
Error: Cannot connect to vm01 via passwordless SSH
Setup: ssh-copy-id vm01
```

**No sessions found:**
```
No sessions found.
```
