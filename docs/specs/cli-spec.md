# CLI Specification

Command-line interface specification for `agent-history`.

## Design Principles

1. **Noun-Verb structure**: `agent-history <object> <verb> [args] [flags]`
2. **Orthogonal scopes**: Home and workspace scopes can be combined independently
3. **Sensible defaults**: No args = list, current workspace, local home
4. **Progressive disclosure**: Simple cases are simple, power features available via flags
5. **Flat output**: Tab-separated data with headers for machine parsing

## Command Aliases

For convenience, short aliases are available:

| Primary | Aliases |
|---------|---------|
| `ws` | - |
| `session` | - |
| `home` | `homes`, `lsh` |
| `project` | `projects`, `alias` |

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
| `session list` | File metadata (name, size, mtime, message count) | JSONL files |
| `session show` | Full conversation content | JSONL file |
| `session export` | Full conversation content | JSONL files |
| `ws list` | Directory listing with session counts | Filesystem |
| `session stats` | Aggregate metrics (tokens, tools, models, time) | Metrics DB |

### Why Stats Uses a Database

Computing aggregate metrics requires parsing every message in every session file to extract:
- Token counts (input, output, cache)
- Tool usage frequency
- Model breakdown
- Time tracking (gaps between messages)

This is expensive. The metrics database (`~/.agent-history/metrics.db`) caches these computed values for fast querying.

### Auto-Sync Behavior

**Stats automatically syncs the scope being queried:**

```
session stats                    # Syncs current workspace, then shows stats
session stats --aw               # Syncs all local workspaces, then shows stats
session stats --ah               # Syncs current workspace from all homes
session stats --ah --aw          # Syncs everything, then shows stats
```

**Sync characteristics:**
- **Automatic**: No explicit `--sync` needed
- **Scope-aware**: Only syncs workspaces being queried
- **Incremental**: Only processes new/modified files (based on mtime)
- **Additive**: Deleted sessions remain in DB until `reset --db`

**Skip sync for speed:**
```
session stats --no-sync          # Query cached data only (faster, may be stale)
```

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

### Workspace Scope (for session commands)

| Argument/Flag | Description |
|---------------|-------------|
| (none) | Current workspace (from cwd) |
| `<pattern>` | Workspace name pattern (positional, repeatable) |
| `--aw` / `--all-workspaces` | All workspaces |
| `--this` | Current workspace only (override project auto-detection) |

**Pattern matching:**
- Patterns match against workspace names (case-insensitive substring)
- Multiple patterns: match any
- Empty pattern or `*` or `all`: match all workspaces

### Project Scope

| Flag | Description |
|------|-------------|
| `--project <name>` | Use workspaces from named project |

**Project Auto-Detection:** When running `session`, `ws`, or `export` commands without explicit workspace arguments, if the current directory belongs to a project, the command automatically scopes to that project. Use `--this` to override and target only the current workspace.

```
# In ~/myproject (which is part of project "myproj")
session list                    # → stderr: "Using project myproj (use --this for current workspace only)"
session list --this             # Current workspace only, no project expansion
session list --project other    # Explicit project selection
```

### Cross-Home Access Guard

When accessing non-local homes (`--windows`, `--wsl`, `-r user@host`, `--ah`) from within a local workspace, all session verbs (`list`, `export`, `stats`) require either:
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

### Agent Filter

| Flag | Description |
|------|-------------|
| (none) / `--agent auto` | Auto-detect (default) |
| `--agent claude` | Claude Code sessions only |
| `--agent codex` | Codex CLI sessions only |
| `--agent gemini` | Gemini CLI sessions only |

Applies to all commands: `ws`, `session`, `project`, `home` (for stats/export).

### Combined Scopes

