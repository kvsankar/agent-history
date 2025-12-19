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

Windows
-------

Successful runs (expected behavior)
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

WSL runs (expected behavior)
----------------------------
- `./agent-history -h`
- `./agent-history lsh`
- `./agent-history lsh --wsl` (shows "No WSL distributions with agent data found")
- `./agent-history lsh --remotes` (no remotes configured)
- `./agent-history lsh --local`
- `./agent-history lsw` (with full permissions)
- `./agent-history lsw --agent claude`
- `./agent-history lsw --agent codex`
- `./agent-history lsw --agent gemini`
- `./agent-history lsw --wsl`
- `./agent-history lsw --local`
- `./agent-history lsw --windows --agent claude`
- `./agent-history lss --agent claude`
- `./agent-history lss --agent codex`
- `./agent-history lss --agent gemini`
- `./agent-history lss --agent codex --aw`
- `./agent-history lss --agent codex --since 2025-12-18`
- `./agent-history lss --agent codex --until 2025-12-18`
- `./agent-history lss --agent gemini --since 2025-12-04` (no sessions found as expected)
- `./agent-history lss --aw --this`
- `./agent-history lss --wsl --agent claude --this`
- `./agent-history stats --agent codex --this`
- `./agent-history stats --agent claude --this`
- `./agent-history stats --agent claude --this --time`
- `./agent-history stats --agent claude --source local --aw`
- `./agent-history stats --agent claude --source local --this`
- `./agent-history stats --agent codex --source codex --aw`
- `./agent-history stats --agent gemini --this`
- `./agent-history stats --agent claude --source windows --aw`
- `./agent-history stats --agent claude --source windows --aw --no-sync`
- `./agent-history stats --agent claude --source remote:ubuntuvm01 --aw --no-sync`
- `./agent-history stats --agent claude --source wsl:Ubuntu --aw --no-sync` (0 sessions, expected with no `wsl:Ubuntu` sources)
- `./agent-history stats --agent claude --source windows:kvsan --aw --no-sync`
- `./agent-history stats --tools --source wsl --aw --no-sync`
- `./agent-history stats --models --source wsl --aw --no-sync`
- `./agent-history stats --agent codex --source remote:ubuntuvm01 --aw --no-sync` (0 sessions; no remote sync yet)
- `./agent-history stats --sync --agent codex --source remote:ubuntuvm01 --aw` (syncs local only without `-r`)
- `./agent-history stats --sync -r sankar@ubuntuvm01 --agent codex --source remote:ubuntuvm01 --aw`
- `./agent-history stats --agent codex --source remote:ubuntuvm01 --aw --no-sync` (after sync)
- `./agent-history stats --by-day --source wsl --aw --no-sync`
- `./agent-history stats --by-workspace --source wsl --aw --no-sync`
- `./agent-history stats --time --source wsl --aw --no-sync`
- `./agent-history stats --by-day --source windows --aw --no-sync`
- `./agent-history stats --by-workspace --source windows --aw --no-sync`
- `./agent-history stats --time --source windows --aw --no-sync`
- `./agent-history stats --by-day --source remote:ubuntuvm01 --aw --no-sync`
- `./agent-history stats --by-workspace --source remote:ubuntuvm01 --aw --no-sync`
- `./agent-history stats --time --source remote:ubuntuvm01 --aw --no-sync`
- `./agent-history export --by-day --source wsl --aw --no-sync` (expected error: unsupported flags)
- `./agent-history stats --by-day --source wsl --this --no-sync`
- `./agent-history lss --alias claude-history`
- `./agent-history export --alias claude-history --quiet -o /tmp/<temp>` (timed out at 20s; temp dir deleted)
- `./agent-history export --alias claude-history --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history lss --alias claude-history --agent codex`
- `./agent-history lsw claude-history`
- `./agent-history stats --by-workspace --source wsl --this --no-sync`
- `./agent-history stats --by-day --source windows --this --no-sync`
- `./agent-history stats --by-day --source remote:ubuntuvm01 --this --no-sync`
- `./agent-history lss --alias claude-history --wsl --agent claude` (no sessions; alias has no WSL entries)
- `./agent-history lss --alias claude-history --windows --agent claude`
- `./agent-history export --alias claude-history --windows --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history export --alias claude-history --wsl --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no WSL entries)
- `./agent-history lss --alias claude-history --local --agent claude` (piped to `head`; BrokenPipeError on stdout flush)
- `./agent-history stats --agent codex --source windows --aw --no-sync`
- `./agent-history lss --alias claude-history -r sankar@ubuntuvm01 --agent claude`
- `./agent-history export --alias claude-history -r sankar@ubuntuvm01 --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no remote entries in range)
- `./agent-history stats --agent codex --source windows --this --no-sync`
- `./agent-history stats --agent gemini --source windows --this --no-sync` (no sessions)
- `./agent-history stats --agent gemini --source remote:ubuntuvm01 --this --no-sync`
- `./agent-history lss --alias claude-history --agent gemini`
- `./agent-history stats --agent claude --source windows --this --no-sync`
- `./agent-history stats --agent codex --source wsl --this --no-sync`
- `./agent-history stats --agent gemini --source wsl --this --no-sync`
- `./agent-history lss --alias claude-history --windows --agent codex --since 2025-12-18`
- `./agent-history stats --agent codex --source remote:ubuntuvm01 --this --no-sync`
- `./agent-history lss --alias claude-history --local --agent codex`
- `./agent-history lss --alias claude-history -r sankar@ubuntuvm01 --agent codex`
- `./agent-history export --minimal -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history lss` (auto agent mode)
- `./agent-history lsh --wsl --agent claude` (after fix)
- `./agent-history lss --windows --agent claude --this` (after fix)
- `./agent-history lss --windows --agent codex --this`
- `./agent-history lss --windows --agent gemini --this` (no sessions found as expected)
- `./agent-history lsw --windows --agent codex`
- `./agent-history stats --agent codex --source windows --aw --no-sync`
- `./agent-history stats --agent codex --source windows --aw --sync`
- `./agent-history lss --wsl --agent codex`
- `./agent-history lss --wsl --agent gemini`
- `./agent-history lss --wsl --agent codex --since 2025-12-18`
- `./agent-history lss --wsl --agent codex --until 2025-12-18`
- `./agent-history lss --wsl --agent gemini --until 2025-12-09`
- `./agent-history lsh --windows --agent codex`
- `./agent-history lsh --windows --agent gemini`
- `./agent-history lsh --windows --agent claude`
- `./agent-history lsw --windows --agent gemini` (hash-only paths shown)
- `./agent-history export --windows --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history export --windows --agent gemini --aw --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history export --windows --agent claude --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history lss --agent codex --ah --aw`
- `./agent-history lss --agent gemini --ah --aw`
- `./agent-history lss --windows --agent codex --aw`
- `./agent-history lss --windows --agent gemini --aw`
- `./agent-history lss --windows --this`
- `./agent-history lss --windows --agent codex --since 2025-12-18 --aw`
- `./agent-history lss --windows --agent codex --until 2025-12-18 --aw`
- `./agent-history stats --agent gemini --source windows --aw --no-sync`
- `./agent-history stats --agent gemini --source windows --aw --sync`
- `./agent-history stats --sync --ah --agent codex --source windows --aw`
- `./agent-history stats --agent codex --source windows --aw --no-sync` (after fix)
- `./agent-history stats --agent gemini --source windows --aw --no-sync` (after fix)
- `./agent-history lss --wsl --agent codex --this`
- `./agent-history lss --wsl --agent gemini --this`
- `./agent-history stats --agent codex --source wsl --aw --no-sync`
- `./agent-history stats --agent gemini --source wsl --aw --no-sync`
- `./agent-history stats --agent claude --source wsl --aw --no-sync`
- `./agent-history stats --sync --ah --agent codex --source wsl --aw` (initial run timed out at 10s; reran with longer timeout)
- `./agent-history export --wsl --agent gemini --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history export --flat --wsl --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history export --wsl --agent claude --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history lss -r sankar@ubuntuvm01 --aw`
- `./agent-history lss -r sankar@ubuntuvm01 --aw --agent codex`
- `./agent-history export -r sankar@ubuntuvm01 --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./agent-history lss -r sankar@ubuntuvm01 --local --this --agent codex`
- `uv run pytest tests/unit/test_claude_history.py -k "agent_flag_after_subcommand or windows_this_only"`

