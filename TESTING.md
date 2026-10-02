# cagelens Regression Test Cases

This document lists all test combinations for `cagelens`. Use this as a checklist when testing across different environments.

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

## Windows Test Runner

On Windows, pytest cache writes can be very slow. Use the helper script to set
temp directories and disable the cache provider by default:

```bash
python scripts/run_tests.py
```

Run `uv sync --dev` first on a fresh checkout. The examples assume an activated
virtualenv; `make test` and `scripts\run-tests.ps1` use `.venv` directly when it
exists.

Options:
- `--cache` keeps pytest's cache provider enabled.
- `--tmp-root <path>` overrides the temp root used for `--basetemp`.

---

## Test Suite Organization

### Section 1: Basic Commands (All Environments)
### Section 2: Local Operations (All Environments)
### Section 3: WSL Operations (Windows only)
### Section 4: Windows Operations (WSL only)
### Section 5: SSH Remote Operations (All Environments)
### Section 6: Multi-Source Operations (All Environments)
  - 6.6: Multiple Workspace Patterns
  - 6.7: Lenient Multi-Source Behavior
### Section 7: Error Handling & Edge Cases
### Section 8: Special Features
### Section 9: Alias Operations (All Environments)
### Section 10: SSH Remote Management (lsh add/remove/clear)
### Section 11: Stats Command (All Environments)
  - 11.3: Time Tracking
  - 11.4: Orthogonal Flags (--ah/--aw)
### Section 12: Automatic Alias Scoping (All Environments)
### Section 13: Orthogonal Flag Combinations
### Section 14: Reset Command (All Environments)

---

## Section 1: Basic Commands (All Environments)

### 1.1 Version and Help

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| cli_help_version | `cagelens --version` | Shows version number | ⬜ |
| cli_help_main | `cagelens --help` | Shows help text | ⬜ |
| cli_help_lsh | `cagelens lsh --help` | Shows lsh help | ⬜ |
| cli_help_lsw | `cagelens lsw --help` | Shows lsw help | ⬜ |
| cli_help_lss | `cagelens lss --help` | Shows lss help (includes --this) | ⬜ |
| cli_help_export | `cagelens export --help` | Shows export help (includes --this) | ⬜ |
| cli_help_alias | `cagelens alias --help` | Shows alias help | ⬜ |
| cli_help_lshadd | `cagelens lsh add --help` | Shows lsh add help | ⬜ |
| cli_help_stats | `cagelens stats --help` | Shows stats help (includes --this, --time, --top-ws) | ⬜ |
| cli_help_reset | `cagelens reset --help` | Shows reset help | ⬜ |

---

## Section 2: Local Operations (All Environments)

### 2.1 lsh - List Hosts (Local)

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| local_lsh_show | `cagelens lsh` | Shows local installation | All | ⬜ |
| local_lsh_local_only | `cagelens lsh --local` | Shows only local | All | ⬜ |
| local_lsh_wsl_win | `cagelens lsh --wsl` | Shows WSL (if on Windows) or empty | Win | ⬜ |
| local_lsh_wsl_na | `cagelens lsh --wsl` | Shows nothing or N/A message | WSL/Linux | ⬜ |
| local_lsh_windows_wsl | `cagelens lsh --windows` | Shows Windows users (if on WSL) | WSL | ⬜ |
| local_lsh_windows_na | `cagelens lsh --windows` | Shows nothing or N/A message | Win/Linux | ⬜ |

### 2.2 lsw - List Workspaces (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| local_lsw_all | `cagelens lsw` | Lists all local workspaces | ⬜ |
| local_lsw_pattern | `cagelens lsw <workspace>` | Lists workspaces matching pattern | ⬜ |
| local_lsw_nonexistent | `cagelens lsw nonexistent` | Lists no workspaces (empty) | ⬜ |
| local_lsw_missing_marker | `cagelens lsw <workspace>` where dir missing | Shows closest match with `[missing]` suffix | ⬜ |

### 2.3 lss - List Sessions (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| local_lss_current | `cagelens lss` | Lists sessions from current workspace | ⬜ |
| local_lss_workspace | `cagelens lss <workspace>` | Lists sessions from specific workspace | ⬜ |
| local_lss_absolute_path | `cagelens lss C:\path\to\workspace` | Resolves absolute path target; lists sessions | ⬜ |
| local_lss_unc_infers_local | `cagelens lss \\wsl.localhost\Distro\home\user\.claude\projects\-home-user-ws` | Works without `--wsl` by inferring projects root | ⬜ |
| local_lss_since | `cagelens lss <workspace> --since 2025-01-01` | Lists sessions after date | ⬜ |
| local_lss_until | `cagelens lss <workspace> --until 2025-12-31` | Lists sessions before date | ⬜ |
| local_lss_range | `cagelens lss <workspace> --since 2025-01-01 --until 2025-12-31` | Lists sessions in date range | ⬜ |

### 2.4 export - Export Sessions (Local)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| local_export_current | `cagelens export` | Exports current workspace to default dir | ⬜ |
| local_export_workspace | `cagelens export <workspace>` | Exports specific workspace | ⬜ |
| local_export_output | `cagelens export <workspace> -o /tmp/test` | Exports to custom directory | ⬜ |
| local_export_aw | `cagelens export --aw` | Exports all workspaces | ⬜ |
| local_export_minimal | `cagelens export --minimal` | Exports without metadata | ⬜ |
| local_export_split | `cagelens export --split 100` | Splits conversations at ~100 lines | ⬜ |
| local_export_flat | `cagelens export --flat` | Uses flat directory structure | ⬜ |
| local_export_force | `cagelens export --force` | Re-exports even if up-to-date | ⬜ |
| local_export_since | `cagelens export --since 2025-01-01` | Exports sessions after date | ⬜ |
| local_export_until | `cagelens export --until 2025-12-31` | Exports sessions before date | ⬜ |

### 2.5 Incremental Export

| Test ID | Steps | Expected Result | Status |
|---------|-------|----------------|--------|
| local_incr_skip_unchanged | 1. `export <workspace>`<br>2. Re-run same command | Second run skips unchanged files | ⬜ |
| local_incr_modified_only | 1. `export <workspace>`<br>2. Touch .jsonl file<br>3. Re-run | Re-exports modified file only | ⬜ |
| local_incr_force_all | 1. `export <workspace>`<br>2. `export <workspace> --force` | Force re-exports all files | ⬜ |

---

