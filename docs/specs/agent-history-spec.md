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
- Offline: No network calls except SSH for remote access and web session API
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
| `web` | Claude.ai web sessions | API with auth token |
| `remote` | SSH-accessible machine | SSH + rsync |

### Web Session Access

Claude.ai web sessions require authentication:
- **Token**: Session cookie from browser
- **Organization UUID**: Organization identifier

Authentication can be:
- **Automatic** (macOS): Extracted from system keychain
- **Manual**: Provided via `--token` and `--org-uuid` flags

Web sessions provide limited metadata compared to CLI agents:
- Conversation content and timestamps
- No token usage or tool execution details
- GitHub repository association (if available)
- Workspace resolution:
  - Build a GitHub→workspace map by scanning **local Claude workspaces only** for git remotes (origin) that point to GitHub; if a web session repo (`owner/repo`) matches, the corresponding local path is used.
  - This mapping is automatic and best-effort; there is no user config for repo→workspace mapping, and only GitHub remotes are considered.
  - If no local match, fall back to the GitHub repo string itself.
  - If no repo, fall back to `session_context.cwd` when present.
  - If none are available, workspace may remain unresolved.

### Home Configuration

Homes are discovered as follows:
- Local is always present.
- WSL/Windows/web are implicitly included when available; no explicit `home add` is required.
- SSH remotes must be added explicitly via `home add user@hostname` (repeatable).

The `--ah` (all homes) flag automatically includes local + detected WSL/Windows/web + configured SSH remotes. Use `--no-wsl`, `--no-windows`, or `--no-web` to exclude those implicit sources.

Projects/aliases share the same configuration file. Legacy `projects.json`/`aliases.json` files are auto-imported into `config.json` at load time (non-destructive). For test isolation or sandboxed runs, set `AGENT_HISTORY_CONFIG_DIR` to point the tool at a temporary config directory so the real `~/.agent-history/config.json` is untouched.

### Home Storage

Configuration stored in `~/.agent-history/config.json` (canonical key: `homes`; legacy `sources` may exist only for backwards compatibility and is no longer used):
```json
{
  "homes": [
    "user@vm01"
  ],
  "projects": {
    "myproj": {
      "local": ["-home-user-myproject"],
      "remote:vm01": ["-home-user-myproject"]
    }
  }
}
```

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
| `assistant` | AI response | Claude: `assistant`, Codex: `assistant`, Gemini: `gemini` |
| `system` | System messages (compaction markers, etc.) | Claude only |

The tool normalizes role names for consistent display: Gemini's `gemini` type is displayed as `Assistant`.

**Message content types:**
| Type | Description | Agents |
|------|-------------|--------|
| `text` | Plain text content | All |
| `tool_use` | Tool invocation request | All |
| `tool_result` | Tool execution output | All |
| `thinking` | Model reasoning steps | Gemini (as `thoughts`) |
| `summary` | Compacted conversation history | Claude |

### Conversation Forks

Claude Code sessions can have **forked conversations** where a single parent message has multiple child responses (e.g., user regenerated a response, or different branches were explored).

**Fork detection:**
- Messages are linked via `parentUuid` field
- A fork occurs when one message has multiple children
- Each branch represents an alternative conversation path

**Export behavior for forks:**
- Forked conversations are detected and marked in export header
- Fork points and branch information are summarized
- Navigation links help trace conversation paths

---

## Operations

### List Operations

**`ws list`** - Enumerate workspaces
- Input: Home scope, optional pattern filter
- Output: Workspace name, session count, last modified date
- Behavior: Scan agent storage directories, count session files

**`session list`** - Enumerate sessions
- Input: Workspace scope, home scope, optional date filter
- Output: Session ID, message count, file size, modified date
- Behavior: Scan workspace directories, count messages per file

**`home list`** - Enumerate configured homes
- Input: None
- Output: Home name, type, status, workspace count
- Behavior: Check connectivity for remote homes

**`project list`** - Enumerate configured projects
- Input: None
- Output: Project name, workspace count, home list
- Behavior: Read from projects configuration

### Export Operations

**`session export`** - Convert sessions to markdown
- Input: Session scope, output directory, format options
- Output: Markdown files with conversation content
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
| `--minimal` | Omit metadata sections |
| `--split <n>` | Split conversations exceeding n lines |
| `--flat` | No workspace subdirectories |
| `--source` | Copy raw source files alongside markdown |
| `--force` | Re-export even if up-to-date |

**Output filename format:** `<source-prefix><timestamp>_<session-id>.md`
- **Source prefix** (multi-home exports): `wsl_<distro>_`, `remote_<host>_`, `windows_` (local has no prefix)
- **Timestamp** from first message: `YYYYMMDDHHMMSS`
- **Session ID**: Original filename stem

