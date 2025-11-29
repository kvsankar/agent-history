# claude-history Regression Test Cases

This document lists all test combinations for `claude-history`. Use this as a checklist when testing across different environments.

**Important Notes:**
- Replace `<user>` with test username (e.g., `testuser`)
- Replace `<workspace>` with test workspace pattern (e.g., `test-project`)
- Replace `<host>` with test hostname (e.g., `testhost`)
- Replace `<distro>` with WSL distribution name (e.g., `Ubuntu`)
- Tests assume Claude Code is installed with at least one conversation
- Mark each test: ✅ Pass, ❌ Fail, ⊘ N/A (not applicable for environment)

## Environment Detection

Before running tests, determine your environment:

```bash
# Check if running in WSL
uname -a | grep -i microsoft && echo "WSL" || echo "Linux"

# Check if running on Windows
ver  # Windows command prompt/PowerShell
```

---

## Test Suite Organization

### Section 1: Basic Commands (All Environments)
### Section 2: Local Operations (All Environments)
### Section 3: WSL Operations (Windows only)
### Section 4: Windows Operations (WSL only)
### Section 5: SSH Remote Operations (All Environments)
### Section 6: Multi-Source Operations (All Environments)
### Section 7: Error Handling & Edge Cases
### Section 8: Special Features
### Section 9: Alias Operations (All Environments)

---

## Section 1: Basic Commands (All Environments)

### 1.1 Version and Help

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 1.1.1 | `./claude-history --version` | Shows version number | ⬜ |
| 1.1.2 | `./claude-history --help` | Shows help text | ⬜ |
| 1.1.3 | `./claude-history lsh --help` | Shows lsh help | ⬜ |
| 1.1.4 | `./claude-history lsw --help` | Shows lsw help | ⬜ |
| 1.1.5 | `./claude-history lss --help` | Shows lss help | ⬜ |
| 1.1.6 | `./claude-history export --help` | Shows export help | ⬜ |
| 1.1.7 | `./claude-history alias --help` | Shows alias help | ⬜ |

---

## Section 2: Local Operations (All Environments)

### 2.1 lsh - List Hosts (Local)

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| 2.1.1 | `./claude-history lsh` | Shows local installation | All | ⬜ |
| 2.1.2 | `./claude-history lsh --local` | Shows only local | All | ⬜ |
| 2.1.3 | `./claude-history lsh --wsl` | Shows WSL (if on Windows) or empty | Win | ⬜ |
| 2.1.4 | `./claude-history lsh --wsl` | Shows nothing or N/A message | WSL/Linux | ⬜ |
| 2.1.5 | `./claude-history lsh --windows` | Shows Windows users (if on WSL) | WSL | ⬜ |
| 2.1.6 | `./claude-history lsh --windows` | Shows nothing or N/A message | Win/Linux | ⬜ |

### 2.2 lsw - List Workspaces (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 2.2.1 | `./claude-history lsw` | Lists all local workspaces | ⬜ |
| 2.2.2 | `./claude-history lsw <workspace>` | Lists workspaces matching pattern | ⬜ |
| 2.2.3 | `./claude-history lsw nonexistent` | Lists no workspaces (empty) | ⬜ |

### 2.3 lss - List Sessions (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 2.3.1 | `./claude-history lss` | Lists sessions from current workspace | ⬜ |
| 2.3.2 | `./claude-history lss <workspace>` | Lists sessions from specific workspace | ⬜ |
| 2.3.3 | `./claude-history lss <workspace> --since 2025-01-01` | Lists sessions after date | ⬜ |
| 2.3.4 | `./claude-history lss <workspace> --until 2025-12-31` | Lists sessions before date | ⬜ |
| 2.3.5 | `./claude-history lss <workspace> --since 2025-01-01 --until 2025-12-31` | Lists sessions in date range | ⬜ |

### 2.4 export - Export Sessions (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 2.4.1 | `./claude-history export` | Exports current workspace to default dir | ⬜ |
| 2.4.2 | `./claude-history export <workspace>` | Exports specific workspace | ⬜ |
| 2.4.3 | `./claude-history export <workspace> -o /tmp/test` | Exports to custom directory | ⬜ |
| 2.4.4 | `./claude-history export --aw` | Exports all workspaces | ⬜ |
| 2.4.5 | `./claude-history export --minimal` | Exports without metadata | ⬜ |
| 2.4.6 | `./claude-history export --split 100` | Splits conversations at ~100 lines | ⬜ |
| 2.4.7 | `./claude-history export --flat` | Uses flat directory structure | ⬜ |
| 2.4.8 | `./claude-history export --force` | Re-exports even if up-to-date | ⬜ |
| 2.4.9 | `./claude-history export --since 2025-01-01` | Exports sessions after date | ⬜ |
| 2.4.10 | `./claude-history export --until 2025-12-31` | Exports sessions before date | ⬜ |