## Section 3: WSL Operations (Windows Only)

### 3.1 lsh with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| wsl_lsh_list | `python cagelens lsh --wsl` | Lists WSL distributions with Claude | ⬜ |
| wsl_lsh_all_homes | `python cagelens lsh` | Shows all homes including WSL | ⬜ |

### 3.2 lsw with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| wsl_lsw_list | `python cagelens lsw --wsl` | Lists workspaces from WSL (auto-detects distro) | ⬜ |
| wsl_lsw_missing_tail | `python cagelens lsw --wsl` with a missing WSL workspace dir | Lists workspace with `[missing]` suffix | ⬜ |
| wsl_lss_slash_pattern | `cagelens lss --wsl projects/my-work` | Matches encoded workspace with slashes | ⬜ |
| wsl_lsw_pattern | `python cagelens lsw <workspace> --wsl` | Filters workspaces by pattern in WSL | ⬜ |
| wsl_lss_unc_without_flag | `cagelens lss \\wsl.localhost\\Distro\\home\\user\\.claude\\projects\\-home-user-ws` | Works without `--wsl`; lists sessions | ⬜ |

### 3.3 lss with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| wsl_lss_current | `python cagelens lss --wsl` | Lists sessions from current workspace in WSL | ⬜ |
| wsl_lss_workspace | `python cagelens lss <workspace> --wsl` | Lists sessions from WSL workspace | ⬜ |
| wsl_lss_date | `python cagelens lss <workspace> --wsl --since 2025-01-01` | Date filtering in WSL | ⬜ |

### 3.4 export with WSL

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| wsl_export_current | `python cagelens export --wsl` | Exports current workspace from WSL | ⬜ |
| wsl_export_workspace | `python cagelens export <workspace> --wsl` | Exports specific workspace from WSL | ⬜ |
| wsl_export_output | `python cagelens export --wsl -o C:\test` | Exports to Windows directory | ⬜ |
| wsl_export_minimal | `python cagelens export --wsl --minimal` | Minimal export from WSL | ⬜ |

### 3.5 WSL Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| wsl_filter_exclude_wsl | List WSL workspaces | Excludes `--wsl-*` cached directories | ⬜ |
| wsl_filter_exclude_remote | List WSL workspaces | Excludes `-remote-*` cached directories | ⬜ |
| wsl_filter_prefix | Export from WSL | Filenames have `wsl_<distro>_` prefix | ⬜ |

---

## Section 4: Windows Operations (WSL Only)

### 4.1 lsh with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| win_lsh_list | `cagelens lsh --windows` | Lists Windows users with Claude | ⬜ |
| win_lsh_all_homes | `cagelens lsh` | Shows all homes including Windows | ⬜ |

### 4.2 lsw with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| win_lsw_list | `cagelens lsw --windows` | Lists workspaces from Windows (auto-detects user) | ⬜ |
| win_lsw_pattern | `cagelens lsw <workspace> --windows` | Filters workspaces by pattern | ⬜ |

### 4.3 lss with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| win_lss_list | `cagelens lss --windows` | Lists sessions from Windows | ⬜ |
| win_lss_workspace | `cagelens lss <workspace> --windows` | Lists sessions from Windows workspace | ⬜ |
| win_lss_date | `cagelens lss <workspace> --windows --since 2025-01-01` | Date filtering | ⬜ |

### 4.4 export with Windows

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| win_export_export | `cagelens export --windows` | Exports from Windows | ⬜ |
| win_export_workspace | `cagelens export <workspace> --windows` | Exports specific workspace | ⬜ |
| win_export_output | `cagelens export --windows -o /tmp/test` | Exports to WSL directory | ⬜ |
| win_export_minimal | `cagelens export --windows --minimal` | Minimal export | ⬜ |

### 4.5 Windows Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| win_filter_exclude_wsl | List Windows workspaces | Excludes `--wsl-*` cached directories | ⬜ |
| win_filter_exclude_remote | List Windows workspaces | Excludes `-remote-*` cached directories | ⬜ |
| win_filter_prefix | Export from Windows | Filenames have `windows_` prefix | ⬜ |

---

## Section 5: SSH Remote Operations (All Environments)

**Prerequisites:**
- SSH access to test host configured
- Passwordless SSH key setup
- Claude Code installed on remote

### 5.1 lsw with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| ssh_lsw_remote | `cagelens lsw -r <user>@<host>` | Lists remote workspaces | ⬜ |
| ssh_lsw_pattern | `cagelens lsw <workspace> -r <user>@<host>` | Filters remote workspaces | ⬜ |

### 5.2 lss with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| ssh_lss_remote | `cagelens lss -r <user>@<host>` | Lists remote sessions | ⬜ |
| ssh_lss_workspace | `cagelens lss <workspace> -r <user>@<host>` | Lists from remote workspace | ⬜ |
| ssh_lss_date | `cagelens lss <workspace> -r <user>@<host> --since 2025-01-01` | Date filtering | ⬜ |

### 5.3 export with SSH

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| ssh_export_remote | `cagelens export -r <user>@<host>` | Exports from remote | ⬜ |
| ssh_export_workspace | `cagelens export <workspace> -r <user>@<host>` | Exports specific workspace | ⬜ |
| ssh_export_output | `cagelens export <workspace> -r <user>@<host> -o /tmp/test` | Custom output dir | ⬜ |
| ssh_export_minimal | `cagelens export --minimal -r <user>@<host>` | Minimal export | ⬜ |

### 5.4 SSH Filtering

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| ssh_filter_exclude_remote | List remote workspaces | Excludes `remote_*` cached directories | ⬜ |
| ssh_filter_exclude_wsl | List remote workspaces | Excludes `wsl_*` cached directories | ⬜ |
| ssh_filter_prefix | Export from remote | Filenames have `remote_<host>_` prefix | ⬜ |

---

## Section 6: Multi-Source Operations (All Environments)

### 6.1 lsw/lss --ah (All Sources)

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| multi_all_lsw | `cagelens lsw --ah` | Lists workspaces from all homes | All | ⬜ |
| multi_all_lss | `cagelens lss --ah` | Lists sessions from all homes | All | ⬜ |
| multi_all_lsw_pattern | `cagelens lsw <workspace> --ah` | Filters workspaces from all homes | All | ⬜ |
| multi_all_lss_pattern | `cagelens lss <workspace> --ah` | Filters sessions from all homes | All | ⬜ |
| multi_all_lsw_ssh | `cagelens lsw --ah -r <user>@<host>` | All sources + SSH remote | All | ⬜ |
| multi_all_lss_ssh | `cagelens lss --ah -r <user>@<host>` | All sources + SSH remote | All | ⬜ |

