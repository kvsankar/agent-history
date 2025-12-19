Exploration Log
===============

This file captures exploratory runs performed in Windows for agent-history.
It lists commands executed, expected behavior, and any unexpected results with fixes.

Scope and rules
---------------
- Raw agent data files were not modified.
- Other projects' source code was not modified.
- Temporary export directories were created and deleted.
- Metrics DB was used and reset only when explicitly requested.

Successful runs (expected behavior)
-----------------------------------
- `python .\agent-history lsh`
- `python .\agent-history lsh --wsl`
- `python .\agent-history lsw --ah`
- `python .\agent-history --agent codex lsw --ah`
- `python .\agent-history --agent gemini lsw --ah`
- `python .\agent-history --agent codex lss --wsl --aw`
- `python .\agent-history --agent gemini lss --wsl --aw`
- `python .\agent-history --agent gemini lss --ah --aw`
- `python .\agent-history --agent codex lss --ah --aw`
- `python .\agent-history --agent gemini lss -r sankar@ubuntuvm01 --aw`
- `python .\agent-history stats --agent gemini --source remote:ubuntuvm01 --no-sync`
- `python .\agent-history stats --agent codex --source wsl:Ubuntu --no-sync`
- `python .\agent-history stats --tools --source remote:ubuntuvm01 --no-sync`
- `python .\agent-history stats --sync --ah --jobs 4 -r sankar@ubuntuvm01 --no-windows`
- `python .\agent-history --agent gemini export --ah --aw --no-remote --quiet --jobs 4 -o .\tmp-export`
- `python .\agent-history --agent gemini export claude-history -r sankar@ubuntuvm01 --quiet -o .\tmp-export-remote`
- `python .\agent-history --agent codex export claude-history -r sankar@ubuntuvm01 --quiet -o .\tmp-export-remote`
- `python .\agent-history lsw --local -r sankar@ubuntuvm01`
- `python .\agent-history lss claude-history --wsl --aw`
- `python C:\sankar\projects\claude-history\agent-history stats --aw --no-sync` (outside workspace)
- `python C:\sankar\projects\claude-history\agent-history stats --source remote:ubuntuvm01 --no-sync` (outside workspace)

Unexpected behavior and fixes
-----------------------------
- `stats --agent gemini --source remote:ubuntuvm01` returned 0 sessions because it scoped to the current workspace when no pattern was provided.
  - Fix: `stats --source` now defaults to all workspaces for that source unless `--this` is set.
  - Added unit test and doc note.

- WSL distribution detection sometimes returned only `docker-desktop` when `wsl -d <distro> whoami` timed out.
  - Fix: on timeout, fallback to UNC username discovery.

- `lss` for WSL/Windows Codex or Gemini always showed `MESSAGES` as `0`.
  - Fix: message counting is skipped only for workspace-only listing; sessions now count messages.
  - Added unit test for `_scan_codex_gemini_sessions`.

- `lss --ah --aw` ignored `--aw` for non-Claude agents and used the implied workspace.
  - Fix: `--aw` uses an empty pattern list in all-homes listing for all agents.
  - Added unit test.

- `lss --local -r` with `--agent gemini|codex` pulled Claude remote sessions.
  - Fix: additive remote listing now respects agent and uses gemini/codex remote collectors.
  - Also fixed `lsw --local -r` to respect agent for remote workspaces.
  - Added unit tests for agent propagation and remote workspace filtering.

- `lss` from Windows drive root (for example `C:\`) treated it as a workspace and returned all sessions.
  - Fix: drive-root pattern like `C--` is treated as not-in-workspace.
  - Added unit test.

- `stats` from outside any workspace returned full stats silently.
  - Fix: now errors unless a pattern, `--aw`, or `--source` is provided.
  - Added unit test and doc note.

Clarified messaging
-------------------
- WSL/Windows "no sessions" errors now say "No matching sessions" and suggest `--aw`.

Temporary directories created and deleted
----------------------------------------
- `.\\tmp-export`
- `.\\tmp-export-remote`
- `C:\\sankar\\projects\\claude-history\\tmp-export-matrix`

Targeted tests run
------------------
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "read_handles_concatenated_json"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "export_all_homes_args_includes_agent"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "scan_codex_gemini_sessions_counts_messages"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "lss_all_homes_aw_uses_all_patterns"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "collect_remotes_for_additive_passes_agent or get_remote_workspaces_for_lsw_agent_filters"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "windows_drive_root"`
- `.\.venv\Scripts\python -m pytest tests\unit\test_claude_history.py -k "stats_outside_workspace_requires_pattern"`
- `.\.venv\Scripts\python -m pytest -vv tests\unit\test_cli_combinatorial.py`

Full test suite attempts
------------------------
- `.\.venv\Scripts\python -m pytest` (timed out twice near `tests\unit\test_cli_combinatorial.py`).
