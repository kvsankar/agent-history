# TODO

## Handoff Context For Fresh Sessions

Use this section with `AGENTS.md` as the bootstrap context after clearing the
chat. `AGENTS.md` explains the supported coding agents and their storage
formats. This file explains the current branch state, architecture intent, and
next work.

### Current Branch And State

- Active branch: `feature/2.0-exploration`.
- As of the last check, the branch was aligned with `origin/feature/2.0-exploration`.
- Current known local changes:
  - `TODO.md` has handoff/planning edits.
  - `docs/agent-history-process-image.md` is untracked and contains a detailed prompt/brief for an architecture process diagram.
- Last known full test baseline after the January fixes:
  - `UV_CACHE_DIR=.uv-cache uv run pytest -q`
  - Result: `1289 passed, 6 skipped`.
- Recent commits on this branch are clustered around January 13, 2026 and focus on path/workspace normalization, non-local inventory, test isolation, and avoiding slow host probes:
  - `cee4cea` Skip WSL probe for Windows override tests
  - `d4af54c` Avoid pytest cache writes in docker runner
  - `2036941` Gate test-only probes and hide count columns
  - `bc3b1e4` Improve test isolation and fast path listings
  - `8244195` Fix path resolution and date filtering
  - `bbcf77b` Normalize cwd workspace detection
  - `cb69438` Remove unused remote workspace enumeration
  - `aa7fb47` Resolve non-local workspaces via inventory
  - `b683ce9` Unify workspace status and formatting
  - `370f29b` Deduplicate workspace encoding and project formatting
  - `8b48e74` Normalize project workspaces with workspace refs
  - `1fe5a7f` Remove unused stats helpers

### Product Shape

`agent-history` is a CLI for reading existing AI coding assistant conversation
files and turning them into consistent listings, exports, and metrics. It does
not record conversations, run an LLM, or write back into the agents' session
stores.

Supported sources:

- Claude Code: JSONL under `~/.claude/projects/<encoded-workspace>/`.
- Codex CLI: JSONL under `~/.codex/sessions/YYYY/MM/DD/`, workspace from session metadata `cwd`.
- Gemini CLI: JSON under `~/.gemini/tmp/<sha256-project-hash>/chats/`, with `gemini-index` for hash-to-path mapping.

Supported homes/environments:

- local filesystem
- WSL distros
- Windows-from-WSL
- SSH remotes
- Claude web sessions where supported

Primary commands/surfaces:

- `session list`, `session export`, `session stats`, `session show`
- `ws list`, `ws export`, `ws stats`, `ws show`
- `home list`, `home add/remove/show/export/stats`
- `project list/show/add/remove/export/stats`
- `gemini-index`
- Utility commands including `install`, `reset`, and `fetch`

### Architecture Intent

The branch is intentionally moving away from monolithic/script-style behavior
toward a cleaner package architecture. Preserve this direction when merging
or fixing behavior.

Important modules:

- `agent_history/cli/parser.py`: converts CLI arguments into structured `CommandRequest`.
- `agent_history/cli/orchestrator.py`: parse -> context -> resolve scope -> dispatch handler -> format output.
- `agent_history/scope/context.py`: builds runtime context, including current workspace/project and available homes.
- `agent_history/scope/resolver.py`: staged scope resolution pipeline.
- `agent_history/scope/stages/`: project, home, workspace, and session resolution stages.
- `agent_history/scope/cache.py`: lazy per-home session cache.
- `agent_history/adapters/inventory.py`: unified workspace/session inventory across agents and homes.
- `agent_history/scope/home_resolver.py`: home-specific path resolution strategy.
- `agent_history/utils/workspace_ref.py`: canonical workspace key/display normalization.
- `agent_history/backends/`: source-specific parsers/readers for Claude, Codex, Gemini, SSH, web.
- `agent_history/handlers/`: command behavior by resource/verb.
- `agent_history/output/formatter.py`: output formatting.
- `agent_history/export/`: markdown/NDJSON export, source copy, manifest, splitting.
- `agent_history/storage/`: config and metrics database.

Design constraints to preserve:

- Keep workspace identity normalized through shared workspace refs; avoid ad hoc path string manipulation where a helper exists.
- Keep scope resolution explicit and staged: command args -> scope args -> template records -> concrete records -> handler output.
- Use `InventoryProvider` and home resolvers for cross-agent/cross-home discovery; avoid reintroducing per-command scanning logic.
- Avoid slow or real host probing in tests unless a test explicitly opts in through override env vars.
- Do not regress exact workspace matching. Substring matching should be explicit (`-n` / contains-style discovery), not accidental.
- Prefer adapting intent from older/main-branch code into the new architecture over direct copy/paste.

### Recent Bug-Fix Context

The last repair work addressed slow/hanging tests and branch behavior around
scope resolution:

