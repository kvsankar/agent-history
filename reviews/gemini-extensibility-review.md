# Gemini Extensibility Review

## Context
Self-review to assess whether source code and tests are ready for adding a third agent (e.g., Gemini) alongside Claude and Codex.

## Source Code Gaps

### 1. Hardcoded Agent Constants (agent-history:41-42)
```python
AGENT_CLAUDE = "claude"
AGENT_CODEX = "codex"
```
**Issue:** No `AGENT_GEMINI` constant. Adding a new agent requires modifying this section.

**Recommendation:** Consider using an enum or registry pattern:
```python
class Agent:
    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    ALL = [CLAUDE, CODEX, GEMINI]
```

### 2. Path Detection Logic (agent-history:89-101)
```python
def detect_agent_from_path(path: Path) -> str:
    path_str = str(path)
    if "/.codex/" in path_str or "\\.codex\\" in path_str:
        return AGENT_CODEX
    return AGENT_CLAUDE  # <-- Falls through to Claude
```
**Issue:** Binary detection - only checks for Codex, defaults to Claude. Gemini paths would incorrectly be detected as Claude.

**Recommendation:** Make detection extensible:
```python
AGENT_PATH_PATTERNS = {
    AGENT_CODEX: ["/.codex/", "\\.codex\\"],
    AGENT_GEMINI: ["/.gemini/", "\\.gemini\\"],
}
def detect_agent_from_path(path: Path) -> str:
    path_str = str(path)
    for agent, patterns in AGENT_PATH_PATTERNS.items():
        if any(p in path_str for p in patterns):
            return agent
    return AGENT_CLAUDE  # Default
```

### 3. CLI Argument Choices (agent-history:8294)
```python
choices=["auto", "claude", "codex"],
```
**Issue:** Hardcoded list. Adding Gemini requires manual update.

**Recommendation:** Use a constant or derive from agent registry.

### 4. Backend Selection Logic (agent-history:1743-1755)
```python
if agent == AGENT_CLAUDE:
    return [AGENT_CLAUDE] if projects_dir.exists() else []
elif agent == AGENT_CODEX:
    return [AGENT_CODEX] if codex_get_home_dir().exists() else []
else:  # auto
    # Manual check for each backend
```
**Issue:** if/elif chain requires modification for each new agent.

**Recommendation:** Use a registry pattern:
```python
AGENT_HOME_DIRS = {
    AGENT_CLAUDE: lambda: Path.home() / ".claude" / "projects",
    AGENT_CODEX: codex_get_home_dir,
    AGENT_GEMINI: lambda: Path.home() / ".gemini" / "sessions",
}
```

### 5. Session Scanning Logic (agent-history:1783-1805)
```python
for backend in backends:
    if backend == AGENT_CLAUDE:
        sessions = get_workspace_sessions(...)
    elif backend == AGENT_CODEX:
        sessions = codex_scan_sessions(...)
```
**Issue:** Another if/elif chain. Would need `elif backend == AGENT_GEMINI`.

**Recommendation:** Use a dispatch table:
```python
AGENT_SCANNERS = {
    AGENT_CLAUDE: get_workspace_sessions,
    AGENT_CODEX: codex_scan_sessions,
    AGENT_GEMINI: gemini_scan_sessions,
}
```

### 6. Default Agent Fallback (multiple locations)
- agent-history:618: `agent = session.get("agent", AGENT_CLAUDE)`
- agent-history:4279: `agent = session.get("agent", AGENT_CLAUDE)`
- agent-history:6930: `agent = session.get("agent", AGENT_CLAUDE)`

**Issue:** Sessions without an explicit agent field default to Claude. This may be incorrect for Gemini sessions.

---

## Test Coverage Gaps

### 1. Tests Only Use "codex" for Propagation Verification
All 14 agent propagation tests use `agent = "codex"`:
```python
class MockArgs:
    agent = "codex"
# ...
assert "codex" in captured_calls
```
**Issue:** Tests verify that "codex" is propagated but don't verify that ANY arbitrary string is propagated. A bug that only propagates "codex" hardcoded would pass these tests.