### 2.5 Incremental Export

| Test ID | Steps | Expected Result | Status |
|---------|-------|----------------|--------|
| 2.5.1 | 1. `export <workspace>`<br>2. Re-run same command | Second run skips unchanged files | ⬜ |
| 2.5.2 | 1. `export <workspace>`<br>2. Touch .jsonl file<br>3. Re-run | Re-exports modified file only | ⬜ |
| 2.5.3 | 1. `export <workspace>`<br>2. `export <workspace> --force` | Force re-exports all files | ⬜ |

---

## Section 3: WSL Operations (Windows Only)

### 3.1 lsh with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 3.1.1 | `python claude-history lsh --wsl` | Lists WSL distributions with Claude | ⬜ |
| 3.1.2 | `python claude-history lsh --wsl <distro>` | Filters by specific distro name | ⬜ |
| 3.1.3 | `python claude-history lsh --wsl NonExistent` | Shows no distributions | ⬜ |

### 3.2 lsw with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 3.2.1 | `python claude-history lsw --wsl` | Lists workspaces from first WSL distro | ⬜ |
| 3.2.2 | `python claude-history lsw --wsl <distro>` | Lists workspaces from specific distro | ⬜ |
| 3.2.3 | `python claude-history lsw <workspace> --wsl` | Filters workspaces by pattern in WSL | ⬜ |

### 3.3 lss with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 3.3.1 | `python claude-history lss --wsl` | Lists sessions from current workspace in WSL | ⬜ |
| 3.3.2 | `python claude-history lss <workspace> --wsl` | Lists sessions from WSL workspace | ⬜ |
| 3.3.3 | `python claude-history lss <workspace> --wsl <distro>` | Lists sessions from specific distro | ⬜ |
| 3.3.4 | `python claude-history lss <workspace> --wsl --since 2025-01-01` | Date filtering in WSL | ⬜ |

### 3.4 export with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 3.4.1 | `python claude-history export --wsl` | Exports current workspace from WSL | ⬜ |
| 3.4.2 | `python claude-history export <workspace> --wsl` | Exports specific workspace from WSL | ⬜ |
| 3.4.3 | `python claude-history export <workspace> --wsl <distro>` | Exports from specific distro | ⬜ |
| 3.4.4 | `python claude-history export --wsl -o C:\test` | Exports to Windows directory | ⬜ |
| 3.4.5 | `python claude-history export --wsl --minimal` | Minimal export from WSL | ⬜ |

### 3.5 WSL Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 3.5.1 | List WSL workspaces | Excludes `--wsl-*` cached directories | ⬜ |
| 3.5.2 | List WSL workspaces | Excludes `-remote-*` cached directories | ⬜ |
| 3.5.3 | Export from WSL | Filenames have `wsl_<distro>_` prefix | ⬜ |

---

## Section 4: Windows Operations (WSL Only)

### 4.1 lsh with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 4.1.1 | `./claude-history lsh --windows` | Lists Windows users with Claude | ⬜ |
| 4.1.2 | `./claude-history lsh --windows <user>` | Filters by specific username | ⬜ |
| 4.1.3 | `./claude-history lsh --windows NonExistent` | Shows no users | ⬜ |

### 4.2 lsw with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 4.2.1 | `./claude-history lsw --windows` | Lists workspaces from Windows | ⬜ |
| 4.2.2 | `./claude-history lsw --windows <user>` | Lists workspaces from specific user | ⬜ |
| 4.2.3 | `./claude-history lsw <workspace> --windows` | Filters workspaces by pattern | ⬜ |

### 4.3 lss with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 4.3.1 | `./claude-history lss --windows` | Lists sessions from Windows | ⬜ |
| 4.3.2 | `./claude-history lss <workspace> --windows` | Lists sessions from Windows workspace | ⬜ |
| 4.3.3 | `./claude-history lss <workspace> --windows <user>` | Lists from specific user | ⬜ |
| 4.3.4 | `./claude-history lss <workspace> --windows --since 2025-01-01` | Date filtering | ⬜ |

