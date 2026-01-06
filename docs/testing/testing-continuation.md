# Testing Continuation Prompt

Use this document to continue test/CLI work with the three-agent topology.

## Context

**Project:** agent-history - CLI tool for exporting coding agent session history

**Current Test Status:**
```
V1 tests:     63 passed, 2 skipped
Stats tests:  91 passed, 16 skipped
Scope tests:  245 passed, 43 skipped
Legacy tests: ~200 passed, 3 skipped
─────────────────────────────────────
Total:        611 passed, 65 skipped
```

## Agent Topology

Two project agents in `.claude/agents/`:

| Agent | Role | Can Access |
|-------|------|------------|
| `test-developer` | Runs tests, identifies failures, works in tests/ | `tests/`, `docs/testing/`, `docs/specs/`, `pytest.ini` |
| `cli-fixer` | Fixes agent-history script, cannot see tests | `agent-history`, `docs/specs/` |

**You are the Coordinator.** Your job:
1. Invoke `test-developer` to run tests and identify failures
2. Receive issue reports from test-developer
3. Pass issue descriptions to `cli-fixer` (without test code)
4. Have cli-fixer make fixes
5. Have test-developer verify fixes

**Never mix concerns** - keep test development and CLI fixing in separate agents.

---

## Pending Work

### Category A: CLI Bugs (cli-fixer)

These are CLI implementation issues causing test failures/skips:

#### 1. Project Infrastructure Not Implemented
- **Symptom:** 5 tests skip with "Project infrastructure not implemented"
- **Tests:** `--project` flag, project auto-detection, `project show`
- **Fix needed:** Implement project commands in CLI

#### 2. `--no-web` Flag Not Implemented
- **Symptom:** Tests skip with "--no-web not implemented"
- **Fix needed:** Add `--no-web` exclusion flag

#### 3. `--by model,tool` Database Schema Error
- **Symptom:** "no such column: m.model" when using multi-group stats
- **Test:** `test_stats_scope_combinations[all-all-none-model,tool]`
- **Fix needed:** Fix SQL query for multi-dimensional grouping

#### 4. Role Column Missing
- **Symptom:** Some stats tests skip because `role` column doesn't exist
- **Fix options:** Add `role` column to schema OR derive from `type` field

---

### Category B: Test Infrastructure (test-developer)

These need test fixtures or skip markers:

#### 1. Current Workspace Tests Need cwd
- **Symptom:** "Not in a Claude Code workspace"
- **Issue:** Tests for "current workspace" scope need to run FROM a workspace directory
- **Fix:** Either pass `cwd` to subprocess OR convert to `--aw` tests
- **Status:** Most fixed with skips, some may need proper fixtures

---

### Category C: Docker/Platform Work (Ubuntu environment)

These require specific infrastructure:

#### Agent 7: Cross-Environment Tests
- **Focus:** Windows ↔ WSL cross-filesystem access
- **Location:** `tests/env/` (doesn't exist yet)
- **Requirements:** Run on actual Windows/WSL platforms
- **Tests:**
  - `--wsl` flag from Windows
  - `--windows` flag from WSL
  - Cross-env error handling on Linux

#### Agent 8: Docker SSH Tests
- **Focus:** Real SSH testing with Docker containers
- **Location:** `tests/docker/` (needs creation)
- **Requirements:** Docker on Ubuntu
- **Deliverables:**
  ```
  tests/docker/
  ├── conftest.py                  # Docker fixtures
  ├── docker-compose.test.yml
  ├── Dockerfile.runner
  ├── Dockerfile.remote
  ├── test_ssh_connection.py       # Connect, auth, timeout
  ├── test_remote_operations.py    # ws list, session list, export
  └── test_multi_home.py           # --ah with local + remote
  ```

---

## Commands

```bash
# Run all tests
timeout 180 uv run pytest tests/ --tb=short -q

# Run specific suites
uv run pytest tests/v1/ --tb=short -q
uv run pytest tests/stats/ --tb=short -q
uv run pytest tests/scope/ --tb=short -q

# Run with verbose skip reasons
uv run pytest tests/ -v --tb=short | grep -E "SKIP|PASS|FAIL"
```

---

## Issue Report Format

When test-developer reports issues to coordinator:
```
ISSUE: [brief description]
TEST: [test file and function name]
EXPECTED: [what test expects]
ACTUAL: [what CLI does]
ENV_VAR/FLAG: [relevant env var or CLI flag]
```

When cli-fixer reports fixes:
```
FIXED: [brief description]
FUNCTION: [function name modified]
CHANGE: [what was changed]
```

---

## Environment Variables (Spec-Compliant)

| Variable | Purpose |
|----------|---------|
| `AGENT_HISTORY_HOME` | Override home directory |
| `AGENT_HISTORY_HOME_WSL` | Override WSL home (skips real WSL probing) |
| `AGENT_HISTORY_HOME_WINDOWS` | Override Windows home (skips real Windows probing) |
| `CLAUDE_PROJECTS_DIR` | Override Claude projects directory |
| `CODEX_SESSIONS_DIR` | Override Codex sessions directory |
| `GEMINI_SESSIONS_DIR` | Override Gemini sessions directory |

**Note:** The old `CLAUDE_SKIP_*` variables have been removed. Use `AGENT_HISTORY_HOME_*` instead.

---

## Success Criteria

All tests should either:
- **PASS** - Feature works correctly
- **SKIP** with clear reason - Requires infrastructure not available (Docker, project system, etc.)

No timeouts allowed. No unexplained failures.

---

## Workflow Example

```
Coordinator: "Run scope tests and report failures"
↓
test-developer: Runs tests, reports:
  "ISSUE: --project flag returns 'Project not found'
   TEST: test_project_flag_filters_to_project_workspaces
   EXPECTED: Filter to project workspaces
   ACTUAL: Error: Project 'myproject' not found
   FLAG: --project"
↓
Coordinator: "Fix the --project flag to handle project lookup"
↓
cli-fixer: Reads agent-history, finds issue, fixes:
  "FIXED: Project lookup now searches project config
   FUNCTION: get_project_workspaces()
   CHANGE: Added project config file parsing"
↓
Coordinator: "Verify the fix"
↓
test-developer: Runs tests, confirms pass
```
