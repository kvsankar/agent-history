# Testing Implementation Prompt

Use this document to initialize a fresh Claude session for implementing the test suite.

## Context

**Project:** agent-history - A CLI tool for exporting and analyzing coding agent session history (Claude Code, Codex CLI, Gemini CLI).

**Goal:** Implement a behavior-driven test suite based on the specifications.

**Key Documents:**
- `docs/testing/testing-strategy.md` - Full testing strategy (READ FIRST)
- `docs/testing/testing-review.md` - Review feedback and gaps
- `docs/specs/` - All specifications

## V1 First Principle

**Get V1 green before expanding.** The strategy defines a minimal V1 slice:
- Golden fixtures per agent (not comprehensive)
- CLI happy paths only (not all flag combinations)
- Single workspace, local home (not combinatorial)
- Stats with exact golden totals (not all groupings)

**Defer until V1 green:** Cross-env, Docker SSH, combinatorial scope matrices.

## Constraints

1. **No real agents** - Use synthetic JSONL/JSON fixtures only
2. **Environment isolation** - Never touch real `~/.claude`, `~/.codex`, `~/.gemini`
3. **Environment variables for injection:**
   - `CLAUDE_PROJECTS_DIR`, `CODEX_SESSIONS_DIR`, `GEMINI_SESSIONS_DIR` (per-agent)
   - `AGENT_HISTORY_HOME`, `AGENT_HISTORY_HOME_WSL`, `AGENT_HISTORY_HOME_WINDOWS` (cross-env)
4. **Three platforms:** Windows, WSL, Ubuntu - platform-specific tests use markers
5. **SQLite:** Use temp files, not in-memory (realistic I/O)
6. **CLI testing:** Both CliRunner (unit) and subprocess (E2E)

## Sub-Agent Work Breakdown

Use focused sub-agents for each testing domain. Each agent should read only the relevant specs and strategy sections.

**V1 agents run first (1-4). Later agents (5-8) run only after V1 is green.**

---

### Agent 1: V1 Golden Fixtures

**Focus:** Create golden fixture files for V1 parser tests.

**Read:**
- `docs/specs/agents/formats/claude-code-format.md`
- `docs/specs/agents/formats/codex-cli-format.md`
- `docs/specs/agents/formats/gemini-cli-format.md`
- `docs/testing/testing-strategy.md` → "V1 Parser Golden Fixtures" section

**Deliverables:**
```
tests/fixtures/v1/
├── claude_golden.jsonl          # User, assistant, tool_use, tool_result, interruption, rejection, compaction, thinking
├── codex_golden.jsonl           # User, assistant, function_call, function_call_output, turn_aborted, compacted, reasoning
├── gemini_golden.json           # User, gemini, toolCalls with result, info (cancelled), thoughts
└── expected_values.json         # Pre-computed expected parse results
```

**V1 Stats Golden Dataset (3 sessions):**
```
Session 1 (Claude): 6 messages, 500 input, 200 output, tools: Read, Edit
Session 2 (Codex):  4 messages, 300 input, 150 output, tools: shell
Session 3 (Gemini): 4 messages, 400 input, 180 output, tools: read_file
───────────────────────────────────────────────────────────────────────
Expected totals:    14 messages, 1200 input, 530 output, 4 tool calls
```

---

### Agent 1b: Extended Fixtures (Post-V1)

**Focus:** Build fixture library for telemetry, compaction, rejection, and forks.

**Read:**
- `docs/specs/agents/features/clearing.md`
- `docs/specs/agents/features/compaction.md`
- `docs/specs/agents/features/rejections.md`
- `docs/testing/testing-strategy.md` → "Telemetry Fixtures", "Compaction Fixtures", "Rejection Fixtures", "Fork/Branch Fixtures"

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
├── forks/
│   └── claude_forked_session.jsonl
└── builders/
    ├── __init__.py
    ├── base.py
    ├── claude.py
    ├── codex.py
    └── gemini.py
```

---

### Agent 2: Core Infrastructure

**Focus:** Set up pytest infrastructure, conftest files, markers, and base fixtures.

**Read:**
- `docs/testing/testing-strategy.md` → "Fixture Architecture", "Environment Strategy"

**Deliverables:**
```
tests/
├── conftest.py                  # Root fixtures
├── env/
│   └── conftest.py              # Platform detection, skip markers
├── pytest.ini                   # Markers, options
└── helpers/
    ├── __init__.py
    ├── cli.py                   # CLI runner helpers
    └── assertions.py            # Custom assertions
```

**Key Fixtures:**
```python
@pytest.fixture(scope="session")
def test_home(tmp_path_factory) -> Path:
    """Session-scoped isolated home directory."""

@pytest.fixture
def cross_env_homes(tmp_path) -> dict[str, Path]:
    """Local/WSL/Windows home directories for cross-env tests."""