### 6.2 export --ah (All Sources)

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| multi_export_all | `cagelens export --ah` | Exports from all available sources | All | ⬜ |
| multi_export_workspace | `cagelens export <workspace> --ah` | Exports workspace from all homes | All | ⬜ |
| multi_export_aw | `cagelens export --ah --aw` | All workspaces, all homes | All | ⬜ |
| multi_export_ssh | `cagelens export --ah -r <user>@<host>` | All sources + SSH remote | All | ⬜ |
| multi_export_wsl_win | `python cagelens export --ah` | Includes local + WSL on Windows | Win | ⬜ |
| multi_export_win_wsl | `cagelens export --ah` | Includes local + Windows on WSL | WSL | ⬜ |

### 6.3 Multiple SSH Remotes

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| multi_remotes_export | `cagelens export -r <user>@<host1> -r <user>@<host2>` | Exports from multiple remotes | ⬜ |
| multi_remotes_all_ssh | `cagelens export --ah -r <user>@<host1> -r <user>@<host2>` | All sources + multiple SSH | ⬜ |
| multi_remotes_lsw | `cagelens lsw --ah -r <user>@<host1> -r <user>@<host2>` | Lists from multiple remotes | ⬜ |
| multi_remotes_lss | `cagelens lss --ah -r <user>@<host1> -r <user>@<host2>` | Lists from multiple remotes | ⬜ |

### 6.4 Source Tag Verification

| Test ID | Scenario | Expected Filename Pattern | Status |
|---------|----------|--------------------------|--------|
| multi_tags_local | Export from local | `YYYYMMDDHHMMSS_<uuid>.md` (no prefix) | ⬜ |
| multi_tags_wsl | Export from WSL | `wsl_<distro>_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |
| multi_tags_windows | Export from Windows | `windows_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |
| multi_tags_ssh | Export from SSH remote | `remote_<host>_YYYYMMDDHHMMSS_<uuid>.md` | ⬜ |

### 6.5 Organized Export Structure

| Test ID | Command | Expected Directory Structure | Status |
|---------|---------|----------------------------|--------|
| multi_struct_workspace_dir | `cagelens export <workspace>` | `./.cagelens/exports/<workspace>/files.md` | ⬜ |
| multi_struct_flat | `cagelens export --flat` | `./.cagelens/exports/files.md` (flat) | ⬜ |
| multi_struct_all_sources | `cagelens export --ah` | Source-tagged files in workspace subdirs | ⬜ |

### 6.6 Multiple Workspace Patterns

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| multi_patterns_lsw | `cagelens lsw <pattern1> <pattern2>` | Lists workspaces matching either pattern | ⬜ |
| multi_patterns_lsw_ah | `cagelens lsw <pattern1> <pattern2> --ah` | Multiple patterns + all homes | ⬜ |
| multi_patterns_lsw_ssh | `cagelens lsw <pattern1> <pattern2> -r <user>@<host>` | Multiple patterns + SSH remote | ⬜ |
| multi_patterns_lss | `cagelens lss <pattern1> <pattern2>` | Lists sessions from both patterns (deduplicated) | ⬜ |
| multi_patterns_lss_ah | `cagelens lss <pattern1> <pattern2> --ah` | Multiple patterns + all homes | ⬜ |
| multi_patterns_lss_ssh | `cagelens lss <pattern1> <pattern2> -r <user>@<host>` | Multiple patterns + SSH remote | ⬜ |
| multi_patterns_lss_all_ssh | `cagelens lss <pattern1> <pattern2> --ah -r <user>@<host>` | Multiple patterns + all homes + SSH | ⬜ |
| multi_patterns_export | `cagelens export <pattern1> <pattern2>` | Exports from both patterns | ⬜ |
| multi_patterns_export_ssh | `cagelens export <pattern1> <pattern2> -r <user>@<host>` | Multiple patterns + SSH remote | ⬜ |
| multi_patterns_export_ah | `cagelens export <pattern1> <pattern2> --ah` | Multiple patterns + all homes export | ⬜ |
| multi_patterns_export_all_ssh | `cagelens export <pattern1> <pattern2> --ah -r <user>@<host>` | Multiple patterns + all homes + SSH | ⬜ |
| multi_patterns_dedup_lss | `cagelens lss <overlapping1> <overlapping2>` | No duplicate sessions (deduplication works) | ⬜ |
| multi_patterns_dedup_export | `cagelens export <overlapping1> <overlapping2>` | No duplicate exports (deduplication works) | ⬜ |

### 6.7 Lenient Multi-Source Behavior

Tests for lenient behavior when patterns don't match on all homes:

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| multi_lenient_partial_match | `cagelens export --ah <exists> <notexists> -r <host>` | Exports from local/windows, reports "No matching" for remote | ⬜ |
| multi_lenient_remote_no_match | `cagelens export --ah <pattern> -r <host_with_no_match>` | Reports "No matching sessions" for remote, continues | ⬜ |
| multi_lenient_multi_pattern | `cagelens export --ah <pattern1> <pattern2>` | Exports from all homes that have matches | ⬜ |
| multi_lenient_no_match | `cagelens export <nonexistent1> <nonexistent2>` | Error: No sessions found (nothing matches anywhere) | ⬜ |
| multi_lenient_some_empty | `cagelens export --ah --aw` (some sources empty) | Exports from sources with data, reports "No matching" for empty | ⬜ |

**Expected Behavior:**
- `export --ah` is lenient: continues when a pattern doesn't match on a particular source
- Single-source `export` fails if no patterns match
- "No matching sessions" message shown for sources without matches
- Summary shows correct count per source

---

## Section 7: Error Handling & Edge Cases

### 7.1 Invalid Arguments

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| err_args_invalid_cmd | `cagelens invalid-command` | Shows error + help text | ⬜ |
| err_args_invalid_date | `cagelens lss --since invalid-date` | Shows date format error | ⬜ |
| err_args_since_after_until | `cagelens lss --since 2025-12-31 --until 2025-01-01` | Shows "since > until" error | ⬜ |
| err_args_split_invalid | `cagelens export --split invalid` | Shows "split value must be an integer" error | ⬜ |
| err_args_split_zero | `cagelens export --split 0` | Shows "split value must be a positive integer" error | ⬜ |
| err_args_split_negative | `cagelens export --split -100` | Shows "split value must be a positive integer" error | ⬜ |

