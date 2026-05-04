# agent-history Specification

This document specifies what `agent-history` does. It defines the functional requirements, supported agents, data sources, and operations.

For CLI syntax and output formats, see [cli-spec.md](cli-spec.md).
For agent-specific session formats, see [agents/formats/](agents/formats/).

---

## Purpose

`agent-history` is a read-only tool that browses, exports, and analyzes conversation history from AI coding assistants.

**Core capabilities:**
- List workspaces and sessions across multiple data sources
- Export sessions to human-readable markdown
- Compute and display usage statistics (tokens, tools, models, time)
- Group workspaces into named projects for cross-environment workflows

**Constraints:**
- Read-only: Never modifies source session files
- Network use: SSH for remote access and HTTPS for Claude web sessions when enabled
- Portable: No external dependencies required

---

## Supported Agents

| Agent | Developer | Format | Storage Location |
|-------|-----------|--------|------------------|
| Claude Code | Anthropic | JSONL | `~/.claude/projects/<workspace>/` |
| Codex CLI | OpenAI | JSONL | `~/.codex/sessions/<date>/` |
| Gemini CLI | Google | JSON | `~/.gemini/tmp/<hash>/chats/` |

Each agent stores sessions differently. See format specifications:
- [claude-code-format.md](agents/formats/claude-code-format.md)
- [codex-cli-format.md](agents/formats/codex-cli-format.md)
- [gemini-cli-format.md](agents/formats/gemini-cli-format.md)

### Agent Detection

When `--agent auto` (default):
1. Detect agent from storage path patterns (`.claude`, `.codex`, `.gemini`)
2. For ambiguous contexts, scan all known locations
3. Deduplicate sessions by file path

When `--agent <name>` is specified, only scan that agent's storage.

---

## Data Sources (Homes)

A **home** is a data source where agent sessions are stored.

| Home Type | Description | Access Method |
|-----------|-------------|---------------|
| `local` | Current machine | Direct filesystem |
| `wsl` | WSL distribution (from Windows) | UNC path (`\\wsl.localhost\...`) |
| `windows` | Windows (from WSL) | Mount path (`/mnt/c/Users/...`) |
| `web` | Claude.ai web sessions | HTTPS API (OAuth token) |
| `remote` | SSH-accessible machine | SSH (per-file read) |

### Web Session Access

Claude.ai web sessions are supported via the Anthropic API.

- Access token resolved from macOS Keychain or `~/.claude/.credentials.json`
- Organization UUID read from `~/.claude.json`
- Session lists are fetched from `/sessions`
- Session exports fetch full loglines and cache to `~/.agent-history/web-cache`
- `--web` includes web sessions; `--no-web` excludes them
- `--ah` includes web sessions by default

### Home Configuration

Homes are discovered as follows:
- Local is always present.
- WSL/Windows are implicitly included when available; no explicit `home add` is required.
- SSH remotes must be added explicitly via `home add user@hostname` (repeatable).

The `--ah` (all homes) flag automatically includes local + detected WSL/Windows + configured SSH remotes + web. `--no-wsl`, `--no-windows`, `--no-remote`, and `--no-web` are honored by scope resolution.

Projects/aliases share the same configuration file. Legacy `projects.json`/`aliases.json` files are auto-imported into `config.json` at load time (non-destructive). For test isolation or sandboxed runs, set `AGENT_HISTORY_CONFIG_DIR` to point the tool at a temporary config directory so the real `~/.agent-history/config.json` is untouched.

### Home Storage

Configuration stored in `~/.agent-history/config.json` (canonical key: `homes`; legacy `sources` may exist only for backwards compatibility and is no longer used).

**Simple format** (array of strings):
```json
{
  "homes": [
    "user@vm01",
    "user@vm02"
  ],
  "projects": {
    "myproj": {
      "local": ["/home/user/myproject"],
      "remote:vm01": ["/home/user/myproject"]
    }
  }
}
```

