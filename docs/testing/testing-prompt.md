# Testing Implementation Prompt

Use this document to initialize a fresh Claude session for implementing the test suite.

## Context

**Project:** agent-history - A CLI tool for exporting and analyzing coding agent session history (Claude Code, Codex CLI, Gemini CLI).

**Goal:** Implement a behavior-driven test suite based on the specifications.

**Key Documents:**
- `docs/testing/testing-strategy.md` - Full testing strategy (READ FIRST)
- `docs/specs/` - All specifications

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

---

### Agent 1: Fixture Library

**Focus:** Build synthetic session generators for all three agents.

**Read:**
- `docs/specs/agents/formats/claude-code-format.md`
- `docs/specs/agents/formats/codex-cli-format.md`
- `docs/specs/agents/formats/gemini-cli-format.md`
- `docs/testing/testing-strategy.md` → "Synthetic Session Generation" section

**Deliverables:**
```
tests/
├── fixtures/
│   ├── builders/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseSessionBuilder
│   │   ├── claude.py            # ClaudeSessionBuilder
│   │   ├── codex.py             # CodexSessionBuilder
│   │   └── gemini.py            # GeminiSessionBuilder
│   ├── static/
│   │   ├── claude/              # Pre-built JSONL files
│   │   ├── codex/
│   │   └── gemini/
│   └── conftest.py              # Fixture factory functions
```

**Key Methods:**
```python
class ClaudeSessionBuilder:
    def with_workspace(self, name: str) -> Self
    def add_user_message(self, content: str) -> Self
    def add_assistant_message(self, content: str, model: str = None) -> Self
    def add_tool_use(self, tool: str, input: dict) -> Self
    def add_tool_result(self, tool_use_id: str, output: str, is_error: bool = False) -> Self
    def add_interruption(self) -> Self
    def add_compaction(self, summary: str, pre_tokens: int) -> Self
    def add_rejection(self, tool_use_id: str, reason: str) -> Self
    def with_timestamps(self, start: datetime, gap_seconds: int = 60) -> Self
    def with_tokens(self, input: int, output: int) -> Self
    def build(self) -> list[dict]
    def write_to(self, path: Path) -> Path
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
```

---

### Agent 3: Parser Tests

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

**Phase 1: Foundation**
1. Agent 1 (Fixtures) + Agent 2 (Infrastructure) - Can run in parallel
2. Agent 3 (Parsers) - Depends on fixtures

**Phase 2: CLI & Core**
3. Agent 4 (CLI) - Depends on infrastructure
4. Agent 5 (Scope) - Depends on multi-home fixtures

**Phase 3: Validation**
5. Agent 6 (Stats) - Depends on fixtures with known values

**Phase 4: Integration**
6. Agent 7 (Cross-Env) - Run on each platform
7. Agent 8 (Docker SSH) - Run on Ubuntu with Docker

---

## Invocation Example

```
Read docs/testing/testing-strategy.md first.

Then spawn sub-agents for each testing domain:

1. "Implement fixture library" → Agent 1 scope
2. "Set up pytest infrastructure" → Agent 2 scope
3. "Implement parser tests" → Agent 3 scope
...

Each agent should:
- Read only the specified docs
- Create the specified files
- Follow the testing strategy decisions
- Use synthetic fixtures, not real agent sessions
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

Before considering testing complete:

- [ ] All agent formats parse correctly (Claude, Codex, Gemini)
- [ ] All CLI commands work with all flag combinations
- [ ] Scope resolution handles all dimension combinations
- [ ] Stats values match expected from known fixtures
- [ ] Invariants hold (grouped sums = totals, effort <= calendar)
- [ ] Cross-env works on Windows, WSL, Ubuntu
- [ ] Docker SSH tests pass on Ubuntu
- [ ] Edge cases handled (empty, unicode, long paths, etc.)
