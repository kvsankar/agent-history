# Exploratory Testing Issues

Date: 2026-06-03

Isolation used for all exploratory commands:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex
```

Raw session/project inputs were read only. The isolated run created only:

- `/tmp/agent-history-explore-20260603-codex/config.json`
- `/tmp/agent-history-explore-20260603-codex/metrics.db`
- `/tmp/agent-history-explore-20260603-codex/codex_index.json`

## 1. `home add --windows` Hits Workspace Scope Guard

Status: Fixed.

Command:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history home add --windows
```

Actual:

```text
Error: Cross-home access to Windows requires a workspace pattern.

Options:
  1. Add a workspace pattern: -n <pattern>
  2. Use --aw to list all workspaces
  3. Use --project to use a project's workspaces
```

Expected:

`home add --windows` should add the Windows home to config without requiring workspace scope flags.

Validation after fix:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-homeadd-test \
  ./agent-history home add --windows
```

Result:

```json
{"message": "Added home: windows"}
```

## 2. Windows Workspace Discovery Reports Zero Sessions

Status: Fixed.

Raw Windows session counts observed:

- Claude: 2,787 JSONL files
- Codex: 430 JSONL files
- Gemini: 20 JSON files
- Pi: 0 JSONL files

Command:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history ws list --windows --aw --format json
```

Actual:

Many Windows workspaces were discovered, but every row had `session_count: 0`.

Expected:

Discovered Windows workspaces should include non-zero session counts where backing session files exist.

Validation after fix:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history ws list --windows --aw --counts --format json
```

Result summary:

```text
workspace rows: 60
sessions: 1,028
agents: claude, codex, gemini
```

## 3. Remote Workspace Discovery Reports Zero Sessions

Status: Fixed.

Raw `sankar@ubuntuvm01` session counts observed:

- Claude: 17,802 JSONL files
- Codex: 10 JSONL files
- Gemini: 7 JSON files
- Pi: 0 JSONL files

Command:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history ws list -r sankar@ubuntuvm01 --aw --format json
```

Actual:

Remote workspaces were discovered, but every row had `session_count: 0`.

Expected:

Remote workspace rows should include non-zero session counts where backing session files exist.

Validation after fix:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history ws list -r sankar@ubuntuvm01 --aw --counts --format json
```

Result summary:

```text
workspace rows: 11
sessions: 16,788
```

## 4. Windows And Remote Session Listing Time Out

Status: Fixed.

Commands timed out after 20 seconds with no output:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list --windows --aw --since 2026-06-01 --format json

AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list --windows /mnt/c/sankar/projects/claude-history \
  --since 2026-01-01 --format json

AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list -r sankar@ubuntuvm01 --aw --since 2026-06-01 \
  --format json

AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list -r sankar@ubuntuvm01 \
  /home/sankar/sankar/projects/claude-history --since 2026-01-01 --format json
```

Expected:

Scoped Windows and remote listing should either return within an interactive time budget or show an explicit bounded/progress behavior.

Validation after fix:

Exact remote listing now returns data:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list -r sankar@ubuntuvm01 \
  /home/sankar/sankar/projects/claude-history --since 2026-01-01 --format json
```

Result included Claude and Codex sessions for `/home/sankar/sankar/projects/claude-history`.

Windows exact listing validation:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session list --windows /mnt/c/sankar/projects/claude-history \
  --since 2026-01-01 --format json
```

Result summary:

```text
sessions: 6
agents: claude
workspace: /mnt/c/sankar/projects/claude-history
```

## 5. Local Stats Report Zero Messages Despite Populated DB

Status: Fixed.

Isolated SQLite evidence:

```text
sessions: 23,716
messages: 503,406
tool_uses: 240,106
```

For current workspace:

```text
claude: 238 sessions, 43,534 messages
codex: 9 synced sessions, 298 messages
tool_uses: 15,295
```

Command:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session stats --this --no-sync --format json
```

Actual:

Stats reported `messages: 0`, zero user/assistant messages, and empty tool/model aggregates.

Expected:

Stats should report message, token, model, and tool aggregates from the scoped DB rows.

Validation after fix:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session stats --this --no-sync --format json
```

Result included:

```text
sessions: 260
messages: 43,849
user_messages: 15,065
assistant_messages: 28,784
tool aggregates: populated
model aggregates: populated
```

## 6. `session stats --this --sync` Mixes Scoped Sessions With Global Tokens/Tools

Status: Fixed.

Command:

```bash
AGENT_HISTORY_CONFIG_DIR=/tmp/agent-history-explore-20260603-codex \
  ./agent-history session stats --this --sync --format json
```

Actual:

The command reported `sessions: 260` for the current workspace, but token and tool totals were global local-history totals.

Expected:

All totals and breakdowns should use the same resolved scope.

Validation after fix:

`session stats --this --sync --format json` now reports scoped message/token/tool/model aggregates for the current workspace instead of global local-history totals.

## 7. Codex Session Counts Are Inconsistent

Status: Fixed for inventory and summary counts; DB counts remain scoped to synced rows by design.

Observed:

- Raw local Codex JSONL files: 709
- Isolated DB Codex sessions: 150
- `claude-history` stats Codex sessions: 22
- `claude-history` DB rows for Codex: 9

Expected:

Inventory, sync, DB, and stats should either agree or expose clear filtering reasons.

Validation after fix:

```text
raw local Codex rollout files: 709
Codex inventory scan: 709
Codex workspace summary total: 709
claude-history Codex inventory sessions: 22
```

The isolated metrics DB still has fewer Codex session rows until those sessions are synced into the DB; scoped stats now reports DB-backed message counts for the resolved scope rather than mixing in global totals.

## Regression Tests Added

Status: Added.

Coverage added:

- `home add --windows` dispatches as config-only work and does not resolve workspace scope.
- `ws list --windows --aw --counts` uses workspace summaries without full scope/session resolution.
- Exact full-path workspace scopes do not enumerate all workspaces.
- Remote session metadata listing does not force local cache fetches.
- Codex workspace summaries ignore stale index entries, out-of-root files, and non-rollout files.
- Exact Windows Claude lookups preserve the requested readable workspace path.

Validation:

```bash
.venv/bin/python -m pytest -q tests/unit/test_exploratory_regressions.py \
  tests/cli/remote/test_non_local_home_behavior.py \
  tests/cli/remote/test_remote_fetch_requirements.py \
  tests/cli/scope/test_cli_parser_windows_paths.py \
  tests/cli/index/test_codex_index_fallback.py \
  tests/unit/scope/test_resolver.py \
  tests/unit/storage/test_metrics_workspace_resolution.py \
  tests/cli/stats/test_stats_cli_behavior.py \
  tests/cli/stats/test_stats_sync_requirements.py
```

Result: `73 passed`.
