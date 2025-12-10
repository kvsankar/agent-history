# Plan: Add Codex CLI Support to claude-history

## Overview

Extend `claude-history` to support OpenAI's Codex CLI conversations alongside Claude Code, creating a unified tool for browsing and exporting AI coding assistant history.

## Key Design Decisions (Confirmed)

### 1. Naming ✓
- **Rename to `agent-history`** - Generic name supporting multiple agents
- Keep backward compatibility: `claude-history` as symlink

### 2. Architecture ✓
- **Single file maintained** - No module splitting
- **Function-based backends** with dispatch dict (not classes)
- **Prefix existing functions**: `claude_*` for Claude-specific code
- **Add `codex_*` functions** for Codex-specific code
- **Shared functions** remain unprefixed (markdown generation, stats, etc.)

### 3. Agent Detection ✓
- `--agent auto|claude|codex` flag (default: `auto`)
- Auto-detect by checking which home directories exist:
  - `~/.claude/projects/` → Claude
  - `~/.codex/sessions/` → Codex

### 4. Display Mode ✓
- **Unified list** - Merge both agents' sessions, add `AGENT` column to output

### 5. Codex Organization ✓
- **Group by cwd** - Extract workspace from session's `cwd` field, group like Claude

## Files to Modify

| File | Purpose |
|------|---------|
| `claude-history` | Main script (rename to `agent-history`) |
| `tests/unit/test_claude_history.py` | Unit tests |
| `tests/integration/test_e2e_cli.py` | Integration tests |
| `CLAUDE.md` | Project documentation |
| `README.md` | User documentation |

## Test Infrastructure

**Test Command:** `source .venv/bin/activate && python -m pytest tests/ -v`
**Current Test Count:** 577 tests (560 unit + 17 integration)

---

## Test Mirroring Strategy

Every Claude-specific test class must have a corresponding Codex mirror. This ensures feature parity.

### Claude → Codex Test Class Mapping

| Claude Test Class | Codex Mirror | Phase |
|-------------------|--------------|-------|
| `TestContentExtraction` | `TestCodexContentExtraction` | 2 |
| `TestJSONLReading` | `TestCodexJSONLReading` | 2 |
| `TestRealJSONLPatterns` | `TestCodexRealJSONLPatterns` | 2 |
| `TestWorkspaceSessions` | `TestCodexSessionScanning` | 3 |
| `TestMarkdownGeneration` | `TestCodexMarkdownGeneration` | 2 |
| `TestMetricsDatabase` (sync) | `TestCodexMetricsSync` | 5 |

### Shared Test Classes (No Mirroring Needed)

These test shared functionality that works for both agents:
- `TestDateParsing` - Date handling (shared)
- `TestPathNormalization` - Path encoding (shared)
- `TestAliasStorage` - Alias persistence (shared)
- `TestConfigStorage` - Config persistence (shared)
- `TestSecurityValidation` - Input validation (shared)
- `TestBarBuilder` - Stats display (shared)

### New Codex-Only Test Classes

| Test Class | Purpose | Phase |
|------------|---------|-------|
| `TestCodexConstants` | Agent constants, home dir | 1 |
| `TestCodexTimestamp` | Timestamp extraction | 2 |
| `TestCodexWorkspaceExtraction` | cwd → workspace encoding | 3 |
| `TestBackendDispatch` | Agent selection logic | 4 |
| `TestUnifiedSessions` | Multi-agent session merging | 4 |
| `TestCLIAgentFlag` | --agent flag parsing | 6 |
| `TestOutputFormatting` | AGENT column in output | 7 |

### Test Fixture Mapping

| Claude Fixture | Codex Mirror | Purpose |
|----------------|--------------|---------|
| `sample_jsonl_content` | `sample_codex_jsonl_content` | Sample JSONL data |
| `temp_projects_dir` | `temp_codex_sessions_dir` | Temp directory structure |
| `temp_session_file` | `temp_codex_session_file` | Single session file |

---

## Phase 1: Constants and Agent Detection

### 1.1 Code Changes (`claude-history`)
Add near top of file (after existing constants):
```python
# Agent backend identifiers
AGENT_CLAUDE = "claude"
AGENT_CODEX = "codex"

# Codex home directory
CODEX_HOME_DIR = Path.home() / ".codex" / "sessions"

def codex_get_home_dir() -> Path:
    """Get Codex sessions directory (~/.codex/sessions/)."""
    return CODEX_HOME_DIR

def detect_agent_from_path(path: Path) -> str:
    """Detect agent type from file path."""
    path_str = str(path)
    if "/.codex/" in path_str or "\\.codex\\" in path_str:
        return AGENT_CODEX
    return AGENT_CLAUDE
```

### 1.2 Test Changes (`tests/unit/test_claude_history.py`)
Add new test class:
```python
class TestCodexConstants:
    """Tests for Codex-related constants and detection."""

    def test_agent_constants_defined(self):
        assert ch.AGENT_CLAUDE == "claude"
        assert ch.AGENT_CODEX == "codex"

    def test_codex_home_dir_default(self):
        result = ch.codex_get_home_dir()
        assert result == Path.home() / ".codex" / "sessions"

    def test_detect_agent_from_claude_path(self):
        path = Path("/home/user/.claude/projects/workspace/session.jsonl")
        assert ch.detect_agent_from_path(path) == "claude"

    def test_detect_agent_from_codex_path(self):
        path = Path("/home/user/.codex/sessions/2025/12/08/rollout.jsonl")
        assert ch.detect_agent_from_path(path) == "codex"

    def test_detect_agent_windows_codex_path(self):
        path = Path("C:\\Users\\test\\.codex\\sessions\\rollout.jsonl")
        assert ch.detect_agent_from_path(path) == "codex"
```