**Extended format** (array of objects with metadata):
```json
{
  "version": 2,
  "homes": [
    {
      "name": "vm01",
      "type": "ssh",
      "host": "user@vm01.example.com"
    },
    {
      "name": "wsl:Ubuntu",
      "type": "wsl",
      "distro": "Ubuntu"
    }
  ],
  "projects": {
    "myproj": {
      "local": ["/home/user/myproject"],
      "remote:vm01": ["/home/user/myproject"]
    }
  }
}
```

Both formats are supported for backward compatibility.

---

## Data Hierarchy

```
Home
└── Workspace (project directory)
    └── Session (conversation file)
        └── Message (user/assistant turn)
```

### Workspace

A workspace corresponds to a project directory where the user invoked the AI assistant.

**Workspace identification by agent:**
| Agent | Workspace Encoding |
|-------|-------------------|
| Claude Code | Path with `/` → `-` (e.g., `/home/user/proj` → `-home-user-proj`) |
| Codex CLI | Extracted from `cwd` field in session metadata |
| Gemini CLI | SHA-256 hash of path, resolved via index |

#### Hierarchical Workspaces

Workspaces at different levels of a directory hierarchy are treated as **separate workspaces**. A parent directory and its subdirectory can each have their own sessions, and they are listed independently.

**Example:**
- `/home/user/projects/monorepo` - workspace with 3 sessions
- `/home/user/projects/monorepo/packages/api` - separate workspace with 5 sessions
- `/home/user/projects/monorepo/packages/web` - separate workspace with 2 sessions

Each workspace is listed separately in `ws list` output. Users can combine related workspaces into a single **project** using `project add` if they want unified access.

**Rationale:**
- Users may work on different parts of a codebase independently
- Parent and child directories often have different concerns (e.g., root for CI/docs, subdirs for code)
- Merging would lose the distinction and make history harder to navigate

#### Workspace Path Decoding (Claude Code)

Claude Code encodes workspace paths by replacing `/` with `-`. Decoding these paths back to human-readable form is ambiguous when folder names contain dashes.

**Example ambiguity:**
- Encoded: `-home-alice-alice-projects-api`
- Could decode to:
  - `/home/alice/alice/projects/api` (correct)
  - `/home/alice/alice-projects-api` (incorrect)
  - `/home/alice/alice/projects-api` (incorrect)

**Decoding algorithm:**

1. **Filesystem probing:** Incrementally test path segments from left to right
   - For encoded `-home-alice-alice-projects-api`:
   - Test `/home` → exists → continue
   - Test `/home/alice` → exists → continue
   - Test `/home/alice/alice` → exists → continue
   - Test `/home/alice/alice/projects` → exists → continue
   - Test `/home/alice/alice/projects/api` → exists → return this path

2. **Greedy matching:** When a segment doesn't exist, try progressively longer dash-joined combinations
   - If `/home/alice/alice/projects/todo` doesn't exist:
   - Try `/home/alice/alice/projects/todo-app` → if exists, continue
   - Otherwise treat `todo-app` as a single segment (possibly non-existent leaf)

3. **Non-existent paths:** When the final path doesn't exist on filesystem:
   - The algorithm should still resolve parent segments correctly using filesystem probing
   - Only the non-existent leaf portion remains ambiguous
   - Prefer keeping the deepest resolvable parent structure

**Expected behavior examples:**

| Encoded Name | Filesystem State | Expected Decoded Path |
|--------------|------------------|----------------------|
| `-home-user-projects-my-app` | `/home/user/projects/my-app/` exists | `/home/user/projects/my-app` |
| `-home-user-projects-my-app` | `/home/user/projects/` exists, `my-app/` doesn't | `/home/user/projects/my-app` |
| `-home-alice-alice-projects-api` | Full path exists | `/home/alice/alice/projects/api` |
| `-home-alice-alice-projects-api` | `/home/alice/alice/projects/` exists, `api/` doesn't | `/home/alice/alice/projects/api` |
| `-home-alice-alice-projects-web-v2` | `/home/alice/alice/projects/web-v2/` exists | `/home/alice/alice/projects/web-v2` |

**Non-goal behaviors (bugs):**

