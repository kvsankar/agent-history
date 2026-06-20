# CLI Specification

<!-- doc-meta
doc_role: spec
audience: contributor
lifecycle: current
content_type: api
surface: public
canonicality: primary
-->

Command-line interface specification for `cagelens`.

## Design Principles

1. **Noun-Verb structure**: `cagelens <object> <verb> [args] [flags]`
2. **Orthogonal scopes**: Home and workspace scopes can be combined independently
3. **Sensible defaults**: Bare `cagelens` prints help; explicit commands use scoped defaults
4. **Progressive disclosure**: Simple cases are simple, power features available via flags
5. **Flat output**: Tab-separated data with headers for machine parsing

## Command Aliases

Command aliases have been removed. Use the canonical command names: `home`, `ws`, `session`, `project`, and `tag`.

## Bare Invocation

Running `cagelens` without a command must print top-level help and exit successfully.
It must not list sessions, scan agent stores, or read workspace/session data. Users
must choose an explicit command such as `cagelens session list`.

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
| `tag` | Normalized project label | Project metadata |

### Hierarchy

```
home (local, wsl, windows, web, remote:user@host)
  └── workspace (directory with sessions)
        └── session (conversation .jsonl file)

project = cross-cutting alias that groups workspaces from any home
tag = label on a project, applied across all homes in that project
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
| `add` | Add to collection | home, project, tag |
| `remove` | Remove from collection | home, project, tag |
| `export` | Convert to markdown | ws, session, project, home |
| `stats` | Show usage metrics | ws, session, project, home |

### Default Verb

When verb is omitted, `list` is assumed:
```
cagelens home          # = home list
cagelens ws            # = ws list
cagelens session       # = session list
cagelens project       # = project list
cagelens tag           # = tag list
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
| `session stats` | Aggregate metrics with token/tool/time overlays from the metrics DB | Scope + metrics DB |

### Why Stats Uses a Database

Computing aggregate metrics requires parsing every message in every session file to extract:
- Token counts (input, output, cache)
- Tool usage frequency
- Model breakdown
- Time tracking (gaps between messages)

This is expensive. The metrics database (`~/.cagelens/metrics.db`) caches these computed values.

### Sync Behavior

Stats use cached metrics from the SQLite DB by default. Use `--sync` when you
want to refresh source session files before display, and `--force` when
unchanged files should be reprocessed during that refresh.

```
stats                            # Query cached metrics
stats --sync --agent codex
stats --no-sync                  # Same as default, explicit cache-only mode
stats --sync --quiet             # Suppress sync progress
```

**Sync characteristics:**
- **Scoped**: Syncs the resolved homes, workspaces, and agent filters
- **Incremental**: Only processes new/modified files (based on mtime)
- **Additive**: Deleted sessions remain in DB until `reset db`
- **Visible**: `--sync` table output prints bounded progress to stderr unless `--quiet`

Cached stats may be stale. If no cached rows match the requested scope, run
`stats --sync` to build or refresh the metrics DB.

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
| `<workspace>` | Exact workspace path or identifier (positional, repeatable) |
| `--glob <pattern>` | Explicit shell-style workspace pattern (repeatable) |
| `--regex <regex>` | Explicit regular expression workspace pattern (repeatable) |
| `--aw` / `--all-workspaces` | All workspaces |
| `--this` | Current workspace only (override project auto-detection) |

**Pattern matching:**
- Positional workspace arguments are exact. They never imply substring matching.
- `--glob` uses shell-style `fnmatch` matching against workspace paths/ids.
- `--regex` uses Python regular-expression search against workspace paths/ids.
- Multiple exact/glob/regex matchers are combined with OR semantics.
- `-n`/`--name` is not supported; users must choose `--glob` or `--regex` explicitly.
- Users should quote glob and regex patterns in the shell, for example
  `--glob '/home/user/projects/auth*'`, so the shell does not expand them to
  existing filesystem paths before `cagelens` receives them.

### Project Scope

| Flag | Description |
|------|-------------|
| `--project <name>` | Use workspaces from named project (repeatable) |
| `--tag <name>` | Use workspaces from projects carrying a normalized tag (repeatable) |

Multiple `--project` flags are combined into a single scope.
Multiple `--tag` flags select projects with any requested tag. When both
`--project` and `--tag` are supplied, the effective project set is the
intersection.

**Project Auto-Detection:** When running `session`, `export`, or `stats` commands without explicit workspace arguments, if the current directory belongs to a project, the command automatically scopes to that project. Use `--this` to override and target only the current workspace. `ws list` is a discovery command and defaults to all workspaces in the selected homes unless a workspace pattern/project/`--this` is provided.