### 4.4 export with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 4.4.1 | `./claude-history export --windows` | Exports from Windows | ⬜ |
| 4.4.2 | `./claude-history export <workspace> --windows` | Exports specific workspace | ⬜ |
| 4.4.3 | `./claude-history export <workspace> --windows <user>` | Exports from specific user | ⬜ |
| 4.4.4 | `./claude-history export --windows -o /tmp/test` | Exports to WSL directory | ⬜ |
| 4.4.5 | `./claude-history export --windows --minimal` | Minimal export | ⬜ |

### 4.5 Windows Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 4.5.1 | List Windows workspaces | Excludes `--wsl-*` cached directories | ⬜ |
| 4.5.2 | List Windows workspaces | Excludes `-remote-*` cached directories | ⬜ |
| 4.5.3 | Export from Windows | Filenames have `windows_` prefix | ⬜ |

---

## Section 5: SSH Remote Operations (All Environments)

**Prerequisites:**
- SSH access to test host configured
- Passwordless SSH key setup
- Claude Code installed on remote

### 5.1 lsw with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 5.1.1 | `./claude-history lsw -r <user>@<host>` | Lists remote workspaces | ⬜ |
| 5.1.2 | `./claude-history lsw <workspace> -r <user>@<host>` | Filters remote workspaces | ⬜ |

### 5.2 lss with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 5.2.1 | `./claude-history lss -r <user>@<host>` | Lists remote sessions | ⬜ |
| 5.2.2 | `./claude-history lss <workspace> -r <user>@<host>` | Lists from remote workspace | ⬜ |
| 5.2.3 | `./claude-history lss <workspace> -r <user>@<host> --since 2025-01-01` | Date filtering | ⬜ |

### 5.3 export with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 5.3.1 | `./claude-history export -r <user>@<host>` | Exports from remote | ⬜ |
| 5.3.2 | `./claude-history export <workspace> -r <user>@<host>` | Exports specific workspace | ⬜ |
| 5.3.3 | `./claude-history export <workspace> -r <user>@<host> -o /tmp/test` | Custom output dir | ⬜ |
| 5.3.4 | `./claude-history export --minimal -r <user>@<host>` | Minimal export | ⬜ |

### 5.4 SSH Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 5.4.1 | List remote workspaces | Excludes `remote_*` cached directories | ⬜ |
| 5.4.2 | List remote workspaces | Excludes `wsl_*` cached directories | ⬜ |
| 5.4.3 | Export from remote | Filenames have `remote_<host>_` prefix | ⬜ |

---

## Section 6: Multi-Source Operations (All Environments)

### 6.1 export --as (All Sources)

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| 6.1.1 | `./claude-history export --as` | Exports from all available sources | All | ⬜ |
| 6.1.2 | `./claude-history export <workspace> --as` | Exports workspace from all sources | All | ⬜ |
| 6.1.3 | `./claude-history export --as --aw` | All workspaces, all sources | All | ⬜ |
| 6.1.4 | `./claude-history export --as -r <user>@<host>` | All sources + SSH remote | All | ⬜ |
| 6.1.5 | `python claude-history export --as` | Includes local + WSL on Windows | Win | ⬜ |
| 6.1.6 | `./claude-history export --as` | Includes local + Windows on WSL | WSL | ⬜ |

### 6.2 Multiple SSH Remotes

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 6.2.1 | `./claude-history export -r <user>@<host1> -r <user>@<host2>` | Exports from multiple remotes | ⬜ |
| 6.2.2 | `./claude-history export --as -r <user>@<host1> -r <user>@<host2>` | All sources + multiple SSH | ⬜ |

### 6.3 Source Tag Verification

