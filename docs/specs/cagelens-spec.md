# cagelens Specification

<!-- doc-meta
doc_role: spec
audience: contributor
lifecycle: current
content_type: requirements
surface: public
canonicality: primary
-->

This document specifies what `cagelens` does. It defines the functional requirements, supported agents, data sources, and operations.

For CLI syntax and output formats, see [cli-spec.md](cli-spec.md).
For agent-specific session formats, see [agents/formats/](agents/formats/).

---

## Purpose

`cagelens` is a read-only tool that browses, exports, and analyzes conversation history from AI coding assistants.

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
| Codex CLI | OpenAI | JSONL / JSONL.ZST | `~/.codex/sessions/<date>/` |
| Gemini CLI | Google | JSONL / legacy JSON | `~/.gemini/tmp/<project-id>/chats/` |
| Pi | Pi | JSONL | `~/.pi/agent/sessions/<workspace>/` |

Each agent stores sessions differently. See format specifications:
- [claude-code-format.md](agents/formats/claude-code-format.md)
- [codex-cli-format.md](agents/formats/codex-cli-format.md)
- [gemini-cli-format.md](agents/formats/gemini-cli-format.md)
- [pi-format.md](agents/formats/pi-format.md)

### Agent Detection

When `--agent auto` (default):
1. Detect agent from storage path patterns (`.claude`, `.codex`, `.gemini`, `.pi`)
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
- Session exports fetch full loglines and cache to `~/.cagelens/web-cache`
- `--web` includes web sessions; `--no-web` excludes them
- `--ah` includes web sessions by default

### Home Configuration

Homes are discovered as follows:
- Local is always present.
- WSL/Windows are implicitly included when available; no explicit `home add` is required.
- SSH remotes must be added explicitly via `home add user@hostname` (repeatable).

The `--ah` (all homes) flag automatically includes local + detected WSL/Windows + configured SSH remotes + web. `--no-wsl`, `--no-windows`, `--no-remote`, and `--no-web` are honored by scope resolution.

Projects/aliases share the same configuration file. Legacy `projects.json`/`aliases.json` files are auto-imported into `config.json` at load time (non-destructive). For test isolation or sandboxed runs, set `CAGELENS_CONFIG_DIR` to point the tool at a temporary config directory so the real `~/.cagelens/config.json` is untouched.

### Home Storage

Configuration stored in `~/.cagelens/config.json` (canonical key: `homes`; legacy `sources` may exist only for backwards compatibility and is no longer used).

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
| Claude Code | `<uuid>.jsonl` | `agent-<id>.jsonl` or nested subagent paths | JSONL |
| Codex CLI | `rollout-<id>.jsonl` / `.jsonl.zst` | N/A (single file) | JSONL |
| Gemini CLI | `session-<date>-<id>.jsonl` | nested `chats/<parent>/<agent>.jsonl` | JSONL |
| Gemini CLI (legacy) | `session-<date>-<id>.json` | N/A (single file) | JSON |
| Pi | `<timestamp>_<uuid>.jsonl` | branch tree entries in same file | JSONL |

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
| `assistant` | AI response | Claude: `assistant`, Codex: `assistant`, Gemini: `model`/`gemini`/`assistant`, Pi: `assistant` |
| `system` | System messages, tool results, warnings, compaction markers | Claude system records, Gemini info/error/warning, Pi tool/internal records |

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

Bare `cagelens` prints top-level help and exits successfully. It does not run a
list operation or scan session stores. Scoped defaults apply after the user
chooses an explicit operation such as `cagelens session list`.

### List Operations

**`ws list`** - Enumerate workspaces
- Input: Home scope, optional pattern filter
- Output columns: HOME, WORKSPACE, SESSIONS, STATUS, MODIFIED
- Behavior: Discovery command. Defaults to all workspaces in the selected homes
  unless a workspace pattern, project, or `--this` is provided.

**`session list`** - Enumerate sessions
- Input: Workspace scope, home scope, optional date filter
- Output columns: AGENT, HOME, WORKSPACE, FILE, MESSAGES, MODIFIED
- Behavior: List session file metadata from the resolved workspace scope. Defaults
  to the current workspace, or its auto-detected project when configured. Message
  counts are empty unless `--counts` is used.

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
| `--layout tree\|squashed\|flat` | Choose workspace directory layout (default: `squashed`) |
| `--flat` | Alias for `--layout flat` |
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
├── -home-user-project/               # With --layout squashed
│   └── 20250103181500_<uuid>.md
└── <workspace-id>/                   # Hash/encoded name when path cannot be decoded
    └── ...
