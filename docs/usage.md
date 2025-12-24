# Command Reference

Detailed documentation for all `agent-history` commands and options.

## Commands Overview

| Command | Description |
|---------|-------------|
| `lsh` | List homes and manage SSH remotes |
| `lsw` | List workspaces |
| `lss` | List sessions |
| `export` | Export sessions to markdown |
| `alias` | Manage workspace aliases |
| `stats` | Show usage statistics and metrics |
| `reset` | Reset stored data (database, settings, aliases) |
| `install` | Install CLI + Claude skill and update retention settings |
| `gemini-index` | Add project paths to Gemini hash→path index |

---

## `lsh` - List Hosts & Manage SSH Remotes

List all Claude Code installations and manage SSH remote homes.

```bash
agent-history lsh [--local|--wsl|--windows|--remotes]
agent-history lsh add <user@hostname>
agent-history lsh remove <user@hostname>
agent-history lsh clear
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
$ agent-history lsh
Local:
  /home/alice/.claude	10 workspaces

SSH Remotes:
  alice@server.example.com

# Add an SSH remote
$ agent-history lsh add alice@server.example.com
Added source: alice@server.example.com

# Remove an SSH remote
$ agent-history lsh remove alice@server.example.com
Removed source: alice@server.example.com

# Show only SSH remotes
$ agent-history lsh --remotes
```

Once configured, `--ah` automatically includes saved SSH remotes:
```bash
agent-history lsw --ah              # includes saved remotes
agent-history export --ah           # exports from all homes
agent-history stats --time --ah     # syncs from all homes
```

---

## `lsw` - List Workspaces

List all workspaces matching a pattern.

```bash
agent-history lsw [PATTERN...] [OPTIONS]
```


---

## Testing

For how to run unit and integration tests, see:

- README.md#testing
- TESTING.md (Integration and E2E Tests)
**Arguments:**
- `PATTERN`: One or more workspace name patterns (optional, lists all if omitted)

**Options:**
- `--wsl`: List WSL workspaces
- `--windows`: List Windows workspaces
- `-r HOST`, `--remote HOST`: List remote workspaces via SSH
- `--ah`, `--all-homes`: List from all homes

**Examples:**
```bash
# List all local workspaces
agent-history lsw

# Filter by pattern
agent-history lsw myproject

# Multiple patterns
agent-history lsw proj1 proj2

# List from all homes
agent-history lsw --ah -r user@vm01
```

---

## `lss` - List Sessions

Show all sessions for a workspace.

```bash
agent-history lss [PATTERN] [OPTIONS]
```

**Arguments:**
- `PATTERN`: Workspace name pattern (default: current workspace or its alias)

**Scope Options:**
- `--this`: Use current workspace only, not its alias (if aliased)
- `--ah`, `--all-homes`: List from all homes (local + WSL/Windows + remotes)
- `--no-wsl`: Exclude WSL sessions (useful with `--ah`)
- `--no-windows`: Exclude Windows sessions (useful with `--ah`)

**Date Filtering:**
- `--since DATE`: Only include sessions modified on or after this date (YYYY-MM-DD)
- `--until DATE`: Only include sessions modified on or before this date (YYYY-MM-DD)

**Multi-Environment Access:**
- `--wsl`: Access WSL distribution (auto-detects)
- `--windows`: Access Windows user (auto-detects)
- `-r HOST`, `--remote HOST`: Access SSH remote server

**Counting:**
- `--counts`: Count messages for all sources (slower, includes remotes)
- `--wsl-counts`: Count messages for WSL sessions on Windows (slower)

**Examples:**
```bash
# List sessions from current workspace (or alias if aliased)
agent-history lss

# Force current workspace only (not alias)
agent-history lss --this

# List sessions from WSL
agent-history lss myproject --wsl

# List sessions from Windows
agent-history lss myproject --windows

# List sessions from SSH remote
agent-history lss myproject -r user@hostname

# Date filtering
agent-history lss myproject --since 2025-11-01
agent-history lss myproject --since 2025-11-01 --until 2025-11-30
```