| Encoded Name | Incorrect Decode | Reason |
|--------------|-----------------|--------|
| `-home-alice-alice-projects-api` | `/home/alice/alice-projects-api` | Merged segments incorrectly |
| `-home-user-projects-my-app` | `/home/user/projects/my/app` | Split dashed folder name |

#### Windows and WSL Path Encoding

- Windows paths encode the drive and separators: `C:\Users\me\project` → `C--Users-me-project`
- WSL UNC prefixes are normalized before decoding: `//wsl.localhost/Ubuntu/home/me` → `/home/me`

### Session

A session is a single conversation file containing messages.

**Session file patterns by agent:**
| Agent | Main Session | Agent/Sub-session | Format |
|-------|--------------|-------------------|--------|
| Claude Code | `<uuid>.jsonl` | `agent-<id>.jsonl` | JSONL |
| Codex CLI | `rollout-<id>.jsonl` | N/A (single file) | JSONL |
| Gemini CLI | `session-<date>-<id>.json` | N/A (single file) | JSON |

**Session types (Claude Code only):**
| Type | Pattern | Description |
|------|---------|-------------|
| Main | `<uuid>.jsonl` | Primary user conversation |
| Agent | `agent-<id>.jsonl` | Task spawned by main session via Task tool |

### Message

A message is a single turn in the conversation.

**Message roles (normalized):**
| Role | Description | Agent-specific names |
|------|-------------|---------------------|
| `user` | Human input or task prompt | All agents use `user` |
| `assistant` | AI response | Claude: `assistant`, Codex: `assistant`, Gemini: `model`/`gemini`/`assistant` |
| `system` | System messages (compaction markers, etc.) | Claude only |

The tool normalizes role names for consistent display: Gemini's `model`/`gemini` types are displayed as `assistant`.

**Message content types:**
| Type | Description | Agents |
|------|-------------|--------|
| `text` | Plain text content | All |
| `tool_use` | Tool invocation request | All |
| `tool_result` | Tool execution output | All |
| `thinking` | Model reasoning steps | Gemini (as `thoughts`) |
| `summary` | Compacted conversation history | Claude |

### Conversation Forks

Conversation fork detection is implemented for Claude sessions using `uuid`/`parentUuid` linkage.
Forked exports include a **Conversation Structure** summary and anchor links for branch navigation.

---

## Operations

### List Operations

**`ws list`** - Enumerate workspaces
- Input: Home scope, optional pattern filter
- Output: Home, workspace path, session count, status, last modified
- Behavior: Aggregate sessions from resolved scope (no extra scanning)

**`session list`** - Enumerate sessions
- Input: Workspace scope, home scope, optional date filter
- Output: Agent, home, workspace, filename, message count, modified date
- Behavior: List session file metadata from resolved scope (message counts are 0 unless `--counts` is used)

**`home list`** - Enumerate configured homes
- Input: None
- Output: Home name, type, status, session count (scope-based)
- Behavior: Lists configured/detected homes; no SSH connectivity checks

**`project list`** - Enumerate configured projects
- Input: None
- Output: Project name, source homes, workspace list (or count), session count when `--counts` is used
- Behavior: Read from config.json (no auto-resolution unless `--counts`)

### Show Operations

**`ws show`** - Display detailed workspace information
- Input: Workspace pattern or path
- Output: Workspace summary entries (same shape as `ws list`)
- Behavior: Aggregate sessions from resolved scope

**`session show`** - Display detailed session information
- Input: Session ID or file path
- Output: Session metadata summary (file, filename, message_count) or session dict from scope
- Behavior: Reads file metadata; does not render full conversation

**`home show`** - Display detailed home information
- Input: Home name or identifier
- Output: Home summary entry (same shape as `home list`)
- Behavior: Filtered view of `home list`

**`project show`** - Display detailed project information
- Input: Project name (optional, defaults to current project if in workspace)
- Output: Project name, total sessions, workspaces grouped by home
- Behavior: Aggregate sessions from resolved scope (no last-modified calculation)

### Export Operations