```

Use `--layout squashed` for one Claude-style workspace folder, `--layout tree`
for workspace path segments, or `--layout flat`/`--flat` to disable workspace
subdirectories.

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

**`stats`** - Compute and display usage metrics
- Input: Session scope, home scope, grouping options
- Output: Aggregate statistics, with token/tool/model/time overlays when available
- Behavior:
  1. Default: Query cached metrics from the SQLite DB without scanning raw session files
  2. Fresh mode: With `--sync`, resolve the raw scope and refresh changed session files first
  3. Progress: For `--sync` table output, print a bounded sync indicator to stderr unless `--quiet`
  4. Compute: Aggregate stats from cached DB rows for the resolved DB scope

**Metrics computed:**
| Metric | Source |
|--------|--------|
| Session count | Metrics DB session rows |
| Message count | Metrics DB session/message rows |
| Token usage | Metrics DB |
| Tool usage | Metrics DB |
| Time spent | Metrics DB work-period calculation |

Top-level `cagelens stats` is the canonical stats entry point because metrics
cut across sessions, workspaces, homes, and projects. Resource-scoped stats
commands remain supported as convenience aliases:
- `session stats` -> top-level stats with session/workspace scope flags
- `ws stats` -> same stats engine, workspace-oriented scope
- `project stats <name>` -> same stats engine scoped to one project
- `home stats [name]` -> same stats engine scoped to selected homes

**Default summary output:**
- Starts with a scope banner:
  - requested scope, such as `all workspaces`, `project <name>`,
    `workspace glob <pattern>`, `workspace regex <regex>`,
    `current project <name>`, or `current workspace <path>`
  - matched home count/names
  - matched workspace count, with workspace names when the set is small
  - matched session count
- Then shows a compact dashboard:
  - total sessions and messages
  - main vs agent/subagent sessions when available
  - user vs assistant messages when available
  - token totals (input, output, cache read, cache creation) when available
  - tool totals and error counts when available
  - top model names when available
  - time summary when metrics DB data is available
- Then shows default breakdowns by agent, home, and workspace.
- Ends with concise coverage and drilldown pointers so users can see which
  metric families are summarized and how to expand each family.
- Workspace rows are truncated to the display limit. Truncation must include an actionable hint such as `use --top-ws all` or `--format json`.
- JSON output returns the full stats payload and must not be truncated for display.
- TSV output is explicit machine-readable output and must include summary rows as well as breakdown rows, not only workspace rows.
- The table scope banner must make workspace-vs-project scope visible. For
  example, `cagelens stats --glob '*bptrial*'` must identify the request as a
  workspace glob, while `cagelens stats --project bptrial` must identify it as
  a project scope. Bare `cagelens stats bptrial` is exact workspace scope.

**Rollup output:**
- `stats rollup` returns a stable table intended for repeated analysis and
  coding-agent consumption.
- Table output also starts with the same scope banner as summary stats.
- Required dimensions are supplied with `--by`, accepting comma-separated values.
- Supported dimensions: `project`, `workspace`, `home`, `agent`, `model`, `day`, `month`.
- Dimension aliases are accepted for common shorthand and plurals, including
  `ws`/`workspaces` for `workspace` and `proj`/`projects` for `project`.
- Supported metrics:
  - `time`: work-period `TIME_HMS`, `TIME_HOURS`, and raw `TIME_SECONDS`
  - `tokens`: input/output/cache token totals
  - `all`: time, tokens, sessions, messages, and tool/error counts
- Token rollups without `model` use session-level token totals. Rollups that
  include `model` use message-level token rows because model is message-scoped.
- Time rollups keep both machine-readable and human-readable forms. Table/TSV
  output includes `TIME_HMS` and `TIME_SECONDS`; JSON includes `time_hms` and
  `time_seconds`.
- Table and TSV token rollup columns use compact K/M/B suffixes by default.
  `-H`/`--human` is retained for explicitness. Use `--raw`/`--no-human` for
  raw numeric values. JSON output keeps raw numeric token fields.
- Table output right-aligns numeric columns and left-aligns dimensions.
- Table and TSV rollup output includes a totals row by default. `-c`/`--total`
  and `--totals` are retained for explicitness. Use `--no-total`/`--no-totals`
  to suppress it. The first dimension column contains `TOTAL`; remaining
  dimension columns are blank; numeric metric columns are summed.
- `--separator` prints `--` between the scope banner and table output, giving
  scripts and coding agents a simple record-separator marker for the tabular
  section. JSON output is unchanged.
- Rollup rows are sorted by the primary metric descending unless the grouping
  is time-only (`day`/`month`), which sorts chronologically.
- `--sort <fields>` overrides default sorting. It accepts comma-separated
  dimensions and metric fields: `metric`, `tokens`, `time`, `sessions`,
  `messages`, `input`, `output`, `cache-read`, `cache-create`, plus active
  dimensions such as `month`, `agent`, or `workspace`.
- `--asc` and `--desc` set sort direction. Without an explicit direction,
  explicit `--sort` fields sort ascending; default metric sorting remains
  descending except time-only rollups, which remain chronological.
- Examples:
  - `cagelens stats rollup --metric time --by project`
  - `cagelens stats rollup --metric time --by project,month`
  - `cagelens stats rollup --metric time --by workspace,day`
  - `cagelens stats rollup --metric tokens --by project,agent,model`
  - `cagelens stats rollup --metric all --by project`

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

**Stats flags:**
| Flag | Behavior |
|------|----------|
| `--sync` | Refresh source files before display (slower, freshest) |
| `--no-sync` | Query cached metrics only (default; retained for explicitness) |
| `--force` | With `--sync`, reprocess unchanged files too |
| `--quiet` | Suppress sync progress and informational stderr output |
| `--by <dims>` | Add requested groupings; accepts comma-separated values |
| `--models` | Compatibility alias for `--by model` |
| `--tools` | Compatibility alias for `--by tool` |
| `--by-day` | Compatibility alias for `--by day` |
| `--by-workspace` | Compatibility alias for `--by workspace` |
| `--time` | Expand work-period time details, including daily time totals |
| `--metric <name>` | Rollup metric: `time`, `tokens`, or `all` |
| `--top <N>` | Rollup row limit |
| `--sort <fields>` | Sort rollup rows by comma-separated fields |
| `--asc` | Sort rollup rows ascending |
| `--desc` | Sort rollup rows descending |
| `-c`, `--total`, `--totals` | Explicitly include the default totals row in rollup table/TSV output |
| `--no-total`, `--no-totals` | Suppress the default rollup totals row |
| `--separator` | Print `--` before the rollup table |
| `--top-ws <N>` | Show top N workspaces in table output |
| `--top-ws all` | Show all workspace rows in table output |
| `-H`, `--human` | Explicitly use default compact human-readable numbers and durations in rollup table/TSV output |
| `--raw`, `--no-human` | Use raw numeric values instead of compact K/M/B rollup token columns |

**Notes:**
- `--by` accepts comma-separated dimensions (e.g., `--by model,tool,day`)
- Table output always shows the dashboard, coverage/drilldown pointers, and default agent/home/workspace breakdowns, and adds requested groupings for model/tool/day/time
- JSON output always includes `by_agent`, `by_home`, `by_workspace`, `by_model`, and `by_tool`, with `by_day` added only when requested
- Cached stats can be stale. Use `--sync` to refresh from raw agent storage.

### Project Operations

**`project add`** - Add workspace to project
- Input: Project name, exact workspace(s), `--glob`/`--regex` workspace matchers,
  or workspace/home scope flags
- Output: Confirmation of added workspaces; with `--dry-run`, a preview of
  workspaces that would be added
- Behavior:
  1. Resolve the requested scope using the same workspace matching rules as
     `ws list`: positional workspaces are exact, `--glob` is shell-style
     matching, and `--regex` is Python regex search.
  2. Treat the resolved workspace set as a snapshot. The project stores exact
     workspace references by home; it does not store the glob/regex as a live
     rule.
  3. Create the project if it does not exist.
  4. Add any new workspace references and leave existing members unchanged.
  5. With `--dry-run`, do not write configuration; show the resolved
     workspaces and counts.
  6. If no workspaces match, return a non-zero error and leave configuration
     unchanged.

Examples:

```bash
cagelens project add auth --glob '/home/sankar/sankar/projects/auth*' --dry-run
cagelens project add auth --glob '/home/sankar/sankar/projects/auth*'
cagelens project add auth /home/sankar/sankar/projects/auth
```

Dynamic project rules are intentionally out of scope for `project add`; if
added later, they must use a separate explicit command such as
`project rule add`.

**`project remove`** - Remove workspace or project
- Input: Project name, optional workspace
- Output: Confirmation
- Behavior:
  - With workspace: Remove workspace from project
  - Without workspace: Delete entire project

**Project storage:** `~/.cagelens/config.json`
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

Workspace matching must be intentional:

- Positional workspace arguments are exact workspace paths or identifiers.
- `--glob <pattern>` performs explicit shell-style matching using `fnmatch`.
- `--regex <regex>` performs explicit Python regular-expression search.
- Multiple exact/glob/regex matchers are combined with OR semantics.
- `-n`/`--name` and implicit substring matching are not supported.
- Glob and regex patterns should be quoted in the shell. For example,
  `--glob '/home/user/projects/auth*'` reaches `cagelens` as a pattern, while
  an unquoted shell glob may be expanded to an existing filesystem path before
  `cagelens` runs.

Examples:
- `ws list /home/user/projects/auth` matches only that exact workspace.
- `ws list --glob '/home/user/projects/auth*'` matches shell-style wildcard paths.
- `ws list --regex '(^|/)auth($|/)'` matches paths containing `auth` as a path segment.
- `ws list --aw` lists all workspaces.

### Deduplication

Sessions are **not** deduplicated across homes. Each home/workspace pair is treated as a distinct scope; overlapping file names may appear multiple times if sources overlap.

### Workspace Scope

`ws list` is a discovery operation: with no workspace pattern, project, or
`--this` flag, it lists all workspaces in the selected home scope. The priority
order below applies to session-oriented commands (`session list`, `session
export`, and `session stats`).

Priority order for workspace resolution:

1. **Explicit project**: `--project <name>` (single project) uses configured workspaces
2. **`--this` flag**: Force current workspace only (skip project auto-detection)
3. **Auto-detect project**: If cwd belongs to a project, use that project
4. **`--aw` (all workspaces)**: Only when no patterns are provided
5. **Explicit workspace scope**: positional exact workspaces, `--glob`, or `--regex`
6. **Current workspace**: If cwd is in a workspace
7. **Fallback**: All workspaces

Positional workspace arguments are exact; pattern matching requires `--glob` or `--regex`.

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
| `ws list` | all | local |
| `session list` | current | local |
| `session list --aw` | all | local |
| `session list --ah` | current | all configured |
| `session list --aw --ah` | all | all configured |
| `session list --glob '*auth*' --ah` | glob pattern "*auth*" | all configured |

**Cross-home guard:** When running session-oriented commands from a local
workspace, non-local homes (`--ah`, `--wsl`, `--windows`, `-r/--home`) require an
explicit workspace scope (exact workspace, `--glob`, `--regex`, `--aw`, or `--project`).
Otherwise the command errors to avoid ambiguous cross-home matching. `ws list`
already defaults to workspace discovery and is not narrowed to the current
workspace.

---

## Metrics Database

Location: `~/.cagelens/metrics.db` (SQLite)

### Purpose

Caches computed metrics for fast querying. Parsing every message in every session is expensive; the database stores pre-computed aggregates.

### Sync Behavior

Stats query cached metrics by default. Sync happens only when `--sync` is passed:
- Syncs only the sessions in scope (homes + workspaces + agent filters)
- Incremental: Skips files unchanged since last sync (by mtime)
- Additive: Deleted sessions remain until explicit reset

`--no-sync` is accepted as an explicit cache-only no-op. `--force` re-syncs all files in scope when combined with `--sync`.

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

Location: `~/.cagelens/gemini_index.json`

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

Location: `~/.cagelens/codex_index.json`

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
- Cache location: `~/.cagelens/remote-cache/<host>/<agent>/<workspace>/`
- Example: `~/.cagelens/remote-cache/vm01/claude/-home-user-myproject/`

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

**`install`** - Install CLI and agent skill packages
- Installs the CLI wrapper to `~/.local/bin/cagelens` by default
- Installs the `cagelens` skill package into agent-native user skill directories
- Use `--agent <name>` to install one agent target; default installs all supported targets
- `--skill-dir` overrides agent-native skill targets with one explicit custom directory
- `--dry-run` prints the exact resolved install plan without writing files
- Does not modify agent settings files; `--skip-settings` is retained for legacy
  compatibility
- `install --help` must include default CLI/skill locations and examples while
  remaining short enough for quick terminal use
- Table output must render install actions as rows with component, agent, status,
  and path instead of a raw Python/JSON dictionary

**Options:**
| Option | Effect |
|--------|--------|
| `--bin-dir` | Custom binary installation directory |
| `--skill-dir` | Custom agent skill installation directory |
| `--skip-cli` | Skip binary installation |
| `--skip-skill` | Skip agent skill installation |
| `--skip-settings` | Skip legacy agent settings step |
| `--agent <name>` | Install skill package for one agent target |
| `--dry-run` | Print resolved install plan without writing files |

**Default skill targets:**
| Agent | Directory |
|-------|-----------|
| Claude Code | `~/.claude/skills/cagelens/` |
| Codex CLI | `${CODEX_HOME:-~/.codex}/skills/cagelens/` |
| Gemini CLI | `~/.gemini/skills/cagelens/` |
| Pi | `~/.pi/agent/skills/cagelens/` |

**Examples:**
```bash
cagelens install                 # Install CLI and all supported agent skills
cagelens install --dry-run        # Show exact paths without writing files
cagelens install --agent codex    # Install only the Codex skill package
cagelens install --skip-cli       # Install skill packages only
```

### Reset

**`reset`** - Reset stored data
- Clears metrics database
- Clears configuration
- Clears caches (remote + web fetch cache)

**Targets:**
| Target | Effect |
|--------|--------|
| `all` | Reset metrics database, config, and caches |
| `db` | Reset metrics database only |
| `config` | Reset configuration only |
| `cache` | Reset remote/web caches only |

**Notes:**
- Prompts for confirmation when run interactively; use `-y` to skip

### Fetch

**`fetch`** - Pre-fetch remote sessions into local cache
- Applies SSH remote, workspace, and agent filters
- Does not fetch local, WSL, Windows, or Claude web sessions
- Useful for offline export or warming remote caches ahead of large operations

**Options:**
| Option | Effect |
|--------|--------|
| `-r <user@host>` | Restrict to SSH remotes |
| `--ah` / `--all-remotes` | Fetch from all configured SSH remotes |
| `--agent <name>` | Filter by agent |

---

## File Locations

| File | Purpose |
|------|---------|
| `~/.cagelens/config.json` | Unified configuration (homes, projects, settings) |
| `~/.cagelens/metrics.db` | Metrics cache database |
| `~/.cagelens/gemini_index.json` | Gemini hash→path mappings |
| `~/.cagelens/codex_index.json` | Codex session→workspace index |
| `~/.cagelens/remote-cache/<host>/<agent>/<workspace>/` | Cached remote session files |
| `~/.cagelens/web-cache/` | Cached Claude web sessions (JSONL) |

**Legacy files (auto-migrated on first use):**
- `~/.cagelens/projects.json` → Merged into `config.json`
- `~/.cagelens/aliases.json` → Merged into `config.json`
- Older pre-rename config directories → Migrated to `~/.cagelens/`

Default export directory: `./.cagelens/exports/`

---

## Related Specifications

- [cli-spec.md](cli-spec.md) - Command syntax, flags, and output formats
- [agents/formats/claude-code-format.md](agents/formats/claude-code-format.md) - Claude Code JSONL structure
- [agents/formats/codex-cli-format.md](agents/formats/codex-cli-format.md) - Codex CLI JSONL structure
- [agents/formats/gemini-cli-format.md](agents/formats/gemini-cli-format.md) - Gemini CLI JSON structure
- [agents/features/](agents/features/) - Agent feature analysis (compaction, clearing, etc.)
- [schema/unified-json-schema.md](schema/unified-json-schema.md) - Normalized export format
