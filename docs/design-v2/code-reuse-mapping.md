# Code Reuse Mapping

## Overview

This document maps existing code in `agent-history` to the new pipeline architecture entities, identifying what can be reused as-is, what needs modification, and what needs to be written new.

## Pipeline Entity → Existing Code Mapping

### 1. CLI Parser

**New Entity Responsibility:** Parse command line arguments into structured CommandContext

**Existing Code (Reuse As-Is):**
- `argparse` setup in `main()` - argument definitions can be kept
- Subparser structure for commands

**Existing Code (Needs Modification):**
- None - CLI parsing is already clean

**New Code Needed:**
- `CommandContext` dataclass to hold parsed arguments
- Validation of mutually exclusive options

---

### 2. Context Builder

**New Entity Responsibility:** Build initial TemplateScope from CommandContext + environment

**Existing Code (Reuse As-Is):**
| Function | Line | Purpose |
|----------|------|---------|
| `get_current_workspace()` | ~5900 | Get CWD workspace |
| `load_aliases()` | 8619 | Load project configurations |
| `get_alias_for_workspace()` | 8880 | Find project for workspace |
| `is_running_in_wsl()` | 5732 | Detect WSL environment |
| `get_wsl_distributions()` | 6127 | List WSL distros |

**Existing Code (Needs Modification):**
| Function | Line | Change Needed |
|----------|------|---------------|
| `_get_patterns_from_args()` | ~various | Refactor to return WorkspaceSpec instead of string patterns |

**New Code Needed:**
- `ContextBuilder` class
- `build_template_scope(ctx: CommandContext) -> TemplateScope`
- ProjectRecord and ScopeRecord dataclasses
- HomeSpec, WorkspaceSpec, SessionSpec types
- `All` sentinel object

---

### 3. Scope Resolver

**New Entity Responsibility:** Progressive expansion from TemplateScope to ConcreteScope

#### Stage 0: Project Expansion

**Existing Code (Reuse As-Is):**
| Function | Line | Purpose |
|----------|------|---------|
| `load_aliases()` | 8619 | Get project → workspace mappings |
| `_expand_alias_to_conditions()` | ~various | Logic for alias expansion (SQL version) |

**New Code Needed:**
- `expand_projects(scope: TemplateScope) -> TemplateScope`
- Handle multi-home projects

#### Stage 1: Home Expansion

**Existing Code (Reuse As-Is):**
| Function | Line | Purpose |
|----------|------|---------|
| `get_wsl_distributions()` | 6127 | List WSL homes |
| `is_running_in_wsl()` | 5732 | Detect current home |
| `get_windows_claude_dir()` | ~various | Windows home path |

**New Code Needed:**
- `expand_homes(scope: TemplateScope) -> TemplateScope`
- Home category resolution (wsl → wsl:Ubuntu, etc.)

#### Stage 2: Workspace Expansion

**Existing Code (Reuse As-Is):**
| Function | Line | Purpose |
|----------|------|---------|
| `normalize_workspace_name()` | 5340 | Normalize paths |
| `get_workspace_name_from_path()` | 5974 | Extract workspace from path |
| `decode_workspace_name()` | 5268 | Decode Claude's format |

**Existing Code (Needs MAJOR Modification):**
| Function | Line | Issue |
|----------|------|-------|
| `_matches_workspace_pattern()` | 1140 | Substring matching bug - needs exact match option |
| `matches_any_pattern()` | 1020 | Uses problematic matching |

**New Code Needed:**
- `expand_workspaces(scope: TemplateScope) -> TemplateScope`
- `resolve_workspace_spec(spec: WorkspaceSpec, home: str) -> List[str]`
- Exact matching implementation

#### Stage 3: Session Expansion

**Existing Code (Reuse As-Is):**
| Function | Line | Purpose |
|----------|------|---------|
| `get_workspace_sessions()` | 5670 | Get sessions for workspace |
| `codex_scan_sessions()` | 3549 | Scan Codex sessions |
| `gemini_scan_sessions()` | 4571 | Scan Gemini sessions |
| `get_session_metadata()` | ~various | Session info extraction |

**Existing Code (Needs Modification):**
| Function | Line | Change Needed |
|----------|------|---------------|
| `collect_sessions_with_dedup()` | ~various | Remove pattern matching, use exact workspace |

**New Code Needed:**
- `expand_sessions(scope: TemplateScope) -> ConcreteScope`
- `collect_sessions_exact(home, workspace, filters) -> List[Session]`

---

### 4. Verb Dispatcher

**New Entity Responsibility:** Route to appropriate verb handler

**Existing Code (Reuse As-Is):**
- Subcommand dispatch in `main()` - already uses subparsers

**New Code Needed:**
- `VerbDispatcher` class (simple routing)
- Verb registration mechanism

---

### 5. Verb Handlers

**New Entity Responsibility:** Execute command logic on ConcreteScope

#### session list
**Existing Code (Partial Reuse):**
| Function | Line | Status |
|----------|------|--------|
| `cmd_list()` | ~1600 | Keep output logic, remove scope resolution |
| `print_sessions_output()` | 1815 | Reuse as-is |

**Changes Needed:**
- Remove pattern resolution, accept ConcreteScope
- Use `flatten_scope_to_sessions()`

#### session export
**Existing Code (Partial Reuse):**
| Function | Line | Status |
|----------|------|--------|
| `cmd_export_all()` | ~various | Keep export logic, remove scope resolution |
| Markdown generation | various | Reuse as-is |

**Changes Needed:**
- Remove pattern resolution, accept ConcreteScope
- Consistent behavior for explicit/implicit

