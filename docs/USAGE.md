# Command Reference

Detailed documentation for all `claude-history` commands and options.

## Commands Overview

| Command | Description |
|---------|-------------|
| `lsh` | List hosts and manage SSH remotes |
| `lsw` | List workspaces |
| `lss` | List sessions |
| `export` | Export sessions to markdown |
| `alias` | Manage workspace aliases |
| `stats` | Show usage statistics and metrics |
| `reset` | Reset stored data (database, settings, aliases) |

---

## `lsh` - List Hosts & Manage SSH Remotes

List all Claude Code installations and manage SSH remote sources.

```bash
claude-history lsh [--local|--wsl|--windows|--remotes]
claude-history lsh add <user@hostname>
claude-history lsh remove <user@hostname>
claude-history lsh clear
```

**Subcommands:**
- `add <user@hostname>`: Add an SSH remote
- `remove <user@hostname>`: Remove an SSH remote
- `clear`: Remove all SSH remotes

**Filter Options:**
- No flags: Show all (local + WSL + Windows + SSH remotes)
- `--local`: Show only local installation
- `--wsl`: Show only WSL distributions
- `--windows`: Show only Windows users
- `--remotes`: Show only SSH remotes

**Examples:**
```bash
# Show all hosts and SSH remotes
$ claude-history lsh
Local:
  /home/alice/.claude	10 workspaces

SSH Remotes:
  alice@server.example.com

# Add an SSH remote
$ claude-history lsh add alice@server.example.com
Added source: alice@server.example.com

# Remove an SSH remote
$ claude-history lsh remove alice@server.example.com
Removed source: alice@server.example.com

# Show only SSH remotes
$ claude-history lsh --remotes
```

Once configured, `--as` automatically includes saved SSH remotes:
```bash
claude-history lsw --al              # includes saved remotes
claude-history export --al           # exports from all homes
claude-history stats --time --al     # syncs from all homes
```

---

## `lsw` - List Workspaces

List all workspaces matching a pattern.

```bash
claude-history lsw [PATTERN...] [OPTIONS]
```

**Arguments:**
- `PATTERN`: One or more workspace name patterns (optional, lists all if omitted)

**Options:**
- `--wsl`: List WSL workspaces
- `--windows`: List Windows workspaces
- `-r HOST`, `--remote HOST`: List remote workspaces via SSH
- `--as`, `--all-homes`: List from all homes

**Examples:**
```bash
# List all local workspaces
claude-history lsw

# Filter by pattern
claude-history lsw myproject

# Multiple patterns
claude-history lsw proj1 proj2

# List from all homes
claude-history lsw --al -r user@vm01
```

---

## `lss` - List Sessions

Show all sessions for a workspace.

```bash
claude-history lss [PATTERN] [OPTIONS]
```

**Arguments:**
- `PATTERN`: Workspace name pattern (default: current workspace or its alias)

**Scope Options:**
- `--this`: Use current workspace only, not its alias (if aliased)
- `--as`, `--all-homes`: List from all homes (local + WSL/Windows + remotes)

**Date Filtering:**
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Multi-Environment Access:**
- `--wsl`: Access WSL distribution (auto-detects)
- `--windows`: Access Windows user (auto-detects)
- `-r HOST`, `--remote HOST`: Access SSH remote server

**Examples:**
```bash
# List sessions from current workspace (or alias if aliased)
claude-history lss

# Force current workspace only (not alias)
claude-history lss --this

# List sessions from WSL
claude-history lss myproject --wsl

# List sessions from Windows
claude-history lss myproject --windows

# List sessions from SSH remote
claude-history lss myproject -r user@hostname

# Date filtering
claude-history lss myproject --since 2025-11-01
claude-history lss myproject --since 2025-11-01 --until 2025-11-30
```

**Output:**
- List of sessions with metadata (file, messages, date)
- Total size, message count, date range
- Grouped by workspace

---

## `export` - Export Sessions

Export sessions from workspace(s) to markdown with flexible scope control.