**`session export`** - Export sessions to markdown or NDJSON
- Input: Session scope, output directory, format options
- Output: Markdown (`.md`) or NDJSON (`.ndjson`) files per session
- Behavior:
  1. Resolve sessions from scope
  2. For each session:
     - Skip if output file exists and is newer than source (unless `--force`)
     - Parse messages from source format
     - Generate markdown with metadata, content, tool use/results
     - Write to output directory
  3. Report counts: exported, skipped, failed

**Export options:**
| Option | Effect |
|--------|--------|
| `--session <id>` | Export specific session IDs or filenames (repeatable) |
| `--minimal` | Omit metadata sections |
| `--split <n>` | Split conversations exceeding n lines |
| `--flat` | No workspace subdirectories |
| `--source` | Copy raw source files alongside markdown |
| `--json` | Export as NDJSON (unified schema) |
| `--force` | Re-export even if up-to-date |

**Notes:**
- `--session` restricts export to matching session IDs/filenames and reports missing IDs as failures.

**Output filename format:** `<source-prefix><timestamp>_<session-id>.(md|ndjson)`
- **Source prefix** (multi-home exports): `wsl_<distro>_`, `remote_<host>_`, `windows_<user>_` (local has no prefix)
- **Timestamp** from first message: `YYYYMMDDHHMMSS`
- **No timestamp**: If the first message lacks a timestamp, the filename is `<source-prefix><session-id>.(md|ndjson)`
- **Session ID**: Original filename stem

**Output directory structure:**
```
<output-dir>/
├── index.md                          # Summary manifest (optional)
├── <workspace-path>/                 # Workspace path segments when decoded
│   ├── 20250103181500_<uuid>.md     # Local session (no prefix)
│   ├── wsl_Ubuntu_20250103174500_<uuid>.md
│   └── remote_vm01_20250102103000_<uuid>.md
└── <workspace-id>/                   # Hash/encoded name when path cannot be decoded
    └── ...
```

Use `--flat` to disable workspace subdirectories.

**Index manifest (`index.md`):**
- Generated when multiple homes or multiple workspaces are exported
- Contains: export timestamp, workspace count, session count
- Lists sources with session counts
- Lists workspaces with session counts per source

**Markdown output structure:**
```markdown
# Claude Code Session: 550e8400-e29b-41d4-a716.jsonl
**Started:** 2025-01-03T10:15:00Z
**Ended:** 2025-01-03T18:15:00Z
**Messages:** 127

---

## Message 1: User
*2025-01-03T10:15:00Z*

Message content here

---

## Message 2: Assistant
*2025-01-03T10:15:05Z*

Response text

<details>
<summary>Metadata</summary>

**Model:** claude-3-5-sonnet
**Tokens:** 12 in / 34 out
**CWD:** /home/user/myproject
**Branch:** main
</details>

---
```

Forked Claude sessions include a **Conversation Structure** summary and per-message anchors for branch navigation (non-minimal exports).

**Minimal mode (`--minimal`):** Omits the per-message metadata details blocks.

**Split behavior (`--split <n>`):**
- Estimates ~30-50 lines per message (varies by content and metadata)
- Splits at message boundaries, preferring:
  1. Before user messages (cleanest break)
  2. After tool results
  3. After time gaps > 5 minutes
- Creates files: `<name>_part1.md`, `<name>_part2.md`, etc.
- Each part includes navigation links to adjacent parts

**Parallel export (`--jobs <n>`):**
- Processes multiple sessions concurrently
- Useful for large exports or remote sources
- Default: sequential unless `--jobs` is set

### Stats Operations

**`session stats`** - Compute and display usage metrics
- Input: Session scope, home scope, grouping options
- Output: Aggregate statistics
- Behavior:
  1. Auto sync: Sync the resolved scope to the metrics DB (unless `--no-sync`)
  2. Compute: Aggregate stats from the resolved scope
  3. Overlay: Overlay token/tool/time totals from the DB when sync runs

**Metrics computed:**
| Metric | Source |
|--------|--------|
| Session count | File count |
| Message count | Message array length |
| Token usage | Metrics DB (requires sync; auto by default) |
| Tool usage | Metrics DB (requires sync; auto by default) |
| Time spent | Metrics DB work-period calculation (requires sync; auto by default) |