#### session stats
**Existing Code (Partial Reuse):**
| Function | Line | Status |
|----------|------|--------|
| `cmd_stats()` | ~various | Keep stats calculation, remove scope resolution |
| Stats calculation logic | various | Reuse as-is |

**Changes Needed:**
- Add @project syntax support
- Accept ConcreteScope

#### project show
**Existing Code (Partial Reuse):**
| Function | Line | Status |
|----------|------|--------|
| `cmd_project_show()` | ~various | Keep display logic |

**Changes Needed:**
- Add implicit project detection
- Accept ConcreteScope

#### project stats
**Existing Code (Reuse As-Is):**
| Function | Line | Status |
|----------|------|--------|
| `cmd_project_stats()` | ~various | Already works correctly! Use as reference |

---

### 6. Output Formatter

**New Entity Responsibility:** Format output consistently

**Existing Code (Reuse As-Is):**
| Function/Class | Line | Purpose |
|----------------|------|---------|
| `TablePrinter` | 1508 | Table formatting |
| `print_sessions_output()` | 1815 | Session list output |
| `format_duration()` | ~various | Time formatting |
| `format_bytes()` | ~various | Size formatting |

**New Code Needed:**
- `OutputFormatter` wrapper class (optional, for consistency)

---

## Summary: Code Reuse Statistics

| Category | Reuse As-Is | Needs Modification | New Code |
|----------|-------------|-------------------|----------|
| CLI Parser | 90% | 0% | 10% |
| Context Builder | 60% | 10% | 30% |
| Scope Resolver | 50% | 20% | 30% |
| Verb Dispatcher | 80% | 0% | 20% |
| Verb Handlers | 70% | 20% | 10% |
| Output Formatter | 95% | 0% | 5% |
| **Overall** | **~65%** | **~15%** | **~20%** |

---

## Critical Functions Requiring Modification

### 1. `_matches_workspace_pattern()` (Line ~1140)

**Current (BUGGY):**
```python
def _matches_workspace_pattern(session, pattern):
    readable_lower = session.get('workspace_readable', '').lower()
    pattern_lower = pattern.lower()
    if readable_lower and pattern_lower in readable_lower:  # SUBSTRING!
        return True
```

**Required Fix:**
```python
def _matches_workspace_pattern(session, pattern, match_type='exact'):
    readable = session.get('workspace_readable', '')
    if match_type == 'exact':
        return readable == pattern  # EXACT MATCH
    elif match_type == 'contains':
        return pattern.lower() in readable.lower()
    elif match_type == 'prefix':
        return readable.startswith(pattern)
    # ... etc
```

### 2. `collect_sessions_with_dedup()` (Various)

**Current:** Uses pattern matching internally
**Required:** Accept workspace list, use exact matching

### 3. Session collection in export

**Current:** Two different code paths for explicit vs implicit
**Required:** Single path using ConcreteScope

---

## Implementation Priority

### Phase 1: Core Infrastructure (Minimal Disruption)
1. Create dataclasses: `CommandContext`, `ScopeRecord`, `ProjectRecord`
2. Create spec types: `HomeSpec`, `WorkspaceSpec`, `SessionSpec`
3. Create `All` sentinel
4. Implement `ContextBuilder.build_template_scope()`

### Phase 2: Scope Resolver (The Fix)
1. Implement `expand_projects()`
2. Implement `expand_homes()`
3. Implement `expand_workspaces()` with EXACT matching
4. Implement `expand_sessions()`
5. Integrate into `resolve_scope()` entry point

### Phase 3: Migrate Commands (One by One)
1. `session list` - highest impact, most broken
2. `session export` - explicit≠implicit bug
3. `session stats` - add @project support
4. `project show` - add implicit detection
5. Keep `project stats` as reference (already works)

### Phase 4: Cleanup
1. Deprecate old pattern matching functions
2. Remove duplicate code paths
3. Update tests

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Breaking existing functionality | Phase by phase migration, comprehensive tests |
| Performance regression | Reuse existing optimized scanning functions |
| Index compatibility | Keep existing index formats, just change resolution |
| Complex refactoring | Leverage working `project stats` as reference implementation |

---

## Files to Create

1. `src/scope/__init__.py` - Package init
2. `src/scope/types.py` - Dataclasses and spec types
3. `src/scope/context_builder.py` - ContextBuilder class
4. `src/scope/resolver.py` - ScopeResolver class
5. `src/scope/utils.py` - flatten_scope, count_scope, etc.

Or, if keeping single-file structure:
- Add new section to `agent-history` with clear markers

---

## Testing Strategy

### Behavioral Tests Enable Safe Refactoring

The tests in `tests/cli/scope/test_context_consistency.py` are **behavioral/integration tests**:
- Use `run_cli_subprocess()` to invoke the CLI
- Test input/output behavior, not internal functions
- No imports of internal module functions

**Implication:** We can freely refactor internals without modifying tests. The tests define the behavioral contract - as long as CLI behavior matches expected output, implementation details don't matter.

### Current Status: 11 FAILED, 6 PASSED

Failed tests expose the bugs we're fixing. When all 17 pass, the architecture is correct.

### Continuous Validation

Run tests after each phase:
```bash
pytest tests/cli/scope/test_context_consistency.py -v
```

## Validation Checklist

After implementation, ALL these tests must pass:

- [ ] `session list --project testproj` returns 5 sessions (not 9)
- [ ] `session list` from project workspace returns 5 sessions
- [ ] Explicit and implicit produce IDENTICAL results
- [ ] `session export --project testproj` exports 5 files
- [ ] `session export` from workspace exports 5 files
- [ ] `session stats @testproj` works
- [ ] `project show` from workspace auto-detects project
- [ ] No auth-infra/auth-api substring bleed in any command