```bash
claude-history export [WORKSPACE...] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--as`, `--all-homes`: Export from ALL sources (local + WSL + Windows + remotes)
- `--aw`, `--all-workspaces` (also `-a`, `--all`): Export ALL workspaces
- `--this`: Use current workspace only, not its alias (if aliased)

**Arguments:**
- `WORKSPACE`: One or more workspace patterns (default: current workspace or its alias)

**Options:**
- `-o`, `--output DIR`: Output directory (default: `./claude-conversations`)
- `--wsl`: Export from WSL (auto-detects distribution)
- `--windows`: Export from Windows (auto-detects user)
- `-r`, `--remote HOST`: Add SSH remote source (repeatable)
- `--force`, `-f`: Force re-export all sessions (default: incremental)
- `--since DATE`: Only include sessions modified on or after this date
- `--until DATE`: Only include sessions modified on or before this date
- `--minimal`: Export conversation content only, no metadata
- `--split LINES`: Split long conversations into parts
- `--flat`: Use flat directory structure (default: organized by workspace)

**Orthogonal Design:**

| Command | Workspace Scope | Source Scope |
|---------|----------------|--------------|
| `export` | Current | Local only |
| `export --as` | Current | All sources |
| `export --aw` | All | Local only |
| `export --al --aw` | All | All sources |

**Examples:**
```bash
# Current workspace, local source (default)
claude-history export

# Current workspace, all homes
claude-history export --al

# All workspaces, local source
claude-history export --aw

# All workspaces, all homes
claude-history export --al --aw

# Specific workspace, all homes, custom output
claude-history export myproject --al -o /tmp/backup

# Multiple workspaces (deduplicated)
claude-history export proj1 proj2 -o ./exports

# Export from WSL
claude-history export myproject --wsl

# Export from Windows
claude-history export myproject --windows

# With splitting and minimal mode
claude-history export myproject --minimal --split 500
```

**Output:**
- Markdown files named `{timestamp}_{session-id}.md`
- Source-tagged filenames: `wsl_ubuntu_`, `windows_`, `remote_hostname_`
- Organized by workspace subdirectories (unless `--flat`)

---

## `alias` - Manage Workspace Aliases

Group related workspaces across environments.

```bash
claude-history alias <subcommand> [OPTIONS]
```

**Subcommands:**

### `alias list`
List all defined aliases.

### `alias show <name>`
Show workspaces in an alias.

### `alias create <name>`
Create a new empty alias.

### `alias delete <name>`
Delete an alias.

### `alias add <name> <pattern>`
Add workspaces matching pattern to an alias.

Options:
- `--wsl`: Add from WSL
- `--windows`: Add from Windows
- `-r HOST`: Add from SSH remote
- `--as`: Add from all homes

### `alias remove <name> -- <workspace>`
Remove a workspace from an alias. Use `--` before workspace names starting with `-`.

### `alias export <file>`
Export aliases to JSON file.

### `alias import <file>`
Import aliases from JSON file.

**Examples:**
```bash
# Create and populate an alias
claude-history alias create myproject
claude-history alias add myproject myproject
claude-history alias add myproject --windows myproject
claude-history alias add myproject -r user@vm01 myproject

# Or add from all homes at once
claude-history alias add myproject --al -r user@vm myproject

# Use aliases with @ prefix
claude-history lss @myproject
claude-history export @myproject -o ./backup

# Sync aliases across machines
claude-history alias export aliases.json
claude-history alias import aliases.json
```

**Automatic Alias Scoping:**

When running commands without arguments from an aliased workspace:
```bash
claude-history lss        # Uses alias automatically
claude-history export     # Uses alias automatically
claude-history stats      # Uses alias automatically

# Force current workspace only
claude-history lss --this
```

---

## `stats` - Usage Statistics

Display usage statistics and metrics from synced Claude Code sessions.

```bash
claude-history stats [WORKSPACE] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--as`, `--all-homes`: Sync from all homes first
- `--aw`, `--all-workspaces`: Query all workspaces (default: current)
- `--this`: Use current workspace only, not its alias

**Sync Options:**
- `--sync`: Sync JSONL files to metrics database
- `--force`: Force re-sync all files