All scope modifiers are orthogonal and can be combined:
```
session list                      # current ws, local home, auto agent
session list --aw                 # all ws, local home
session list --ah                 # current ws, all homes
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
home add --web                    # Add Claude.ai web sessions
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
session export [options]          # Export sessions to markdown
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
  --web                           # Claude.ai web sessions
  -r <user@host>                  # SSH remote (repeatable)
  --no-wsl, --no-windows, --no-remote, --no-web  # Exclude sources (with --ah)

Filter Options:
  --agent <agent>                 # Filter by agent: auto, claude, codex, gemini
  --since <date>                  # Filter by start date (YYYY-MM-DD)
  --until <date>                  # Filter by end date (YYYY-MM-DD)

List Options:
  --counts                        # Include message counts (slower)

Export Options:
  -o, --output <dir>              # Output directory (default: ./ai-chats/)
  --minimal                       # No metadata
  --split <lines>                 # Split long conversations
  --flat                          # No workspace subdirectories
  --source                        # Include raw source files
  --jobs <n>                      # Parallel export
  --quiet                         # Suppress per-file output
  --force                         # Re-export even if up-to-date

Stats Options:
  --sync                          # Force sync before display
  --by <dimension>                # Group by: model, tool, day, workspace, home, agent
  --time                          # Time tracking mode
  --top-ws <n>                    # Limit to top N workspaces
  -H                              # Human-readable numbers

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
project add <name> --ah ...       # Add from all homes
project remove <name> [workspace] # Remove workspace (or entire project)
project export <name> [options]   # Export all sessions in project
project stats <name> [options]    # Stats for project
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
| `install` | Install CLI to PATH and Claude skill |
| `reset` | Reset stored data (database, config, projects) |
| `gemini-index` | Manage Gemini CLI hash→path mappings |

```
install                           # Install CLI + skill + retention settings
install --skip-skill              # Skip skill installation
install --skip-cli                # Skip CLI installation
install --skip-settings           # Skip settings update
install --bin-dir ~/.local/bin    # Custom bin directory
install --skill-dir ~/.claude/skills/custom  # Custom skill directory

reset                             # Interactive reset (prompts for confirmation)
reset --db                        # Reset metrics database only
reset --config                    # Reset configuration only

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
agent-history ws --ah

# List sessions from WSL
agent-history session --wsl

# List sessions from Windows (from WSL)
agent-history session --windows

# List Claude.ai web sessions
agent-history session --web

# Export from multiple homes
agent-history session export --home local --home remote:vm01

# Export from all homes except remotes
agent-history session export --ah --no-remote

# Stats across all homes
agent-history session stats --ah --aw
```

### Projects

```bash
# Create a project (auto-created on first add)
agent-history project add myproj -n myproject

# Add workspace from remote
agent-history project add myproj -n myproject -r vm01

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

# Export single session
agent-history session export <session-id>

# Minimal export (no metadata)
agent-history session export --minimal

# Split long conversations
agent-history session export --split 500

# Flat structure (no workspace subdirectories)
agent-history session export --flat

# Include raw source files
agent-history session export --source

# Parallel export
agent-history session export --jobs 4

# Quiet mode (suppress per-file output)
agent-history session export --quiet

# Force re-export (ignore timestamps)
agent-history session export --force
```

### Stats Options

```bash
# Summary stats (auto-syncs current workspace)
agent-history session stats

# Stats across scopes (auto-syncs each scope)
agent-history session stats --aw             # All workspaces
agent-history session stats --ah             # All homes
agent-history session stats --ah --aw        # Everything

# Skip sync for speed (use cached data)
agent-history session stats --no-sync

# Group by dimension
agent-history session stats --by model
agent-history session stats --by tool
agent-history session stats --by day
agent-history session stats --by workspace
agent-history session stats --by home,agent    # Multi-dimension

# Time tracking
agent-history session stats --time

# Limit results
agent-history session stats --top-ws 10

# Human-readable numbers
agent-history session stats -H

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
HOME    WORKSPACE                    SESSIONS  STATUS   LAST MODIFIED
local   /home/user/projects/api           144  ok       2025-01-03 18:15
local   /home/user/projects/my-app         23  ok       2025-01-02 10:30
local   /home/user/projects/deleted        12  missing  2024-12-28 14:22
```

**With multi-home (`--ah` or `-r`):**
```
HOME              WORKSPACE                    SESSIONS  STATUS   LAST MODIFIED
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
  {"home": "local", "workspace": "/home/user/projects/api", "sessions": 144, "status": "ok", "last_modified": "2025-01-03T18:15:00"},
  {"home": "local", "workspace": "/home/user/projects/my-app", "sessions": 23, "status": "ok", "last_modified": "2025-01-02T10:30:00"}
]
```

### session list

Lists sessions with metadata.

**Default (table):**
```
SESSION                                   MESSAGES  SIZE      MODIFIED
550e8400-e29b-41d4-a716-446655440000           127  45.2 KB   2025-01-03 18:15
agent-a1b2c3d4                                  34  12.1 KB   2025-01-03 17:45
6ba7b810-9dad-11d1-80b4-00c04fd430c8            89  28.7 KB   2025-01-02 10:30
```

**With `--ah` (multi-home):**
```
HOME              WORKSPACE       SESSION                             MESSAGES  SIZE
local             claude-history  550e8400-e29b-41d4-a716-446655...        127  45.2 KB
wsl:Ubuntu        claude-history  6ba7b810-9dad-11d1-80b4-00c04f...         89  28.7 KB
remote:vm01       my-project      agent-a1b2c3d4                            34  12.1 KB
```

### session export

Exports sessions to markdown files.

**Default output:**
```
Exporting 3 sessions to ./ai-chats/claude-history/
  ✓ 20250103181500_550e8400-e29b.md (127 messages)
  ✓ 20250103174500_agent-a1b2c3d4.md (34 messages)
  ○ 20250102103000_6ba7b810-9dad.md (skipped, up-to-date)