**Output directory structure:**
```
<output-dir>/
├── index.md                          # Summary manifest (optional)
├── <workspace-name>/                 # Workspace subdirectory
│   ├── 20250103181500_<uuid>.md     # Local session (no prefix)
│   ├── wsl_ubuntu_20250103174500_<uuid>.md
│   └── remote_vm01_20250102103000_<uuid>.md
└── <another-workspace>/
    └── ...
```

Use `--flat` to disable workspace subdirectories.

**Index manifest (`index.md`):**
- Generated after multi-home export (`--ah`)
- Contains: export timestamp, workspace count, session count
- Lists sources with session counts
- Lists workspaces with session counts per source

**Markdown output structure:**
```markdown
# Claude Conversation
or
# Claude Conversation (Agent)  <!-- for agent sessions -->

> ⚠️ **Agent Conversation** notice (if applicable)

## Session Information
- Session ID, timestamps, workspace, git branch
- Model, token usage summary

---

## Message 1
**User** | 2025-01-03 10:15:00

Message content here

---

## Message 2
**Assistant** | 2025-01-03 10:15:05

Response text

### Tool Use: Read
```json
{"file_path": "/path/to/file"}
```

### Tool Result
File contents here...

---
```

**Minimal mode (`--minimal`):** Omits Session Information section, UUIDs, and navigation links.

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
- Default: 1 (sequential)

**Single file conversion:**
- Export accepts a single `.jsonl` or `.json` file path
- Converts directly to markdown without workspace context
- Supports remote files: fetches via SSH, converts locally

### Stats Operations

**`session stats`** - Compute and display usage metrics
- Input: Session scope, home scope, grouping options
- Output: Aggregate statistics
- Behavior:
  1. Sync: Parse sessions and store metrics in database
  2. Query: Aggregate metrics from database
  3. Display: Format and output results

**Metrics computed:**
| Metric | Source |
|--------|--------|
| Session count | File count |
| Message count | Message array length |
| Token usage | `usage` field in assistant messages |
| Tool usage | `tool_use` content blocks |
| Time spent | Gaps between message timestamps |

**Time tracking algorithm:**
- **Gap threshold:** 30 minutes of inactivity marks end of work period
- **Work period:** Continuous activity with gaps < 30 minutes
- **Effort time:** Sum of work period durations (excludes idle gaps)
- **Calendar time:** Last timestamp minus first timestamp (includes all gaps)
- **Concurrent agents:** Counted separately for effort, once for calendar

**Grouping dimensions:**
| Dimension | Groups by |
|-----------|-----------|
| `model` | Model name from assistant messages |
| `tool` | Tool name from tool_use blocks |
| `day` | Date portion of timestamp |
| `workspace` | Workspace name |
| `home` | Home identifier |
| `agent` | Agent type (claude, codex, gemini) |

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

**Project storage:** `~/.agent-history/projects.json`
```json
{
  "projects": {
    "myproject": {
      "local": ["-home-user-myproject"],
      "wsl": {"Ubuntu": ["-home-user-myproject"]},
      "remote": {"vm01": ["-home-user-myproject"]}
    }
  }
}
```

---

## Scope Resolution

### Pattern Matching

The `-n <pattern>` flag performs **case-insensitive substring matching** on workspace names.

Examples:
- Pattern `auth` matches `authentication`, `oauth-service`, `my-auth-lib`
- Pattern `API` matches `api-server`, `rest-api`, `graphql-api`
- Empty pattern or `*` matches all workspaces

### Deduplication

When multiple scope modifiers result in overlapping sessions:
- Sessions are deduplicated by **file path**
- The first occurrence is kept (order: local → WSL → Windows → remotes)
- Deduplication happens after all sources are scanned

### Workspace Scope

Priority order for workspace resolution:

1. **Explicit path**: Positional argument specifies exact workspace
2. **Pattern match**: `-n <pattern>` matches workspace names containing pattern
3. **Project**: `--project <name>` uses workspaces from named project
4. **Auto-detect project**: If cwd belongs to a project, use that project
5. **Current workspace**: Derive from current working directory
6. **All workspaces**: `--aw` flag

The `--this` flag overrides project auto-detection, forcing current workspace only.

### Home Scope

Priority order for home resolution:

1. **Explicit home**: `--home <name>` specifies saved home
2. **Home type flags**: `--wsl`, `--windows`, `--web`
3. **Remote flag**: `-r <user@host>` specifies SSH remote
4. **All homes**: `--ah` flag includes all configured homes
5. **Local**: Default when no home specified

Exclusion flags (`--no-wsl`, `--no-windows`, `--no-remote`) filter sources when using `--ah`.

### Combined Scope

Home and workspace scopes are orthogonal:

| Command | Workspace Scope | Home Scope |
|---------|-----------------|------------|
| `session list` | current | local |
| `session list --aw` | all | local |
| `session list --ah` | current | all configured |
| `session list --aw --ah` | all | all configured |
| `session list -n auth --ah` | pattern "auth" | all configured |

---

## Metrics Database

Location: `~/.agent-history/metrics.db` (SQLite)

### Purpose

Caches computed metrics for fast querying. Parsing every message in every session is expensive; the database stores pre-computed aggregates.

### Sync Behavior

Stats commands automatically sync before querying:
- Scope-aware: Only syncs workspaces being queried
- Incremental: Skips files unchanged since last sync (by mtime)
- Additive: Deleted sessions remain until explicit reset

Use `--no-sync` to query cached data without syncing.

### Schema

**sessions table:**
| Column | Type | Description |
|--------|------|-------------|
| id | TEXT | Session file path (primary key) |
| home | TEXT | Home identifier |
| workspace | TEXT | Workspace name |
| agent | TEXT | Agent type (claude, codex, gemini) |
| message_count | INTEGER | Total messages |
| user_messages | INTEGER | User message count |
| assistant_messages | INTEGER | Assistant message count |
| input_tokens | INTEGER | Total input tokens |
| output_tokens | INTEGER | Total output tokens |
| cache_creation_tokens | INTEGER | Tokens written to cache |
| cache_read_tokens | INTEGER | Tokens read from cache |
| first_timestamp | TEXT | First message timestamp (ISO 8601) |
| last_timestamp | TEXT | Last message timestamp (ISO 8601) |
| mtime | REAL | Source file modification time (Unix epoch) |

**tool_usage table:**
| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT | Foreign key to sessions |
| tool_name | TEXT | Tool name |
| call_count | INTEGER | Number of invocations |

**model_usage table:**
| Column | Type | Description |
|--------|------|-------------|
| session_id | TEXT | Foreign key to sessions |
| model_name | TEXT | Model identifier |
| message_count | INTEGER | Messages using this model |
| tokens | INTEGER | Tokens for this model |

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

**Progressive learning:** The index is updated automatically when running commands from directories that have Gemini sessions.

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
| Workspace not found | Error with suggestions (fuzzy match) |
| No sessions match | Empty result (not an error) |
| Session file corrupt | Skip file, log warning, continue |

### Remote Failures

| Condition | Behavior |
|-----------|----------|
| SSH connection failed | Error with connection details |
| Remote home unreachable | Skip home in `--ah` mode, log warning |
| rsync failure | Error with rsync output |

### Permissions

| Condition | Behavior |
|-----------|----------|
| Cannot read session file | Skip file, log warning |
| Cannot write output | Error before processing |
| Cannot create output directory | Create directory automatically |

---

## Remote Session Caching

When exporting from remote sources (SSH, WSL from Windows, Windows from WSL):

**Caching behavior:**
- Sessions are fetched to local cache before export
- Cache location: Within local agent storage directory with source prefix
- Example: `remote_vm01_<workspace>/` for SSH remote `vm01`

**Incremental sync:**
- Uses rsync for efficient transfer (SSH remotes)
- Only new/modified files are transferred
- Circular fetch prevention: Remote/WSL prefixed directories are skipped

**List vs Export:**
- `session list -r <host>`: Direct remote query, no caching
- `session export -r <host>`: Fetches to cache first, then exports

---

## Utility Operations

### Install

**`install`** - Install CLI and Claude Code skill
- Copies CLI binary to PATH directory (default: `~/.local/bin/`)
- Installs Claude Code skill files (default: `~/.claude/skills/agent-history/`)
- Updates Claude Code settings for session retention

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
- Clears projects

**Options:**
| Option | Effect |
|--------|--------|
| `--db` | Reset metrics database only |
| `--config` | Reset configuration only |

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.agent-history/config.json` | Home configuration |
| `~/.agent-history/projects.json` | Project definitions |
| `~/.agent-history/metrics.db` | Metrics cache database |
| `~/.agent-history/gemini_index.json` | Gemini hash→path mappings |
| `~/.agent-history/codex_index.json` | Codex session→workspace index |

Default export directory: `./ai-chats/`

---

## Related Specifications

- [cli-spec.md](cli-spec.md) - Command syntax, flags, and output formats
- [agents/formats/claude-code-format.md](agents/formats/claude-code-format.md) - Claude Code JSONL structure
- [agents/formats/codex-cli-format.md](agents/formats/codex-cli-format.md) - Codex CLI JSONL structure
- [agents/formats/gemini-cli-format.md](agents/formats/gemini-cli-format.md) - Gemini CLI JSON structure
- [agents/features/](agents/features/) - Agent feature analysis (compaction, clearing, etc.)
- [schema/unified-json-schema.md](schema/unified-json-schema.md) - Normalized export format