### 1.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** 577 existing + 5 new = 582 tests pass

### 1.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 1.4.1 | `AGENT_CLAUDE` and `AGENT_CODEX` constants exist | ✅ |
| 1.4.2 | `codex_get_home_dir()` returns correct path | ✅ |
| 1.4.3 | `detect_agent_from_path()` correctly identifies Claude paths | ✅ |
| 1.4.4 | `detect_agent_from_path()` correctly identifies Codex paths | ✅ |
| 1.4.5 | All 576 existing tests still pass | ✅ |
| 1.4.6 | All 5 new tests pass | ✅ |

**Phase 1 Complete:** ✅

---

## Phase 2: Codex JSONL Parsing Functions

### 2.1 Code Changes (`claude-history`)
Add Codex parsing section:
```python
# ============================================================================
# CODEX BACKEND - JSONL Parsing
# ============================================================================

def codex_extract_content(payload: dict) -> str:
    """Extract text content from Codex message payload."""
    content = payload.get("content", [])
    if isinstance(content, str):
        return content
    parts = []
    for item in content:
        if item.get("type") in ("input_text", "output_text"):
            parts.append(item.get("text", ""))
    return "\n".join(parts)

def codex_format_function_call(payload: dict) -> str:
    """Format a function_call payload as markdown."""
    name = payload.get("name", "unknown")
    args = payload.get("arguments", "{}")
    call_id = payload.get("call_id", "")
    return f"**[Tool: {name}]**\nCall ID: `{call_id}`\n```json\n{args}\n```"

def codex_format_function_result(payload: dict) -> str:
    """Format a function_call_output payload as markdown."""
    call_id = payload.get("call_id", "")
    output = payload.get("output", "")
    return f"**[Tool Result]**\nCall ID: `{call_id}`\n```\n{output}\n```"

def codex_read_jsonl_messages(jsonl_file: Path) -> list:
    """Read messages from Codex rollout JSONL file."""
    messages = []
    session_meta = None

    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                entry_type = entry.get("type")
                timestamp = entry.get("timestamp", "")
                payload = entry.get("payload", {})

                if entry_type == "session_meta":
                    session_meta = payload
                elif entry_type == "response_item":
                    payload_type = payload.get("type")
                    if payload_type == "message":
                        messages.append({
                            "role": payload.get("role"),
                            "content": codex_extract_content(payload),
                            "timestamp": timestamp,
                        })
                    elif payload_type in ("function_call", "custom_tool_call"):
                        messages.append({
                            "role": "assistant",
                            "content": codex_format_function_call(payload),
                            "timestamp": timestamp,
                            "is_tool_call": True,
                        })
                    elif payload_type in ("function_call_output", "custom_tool_call_output"):
                        messages.append({
                            "role": "tool",
                            "content": codex_format_function_result(payload),
                            "timestamp": timestamp,
                            "is_tool_result": True,
                        })
            except json.JSONDecodeError:
                continue

    return messages, session_meta

def codex_get_first_timestamp(jsonl_file: Path) -> str:
    """Get timestamp from Codex session's session_meta line."""
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            first_line = f.readline()
            entry = json.loads(first_line)
            if entry.get("type") == "session_meta":
                return entry.get("timestamp", "")
    except (OSError, json.JSONDecodeError):
        pass
    return None

def codex_parse_jsonl_to_markdown(jsonl_file: Path, minimal: bool = False) -> str:
    """Convert Codex rollout JSONL to markdown format."""
    messages, session_meta = codex_read_jsonl_messages(jsonl_file)
    # ... generate markdown similar to Claude format

def codex_extract_metrics_from_jsonl(jsonl_file: Path) -> dict:
    """Extract metrics from Codex JSONL file for stats database.

    Mirror of extract_metrics_from_jsonl() for Codex format.
    """
    messages, session_meta = codex_read_jsonl_messages(jsonl_file)

    metrics = {
        "session": {
            "id": session_meta.get("id") if session_meta else None,
            "cwd": session_meta.get("cwd") if session_meta else None,
            "cli_version": session_meta.get("cli_version") if session_meta else None,
            "model": None,  # Extract from turn_context
        },
        "messages": [],
        "tool_uses": [],
    }

    # Extract from turn_context for model info
    with open(jsonl_file, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
                if entry.get("type") == "turn_context":
                    metrics["session"]["model"] = entry.get("payload", {}).get("model")
                    break
            except json.JSONDecodeError:
                continue

    for msg in messages:
        if msg.get("is_tool_call"):
            metrics["tool_uses"].append({
                "name": "function_call",  # Parse from content
                "timestamp": msg.get("timestamp"),
            })
        else:
            metrics["messages"].append({
                "role": msg.get("role"),
                "timestamp": msg.get("timestamp"),
            })

    return metrics
```