```
# In ~/myproject (which is part of project "myproj")
session list                    # Uses project myproj (implicit)
session list --this             # Current workspace only, no project expansion
session list --project other    # Explicit project selection
session list --tag work         # All projects tagged work
```

### Cross-Home Access Guard

When accessing non-local homes (`--windows`, `--wsl`, `-r user@host`, `--home <name>`, `--ah`) from within a local workspace, all session verbs (`list`, `export`, `stats`) require either:
1. An explicit workspace scope (`<workspace>`, `--glob <pattern>`, or `--regex <regex>`)
2. A project or project tag that ties the local workspace to remote workspaces
3. The `--aw` flag (explicitly requesting all workspaces)

**Rationale:** The same path on different machines (e.g., `/home/user/myproject` on local vs remote) may be completely unrelated codebases. Implicit path matching across homes would show misleading results.

```
# In ~/myproject (no project defined)
session list --windows              # ERROR: requires project or pattern
session list --windows --glob '*myproject*' # OK: explicit pattern
session list -r vm01                # ERROR: requires project or pattern
session list -r vm01 --regex '(^|/)myproject$' # OK: explicit pattern
session list --ah                   # ERROR: requires project or pattern
session list --ah /home/user/myproject # OK: explicit exact workspace
session list --ah --aw              # OK: explicitly requesting all workspaces

# In ~/myproject (part of project "myproj" that includes remote workspaces)
session list --windows              # OK: project ties homes together
session list -r vm01                # OK: project ties homes together
session list --ah                   # OK: project ties homes together
```

**When guard is skipped:**
- Not in a local workspace (no implicit path to match)
- Using `--aw` (explicitly requesting all workspaces)
- Project or project tag exists that ties workspaces together

**Allowed examples (guard skipped):**
- Outside any workspace (e.g., in `~/`): `session list --windows --aw`
- In a workspace but explicitly all workspaces: `session list --ah --aw`
- With a project that links homes: `session list --wsl --project myproj`
- With a project tag that links homes: `session list --wsl --tag work`
- Explicit patterns without a project: `session list --windows --glob '*myproj*'`

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
session list --glob '*auth*' --ah     # workspaces containing "auth", all homes
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
  --glob <pattern>                # Shell-style workspace pattern
  --regex <regex>                 # Python regex workspace pattern
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
  --tag <name>                    # Use workspaces from tagged projects
  --home <name>                   # Specific home (repeatable)
  --ah, --all-homes               # All homes
  --wsl                           # WSL home
  --windows                       # Windows home
  --web                           # Include Claude.ai web sessions
  -r <user@host>                  # SSH remote (repeatable)
  --no-wsl, --no-windows, --no-remote, --no-web  # Exclude homes when using --ah

Filter Options:
  --agent <agent>                 # Filter by agent: auto, claude, codex, gemini, pi, copilot-cli, copilot-vscode
  --since <date>                  # Filter by start date (YYYY-MM-DD)
  --until <date>                  # Filter by end date (YYYY-MM-DD)

List Options:
  --counts                        # Include message counts (slower)

Export Options:
  -o, --output <dir>              # Output directory (default: ./.cagelens/exports/)
  --session <id>                  # Export specific session IDs or filenames (repeatable)
  --json                          # Export NDJSON (unified schema) instead of Markdown
  --minimal                       # No metadata
  --split <lines>                 # Split long conversations
  --layout <tree|squashed|flat>   # Workspace directory layout (default: squashed)
  --flat                          # Alias for --layout flat
  --source                        # Include raw source files
  --jobs <n>                      # Parallel export
  --quiet                         # Suppress per-file output
  --force                         # Re-export even if up-to-date

Stats Options:
  --sync                          # Refresh source files before display (slower)
  --no-sync                       # Use cached metrics (default)
  --force                         # With --sync, reprocess unchanged session files
  --quiet                         # Suppress sync progress
  --by <dimension>                # Group by (comma-separated): model, tool, day, workspace, home, agent
                                  # Rollup also supports: project, tag, month
  --metric <metric>                # Rollup metric: time, tokens, all
  --top <n>                       # Rollup row limit
  --models                        # Alias for --by model
  --tools                         # Alias for --by tool
  --by-day                        # Alias for --by day
  --by-workspace                  # Alias for --by workspace
  --time                          # Summary-only time details; use rollup for monthly totals
  --top-ws <n|all>                # Limit to top N workspaces, or show all
  -H, --human                     # Human-readable numbers and h/m/s durations