@pytest.fixture
def cli_runner() -> CliRunner:
    """Click CLI test runner."""

@pytest.fixture
def metrics_db(tmp_path) -> Path:
    """Isolated metrics database path."""
```

**Markers:**
```python
pytest.mark.windows_only
pytest.mark.wsl_only
pytest.mark.linux_only
pytest.mark.docker
pytest.mark.ssh
pytest.mark.slow
pytest.mark.v1          # V1 minimal slice tests
```

---

### Agent 3: V1 Parser Tests

**Focus:** Test parsing of each agent's native session format.

**Read:**
- `docs/specs/agents/formats/claude-code-format.md`
- `docs/specs/agents/formats/codex-cli-format.md`
- `docs/specs/agents/formats/gemini-cli-format.md`
- `docs/specs/agents/features/*.md` (compaction, interruptions, rejections, clearing)

**Deliverables:**
```
tests/agents/
├── conftest.py
├── test_claude_parser.py
├── test_codex_parser.py
├── test_gemini_parser.py
└── test_unified_export.py
```

**Test Categories:**
- Basic message parsing (user, assistant)
- Tool use extraction
- Tool result handling
- Timestamp parsing
- Token usage extraction
- Thinking/reasoning
- Compaction boundaries
- Interruption markers
- Rejection detection

---

### Agent 4: CLI Tests

**Focus:** Test all CLI commands and options.

**Read:**
- `docs/specs/cli-spec.md`
- `docs/testing/testing-strategy.md` → "Category 3: CLI Commands"

**Deliverables:**
```
tests/cli/
├── conftest.py
├── test_ws_commands.py          # ws list, ws show
├── test_session_commands.py     # session list, session show
├── test_export_commands.py      # session export with all flags
├── test_stats_commands.py       # session stats with all flags
├── test_home_commands.py        # home list, home add
└── test_project_commands.py     # project list, project add
```

**Export Flags to Test:**
- `--minimal`, `--split N`, `--flat`, `--json`
- `--output PATH`, `--force`

---

### Agent 5: Scope Resolution Tests

**Focus:** Combinatorial testing of workspace/home/filter scopes.

**Read:**
- `docs/specs/cli-spec.md` → scope modifiers
- `docs/specs/agent-history-spec.md` → scope resolution
- `docs/testing/testing-strategy.md` → "Category 4: Scope Resolution (Combinatorial)"

**Deliverables:**
```
tests/scope/
├── conftest.py                  # Multi-workspace/home fixtures
├── test_workspace_scope.py      # current, named, pattern, --aw, --project
├── test_home_scope.py           # local, --wsl, --windows, -r, --ah
├── test_filter_scope.py         # --since, --until, --agent
├── test_exclusions.py           # --no-wsl, --no-windows, --no-remote
├── test_precedence.py           # Flag priority rules
└── test_combinations.py         # Parameterized critical combos
```

**Fixture Requirements:**
- Multiple workspaces per home
- Multiple homes (local, wsl, windows, remote)
- Sessions across date ranges
- Mixed agents in same workspace

---

### Agent 6: Stats Validation Tests

**Focus:** Deep validation of stats calculations.

**Read:**
- `docs/testing/testing-strategy.md` → "3c: Stats Commands (Deep Validation)"

**Deliverables:**
```
tests/stats/
├── conftest.py                  # Stats fixtures with known expected values
├── test_counts.py               # sessions, messages, user/assistant
├── test_tokens.py               # input, output, cache_creation, cache_read
├── test_tools.py                # per-tool call counts
├── test_grouping.py             # --by model, tool, day, workspace, home, agent
├── test_multi_group.py          # --by model,tool combinations
├── test_time_tracking.py        # calendar_time, effort_time, work_periods
├── test_invariants.py           # Mathematical invariants
└── test_sync.py                 # Incremental sync, --no-sync
```

**Validation Approach:**
```python
# Fixture defines expected values
FIXTURE = {
    "sessions": [...],
    "expected": {
        "sessions": 3,
        "messages": 15,
        "input_tokens": 5000,
        "tools": {"Read": 5, "Edit": 3},
    }
}

# Test validates computed matches expected
def test_token_totals(stats_fixture):
    result = run_stats()
    assert result.input_tokens == stats_fixture.expected["input_tokens"]
```

---

### Agent 7: Cross-Environment Tests

**Focus:** Windows ↔ WSL cross-filesystem access.

**Read:**
- `docs/testing/testing-strategy.md` → "Cross-Environment Access Testing"

**Deliverables:**
```
tests/env/
├── conftest.py                  # Platform detection, cross_env_homes fixture
├── windows/
│   ├── test_wsl_access.py       # --wsl flag from Windows
│   └── test_windows_local.py
├── wsl/
│   ├── test_windows_access.py   # --windows flag from WSL
│   └── test_wsl_local.py
├── linux/
│   └── test_cross_env_errors.py # --wsl/--windows should error
└── test_path_edge_cases.py      # Spaces, unicode, long paths
```

**Platform Markers:**
```python
@pytest.mark.windows_only
@pytest.mark.wsl_only
@pytest.mark.linux_only
```

---

### Agent 8: Docker SSH Tests

**Focus:** Real SSH testing with Docker containers.

**Read:**
- `docs/testing/testing-strategy.md` → "Docker SSH Integration Tests"

**Deliverables:**
```
tests/docker/
├── conftest.py                  # Docker fixtures (remote_sim, etc.)
├── docker-compose.test.yml
├── Dockerfile.runner
├── Dockerfile.remote
├── test_ssh_connection.py       # Connect, auth, timeout, unreachable
├── test_remote_operations.py    # ws list, session list, export, stats
├── test_multi_home.py           # --ah with local + remote
└── test_ssh_errors.py           # Connection lost, permission denied
```

**Markers:**
```python
@pytest.mark.docker
@pytest.mark.ssh
```

---

## Execution Order

**V1 agents run first (1-4). Later agents (5-8) run only after V1 is green.**

### V1 Phase (Get Green First)

**Step 1: Foundation (Parallel)**
- Agent 1 (V1 Golden Fixtures) - Create minimal fixtures per agent
- Agent 2 (Core Infrastructure) - Set up pytest, conftest, markers

**Step 2: Parsing (Depends on Step 1)**
- Agent 3 (V1 Parser Tests) - Test basic parsing with golden fixtures

**Step 3: CLI (Depends on Steps 1-2)**
- Agent 4 (CLI Tests) - Happy paths only (ws list, session list, export, stats)

**V1 Success Gate:** All V1 tests pass before proceeding.

### Post-V1 Phase (Expand After Green)

**Step 4: Extended Fixtures**
- Agent 1b (Extended Fixtures) - Telemetry, compaction, rejection, fork fixtures

**Step 5: Comprehensive Coverage (Parallel)**
- Agent 5 (Scope Resolution) - Combinatorial workspace/home/filter tests
- Agent 6 (Stats Validation) - Deep validation with groupings and invariants

**Step 6: Integration (Platform-Specific)**
- Agent 7 (Cross-Env) - Run on each platform (Windows, WSL, Ubuntu)
- Agent 8 (Docker SSH) - Run on Ubuntu with Docker

---

## Invocation Example

```
Read docs/testing/testing-strategy.md first.

V1 Phase (run these first):
1. "Create V1 golden fixtures" → Agent 1 scope
2. "Set up pytest infrastructure" → Agent 2 scope (parallel with 1)
3. "Implement V1 parser tests" → Agent 3 scope
4. "Implement CLI happy path tests" → Agent 4 scope

Run tests: pytest -m v1
If all pass, proceed to Post-V1 Phase.

Post-V1 Phase (only after V1 is green):
5. "Create extended fixtures" → Agent 1b scope
6. "Implement scope resolution tests" → Agent 5 scope
7. "Implement stats validation tests" → Agent 6 scope
8. "Implement cross-env tests" → Agent 7 scope
9. "Implement Docker SSH tests" → Agent 8 scope

Each agent should:
- Read only the specified docs
- Create the specified files
- Follow the testing strategy decisions
- Use synthetic fixtures, not real agent sessions
- Mark V1 tests with @pytest.mark.v1
```

---

## Quick Reference: Key Decisions

| Decision | Choice |
|----------|--------|
| Home injection | Environment variables (`CLAUDE_PROJECTS_DIR`, etc.) |
| Cross-env testing | All 3 platforms available (Windows, WSL, Ubuntu) |
| Database | Temp file (not in-memory) |
| Fixtures | Hybrid (static + dynamic) |
| CLI testing | Both CliRunner and subprocess |
| Network | Mock for unit tests, Docker for integration |
| SSH | Docker containers on Ubuntu |

---

## Validation Checklist

### V1 Gate (Must Pass First)

- [ ] Golden fixtures created for all 3 agents (Claude, Codex, Gemini)
- [ ] Parser tests pass with golden fixtures
- [ ] CLI happy paths work (ws list, session list, export, stats)
- [ ] Stats totals match expected values from V1 golden dataset

### Post-V1 Complete

- [ ] Telemetry fixtures (context clearing) created and tested
- [ ] Compaction/fork fixtures created and tested
- [ ] All CLI commands work with all flag combinations
- [ ] Scope resolution handles all dimension combinations
- [ ] Stats groupings and invariants validated
- [ ] Cross-env works on Windows, WSL, Ubuntu
- [ ] Docker SSH tests pass on Ubuntu
- [ ] Edge cases handled (empty, unicode, long paths, etc.)