**Recommendation:** Parameterize tests:
```python
@pytest.mark.parametrize("agent_value", ["claude", "codex", "gemini", "unknown"])
def test_dispatch_lsw_additive_passes_agent(self, monkeypatch, agent_value):
    class MockArgs:
        agent = agent_value
    # ...
    assert agent_value in captured_calls
```

### 2. `detect_agent_from_path` Only Tests Two Cases
```python
def test_detect_claude_path(self):
    assert ch.detect_agent_from_path(path) == "claude"

def test_detect_codex_path(self):
    assert ch.detect_agent_from_path(path) == "codex"
```
**Issue:** No test for unknown paths (e.g., `/home/user/.gemini/sessions/...`).

**Recommendation:** Add negative test:
```python
def test_detect_unknown_path_defaults_to_claude(self):
    path = Path("/home/user/.gemini/sessions/test.jsonl")
    assert ch.detect_agent_from_path(path) == "claude"  # Current behavior
```

### 3. `get_active_backends` Tests Are Exhaustive but Not Extensible
Tests verify Claude-only, Codex-only, and auto modes work, but don't test what happens with an unknown agent value.

**Recommendation:** Add test:
```python
def test_get_active_backends_unknown_agent_returns_empty(self):
    backends = ch.get_active_backends("gemini")
    assert backends == []  # Or should it raise?
```

### 4. No CLI Argument Validation Test
No test verifies that `--agent gemini` is rejected.

**Recommendation:** Add test:
```python
def test_agent_flag_rejects_unknown_value(self):
    with pytest.raises(SystemExit):
        parser.parse_args(["--agent", "gemini", "lsw"])
```

### 5. Parser Selection Tests Missing
No tests verify that the correct parser (Claude vs Codex) is selected based on file path.

**Recommendation:** Add tests:
```python
def test_convert_uses_codex_parser_for_codex_files(self, monkeypatch):
    # Verify codex_parse_jsonl_to_markdown is called for .codex paths

def test_convert_uses_claude_parser_for_claude_files(self, monkeypatch):
    # Verify parse_jsonl_to_markdown is called for .claude paths
```

---

## Summary

### Source Code Issues (6)
| # | Location | Issue | Severity |
|---|----------|-------|----------|
| 1 | :41-42 | Hardcoded agent constants | Medium |
| 2 | :89-101 | Binary path detection | High |
| 3 | :8294 | Hardcoded CLI choices | Low |
| 4 | :1743-1755 | if/elif for backend selection | Medium |
| 5 | :1783-1805 | if/elif for session scanning | Medium |
| 6 | Multiple | Default to Claude fallback | Medium |

### Test Coverage Issues (5)
| # | Issue | Impact |
|---|-------|--------|
| 1 | Propagation tests only use "codex" | May miss bugs that hardcode specific values |
| 2 | No unknown path detection test | Won't catch regression if default changes |
| 3 | No unknown agent backend test | Undefined behavior for new agents |
| 4 | No CLI validation test for unknown agents | Won't catch if choices list is wrong |
| 5 | No parser selection tests | Won't catch wrong parser being used |

---

## Recommendations for Gemini Support

### Minimum Changes Required
1. Add `AGENT_GEMINI = "gemini"` constant
2. Update `detect_agent_from_path()` to check for `.gemini`
3. Update CLI choices to include "gemini"
4. Add `gemini_scan_sessions()` function
5. Add `gemini_parse_jsonl_to_markdown()` function (or reuse if format is same)
6. Update `get_active_backends()` and `get_unified_sessions()` with elif branches

### Better Approach: Refactor for Extensibility
1. Create agent registry with home dirs, scanners, and parsers
2. Loop over registry instead of if/elif chains
3. Derive CLI choices from registry
4. Make path detection data-driven

### Test Improvements Needed
1. Parameterize agent propagation tests with multiple values
2. Add tests for unknown/new agent values
3. Add parser selection tests
4. Add CLI validation tests