**Output:**
- List of sessions with metadata (file, messages, date)
- Total size, message count, date range
- Grouped by workspace
- When WSL message counts are skipped on Windows, the `MESSAGES` column shows `?`

---

## `export` - Export Sessions

Export sessions from workspace(s) to markdown with flexible scope control.

```bash
agent-history export [WORKSPACE...] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--ah`, `--all-homes`: Export from ALL sources (local + WSL + Windows + remotes)
- `--aw`, `--all-workspaces` (also `-a`, `--all`): Export ALL workspaces
- `--this`: Use current workspace only, not its alias (if aliased)

**Arguments:**
- `WORKSPACE`: One or more workspace patterns (default: current workspace or its alias)

**Options:**
- `-o`, `--output DIR`: Output directory (default: `./ai-chats`)
- `--wsl`: Export from WSL (auto-detects distribution)
- `--windows`: Export from Windows (auto-detects user)
- `-r`, `--remote HOST`: Add SSH remote source (repeatable)
- `--no-remote`: Skip SSH remotes (useful with `--ah`)
- `--no-wsl`: Skip WSL sources (useful with `--ah`)
- `--no-windows`: Skip Windows sources (useful with `--ah`)
- `--force`, `-f`: Force re-export all sessions (default: incremental)
- `--since DATE`: Only include sessions modified on or after this date
- `--until DATE`: Only include sessions modified on or before this date
- `--minimal`: Export conversation content only, no metadata
- `--split LINES`: Split long conversations into parts
- `--flat`: Use flat directory structure (default: organized by workspace)
- `--jobs N`: Parallel export workers (default: 1)
- `--quiet`: Suppress per-file output (keeps summary/progress)

**Orthogonal Design:**

| Command | Workspace Scope | Source Scope |
|---------|----------------|--------------|
| `export` | Current | Local only |
| `export --ah` | Current | All homes |
| `export --aw` | All | Local only |
| `export --ah --aw` | All | All homes |

**Examples:**
```bash
# Current workspace, local home (default)
agent-history export

# Current workspace, all homes
agent-history export --ah

# All workspaces, local home
agent-history export --aw

# All workspaces, all homes
agent-history export --ah --aw

# Specific workspace, all homes, custom output
agent-history export myproject --ah -o /tmp/backup

# Multiple workspaces (deduplicated)
agent-history export proj1 proj2 -o ./exports

# Export from WSL
agent-history export myproject --wsl

# Export from Windows
agent-history export myproject --windows

# With splitting and minimal mode
agent-history export myproject --minimal --split 500

# Faster export with less output
agent-history export myproject --jobs 4 --quiet
```

**Output:**
- Markdown files named `{timestamp}_{session-id}.md`
- Source-tagged filenames: `wsl_ubuntu_`, `windows_`, `remote_hostname_`
- Organized by workspace subdirectories (unless `--flat`)

---

## `alias` - Manage Workspace Aliases

Group related workspaces across environments.

```bash
agent-history alias <subcommand> [OPTIONS]
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
- `--ah`: Add from all homes

### `alias remove <name> -- <workspace>`
Remove a workspace from an alias. Use `--` before workspace names starting with `-`.

Accepted formats:
- Encoded names (`-home-user-project`, `C--Users-me-proj`)
- Absolute Linux paths (`/home/user/project`)
- WSL mounts (`/mnt/c/Users/me/project`)
- Remote-style prefixes (`user@host:/home/user/project`)

### `alias export <file>`
Export aliases to JSON file.

### `alias import <file>`
Import aliases from JSON file.

**Examples:**
```bash
# Create and populate an alias
agent-history alias create myproject
agent-history alias add myproject myproject
agent-history alias add myproject --windows myproject
agent-history alias add myproject -r user@vm01 myproject

# Or add from all homes at once
agent-history alias add myproject --ah -r user@vm myproject

# Use aliases with @ prefix
agent-history lss @myproject
agent-history export @myproject -o ./backup