Output Options:
  --format <fmt>                  # Output format: table, tsv, json
```

### stats

Top-level stats is the canonical analytics surface. It uses the same cached
metrics DB and scope flags as `session stats`, while resource-scoped stats
commands remain supported for convenience.

```
stats [summary] [options]          # Cached dashboard summary
stats rollup [options]             # Stable tabular rollups

Rollup Options:
  --metric <time|tokens|all>        # Metric family (default: all)
  --by <dims>                      # project/proj, tag, workspace/ws, home, agent, model, day, month
  --top <n>                        # Limit rows
  --sort <fields>                  # metric/tokens/time/sessions/messages/input/output/cache-read/dims
  --asc | --desc                   # Sort direction
  -c, --total, --totals            # Explicitly include the default totals row
  --no-total, --no-totals          # Suppress the default totals row
  --separator                      # Print -- before the rollup table

Time rollup columns:
  TIME_HMS                         # Human-readable total, e.g. 170h 6m 45s
  TIME_HOURS                       # Decimal hours for quick spreadsheet math
  TIME_SECONDS                     # Raw seconds for scripts and exact calculations

Human-readable rollups:
  -H, --human                      # Explicit default: compact token columns with K/M/B
  --raw, --no-human                # Raw token values in table/TSV
                                   # JSON keeps raw numeric fields

Table rollups:
  Numeric columns are right-aligned. Dimension columns are left-aligned.

Discoverability examples:
  cagelens stats --time
      Show dashboard time coverage and daily time details.

  cagelens stats rollup --metric time --by month
      Show work-period time totals by month.

  cagelens stats rollup --metric time --by project,month
      Show monthly work-period time totals per project.

  cagelens stats rollup --metric time --by tag
      Show work-period time totals by project tag, including untagged.

  cagelens stats rollup --metric time --by workspace,month --project myproj
      Show monthly work-period time totals per workspace in a project.

  cagelens stats rollup --metric tokens --by agent,month --sort month,agent --asc
      Sort grouped token rows chronologically, then by agent.
```

### project

Manage named workspace groups (cross-cutting aliases).

```
project [list]                    # List all projects
project show <name>               # Show project details
project add <name> <workspace>    # Add workspace to project
project add <name> --glob <pattern>   # Add by pattern
project add <name> --glob <pattern> --dry-run # Preview resolved additions
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

### tag

Manage normalized project tags. Tags are stored as project metadata and apply
to the project across all homes.

```
tag [list]                         # List project tags
tag list --project <name>           # List tags for one project
tag add --project <name> <tag...>   # Add tags to a project
tag remove --project <name> <tag...> # Remove tags from a project
```

Tags are normalized to lowercase shell-friendly slugs. For example,
`Work Stuff` becomes `work-stuff`.

Tagged projects can be used as a scope:
```
session list --tag work
session export --tag work -o ./backup
stats --tag work
stats rollup --metric time --by tag
```

For filtering (`--tag work`), each matching session counts once. For rollups
grouped by `tag`, sessions in multi-tag projects count once in each matching tag
bucket. Projects without tags, and sessions not matched to a configured project,
appear in the `untagged` bucket.

---

## Utility Commands

These are top-level commands that don't follow the noun-verb pattern:

| Command | Description |
|---------|-------------|
| `install` | Install CLI and agent skill packages |
| `reset` | Reset stored data (database, config, caches) |
| `fetch` | Pre-fetch remote sessions into local cache |
| `gemini-index` | Manage Gemini CLI hash→path mappings |