### 7.2 Missing Resources

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| err_missing_workspace | `cagelens lss nonexistent-workspace` | Shows no sessions found | ⬜ |
| err_missing_export | `cagelens export nonexistent-workspace` | Shows no sessions or skips | ⬜ |
| err_missing_wsl_distro | `cagelens lsw --wsl NonExistentDistro` | Shows no workspaces | ⬜ |
| err_missing_outside_lss | `cd /tmp && cagelens lss` | Shows "Not in a Claude Code workspace" error with suggestions | ⬜ |
| err_missing_outside_export | `cd /tmp && cagelens export` | Shows "Not in a Claude Code workspace" error with suggestions | ⬜ |
| err_missing_outside_lsw | `cd /tmp && cagelens lsw` | Works - lists all workspaces | ⬜ |
| err_missing_outside_pattern | `cd /tmp && cagelens lss <pattern>` | Works - pattern matching still works outside workspace | ⬜ |
| err_missing_outside_ah | `cd /tmp && cagelens lss --ah` | Works - --ah flag bypasses workspace check | ⬜ |
| err_missing_outside_aw | `cd /tmp && cagelens export --aw` | Works - --aw flag bypasses workspace check | ⬜ |

### 7.3 SSH Errors

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| err_ssherr_invalid_host | `cagelens lsw -r invalid@host` | Shows SSH connection error | ⬜ |
| err_ssherr_timeout | `cagelens lsw -r <user>@unreachable-host` | Shows timeout/connection error | ⬜ |

### 7.4 File System Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| err_fs_spaces | Workspace with spaces in name | Handles correctly | ⬜ |
| err_fs_special_chars | Workspace with special characters | Handles correctly | ⬜ |
| err_fs_long_name | Very long workspace name | Handles correctly | ⬜ |
| err_fs_empty_jsonl | Empty .jsonl file | Skips or shows warning | ⬜ |
| err_fs_corrupted | Corrupted .jsonl file | Shows error, continues with others | ⬜ |

### 7.5 Circular Fetching Prevention

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| err_circ_remote | List workspaces with `remote_*` dirs present | Excludes cached dirs | ⬜ |
| err_circ_wsl | List workspaces with `wsl_*` dirs present | Excludes cached dirs | ⬜ |
| err_circ_wsl_dash | List workspaces with `--wsl-*` dirs present | Excludes cached dirs | ⬜ |
| err_circ_remote_dash | List workspaces with `-remote-*` dirs present | Excludes cached dirs | ⬜ |

---

## Section 8: Special Features

### 8.1 Conversation Splitting

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| feat_split_create_parts | `cagelens export --split 100` | Creates part1, part2, etc. files | ⬜ |
| feat_split_navigation | Verify split files | Each part has navigation footer | ⬜ |
| feat_split_range_info | Verify split files | Parts have message range info | ⬜ |
| feat_split_short_no_split | Short conversation with --split | Single file (no splitting needed) | ⬜ |

### 8.2 Minimal Export Mode

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| feat_minimal_no_metadata | `cagelens export --minimal` | Output has no metadata sections | ⬜ |
| feat_minimal_no_anchors | `cagelens export --minimal` | Output has no HTML anchors | ⬜ |
| feat_minimal_has_content | `cagelens export --minimal` | Output has conversation content | ⬜ |

### 8.3 Agent Conversation Detection

| Test ID | Scenario | Expected Result | Status |
|---------|----------|--------|
| feat_agent_title | Export agent file (agent-*.jsonl) | Title says "Agent" | ⬜ |
| feat_agent_warning | Export agent file | Has warning notice in header | ⬜ |
| feat_agent_parent | Export agent file | Shows parent session ID | ⬜ |

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
| 1 | `cagelens --version` | Shows version |
| 2 | `cagelens lsh` | Lists local |
| 3 | `cagelens lsw` | Lists workspaces |
| 4 | `cagelens lss` | Lists sessions |
| 5 | `cagelens export -o /tmp/test` | Exports successfully |

**Environment-specific additions:**

Windows: Add `python cagelens lsw --wsl`
WSL: Add `cagelens lsw --windows`
All: Add `cagelens lsw -r <user>@<host>` (if SSH available)

---

## Section 9: Alias Operations (All Environments)

### 9.1 Alias Management

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| alias_mgmt_list_empty | `cagelens alias list` | Shows all aliases (or empty) | ⬜ |
| alias_mgmt_create | `cagelens alias create testproject` | Creates new alias | ⬜ |
| alias_mgmt_show_empty | `cagelens alias show testproject` | Shows empty alias | ⬜ |
| alias_mgmt_add | `cagelens alias add testproject -- <workspace>` | Adds local workspace | ⬜ |
| alias_mgmt_show_ws | `cagelens alias show testproject` | Shows added workspace | ⬜ |
| alias_mgmt_remove | `cagelens alias remove testproject -- <workspace>` | Removes workspace | ⬜ |
| alias_mgmt_delete | `cagelens alias delete testproject` | Deletes alias | ⬜ |

### 9.2 Alias with Sources

| Test ID | Command | Expected Result | Env | Status |
|---------|---------|----------------|-----|--------|
| alias_source_local | `cagelens alias add testproject <pattern>` | Adds local workspace by pattern | All | ⬜ |
| alias_source_windows | `cagelens alias add testproject --windows <pattern>` | Adds Windows workspace | WSL | ⬜ |
| alias_source_wsl | `python cagelens alias add testproject --wsl <pattern>` | Adds WSL workspace | Win | ⬜ |
| alias_source_remote | `cagelens alias add testproject -r user@host <pattern>` | Adds remote workspace | All | ⬜ |
| alias_source_all_homes | `cagelens alias add testproject --ah -r user@host <pattern>` | Adds from all homes at once | All | ⬜ |
| alias_source_pick | `cagelens alias add testproject --ah --pick` | Interactive picker from all homes | All | ⬜ |
| alias_source_show_counts | `cagelens alias show testproject` | Shows workspaces by source with session counts | All | ⬜ |