### 2.2 Test Changes (`tests/unit/test_claude_history.py`)
Add test fixture and classes:
```python
@pytest.fixture
def sample_codex_jsonl_content():
    """Sample Codex rollout JSONL for testing."""
    return [
        {
            "timestamp": "2025-12-08T00:37:46.102Z",
            "type": "session_meta",
            "payload": {
                "id": "test-session-id",
                "cwd": "/home/user/project",
                "cli_version": "0.65.0",
                "source": "cli",
            }
        },
        {
            "timestamp": "2025-12-08T00:39:54.852Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "Hello Codex"}]
            }
        },
        {
            "timestamp": "2025-12-08T00:39:59.538Z",
            "type": "response_item",
            "payload": {
                "type": "function_call",
                "name": "shell_command",
                "arguments": '{"command": "pwd"}',
                "call_id": "call_123"
            }
        },
        {
            "timestamp": "2025-12-08T00:40:00.000Z",
            "type": "response_item",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_123",
                "output": "/home/user/project"
            }
        },
        {
            "timestamp": "2025-12-08T00:40:05.000Z",
            "type": "response_item",
            "payload": {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "You are in /home/user/project"}]
            }
        },
    ]

@pytest.fixture
def temp_codex_session_file(sample_codex_jsonl_content):
    """Create a temporary Codex session file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        session_dir = Path(tmpdir) / ".codex" / "sessions" / "2025" / "12" / "08"
        session_dir.mkdir(parents=True)
        session_file = session_dir / "rollout-2025-12-08T00-37-46-test.jsonl"
        with open(session_file, "w", encoding="utf-8") as f:
            for entry in sample_codex_jsonl_content:
                f.write(json.dumps(entry) + "\n")
        yield session_file


class TestCodexContentExtraction:
    """Tests for codex_extract_content."""

    def test_extract_input_text(self):
        payload = {"content": [{"type": "input_text", "text": "Hello"}]}
        assert ch.codex_extract_content(payload) == "Hello"

    def test_extract_output_text(self):
        payload = {"content": [{"type": "output_text", "text": "Response"}]}
        assert ch.codex_extract_content(payload) == "Response"

    def test_extract_multiple_parts(self):
        payload = {"content": [
            {"type": "input_text", "text": "Part 1"},
            {"type": "input_text", "text": "Part 2"}
        ]}
        assert ch.codex_extract_content(payload) == "Part 1\nPart 2"

    def test_extract_string_content(self):
        payload = {"content": "Simple string"}
        assert ch.codex_extract_content(payload) == "Simple string"


class TestCodexJSONLReading:
    """Tests for codex_read_jsonl_messages."""

    def test_read_session_meta(self, temp_codex_session_file):
        messages, meta = ch.codex_read_jsonl_messages(temp_codex_session_file)
        assert meta["id"] == "test-session-id"
        assert meta["cwd"] == "/home/user/project"

    def test_read_user_messages(self, temp_codex_session_file):
        messages, _ = ch.codex_read_jsonl_messages(temp_codex_session_file)
        user_msgs = [m for m in messages if m["role"] == "user"]
        assert len(user_msgs) == 1
        assert "Hello Codex" in user_msgs[0]["content"]

    def test_read_assistant_messages(self, temp_codex_session_file):
        messages, _ = ch.codex_read_jsonl_messages(temp_codex_session_file)
        asst_msgs = [m for m in messages if m["role"] == "assistant" and not m.get("is_tool_call")]
        assert len(asst_msgs) == 1
        assert "You are in" in asst_msgs[0]["content"]

    def test_read_function_calls(self, temp_codex_session_file):
        messages, _ = ch.codex_read_jsonl_messages(temp_codex_session_file)
        tool_calls = [m for m in messages if m.get("is_tool_call")]
        assert len(tool_calls) == 1
        assert "shell_command" in tool_calls[0]["content"]

    def test_read_handles_empty_file(self, tmp_path):
        empty_file = tmp_path / "empty.jsonl"
        empty_file.touch()
        messages, meta = ch.codex_read_jsonl_messages(empty_file)
        assert messages == []
        assert meta is None


class TestCodexTimestamp:
    """Tests for codex_get_first_timestamp."""

    def test_get_first_timestamp_from_session_meta(self, temp_codex_session_file):
        ts = ch.codex_get_first_timestamp(temp_codex_session_file)
        assert ts == "2025-12-08T00:37:46.102Z"

    def test_get_first_timestamp_missing_file(self, tmp_path):
        ts = ch.codex_get_first_timestamp(tmp_path / "nonexistent.jsonl")
        assert ts is None


# ============================================================================
# MIRROR: TestRealJSONLPatterns → TestCodexRealJSONLPatterns
# ============================================================================
class TestCodexRealJSONLPatterns:
    """Mirror of TestRealJSONLPatterns for Codex format."""

    def test_read_realistic_conversation(self, temp_codex_session_file):
        """Mirror: test_read_realistic_conversation"""
        messages, meta = ch.codex_read_jsonl_messages(temp_codex_session_file)
        assert len(messages) >= 2  # At least user + assistant
        assert meta is not None

    def test_extract_tool_use_content(self, temp_codex_session_file):
        """Mirror: test_extract_tool_use_content"""
        messages, _ = ch.codex_read_jsonl_messages(temp_codex_session_file)
        tool_calls = [m for m in messages if m.get("is_tool_call")]
        assert len(tool_calls) >= 1
        assert "shell_command" in tool_calls[0]["content"]

    def test_extract_tool_result_content(self, temp_codex_session_file):
        """Mirror: test_extract_tool_result_content"""
        messages, _ = ch.codex_read_jsonl_messages(temp_codex_session_file)
        tool_results = [m for m in messages if m.get("is_tool_result")]
        assert len(tool_results) >= 1
        assert "call_123" in tool_results[0]["content"]

    def test_metrics_extraction_realistic(self, temp_codex_session_file):
        """Mirror: test_metrics_extraction_realistic"""
        metrics = ch.codex_extract_metrics_from_jsonl(temp_codex_session_file)
        assert "session" in metrics
        assert metrics["session"]["cwd"] == "/home/user/project"

    def test_metrics_extraction_tool_uses(self, temp_codex_session_file):
        """Mirror: test_metrics_extraction_tool_uses"""
        metrics = ch.codex_extract_metrics_from_jsonl(temp_codex_session_file)
        assert "tool_uses" in metrics
        assert len(metrics["tool_uses"]) >= 1


# ============================================================================
# MIRROR: TestMarkdownGeneration → TestCodexMarkdownGeneration
# ============================================================================
class TestCodexMarkdownGeneration:
    """Mirror of TestMarkdownGeneration for Codex format."""

    def test_generates_markdown_header(self, temp_codex_session_file):
        """Mirror: test_generates_markdown_header"""
        md = ch.codex_parse_jsonl_to_markdown(temp_codex_session_file)
        assert "# " in md  # Has heading
        assert "Codex" in md or "Conversation" in md

    def test_includes_message_content(self, temp_codex_session_file):
        """Mirror: test_includes_message_content"""
        md = ch.codex_parse_jsonl_to_markdown(temp_codex_session_file)
        assert "Hello Codex" in md
        assert "You are in" in md

    def test_minimal_mode_excludes_metadata(self, temp_codex_session_file):
        """Mirror: test_minimal_mode_excludes_metadata"""
        md_full = ch.codex_parse_jsonl_to_markdown(temp_codex_session_file, minimal=False)
        md_minimal = ch.codex_parse_jsonl_to_markdown(temp_codex_session_file, minimal=True)
        # Minimal should be shorter (less metadata)
        assert len(md_minimal) <= len(md_full)

    def test_includes_tool_calls(self, temp_codex_session_file):
        """Mirror: test_markdown_generation_with_tools"""
        md = ch.codex_parse_jsonl_to_markdown(temp_codex_session_file)
        assert "shell_command" in md
        assert "pwd" in md
```