Ubuntu (remote)
---------------

Successful runs (expected behavior)
- `python3 ./agent-history lsh`
- `python3 ./agent-history lsw --ah`
- `python3 ./agent-history --agent codex lss --aw`
- `python3 ./agent-history --agent gemini lss --aw`
- `python3 /home/sankar/sankar/projects/claude-history/agent-history stats --no-sync` from `/` (expected error because no DB)

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
- `stats --no-sync` from `/` inside WSL still returns full stats instead of erroring.
  - Fix: treat empty workspace patterns (root path) as not-in-workspace.
  - Added unit test to lock the behavior.

WSL-specific issues and fixes
-----------------------------
- `lss --windows --agent claude --this` returned no sessions even though the Windows mirror of the current workspace existed.
  - Fix: `--this` now infers patterns from cwd/repo name when targeting Windows/WSL sources instead of using only Claude-encoded paths.
  - Added unit test for Windows `--this` inference.
- `lsh --wsl --agent claude` failed to parse because `--agent` was only accepted before the subcommand.
  - Fix: `--agent` can now appear anywhere in the command line (pre-parsed and applied as an override).
  - Added unit test for `--agent` placement.
- `lsh --wsl` produced no output when no WSL distros were detected.
  - Fix: always emit the WSL section and print "No WSL distributions with agent data found".