### 9.3 Using Aliases with lss

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| alias_lss_at_syntax | `cagelens lss @testproject` | Lists sessions from alias workspaces | ⬜ |
| alias_lss_flag | `cagelens lss --alias testproject` | Same as above | ⬜ |
| alias_lss_date | `cagelens lss @testproject --since 2025-01-01` | Date filtering works | ⬜ |
| alias_lss_not_found | `cagelens lss @nonexistent` | Shows alias not found error | ⬜ |

### 9.4 Using Aliases with export

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| alias_export_at_syntax | `cagelens export @testproject` | Exports from alias workspaces (all homes) | ⬜ |
| alias_export_flag | `cagelens export --alias testproject` | Same as above | ⬜ |
| alias_export_output | `cagelens export @testproject -o /tmp/test` | Custom output dir | ⬜ |
| alias_export_minimal | `cagelens export @testproject --minimal` | Minimal mode works | ⬜ |
| alias_export_not_found | `cagelens export @nonexistent` | Shows alias not found error | ⬜ |

### 9.4a Alias Export with Remote Auto-Fetch

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| alias_fetch_fetch | Alias has remote workspace (not cached) | Auto-fetches via SSH then exports | ⬜ |
| alias_fetch_cached | Alias has remote workspace (already cached) | Uses cache, exports directly | ⬜ |
| alias_fetch_windows | Alias has Windows workspace | Exports from Windows directly | ⬜ |
| alias_fetch_mixed | Alias has mixed sources | Exports from all homes with correct prefixes | ⬜ |
| alias_fetch_unreachable | Remote unreachable | Shows warning, continues with other sources | ⬜ |

### 9.5 Alias Export/Import

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| alias_io_export | `cagelens alias export /tmp/aliases.json` | Exports aliases to file | ⬜ |
| alias_io_verify | Verify `/tmp/aliases.json` | Valid JSON with version and aliases | ⬜ |
| alias_io_import | `cagelens alias import /tmp/aliases.json` | Imports aliases from file | ⬜ |
| alias_io_not_found | `cagelens alias import nonexistent.json` | Shows file not found error | ⬜ |

### 9.6 Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| alias_edge_dash_ws | Workspace name starting with `-` | Requires `--` separator | ⬜ |
| alias_edge_special | Alias name with special chars | Handled correctly | ⬜ |
| alias_edge_duplicate | Add duplicate workspace | Shows already exists | ⬜ |
| alias_edge_remove_missing | Remove non-existent workspace | Shows not found | ⬜ |
| alias_edge_create_dup | Create duplicate alias | Shows already exists | ⬜ |
| alias_edge_empty | Empty alias with lss/export | Shows no workspaces message | ⬜ |

---

## Section 10: SSH Remote Management (lsh add/remove/clear)

### 10.1 SSH Remote Management

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| lshadd_mgmt_list | `cagelens lsh` | Lists hosts including SSH remotes (or empty) | ⬜ |
| lshadd_mgmt_remotes_only | `cagelens lsh --remotes` | Lists only SSH remotes | ⬜ |
| lshadd_mgmt_add | `cagelens lsh add user@host` | Adds SSH remote | ⬜ |
| lshadd_mgmt_show_added | `cagelens lsh` | Shows added remote in SSH Remotes section | ⬜ |
| lshadd_mgmt_add_another | `cagelens lsh add user@host2` | Adds another remote | ⬜ |
| lshadd_mgmt_remove | `cagelens lsh remove user@host` | Removes remote | ⬜ |
| lshadd_mgmt_clear | `cagelens lsh clear` | Clears all SSH remotes | ⬜ |

### 10.2 SSH Remote Validation

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| lshadd_valid_wsl_rejected | `cagelens lsh add wsl://Ubuntu` | Shows "auto-detected" message, not added | ⬜ |
| lshadd_valid_win_rejected | `cagelens lsh add windows` | Shows "auto-detected" message, not added | ⬜ |
| lshadd_valid_invalid_fmt | `cagelens lsh add invalid` | Shows invalid format error | ⬜ |
| lshadd_valid_duplicate | `cagelens lsh add user@host` (duplicate) | Shows already exists | ⬜ |
| lshadd_valid_remove_missing | `cagelens lsh remove nonexistent@host` | Shows not found | ⬜ |

### 10.3 SSH Remotes with --ah Flag

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| lshadd_alflag_lsw | Add remote, then `cagelens lsw --ah` | Includes saved remote | ⬜ |
| lshadd_alflag_lss | Add remote, then `cagelens lss --ah` | Includes saved remote | ⬜ |
| lshadd_alflag_export | Add remote, then `cagelens export --ah` | Includes saved remote | ⬜ |
| lshadd_alflag_stats_sync | Add remote, then `cagelens stats --sync --ah` | Syncs from saved remote | ⬜ |
| lshadd_alflag_extra | `cagelens lsw --ah -r extra@host` | Saved remotes + additional remote | ⬜ |

---

## Section 11: Stats Command (All Environments)

### 11.1 Stats Sync

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| stats_sync_local | `cagelens stats --sync` | Syncs local sessions to DB | ⬜ |
| stats_sync_force | `cagelens stats --sync --force` | Re-syncs all files | ⬜ |
| stats_sync_ah | `cagelens stats --sync --ah` | Syncs from all homes | ⬜ |
| stats_sync_ah_remote | `cagelens stats --sync --ah -r user@host` | Syncs all + extra remote | ⬜ |

### 11.2 Stats Display

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| stats_display_current | `cagelens stats` | Shows summary for current workspace | ⬜ |
| stats_display_aw | `cagelens stats --aw` | Shows summary for all workspaces | ⬜ |
| stats_display_pattern | `cagelens stats <pattern>` | Filters by workspace pattern | ⬜ |
| stats_display_top_ws | `cagelens stats --aw --top-ws 3` | Limits workspaces per home, shows Homes & Workspaces section | ⬜ |
| stats_display_tools | `cagelens stats --by tool` | Shows tool usage stats | ⬜ |
| stats_display_models | `cagelens stats --by model` | Shows model usage stats | ⬜ |
| stats_display_by_ws | `cagelens stats --by workspace` | Shows per-workspace breakdown | ⬜ |
| stats_display_by_day | `cagelens stats --by day` | Shows daily breakdown | ⬜ |
| stats_display_since | `cagelens stats --since 2025-01-01` | Date filtering | ⬜ |
| stats_display_source | `cagelens stats --source local` | Source filtering | ⬜ |