### 2.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** 582 + ~24 new = ~606 tests pass

### 2.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 2.4.1 | `codex_extract_content()` extracts input_text correctly | ✅ |
| 2.4.2 | `codex_extract_content()` extracts output_text correctly | ✅ |
| 2.4.3 | `codex_format_function_call()` formats tool calls | ✅ |
| 2.4.4 | `codex_format_function_result()` formats tool results | ✅ |
| 2.4.5 | `codex_read_jsonl_messages()` parses session_meta | ✅ |
| 2.4.6 | `codex_read_jsonl_messages()` extracts user messages | ✅ |
| 2.4.7 | `codex_read_jsonl_messages()` extracts assistant messages | ✅ |
| 2.4.8 | `codex_read_jsonl_messages()` extracts function calls | ✅ |
| 2.4.9 | `codex_get_first_timestamp()` returns correct timestamp | ✅ |
| 2.4.10 | **MIRROR:** `TestCodexRealJSONLPatterns` matches `TestRealJSONLPatterns` | ✅ |
| 2.4.11 | **MIRROR:** `TestCodexMarkdownGeneration` matches `TestMarkdownGeneration` | ✅ |
| 2.4.12 | `codex_extract_metrics_from_jsonl()` extracts session metrics | ✅ |
| 2.4.13 | `codex_extract_metrics_from_jsonl()` extracts tool uses | ✅ |
| 2.4.14 | All previous tests still pass (581) | ✅ |
| 2.4.15 | All new tests pass (28 new, 604 total) | ✅ |

**Phase 2 Complete:** ✅

---

## Phase 3: Codex Session Scanning

### 3.1 Code Changes (`claude-history`)
```python
def codex_get_workspace_from_session(jsonl_file: Path) -> str:
    """Extract workspace (cwd) from Codex session's session_meta."""
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            first_line = f.readline()
            entry = json.loads(first_line)
            if entry.get("type") == "session_meta":
                cwd = entry.get("payload", {}).get("cwd", "")
                if cwd:
                    return path_to_encoded_workspace(cwd)
    except (OSError, json.JSONDecodeError):
        pass
    return "unknown"

def codex_scan_sessions(
    pattern: str = "",
    since_date=None,
    until_date=None,
    sessions_dir: Path = None,
    skip_message_count: bool = False,
) -> list:
    """Scan ~/.codex/sessions/YYYY/MM/DD/ for rollout-*.jsonl files."""
    if sessions_dir is None:
        sessions_dir = codex_get_home_dir()

    if not sessions_dir.exists():
        return []

    sessions = []
    # Walk through YYYY/MM/DD structure
    for year_dir in sessions_dir.iterdir():
        if not year_dir.is_dir() or not year_dir.name.isdigit():
            continue
        for month_dir in year_dir.iterdir():
            if not month_dir.is_dir():
                continue
            for day_dir in month_dir.iterdir():
                if not day_dir.is_dir():
                    continue
                for jsonl_file in day_dir.glob("rollout-*.jsonl"):
                    workspace = codex_get_workspace_from_session(jsonl_file)

                    # Pattern filtering
                    if pattern and pattern not in workspace:
                        continue

                    stat = jsonl_file.stat()
                    modified = datetime.fromtimestamp(stat.st_mtime)

                    # Date filtering
                    if since_date and modified.date() < since_date.date():
                        continue
                    if until_date and modified.date() > until_date.date():
                        continue

                    sessions.append({
                        "agent": AGENT_CODEX,
                        "workspace": workspace,
                        "workspace_readable": normalize_workspace_name(workspace, verify_local=False),
                        "file": jsonl_file,
                        "filename": jsonl_file.name,
                        "message_count": 0 if skip_message_count else codex_count_messages(jsonl_file),
                        "modified": modified,
                        "source": "local",
                    })

    return sorted(sessions, key=lambda s: s["modified"], reverse=True)

def codex_count_messages(jsonl_file: Path) -> int:
    """Count user/assistant messages in a Codex session."""
    count = 0
    try:
        with open(jsonl_file, encoding="utf-8") as f:
            for line in f:
                entry = json.loads(line)
                if entry.get("type") == "response_item":
                    payload = entry.get("payload", {})
                    if payload.get("type") == "message":
                        count += 1
    except (OSError, json.JSONDecodeError):
        pass
    return count
```

