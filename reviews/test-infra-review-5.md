# Test Infrastructure Review (Round 5)

## What was run
- Command: `UV_CACHE_DIR=/tmp/uv-cache uv run pytest tests/integration/test_e2e_codex.py -q`
- Result: 7 passed, 5 failed in 0.72s.

## Failures
- All failures stem from a signature mismatch in Codex E2E tests:
  - `setup_env()` now accepts only one positional argument, but tests call it with `(tmp_path, cfg)`, raising `TypeError: setup_env() takes 1 positional argument but 2 were given`.
  - Affected tests:
    - `TestCodexStats.test_stats_sync_includes_codex_sessions`
    - `TestCodexStats.test_stats_display_codex_sessions`
    - `TestCodexStats.test_stats_codex_model_extraction`
    - `TestMixedAgents.test_stats_sync_both_agents`
    - `TestCodexWorkspaces.test_codex_sessions_have_workspace`

## Impact
- No Codex stats/mixed-agent coverage currently executes due to the argument mismatch, so these paths remain unvalidated.

## Suggested Fix
- Update `setup_env` to accept an optional config path (restoring previous signature), or adjust the failing tests to call the current signature and set `HOME/USERPROFILE` explicitly after creation of `cfg`.
- Re-run `tests/integration/test_e2e_codex.py` after the signature fix to validate Codex stats and mixed-agent flows.

## Notes
- The passing tests indicate basic Codex lsw/lss/export flows are covered, but stats/workspace verification remains untested until the setup mismatch is resolved.
