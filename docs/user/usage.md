# Command Reference

<!-- doc-meta
doc_role: reference
audience: user
lifecycle: current
content_type: workflow
surface: public
canonicality: primary
-->

Detailed documentation for all `cagelens` commands and options.

## Commands Overview

| Command | Description |
|---------|-------------|
| `home` | List homes and manage sources (WSL, Windows, SSH) |
| `ws` | List workspaces |
| `session` | List sessions |
| `session export` | Export sessions to Markdown, HTML, or NDJSON |
| `project` | Manage workspace projects |
| `tag` | Tag projects for filtered stats and rollups |
| `session stats` | Show usage statistics and metrics |
| `reset` | Reset stored data (metrics/config/cache) |
| `install` | Install CLI and agent skill packages |
| `fetch` | Fetch remote sessions into local cache |
| `gemini-index` | Add project paths to Gemini hash→path index |

---

## `home` - List Homes & Manage Sources

List all Claude Code installations and manage sources (WSL, Windows, SSH remotes).

```bash
cagelens home [--local|--wsl|--windows|--remotes]
cagelens home add [--wsl|--windows|<user@hostname>]
cagelens home remove <source>
cagelens home clear
```

**Subcommands:**
- `add --wsl`: Add WSL to configured homes
- `add --windows`: Add Windows to configured homes
- `add <user@hostname>`: Add an SSH remote
- `remove <source>`: Remove a source
- `clear`: Remove all saved sources

**Filter Options:**
- No flags: Show all configured homes
- `--local`: Show only local installation
- `--wsl`: Show only WSL distributions
- `--windows`: Show only Windows users
- `--remotes`: Show only SSH remotes

**Explicit Homes Model:**

Sources must be explicitly added for `--ah` to include them:
```bash
# Add homes (explicit model)
cagelens home add --wsl              # add WSL
cagelens home add --windows          # add Windows
cagelens home add alice@server       # add SSH remote

# Now --ah includes configured sources
cagelens ws list --ah                # includes configured homes
cagelens session export --ah         # current workspace/project from all homes
cagelens session export --ah --aw    # all workspaces from all homes
cagelens session stats --time --ah   # cached stats from all homes
```

**Examples:**
```bash
# Show configured homes
$ cagelens home list
HOME		PATH		SESSIONS
local		/home/alice/.claude	10
remote:alice@server	alice@server.example.com	5

# Add an SSH remote
$ cagelens home add alice@server.example.com
Added source: alice@server.example.com

# Remove a source
$ cagelens home remove alice@server.example.com
Removed source: alice@server.example.com
```

---

## `ws list` - List Workspaces

List all workspaces matching a pattern.

```bash
cagelens ws list [PATTERN...] [OPTIONS]
```

**Arguments:**
- `PATTERN`: One or more workspace name patterns (optional, lists all if omitted)

**Options:**
- `--wsl`: List WSL workspaces
- `--windows`: List Windows workspaces
- `-r HOST`, `--remote HOST`: List remote workspaces via SSH
- `--ah`, `--all-homes`: List from all configured homes

**Examples:**
```bash
# List all local workspaces
cagelens ws list

# Filter by pattern
cagelens ws list myproject

# Multiple patterns
cagelens ws list proj1 proj2

# List from all homes
cagelens ws list --ah -r user@vm01
```

---

## `session list` - List Sessions

Show all sessions for a workspace.

```bash
cagelens session list [PATTERN] [OPTIONS]
```

**Arguments:**
- `PATTERN`: Workspace name pattern (default: current workspace or its project)

**Scope Options:**
- `--this`: Use current workspace only, not its project (if in a project)
- `--project NAME`: Use workspaces from a configured project
- `--tag NAME`: Use workspaces from projects with this tag
- `--ah`, `--all-homes`: List from all configured homes
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
# List sessions from current workspace (or project if in a project)
cagelens session list

# Force current workspace only (not project)
cagelens session list --this

# List sessions from WSL
cagelens session list myproject --wsl