**View Options:**
- `--time`: Show time tracking with daily breakdown
- `--tools`: Show tool usage statistics
- `--models`: Show model usage statistics
- `--by-workspace`: Show per-workspace breakdown
- `--by-day`: Show daily statistics

**Filters:**
- `--source SOURCE`: Filter by source (local, wsl:distro, windows, remote:host)
- `--since DATE`: Filter from this date
- `--until DATE`: Filter until this date

**Examples:**
```bash
# Summary dashboard (current workspace)
claude-history stats

# All workspaces
claude-history stats --aw

# Time tracking with auto-sync from all homes
claude-history stats --time --al

# Tool usage statistics
claude-history stats --tools

# Daily trends
claude-history stats --by-day

# Filter by date range
claude-history stats --since 2025-11-01 --until 2025-11-30
```

**Metrics Available:**
- **Sessions**: Total, main vs agent, message counts
- **Tokens**: Input, output, cache creation, cache read, hit ratio
- **Tools**: Usage counts and error rates per tool
- **Models**: Usage distribution across Claude models
- **Workspaces**: Top workspaces by activity (alias-aware)
- **Daily trends**: Session and token usage over time

**Database Location:** `~/.claude-history/metrics.db` (SQLite)

---

## Date Filtering

Both `lss` and `export` support date filtering:

```bash
# Sessions modified on or after a date
claude-history lss myproject --since 2025-11-01

# Sessions within a date range
claude-history export myproject --since 2025-11-01 --until 2025-11-30

# Export recent sessions only
claude-history export myproject --since 2025-11-01 -o ./recent
```

**Notes:**
- Date format: ISO 8601 (`YYYY-MM-DD`)
- Dates are based on file modification time
- `--since` must be before `--until`

---

## Export Modes

### Full Export (Default)

Preserves all information:
- Message content (text, tool use inputs, tool results)
- All metadata (UUIDs, session IDs, working directory, git branch, etc.)
- Model information and token usage statistics
- Parent/child message relationships with clickable navigation links

### Minimal Export (`--minimal`)

Clean output for sharing:
- Message text content
- Tool use inputs (full JSON)
- Tool results (complete output)
- Timestamps

Omits:
- All metadata sections
- HTML anchors and navigation links
- Model information and token usage

### Conversation Splitting (`--split`)

Split long conversations into multiple parts:

```bash
claude-history export myproject --split 500
```

- Smart break points (before User messages, after tool results, time gaps)
- Navigation links between parts
- Each part shows message range

---

## Remote Operations

### SSH Remote Access

```bash
# List remote workspaces
claude-history lsw -r user@server

# List sessions from remote
claude-history lss myproject -r user@server

# Export from remote
claude-history export myproject -r user@server
```

**Requirements:**
- Passwordless SSH key setup
- `rsync` installed on both machines

### WSL Access (from Windows)

```bash
python claude-history lsw --wsl
python claude-history lss myproject --wsl
python claude-history export myproject --wsl
```

### Windows Access (from WSL)

```bash
claude-history lsw --windows
claude-history lss myproject --windows
claude-history export myproject --windows
```

---

## `reset` - Reset Stored Data

Delete metrics database, settings (SSH remotes), and/or aliases.

```bash
claude-history reset [what] [--force]
```

**Arguments:**
- `what`: What to reset (optional, default: `all`)
  - `db`: Delete metrics database only
  - `settings`: Delete SSH remote configuration only
  - `aliases`: Delete aliases only
  - `all`: Delete everything (default)

**Options:**
- `-y`, `--yes`: Skip confirmation prompt

**Examples:**
```bash
# Reset everything (prompts for confirmation)
claude-history reset

# Reset only metrics database
claude-history reset db

# Reset without confirmation (for scripts)
claude-history reset -y
claude-history reset db -y
```

**Files affected:**
- `~/.claude-history/metrics.db` - Metrics database (stats, time tracking)
- `~/.claude-history/config.json` - Settings (SSH remotes)
- `~/.claude-history/aliases.json` - Workspace aliases