**Time tracking algorithm (metrics DB):**
- **Gap threshold:** 30 minutes of inactivity marks end of a work period
- **Work period time:** Sum of gaps below the threshold
- **Outputs:** `work_period_seconds` totals and counts (no calendar time)

**Grouping dimensions:**
| Dimension | Groups by |
|-----------|-----------|
| `model` | Model name from assistant messages |
| `tool` | Tool name from tool_use blocks |
| `day` | Date portion of timestamp |
| `workspace` | Workspace name |
| `home` | Home identifier |
| `agent` | Agent type (claude, codex, gemini) |

**Notes:**
- `--by` accepts comma-separated dimensions (e.g., `--by model,tool,day`)
- Table output shows only the requested groupings; JSON output always includes `by_agent`, `by_home`, `by_workspace`, `by_model`, and `by_tool`, with `by_day` added only when requested
- `--no-sync` skips the automatic metrics sync (faster, but tokens/tools/time may be stale)

### Project Operations

**`project add`** - Add workspace to project
- Input: Project name, workspace pattern, home scope
- Output: Confirmation of added workspaces
- Behavior:
  1. Resolve workspaces matching pattern from specified homes
  2. Create project if not exists
  3. Add workspace references to project

**`project remove`** - Remove workspace or project
- Input: Project name, optional workspace
- Output: Confirmation
- Behavior:
  - With workspace: Remove workspace from project
  - Without workspace: Delete entire project

**Project storage:** `~/.agent-history/config.json`
```json
{
  "projects": {
    "myproject": {
      "local": ["/home/user/myproject"],
      "wsl:Ubuntu": ["/home/user/myproject"],
      "remote:vm01": ["/home/user/myproject"]
    }
  }
}
```

---

## Scope Resolution

### Pattern Matching

The `-n <pattern>` flag performs **case-insensitive substring matching** on workspace names.
Positional patterns use **exact matching** when the pattern looks path-like (`/`, `-`, or contains `/`), otherwise they use substring matching.

Examples:
- Pattern `auth` matches `authentication`, `oauth-service`, `my-auth-lib`
- Pattern `API` matches `api-server`, `rest-api`, `graphql-api`
- Empty pattern or `*` matches all workspaces

### Deduplication

Sessions are **not** deduplicated across homes. Each home/workspace pair is treated as a distinct scope; overlapping file names may appear multiple times if sources overlap.

### Workspace Scope

Priority order for workspace resolution:

1. **Explicit project**: `--project <name>` (single project) uses configured workspaces
2. **`--this` flag**: Force current workspace only (skip project auto-detection)
3. **Auto-detect project**: If cwd belongs to a project, use that project
4. **`--aw` (all workspaces)**: Only when no patterns are provided
5. **Explicit patterns**: Positional patterns and `-n <pattern>` filters
6. **Current workspace**: If cwd is in a workspace
7. **Fallback**: All workspaces

Positional patterns use exact matching when path-like; `-n` patterns always use substring matching.

### Home Scope

Priority order for home resolution:

1. **All homes**: `--ah` includes local + WSL/Windows + configured remotes + web
2. **Home type flags**: `--wsl`, `--windows`, `--local` (category selection)
3. **Explicit homes**: `--home <name>` and `-r <user@host>` (concrete home names)
4. **Local**: Default when no home specified

Notes:
- `--web` includes Claude web sessions
- `--no-wsl`, `--no-windows`, `--no-remote`, `--no-web` exclude those homes when used with `--ah`

### Combined Scope

Home and workspace scopes are orthogonal:

| Command | Workspace Scope | Home Scope |
|---------|-----------------|------------|
| `session list` | current | local |
| `session list --aw` | all | local |
| `session list --ah` | current | all configured |
| `session list --aw --ah` | all | all configured |
| `session list -n auth --ah` | pattern "auth" | all configured |