```
install                           # Install CLI and all supported agent skill packages
install --dry-run                 # Show exact resolved paths without writing files
install --agent codex             # Install Codex skill package only
install --skip-skill              # Skip agent skill installation
install --skip-cli                # Skip CLI installation
install --skip-settings           # Skip legacy agent settings step
install --bin-dir ~/.local/bin    # Custom bin directory
install --skill-dir ~/.config/agent/skills/custom  # Custom agent skill directory

Default skill package targets:

| Agent | Directory |
|-------|-----------|
| Claude Code | `~/.claude/skills/cagelens/` |
| Codex CLI | `${CODEX_HOME:-~/.codex}/skills/cagelens/` |
| Gemini CLI | `~/.gemini/skills/cagelens/` |
| Pi | `~/.pi/agent/skills/cagelens/` |

`--skill-dir` installs one custom skill package directory instead of the
agent-native targets. `install` does not modify agent settings files;
`--skip-settings` is retained for legacy compatibility.

`install --help` includes default CLI and skill locations plus examples. Table
output renders install actions as rows with component, agent, status, and path.

reset                             # Interactive reset (prompts for confirmation)
reset db                          # Reset metrics database only
reset config                      # Reset configuration only
reset cache                       # Reset remote/web caches only

fetch -r user@host --aw            # Prefetch all workspaces from one SSH remote
fetch -r user@host --glob '*auth*'      # Prefetch matching remote workspaces
fetch --ah --aw                    # Prefetch all configured SSH remotes
fetch --agent codex -r host --aw   # Prefetch Codex sessions from one SSH remote

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
| `CAGELENS_CONFIG_DIR` | Override config directory (`~/.cagelens/`). Bypasses migration logic. Used for test isolation. |

### Session Data Paths

| Variable | Description |
|----------|-------------|
| `CAGELENS_HOME` | Override local home directory for session discovery |
| `CAGELENS_HOME_WSL` | Override WSL home path (skips real WSL probing) |
| `CAGELENS_HOME_WINDOWS` | Override Windows home path (skips real Windows probing) |
| `CLAUDE_PROJECTS_DIR` | Override Claude Code projects directory |
| `CODEX_HOME` | Upstream Codex home directory; sessions are read from `CODEX_HOME/sessions` |
| `CODEX_SESSIONS_DIR` | Direct Codex sessions directory override (cagelens compatibility/testing) |
| `GEMINI_CLI_HOME` | Upstream Gemini CLI home root; sessions are read from `GEMINI_CLI_HOME/.gemini/tmp` |
| `GEMINI_SESSIONS_DIR` | Direct Gemini sessions directory override (cagelens compatibility/testing) |
| `PI_CODING_AGENT_SESSION_DIR` | Upstream Pi session directory override |
| `PI_CODING_AGENT_DIR` | Upstream Pi agent config directory override |
| `PI_SESSIONS_DIR` | Direct Pi sessions directory override (cagelens compatibility/testing) |

### Usage Examples

```bash
# Test isolation: use temporary config directory
CAGELENS_CONFIG_DIR=/tmp/test-config cagelens session stats

# Testing with mock session data
CAGELENS_HOME=/tmp/mock-home cagelens session list

# Skip WSL probing in tests
CAGELENS_HOME_WSL=/tmp/mock-wsl cagelens ws --wsl
```

---

## Examples

### Basic Usage

```bash
# List all workspaces
cagelens ws

# List sessions in current workspace
cagelens session

# Export current workspace sessions
cagelens session export

# Show stats for current workspace
cagelens session stats
```

### Pattern Matching

```bash
# List workspaces matching "auth"
cagelens ws --glob '*auth*'

# List sessions from workspaces matching "auth"
cagelens session --glob '*auth*'

# Export sessions from matching workspaces
cagelens session export --glob '*auth*' -o ./exports
```

### Multi-Home Operations

```bash
# List workspaces from all homes
cagelens ws --aw --ah

# List sessions from WSL
cagelens session --wsl --aw

# List sessions from Windows (from WSL)
cagelens session --windows --aw

# Export from multiple homes
cagelens session export --home local --home remote:vm01

# Stats across all homes
cagelens session stats --ah --aw
```

### Projects

```bash
# Create a project (auto-created on first add)
cagelens project add myproj /home/user/myproject

# Add workspace from WSL/Windows
cagelens project add myproj /home/user/myproject --wsl
cagelens project add myproj /mnt/c/Users/alice/myproject --windows

# Use the project
cagelens session list --project myproj
cagelens session export --project myproj
cagelens session stats --project myproj

# Project auto-detection (when in a project workspace)
cagelens session list              # Auto-detects project
cagelens session list --this       # Override: current workspace only
```

### Export Options

```bash
# Export with date filter
cagelens session export --since 2025-01-01 --until 2025-01-31

# Export with custom output directory
cagelens session export -o ./my-exports

# Export by session ID or filename
cagelens session export --session 550e8400-e29b-41d4 -o ./exports

# Minimal export (no metadata)
cagelens session export --minimal

# Split long conversations
cagelens session export --split 500

# Flat structure (no workspace subdirectories)
cagelens session export --flat

# Claude-style single workspace folder
cagelens session export --layout squashed

# Include raw source files
cagelens session export --source

# NDJSON export
cagelens session export --json

# Parallel export
cagelens session export --jobs 4

# Quiet mode (suppress per-file output)
cagelens session export --quiet