### 11.3 Stats Time Tracking

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| stats_time_current | `cagelens stats --time` | Shows time stats for current workspace | ⬜ |
| stats_time_aw | `cagelens stats --time --aw` | Shows time stats for all workspaces | ⬜ |
| stats_time_ah | `cagelens stats --time --ah` | Auto-syncs, then shows time stats | ⬜ |
| stats_time_ah_aw | `cagelens stats --time --ah --aw` | Syncs all, shows all workspaces | ⬜ |
| stats_time_since | `cagelens stats --time --since 2025-01-01` | Date filtering with time | ⬜ |
| stats_time_format | Verify time output | Shows daily breakdown with work periods; summary always includes time section | ⬜ |
| stats_time_max_24h | Verify time output | No day exceeds 24 hours | ⬜ |

### 11.4 Stats Orthogonal Flags

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| stats_flags_default | `cagelens stats` | Current workspace, local DB | ⬜ |
| stats_flags_ah | `cagelens stats --ah` | Current workspace, syncs all homes first | ⬜ |
| stats_flags_aw | `cagelens stats --aw` | All workspaces, local DB | ⬜ |
| stats_flags_ah_aw | `cagelens stats --ah --aw` | All workspaces, syncs all homes first | ⬜ |

---

## Section 12: Automatic Alias Scoping (All Environments)

**Setup:** Create an alias containing the current workspace before running these tests.

```bash
# Setup (run once before tests)
cagelens alias create testscope
cagelens alias add testscope <current-workspace-pattern>
```

### 12.1 Automatic Scoping with lss

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| scope_lss_message | `cagelens lss` (in aliased workspace) | Shows "📎 Using alias @testscope" message | ⬜ |
| scope_lss_lists_all | `cagelens lss` (in aliased workspace) | Lists sessions from all alias workspaces | ⬜ |
| scope_lss_this | `cagelens lss --this` | Uses current workspace only, no alias message | ⬜ |
| scope_lss_pattern | `cagelens lss <pattern>` | Explicit pattern bypasses alias scoping | ⬜ |
| scope_lss_no_alias | `cagelens lss` (in non-aliased workspace) | No alias message, uses current workspace | ⬜ |

### 12.2 Automatic Scoping with export

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| scope_export_message | `cagelens export` (in aliased workspace) | Shows "📎 Using alias @testscope" message | ⬜ |
| scope_export_exports_all | `cagelens export` (in aliased workspace) | Exports from all alias workspaces | ⬜ |
| scope_export_this | `cagelens export --this` | Exports current workspace only | ⬜ |
| scope_export_pattern | `cagelens export <pattern>` | Explicit pattern bypasses alias scoping | ⬜ |
| scope_export_aw | `cagelens export --aw` | All workspaces, no alias scoping | ⬜ |
| scope_export_ah | `cagelens export --ah` (in aliased workspace) | Shows alias message, uses all homes | ⬜ |

### 12.3 Automatic Scoping with stats

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| scope_stats_message | `cagelens stats` (in aliased workspace) | Shows "📎 Using alias @testscope" message | ⬜ |
| scope_stats_stats_all | `cagelens stats` (in aliased workspace) | Shows stats for all alias workspaces | ⬜ |
| scope_stats_this | `cagelens stats --this` | Shows stats for current workspace only | ⬜ |
| scope_stats_pattern | `cagelens stats <pattern>` | Explicit pattern bypasses alias scoping | ⬜ |
| scope_stats_aw | `cagelens stats --aw` | All workspaces, no alias scoping | ⬜ |
| scope_stats_time | `cagelens stats --time` (in aliased workspace) | Time tracking uses alias scope | ⬜ |
| scope_stats_time_this | `cagelens stats --time --this` | Time tracking for current workspace only | ⬜ |

### 12.4 Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| scope_edge_multi_alias | Workspace in multiple aliases | Uses first matching alias | ⬜ |
| scope_edge_empty | Empty alias (no workspaces) | Shows empty/no sessions message | ⬜ |
| scope_edge_remote_only | Alias with only remote workspaces | Auto-fetches or shows not cached | ⬜ |
| scope_edge_deleted | Delete alias, then run lss | No alias message, uses current workspace | ⬜ |

### 12.5 Cleanup

```bash
# Cleanup after tests
cagelens alias delete testscope
```

---

## Updated Quick Smoke Test

Minimal test set including new features:

| Test | Command | Expected |
|------|---------|----------|
| 1 | `cagelens --version` | Shows version |
| 2 | `cagelens lsh` | Lists hosts and SSH remotes |
| 3 | `cagelens lsw` | Lists workspaces |
| 4 | `cagelens lss` | Lists sessions |
| 5 | `cagelens export -o /tmp/test` | Exports successfully |
| 6 | `cagelens lsh --remotes` | Lists saved SSH remotes |
| 7 | `cagelens stats --sync` | Syncs to DB |
| 8 | `cagelens stats` | Shows summary |
| 9 | `cagelens stats --time` | Shows time tracking |
| 10 | `cagelens stats --agent codex` | Tokens are non-zero for Codex sessions |
| 11 | `cagelens stats --agent gemini` | Tokens are non-zero for Gemini sessions |

**Environment-specific additions:**

- Windows: Add `python cagelens lsw --wsl`
- WSL: Add `cagelens lsw --windows`
- All: Add `cagelens lsw -r <user>@<host>` (if SSH available)
- All: Add `cagelens lsh add <user>@<host>` then `cagelens lsw --ah`

---

## Section 13: Orthogonal Flag Combinations

This section tests all combinations of workspace scope and source scope flags to ensure orthogonal behavior.

### Dimensions

| Dimension | Values |
|-----------|--------|
| **Context** | In-workspace (aliased), In-workspace (not aliased), Outside-workspace |
| **Command** | lss, export, stats |
| **Source Scope** | (default), --ah, -r host, --wsl, --windows |
| **Workspace Scope** | (default), --aw, pattern, @alias |
| **Override** | (default), --this |

### Expected Behavior Matrix

| Scenario | Expected Workspace | Expected Source |
|----------|-------------------|-----------------|
| No flags, in aliased workspace | Alias workspaces | Local only |
| --ah, in aliased workspace | Alias workspaces | All sources |
| --this, in aliased workspace | Current workspace only | Local only |
| --ah --this, in aliased workspace | Current workspace only | All sources |
| --aw | All workspaces | Local only |
| --ah --aw | All workspaces | All sources |
| pattern specified | Pattern workspaces | Local only |
| @alias specified | Alias workspaces | All sources in alias |
| Outside workspace, no flags | ERROR | - |
| Outside workspace, --aw | All workspaces | Local only |
| Outside workspace, pattern | Pattern workspaces | Local only |

