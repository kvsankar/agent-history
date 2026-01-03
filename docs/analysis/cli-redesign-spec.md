# CLI Redesign Specification

## Design Principles

1. **Noun-Verb structure**: `agent-history <object> <verb> [args] [flags]`
2. **Orthogonal scopes**: Home and workspace scopes can be combined independently
3. **Explicit over implicit**: Pattern matching requires explicit flag (`-n`)
4. **Sensible defaults**: No args = list, current workspace, local home
5. **Progressive disclosure**: Simple cases are simple, power features available via flags

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

Use `--no-sync` when you know the data hasn't changed and want instant results

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
| `--local` | Local home only |

### Workspace Scope (for session commands)

| Argument/Flag | Description |
|---------------|-------------|
| (none) | Current workspace (from cwd) |
| `<path>` | Exact workspace path (positional, repeatable) |
| `-n <pattern>` / `--name <pattern>` | Pattern match workspace names |
| `--aw` / `--all-workspaces` | All workspaces |
| `--this` | Current workspace only (override project auto-detection) |

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
  <path>                          # Exact workspace path (positional, repeatable)
  -n, --name <pattern>            # Pattern match workspace names
  --aw, --all-workspaces          # All workspaces
  --this                          # Current workspace only (override project)
  --project <name>                # Use workspaces from project
  --home <name>                   # Specific home (repeatable)
  --ah, --all-homes               # All homes
  --wsl                           # WSL home
  --windows                       # Windows home
  --web                           # Claude.ai web sessions
  -r <user@host>                  # SSH remote
  --no-wsl, --no-windows, --no-remote  # Exclude sources (with --ah)

Filter Options:
  --agent <agent>                 # Filter by agent: auto, claude, codex, gemini
  --since <date>                  # Filter by start date
  --until <date>                  # Filter by end date

Export Options:
  -o, --output <dir>              # Output directory
  --minimal                       # No metadata
  --split <lines>                 # Split long conversations
  --flat                          # No workspace subdirectories
  --source                        # Include raw source files
  --jobs <n>                      # Parallel export
  --quiet                         # Suppress per-file output
  --force                         # Re-export even if up-to-date

Stats Options:
  --no-sync                       # Skip auto-sync (use cached data)
  --by <dimension>                # Group by: model, tool, day, workspace, home
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

### Using Projects

Projects are referenced with `--project` flag:
```
session list --project myproject      # List sessions from project workspaces
session export --project myproject    # Export project sessions
session stats --project myproject     # Stats for project
```

Note: Project auto-detection applies when in a workspace that belongs to a project (see Project Scope above).

---

## Utility Commands

These are top-level commands that don't follow the noun-verb pattern:

| Command | Description |
|---------|-------------|
| `install` | Install CLI to PATH and Claude skill |
| `reset` | Reset stored data (database, settings, projects) |
| `gemini-index` | Manage Gemini CLI hash→path mappings |

```
install                           # Install CLI + skill + retention settings
install --skip-skill              # Skip skill installation
install --bin-dir ~/.local/bin    # Custom bin directory

reset                             # Interactive reset
reset --db                        # Reset metrics database only
reset --config                    # Reset configuration only

gemini-index                      # List hash→path mappings
gemini-index --add                # Add current directory
gemini-index --add ~/projects     # Add specific path
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

## Output Formats

### Default (Table)

Human-readable, aligned columns:
```
Workspace              Sessions    Messages
────────────────────  ──────────  ──────────
claude-history              144      30,728
my-project                   23       5,421
```

### TSV

Tab-separated for scripting:
```
WORKSPACE	SESSIONS	MESSAGES
claude-history	144	30728
my-project	23	5421
```

### JSON

Machine-readable:
```json
[
  {"workspace": "claude-history", "sessions": 144, "messages": 30728},
  {"workspace": "my-project", "sessions": 23, "messages": 5421}
]
```

---

## Migration from v1

Users of the previous CLI will need to update their commands:

| Old Command | New Command |
|-------------|-------------|
| `lsw` | `ws` |
| `lss` | `session` |
| `lsh` | `home` |
| `export myproj` | `session export -n myproj` |
| `stats` | `session stats` |
| `stats --sync` | `session stats` |
| `ss @myproj` | `session --project myproj` |
| `project create X` | `project add X <workspace>` |

### Key Changes

1. **Noun-verb structure**: Commands are now `<object> [verb]` (e.g., `session list`, `ws export`)
2. **No top-level verbs**: `export` and `stats` are now verbs on objects, not standalone commands
3. **Explicit patterns**: Use `-n <pattern>` for pattern matching; positional args are exact paths
4. **Projects via flag**: Use `--project <name>` instead of `@name` prefix
5. **Auto-sync**: Stats automatically syncs; use `--no-sync` to skip
