# Testing Strategy for agent-history

Draft strategy for behavior-driven testing based on specifications.

## Table of Contents

1. [Overview](#overview)
2. [V1 Minimal Slice](#v1-minimal-slice)
3. [Known Spec/Impl Conflicts](#known-specimpl-conflicts)
4. [Heavy Suite Gating](#heavy-suite-gating)
5. [Test Philosophy](#test-philosophy)
6. [Environment Strategy](#environment-strategy)
7. [Fixture Architecture](#fixture-architecture)
8. [Mocking Strategy](#mocking-strategy)
9. [Test Categories](#test-categories)
10. [Parameterization Strategy](#parameterization-strategy)
11. [Test Data Generation](#test-data-generation)
12. [Open Questions](#open-questions)

---

## Overview

### Goals

- **Spec-Driven**: Every test traces back to a specification requirement
- **Environment-Agnostic**: Tests run identically on Windows, WSL, Ubuntu
- **Synthetic Data**: No dependency on real coding agent sessions
- **Isolation**: Tests don't affect user's actual `~/.claude`, `~/.codex`, `~/.gemini` directories
- **Fast**: Avoid I/O-bound operations; use in-memory fixtures where possible

### Non-Goals (Phase 1)

- Running actual coding agents (Claude Code, Codex CLI, Gemini CLI)
- Generating real session files via agent automation
- Testing network-dependent features (SSH remotes, web sessions)
- Performance benchmarking

---

## V1 Minimal Slice

**Priority:** Get a minimal test suite green before expanding to combinatorial matrices.

### V1 Scope

| Layer | In V1 | Deferred |
|-------|-------|----------|
| **Parsers** | Golden fixtures per agent | Edge cases, malformed input |
| **CLI** | Happy paths only | All flag combinations |
| **Scope** | Single workspace, local home | Combinatorial matrices |
| **Stats** | Basic counts + goldens | All groupings, time tracking |
| **Cross-env** | Skip in V1 | Windows ↔ WSL |
| **Docker SSH** | Skip in V1 | Remote operations |

### V1 Parser Golden Fixtures

Each agent needs a single "golden" session file covering core record types:

| Record Type | Claude | Codex | Gemini |
|-------------|:------:|:-----:|:------:|
| User message | ✓ | ✓ | ✓ |
| Assistant message | ✓ | ✓ | ✓ |
| Tool use | ✓ | ✓ | ✓ |
| Tool result | ✓ | ✓ | ✓ |
| Tool error | ✓ | ✓ | ✓ |
| Interruption | ✓ | ✓ | ✓ |
| Rejection | ✓ | — | — |
| Compaction | ✓ | ✓ | — |
| Thinking/reasoning | ✓ | ✓ | ✓ |
| Token usage | ✓ | ✓ | ✓ |

### V1 CLI Happy Paths

| Command | V1 Test |
|---------|---------|
| `ws list` | Lists workspaces, shows session count |
| `session list` | Lists sessions in current workspace |
| `session export` | Exports to markdown, correct filename |
| `session export --json` | Exports to NDJSON unified format |
| `session stats` | Shows aggregate counts |

### V1 Stats Golden Dataset

**Three sessions with known totals:**

```
Session 1 (Claude): 6 messages, 500 input tokens, 200 output tokens, 2 tool calls (Read, Edit)
Session 2 (Codex):  4 messages, 300 input tokens, 150 output tokens, 1 tool call (shell)
Session 3 (Gemini): 4 messages, 400 input tokens, 180 output tokens, 1 tool call (read_file)
─────────────────────────────────────────────────────────────────────────────────────────────
Total:              14 messages, 1200 input tokens, 530 output tokens, 4 tool calls
```

**Expected stats output:**
```
sessions:           3
messages:           14
user_messages:      7
assistant_messages: 7
input_tokens:       1200
output_tokens:      530
tools:              Read: 1, Edit: 1, shell: 1, read_file: 1
```

### V1 Test Files

```
tests/
├── v1/
│   ├── test_claude_parser.py      # Parse golden fixture
│   ├── test_codex_parser.py       # Parse golden fixture
│   ├── test_gemini_parser.py      # Parse golden fixture
│   ├── test_unified_export.py     # Export all 3 to NDJSON
│   ├── test_cli_happy_paths.py    # ws list, session list, export, stats
│   └── test_stats_golden.py       # Validate against known totals
├── fixtures/
│   └── v1/
│       ├── claude_golden.jsonl
│       ├── codex_golden.jsonl
│       └── gemini_golden.json
```

### V1 Success Criteria

- [ ] All 3 agent parsers parse golden fixtures without error
- [ ] Unified export produces valid NDJSON for all 3 agents
- [ ] `ws list` shows correct workspace count
- [ ] `session list` shows correct session count
- [ ] `session export` creates correctly-named markdown file
- [ ] `session stats` totals match golden dataset exactly

### V1 Timeline

1. **Create golden fixtures** (Agent 1 partial)
2. **Parser tests** (Agent 3 partial)
3. **CLI happy paths** (Agent 4 partial)
4. **Stats golden validation** (Agent 6 partial)

Only after V1 is green: expand to combinatorial scope, cross-env, Docker SSH.

---

## Known Spec/Impl Conflicts

Before writing tests, these conflicts must be resolved:

### 1. `ws list` Output Fields

**Status:** Spec differs from implementation (see `docs/specs/todo.md`)

| Field | Spec Says | Impl Does |
|-------|-----------|-----------|
| HOME | ✓ | ✓ |
| WORKSPACE | ✓ | ✓ |
| SESSIONS | ✓ (count) | ❌ (missing) |
| LAST_MODIFIED | ✓ | ❌ (missing) |

**Decision:** Keep spec as-is. Implementation needs to be updated to add SESSIONS count and LAST_MODIFIED columns.

**Testing Decision:** V1 tests are written against the **spec** (WORKSPACE, SESSIONS, LAST_MODIFIED). Tests will fail until implementation is updated. This is intentional - the test failure tracks the impl gap.

### 2. Web Sessions Scope

**Status:** Undecided whether to include (see `docs/specs/todo.md`)

**Current state:**
- `web list`, `web export` commands exist
- `--web` flag on various commands
- Requires authentication (token + org-uuid)

**Testing Decision:** Web sessions are **out of scope** for V1 testing. If kept in final scope:
- Add tests for auth flow
- Add fixtures for web session format
- Mark with `@pytest.mark.web`

---

## Heavy Suite Gating

Heavy tests (Docker, SSH, cross-env) need explicit gating to keep CI fast.

### Markers and Skip Conditions

```python
# Mark heavy tests
@pytest.mark.docker   # Requires Docker
@pytest.mark.ssh      # Requires SSH containers
@pytest.mark.slow     # Takes > 10 seconds
@pytest.mark.cross_env  # Requires specific platform

# Skip by default in CI
def pytest_configure(config):
    if os.environ.get("CI") and not os.environ.get("RUN_HEAVY_TESTS"):
        config.addinivalue_line("addopts", "-m 'not (docker or ssh or slow)'")
```

### CI Configuration

```yaml
# Fast CI (default) - runs on every push
fast_tests:
  script: pytest -m "not (docker or ssh or slow)"
  timeout: 10m

# Heavy CI (scheduled/manual) - runs nightly or on demand
heavy_tests:
  script: pytest -m "docker or ssh"
  timeout: 30m
  only:
    - schedules
    - manual
```

### Timeout Budget

| Suite | Max Duration | Notes |
|-------|--------------|-------|
| V1 tests | 2 minutes | Must pass on every push |
| Parser tests | 30 seconds | Fast, no I/O |
| CLI tests | 2 minutes | Uses temp dirs |
| Docker SSH | 10 minutes | Container startup overhead |
| Cross-env | 5 minutes | Per platform |

### Skip Messaging

Tests should provide clear skip messages:

```python
@pytest.mark.docker
def test_ssh_connection():
    """
    SKIPPED: Requires Docker. Run with RUN_HEAVY_TESTS=1
    or use: pytest -m docker
    """
```

---

## Test Philosophy

### Behavior-Driven Approach

Tests describe **what the system does** from a user perspective, not implementation details.

**Format:**
```gherkin
Feature: Session Export
  Scenario: Export single session to markdown
    Given a Claude Code session with 5 messages
    When I run `agent-history session export`
    Then a markdown file is created in ./ai-chats/
    And the file contains all 5 messages in order
```

### Specification Traceability

Every test should reference the specification it validates:

| Test | Spec Reference |
|------|----------------|
| `test_claude_session_parsing` | `claude-code-format.md#record-types` |
| `test_workspace_encoding` | `agent-history-spec.md#workspace` |
| `test_export_filename_format` | `cli-spec.md#session-export` |

---

## Environment Strategy

### Challenge

The tool must work on:
- **Windows**: Native Python, UNC paths to WSL
- **WSL**: Linux Python, `/mnt/c/` paths to Windows
- **Ubuntu (native Linux)**: Standard POSIX paths

### Solution: Environment Abstraction Layer

```
┌─────────────────────────────────────────┐
│            Test Suite                   │
├─────────────────────────────────────────┤
│       Environment Abstraction           │
│  ┌──────────┬──────────┬──────────┐     │
│  │ Windows  │   WSL    │  Linux   │     │
│  │ Provider │ Provider │ Provider │     │
│  └──────────┴──────────┴──────────┘     │
├─────────────────────────────────────────┤
│         Synthetic Test Home             │
└─────────────────────────────────────────┘
```

### Environment Detection

```python
# Pseudocode
class TestEnvironment:
    @property
    def platform(self) -> Literal["windows", "wsl", "linux"]:
        """Detect current platform."""

    @property
    def path_separator(self) -> str:
        """Return OS-appropriate separator."""

    def make_path(self, *parts) -> Path:
        """Create platform-appropriate path."""
```

### Path Handling Tests

| Scenario | Windows | WSL | Linux |
|----------|---------|-----|-------|
| Local home | `C:\Users\alice` | `/home/alice` | `/home/alice` |
| WSL access | `\\wsl.localhost\Ubuntu\home\...` | N/A | N/A |
| Windows access | N/A | `/mnt/c/Users/...` | N/A |
| Workspace encoding | `C--Users-alice-proj` | `-home-alice-proj` | `-home-alice-proj` |

### Environment-Specific Test Marks

```python
@pytest.mark.windows_only
def test_wsl_unc_paths():
    """Test UNC path handling for WSL access from Windows."""

@pytest.mark.wsl_only
def test_mnt_c_paths():
    """Test /mnt/c/ path handling for Windows access from WSL."""

@pytest.mark.linux_only
def test_posix_paths():
    """Test standard POSIX path handling."""

@pytest.mark.cross_platform
def test_workspace_encoding():
    """Test workspace name encoding works on all platforms."""
```

---

## Fixture Architecture

### Test Home Isolation

**Problem:** Tests must not touch user's real `~/.claude`, `~/.codex`, `~/.gemini`.

**Solution:** Redirect "home" to a temp directory via environment/config injection.

```
test_home/
├── .agent-history/
│   ├── config.json
│   ├── projects.json
│   ├── metrics.db
│   ├── gemini_index.json
│   └── codex_index.json
├── .claude/
│   └── projects/
│       └── -home-testuser-myproject/
│           └── <uuid>.jsonl
├── .codex/
│   └── sessions/
│       └── 2025/01/03/
│           └── rollout-<id>.jsonl
└── .gemini/
    └── tmp/
        └── <hash>/
            └── chats/
                └── session-*.json
```

### Fixture Hierarchy

```
conftest.py (root)
├── test_home (session-scoped) - Creates isolated test directory
├── mock_config (function-scoped) - Injects test home path
└── session_builder (function-scoped) - Creates synthetic sessions

tests/agents/conftest.py
├── claude_session_factory
├── codex_session_factory
└── gemini_session_factory

tests/cli/conftest.py
├── cli_runner (CliRunner wrapper)
└── output_dir (temp export directory)
```

### Home Directory Injection Points

The application needs configuration hooks to read from test locations:

| Component | Injection Method |
|-----------|------------------|
| Agent session paths | Environment variable or constructor parameter |
| Config file location | `AGENT_HISTORY_HOME` env var |
| Metrics database | In-memory SQLite for tests |
| Export output | Temp directory per test |

**Required Code Changes:**

```python
# Application code needs this pattern
def get_home_dir() -> Path:
    if env_home := os.environ.get("AGENT_HISTORY_HOME"):
        return Path(env_home)
    return Path.home()

def get_claude_projects_dir() -> Path:
    return get_home_dir() / ".claude" / "projects"
```

---

## Mocking Strategy

### What We Mock (Phase 1)

| Component | Mock Type | Rationale |
|-----------|-----------|-----------|
| Session files | Synthetic fixtures | No real agents needed |
| Filesystem operations | Real (temp dir) | Need to test actual I/O |
| SQLite database | In-memory | Fast, isolated |
| SSH connections | Full mock | Network isolation |
| Web API calls | Full mock | Network isolation |
| System time | Controlled | Reproducible timestamps |

### What We Don't Mock

| Component | Rationale |
|-----------|-----------|
| JSONL/JSON parsing | Core functionality being tested |
| Path operations | Platform behavior is the point |
| Markdown generation | Output format is specification |
| CLI argument parsing | User interface under test |

### Synthetic Session Generation

**Problem:** Need realistic session data without running agents.

**Solution:** Session builder factories that produce valid JSONL/JSON.

```python
# Pseudocode
class ClaudeSessionBuilder:
    def __init__(self, workspace: str, session_id: str = None):
        self.workspace = workspace
        self.session_id = session_id or str(uuid.uuid4())
        self.messages = []

    def add_user_message(self, content: str, **kwargs) -> Self:
        """Add a user message."""

    def add_assistant_message(self, content: str, tools: list = None, **kwargs) -> Self:
        """Add an assistant message with optional tool use."""

    def add_tool_result(self, tool_use_id: str, output: str, is_error: bool = False) -> Self:
        """Add tool result."""

    def add_interruption(self) -> Self:
        """Add interruption marker."""

    def add_compaction(self, summary: str, pre_tokens: int) -> Self:
        """Add compaction boundary."""

    def build(self) -> list[dict]:
        """Generate JSONL records."""

    def write_to(self, path: Path) -> None:
        """Write session to file."""
```

### Telemetry Fixtures (Context Clearing)

Context clearing is recorded in telemetry files, not session files. Tests need these fixtures:

**Claude - `~/.claude/history.jsonl`:**
```json
{"display": "/clear ", "timestamp": 1762870614075, "project": "/home/user/myproject", "sessionId": "9d6909e3-aaea-454d-ab21-15c939e865b1"}
```

**Codex - `~/.codex/history.jsonl`:**
```json
{"session_id": "0199bf0a-f9b4-7de3-8628-f1ab7b42b75c", "ts": 1759848429, "text": "/clear"}
```

**Gemini - `~/.gemini/tmp/<hash>/logs.json`:**
```json
[
  {"sessionId": "sess-1", "messageId": 5, "type": "user", "message": "/clear", "timestamp": "2025-11-07T11:34:04.247Z"},
  {"sessionId": "sess-2", "messageId": 0, "type": "user", "message": "New session after clear", "timestamp": "2025-11-07T12:00:00.000Z"}
]
```

**Test Fixture Structure:**
```
tests/fixtures/telemetry/
├── claude_history.jsonl      # Contains /clear commands
├── codex_history.jsonl       # Contains /clear commands
└── gemini_logs.json          # Shows sessionId change after /clear
```

**Tests:**
```python
def test_detect_claude_clear(telemetry_fixtures):
    """Detect /clear in Claude history.jsonl."""
    clears = detect_context_clears("claude", telemetry_fixtures["claude_history"])
    assert len(clears) == 2
    assert clears[0].session_id == "9d6909e3-aaea-454d-ab21-15c939e865b1"

def test_gemini_clear_creates_new_session(telemetry_fixtures):
    """Gemini /clear creates new sessionId."""
    clears = detect_context_clears("gemini", telemetry_fixtures["gemini_logs"])
    assert clears[0].old_session_id == "sess-1"
    assert clears[0].new_session_id == "sess-2"
```

### Compaction Fixtures

**Claude - Dual-Layer Compaction:**

1. **Inline marker** in session JSONL:
```json
{
  "type": "system",
  "subtype": "compact_boundary",
  "content": "Conversation compacted",
  "uuid": "db0953ca-b5ae-4e37-a85c-7884b9d2cc5e",
  "parentUuid": null,
  "logicalParentUuid": "9f8cc203-0e27-444f-88e7-b3eb9eef86d1",
  "timestamp": "2025-12-16T10:37:04.233Z",
  "compactMetadata": {"trigger": "auto", "preTokens": 155116}
}
```

2. **Session memory file** at `<session-id>/session-memory/summary.md`:
```markdown
# Session Summary

## Current State
Working on feature X...

## Files Modified
- src/main.py
- tests/test_main.py

## Learnings
- Pattern A works better than B
```

**Codex - Inline Compaction:**
```json
{
  "timestamp": "2025-10-28T05:26:42.667Z",
  "type": "compacted",
  "payload": {
    "message": "**Progress + Plan Status**\n- Completed X\n- In progress Y\n\n**Outstanding TODOs**\n- Task 1"
  }
}
```

**Fixture Structure:**
```
tests/fixtures/compaction/
├── claude/
│   ├── session_with_compaction.jsonl
│   └── abc123-def456/
│       └── session-memory/
│           └── summary.md
├── codex/
│   └── session_with_compaction.jsonl
└── gemini/
    └── (none - Gemini has no compaction)
```

**Tests:**
```python
def test_claude_compaction_boundary(compaction_fixtures):
    """Parse Claude compact_boundary and link to summary.md."""
    session = parse_session(compaction_fixtures["claude"])
    boundaries = [m for m in session.messages if m.type == "compact_boundary"]
    assert len(boundaries) == 1
    assert boundaries[0].pre_tokens == 155116
    assert boundaries[0].summary_path.exists()

def test_codex_compaction_inline(compaction_fixtures):
    """Parse Codex inline compaction with payload.message."""
    session = parse_session(compaction_fixtures["codex"])
    compacted = [r for r in session.records if r.type == "compacted"]
    assert len(compacted) == 1
    assert "Progress + Plan Status" in compacted[0].message
```

### Rejection Fixtures

**Claude - Explicit Rejection:**
```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [{
      "type": "tool_result",
      "tool_use_id": "toolu_01CCX4pcawRMsHndU7hn4d8K",
      "content": "The user doesn't want to proceed with this tool use. The tool use was rejected (eg. if it was a file edit, the new_string was NOT written to the file). To tell you how to proceed, the user said:\nHold.",
      "is_error": true
    }]
  },
  "uuid": "3a7fb54f-a20b-4e93-92f1-21b64b16a22e"
}
```

**Codex - Inferred Rejection (missing output):**
```json
// Request with escalation
{"type": "response_item", "payload": {"type": "function_call", "name": "shell", "arguments": {"command": "rm -rf /", "sandbox_permissions": "require_escalated"}, "call_id": "call_abc"}}
// NO matching function_call_output for call_abc = rejection
```

**Gemini - Tool Error (not explicit rejection):**
```json
{
  "type": "gemini",
  "toolCalls": [{
    "name": "edit_file",
    "status": "error",
    "error": "Failed to edit, 0 occurrences found..."
  }]
}
```

**Fixture Structure:**
```
tests/fixtures/rejections/
├── claude_with_rejection.jsonl    # Explicit rejection with user reason
├── codex_with_escalation.jsonl    # Escalation request, no output = rejected
└── gemini_with_tool_error.jsonl   # Tool error (not user rejection)
```

**Tests:**
```python
def test_claude_rejection_detection(rejection_fixtures):
    """Detect Claude rejection and extract user reason."""
    session = parse_session(rejection_fixtures["claude"])
    rejections = detect_rejections(session)
    assert len(rejections) == 1
    assert rejections[0].tool_use_id == "toolu_01CCX4pcawRMsHndU7hn4d8K"
    assert rejections[0].user_reason == "Hold."

def test_codex_rejection_inference(rejection_fixtures):
    """Infer Codex rejection from missing function_call_output."""
    session = parse_session(rejection_fixtures["codex"])
    rejections = detect_rejections(session)
    assert len(rejections) == 1
    assert rejections[0].call_id == "call_abc"
    assert rejections[0].inferred == True
```

### Fork/Branch Fixtures (Claude Only)

Claude supports conversation forks via `parentUuid` chains.

**Fixture - Forked Conversation:**
```json
{"type": "user", "uuid": "msg-1", "parentUuid": null, "message": {"content": [{"text": "Start"}]}}
{"type": "assistant", "uuid": "msg-2", "parentUuid": "msg-1", "message": {"content": [{"text": "Response A"}]}}
{"type": "user", "uuid": "msg-3", "parentUuid": "msg-2", "message": {"content": [{"text": "Continue A"}]}}
{"type": "user", "uuid": "msg-4", "parentUuid": "msg-2", "message": {"content": [{"text": "Fork: try B instead"}]}}
{"type": "assistant", "uuid": "msg-5", "parentUuid": "msg-4", "message": {"content": [{"text": "Response B"}]}}
```

**Graph Structure:**
```
msg-1 (user: Start)
  └── msg-2 (assistant: Response A)
        ├── msg-3 (user: Continue A)          <- Branch 1
        └── msg-4 (user: Fork: try B instead) <- Branch 2
              └── msg-5 (assistant: Response B)
```

**Fixture Structure:**
```
tests/fixtures/forks/
└── claude_forked_session.jsonl
```

**Tests:**
```python
def test_fork_detection(fork_fixtures):
    """Detect fork point where parentUuid has multiple children."""
    session = parse_session(fork_fixtures["claude"])
    forks = detect_forks(session)
    assert len(forks) == 1
    assert forks[0].parent_uuid == "msg-2"
    assert set(forks[0].child_uuids) == {"msg-3", "msg-4"}

def test_export_graph_field(fork_fixtures):
    """Unified export includes graph field for forked sessions."""
    ndjson = export_unified(fork_fixtures["claude"])
    session_record = json.loads(ndjson.split("\n")[1])
    assert session_record["session"]["graph"]["has_forks"] == True
    assert len(session_record["session"]["graph"]["fork_points"]) == 1
```

### Mock Boundary Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    Test Boundary                        │
│  ┌────────────────────────────────────────────────────┐ │
│  │                Real Code Under Test                │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │ │
│  │  │ Parsers  │  │ CLI      │  │ Export/Stats     │  │ │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
│                          │                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │               Synthetic Layer                      │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │ │
│  │  │ Fixture  │  │ Test     │  │ In-Memory        │  │ │
│  │  │ Files    │  │ Home     │  │ Database         │  │ │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
│                          │                              │
│  ┌────────────────────────────────────────────────────┐ │
│  │                Mocked Layer                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │ │
│  │  │ SSH      │  │ Web API  │  │ External         │  │ │
│  │  │ Client   │  │ Calls    │  │ Processes        │  │ │
│  │  └──────────┘  └──────────┘  └──────────────────┘  │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Test Categories

### Category 1: Agent Format Parsing

Tests for parsing each agent's native session format.

**Specs:** `claude-code-format.md`, `codex-cli-format.md`, `gemini-cli-format.md`

| Test Area | Claude Code | Codex CLI | Gemini CLI |
|-----------|-------------|-----------|------------|
| Basic message parsing | `type: user/assistant` | `response_item.message` | `type: user/gemini` |
| Tool use extraction | `tool_use` blocks | `function_call` | `toolCalls` array |
| Tool result handling | `tool_result` blocks | `function_call_output` | `result` in toolCalls |
| Timestamp parsing | ISO 8601 with ms | ISO 8601 | ISO 8601 |
| Token usage | `message.usage` | `event_msg.token_count` | `tokens` object |
| Thinking/reasoning | `type: thinking` | `type: reasoning` | `thoughts` array |

**Example Tests:**

```gherkin
Feature: Claude Code Session Parsing

  Scenario: Parse user message
    Given a Claude session file with a user message
    When I parse the session
    Then I get a message with role "user"
    And the content matches the input text

  Scenario: Parse tool use with result
    Given a Claude session with Edit tool use
    And a following tool result
    When I parse the session
    Then the tool use has type "Edit"
    And the tool result is linked by tool_use_id

  Scenario: Handle interruption marker
    Given a Claude session with "[Request interrupted by user]"
    When I parse the session
    Then an interruption event is detected
```

### Category 2: Workspace & Session Discovery

Tests for finding workspaces and sessions across storage locations.

**Specs:** `agent-history-spec.md#workspace`, `agent-history-spec.md#session`

| Test Area | Description |
|-----------|-------------|
| Workspace discovery | Find all workspaces in agent storage |
| Workspace encoding/decoding | Path ↔ encoded name conversion |
| Session enumeration | List sessions in workspace |
| Agent file detection | Identify `agent-*.jsonl` as sub-sessions |
| Multi-agent scanning | Scan Claude + Codex + Gemini |

**Example Tests:**

```gherkin
Feature: Workspace Discovery

  Scenario: List workspaces from Claude storage
    Given Claude storage with workspaces "projectA" and "projectB"
    When I run `agent-history ws list`
    Then I see 2 workspaces listed

  Scenario: Decode workspace name
    Given a workspace directory "-home-alice-my-project"
    When I decode the workspace name
    Then I get "/home/alice/my-project"

  Scenario: Handle Windows workspace encoding
    Given a Windows workspace directory "C--Users-alice-project"
    When I decode the workspace name
    Then I get "C:\Users\alice\project"
```

### Category 3: CLI Commands

Tests for command-line interface behavior.

**Specs:** `cli-spec.md`

#### 3a: List Commands

| Command | Test Areas |
|---------|------------|
| `ws list` | Workspace enumeration, session counts, last modified |
| `session list` | Session enumeration, message counts, size |
| `home list` | Home configuration, status checking |
| `project list` | Project configuration display |

#### 3b: Export Commands

| Command | Test Areas |
|---------|------------|
| `session export` | Markdown generation, filename format, directory structure |
| `session export --minimal` | Omit metadata sections |
| `session export --split` | Split long conversations |
| `session export --flat` | No workspace subdirectories |
| `session export --json` | NDJSON unified format |

#### 3c: Stats Commands (Deep Validation)

Stats testing requires validating computed values against known fixture data, not just checking output format.

**Test Flow:**
```
Synthetic JSONL fixtures → App syncs to temp SQLite → Stats query → Validate output
```

**Stats Dimensions:**

| Dimension | Options | Flag |
|-----------|---------|------|
| **Scope** | (same as session list) | `--aw`, `--ah`, `-n`, etc. |
| **Grouping** | none, model, tool, day, workspace, home, agent | `--by` |
| **Multi-group** | combinations | `--by model,tool` |
| **Time mode** | off, on | `--time` |
| **Sync** | auto, skip | `--no-sync` |
| **Format** | table, tsv, json | `--format` |

**Output Values to Validate:**

| Category | Metrics | Source Field |
|----------|---------|--------------|
| **Counts** | sessions, messages, user_messages, assistant_messages | Computed from records |
| **Tokens** | input_tokens, output_tokens, cache_creation, cache_read, total | `message.usage.*` |
| **Tools** | per-tool call counts | `tool_use` blocks |
| **Models** | per-model message counts, tokens | `message.model` |
| **Time** | calendar_time, effort_time, work_periods, active_days | Timestamp analysis |

**Validation Strategy: Known Fixtures with Pre-Computed Expected Values**

```python
# Fixture with known values
STATS_FIXTURE = {
    "sessions": [
        {
            "id": "session-1",
            "agent": "claude",
            "messages": [
                {"role": "user", "tokens": None},
                {"role": "assistant", "tokens": {"input": 100, "output": 50}},
                {"role": "user", "tokens": None},
                {"role": "assistant", "tokens": {"input": 150, "output": 75}, "tools": ["Read", "Edit"]},
            ],
        },
    ],
    "expected": {
        "total": {
            "sessions": 1,
            "messages": 4,
            "user_messages": 2,
            "assistant_messages": 2,
            "input_tokens": 250,
            "output_tokens": 125,
            "tools": {"Read": 1, "Edit": 1},
        },
    },
}
```

**Invariants to Assert:**

```python
def test_stats_invariants(stats_result, expected):
    """Stats must satisfy mathematical invariants."""

    # 1. Message counts add up
    assert (stats_result.user_messages + stats_result.assistant_messages
            == stats_result.messages)

    # 2. Grouped totals equal ungrouped total
    by_model = run_stats("--by model")
    assert sum(m.input_tokens for m in by_model) == stats_result.input_tokens

    # 3. Per-day sums equal total
    by_day = run_stats("--by day")
    assert sum(d.sessions for d in by_day) == stats_result.sessions

    # 4. Tool counts match tool_use blocks in fixture
    assert stats_result.tools["Read"] == expected.tool_counts["Read"]

    # 5. Time: effort <= calendar
    assert stats_result.effort_time <= stats_result.calendar_time
```

**Grouping Combinations:**

| Grouping | Test Focus |
|----------|------------|
| (none) | Aggregate totals |
| `--by model` | Per-model breakdown sums to total |
| `--by tool` | Per-tool counts match tool_use blocks |
| `--by day` | Per-day breakdown sums to total |
| `--by workspace` | Per-workspace breakdown |
| `--by home` | Per-home breakdown |
| `--by agent` | Per-agent (claude/codex/gemini) |
| `--by model,tool` | Multi-dimension grouping |

**Time Tracking Fixtures:**

| Scenario | Fixture Design | Expected |
|----------|----------------|----------|
| Continuous work | Messages 1-2 min apart | effort ≈ calendar |
| With gaps | 2hr gap in middle | effort < calendar, 2 work periods |
| Overnight gap | Session spans midnight | Multiple work periods |
| Concurrent agents | Overlapping agent sessions | Effort counted per agent |

**Stats × Scope Combinations:**

```python
STATS_SCOPE_COMBOS = [
    # Basic stats
    ("current", "local", "none", None),
    ("all", "all", "none", None),

    # With grouping
    ("all", "local", "none", "model"),
    ("all", "all", "none", "day"),
    ("all", "all", "none", "agent"),

    # Multi-group
    ("all", "all", "none", "model,tool"),

    # With filters + grouping
    ("all", "local", "agent-claude", "model"),
    ("all", "all", "range", "day"),

    # Time mode
    ("all", "all", "none", "time"),
]
```

**Edge Cases:**

| Case | Expected Behavior |
|------|-------------------|
| Empty scope (no sessions) | Zero counts, no error |
| Session with no tokens | Tokens = 0, not null |
| Session with no tools | Tool counts empty |
| Codex session (no cache tokens) | Cache fields = 0 |
| Gemini session (different token fields) | Normalized correctly |

**Sync Validation:**

```python
def test_stats_sync_incremental(test_home):
    """Verify incremental sync works correctly."""
    create_session(test_home, messages=5)
    result1 = run_stats()
    assert result1.messages == 5

    # Add more messages
    append_messages(test_home, count=3)
    result2 = run_stats()  # Should re-sync
    assert result2.messages == 8
```

**Example Tests:**

```gherkin
Feature: Session Export

  Scenario: Export creates correct filename
    Given a session starting at 2025-01-03 18:15:00
    And session ID "abc123-def456"
    When I export to markdown
    Then the file is named "20250103181500_abc123-def456.md"

  Scenario: Export with --minimal omits metadata
    Given a session with 3 messages
    When I export with --minimal flag
    Then the output does not contain "## Session Information"

  Scenario: Export split at message boundary
    Given a session with 100 messages
    When I export with --split 50
    Then 2 files are created
    And each file has navigation links to the other
```

### Category 4: Scope Resolution (Combinatorial)

Tests for workspace and home scope handling. This is the most complex test category due to combinatorial scope interactions.

**Specs:** `cli-spec.md#scope-modifiers`, `agent-history-spec.md#scope-resolution`

#### Scope Dimensions

| Dimension | Options | Flag/Mechanism |
|-----------|---------|----------------|
| **Session** | one, some, all | positional ID, pattern, implicit |
| **Workspace** | current, one, some, all, project | cwd, positional, `-n`, `--aw`, `--project` |
| **Home** | local, wsl, windows, remote, named, all | default, `--wsl`, `--windows`, `-r`, `--home`, `--ah` |
| **Date filter** | none, since, until, range | `--since`, `--until` |
| **Agent filter** | auto, claude, codex, gemini | `--agent` |
| **Exclusions** | none, no-wsl, no-windows, no-remote | `--no-*` flags |
| **Override** | none, this | `--this` |

#### Scope Combination Matrix

**Workspace × Home combinations (core matrix):**

| | Local | WSL | Windows | Remote | --ah |
|---|:---:|:---:|:---:|:---:|:---:|
| **Current ws** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Named ws** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Pattern ws** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **--aw** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **--project** | ✓ | ✓ | ✓ | ✓ | ✓ |

**Filter overlay (applies to any base combination):**

| Filter | Combines With |
|--------|---------------|
| `--since 2025-01-01` | Any ws × home combination |
| `--until 2025-01-31` | Any ws × home combination |
| `--since X --until Y` | Any ws × home combination |
| `--agent claude` | Any ws × home combination |
| `--agent codex` | Any ws × home combination |
| `--agent gemini` | Any ws × home combination |

**Exclusion combinations (with --ah only):**

| Exclusion Flags | Result |
|-----------------|--------|
| `--ah` | All homes |
| `--ah --no-wsl` | All except WSL |
| `--ah --no-remote` | All except remotes |
| `--ah --no-wsl --no-remote` | Local + Windows only |
| `--ah --local` | Local only (overrides --ah) |

#### Priority/Precedence Rules to Test

| Scenario | Expected Behavior |
|----------|-------------------|
| `--project X` + `--this` | `--this` wins (current ws only) |
| `-n pattern` + `--aw` | `--aw` wins (all workspaces) |
| `--home foo` + `--ah` | Both apply? Or `--ah` wins? |
| `--wsl` + `--windows` | Both apply (multi-home) |
| `--agent claude` + Codex-only workspace | Empty result |

#### Test Parameterization Strategy

```python
# Workspace scope options
WS_SCOPES = [
    ("current", [], {}),                    # Default: current workspace
    ("named", ["my-project"], {}),          # Positional workspace name
    ("pattern", [], {"-n": "auth"}),        # Pattern match
    ("all", [], {"--aw": True}),            # All workspaces
    ("project", [], {"--project": "proj"}), # Project scope
]

# Home scope options
HOME_SCOPES = [
    ("local", {}),                          # Default: local
    ("wsl", {"--wsl": True}),
    ("windows", {"--windows": True}),
    ("remote", {"-r": "user@host"}),
    ("named", {"--home": "my-home"}),
    ("all", {"--ah": True}),
    ("all-no-wsl", {"--ah": True, "--no-wsl": True}),
]

# Filter options
FILTERS = [
    ("none", {}),
    ("since", {"--since": "2025-01-01"}),
    ("until", {"--until": "2025-01-31"}),
    ("range", {"--since": "2025-01-01", "--until": "2025-01-31"}),
    ("agent-claude", {"--agent": "claude"}),
    ("agent-codex", {"--agent": "codex"}),
]

# Critical combinations to test (not full cartesian - prioritized)
CRITICAL_SCOPE_COMBOS = [
    # Basic single-dimension
    ("current", "local", "none"),
    ("all", "local", "none"),
    ("current", "all", "none"),
    ("all", "all", "none"),

    # With filters
    ("current", "local", "since"),
    ("all", "all", "range"),
    ("pattern", "all", "agent-claude"),

    # Multi-home
    ("current", "wsl", "none"),
    ("current", "remote", "none"),
    ("all", "all-no-wsl", "none"),

    # Project scope
    ("project", "local", "none"),
    ("project", "all", "none"),

    # Edge cases
    ("named", "wsl", "agent-codex"),  # Codex on WSL, specific ws
]

@pytest.mark.parametrize("ws_scope,home_scope,filter_scope", CRITICAL_SCOPE_COMBOS)
def test_scope_combination(ws_scope, home_scope, filter_scope, test_fixtures):
    """Test critical scope combinations."""
    # Build command args from scope tuples
    # Execute and verify correct sessions returned
```

#### Fixture Requirements for Scope Tests

```
test_home/
├── local/
│   ├── .claude/projects/
│   │   ├── -home-user-projectA/     # 3 sessions
│   │   ├── -home-user-projectB/     # 2 sessions
│   │   └── -home-user-auth-service/ # 1 session (matches "auth")
│   ├── .codex/sessions/2025/01/
│   │   └── ...                      # 2 sessions
│   └── .gemini/tmp/<hash>/
│       └── ...                      # 1 session
├── wsl/
│   └── (mirror structure)
├── windows/
│   └── (mirror structure)
└── remote_vm01/
    └── (mirror structure)
```

#### Expected Result Counts (for verification)

| Scope Combination | Expected Sessions |
|-------------------|-------------------|
| current ws, local | Sessions in cwd workspace only |
| `--aw`, local | All sessions in local home |
| current ws, `--ah` | Current ws across all homes |
| `--aw --ah` | Everything |
| `-n auth`, local | Sessions in workspaces matching "auth" |
| `--aw --agent claude`, local | All Claude sessions in local |
| `--aw --ah --since 2025-01-01` | Everything after date |

#### Edge Cases

| Case | Test |
|------|------|
| Empty result | Valid scope but no matching sessions |
| Workspace not found | Error with suggestions |
| Home unreachable | Skip with warning (--ah) or error (specific) |
| Pattern matches nothing | Empty result (not error) |
| Project has no workspaces | Empty result |
| Mixed agents in workspace | Filter works correctly |
| Session spans date boundary | Included if start OR end in range? |

### Category 5: Unified Schema Export

Tests for normalized NDJSON output.

**Specs:** `unified-json-schema.md`

| Test Area | Description |
|-----------|-------------|
| Header record | Schema version, export metadata |
| Session record | Normalized session fields |
| Message normalization | Role unification, content blocks |
| Reasoning normalization | `format` field for thinking/summary/thoughts |
| Tool normalization | Unified tool_use/tool_result |
| Gemini tool split | Extract results to synthetic user messages |

**Example Tests:**

```gherkin
Feature: Unified Export Schema

  Scenario: Normalize Gemini role to assistant
    Given a Gemini message with type "gemini"
    When I export to unified format
    Then the message has role "assistant"

  Scenario: Split Gemini tool results
    Given a Gemini message with embedded tool results
    When I export to unified format
    Then tool results appear in separate user messages
    And synthetic messages have metadata.synthetic: true
```

### Category 6: Feature-Specific Parsing

Tests for agent-specific features.

**Specs:** `agents/features/*.md`

#### 6a: Compaction

| Agent | Test Areas |
|-------|------------|
| Claude | `compact_boundary` system messages, `logicalParentUuid` |
| Codex | `type: compacted` records, `payload.message` |
| Gemini | N/A (no compaction) |

#### 6b: Interruptions

| Agent | Test Areas |
|-------|------------|
| Claude | `[Request interrupted by user]` marker |
| Codex | `turn_aborted` event with `reason` |
| Gemini | `type: info` with "Request cancelled." |

#### 6c: Rejections

| Agent | Test Areas |
|-------|------------|
| Claude | `is_error: true` with "doesn't want to proceed" |
| Codex | Infer from missing `function_call_output` |
| Gemini | `status: error` in toolCalls |

#### 6d: Clearing

| Agent | Test Areas |
|-------|------------|
| Claude | Detection via `history.jsonl` (not session file) |
| Codex | Detection via `history.jsonl` |
| Gemini | Detection via `logs.json`, new session ID |

---

## Parameterization Strategy

### Multi-Agent Parameterization

Many tests apply to all three agents with different details.

```python
@pytest.mark.parametrize("agent", ["claude", "codex", "gemini"])
def test_message_parsing(agent, session_factory):
    """Test that each agent's messages are parsed correctly."""
    session = session_factory(agent).with_messages(5).build()
    # ...
```

### Format Variation Matrix

| Dimension | Values | Test Impact |
|-----------|--------|-------------|
| Agent | claude, codex, gemini | Parser selection |
| Home type | local, wsl, windows, remote | Path handling |
| Message count | 0, 1, many | Edge cases |
| Has tool use | yes, no | Tool parsing |
| Has compaction | yes, no | Boundary handling |
| Has interruption | yes, no | Event detection |
| Has fork | yes, no (Claude only) | Graph handling |

### Combinatorial Testing

For critical paths, test key combinations:

```python
@pytest.mark.parametrize("agent,home_type", [
    ("claude", "local"),
    ("claude", "wsl"),
    ("codex", "local"),
    ("codex", "remote"),
    ("gemini", "local"),
])
def test_export_across_environments(agent, home_type):
    """Test export works for agent+home combinations."""
```

### Parameterized CLI Tests

```python
EXPORT_OPTIONS = [
    ([], "default"),
    (["--minimal"], "minimal"),
    (["--split", "50"], "split"),
    (["--flat"], "flat"),
    (["--json"], "json"),
]

@pytest.mark.parametrize("flags,description", EXPORT_OPTIONS)
def test_export_options(cli_runner, flags, description):
    """Test each export option produces expected output."""
```

---

## Test Data Generation

### Synthetic Message Templates

**User Messages:**
```python
USER_MESSAGES = [
    "Help me fix this bug",
    "Can you add error handling?",
    "Run the tests",
    "Explain what this code does",
]
```

**Tool Use Patterns:**
```python
TOOL_PATTERNS = {
    "read_file": {"file_path": "/path/to/file.py"},
    "edit_file": {"file_path": "/path/to/file.py", "old_string": "...", "new_string": "..."},
    "bash": {"command": "ls -la"},
    "grep": {"pattern": "TODO", "path": "."},
}
```

### Timestamp Generation

```python
def generate_session_timestamps(message_count: int,
                                start: datetime = None,
                                gaps: list[int] = None) -> list[datetime]:
    """Generate realistic message timestamps.

    Args:
        message_count: Number of messages
        start: Session start time (default: now)
        gaps: Custom gap durations in seconds (for testing work periods)
    """
```

### Edge Case Generators

| Edge Case | Generator |
|-----------|-----------|
| Empty session | `empty_session()` |
| Single message | `single_message_session()` |
| Very long session | `large_session(messages=10000)` |
| Unicode content | `unicode_session()` |
| Binary in tool result | `binary_output_session()` |
| Timestamp anomalies | `out_of_order_timestamps()` |

---

## Open Questions

### 1. Home Directory Injection

**Question:** How should tests inject the test home path?

**Decision: Option A - Environment Variables**

The codebase already supports per-agent environment variables:

| Agent | Environment Variable |
|-------|---------------------|
| Claude Code | `CLAUDE_PROJECTS_DIR` |
| Codex CLI | `CODEX_SESSIONS_DIR` |
| Gemini CLI | `GEMINI_SESSIONS_DIR` |

**Test fixture approach:**
```python
@pytest.fixture
def test_home(tmp_path):
    """Create isolated test home with all agent directories."""
    claude_dir = tmp_path / ".claude" / "projects"
    codex_dir = tmp_path / ".codex" / "sessions"
    gemini_dir = tmp_path / ".gemini" / "tmp"

    claude_dir.mkdir(parents=True)
    codex_dir.mkdir(parents=True)
    gemini_dir.mkdir(parents=True)

    with patch.dict(os.environ, {
        "CLAUDE_PROJECTS_DIR": str(claude_dir),
        "CODEX_SESSIONS_DIR": str(codex_dir),
        "GEMINI_SESSIONS_DIR": str(gemini_dir),
    }):
        yield tmp_path
```

### 2. Cross-Environment Testing

**Question:** How do we test WSL/Windows path handling on Linux CI?

**Decision: Multi-Environment CI with Environment-Specific Tests**

Available environments:
- **Windows** (native)
- **WSL** (Ubuntu on Windows)
- **Ubuntu VM** (native Linux)

**Approach:**
- Create environment-specific test directories: `tests/env/windows/`, `tests/env/wsl/`, `tests/env/linux/`
- Shared fixtures in `tests/env/conftest.py`
- Platform detection to skip irrelevant tests
- CI runs on all three environments

**Directory structure:**
```
tests/
├── env/
│   ├── conftest.py          # Shared env fixtures, platform detection
│   ├── windows/
│   │   ├── test_unc_paths.py
│   │   └── test_wsl_access.py
│   ├── wsl/
│   │   ├── test_mnt_paths.py
│   │   └── test_windows_access.py
│   └── linux/
│       └── test_posix_paths.py
├── agents/                   # Cross-platform agent tests
├── cli/                      # Cross-platform CLI tests
└── conftest.py
```

**Platform skip decorator:**
```python
# tests/env/conftest.py
import platform
import pytest

def get_platform():
    if platform.system() == "Windows":
        return "windows"
    elif "microsoft" in platform.uname().release.lower():
        return "wsl"
    return "linux"

CURRENT_PLATFORM = get_platform()

skip_unless_windows = pytest.mark.skipif(
    CURRENT_PLATFORM != "windows", reason="Windows-only test")
skip_unless_wsl = pytest.mark.skipif(
    CURRENT_PLATFORM != "wsl", reason="WSL-only test")
skip_unless_linux = pytest.mark.skipif(
    CURRENT_PLATFORM != "linux", reason="Linux-only test")
```

### 3. Database Testing

**Question:** Should stats tests use real SQLite or in-memory only?

**Decision: Option B - Temp File for Realistic I/O**

```python
@pytest.fixture
def metrics_db(tmp_path):
    """Create isolated metrics database."""
    db_path = tmp_path / "metrics.db"
    yield db_path
    # Cleanup handled by tmp_path
```

**Rationale:**
- Catches I/O bugs that in-memory would miss
- `tmp_path` provides isolation for parallel tests
- Realistic behavior matches production

### 4. Fixture File Management

**Question:** How should synthetic JSONL files be managed?

**Decision: Option D - Hybrid Approach**

| Fixture Type | Storage | Use Case |
|--------------|---------|----------|
| Static | `tests/fixtures/` in repo | Simple parsing tests, edge cases |
| Dynamic | Generated per test | Complex scenarios, parameterized tests |

**Static fixtures:**
```
tests/fixtures/
├── claude/
│   ├── minimal_session.jsonl      # 2 messages
│   ├── with_tool_use.jsonl        # Tool use + result
│   ├── with_interruption.jsonl    # Interruption marker
│   └── with_compaction.jsonl      # Compaction boundary
├── codex/
│   └── ...
└── gemini/
    └── ...
```

**Dynamic generation for:**
- Parameterized message counts
- Timestamp variations
- Multi-session workspaces
- Random content for fuzz testing

### 5. CLI Testing Approach

**Question:** Test CLI via subprocess or programmatically?

**Decision: Option C - Both Approaches**

| Test Type | Method | Rationale |
|-----------|--------|-----------|
| Unit tests | CliRunner | Fast, easy assertions, captures output |
| E2E tests | subprocess | Tests real entry point, actual process |

```python
# Unit test with CliRunner
def test_ws_list_output(cli_runner, test_home):
    result = cli_runner.invoke(cli, ["ws", "list"])
    assert result.exit_code == 0
    assert "my-project" in result.output

# E2E test with subprocess
def test_cli_entrypoint(test_home):
    result = subprocess.run(
        ["agent-history", "ws", "list"],
        capture_output=True, text=True
    )
    assert result.returncode == 0
```

### 6. Network Mocking Scope

**Question:** How much network code should be mocked vs tested?

**Decision: Hybrid - Mocks for Unit Tests, Docker SSH for Integration**

Unit tests use mocks; integration tests use real Docker SSH containers.

| Component | Mock Strategy |
|-----------|---------------|
| SSH connections | `unittest.mock.patch` on SSH client |
| Web API calls | `responses` library or `unittest.mock` |
| Remote file access | Synthetic local files |

**Rationale:**
- Phase 1 focuses on core parsing/export logic
- Network tests add complexity and flakiness
- Can add integration tests in phase 2

```python
@pytest.fixture
def mock_ssh():
    """Mock SSH client for remote tests."""
    with patch("paramiko.SSHClient") as mock:
        mock.return_value.exec_command.return_value = (
            None,  # stdin
            io.StringIO("mock output"),  # stdout
            io.StringIO(""),  # stderr
        )
        yield mock
```

---

## Docker SSH Integration Tests

Real SSH testing using Docker containers on Ubuntu VM.

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                     Ubuntu VM (test runner)                  │
│  ┌─────────────────┐           ┌─────────────────────────┐   │
│  │   test-runner   │    SSH    │      remote-sim         │   │
│  │   container     │ ────────▶ │      container          │   │
│  │                 │           │                         │   │
│  │  - pytest       │           │  - sshd                 │   │
│  │  - agent-history│           │  - .claude/projects/    │   │
│  │                 │           │  - .codex/sessions/     │   │
│  └─────────────────┘           │  - .gemini/tmp/         │   │
│                                └─────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

### Container Definitions

**docker-compose.test.yml:**
```yaml
version: '3.8'
services:
  test-runner:
    build:
      context: .
      dockerfile: tests/docker/Dockerfile.runner
    volumes:
      - .:/app
      - test-results:/app/test-results
    depends_on:
      - remote-sim
    networks:
      - test-network

  remote-sim:
    build:
      context: .
      dockerfile: tests/docker/Dockerfile.remote
    volumes:
      - ./tests/fixtures/remote:/home/testuser
    networks:
      - test-network
    expose:
      - "22"

networks:
  test-network:
    driver: bridge

volumes:
  test-results:
```

**Dockerfile.remote:**
```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y openssh-server
RUN useradd -m -s /bin/bash testuser
RUN echo "testuser:testpass" | chpasswd
RUN mkdir /var/run/sshd

# Pre-populate with synthetic session fixtures
COPY tests/fixtures/remote/.claude /home/testuser/.claude
COPY tests/fixtures/remote/.codex /home/testuser/.codex
COPY tests/fixtures/remote/.gemini /home/testuser/.gemini
RUN chown -R testuser:testuser /home/testuser

EXPOSE 22
CMD ["/usr/sbin/sshd", "-D"]
```

### SSH Test Fixtures

```
tests/fixtures/remote/
├── .claude/projects/
│   └── -home-testuser-remote-project/
│       └── session-remote-1.jsonl    # 5 messages
├── .codex/sessions/2025/01/03/
│   └── rollout-remote-1.jsonl        # 3 messages
└── .gemini/tmp/<hash>/chats/
    └── session-remote-1.json         # 4 messages
```

### Test Categories

#### Connection Tests

```python
@pytest.mark.docker
@pytest.mark.ssh
class TestSSHConnection:

    def test_connect_success(self, remote_sim):
        """Verify SSH connection to remote-sim container."""
        result = run_cli(["-r", "testuser@remote-sim", "ws", "list"])
        assert result.exit_code == 0

    def test_connect_wrong_password(self, remote_sim):
        """Verify auth failure handling."""
        result = run_cli(["-r", "wronguser@remote-sim", "ws", "list"])
        assert result.exit_code != 0
        assert "Authentication failed" in result.stderr

    def test_connect_timeout(self, remote_sim_slow):
        """Verify timeout handling."""
        result = run_cli(["-r", "testuser@remote-sim", "--timeout", "1", "ws", "list"])
        assert "timeout" in result.stderr.lower()

    def test_connect_host_unreachable(self):
        """Verify unreachable host handling."""
        result = run_cli(["-r", "testuser@nonexistent-host", "ws", "list"])
        assert result.exit_code != 0
```

#### Remote Operations Tests

```python
@pytest.mark.docker
@pytest.mark.ssh
class TestRemoteOperations:

    def test_ws_list_remote(self, remote_sim):
        """List workspaces on remote host."""
        result = run_cli(["-r", "testuser@remote-sim", "ws", "list"])
        assert "remote-project" in result.output

    def test_session_list_remote(self, remote_sim):
        """List sessions on remote host."""
        result = run_cli(["-r", "testuser@remote-sim", "session", "list", "--aw"])
        assert result.exit_code == 0
        # Verify expected session count from fixtures

    def test_session_export_remote(self, remote_sim, tmp_path):
        """Export session from remote to local."""
        result = run_cli([
            "-r", "testuser@remote-sim",
            "session", "export",
            "--output", str(tmp_path)
        ])
        assert result.exit_code == 0
        assert (tmp_path / "remote-project").exists()

    def test_session_stats_remote(self, remote_sim):
        """Get stats from remote sessions."""
        result = run_cli(["-r", "testuser@remote-sim", "session", "stats"])
        assert result.exit_code == 0
        # Validate against known fixture values
        assert "sessions: 3" in result.output  # 1 claude + 1 codex + 1 gemini
```

#### Multi-Home Tests (Local + Remote)

```python
@pytest.mark.docker
@pytest.mark.ssh
class TestMultiHome:

    def test_all_homes_includes_remote(self, test_home, remote_sim):
        """--ah includes both local and remote."""
        result = run_cli(["--ah", "ws", "list"])
        assert "local-project" in result.output
        assert "remote-project" in result.output

    def test_stats_all_homes(self, test_home, remote_sim):
        """Stats aggregates across local and remote."""
        result = run_cli(["--ah", "--aw", "session", "stats"])
        # Local: 5 sessions, Remote: 3 sessions = 8 total
        assert "sessions: 8" in result.output

    def test_exclude_remote(self, test_home, remote_sim):
        """--no-remote excludes remote homes."""
        result = run_cli(["--ah", "--no-remote", "ws", "list"])
        assert "local-project" in result.output
        assert "remote-project" not in result.output
```

#### Error Handling Tests

```python
@pytest.mark.docker
@pytest.mark.ssh
class TestSSHErrorHandling:

    def test_connection_lost_mid_operation(self, remote_sim_flaky):
        """Handle connection drop during operation."""
        # remote_sim_flaky drops connection after N bytes
        result = run_cli(["-r", "testuser@remote-sim", "session", "export"])
        assert result.exit_code != 0
        assert "connection" in result.stderr.lower()

    def test_remote_path_not_found(self, remote_sim_empty):
        """Handle missing .claude directory on remote."""
        result = run_cli(["-r", "testuser@remote-sim", "ws", "list"])
        assert result.exit_code == 0
        assert "No workspaces found" in result.output

    def test_permission_denied(self, remote_sim_restricted):
        """Handle permission errors on remote files."""
        result = run_cli(["-r", "testuser@remote-sim", "session", "list"])
        assert "Permission denied" in result.stderr or result.exit_code != 0
```

### Pytest Fixtures for Docker

```python
# tests/docker/conftest.py
import pytest
import docker
import time

@pytest.fixture(scope="session")
def docker_client():
    """Docker client for container management."""
    return docker.from_env()

@pytest.fixture(scope="session")
def remote_sim(docker_client):
    """Start remote-sim container for SSH tests."""
    # Start container
    container = docker_client.containers.run(
        "agent-history-remote-sim",
        detach=True,
        network="test-network",
        name="remote-sim",
    )

    # Wait for SSH to be ready
    for _ in range(30):
        try:
            exit_code, _ = container.exec_run("pgrep sshd")
            if exit_code == 0:
                break
        except:
            pass
        time.sleep(0.5)

    yield container

    # Cleanup
    container.stop()
    container.remove()

@pytest.fixture
def remote_sim_empty(docker_client):
    """Remote container with no session files."""
    # Similar but with empty home directory
    ...

@pytest.fixture
def remote_sim_restricted(docker_client):
    """Remote container with restricted permissions."""
    # Similar but with chmod 000 on session files
    ...
```

### Running Docker Tests

```bash
# Build containers
docker-compose -f tests/docker/docker-compose.test.yml build

# Run SSH integration tests only
pytest -m "docker and ssh" tests/

# Run all tests including Docker
pytest tests/

# Skip Docker tests (for local dev without Docker)
pytest -m "not docker" tests/
```

### CI Integration

```yaml
# .github/workflows/test.yml (or equivalent)
jobs:
  integration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker
        uses: docker/setup-buildx-action@v3

      - name: Build test containers
        run: docker-compose -f tests/docker/docker-compose.test.yml build

      - name: Run integration tests
        run: |
          docker-compose -f tests/docker/docker-compose.test.yml up -d remote-sim
          pytest -m "docker" tests/
          docker-compose -f tests/docker/docker-compose.test.yml down
```

---

## Cross-Environment Access Testing (Windows ↔ WSL)

Testing `--wsl` and `--windows` flags for cross-filesystem access.

### Access Patterns

| Running On | Local Home | `--wsl` accesses | `--windows` accesses |
|------------|------------|------------------|----------------------|
| **Windows** | `C:\Users\<user>\` | `\\wsl.localhost\Ubuntu\home\<user>\` | (same as local) |
| **WSL** | `/home/<user>/` | (same as local) | `/mnt/c/Users/<user>/` |
| **Linux** | `/home/<user>/` | Error: "WSL not available" | Error: "Windows not available" |

### Path Translation

| Context | Claude Projects Path |
|---------|---------------------|
| Windows local | `C:\Users\alice\.claude\projects\` |
| Windows → WSL | `\\wsl.localhost\Ubuntu\home\alice\.claude\projects\` |
| WSL local | `/home/alice/.claude/projects/` |
| WSL → Windows | `/mnt/c/Users/alice/.claude/projects/` |

### Environment Variables for Testing

**Proposed scheme - base home overrides:**

```python
# Base home directories (app constructs .claude/, .codex/, .gemini/ under these)
AGENT_HISTORY_HOME          # Local home override
AGENT_HISTORY_HOME_WSL      # WSL home override (used by --wsl)
AGENT_HISTORY_HOME_WINDOWS  # Windows home override (used by --windows)
```

**Application logic:**

```python
def get_home_for_source(source: str) -> Path:
    if source == "local":
        return Path(os.environ.get("AGENT_HISTORY_HOME", Path.home()))
    elif source == "wsl":
        if env := os.environ.get("AGENT_HISTORY_HOME_WSL"):
            return Path(env)
        return get_default_wsl_home()  # \\wsl.localhost\... or /home/...
    elif source == "windows":
        if env := os.environ.get("AGENT_HISTORY_HOME_WINDOWS"):
            return Path(env)
        return get_default_windows_home()  # /mnt/c/Users/... or C:\Users\...
```

**Test fixture injection:**

```python
@pytest.fixture
def cross_env_homes(tmp_path):
    """Create isolated homes for cross-environment testing."""
    local_home = tmp_path / "local"
    wsl_home = tmp_path / "wsl"
    windows_home = tmp_path / "windows"

    # Create agent directories in each
    for home in [local_home, wsl_home, windows_home]:
        (home / ".claude" / "projects").mkdir(parents=True)
        (home / ".codex" / "sessions").mkdir(parents=True)
        (home / ".gemini" / "tmp").mkdir(parents=True)

    with patch.dict(os.environ, {
        "AGENT_HISTORY_HOME": str(local_home),
        "AGENT_HISTORY_HOME_WSL": str(wsl_home),
        "AGENT_HISTORY_HOME_WINDOWS": str(windows_home),
    }):
        yield {
            "local": local_home,
            "wsl": wsl_home,
            "windows": windows_home,
        }
```

### Test Fixture Structure

```
tmp_path/
├── local/
│   ├── .claude/projects/
│   │   └── -home-user-local-project/
│   │       └── session-local.jsonl
│   ├── .codex/sessions/2025/01/
│   │   └── rollout-local.jsonl
│   └── .gemini/tmp/<hash>/
│       └── session-local.json
├── wsl/
│   ├── .claude/projects/
│   │   └── -home-user-wsl-project/
│   │       └── session-wsl.jsonl
│   └── ...
└── windows/
    ├── .claude/projects/
    │   └── C--Users-user-windows-project/   # Windows-style encoding
    │       └── session-windows.jsonl
    └── ...
```

### Platform-Specific Test Matrix

#### Tests That Run on Windows Only

```python
@pytest.mark.windows_only
class TestWindowsToWSL:
    """Tests for Windows accessing WSL homes."""

    def test_wsl_flag_accesses_wsl_home(self, cross_env_homes):
        """--wsl reads from WSL home directory."""
        create_session(cross_env_homes["wsl"], "wsl-project", messages=3)

        result = run_cli(["--wsl", "ws", "list"])
        assert "wsl-project" in result.output
        assert "local-project" not in result.output

    def test_wsl_path_translation(self, cross_env_homes):
        """Verify UNC path handling for WSL access."""
        # When running on Windows, --wsl should use \\wsl.localhost\...
        result = run_cli(["--wsl", "ws", "list", "--debug"])
        assert "\\\\wsl.localhost" in result.debug_output or \
               cross_env_homes["wsl"] in result.debug_output

    def test_wsl_workspace_encoding(self, cross_env_homes):
        """WSL workspaces use Linux-style path encoding."""
        # WSL workspace: -home-user-project (not C--Users-...)
        create_session(cross_env_homes["wsl"], "-home-alice-myproject")
        result = run_cli(["--wsl", "ws", "list"])
        assert "-home-alice-myproject" in result.output

    def test_all_homes_includes_wsl(self, cross_env_homes):
        """--ah includes both local (Windows) and WSL homes."""
        create_session(cross_env_homes["local"], "win-project")
        create_session(cross_env_homes["wsl"], "wsl-project")

        result = run_cli(["--ah", "ws", "list"])
        assert "win-project" in result.output
        assert "wsl-project" in result.output

    def test_wsl_not_installed(self, monkeypatch):
        """Error handling when WSL is not available."""
        monkeypatch.setattr("shutil.which", lambda x: None if x == "wsl" else "/bin/" + x)
        result = run_cli(["--wsl", "ws", "list"])
        assert result.exit_code != 0
        assert "WSL not available" in result.stderr
```

#### Tests That Run on WSL Only

```python
@pytest.mark.wsl_only
class TestWSLToWindows:
    """Tests for WSL accessing Windows homes."""

    def test_windows_flag_accesses_windows_home(self, cross_env_homes):
        """--windows reads from Windows home directory."""
        create_session(cross_env_homes["windows"], "windows-project", messages=3)

        result = run_cli(["--windows", "ws", "list"])
        assert "windows-project" in result.output
        assert "local-project" not in result.output

    def test_windows_path_translation(self, cross_env_homes):
        """Verify /mnt/c/ path handling for Windows access."""
        result = run_cli(["--windows", "ws", "list", "--debug"])
        assert "/mnt/c/" in result.debug_output or \
               cross_env_homes["windows"] in result.debug_output

    def test_windows_workspace_encoding(self, cross_env_homes):
        """Windows workspaces use Windows-style path encoding."""
        # Windows workspace: C--Users-alice-project
        create_session(cross_env_homes["windows"], "C--Users-alice-myproject")
        result = run_cli(["--windows", "ws", "list"])
        assert "C--Users-alice-myproject" in result.output

    def test_all_homes_includes_windows(self, cross_env_homes):
        """--ah includes both local (WSL) and Windows homes."""
        create_session(cross_env_homes["local"], "wsl-project")
        create_session(cross_env_homes["windows"], "win-project")

        result = run_cli(["--ah", "ws", "list"])
        assert "wsl-project" in result.output
        assert "win-project" in result.output

    def test_windows_not_mounted(self, monkeypatch):
        """Error handling when /mnt/c is not available."""
        monkeypatch.setattr("os.path.exists", lambda x: False if "/mnt/c" in x else True)
        result = run_cli(["--windows", "ws", "list"])
        assert result.exit_code != 0
        assert "Windows" in result.stderr and "not available" in result.stderr
```

#### Tests That Run on Linux Only

```python
@pytest.mark.linux_only
class TestLinuxCrossEnvErrors:
    """Tests for Linux where --wsl/--windows should fail."""

    def test_wsl_flag_errors_on_linux(self):
        """--wsl is not available on native Linux."""
        result = run_cli(["--wsl", "ws", "list"])
        assert result.exit_code != 0
        assert "WSL" in result.stderr
        assert "not available" in result.stderr or "only supported" in result.stderr

    def test_windows_flag_errors_on_linux(self):
        """--windows is not available on native Linux."""
        result = run_cli(["--windows", "ws", "list"])
        assert result.exit_code != 0
        assert "Windows" in result.stderr
```

### Cross-Environment Scope Combinations

```python
CROSS_ENV_SCOPE_COMBOS = [
    # Windows-only tests
    ("windows", "current", "local", None),
    ("windows", "current", "wsl", None),        # --wsl
    ("windows", "all", "local", None),
    ("windows", "all", "wsl", None),
    ("windows", "all", "all", None),            # --ah (local + wsl)
    ("windows", "all", "all-no-wsl", None),     # --ah --no-wsl

    # WSL-only tests
    ("wsl", "current", "local", None),
    ("wsl", "current", "windows", None),        # --windows
    ("wsl", "all", "local", None),
    ("wsl", "all", "windows", None),
    ("wsl", "all", "all", None),                # --ah (local + windows)
    ("wsl", "all", "all-no-windows", None),     # --ah --no-windows

    # Stats with cross-env
    ("windows", "all", "all", "model"),         # Stats across win + wsl
    ("wsl", "all", "all", "day"),               # Stats across wsl + windows
]

@pytest.mark.parametrize("platform,ws_scope,home_scope,grouping", CROSS_ENV_SCOPE_COMBOS)
def test_cross_env_scope(platform, ws_scope, home_scope, grouping, cross_env_homes):
    """Test scope combinations across environments."""
    if get_current_platform() != platform:
        pytest.skip(f"Test requires {platform}")
    # ... execute and validate
```

### Path Handling Edge Cases

| Case | Test |
|------|------|
| Spaces in Windows path | `C:\Users\John Doe\.claude\` |
| Unicode in path | `/home/用户/.claude/` |
| Long Windows paths | Paths > 260 chars |
| Symlinks across filesystems | WSL symlink to /mnt/c/ |
| Case sensitivity | Windows case-insensitive, WSL case-sensitive |
| Network drive in Windows | `Z:\` mapped to network |

```python
@pytest.mark.windows_only
def test_windows_path_with_spaces(cross_env_homes):
    """Handle spaces in Windows paths."""
    spaced_home = cross_env_homes["local"].parent / "John Doe Home"
    spaced_home.mkdir()
    # ... create sessions and test

@pytest.mark.wsl_only
def test_case_sensitivity_difference():
    """WSL is case-sensitive, Windows is not."""
    # Create 'Project' and 'project' - should be 2 on WSL, 1 on Windows
    ...
```

### Exclusion Flag Tests

```python
class TestCrossEnvExclusions:

    @pytest.mark.windows_only
    def test_no_wsl_excludes_wsl(self, cross_env_homes):
        """--ah --no-wsl excludes WSL homes on Windows."""
        create_session(cross_env_homes["local"], "win-project")
        create_session(cross_env_homes["wsl"], "wsl-project")

        result = run_cli(["--ah", "--no-wsl", "ws", "list"])
        assert "win-project" in result.output
        assert "wsl-project" not in result.output

    @pytest.mark.wsl_only
    def test_no_windows_excludes_windows(self, cross_env_homes):
        """--ah --no-windows excludes Windows homes on WSL."""
        create_session(cross_env_homes["local"], "wsl-project")
        create_session(cross_env_homes["windows"], "win-project")

        result = run_cli(["--ah", "--no-windows", "ws", "list"])
        assert "wsl-project" in result.output
        assert "win-project" not in result.output
```

### Required Code Changes

For testability, the application needs:

1. **Environment variable support:**
   ```python
   AGENT_HISTORY_HOME_WSL = os.environ.get("AGENT_HISTORY_HOME_WSL")
   AGENT_HISTORY_HOME_WINDOWS = os.environ.get("AGENT_HISTORY_HOME_WINDOWS")
   ```

2. **Platform detection function:**
   ```python
   def get_platform() -> Literal["windows", "wsl", "linux"]:
       if sys.platform == "win32":
           return "windows"
       elif "microsoft" in platform.uname().release.lower():
           return "wsl"
       return "linux"
   ```

3. **Cross-env availability checks:**
   ```python
   def is_wsl_available() -> bool:
       if get_platform() == "windows":
           return shutil.which("wsl") is not None
       elif get_platform() == "wsl":
           return True  # Already on WSL
       return False

   def is_windows_available() -> bool:
       if get_platform() == "wsl":
           return os.path.exists("/mnt/c/Users")
       elif get_platform() == "windows":
           return True  # Already on Windows
       return False
   ```

---

## Next Steps

1. **Validate injection approach** - Determine how to redirect home directory
2. **Create fixture library** - Build session builders for each agent
3. **Set up pytest infrastructure** - Configure marks, fixtures, conftest
4. **Write first test suite** - Start with parser tests (most fundamental)
5. **Add CLI tests** - Cover core commands
6. **Add edge case coverage** - Error handling, malformed input
7. **CI setup** - Multi-platform runners if needed

---

## Appendix: Spec-to-Test Mapping

| Spec File | Primary Test Categories |
|-----------|------------------------|
| `agent-history-spec.md` | Discovery, Scope, Operations |
| `cli-spec.md` | CLI Commands, Output Format |
| `claude-code-format.md` | Claude Parsing |
| `codex-cli-format.md` | Codex Parsing |
| `gemini-cli-format.md` | Gemini Parsing |
| `unified-json-schema.md` | Export Normalization |
| `compaction.md` | Compaction Detection |
| `clearing.md` | Clear Event Detection |
| `interruptions.md` | Interruption Detection |
| `rejections.md` | Rejection Detection |