**Cross-home guard:** When running in a local workspace, non-local homes (`--ah`, `--wsl`, `--windows`, `-r/--home`) require an explicit workspace scope (`-n`, positional pattern, `--aw`, or `--project`). Otherwise the command errors to avoid ambiguous cross-home matching.

---

## Metrics Database

Location: `~/.agent-history/metrics.db` (SQLite)

### Purpose

Caches computed metrics for fast querying. Parsing every message in every session is expensive; the database stores pre-computed aggregates.

### Sync Behavior

Stats auto-sync by default. Sync happens for the resolved scope unless `--no-sync` is passed:
- Syncs only the sessions in scope (homes + workspaces + agent filters)
- Incremental: Skips files unchanged since last sync (by mtime)
- Additive: Deleted sessions remain until explicit reset
 
`--sync` is accepted for explicit refresh; `--force` re-syncs all files in scope.

### Schema

**sessions table (core columns):**
| Column | Type | Description |
|--------|------|-------------|
| file_path | TEXT | Session file path (primary key) |
| session_id | TEXT | Session identifier (if available) |
| workspace | TEXT | Workspace name |
| home | TEXT | Home identifier |
| agent | TEXT | Agent type |
| file_mtime | REAL | Source file mtime (Unix epoch) |
| is_agent | INTEGER | Claude agent session flag |
| parent_session_id | TEXT | Claude parent session id |
| message_count | INTEGER | Total messages |
| user_messages | INTEGER | User message count |
| assistant_messages | INTEGER | Assistant message count |
| input_tokens | INTEGER | Total input tokens |
| output_tokens | INTEGER | Total output tokens |
| cache_creation_tokens | INTEGER | Tokens written to cache |
| cache_read_tokens | INTEGER | Tokens read from cache |
| first_timestamp | TEXT | First message timestamp (ISO 8601) |
| last_timestamp | TEXT | Last message timestamp (ISO 8601) |
| work_period_seconds | REAL | Active time (gap-based) |
| num_work_periods | INTEGER | Number of work periods |

**tool_uses table:**
| Column | Type | Description |
|--------|------|-------------|
| file_path | TEXT | Foreign key to sessions |
| session_id | TEXT | Session id |
| tool_name | TEXT | Tool name |
| is_error | INTEGER | Tool error flag |
| timestamp | TEXT | Tool timestamp |

**messages table (aggregates per message):**
| Column | Type | Description |
|--------|------|-------------|
| file_path | TEXT | Foreign key to sessions |
| type | TEXT | Message type |
| timestamp | TEXT | Message timestamp |
| model | TEXT | Model name (if any) |
| input_tokens | INTEGER | Input tokens |
| output_tokens | INTEGER | Output tokens |

---

## Agent-Specific Indexes

### Gemini Index

Location: `~/.agent-history/gemini_index.json`

**Purpose:** Gemini CLI uses SHA-256 hashes of project paths as directory names. The index maps hashes back to human-readable paths.

### Structure

```json
{
  "abc123...": "/home/user/myproject",
  "def456...": "/home/user/other-project"
}
```

**Operations:**
- `gemini-index` - List all mappings
- `gemini-index --add` - Add current directory
- `gemini-index --add <path>` - Add specific path

The hash is computed from the absolute path string.

**Index updates:** The index is updated via `gemini-index` (and may also merge `~/.gemini/hash_index.json` if present). It is not auto-updated during normal commands.

### Codex Index

Location: `~/.agent-history/codex_index.json`

**Purpose:** Codex CLI stores sessions by date (`~/.codex/sessions/YYYY/MM/DD/`), not by workspace. The index maps session files to their workspace paths for efficient listing.

**Structure:**
```json
{
  "version": 3,
  "last_scan_date": "2025-01-03",
  "sessions": {
    "/path/to/session.jsonl": "/home/user/project"
  }
}
```

**Incremental updates:**
- Only scans date folders since last scan
- Removes stale entries for deleted files
- Workspace extracted from session metadata (`cwd` field)

---

## Error Handling

### Missing Data