# Sync aliases across machines
agent-history alias export aliases.json
agent-history alias import aliases.json
```

**Automatic Alias Scoping:**

When running commands without arguments from an aliased workspace:
```bash
agent-history lss        # Uses alias automatically
agent-history export     # Uses alias automatically
agent-history stats      # Uses alias automatically

# Force current workspace only
agent-history lss --this
```

---

## `stats` - Usage Statistics

Display usage statistics and metrics from synced Claude Code sessions.

```bash
agent-history stats [WORKSPACE] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--ah`, `--all-homes`: Sync from all homes first
- `--aw`, `--all-workspaces`: Query all workspaces (default: current)
- `--this`: Use current workspace only, not its alias

**Sync Options:**
- `--sync`: Sync JSONL files to metrics database
- `--force`: Force re-sync all files
- `--jobs N`: Parallel remote sync workers (default: 1)
- `--no-remote`: Skip SSH remotes during sync
- `--no-wsl`: Skip WSL sources during sync
- `--no-windows`: Skip Windows sources during sync

**View Options:**
- `--time`: Show time tracking with daily breakdown (default summary already includes a time summary)
- `--tools`: Show tool usage statistics
- `--models`: Show model usage statistics
- `--by-workspace`: Show per-workspace breakdown
- `--by-day`: Show daily statistics
- `--top-ws N`: Limit workspaces shown per home in the summary (default: all; N must be > 0)

**Filters:**
- `--source SOURCE`: Filter by source (local, wsl:distro, windows, remote:host)
- `--since DATE`: Filter from this date
- `--until DATE`: Filter until this date
Note: `--source` defaults to all workspaces for that source unless `--this` is set. If you are outside a workspace, pass a pattern or use `--aw`.

**Examples:**
```bash
# Summary dashboard (current workspace)
agent-history stats

# All workspaces (Homes & Workspaces section plus summary with time)
agent-history stats --aw

# Time tracking with auto-sync from all homes
agent-history stats --time --ah

# Tool usage statistics
agent-history stats --tools

# Daily trends
agent-history stats --by-day

# Filter by date range
agent-history stats --since 2025-11-01 --until 2025-11-30

# Faster sync with selective sources
agent-history stats --sync --ah --jobs 4 --no-remote
```

**Metrics Available:**
- **Sessions**: Total, main vs agent, message counts
- **Tokens**: Input, output, cache creation, cache read, hit ratio
- **Tools**: Usage counts and error rates per tool
- **Models**: Usage distribution across Claude models
- **Homes & Workspaces**: Homes with per-home workspaces (alias-aware, per-home limiting via `--top-ws`)
- **Workspaces**: Top workspaces by activity (alias-aware)
- **Daily trends**: Session and token usage over time

**Database Location:** `~/.agent-history/metrics.db` (SQLite)

---

## Date Filtering

Both `lss` and `export` support date filtering:

```bash
# Sessions modified on or after a date
agent-history lss myproject --since 2025-11-01

# Sessions within a date range
agent-history export myproject --since 2025-11-01 --until 2025-11-30

# Export recent sessions only
agent-history export myproject --since 2025-11-01 -o ./recent
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
agent-history export myproject --split 500
```

- Smart break points (before User messages, after tool results, time gaps)
- Navigation links between parts
- Each part shows message range

---

## Remote Operations

### SSH Remote Access

```bash
# List remote workspaces
agent-history lsw -r user@server

# List sessions from remote
agent-history lss myproject -r user@server

# Export from remote
agent-history export myproject -r user@server
```

**Requirements:**
- Passwordless SSH key setup
- `rsync` installed on both machines

### WSL Access (from Windows)

```bash
python agent-history lsw --wsl
python agent-history lss myproject --wsl
python agent-history export myproject --wsl
python agent-history lss --wsl --agent codex
python agent-history lss --wsl --agent gemini
```

### Windows Access (from WSL)

```bash
agent-history lsw --windows
agent-history lss myproject --windows
agent-history export myproject --windows
```

---

## `reset` - Reset Stored Data

Delete metrics database, settings (SSH remotes), and/or aliases.

```bash
agent-history reset [what] [--force]
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
agent-history reset

# Reset only metrics database
agent-history reset db