- `lss --agent codex --ah --aw` showed Windows rows with WSL paths.
  - Fix: Windows collection now scans Codex sessions from Windows session directories.
- `lss --agent gemini --ah --aw` showed Windows rows with WSL paths.
  - Fix: Windows collection now scans Gemini sessions from Windows session directories (hash-based workspaces preserved).
- `stats --agent codex|gemini --source windows --aw --sync` synced but `--no-sync` still showed 0 sessions.
  - Fix: `--source windows|wsl|remote` now matches `windows:*`/`wsl:*`/`remote:*` sources in stats filtering.
- `stats --agent codex|gemini --source wsl --aw --no-sync` returned 0 sessions in WSL.
  - Fix: when running in WSL, `--source wsl` also includes `local`, `codex`, and `gemini` sources in stats filtering.
- `lss -r <host> --agent codex --aw` showed Codex workspaces as basenames (for example `claude-history`) instead of full paths.
  - Fix: remote Codex session listing now uses the full `cwd` as `workspace_readable` (matching local Codex output).
- `export --alias <name> --quiet` still printed per-file output.
  - Fix: alias export now honors `--quiet` and suppresses per-file output.
- `lss --alias <name> --wsl` ignored the source flags and still listed non-WSL entries.
  - Fix: alias listing/export now filters alias sources by `--local`, `--wsl`, `--windows`, and `-r`.
- `lss --alias <name> --windows --agent codex` returned zero message counts.
  - Fix: alias Codex/Gemini scans now include message counts for Windows/WSL sources.

WSL-specific issues (unfixed)
-----------------------------
- `stats --sync --source windows --aw` still requires `--ah` to sync Windows sources (by design); without `--ah` only local sources are synced.
  - Potential fix: allow `--sync` to respect explicit `--source windows|wsl|remote:*` without requiring `--ah`.

Clarified messaging
-------------------
- WSL/Windows "no sessions" errors now say "No matching sessions" and suggest `--aw`.

Temporary directories created and deleted
----------------------------------------
- `.\\tmp-export`
- `.\\tmp-export-remote`
- `C:\\sankar\\projects\\claude-history\\tmp-export-matrix`
- `/tmp/<temp>`

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
- `uv run pytest tests/unit/test_claude_history.py -k "stats_source_wsl_includes_local_when_in_wsl"`
- `uv run pytest tests/unit/test_claude_history.py -k "collect_remote_codex_with_sessions"`
- `uv run pytest tests/unit/test_claude_history.py -k "get_alias_export_options"`
- `uv run pytest tests/unit/test_claude_history.py -k "filter_alias_config_by_flags_wsl"`
- `uv run pytest tests/unit/test_claude_history.py -k "collect_non_claude_alias_sessions_windows_only"`
- `uv run pytest tests/unit/test_claude_history.py -k "collect_non_claude_alias_sessions_windows_default_user"`

Full test suite attempts
------------------------
- `.\.venv\Scripts\python -m pytest` (timed out twice near `tests\unit\test_cli_combinatorial.py`).