### 13.1 In Aliased Workspace

**Setup:** Run from a workspace that belongs to an alias

#### 13.1.1 Default (no flags)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_default_lss | `lss` | Alias workspaces | Local | ⬜ |
| flags_aliased_default_export | `export -o /tmp/t` | Alias workspaces | Local | ⬜ |
| flags_aliased_default_stats | `stats` | Alias workspaces | Local DB | ⬜ |

#### 13.1.2 With --ah (all homes)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_ah_lss | `lss --ah` | Alias workspaces | All sources | ⬜ |
| flags_aliased_ah_export | `export --ah -o /tmp/t` | Alias workspaces | All sources | ⬜ |
| flags_aliased_ah_stats | `stats --ah` | Alias workspaces | Sync all, query alias | ⬜ |

#### 13.1.3 With --this (override alias)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_this_lss | `lss --this` | Current workspace only | Local | ⬜ |
| flags_aliased_this_export | `export --this -o /tmp/t` | Current workspace only | Local | ⬜ |
| flags_aliased_this_stats | `stats --this` | Current workspace only | Local DB | ⬜ |

#### 13.1.4 With --ah --this

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_ah_this_lss | `lss --ah --this` | Current workspace only | All sources | ⬜ |
| flags_aliased_ah_this_export | `export --ah --this -o /tmp/t` | Current workspace only | All sources | ⬜ |
| flags_aliased_ah_this_stats | `stats --ah --this` | Current workspace only | Sync all, query current | ⬜ |

#### 13.1.5 With --aw (all workspaces)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_aw_export | `export --aw -o /tmp/t` | All workspaces | Local | ⬜ |
| flags_aliased_aw_stats | `stats --aw` | All workspaces | Local DB | ⬜ |

#### 13.1.6 With --ah --aw

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_ah_aw_export | `export --ah --aw -o /tmp/t` | All workspaces | All sources | ⬜ |
| flags_aliased_ah_aw_stats | `stats --ah --aw` | All workspaces | Sync all, query all | ⬜ |

#### 13.1.7 With explicit pattern

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_pattern_lss | `lss otherproject` | otherproject | Local | ⬜ |
| flags_aliased_pattern_export | `export otherproject -o /tmp/t` | otherproject | Local | ⬜ |
| flags_aliased_pattern_stats | `stats otherproject` | otherproject | Local DB | ⬜ |

#### 13.1.8 With explicit @alias

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_aliased_alias_lss | `lss @otheralias` | otheralias workspaces | All in alias | ⬜ |
| flags_aliased_alias_export | `export @otheralias -o /tmp/t` | otheralias workspaces | All in alias | ⬜ |
| flags_aliased_alias_stats | `stats @otheralias` | otheralias workspaces | Local DB | ⬜ |

### 13.2 In Non-Aliased Workspace

**Setup:** Run from a workspace that does NOT belong to any alias

#### 13.2.1 Default (no flags)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_nonalias_default_lss | `lss` | Current workspace | Local | ⬜ |
| flags_nonalias_default_export | `export -o /tmp/t` | Current workspace | Local | ⬜ |
| flags_nonalias_default_stats | `stats` | Current workspace | Local DB | ⬜ |

#### 13.2.2 With --ah

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_nonalias_ah_lss | `lss --ah` | Current workspace | All sources | ⬜ |
| flags_nonalias_ah_export | `export --ah -o /tmp/t` | Current workspace | All sources | ⬜ |
| flags_nonalias_ah_stats | `stats --ah` | Current workspace | Sync all, query current | ⬜ |

#### 13.2.3 With --this (no effect in non-aliased)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_nonalias_this_lss | `lss --this` | Current workspace | Local | ⬜ |
| flags_nonalias_this_export | `export --this -o /tmp/t` | Current workspace | Local | ⬜ |
| flags_nonalias_this_stats | `stats --this` | Current workspace | Local DB | ⬜ |

### 13.3 Outside Workspace

**Setup:** Run from a directory that is NOT a Claude workspace (e.g., /tmp)

#### 13.3.1 Default (no flags) - Should ERROR

| ID | Command | Expected Result | Status |
|----|---------|-----------------|--------|
| flags_outside_error_lss | `lss` | ERROR: Not in a workspace | ⬜ |
| flags_outside_error_export | `export` | ERROR: Not in a workspace | ⬜ |
| flags_outside_error_stats | `stats` | ERROR: Not in a workspace | ⬜ |

#### 13.3.2 With --aw (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_outside_aw_export | `export --aw -o /tmp/t` | All workspaces | Local | ⬜ |
| flags_outside_aw_stats | `stats --aw` | All workspaces | Local DB | ⬜ |

#### 13.3.3 With explicit pattern (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_outside_pattern_lss | `lss myproject` | myproject | Local | ⬜ |
| flags_outside_pattern_export | `export myproject -o /tmp/t` | myproject | Local | ⬜ |
| flags_outside_pattern_stats | `stats myproject` | myproject | Local DB | ⬜ |

#### 13.3.4 With @alias (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| flags_outside_alias_lss | `lss @myalias` | Alias workspaces | All in alias | ⬜ |
| flags_outside_alias_export | `export @myalias -o /tmp/t` | Alias workspaces | All in alias | ⬜ |
| flags_outside_alias_stats | `stats @myalias` | Alias workspaces | Local DB | ⬜ |

---

## Section 14: Reset Command (All Environments)

### 14.1 Reset with Confirmation Prompt

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| reset_confirm_cancelled | `cagelens reset` (answer n) | Shows files, prompts, cancelled | ⬜ |
| reset_confirm_confirmed | `cagelens reset` (answer y) | Shows files, prompts, deletes all | ⬜ |
| reset_confirm_db_only | `cagelens reset db` (answer y) | Deletes only metrics.db | ⬜ |
| reset_confirm_settings_only | `cagelens reset settings` (answer y) | Deletes only config.json | ⬜ |
| reset_confirm_aliases_only | `cagelens reset aliases` (answer y) | Deletes only aliases.json | ⬜ |

### 14.2 Reset with -y (Skip Confirmation)

