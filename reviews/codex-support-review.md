# Codex Support Rereview

## Context
- Reviewed current `agent-history` script after Codex support fixes.
- Focus: functional correctness for Codex vs Claude paths, export/list commands, stats sync, and agent flag handling.

## Findings
- `ExportConfig.from_args` still drops `args.agent`, so export-all helpers build configs with `agent="auto"` regardless of the CLI flag. As a result, `agent-history export --agent codex --ah` will continue exporting Claude sessions. (agent-history:109-156, 7318-7451)
- `lsw` additive path (local + remotes) ignores the agent flag: `_dispatch_lsw_additive` calls `collect_sessions_with_dedup` without propagating `args.agent`, so `lsw --agent codex --local -r host` lists Claude workspaces from the local side. (agent-history:8394-8424, 8531-8570)

## Improvements Observed
- Markdown conversion now dispatches to the Codex parser, so Codex exports/converts render correctly. (agent-history:6305-6665)
- Metrics sync now scans `~/.codex/sessions` via `_sync_codex_to_db`, so Codex sessions can populate the stats DB. (agent-history:5170-5189, 5022-5052)
- Agent flag is propagated through most list/export paths, except the two issues above.

## Testing
- Not run (pytest unavailable in environment).