Exported: 2, Skipped: 1, Failed: 0
```

**With `--quiet`:**
```
Exported: 2, Skipped: 1, Failed: 0
```

**Exit codes:**
- `0`: Success (all files exported or skipped)
- `1`: Error (one or more files failed)

### session stats

Shows usage statistics.

**Summary (default):**
```
Statistics for claude-history (local)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Sessions:        144
Messages:     30,728
  User:       12,456
  Assistant:  18,272

Tokens:    4,521,890
  Input:   1,234,567
  Output:  3,287,323

Top Models:
  claude-sonnet-4-5-20250929     89%
  claude-opus-4-5-20250919       11%

Top Tools:
  Read          8,234 calls
  Edit          5,123 calls
  Bash          3,456 calls
```

**With `--by tool`:**
```
TOOL              CALLS     TOKENS
Read              8,234    234,567
Edit              5,123    189,012
Bash              3,456    156,789
Grep              2,345     89,012
Write             1,234     67,890
```

**With `--by day`:**
```
DATE          SESSIONS  MESSAGES    TOKENS
2025-01-03          12       456    45,678
2025-01-02          15       789    78,901
2025-01-01           8       234    23,456
```

**With `--time`:**
```
Time Tracking for claude-history
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Total Time:   45h 23m
Active Days:       12

Daily Breakdown:
DATE          TIME      SESSIONS
2025-01-03   4h 12m          12
2025-01-02   5h 45m          15
2025-01-01   2h 30m           8
```

### home list

Lists configured homes.

**Default:**
```
HOME              TYPE      STATUS    WORKSPACES
local             local     ✓              45
wsl:Ubuntu        wsl       ✓              23
remote:vm01       ssh       ✓              12
remote:vm02       ssh       ✗ unreachable   -
```

### project list

Lists configured projects.

**Default:**
```
PROJECT       WORKSPACES  HOMES
myproject              3  local, wsl:Ubuntu, remote:vm01
api-work               2  local, remote:vm01
```

### project show

Shows project details.

**Default:**
```
Project: myproject

Workspaces:
  local             /home/user/myproject
  wsl:Ubuntu        /home/user/myproject
  remote:vm01       /home/user/myproject

Sessions: 45
Last Modified: 2025-01-03 18:15
```

### ws show

Shows workspace details.

**Default:**
```
Workspace: claude-history
Path: /home/user/claude-history
Home: local

Sessions:        144
Messages:     30,728
Last Modified: 2025-01-03 18:15

Recent Sessions:
  550e8400-e29b-41d4...  127 messages  2025-01-03 18:15
  agent-a1b2c3d4          34 messages  2025-01-03 17:45
  6ba7b810-9dad-11d1...   89 messages  2025-01-02 10:30
```

### session show

Shows session details (full conversation).

**Default:**
```
Session: 550e8400-e29b-41d4-a716-446655440000
Workspace: claude-history
Home: local
Agent: claude

Started: 2025-01-03 10:15:00
Ended: 2025-01-03 18:15:00
Duration: 8h 0m (effort: 2h 15m)

Messages: 127 (52 user, 75 assistant)
Tokens: 45,678 (input: 12,345, output: 33,333)
Tools: Read (45), Edit (23), Bash (12)

--- Conversation ---

[Message 1] User | 2025-01-03 10:15:00
Help me fix this bug...

[Message 2] Assistant | 2025-01-03 10:15:05
I'll help you fix that bug...
```

### home show

Shows home details.

**Default:**
```
Home: remote:vm01
Type: ssh
Host: user@vm01
Status: ✓ connected

Workspaces: 12
Sessions: 156
Last Synced: 2025-01-03 18:00

Top Workspaces:
  my-project         45 sessions
  api-server         23 sessions
  docs               12 sessions
```

### Error Output

Errors are written to stderr.

**Workspace not found:**
```
Error: Workspace 'nonexistent' not found

Did you mean one of these?
  - my-project
  - my-other-project
```

**SSH connection failed:**
```
Error: Cannot connect to remote 'vm01'
  SSH connection failed: Connection refused
```

**No sessions found:**
```
No sessions found matching criteria.
```

**Project auto-detection notice (stderr):**
```
Using project myproj (use --this for current workspace only)
```