### 3.2 Test Changes (`tests/unit/test_claude_history.py`)
```python
@pytest.fixture
def temp_codex_sessions_dir(sample_codex_jsonl_content):
    """Create a temporary Codex sessions directory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir) / ".codex" / "sessions"

        # Create session in 2025/12/08
        day1 = base / "2025" / "12" / "08"
        day1.mkdir(parents=True)
        with open(day1 / "rollout-2025-12-08T00-37-46-test1.jsonl", "w") as f:
            for entry in sample_codex_jsonl_content:
                f.write(json.dumps(entry) + "\n")

        # Create session in 2025/12/09 with different workspace
        day2 = base / "2025" / "12" / "09"
        day2.mkdir(parents=True)
        modified_content = sample_codex_jsonl_content.copy()
        modified_content[0] = {
            **modified_content[0],
            "payload": {**modified_content[0]["payload"], "cwd": "/home/user/other-project"}
        }
        with open(day2 / "rollout-2025-12-09T10-00-00-test2.jsonl", "w") as f:
            for entry in modified_content:
                f.write(json.dumps(entry) + "\n")

        yield base


class TestCodexWorkspaceExtraction:
    """Tests for codex_get_workspace_from_session."""

    def test_extract_workspace_from_session_meta(self, temp_codex_session_file):
        ws = ch.codex_get_workspace_from_session(temp_codex_session_file)
        assert ws == "-home-user-project"

    def test_workspace_encoding_from_cwd(self):
        # Test the encoding logic directly
        assert ch.path_to_encoded_workspace("/home/user/project") == "-home-user-project"
        assert ch.path_to_encoded_workspace("/var/www/app") == "-var-www-app"


# ============================================================================
# MIRROR: TestWorkspaceSessions → TestCodexSessionScanning
# ============================================================================
class TestCodexSessionScanning:
    """Mirror of TestWorkspaceSessions for Codex format."""

    def test_scan_finds_sessions(self, temp_codex_sessions_dir):
        """Mirror: test_get_sessions_empty_pattern"""
        sessions = ch.codex_scan_sessions(sessions_dir=temp_codex_sessions_dir)
        assert len(sessions) == 2

    def test_scan_filters_by_pattern(self, temp_codex_sessions_dir):
        """Mirror: test_get_sessions_by_pattern"""
        sessions = ch.codex_scan_sessions(pattern="other-project", sessions_dir=temp_codex_sessions_dir)
        assert len(sessions) == 1
        assert "other-project" in sessions[0]["workspace"]

    def test_scan_no_match(self, temp_codex_sessions_dir):
        """Mirror: test_get_sessions_no_match"""
        sessions = ch.codex_scan_sessions(pattern="nonexistent", sessions_dir=temp_codex_sessions_dir)
        assert len(sessions) == 0

    def test_scan_returns_session_metadata(self, temp_codex_sessions_dir):
        """Mirror: test_sessions_include_file_info"""
        sessions = ch.codex_scan_sessions(sessions_dir=temp_codex_sessions_dir)
        session = sessions[0]
        assert "agent" in session and session["agent"] == "codex"
        assert "workspace" in session
        assert "workspace_readable" in session
        assert "file" in session
        assert "filename" in session
        assert "message_count" in session
        assert "modified" in session
        assert "source" in session

    def test_scan_date_filtering_since(self, temp_codex_sessions_dir):
        """Mirror: date filtering tests"""
        from datetime import datetime
        since = datetime(2025, 12, 9)
        sessions = ch.codex_scan_sessions(sessions_dir=temp_codex_sessions_dir, since_date=since)
        # Should only include sessions from 12/09 onwards
        assert all(s["modified"].date() >= since.date() for s in sessions)

    def test_scan_date_filtering_until(self, temp_codex_sessions_dir):
        """Mirror: date filtering tests"""
        from datetime import datetime
        until = datetime(2025, 12, 8)
        sessions = ch.codex_scan_sessions(sessions_dir=temp_codex_sessions_dir, until_date=until)
        # Should only include sessions up to 12/08
        assert all(s["modified"].date() <= until.date() for s in sessions)

    def test_scan_empty_dir(self, tmp_path):
        empty_dir = tmp_path / ".codex" / "sessions"
        empty_dir.mkdir(parents=True)
        sessions = ch.codex_scan_sessions(sessions_dir=empty_dir)
        assert sessions == []

    def test_scan_nonexistent_dir(self, tmp_path):
        sessions = ch.codex_scan_sessions(sessions_dir=tmp_path / "nonexistent")
        assert sessions == []

    def test_scan_skip_message_count(self, temp_codex_sessions_dir):
        """Test skip_message_count optimization."""
        sessions = ch.codex_scan_sessions(sessions_dir=temp_codex_sessions_dir, skip_message_count=True)
        assert all(s["message_count"] == 0 for s in sessions)
```

### 3.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** ~606 + ~12 new = ~618 tests pass

### 3.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 3.4.1 | `codex_get_workspace_from_session()` extracts cwd from session_meta | ✅ |
| 3.4.2 | `codex_get_workspace_from_session()` encodes cwd as workspace name | ✅ |
| 3.4.3 | `codex_scan_sessions()` finds sessions in YYYY/MM/DD structure | ✅ |
| 3.4.4 | `codex_scan_sessions()` filters by pattern | ✅ |
| 3.4.5 | `codex_scan_sessions()` returns correct session metadata | ✅ |
| 3.4.6 | `codex_scan_sessions()` handles empty directory | ✅ |
| 3.4.7 | `codex_scan_sessions()` handles nonexistent directory | ✅ |
| 3.4.8 | `codex_count_messages()` counts messages correctly | ✅ |
| 3.4.9 | **MIRROR:** `TestCodexSessionScanning` matches `TestWorkspaceSessions` | ✅ |
| 3.4.10 | Date filtering (since/until) works for Codex sessions | ✅ |
| 3.4.11 | All previous tests still pass (604) | ✅ |
| 3.4.12 | All new tests pass (12 new, 616 total) | ✅ |