# List sessions from Windows
cagelens session list myproject --windows

# List sessions from SSH remote
cagelens session list myproject -r user@hostname

# Date filtering
cagelens session list myproject --since 2025-11-01
cagelens session list myproject --since 2025-11-01 --until 2025-11-30
```

**Output:**
- List of sessions with metadata (file, messages, date)
- Total size, message count, date range
- Grouped by workspace
- When WSL message counts are skipped on Windows, the `MESSAGES` column shows `?`

---

## `session export` - Export Sessions

Export sessions from workspace(s) to Markdown, offline HTML, or NDJSON with flexible scope control.

```bash
cagelens session export [WORKSPACE...] [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--ah`, `--all-homes`: Export from ALL sources (local + WSL + Windows + remotes)
- `--aw`, `--all-workspaces` (also `-a`, `--all`): Export ALL workspaces
- `--this`: Use current workspace only, not its project membership
- `--project NAME`: Export workspaces from a configured project
- `--tag NAME`: Export workspaces from projects with this tag

**Arguments:**
- `WORKSPACE`: One or more workspace patterns (default: current workspace or its project)

`--ah` and `--aw` are independent. `--ah` does not mean "all workspaces"; it
only expands the source homes. Use `--ah --aw` for every workspace in every
selected home, or pass an explicit workspace path/pattern.

**Options:**
- `-o`, `--output DIR`: Output directory (default: `./.cagelens/exports`)
- `--format markdown|html`: Export Markdown or offline HTML (default: `markdown`)
- `--json`: Export NDJSON using the [unified schema](../specs/schema/unified-json-schema.md)
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
- `--layout tree|squashed|flat`: Directory layout (default: `squashed`)
- `--flat`: Use flat directory structure (alias for `--layout flat`)
- `--jobs N`: Parallel export workers (default: 1)
- `--quiet`: Suppress per-file output (keeps summary/progress)

**Orthogonal Design:**

| Command | Workspace Scope | Source Scope |
|---------|----------------|--------------|
| `session export` | Current | Local only |
| `session export --ah` | Current | All homes |
| `session export --aw` | All | Local only |
| `session export --ah --aw` | All | All homes |

**Examples:**
```bash
# Current workspace, local home (default)
cagelens session export

# Current workspace, all homes
cagelens session export --ah

# All workspaces, local home
cagelens session export --aw

# All workspaces, all homes
cagelens session export --ah --aw

# All VS Code Copilot sessions from all homes
cagelens session export --ah --aw --agent copilot-vscode --format html -o ./exports

# Specific workspace, all homes, custom output
cagelens session export myproject --ah -o /tmp/backup

# Offline HTML export
cagelens session export myproject --format html

# Multiple workspaces (deduplicated)
cagelens session export proj1 proj2 -o ./exports

# Export from WSL
cagelens session export myproject --wsl

# Export from Windows
cagelens session export myproject --windows

# With splitting and minimal mode
cagelens session export myproject --minimal --split 500

# Claude-style single workspace folder
cagelens session export myproject --layout squashed

# Faster export with less output
cagelens session export myproject --jobs 4 --quiet
```

**Output:**
- Markdown/HTML files named `{timestamp}_{session-id}.md` or `{timestamp}_{session-id}.html`; NDJSON files use `.ndjson`
- Source-tagged filenames: `wsl_ubuntu_`, `windows_`, `remote_hostname_`
- Layouts: `squashed` uses one Claude-style workspace folder, `tree` recreates workspace path segments, `flat` writes directly to the output directory

---

## `project` - Manage Workspace Projects

Group related workspaces across environments.

```bash
cagelens project <subcommand> [OPTIONS]
```

**Subcommands:**

### `project list`
List all defined projects.

### `project show <name>`
Show workspaces in a project.

### `project add <name> <pattern>`
Add workspaces matching pattern to a project.

Options:
- `--wsl`: Add from WSL
- `--windows`: Add from Windows
- `-r HOST`: Add from SSH remote
- `--ah`: Add from all homes

### `project remove <name> -- <workspace>`
Remove a workspace from a project. Use `--` before workspace names starting with `-`.

Accepted formats:
- Encoded names (`-home-user-project`, `C--Users-me-proj`)
- Absolute Linux paths (`/home/user/project`)
- WSL mounts (`/mnt/c/Users/me/project`)
- Remote-style prefixes (`user@host:/home/user/project`)

### `project export <name>`
Export all sessions in a project. Supports the same export options as `session export`, including `--format html`, `--json`, `--split`, `--source`, and `--agent`.

### `project stats <name>`
Show stats for a project. Supports the same stats options as `session stats`, including `--sync`, `--by`, `--time`, and `--agent`.

**Examples:**
```bash
# Populate a project
cagelens project add myproject myproject
cagelens project add myproject --windows myproject
cagelens project add myproject -r user@vm01 myproject

# Or add from all homes at once
cagelens project add myproject --ah -r user@vm myproject

# Use projects with @ prefix
cagelens session list @myproject
cagelens session export @myproject -o ./backup

# Export or inspect project sessions
cagelens project export myproject --agent codex -o ./backup
cagelens project stats myproject --agent codex --sync
```

**Automatic Project Scoping:**

When running commands without arguments from a project workspace:
```bash
cagelens session list      # Uses project automatically
cagelens session export    # Uses project automatically
cagelens session stats     # Uses project automatically

# Force current workspace only
cagelens session list --this
```

---

## `tag` - Manage Project Tags

Tags are normalized labels on projects. A project can have multiple tags, and a
tag applies to that project across all homes.

```bash
cagelens tag list
cagelens tag list --project myproject
cagelens tag add --project myproject work personal
cagelens tag remove --project myproject personal

cagelens session list --tag work
cagelens session export --tag work -o ./backup
cagelens stats --tag work
cagelens stats rollup --metric time --by tag
```

`Work Stuff` normalizes to `work-stuff`. `stats --tag work` counts each
matching session once. `stats rollup --by tag` counts a multi-tag project once
per tag bucket and includes `untagged`.

---

## `stats` - Usage Statistics

Display usage statistics and metrics from coding-agent sessions.
The default table summarizes the full metric surface: sessions, messages,
tokens, tools, models, time, agents, homes, and workspaces. Use the drilldown
flags printed at the bottom of the table to expand each metric family.
`cagelens stats` is the canonical analytics entry point. `cagelens session stats`,
`cagelens ws stats`, `cagelens project stats`, and `cagelens home stats` remain
supported convenience forms.

```bash
cagelens stats [WORKSPACE] [OPTIONS]
cagelens stats rollup --metric METRIC --by DIMS [OPTIONS]
```

**Scope Flags (Orthogonal):**
- `--ah`, `--all-homes`: Sync from all homes first
- `--aw`, `--all-workspaces`: Query all workspaces (default: current)
- `--this`: Use current workspace only, not its project membership

**Sync Options:**
- `--sync`: Refresh source session files before showing stats (slower, freshest)
- `--no-sync`: Query cached metrics without refreshing first (default)
- `--force`: With `--sync`, reprocess unchanged files too
- `--quiet`: Suppress sync progress

**View Options:**
- `--time`: Expand work-period time details, including daily time totals
- `--by DIMS`: Group by dimensions (comma-separated): home, agent, workspace, day, model, tool
  - Rollup also supports `project`, `tag`, and `month`
- `--metric time|tokens|all`: Rollup metric family
- `--top N`: Limit rollup rows
- `--sort FIELDS`: Sort rollup rows by comma-separated fields such as month, agent, tokens, time, sessions, input, output, cache-read
- `--asc`, `--desc`: Sort direction
- `-c`, `--total`, `--totals`: Explicitly include the default totals row
- `--no-total`, `--no-totals`: Suppress the default totals row
- `--separator`: Print `--` before the rollup table
- `--models`: Shortcut for `--by model`
- `--tools`: Shortcut for `--by tool`
- `--by-day`: Shortcut for `--by day`
- `--by-workspace`: Shortcut for `--by workspace`
- `--top-ws N`: Limit workspaces shown in the summary (N must be > 0)
- `--top-ws all`: Show every workspace row
- `-H`, `--human`: Explicit default for rollups; compact large numbers and durations
- `--raw`, `--no-human`: Use raw numeric rollup values instead of compact K/M/B values

**Filters:**
- `--since DATE`: Filter from this date
- `--until DATE`: Filter until this date
If you are outside a known workspace, pass a workspace pattern or use `--aw`.

**Examples:**
```bash
# Summary dashboard (current workspace)
cagelens stats

# All workspaces (Homes & Workspaces section plus summary with time)
cagelens stats --aw

# Time tracking from cached all-home metrics
cagelens stats --time --ah

# Tool usage statistics
cagelens stats --by tool

# Daily trends
cagelens stats --by day

# Multi-dimension grouping
cagelens stats --by home,agent

# Filter by date range
cagelens stats --since 2025-11-01 --until 2025-11-30

# Show every workspace row
cagelens stats --top-ws all

# Refresh the metrics cache before display
cagelens stats --sync --aw

# Rollups
cagelens stats rollup --metric time --by project
cagelens stats rollup --metric time --by tag
cagelens stats rollup --metric time --by project,month
cagelens stats rollup --metric time --by workspace,day
cagelens stats rollup --metric tokens --by project,agent,model
cagelens stats rollup --metric all --by project
cagelens stats rollup --metric tokens --by workspace,month --separator
cagelens stats rollup --metric tokens --by workspace,month --raw --no-total
cagelens stats rollup --metric tokens --by agent,month --sort month,agent --asc
```

**Metrics Available:**
- **Sessions**: Total, main vs agent, message counts
- **Tokens/tools/models/time**: Aggregated from parsed sessions and cached metrics
- **Homes, workspaces, and projects**: Grouped by the resolved command scope
- **Daily trends**: Available with `--by day` or JSON output

For metrics storage internals, see
[cagelens-spec.md](../specs/cagelens-spec.md#metrics-database).

---

## Date Filtering

Both `session list` and `session export` support date filtering:

```bash
# Sessions modified on or after a date
cagelens session list myproject --since 2025-11-01

# Sessions within a date range
cagelens session export myproject --since 2025-11-01 --until 2025-11-30

# Export recent sessions only
cagelens session export myproject --since 2025-11-01 -o ./recent
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
cagelens session export myproject --split 500
```

- Smart break points (before User messages, after tool results, time gaps)
- Navigation links between parts
- Each part shows message range

---

## Remote Operations

### SSH Remote Access

```bash
# List remote workspaces
cagelens ws list -r user@server

# List sessions from remote
cagelens session list myproject -r user@server

# Export from remote
cagelens session export myproject -r user@server
```

**Requirements:**
- Passwordless SSH key setup
- `rsync` installed on both machines

### WSL Access (from Windows)

```bash
python cagelens ws list --wsl
python cagelens session list myproject --wsl
python cagelens session export myproject --wsl
python cagelens session list --wsl --agent codex
python cagelens session list --wsl --agent gemini
```

### Windows Access (from WSL)

```bash
cagelens ws list --windows
cagelens session list myproject --windows
cagelens session export myproject --windows
```

---

## `reset` - Reset Stored Data

Delete metrics database, config, and/or cache.

```bash
cagelens reset [all|db|config|cache] [-y]
```

**Arguments:**
- Target: What to reset (optional, default: `all`)
  - `db`: Delete metrics database only
  - `config`: Delete config (homes/projects) only
  - `cache`: Delete remote/web caches only
  - `all`: Delete everything (default)

**Options:**
- `-y`, `--yes`: Skip confirmation prompt

**Examples:**
```bash
# Reset everything (prompts for confirmation)
cagelens reset

# Reset only metrics database
cagelens reset db

# Reset only remote/web caches
cagelens reset cache

# Reset without confirmation (for scripts)
cagelens reset -y
cagelens reset db -y
```

For the internal files affected by each reset target, see
[cagelens-spec.md](../specs/cagelens-spec.md#file-locations).

---

## `fetch` - Fetch SSH Remote Sessions

Fetch SSH remote sessions into the local cagelens remote cache. This command
does not fetch local, WSL, Windows, or Claude web sessions.

```bash
cagelens fetch -r user@host --aw
```

**Notes:**
- Use `-r HOST` for explicit SSH remotes, or `--ah --aw` for all configured
  SSH remotes.
- Use workspace filters such as `--glob "*auth*"`, `--project NAME`, `--tag NAME`, or `--aw`.
- Use `--agent` to restrict the agent backend.
- Remote cache layout is documented in [cagelens-spec.md](../specs/cagelens-spec.md#file-locations).

---

## `gemini-index` - Manage Gemini Hash Index

Add project directory paths to the Gemini hash→path index, or list existing mappings. This allows `cagelens` to display readable workspace paths instead of SHA-256 hashes when listing or exporting Gemini sessions.

```bash
cagelens gemini-index                      # list all mappings (default)
cagelens gemini-index --add [path ...]     # add paths to index
cagelens gemini-index --list [--full-hash] # list with options
```

**Options:**
- `-a`, `--add [PATH ...]`: Add project directories to index (default: current directory if no paths given)
- `-l`, `--list`: List all mappings in the hash index (default if no options)
- `--full-hash`: Show full SHA-256 hashes instead of truncated (with `--list`)

**How it works:**

Without the hash/index mapping, unresolved Gemini workspaces can appear as
`[hash:abc123de]` or another opaque project identifier. The `gemini-index`
command records a readable project path mapping when a provided path matches
known Gemini sessions. Gemini storage details live in
[gemini-cli-format.md](../specs/agents/formats/gemini-cli-format.md).

**Examples:**
```bash
# Add current directory to index
cagelens gemini-index --add

# Add a specific project
cagelens gemini-index --add ~/projects/myapp

# Add multiple projects at once
cagelens gemini-index --add ~/projects/app1 ~/projects/app2 ~/projects/app3

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
cagelens gemini-index --list

# Output:
Hash Index Mappings (5 entries):

  [hash:abc123de] → /home/user/projects/app1
  [hash:def456gh] → /home/user/projects/app2
  ...

# List with full hashes
cagelens gemini-index --list --full-hash

# Output:
Hash Index Mappings (5 entries):

  abc123def456789...
    → /home/user/projects/app1
  ...
```

**Automatic learning:**

The hash index also learns progressively when you run any `cagelens` command from a Gemini project directory. The explicit `gemini-index` command is useful for adding multiple projects at once.

**Index location:**
- `~/.cagelens/gemini_hash_index.json`

---

## `install` - Install CLI and Agent Skill Packages

Install the CLI wrapper and the `cagelens` skill package.

```bash
cagelens install [--bin-dir DIR] [--skill-dir DIR] [--agent AGENT]
                       [--dry-run] [--skip-cli] [--skip-skill] [--skip-settings]
```

By default, `install` writes:
- CLI wrapper: `~/.local/bin/cagelens`
- Claude Code skill: `~/.claude/skills/cagelens/`
- Codex CLI skill: `${CODEX_HOME:-~/.codex}/skills/cagelens/`
- Gemini CLI skill: `~/.gemini/skills/cagelens/`
- Pi skill: `~/.pi/agent/skills/cagelens/`

**Options:**
- `--bin-dir DIR`: Custom binary install directory
- `--skill-dir DIR`: Custom agent skill install directory
- `--agent AGENT`: Install one agent skill package (`claude`, `codex`, `gemini`, or `pi`)
- `--dry-run`: Show the exact install plan without writing files
- `--skip-cli`, `--skip-skill`, `--skip-settings`: Skip specific install steps

**Examples:**
```bash
cagelens install
cagelens install --dry-run
cagelens install --agent codex
cagelens install --skip-cli
```
