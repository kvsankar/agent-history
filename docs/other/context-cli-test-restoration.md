# Context: CLI Redesign Test Restoration

**Date:** 2026-01-04
**Branch:** feature/2.0-exploration

## Problem Summary

Commit `78ccdf1` ("Implement CLI noun-verb redesign and legacy mapping") deleted ~1,000 tests from `tests/unit/test_claude_history.py` (14,135 → 159 lines). Test count dropped from 1,200+ to ~215.

## CLI Redesign Overview

### Old CLI (Legacy)
```
lsw                    # list workspaces
lss                    # list sessions
lsh                    # list homes
export <pattern>       # export sessions
stats                  # show statistics
alias <subcommand>     # manage projects
```

### New CLI (Noun-Verb)
```
ws [list|show|export|stats]           # workspace commands
session [list|show|export|stats]      # session commands
home [list|add|remove|show|export]    # home commands
project [list|add|remove|show|...]    # project commands
```

### Key Changes
- `lsw` → `ws`
- `lss` → `session`
- `lsh` → `home`
- `export` → `session export`
- `stats` → `session stats`
- `alias` → `project`
- Pattern matching now uses `-n <pattern>` flag

## Work Completed

### 1. Removed legacy translation from agent-history script
- Deleted `_translate_legacy_cli_args()` function (~60 lines)
- Removed call in `main()` function
- File: `agent-history` (lines 17585-17646 removed)

### 2. Removed legacy_cli import from integration tests
Updated these files to remove `from tests.legacy_cli import translate_legacy_args`:
- `tests/integration/test_cli_flags.py` ✅ (also updated CLI calls)
- `tests/integration/test_e2e_cli.py` ✅ (also updated CLI calls)
- `tests/integration/test_e2e_codex.py` ✅ (import removed, CLI calls partially updated)
- `tests/integration/test_e2e_gemini.py` ✅ (import removed)
- `tests/integration/test_e2e_stats_alias.py` ✅ (import removed)
- `tests/integration/test_e2e_stats_more.py` ✅ (import removed)
- `tests/integration/test_real_local.py` ✅ (import removed)

### 3. Updated CLI calls in some files
- `test_cli_flags.py`: Updated all `export` → `session export` calls
- `test_e2e_cli.py`: Updated `lsh`→`home`, `lsw`→`ws`, `lss`→`session`, `export`→`session export`, `stats`→`session stats`

## Work Pending

### 1. Update remaining CLI calls in integration tests
Files still have legacy command patterns:
```
tests/integration/test_e2e_codex.py:  stats, lss
tests/integration/test_e2e_gemini.py: stats
tests/integration/test_e2e_stats_alias.py: stats, alias, lss
tests/integration/test_e2e_stats_more.py: stats, lss
tests/integration/test_real_local.py: lsw, lss
```

### 2. Delete tests/legacy_cli.py
File exists but is no longer imported anywhere after our changes.

### 3. Restore pure unit tests
The original plan was Option D (Hybrid):
- Keep ~400 pure unit tests (no CLI dependency) - restore as-is
- Skip/delete ~600 CLI parser tests that test old structure
- Keep 9 new v2 CLI tests already in the file

The old tests are extracted at `/tmp/old_tests.py` (14,135 lines).

### 4. Update unit test file
Current state of `tests/unit/test_claude_history.py`:
- Has merged content (14,254 lines) but uses `translate_legacy_args` which we're removing
- Needs to be reverted/rebuilt with only pure unit tests

## Command Mapping Reference

| Old | New | Notes |
|-----|-----|-------|
| `["lsw"]` | `["ws"]` | |
| `["lss", "pattern"]` | `["session", "-n", "pattern"]` | Pattern now uses `-n` flag |
| `["lsh"]` | `["home"]` | |
| `["export", "pattern"]` | `["session", "export", "-n", "pattern"]` | |
| `["stats", "--aw"]` | `["session", "stats", "--aw"]` | |
| `["stats", "--sync"]` | `["session", "stats", "--sync"]` | |
| `["alias", "create", name]` | `["project", "add", name, "--allow-empty"]` | |
| `["alias", "add", ...]` | `["project", "add", ...]` | |
| `["alias", "show", name]` | `["project", "show", name]` | |
| `["alias", "export"]` | `["project", "config-export"]` | |
| `["lss", "@alias"]` | `["session", "--project", alias]` | |

## Stats flag mapping
| Old | New |
|-----|-----|
| `--by-workspace` | `--by workspace` |
| `--models` | `--by model` |
| `--tools` | `--by tool` |
| `--by-day` | `--by day` |

## Files Modified

```
agent-history                                  # Removed _translate_legacy_cli_args
tests/integration/test_cli_flags.py            # Removed import + updated CLI calls
tests/integration/test_e2e_cli.py              # Removed import + updated CLI calls
tests/integration/test_e2e_codex.py            # Removed import only
tests/integration/test_e2e_gemini.py           # Removed import only
tests/integration/test_e2e_stats_alias.py      # Removed import only
tests/integration/test_e2e_stats_more.py       # Removed import only
tests/integration/test_real_local.py           # Removed import only
tests/unit/test_claude_history.py              # Currently in mixed state
```

## Files to Delete
```
tests/legacy_cli.py                            # No longer needed
```

## Decision Points for Reconsideration

1. **Keep legacy support?** We decided to remove it, but this is a breaking change for users.

2. **Test restoration strategy:**
   - Option A: Update all tests to new CLI syntax (high effort, clean)
   - Option B: Keep legacy translation in tests only (medium effort, tests legacy compat)
   - Option C: Only restore pure unit tests (low effort, reduced coverage)
   - Option D: Hybrid - pure unit tests + some new CLI tests (current choice)

3. **Integration test updates:** Many tests use legacy commands. Either update them all or reconsider removing legacy support.

## Current Test Count
- Before work: 215 tests collected
- After merged file (with issues): 1,081 tests collected
- Target: ~1,100+ tests

## To Resume Work

1. Decide on legacy support (keep or remove)
2. If removing legacy:
   - Complete CLI call updates in integration tests
   - Delete `tests/legacy_cli.py`
   - Rebuild unit test file with pure unit tests only
3. If keeping legacy:
   - Revert agent-history changes
   - Keep `tests/legacy_cli.py`
   - Use translation layer in tests
4. Run `uv run pytest` to verify