**Phase 3 Complete:** ✅

---

## Phase 4: Unified Backend Dispatch

### 4.1 Code Changes (`claude-history`)
```python
def get_active_backends(agent: str) -> list:
    """Return list of active backends based on agent flag."""
    if agent == AGENT_CLAUDE:
        return [AGENT_CLAUDE] if get_claude_projects_dir().exists() else []
    elif agent == AGENT_CODEX:
        return [AGENT_CODEX] if codex_get_home_dir().exists() else []
    else:  # auto
        backends = []
        if get_claude_projects_dir().exists():
            backends.append(AGENT_CLAUDE)
        if codex_get_home_dir().exists():
            backends.append(AGENT_CODEX)
        return backends

def get_unified_sessions(
    agent: str = "auto",
    pattern: str = "",
    **kwargs
) -> list:
    """Get sessions from specified agent backend(s)."""
    all_sessions = []
    backends = get_active_backends(agent)

    for backend in backends:
        if backend == AGENT_CLAUDE:
            sessions = get_workspace_sessions(pattern, **kwargs)
            for s in sessions:
                s["agent"] = AGENT_CLAUDE
            all_sessions.extend(sessions)
        elif backend == AGENT_CODEX:
            sessions = codex_scan_sessions(pattern, **kwargs)
            all_sessions.extend(sessions)

    return sorted(all_sessions, key=lambda s: s["modified"], reverse=True)
```

### 4.2 Test Changes (`tests/unit/test_claude_history.py`)
```python
class TestBackendDispatch:
    """Tests for backend selection and dispatch."""

    def test_get_active_backends_explicit_claude(self, temp_projects_dir):
        with patch.object(ch, 'get_claude_projects_dir', return_value=temp_projects_dir):
            backends = ch.get_active_backends("claude")
            assert backends == ["claude"]

    def test_get_active_backends_explicit_codex(self, temp_codex_sessions_dir):
        with patch.object(ch, 'codex_get_home_dir', return_value=temp_codex_sessions_dir):
            backends = ch.get_active_backends("codex")
            assert backends == ["codex"]

    def test_get_active_backends_auto_both_exist(self, temp_projects_dir, temp_codex_sessions_dir):
        with patch.object(ch, 'get_claude_projects_dir', return_value=temp_projects_dir):
            with patch.object(ch, 'codex_get_home_dir', return_value=temp_codex_sessions_dir):
                backends = ch.get_active_backends("auto")
                assert "claude" in backends
                assert "codex" in backends

    def test_get_active_backends_auto_only_claude(self, temp_projects_dir, tmp_path):
        with patch.object(ch, 'get_claude_projects_dir', return_value=temp_projects_dir):
            with patch.object(ch, 'codex_get_home_dir', return_value=tmp_path / "nonexistent"):
                backends = ch.get_active_backends("auto")
                assert backends == ["claude"]


class TestUnifiedSessions:
    """Tests for get_unified_sessions."""

    def test_get_sessions_merges_both_agents(self, temp_projects_dir, temp_codex_sessions_dir):
        with patch.object(ch, 'get_claude_projects_dir', return_value=temp_projects_dir):
            with patch.object(ch, 'codex_get_home_dir', return_value=temp_codex_sessions_dir):
                sessions = ch.get_unified_sessions(agent="auto")
                agents = {s["agent"] for s in sessions}
                assert "claude" in agents
                assert "codex" in agents

    def test_sessions_tagged_with_agent_field(self, temp_projects_dir):
        with patch.object(ch, 'get_claude_projects_dir', return_value=temp_projects_dir):
            sessions = ch.get_unified_sessions(agent="claude")
            for s in sessions:
                assert s["agent"] == "claude"
```

### 4.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** ~618 + ~6 new = ~624 tests pass

### 4.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 4.4.1 | `get_active_backends("claude")` returns `["claude"]` when Claude dir exists | ✅ |
| 4.4.2 | `get_active_backends("codex")` returns `["codex"]` when Codex dir exists | ✅ |
| 4.4.3 | `get_active_backends("auto")` returns both when both dirs exist | ✅ |
| 4.4.4 | `get_active_backends("auto")` returns only existing backends | ✅ |
| 4.4.5 | `get_unified_sessions()` merges sessions from both agents | ✅ |
| 4.4.6 | `get_unified_sessions()` tags sessions with `agent` field | ✅ |
| 4.4.7 | All previous tests still pass (616) | ✅ |
| 4.4.8 | All new tests pass (9 new, 625 total) | ✅ |

**Phase 4 Complete:** ✅

---

## Phase 5: Database Schema Update

### 5.1 Code Changes (`claude-history`)
```python
METRICS_DB_VERSION = 4  # Bump from 3

# In init_metrics_db(), add migration after version 3:
if current_version < 4:
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN agent TEXT DEFAULT 'claude'")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent)")
    except sqlite3.OperationalError:
        pass  # Column already exists

# Update sync_file_to_db() to set agent based on file path
def sync_file_to_db(...):
    ...
    agent = detect_agent_from_path(jsonl_file)
    # Include agent in INSERT/UPDATE
```

