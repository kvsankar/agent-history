# Command Reference

Detailed documentation for all `claude-history` commands and options.

## Commands Overview

| Command | Description |
|---------|-------------|
| `lsh` | List hosts (local, WSL, Windows installations) |
| `lsw` | List workspaces |
| `lss` | List sessions |
| `export` | Export sessions to markdown |
| `alias` | Manage workspace aliases |
| `sources` | Manage saved SSH remote sources |
| `stats` | Show usage statistics and metrics |

---

## `lsh` - List Hosts

List all Claude Code installations across local, WSL, and Windows environments.

```bash
./claude-history lsh [--local|--wsl|--windows]
```

**Options:**
- No flags: Show all hosts (local + WSL + Windows)
- `--local`: Show only local installation
- `--wsl`: Show only WSL distributions
- `--windows`: Show only Windows users

**Examples:**
```bash
# Show all hosts
$ ./claude-history lsh
Local:
  /home/alice/.claude	10 workspaces

WSL Distributions:
  Ubuntu          alice           5 workspaces     \\wsl.localhost\Ubuntu\home\alice\.claude\projects

Windows Users:
  alice       /mnt/c/Users/alice        16 workspaces

# Show only WSL distributions
$ ./claude-history lsh --wsl
```

---

## `lsw` - List Workspaces

List all workspaces matching a pattern.

```bash
./claude-history lsw [PATTERN...] [OPTIONS]
```

**Arguments:**
- `PATTERN`: One or more workspace name patterns (optional, lists all if omitted)

**Options:**
- `--wsl`: List WSL workspaces
- `--windows`: List Windows workspaces
- `-r HOST`, `--remote HOST`: List remote workspaces via SSH
- `--as`, `--all-sources`: List from all sources

**Examples:**
```bash
# List all local workspaces
./claude-history lsw

# Filter by pattern
./claude-history lsw myproject

# Multiple patterns
./claude-history lsw proj1 proj2

# List from all sources
./claude-history lsw --as -r user@vm01
```

---

## `lss` - List Sessions

Show all sessions for a workspace.

```bash
./claude-history lss [PATTERN] [OPTIONS]
```

**Arguments:**
- `PATTERN`: Workspace name pattern (default: current workspace or its alias)

**Scope Options:**
- `--this`: Use current workspace only, not its alias (if aliased)
- `--as`, `--all-sources`: List from all sources (local + WSL/Windows + remotes)

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
./claude-history lss

# Force current workspace only (not alias)
./claude-history lss --this

# List sessions from WSL
./claude-history lss myproject --wsl

# List sessions from Windows
./claude-history lss myproject --windows

# List sessions from SSH remote
./claude-history lss myproject -r user@hostname

# Date filtering
./claude-history lss myproject --since 2025-11-01
./claude-history lss myproject --since 2025-11-01 --until 2025-11-30
```

**Output:**
- List of sessions with metadata (file, messages, date)
- Total size, message count, date range
- Grouped by workspace

---

## `export` - Export Sessions

Export sessions from workspace(s) to markdown with flexible scope control.

```bash
./claude-history export [WORKSPACE...] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--as`, `--all-sources`: Export from ALL sources (local + WSL + Windows + remotes)
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
| `export --as --aw` | All | All sources |

**Examples:**
```bash
# Current workspace, local source (default)
./claude-history export

# Current workspace, all sources
./claude-history export --as

# All workspaces, local source
./claude-history export --aw

# All workspaces, all sources
./claude-history export --as --aw

# Specific workspace, all sources, custom output
./claude-history export myproject --as -o /tmp/backup

# Multiple workspaces (deduplicated)
./claude-history export proj1 proj2 -o ./exports

# Export from WSL
./claude-history export myproject --wsl

# Export from Windows
./claude-history export myproject --windows

# With splitting and minimal mode
./claude-history export myproject --minimal --split 500
```

**Output:**
- Markdown files named `{timestamp}_{session-id}.md`
- Source-tagged filenames: `wsl_ubuntu_`, `windows_`, `remote_hostname_`
- Organized by workspace subdirectories (unless `--flat`)

---

## `alias` - Manage Workspace Aliases

Group related workspaces across environments.

```bash
./claude-history alias <subcommand> [OPTIONS]
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
- `--as`: Add from all sources

### `alias remove <name> -- <workspace>`
Remove a workspace from an alias. Use `--` before workspace names starting with `-`.

### `alias export <file>`
Export aliases to JSON file.

### `alias import <file>`
Import aliases from JSON file.

**Examples:**
```bash
# Create and populate an alias
./claude-history alias create myproject
./claude-history alias add myproject myproject
./claude-history alias add myproject --windows myproject
./claude-history alias add myproject -r user@vm01 myproject

# Or add from all sources at once
./claude-history alias add myproject --as -r user@vm myproject

# Use aliases with @ prefix
./claude-history lss @myproject
./claude-history export @myproject -o ./backup

# Sync aliases across machines
./claude-history alias export aliases.json
./claude-history alias import aliases.json
```

**Automatic Alias Scoping:**

When running commands without arguments from an aliased workspace:
```bash
./claude-history lss        # Uses alias automatically
./claude-history export     # Uses alias automatically
./claude-history stats      # Uses alias automatically

# Force current workspace only
./claude-history lss --this
```

---

## `sources` - Manage Saved Sources

Manage saved SSH remote sources for `--as` flag.

```bash
./claude-history sources [list|add|remove|clear]
```

**Note:** WSL/Windows are auto-detected by `--as`. This command is only for SSH remotes.

**Examples:**
```bash
# List saved sources
./claude-history sources

# Add SSH remotes
./claude-history sources add user@vm01
./claude-history sources add user@vm02

# Remove a source
./claude-history sources remove user@vm02

# Clear all sources
./claude-history sources clear
```

Once configured, `--as` automatically includes saved sources:
```bash
./claude-history lsw --as              # includes vm01 and vm02
./claude-history stats --time --as     # syncs from vm01 and vm02
```

---

## `stats` - Usage Statistics

Display usage statistics and metrics from synced Claude Code sessions.

```bash
./claude-history stats [WORKSPACE] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--as`, `--all-sources`: Sync from all sources first
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
./claude-history stats

# All workspaces
./claude-history stats --aw

# Time tracking with auto-sync from all sources
./claude-history stats --time --as

# Tool usage statistics
./claude-history stats --tools

# Daily trends
./claude-history stats --by-day

# Filter by date range
./claude-history stats --since 2025-11-01 --until 2025-11-30
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
./claude-history lss myproject --since 2025-11-01

# Sessions within a date range
./claude-history export myproject --since 2025-11-01 --until 2025-11-30

# Export recent sessions only
./claude-history export myproject --since 2025-11-01 -o ./recent
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
./claude-history export myproject --split 500
```

- Smart break points (before User messages, after tool results, time gaps)
- Navigation links between parts
- Each part shows message range

---

## Remote Operations

### SSH Remote Access

```bash
# List remote workspaces
./claude-history lsw -r user@server

# List sessions from remote
./claude-history lss myproject -r user@server

# Export from remote
./claude-history export myproject -r user@server
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
./claude-history lsw --windows
./claude-history lss myproject --windows
./claude-history export myproject --windows
```