# Reset without confirmation (for scripts)
agent-history reset -y
agent-history reset db -y
```

**Files affected:**
- `~/.agent-history/metrics.db` - Metrics database (stats, time tracking)
- `~/.agent-history/config.json` - Settings (SSH remotes)
- `~/.agent-history/aliases.json` - Workspace aliases
- On first run, any legacy `~/.claude-history/` directory is migrated here and cleaned up.

---

## `gemini-index` - Manage Gemini Hash Index

Add project directory paths to the Gemini hash→path index, or list existing mappings. This allows `agent-history` to display readable workspace paths instead of SHA-256 hashes when listing or exporting Gemini sessions.

```bash
agent-history gemini-index                      # list all mappings (default)
agent-history gemini-index --add [path ...]     # add paths to index
agent-history gemini-index --list [--full-hash] # list with options
```

**Options:**
- `-a`, `--add [PATH ...]`: Add project directories to index (default: current directory if no paths given)
- `-l`, `--list`: List all mappings in the hash index (default if no options)
- `--full-hash`: Show full SHA-256 hashes instead of truncated (with `--list`)

**How it works:**

Gemini CLI stores sessions in directories named by SHA-256 hashes of project paths:
```
~/.gemini/tmp/<sha256-hash>/chats/session-*.json
```

Without the hash index, workspace names appear as `[hash:abc123de]`. The `gemini-index` command:
1. Computes the SHA-256 hash for each provided path
2. Checks if that hash has any Gemini sessions in `~/.gemini/tmp/`
3. If sessions exist, adds the hash→path mapping to the index

**Examples:**
```bash
# Add current directory to index
agent-history gemini-index --add

# Add a specific project
agent-history gemini-index --add ~/projects/myapp

# Add multiple projects at once
agent-history gemini-index --add ~/projects/app1 ~/projects/app2 ~/projects/app3

# Output:
Adding 3 path(s) to Gemini index...

  ✅ /home/user/projects/app1
     → [hash:abc123de] (added)
  ⏭️  /home/user/projects/app2
     → [hash:def456gh] (already in index)
  ❌ /home/user/projects/app3
     → [hash:hij789kl] (no Gemini sessions found)

Summary: 1 added, 1 existing, 1 skipped
Total mappings in index: 5

# List all mappings (short hashes)
agent-history gemini-index --list

# Output:
Hash Index Mappings (5 entries):

  [hash:abc123de] → /home/user/projects/app1
  [hash:def456gh] → /home/user/projects/app2
  ...

# List with full hashes
agent-history gemini-index --list --full-hash

# Output:
Hash Index Mappings (5 entries):

  abc123def456789...
    → /home/user/projects/app1
  ...
```

**Automatic learning:**

The hash index also learns progressively when you run any `agent-history` command from a Gemini project directory. The explicit `gemini-index` command is useful for adding multiple projects at once.

**Index location:**
- `~/.agent-history/gemini_hash_index.json`

---

## `install` - Install CLI and Claude Skill

Install the CLI into your local `PATH`, copy the Claude skill files, and bump Claude Code’s retention settings so conversations aren’t auto-deleted.

```bash
agent-history install [--bin-dir DIR] [--skill-dir DIR]
                       [--cli-name NAME] [--skill-name NAME]
                       [--skip-cli] [--skip-skill] [--skip-settings]
```

**Default behavior:**
- CLI installed to `~/.local/bin/agent-history` (sudo-free). The command warns if that directory isn't on `PATH`.
- Claude skill (binary + `SKILL.md`) installed to `~/.claude/skills/agent-history/`.
- `~/.claude/settings.json` is created or updated with `{"cleanupPeriodDays": 99999}` so Claude Code keeps session history.

**Common options:**
- `--bin-dir DIR`, `--cli-name NAME`: Customize CLI destination and binary name.
- `--skill-dir DIR`, `--skill-name NAME`: Customize Claude skill destination.
- `--skip-cli`, `--skip-skill`, `--skip-settings`: Skip specific parts of the install workflow.

Run the installer whenever you update the script to keep the CLI and skill copy in sync.