### 5.2 Test Changes (`tests/unit/test_claude_history.py`)
```python
class TestMetricsDBMigration:
    """Tests for database schema migrations."""

    def test_new_db_has_agent_column(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = ch.init_metrics_db(db_path)
        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "agent" in columns
        conn.close()

    def test_schema_migration_adds_agent_column(self, tmp_path):
        # Create old schema database
        db_path = tmp_path / "old.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO schema_version VALUES (3)")
        conn.execute("""CREATE TABLE sessions (
            file_path TEXT PRIMARY KEY, workspace TEXT, source TEXT
        )""")
        conn.commit()
        conn.close()

        # Run migration
        conn = ch.init_metrics_db(db_path)
        cursor = conn.execute("PRAGMA table_info(sessions)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "agent" in columns
        conn.close()


# ============================================================================
# MIRROR: TestMetricsDatabase (sync) → TestCodexMetricsSync
# ============================================================================
class TestCodexMetricsSync:
    """Mirror of TestMetricsDatabase sync tests for Codex format."""

    def test_sync_codex_file_to_db(self, tmp_path, temp_codex_session_file):
        """Mirror: test_sync_file_to_db for Codex"""
        db_path = tmp_path / "test.db"
        conn = ch.init_metrics_db(db_path)
        ch.sync_file_to_db(conn, temp_codex_session_file, "local")

        cursor = conn.execute("SELECT agent FROM sessions WHERE file_path = ?",
                              (str(temp_codex_session_file),))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "codex"
        conn.close()

    def test_sync_codex_extracts_workspace(self, tmp_path, temp_codex_session_file):
        """Mirror: test workspace extraction for Codex"""
        db_path = tmp_path / "test.db"
        conn = ch.init_metrics_db(db_path)
        ch.sync_file_to_db(conn, temp_codex_session_file, "local")

        cursor = conn.execute("SELECT workspace FROM sessions WHERE file_path = ?",
                              (str(temp_codex_session_file),))
        result = cursor.fetchone()
        assert result is not None
        assert "home-user-project" in result[0]
        conn.close()

    def test_sync_codex_extracts_metrics(self, tmp_path, temp_codex_session_file):
        """Mirror: test metrics extraction for Codex"""
        db_path = tmp_path / "test.db"
        conn = ch.init_metrics_db(db_path)
        ch.sync_file_to_db(conn, temp_codex_session_file, "local")

        # Check messages were synced
        cursor = conn.execute("SELECT COUNT(*) FROM messages WHERE file_path = ?",
                              (str(temp_codex_session_file),))
        msg_count = cursor.fetchone()[0]
        assert msg_count >= 2  # At least user + assistant

        # Check tool uses were synced
        cursor = conn.execute("SELECT COUNT(*) FROM tool_uses WHERE file_path = ?",
                              (str(temp_codex_session_file),))
        tool_count = cursor.fetchone()[0]
        assert tool_count >= 1  # At least one tool call
        conn.close()

    def test_sync_claude_file_sets_claude_agent(self, tmp_path, temp_session_file):
        """Mirror: verify Claude files still set agent='claude'"""
        db_path = tmp_path / "test.db"
        conn = ch.init_metrics_db(db_path)
        ch.sync_file_to_db(conn, temp_session_file, "local")

        cursor = conn.execute("SELECT agent FROM sessions WHERE file_path = ?",
                              (str(temp_session_file),))
        result = cursor.fetchone()
        assert result is not None
        assert result[0] == "claude"
        conn.close()
```

### 5.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** ~624 + ~6 new = ~630 tests pass

### 5.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 5.4.1 | `METRICS_DB_VERSION` is 4 | ✅ |
| 5.4.2 | New database has `agent` column in sessions table | ✅ |
| 5.4.3 | Migration from v3 adds `agent` column | ✅ |
| 5.4.4 | `agent` column has default value `'claude'` | ✅ |
| 5.4.5 | Index `idx_sessions_agent` is created | ✅ |
| 5.4.6 | `sync_file_to_db()` sets agent based on path | ✅ |
| 5.4.7 | **MIRROR:** `TestCodexMetricsSync` matches `TestMetricsDatabase` sync tests | ✅ |
| 5.4.8 | Codex sessions synced with `agent='codex'` | ✅ |
| 5.4.9 | Claude sessions still synced with `agent='claude'` | ✅ |
| 5.4.10 | All previous tests still pass (625) | ✅ |
| 5.4.11 | All new tests pass (6 new, 631 total) | ✅ |

**Phase 5 Complete:** ✅

---

## Phase 6: CLI `--agent` Flag

### 6.1 Code Changes (`claude-history`)
In `_create_argument_parser()`:
```python
parser.add_argument(
    '--agent', '-a',
    choices=['auto', 'claude', 'codex'],
    default='auto',
    help='Agent backend to use (default: auto-detect)'
)
```
Update dispatch functions to pass `args.agent` through.

### 6.2 Test Changes (`tests/unit/test_claude_history.py`)
```python
class TestCLIAgentFlag:
    """Tests for --agent CLI flag."""

    def test_agent_flag_default_is_auto(self):
        parser = ch._create_argument_parser()
        args = parser.parse_args(["lsw"])
        assert args.agent == "auto"

    def test_agent_flag_accepts_claude(self):
        parser = ch._create_argument_parser()
        args = parser.parse_args(["--agent", "claude", "lsw"])
        assert args.agent == "claude"

    def test_agent_flag_accepts_codex(self):
        parser = ch._create_argument_parser()
        args = parser.parse_args(["-a", "codex", "lsw"])
        assert args.agent == "codex"

    def test_agent_flag_rejects_invalid(self):
        parser = ch._create_argument_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--agent", "invalid", "lsw"])
```

### 6.3 Integration Test Changes (`tests/integration/test_e2e_cli.py`)
```python
def test_e2e_agent_flag_codex_only():
    """Test --agent codex limits to Codex sessions only."""
    result = subprocess.run(
        ["./claude-history", "--agent", "codex", "lsw"],
        capture_output=True, text=True
    )
    # Should not error even if no Codex data exists
    assert result.returncode == 0
```

