# Post-V1 Testing Continuation Prompt

Use this document to initialize a fresh Claude session for continuing test implementation after V1.

## Context

**Project:** agent-history - A CLI tool for exporting and analyzing coding agent session history (Claude Code, Codex CLI, Gemini CLI).

**V1 Status:** COMPLETE - 63 passed, 3 skipped, 0 failed

**Key Documents:**
- `docs/testing/testing-strategy.md` - Full testing strategy
- `docs/testing/testing-prompt.md` - Original V1 implementation prompt
- `docs/testing/v1-status.md` - V1 completion status
- `docs/specs/` - All specifications

## What V1 Delivered

```
tests/
├── conftest.py                    # Root fixtures
├── helpers/
│   ├── cli.py                     # CLI subprocess runner
│   ├── assertions.py              # Custom assertions
│   └── session_builders.py        # Session factory classes
├── fixtures/v1/
│   ├── claude_golden.jsonl        # 6 msgs, 500 in, 200 out
│   ├── codex_golden.jsonl         # 4 msgs, 300 in, 150 out
│   ├── gemini_golden.json         # 4 msgs, 400 in, 180 out
│   └── expected_values.json       # Pre-computed totals
└── v1/
    ├── test_claude_parser.py      # 10 tests
    ├── test_codex_parser.py       # 11 tests
    ├── test_gemini_parser.py      # 12 tests
    ├── test_cli_happy_paths.py    # 15 tests
    ├── test_unified_export.py     # 6 tests
    └── test_stats_golden.py       # 9 tests (3 skipped)
```

**Features Implemented:**
- `--json` flag for unified NDJSON export with role normalization

## Post-V1 Agents

Run these in order per `docs/testing/testing-prompt.md`:

### Agent 1b: Extended Fixtures (First Priority)

**Focus:** Build fixture library for telemetry, compaction, rejection, and forks.

**Read:**
- `docs/specs/agents/features/clearing.md`
- `docs/specs/agents/features/compaction.md`
- `docs/specs/agents/features/rejections.md`
- `docs/testing/testing-strategy.md` → Telemetry/Compaction/Rejection/Fork sections

**Deliverables:**
```
tests/fixtures/
├── telemetry/
│   ├── claude_history.jsonl     # /clear commands
│   ├── codex_history.jsonl      # /clear commands
│   └── gemini_logs.json         # /clear with new sessionId
├── compaction/
│   ├── claude/
│   │   ├── session_with_compaction.jsonl
│   │   └── <session-id>/session-memory/summary.md
│   └── codex/
│       └── session_with_compaction.jsonl
├── rejections/
│   ├── claude_with_rejection.jsonl
│   ├── codex_with_escalation.jsonl
│   └── gemini_with_tool_error.jsonl
└── forks/
    └── claude_forked_session.jsonl
```

---

### Agent 5: Scope Resolution Tests

**Focus:** Combinatorial testing of workspace/home/filter scopes.

**Read:**
- `docs/specs/cli-spec.md` → scope modifiers
- `docs/testing/testing-strategy.md` → "Category 4: Scope Resolution"

**Deliverables:**
```
tests/scope/
├── conftest.py                  # Multi-workspace/home fixtures
├── test_workspace_scope.py      # current, named, pattern, --aw, --project
├── test_home_scope.py           # local, --wsl, --windows, -r, --ah
├── test_filter_scope.py         # --since, --until, --agent
└── test_combinations.py         # Parameterized critical combos
```

---

### Agent 6: Stats Validation Tests

**Focus:** Deep validation of stats calculations.

**Read:**
- `docs/testing/testing-strategy.md` → "3c: Stats Commands"

**Deliverables:**
```
tests/stats/
├── conftest.py                  # Stats fixtures with known expected values
├── test_counts.py               # sessions, messages, user/assistant
├── test_tokens.py               # input, output, cache tokens
├── test_tools.py                # per-tool call counts
├── test_grouping.py             # --by model, tool, day, workspace
└── test_invariants.py           # Mathematical invariants
```

**Note:** Requires adding `role` column to schema or deriving from `type` field.

---

### Agent 7: Cross-Environment Tests

**Focus:** Windows ↔ WSL cross-filesystem access.

**Read:**
- `docs/testing/testing-strategy.md` → "Cross-Environment Access Testing"

**Deliverables:**
```
tests/env/
├── windows/
│   └── test_wsl_access.py       # --wsl flag from Windows
├── wsl/
│   └── test_windows_access.py   # --windows flag from WSL
└── linux/
    └── test_cross_env_errors.py # --wsl/--windows should error
```

---

### Agent 8: Docker SSH Tests

**Focus:** Real SSH testing with Docker containers.

**Read:**
- `docs/testing/testing-strategy.md` → "Docker SSH Integration Tests"
- `docs/testing/docker-e2e.md`

**Deliverables:**
```
tests/docker/
├── conftest.py                  # Docker fixtures
├── docker-compose.test.yml
├── test_ssh_connection.py
├── test_remote_operations.py
└── test_multi_home.py
```

---

## Skipped Tests to Fix

These 3 tests in `tests/v1/test_stats_golden.py` are skipped because they query a `role` column that doesn't exist:

1. `test_stats_user_assistant_breakdown`
2. `test_stats_invariants`

**Fix options:**
1. Add `role` column to messages table schema
2. Derive role from `type` field (user/assistant already used)

---

## Quick Reference

```bash
# Run V1 tests
uv run pytest -m v1

# Run all tests
uv run pytest

# Run specific agent tests
uv run pytest tests/v1/test_claude_parser.py -v
```

## Invocation Example

```
Start with Agent 1b (Extended Fixtures):
"Create extended fixtures for telemetry, compaction, rejection, and forks per docs/testing/testing-prompt.md Agent 1b specification"

Then run Agents 5-6 in parallel:
"Implement scope resolution tests" → Agent 5
"Implement stats validation tests" → Agent 6

Platform-specific:
"Implement cross-env tests" → Agent 7 (run on each platform)
"Implement Docker SSH tests" → Agent 8 (run on Ubuntu with Docker)
```