| Condition | Behavior |
|-----------|----------|
| Workspace not found | Error with generic suggestion (e.g., use `--aw` or a pattern) |
| No sessions match | Empty result (not an error) |
| Session file corrupt | Skip file, log warning, continue |

### Remote Failures

| Condition | Behavior |
|-----------|----------|
| SSH connection failed | Error with connection details |
| Remote home unreachable | Skip home in `--ah` mode (no warning) |
| Remote fetch failure | Error with SSH output or missing file |

### Permissions

| Condition | Behavior |
|-----------|----------|
| Cannot read session file | Skip file, log warning |
| Cannot write output | Error before processing |
| Cannot create output directory | Create directory automatically |

---

## Remote Session Caching

When using SSH remote sources:

**Caching behavior:**
- Sessions are fetched to local cache before list/export
- Cache location: `~/.agent-history/remote-cache/<host>/<agent>/<workspace>/`
- Example: `~/.agent-history/remote-cache/vm01/claude/-home-user-myproject/`

**Incremental sync:**
- Per-file SSH reads (no rsync)
- Only missing or stale files are fetched (mtime-based refresh)
- Remote deletes purge cached files with matching filenames
- Cached `remote_`/`wsl_`/`windows_` directories in `~/.claude/projects/` are ignored in v2

**List vs Export:**
- `session list -r <host>`: Remote query with cache refresh
- `session export -r <host>`: Fetches to cache first, then exports

---

## Utility Operations

### Install

**`install`** - Report install status (compatibility stub)
- Accepts legacy install flags but performs no filesystem changes in v2
- Returns a status payload describing requested paths and flags

**Options:**
| Option | Effect |
|--------|--------|
| `--bin-dir` | Custom binary installation directory |
| `--skill-dir` | Custom skill installation directory |
| `--skip-cli` | Skip binary installation |
| `--skip-skill` | Skip skill installation |
| `--skip-settings` | Skip settings update |

### Reset

**`reset`** - Reset stored data
- Clears metrics database
- Clears configuration
- Clears caches (remote + web fetch cache)

**Options:**
| Option | Effect |
|--------|--------|
| `--db` | Reset metrics database only |
| `--config` | Reset configuration only |
| `--settings` | Reset caches only |

**Notes:**
- Prompts for confirmation when run interactively; use `-y` to skip

### Fetch

**`fetch`** - Pre-fetch remote sessions into local cache
- Applies the same home/workspace/agent filters as session export
- Useful for offline export or warming remote caches ahead of large operations

**Options:**
| Option | Effect |
|--------|--------|
| `-r <user@host>` | Restrict to SSH remotes |
| `--ah` | Fetch from all homes |
| `--agent <name>` | Filter by agent |

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.agent-history/config.json` | Unified configuration (homes, projects, settings) |
| `~/.agent-history/metrics.db` | Metrics cache database |
| `~/.agent-history/gemini_index.json` | Gemini hash→path mappings |
| `~/.agent-history/codex_index.json` | Codex session→workspace index |
| `~/.agent-history/remote-cache/<host>/<agent>/<workspace>/` | Cached remote session files |
| `~/.agent-history/web-cache/` | Cached Claude web sessions (JSONL) |

**Legacy files (auto-migrated on first use):**
- `~/.agent-history/projects.json` → Merged into `config.json`
- `~/.agent-history/aliases.json` → Merged into `config.json`
- `~/.claude-history/` → Migrated to `~/.agent-history/`

Default export directory: `./ai-chats/`

---

## Related Specifications

- [cli-spec.md](cli-spec.md) - Command syntax, flags, and output formats
- [agents/formats/claude-code-format.md](agents/formats/claude-code-format.md) - Claude Code JSONL structure
- [agents/formats/codex-cli-format.md](agents/formats/codex-cli-format.md) - Codex CLI JSONL structure
- [agents/formats/gemini-cli-format.md](agents/formats/gemini-cli-format.md) - Gemini CLI JSON structure
- [agents/features/](agents/features/) - Agent feature analysis (compaction, clearing, etc.)
- [schema/unified-json-schema.md](schema/unified-json-schema.md) - Normalized export format
