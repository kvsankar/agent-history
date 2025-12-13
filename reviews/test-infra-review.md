# Test Infrastructure Review (Round 3)

## Overview
- Inspected unit and integration tests under `tests/unit` and `tests/integration` for coverage and extensibility.
- Focus: agent selection (Claude/Codex/placeholder future agents), Codex end-to-end coverage, stats/export/list flows, and readiness to add a third model such as Gemini.

## Strengths
- Comprehensive unit coverage for Codex parsing/metrics/scan plus CLI agent propagation, including a propagation matrix that parameterizes `agent` with `["claude", "codex", "gemini", "future-agent"]` to guard against hardcoded values. (tests/unit/test_claude_history.py:965-1278)
- Unit tests assert parser selection, detect-agent behavior, metrics sync, and database agent tagging for Codex fixtures.
- Integration suite exercises key Claude flows (lsw/lss/export/stats/alias) across local/Windows/WSL permutations.

## Gaps / Risks
- No integration/E2E scenarios for Codex: listing sessions/workspaces, exporting Markdown, or stats sync from `~/.codex/sessions` are not exercised end-to-end. Failures in real Codex environments would only be caught by unit tests.
- Stats integration tests only populate Claude-style JSONL and do not verify Codex rows in the metrics DB (session/tool/message tables or agent column behavior).
- Export integration tests do not cover `--agent codex` or Codex-specific rollouts; they only ensure Claude paths produce Markdown.
- Workspace/session listing integration lacks `--agent codex` coverage (local/additive/all-homes), so regressions in Codex filtering could slip through.
- CLI parser acceptance/rejection is tested for known agents only; adding a new agent will require updating parser choices and detection behavior, but there is no positive integration test for a third agent.
- No contract tests around turn_context/model extraction for Codex or future agents (e.g., ensuring model is recorded in metrics DB).

## Readiness for a Third Agent (e.g., Gemini)
- Unit tests already assert that unknown agents fall back to auto and are rejected by the CLI flag; to add Gemini you’ll need to:
  - Extend `--agent` choices, detection logic, and backend scanners.
  - Add fixtures and parser/metrics tests for Gemini session format.
  - Add integration smoke tests for `lsw/lss/export/stats --agent gemini` with synthetic session trees.
- Current tests will fail until those updates are made; they document the existing “unknown → auto/CLI rejection” behavior.

## Suggested Next Tests
- Add Codex E2E coverage: create temp `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl` fixtures and run `lsw/lss/export/stats --agent codex` in integration tests.
- Add stats integration that asserts Codex sessions appear in DB with `agent='codex'`, workspace encoded, and model captured from `turn_context`.
- Add export integration that verifies Codex Markdown structure (tool calls/results, session metadata) and timestamp-based filenames.
- Add “mixed agents” integration to ensure `--agent auto/claude/codex` filters correctly across combined Claude/Codex fixtures.
- When adding Gemini, mirror the Codex unit + integration fixture pattern (parser, metrics, scan, export, agent detection) and update CLI choices.

## Test Execution
- Tests were **not run** in this environment (pytest not installed here). This review is static analysis of the suite.