- Host WSL/Windows probing caused tests to hang or touch real user data. Tests
  should use env overrides like `CLAUDE_PROJECTS_DIR`, `CODEX_SESSIONS_DIR`,
  `GEMINI_SESSIONS_DIR`, `AGENT_HISTORY_CONFIG_DIR`, and `AGENT_HISTORY_HOME`.
- `home list` and `project list` now use fast metadata paths unless counts are
  explicitly requested.
- Remote probing is skipped in isolated test environments to avoid SSH delays.
- Explicit patterns should override implicit project detection. A call like
  `api.list_sessions("nonexistent-pattern-xyz")` should return no sessions even
  if the current directory belongs to a configured project.
- Some list/count columns are intentionally hidden or opt-in to avoid expensive
  session counting.

### Testing Notes

Use these commands as the starting point:

```bash
UV_CACHE_DIR=.uv-cache uv run pytest -q
UV_CACHE_DIR=.uv-cache uv run pytest tests/cli/commands/test_cli_hypothesis.py -vv
UV_CACHE_DIR=.uv-cache uv run pytest tests/cli/home -q
UV_CACHE_DIR=.uv-cache uv run pytest tests/cli/project -q
```

If `uv run pytest` fails due to cache permissions, set `UV_CACHE_DIR=.uv-cache`.
If subprocess CLI tests unexpectedly read real user sessions, check the test
environment isolation first.

## Main Branch Integration

- [x] Implement an internal coding-agent backend registry before porting more feature rewrites.
  - Goal: adding Pi or another source should mean adding/registering a backend module, not editing scattered `if agent == ...` branches.
  - Start with an internal plugin-style design, not third-party package loading:
    - Define an `AgentBackend` protocol/dataclass with stable capabilities such as `id`, `label`, `scan_sessions`, `read_messages`, `count_messages`, `render_markdown`, and home path resolution hooks.
    - Register built-in backends for Claude, Codex, Gemini, and later Pi through one registry module.
    - Derive CLI agent choices from the registry instead of hardcoding `("auto", "claude", "codex", "gemini")`.
    - Make `InventoryProvider`, list/count handling, export handling, NDJSON/Markdown rendering, and cross-home path resolution call backend capabilities rather than doing direct agent comparisons.
    - Keep source-specific parsing inside backend modules; keep scope resolution and handlers agent-agnostic where practical.
  - Add regression tests that prove a fake/minimal backend can be registered and discovered without changing handler or inventory code.
  - Implemented initial registry foundation in `agent_history/backends/registry.py`.
  - Migrated CLI agent choices, inventory scanning/workspace enumeration, list message counts, export read/render, and NDJSON normalization to backend capabilities.
  - Added fake-backend regression coverage proving parser and inventory discovery use registration.
  - Remaining cleanup before/alongside Pi: move stats sync parsing, remote command construction, low-level WSL path candidate selection, and generic Markdown presentation labels behind backend capabilities where that reduces hardcoded agent checks.
  - After this foundation, implement Pi support, HTML export, and non-Claude workspace/alias fixes on top of the registry.
- [x] Port Pi coding-agent support from `main` onto the backend registry.
  - Implement Pi JSONL parsing, workspace extraction, session scanning, message counting, Markdown export, and NDJSON normalization as backend capabilities.
  - Register Pi so `--agent pi`, inventory discovery, list/count, and export paths work without handler-specific Pi branches.
  - Add focused unit and CLI integration tests for Pi registry discovery, listing, and export.
- [ ] Finish backend-registry cleanup for remaining hardcoded agent dispatch.
  - [x] Move stats database sync parsing and workspace extraction behind backend capabilities.
    - `AgentBackend` now owns normalized stats extraction and workspace resolution hooks.
    - `sync_file_to_db()` and `sync_sessions_to_db()` use registered backend capabilities instead of storage-layer agent dispatch.
    - Added regression coverage for fake registered stats backends and Pi stats sync.
  - [x] Move SSH/remote command construction and remote path conventions behind backend capabilities.
    - Backend descriptors now provide optional remote workspace/session listing commands, workspace parsing, readable workspace labels, and remote file path fallbacks.
    - SSH transport executes backend-provided commands and parses the shared remote session line format without Claude/Codex/Gemini/Pi dispatch.
    - Added fake-backend regression coverage proving remote listing can be added through registration.
  - Move low-level WSL path candidate selection behind backend path capabilities.
  - Move generic Markdown presentation labels/titles behind backend metadata where practical.
  - Keep exact-match scope filters as ordinary data filters; only backend-specific behavior belongs in backend capabilities.
  - Add focused tests before each migration so future agents do not require handler/inventory/stats edits.