# Force re-export (ignore timestamps)
cagelens session export --force
```

### Stats Options

```bash
# Summary stats (cached)
cagelens stats
cagelens stats summary
cagelens session stats              # compatibility/convenience form

# Stats across scopes
cagelens stats --aw                     # All workspaces
cagelens stats --ah                     # All homes
cagelens stats --ah --aw                # Everything

# Make sync explicit or skip it
cagelens stats --sync
cagelens stats --sync --agent codex
cagelens stats --no-sync

# Add by_day key in JSON output
cagelens stats --by day --format json
cagelens stats --by-day

# Add model/tool summaries
cagelens stats --models
cagelens stats --tools

# Time drilldown
cagelens stats --time

# Limit results
cagelens stats --top-ws 10
cagelens stats --top-ws all

# Rollups
cagelens stats rollup --metric time --by project
cagelens stats rollup --metric time --by project,month
cagelens stats rollup --metric time --by workspace,day
cagelens stats rollup --metric tokens --by project,agent,model
cagelens stats rollup --metric all --by project
cagelens stats rollup --metric tokens --by workspace,month --separator
cagelens stats rollup --metric tokens --by workspace,month --raw --no-total
cagelens stats rollup --metric tokens --by agent,month --sort month,agent --asc

# Output format
cagelens stats --format json
cagelens stats --format tsv
```

Stats table output begins with an explicit scope banner before metrics:

```text
Scope:
  Request: workspace glob *bptrial*
  Homes: local
  Workspaces: 3 (bptrial-main, /home/sankar/sankar/projects/bptrial-main, bptrial-mobile)
  Sessions: 7
```

This banner is required for both `stats summary` and `stats rollup` table
output. It must distinguish project scope from workspace-pattern scope:
`cagelens stats --glob '*bptrial*'` is a workspace glob filter, while
`cagelens stats --project bptrial` is a project filter. Bare
`cagelens stats bptrial` is exact workspace scope.

For rollup table output, `--separator` inserts a `--` line after this banner
and before the table. Rollups include a `TOTAL` row by default; use
`--no-total`/`--no-totals` to suppress it. Token columns use compact K/M/B
values by default in table/TSV; use `--raw`/`--no-human` for raw values.
Numeric table columns are right-aligned.

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
HOME    WORKSPACE                    SESSIONS  STATUS   MODIFIED
local   /home/user/projects/api           144  ok       2025-01-03 18:15
local   /home/user/projects/my-app         23  ok       2025-01-02 10:30
local   /home/user/projects/deleted        12  missing  2024-12-28 14:22
```

**With multi-home (`--ah` or `-r`):**
```
HOME              WORKSPACE                    SESSIONS  STATUS   MODIFIED
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
| MODIFIED | Timestamp of most recent session |

**TSV (`--format tsv`):**
```
HOME	WORKSPACE	SESSIONS	STATUS	MODIFIED
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
AGENT    HOME    WORKSPACE              FILE                                 MESSAGES  MODIFIED
claude   local   /home/user/myproj      550e8400-e29b-41d4-a716.jsonl              127  2025-01-03
claude   local   /home/user/myproj      agent-a1b2c3d4.jsonl                        34  2025-01-03
codex    local   /home/user/other       rollout-173590.jsonl                        89  2025-01-02
```

**With `--ah` (multi-home):**
```
AGENT    HOME        WORKSPACE           FILE                               MESSAGES  MODIFIED
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
./.cagelens/exports/home/user/myproj/20250103181500_550e8400-e29b.md
./.cagelens/exports/home/user/myproj/20250103174500_agent-a1b2c3d4.md
{'exported': 2, 'skipped': 0, 'failed': 0, 'output_dir': './.cagelens/exports'}
```

**With `--quiet`:**
```
{'exported': 2, 'skipped': 0, 'failed': 0, 'output_dir': './.cagelens/exports'}
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
- Token/tool/time breakdowns come from the cached metrics DB; run `--sync` to refresh that cache
- `--by` adds groupings to table output; `by_day` is included only when requested

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
PROJECT       TAGS           SOURCE                         WORKSPACE       SESSIONS
myproject     work,client-a   local, wsl:Ubuntu, remote:vm01 3 workspaces   45
api-work      work            local, remote:vm01             2 workspaces   12
```

Note: `SESSIONS` is only populated with `project list --counts`.

### project show

Shows project details.

**Default:**
```
Project: myproject
Tags: work,client-a
Total Workspaces: 3
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
HOME    WORKSPACE                 SESSIONS  STATUS  MODIFIED
local   /home/user/cagelens            144  ok      2025-01-03 18:15
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