### 6.4 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** ~630 + ~5 new = ~635 tests pass

### 6.5 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 6.5.1 | `--agent` flag exists in argument parser | ✅ |
| 6.5.2 | `--agent` accepts `auto`, `claude`, `codex` | ✅ |
| 6.5.3 | `--agent` defaults to `auto` | ✅ |
| 6.5.4 | `-a` short form works | ✅ |
| 6.5.5 | Invalid agent value is rejected | ✅ |
| 6.5.6 | `--agent codex` works with `lsw` command | ✅ |
| 6.5.7 | All previous tests still pass (631) | ✅ |
| 6.5.8 | All new tests pass (5 new, 636 total) | ✅ |

**Phase 6 Complete:** ✅

---

## Phase 7: Output Format (AGENT Column)

### 7.1 Code Changes (`claude-history`)
Update `format_session_line()` and `print_sessions_output()`:
```python
def format_session_line(session: dict, source_label: str) -> str:
    agent = session.get("agent", "claude")
    return (
        f"{agent}\t{source_label}\t{session['workspace_readable']}\t{session['filename']}\t"
        f"{session['message_count']}\t{session['modified'].strftime('%Y-%m-%d')}"
    )

def print_sessions_output(sessions: list, source_label: str, workspaces_only: bool):
    if workspaces_only:
        # ... existing logic
    else:
        print("AGENT\tHOME\tWORKSPACE\tFILE\tMESSAGES\tDATE")
        for session in sessions:
            print(format_session_line(session, source_label))
```

### 7.2 Test Changes
```python
class TestOutputFormatting:
    """Tests for output formatting with agent column."""

    def test_session_line_includes_agent(self):
        session = {
            "agent": "codex",
            "workspace_readable": "/home/user/project",
            "filename": "rollout.jsonl",
            "message_count": 10,
            "modified": datetime(2025, 12, 8),
        }
        line = ch.format_session_line(session, "Local")
        assert line.startswith("codex\t")

    def test_header_includes_agent_column(self, capsys):
        ch.print_sessions_output([], "Local", workspaces_only=False)
        captured = capsys.readouterr()
        assert "AGENT" in captured.out
```

### 7.3 Run Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** ~635 + ~2 new = ~637 tests pass

### 7.4 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 7.4.1 | `format_session_line()` includes agent field | ⬜ |
| 7.4.2 | Session line starts with agent name | ⬜ |
| 7.4.3 | `print_sessions_output()` header includes `AGENT` column | ⬜ |
| 7.4.4 | Output columns are in correct order | ⬜ |
| 7.4.5 | All previous tests still pass (~635) | ⬜ |
| 7.4.6 | All new tests pass (~2) | ⬜ |

**Phase 7 Complete:** ⬜

---

## Phase 8: Rename to `agent-history`

### 8.1 Code Changes
```bash
# Rename file
mv claude-history agent-history

# Create symlink for backward compatibility
ln -s agent-history claude-history
```

Update in `agent-history`:
- Change `__doc__` string
- Update help text references
- Change `DEFAULT_CLI_NAME = "agent-history"`

### 8.2 Test Changes (`tests/unit/test_claude_history.py`)
Update import to handle both names:
```python
# Try both names for import
module_path = None
for name in ["agent-history", "claude-history"]:
    for base in root_search:
        candidate = base / name
        if candidate.exists():
            module_path = candidate
            break
    if module_path:
        break
```

### 8.3 Documentation Updates
- Update `CLAUDE.md` with new name and Codex support
- Update `README.md` with new name and examples

### 8.4 Run Final Tests
```bash
source .venv/bin/activate && python -m pytest tests/ -v
```
**Expected:** All ~637+ tests pass

### 8.5 Checkpoints

| # | Checkpoint | Status |
|---|------------|--------|
| 8.5.1 | File renamed to `agent-history` | ⬜ |
| 8.5.2 | Symlink `claude-history` → `agent-history` exists | ⬜ |
| 8.5.3 | `__doc__` string updated | ⬜ |
| 8.5.4 | Help text references `agent-history` | ⬜ |
| 8.5.5 | `DEFAULT_CLI_NAME` is `"agent-history"` | ⬜ |
| 8.5.6 | Test imports work with both names | ⬜ |
| 8.5.7 | `CLAUDE.md` updated with Codex support docs | ⬜ |
| 8.5.8 | `README.md` updated with new name and examples | ⬜ |
| 8.5.9 | All 637+ tests pass | ⬜ |
| 8.5.10 | CLI works via both `./agent-history` and `./claude-history` | ⬜ |

**Phase 8 Complete:** ⬜

---

## Implementation Complete Checklist

| Phase | Status | Tests | Mirror Tests |
|-------|--------|-------|--------------|
| Phase 1: Constants and Agent Detection | ⬜ | 577 → 582 | - |
| Phase 2: Codex JSONL Parsing | ⬜ | 582 → 606 | `TestCodexRealJSONLPatterns`, `TestCodexMarkdownGeneration` |
| Phase 3: Codex Session Scanning | ⬜ | 606 → 618 | `TestCodexSessionScanning` |
| Phase 4: Unified Backend Dispatch | ⬜ | 618 → 624 | - |
| Phase 5: Database Schema Update | ⬜ | 624 → 630 | `TestCodexMetricsSync` |
| Phase 6: CLI --agent Flag | ⬜ | 630 → 635 | - |
| Phase 7: Output Format (AGENT Column) | ⬜ | 635 → 637 | - |
| Phase 8: Rename to agent-history | ⬜ | 637+ | - |

**Total New Tests:** ~60 (including all mirror tests)
**All Phases Complete:** ⬜