| Test ID | Scenario | Expected Filename Pattern | Status |
|---------|----------|--------------------------|--------|
| 6.3.1 | Export from local | `YYYYMMDDHHMMSS_<uuid>.md` (no prefix) | ⬜ |
| 6.3.2 | Export from WSL | `wsl_<distro>_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |
| 6.3.3 | Export from Windows | `windows_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |
| 6.3.4 | Export from SSH remote | `remote_<host>_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |

### 6.4 Organized Export Structure

| Test ID | Command | Expected Directory Structure | Status |
|---------|---------|----------------------------|--------|
| 6.4.1 | `./claude-history export <workspace>` | `./claude-conversations/<workspace>/files.md` | ⬜ |
| 6.4.2 | `./claude-history export --flat` | `./claude-conversations/files.md` (flat) | ⬜ |
| 6.4.3 | `./claude-history export --as` | Source-tagged files in workspace subdirs | ⬜ |

---

## Section 7: Error Handling & Edge Cases

### 7.1 Invalid Arguments

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 7.1.1 | `./claude-history invalid-command` | Shows error + help text | ⬜ |
| 7.1.2 | `./claude-history lss --since invalid-date` | Shows date format error | ⬜ |
| 7.1.3 | `./claude-history lss --since 2025-12-31 --until 2025-01-01` | Shows "since > until" error | ⬜ |
| 7.1.4 | `./claude-history export --split invalid` | Shows "split value must be an integer" error | ⬜ |
| 7.1.5 | `./claude-history export --split 0` | Shows "split value must be a positive integer" error | ⬜ |
| 7.1.6 | `./claude-history export --split -100` | Shows "split value must be a positive integer" error | ⬜ |

### 7.2 Missing Resources

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 7.2.1 | `./claude-history lss nonexistent-workspace` | Shows no sessions found | ⬜ |
| 7.2.2 | `./claude-history export nonexistent-workspace` | Shows no sessions or skips | ⬜ |
| 7.2.3 | `./claude-history lsw --wsl NonExistentDistro` | Shows no workspaces | ⬜ |

### 7.3 SSH Errors

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 7.3.1 | `./claude-history lsw -r invalid@host` | Shows SSH connection error | ⬜ |
| 7.3.2 | `./claude-history lsw -r <user>@unreachable-host` | Shows timeout/connection error | ⬜ |

### 7.4 File System Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 7.4.1 | Workspace with spaces in name | Handles correctly | ⬜ |
| 7.4.2 | Workspace with special characters | Handles correctly | ⬜ |
| 7.4.3 | Very long workspace name | Handles correctly | ⬜ |
| 7.4.4 | Empty .jsonl file | Skips or shows warning | ⬜ |
| 7.4.5 | Corrupted .jsonl file | Shows error, continues with others | ⬜ |

### 7.5 Circular Fetching Prevention

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 7.5.1 | List workspaces with `remote_*` dirs present | Excludes cached dirs | ⬜ |
| 7.5.2 | List workspaces with `wsl_*` dirs present | Excludes cached dirs | ⬜ |
| 7.5.3 | List workspaces with `--wsl-*` dirs present | Excludes cached dirs | ⬜ |
| 7.5.4 | List workspaces with `-remote-*` dirs present | Excludes cached dirs | ⬜ |

---

## Section 8: Special Features

### 8.1 Conversation Splitting

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 8.1.1 | `./claude-history export --split 100` | Creates part1, part2, etc. files | ⬜ |
| 8.1.2 | Verify split files | Each part has navigation footer | ⬜ |
| 8.1.3 | Verify split files | Parts have message range info | ⬜ |
| 8.1.4 | Short conversation with --split | Single file (no splitting needed) | ⬜ |

### 8.2 Minimal Export Mode

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 8.2.1 | `./claude-history export --minimal` | Output has no metadata sections | ⬜ |
| 8.2.2 | `./claude-history export --minimal` | Output has no HTML anchors | ⬜ |
| 8.2.3 | `./claude-history export --minimal` | Output has conversation content | ⬜ |

### 8.3 Agent Conversation Detection

| Test ID | Scenario | Expected Result | Status |
|---------|----------|--------|
| 8.3.1 | Export agent file (agent-*.jsonl) | Title says "Agent" | ⬜ |
| 8.3.2 | Export agent file | Has warning notice in header | ⬜ |
| 8.3.3 | Export agent file | Shows parent session ID | ⬜ |

---

## Test Execution Guidelines

### Running Tests by Environment

**On Windows:**
- Run all Section 1, 2 tests
- Run all Section 3 tests (WSL operations)
- Run Section 5 tests if SSH configured
- Run Section 6.1.5 (multi-source with WSL)
- Skip Section 4 (N/A)

**On WSL:**
- Run all Section 1, 2 tests
- Run all Section 4 tests (Windows operations)
- Run Section 5 tests if SSH configured
- Run Section 6.1.6 (multi-source with Windows)
- Skip Section 3 (N/A)

**On Linux:**
- Run all Section 1, 2 tests
- Run Section 5 tests if SSH configured
- Run Section 6.1.1-6.1.4 (SSH multi-source only)
- Skip Section 3, 4 (N/A)

### Success Criteria

- **Pass**: Command produces expected result
- **Fail**: Command produces unexpected result or error
- **N/A**: Test not applicable to current environment

### Logging Results

Create a test report with:
```
Environment: [Windows|WSL|Linux]
Date: YYYY-MM-DD
Version: vX.Y.Z
Total Tests Run: N
Passed: N
Failed: N
N/A: N
```

List any failures with:
- Test ID
- Command executed
- Expected result
- Actual result
- Error messages (if any)

---

## Quick Smoke Test (Essential Tests Only)

Minimal test set to verify basic functionality:

| Test | Command | Expected |
|------|---------|----------|
| 1 | `./claude-history --version` | Shows version |
| 2 | `./claude-history lsh` | Lists local |
| 3 | `./claude-history lsw` | Lists workspaces |
| 4 | `./claude-history lss` | Lists sessions |
| 5 | `./claude-history export -o /tmp/test` | Exports successfully |

**Environment-specific additions:**

Windows: Add `python claude-history lsw --wsl`
WSL: Add `./claude-history lsw --windows`
All: Add `./claude-history lsw -r <user>@<host>` (if SSH available)

---

## Section 9: Alias Operations (All Environments)

### 9.1 Alias Management

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 9.1.1 | `./claude-history alias list` | Shows all aliases (or empty) | ⬜ |
| 9.1.2 | `./claude-history alias create testproject` | Creates new alias | ⬜ |
| 9.1.3 | `./claude-history alias show testproject` | Shows empty alias | ⬜ |
| 9.1.4 | `./claude-history alias add testproject -- <workspace>` | Adds local workspace | ⬜ |
| 9.1.5 | `./claude-history alias show testproject` | Shows added workspace | ⬜ |
| 9.1.6 | `./claude-history alias remove testproject -- <workspace>` | Removes workspace | ⬜ |
| 9.1.7 | `./claude-history alias delete testproject` | Deletes alias | ⬜ |

### 9.2 Alias with Sources

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| 9.2.1 | `./claude-history alias add testproject --windows -- <ws>` | Adds Windows workspace | WSL | ⬜ |
| 9.2.2 | `python claude-history alias add testproject --wsl -- <ws>` | Adds WSL workspace | Win | ⬜ |
| 9.2.3 | `./claude-history alias add testproject -r user@host -- <ws>` | Adds remote workspace | All | ⬜ |
| 9.2.4 | `./claude-history alias show testproject` | Shows workspaces by source | All | ⬜ |

### 9.3 Using Aliases with lss

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 9.3.1 | `./claude-history lss @testproject` | Lists sessions from alias workspaces | ⬜ |
| 9.3.2 | `./claude-history lss --alias testproject` | Same as above | ⬜ |
| 9.3.3 | `./claude-history lss @testproject --since 2025-01-01` | Date filtering works | ⬜ |
| 9.3.4 | `./claude-history lss @nonexistent` | Shows alias not found error | ⬜ |

### 9.4 Using Aliases with export

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 9.4.1 | `./claude-history export @testproject` | Exports from alias workspaces | ⬜ |
| 9.4.2 | `./claude-history export --alias testproject` | Same as above | ⬜ |
| 9.4.3 | `./claude-history export @testproject -o /tmp/test` | Custom output dir | ⬜ |
| 9.4.4 | `./claude-history export @testproject --minimal` | Minimal mode works | ⬜ |
| 9.4.5 | `./claude-history export @testproject --as` | All sources for alias | ⬜ |
| 9.4.6 | `./claude-history export @nonexistent` | Shows alias not found error | ⬜ |

### 9.5 Alias Export/Import

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| 9.5.1 | `./claude-history alias export /tmp/aliases.json` | Exports aliases to file | ⬜ |
| 9.5.2 | Verify `/tmp/aliases.json` | Valid JSON with version and aliases | ⬜ |
| 9.5.3 | `./claude-history alias import /tmp/aliases.json` | Imports aliases from file | ⬜ |
| 9.5.4 | `./claude-history alias import nonexistent.json` | Shows file not found error | ⬜ |

### 9.6 Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| 9.6.1 | Workspace name starting with `-` | Requires `--` separator | ⬜ |
| 9.6.2 | Alias name with special chars | Handled correctly | ⬜ |
| 9.6.3 | Add duplicate workspace | Shows already exists | ⬜ |
| 9.6.4 | Remove non-existent workspace | Shows not found | ⬜ |
| 9.6.5 | Create duplicate alias | Shows already exists | ⬜ |
| 9.6.6 | Empty alias with lss/export | Shows no workspaces message | ⬜ |

---

## Notes

- All tests should complete without crashes or unhandled exceptions
- Error messages should be clear and actionable
- Deprecation warnings should not prevent commands from working
- File paths should use platform-appropriate separators
- Timestamps should be in ISO 8601 format
- Output should be UTF-8 encoded