| Test ID | Command | Expected Result | Status |
|---------|---------|----------------|--------|
| reset_skip_db | `cagelens reset db -y` | Deletes metrics.db without prompt | ⬜ |
| reset_skip_settings | `cagelens reset settings -y` | Deletes config.json without prompt | ⬜ |
| reset_skip_aliases | `cagelens reset aliases -y` | Deletes aliases.json without prompt | ⬜ |
| reset_skip_all | `cagelens reset all -y` | Deletes all three files without prompt | ⬜ |
| reset_skip_default_all | `cagelens reset -y` | Deletes all three files without prompt | ⬜ |

### 14.3 Reset Edge Cases

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| reset_edge_nothing | Reset when no files exist | Shows "Nothing to reset." | ⬜ |
| reset_edge_db_only_exists | Reset db when only db exists | Deletes only db | ⬜ |
| reset_edge_after_reset | Reset after reset | Shows "Nothing to reset." | ⬜ |
| reset_edge_ctrl_c | Ctrl+C during prompt | Shows "Cancelled." | ⬜ |

---

## Section 15: Platform-Specific Tests (Real Environment)

These tests run without mocking, using real platform capabilities. They are automatically skipped on platforms where they don't apply.

### 15.1 WSL Environment Tests

**Run on:** WSL only

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| platform_wsl_detection | Running on WSL | `is_running_in_wsl()` returns True | ⬜ |
| platform_wsl_mnt_c_exists | /mnt/c accessible | Path exists and is directory | ⬜ |
| platform_wsl_users_dir_exists | /mnt/c/Users accessible | Path exists and is directory | ⬜ |

### 15.2 WSL with Windows Claude Tests

**Run on:** WSL with Windows Claude installation

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| platform_win_get_users_with_claude | Get Windows users | Returns list with username, path, claude_dir | ⬜ |
| platform_win_get_projects_dir | Get Windows projects dir | Returns valid Path | ⬜ |
| platform_win_list_workspaces | List Windows workspaces | Returns list (may be empty) | ⬜ |
| platform_win_list_sessions | List Windows sessions | Returns list (may be empty) | ⬜ |
| platform_win_source_tag | Windows source tag | Returns "windows_username_" format | ⬜ |
| platform_win_is_windows_remote | Windows remote detection | Correctly identifies windows:// URLs | ⬜ |

### 15.3 Windows Environment Tests

**Run on:** Windows only

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| platform_windows_detection | Running on Windows | `platform.system()` returns "Windows" | ⬜ |
| platform_windows_not_wsl | Not WSL | `is_running_in_wsl()` returns False | ⬜ |

### 15.4 Windows with WSL Tests

**Run on:** Windows with WSL installed

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| platform_wsl_distributions | Get WSL distros | Returns list of distribution names | ⬜ |
| platform_wsl_projects_dir | Get WSL projects dir | Returns Path or None | ⬜ |
| platform_wsl_source_tag | WSL source tag | Returns "wsl_distro_" format | ⬜ |
| platform_wsl_is_wsl_remote | WSL remote detection | Correctly identifies wsl:// URLs | ⬜ |

### 15.5 Cross-Platform Tests

**Run on:** All platforms

| Test ID | Scenario | Expected Result | Status |
|---------|----------|----------------|--------|
| platform_local_projects_dir | Get local projects dir | Returns Path containing ".claude" | ⬜ |
| platform_is_cached_workspace | Cached workspace detection | Correctly identifies remote_, wsl_, windows_ prefixes | ⬜ |
| platform_validate_remote_host | Remote host validation | Validates user@host format, rejects wsl://, windows:// | ⬜ |
| platform_workspace_name_normalization | Workspace name normalization | Decodes -home-user-project format | ⬜ |
| platform_workspace_native_detection | Native workspace detection | Distinguishes native from cached workspaces | ⬜ |

---

## Test Platform Matrix

| Test Suite | Linux | WSL | Windows |
|------------|-------|-----|---------|
| Section 1-2 (Basic, Local) | ✓ | ✓ | ✓ |
| Section 3 (WSL Operations) | Skip | Skip | ✓ |
| Section 4 (Windows Operations) | Skip | ✓ | Skip |
| Section 5 (SSH) | ✓ | ✓ | ✓ |
| Section 6-14 | ✓ | ✓ | ✓ |
| Section 15.1 (WSL Env) | Skip | ✓ | Skip |
| Section 15.2 (WSL+Win Claude) | Skip | ✓* | Skip |
| Section 15.3 (Windows Env) | Skip | Skip | ✓ |
| Section 15.4 (Windows+WSL) | Skip | Skip | ✓* |
| Section 15.5 (Cross-Platform) | ✓ | ✓ | ✓ |

*Requires the target environment to have Claude installed

---

## Notes

- All tests should complete without crashes or unhandled exceptions
- Error messages should be clear and actionable
- Deprecation warnings should not prevent commands from working
- File paths should use platform-appropriate separators
- Timestamps should be in ISO 8601 format
- Output should be UTF-8 encoded

---

## Integration and E2E Tests (No Mocks)

This project includes end-to-end tests that exercise the real CLI against synthetic projects.

Structure
- Unit tests: `tests/unit/` (pure functions, smoke tests)
- Integration tests: `tests/integration/` (no mocks; use env to point CLI at synthetic roots)

Markers and selection
- All E2E modules have `pytestmark = pytest.mark.integration`.
- Run everything (default): `pytest`
- Unit only: `pytest -m "not integration"`
- Integration only: `pytest -m integration tests/integration`

Environment overrides for cross-boundary tests
- Windows → simulate WSL:
  - `CLAUDE_WSL_TEST_DISTRO=TestWSL`
  - `CLAUDE_WSL_PROJECTS_DIR=C:\path\to\synthetic\projects`
- WSL → simulate Windows:
  - `CLAUDE_WINDOWS_PROJECTS_DIR=/mnt/c/path/to/synthetic/projects`
- Isolate config/DB to a temp dir:
  - Windows: `set USERPROFILE=C:\temp\cfg`
  - WSL/Linux: `export HOME=/tmp/cfg`

Scenarios covered (representative)
- Local: lsh/lsw/lss, export (minimal/flat/split)
- Stats: `--sync` then `--by model`, `--by tool`, `--by day`
- Alias: create/add/show/export and `lss @alias`
- All-homes (Windows): combine local + WSL via env override

CI
- GitHub Actions runs unit and integration on `ubuntu-latest` and `windows-latest`.
- Hosted Windows has no WSL; WSL flows are exercised via the environment overrides.
- Full suite runtime can exceed 5 minutes on Windows; set CI timeouts accordingly.