- [ ] Review changes recently pushed to `main` and determine how to merge the intent into `feature/2.0-exploration`.
  - Preserve the newer package architecture, scope pipeline, shared workspace/session model, and cleaner handler structure.
  - Rewrite or adapt main-branch code where direct merges would regress design quality or reintroduce older coupling.
  - Suggested start:
    - Fetch `main`/`master` as appropriate for the remote.
    - Inspect `git log feature/2.0-exploration..origin/<branch>` and `git diff feature/2.0-exploration...origin/<branch>`.
    - Classify main-branch changes as: directly portable, needs architectural rewrite, already superseded, or should be dropped.
    - Port behavior in small commits with tests, routing agent-specific behavior through the backend registry first.
- [ ] Add focused tests for every feature or behavior brought over from `main`.
  - Cover both the migrated behavior and the architectural integration points it touches.
  - Prefer tests that exercise supported command permutations rather than only narrow unit seams.
- [ ] Audit this branch for missing or broken functionality using multiple independent sub-agent reviews.
  - Compare expected CLI behavior across `session`, `ws`, `home`, `project`, `export`, `stats`, and agent filters.
  - Pay special attention to permutations involving `--ah`, `--aw`, `--this`, `--wsl`, `--windows`, `-r`, projects, patterns, dates, and `--agent`.
  - Include a hardcoded-agent-dispatch audit so backend-specific conditionals are either moved into registered backend capabilities or explicitly justified.
  - Consolidate findings into concrete bugs, missing tests, and design-compatible fixes.
  - Suggested sub-agent split:
    - Agent 1: CLI scope/permutation audit.
    - Agent 2: export/stats behavior audit.
    - Agent 3: backend format and cross-home inventory audit.
    - Agent 4: regression comparison against `main` and legacy `ah.py` behavior.

## Edge Case Tests

- [ ] Corrupted/malformed JSONL files (invalid JSON, missing fields)
- [ ] Empty workspaces (directory exists but no sessions)
- [ ] Very large sessions (>10k messages) with split
- [ ] Concurrent database access
- [ ] Import/export alias round-trip

## Remote Operations

- [ ] SSH timeout coordination (currently varies: 5s, 10s, 30s, 300s)
- [ ] Filenames with `|` character break remote parsing
- [ ] Check rsync availability on remote before operations
- [ ] Multiple Windows users enumeration

## Stats Database

- [ ] Schema migration atomicity (race condition possible)
- [ ] TOCTOU race (file deleted between stat and open)
- [ ] Query limits for large databases (>100k sessions)
- [ ] Codex cache semantics: consider per-turn vs cumulative token_count reporting

## Command Combinations

- [ ] Multiple `-r` flags only use first (document or warn)
- [ ] `--split --minimal` uses non-minimal line estimates
- [ ] `--alias` with pattern silently ignores pattern

## Record Type Support (moved from format docs)

### Claude Code

| Type | Status | Notes |
|------|--------|-------|
| `user` | ✅ Supported | User messages parsed and exported |
| `assistant` | ✅ Supported | Assistant messages parsed and exported |
| `summary` | ❓ Not handled | Compacted conversation summaries |
| `file-history-snapshot` | ❓ Not handled | File state snapshots |
| `queue-operation` | ❓ Not handled | Internal queue events |

### Codex CLI

| Type | Status | Notes |
|------|--------|-------|
| `session_meta` | ❓ Verify | ID, cwd, cli_version, source extracted |
| `turn_context` | ❓ Verify | Model name extracted for stats |
| `response_item.message` | ❓ Verify | User and assistant messages |
| `response_item.function_call` | ❓ Verify | Tool calls with arguments |
| `response_item.function_call_output` | ❓ Verify | Tool results |
| `response_item.custom_tool_call` | ❓ Verify | Custom/MCP tool calls |
| `response_item.custom_tool_call_output` | ❓ Verify | Custom tool results |
| `event_msg.token_count` | ✅ Supported | Token usage snapshots |
| `response_item.reasoning` | ❓ Not handled | Extended thinking summaries |
| `response_item.local_shell_call` | ❓ Not handled | Shell command executions |
| `response_item.web_search_call` | ❓ Not handled | Web search actions |
| `response_item.ghost_snapshot` | ❓ Not handled | Git snapshots |
| `compacted` | ❓ Not handled | Compacted conversation items |
| `event_msg` (other) | ❓ Not handled | Other event messages |

### Codex CLI Session Metadata Fields

| Field | Shown in Export | Used in Stats |
|-------|-----------------|---------------|
| `id` | ✅ Yes | ✅ Yes |
| `cwd` | ✅ Yes | ✅ Yes (workspace) |
| `cli_version` | ✅ Yes | ✅ Yes |
| `source` | ✅ Yes | ❌ No |
| `timestamp` | ✅ Yes | ✅ Yes |
| `originator` | ❌ No | ❌ No |
| `instructions` | ❌ No | ❌ No |
| `model_provider` | ❌ No | ❌ No |
| `git` (branch, commit) | ❌ No | ❌ No |
