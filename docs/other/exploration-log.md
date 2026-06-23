Exploration Log
===============

This file captures exploratory runs performed in Windows for cagelens.
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
- `python .\cagelens lsh`
- `python .\cagelens lsh --wsl`
- `python .\cagelens lsw --ah`
- `python .\cagelens --agent codex lsw --ah`
- `python .\cagelens --agent gemini lsw --ah`
- `python .\cagelens --agent codex lss --wsl --aw`
- `python .\cagelens --agent gemini lss --wsl --aw`
- `python .\cagelens --agent gemini lss --ah --aw`
- `python .\cagelens --agent codex lss --ah --aw`
- `python .\cagelens --agent gemini lss -r user@remotehost --aw`
- `python .\cagelens stats --agent gemini --source remote:remotehost --no-sync`
- `python .\cagelens stats --agent codex --source wsl:Ubuntu --no-sync`
- `python .\cagelens stats --tools --source remote:remotehost --no-sync`
- `python .\cagelens stats --sync --ah --jobs 4 -r user@remotehost --no-windows`
- `python .\cagelens --agent gemini export --ah --aw --no-remote --quiet --jobs 4 -o .\tmp-export`
- `python .\cagelens --agent gemini export claude-history -r user@remotehost --quiet -o .\tmp-export-remote`
- `python .\cagelens --agent codex export claude-history -r user@remotehost --quiet -o .\tmp-export-remote`
- `python .\cagelens lsw --local -r user@remotehost`
- `python .\cagelens lss claude-history --wsl --aw`
- `python C:\Users\user\projects\claude-history\cagelens stats --aw --no-sync` (outside workspace)
- `python C:\Users\user\projects\claude-history\cagelens stats --source remote:remotehost --no-sync` (outside workspace)
- `python C:\Users\user\projects\claude-history\cagelens lss --aw` (from `C:\`)
- `python C:\Users\user\projects\claude-history\cagelens lsw --ah` (from `C:\`)
- `python C:\Users\user\projects\claude-history\cagelens stats --aw --no-sync` (from `C:\`)
- `python C:\Users\user\projects\claude-history\cagelens stats --source remote:remotehost --no-sync` (from `C:\`)
- `python C:\Users\user\projects\claude-history\cagelens export --aw --no-remote --quiet -o C:\Users\user\projects\claude-history\tmp-export-matrix-2` (from `C:\`)
- `python .\cagelens stats --sync --ah --jobs 4 -r user@remotehost --no-wsl`

Observations
------------
- `python C:\Users\user\projects\claude-history\cagelens lss --this` (from `C:\`) correctly errors with "Not in a Claude Code workspace."
- `python C:\Users\user\projects\claude-history\cagelens lss --ah` (from `C:\`) timed out at 30s (likely large data; no error besides timeout).
- Cross-env sanity for `claude-history` (Windows stats, `--no-sync`):
  - Codex: local 7 sessions, wsl:Ubuntu 4 sessions, remote:remotehost 3 sessions.
  - Claude: local 40 sessions, wsl:Ubuntu 98 sessions, remote:remotehost 35 sessions.
- Timing (Windows, C:\, output discarded):
  - `lss --local --aw`: ~2.6s
  - `lss --windows --aw`: ~2.7s
  - `lss --wsl --aw`: ~65s (dominant contributor to `lss --ah` timeout)
  - Fix: skip WSL message counts by default on Windows (show `?` unless `--counts`/`--wsl-counts`).
  - `lss --ah`: ~3.2s after fix (WSL counts skipped)
  - `lss --wsl --aw`: shows `?` in `MESSAGES`
  - `lss --wsl --aw --wsl-counts`: shows numeric message counts
  - `lss --ah --no-wsl`: WSL rows excluded
  - `lss --ah --no-windows`: Windows rows excluded

WSL runs (expected behavior)
----------------------------
- `./cagelens -h`
- `./cagelens lsh`
- `./cagelens lsh --wsl` (shows "No WSL distributions with agent data found")
- `./cagelens lsh --remotes` (no remotes configured)
- `./cagelens lsh --local`
- `./cagelens lsw` (with full permissions)
- `./cagelens lsw --agent claude`
- `./cagelens lsw --agent codex`
- `./cagelens lsw --agent gemini`
- `./cagelens lsw --wsl`
- `./cagelens lsw --local`
- `./cagelens lsw --windows --agent claude`
- `./cagelens lsw --ah`
- `./cagelens lsw --local -r user@remotehost`
- `./cagelens lss --agent claude`
- `./cagelens lss --agent codex`
- `./cagelens lss --agent gemini`
- `./cagelens --agent codex lss --wsl --aw`
- `./cagelens --agent gemini lss --wsl --aw`
- `./cagelens lss claude-history --wsl --aw`
- `./cagelens lss --agent codex --aw`
- `./cagelens lss --agent codex --since 2025-12-18`
- `./cagelens lss --agent codex --until 2025-12-18`
- `./cagelens lss --agent gemini --since 2025-12-04` (no sessions found as expected)
- `./cagelens lss --aw --this`
- `./cagelens lss --wsl --agent claude --this`
- `./cagelens stats --agent codex --this`
- `./cagelens stats --agent claude --this`
- `./cagelens stats --agent claude --this --time`
- `./cagelens stats --agent claude --source local --aw`
- `./cagelens stats --agent claude --source local --this`
- `./cagelens stats --agent codex --source codex --aw`
- `./cagelens stats --agent gemini --this`
- `./cagelens stats --agent claude --source windows --aw`
- `./cagelens stats --agent claude --source windows --aw --no-sync`
- `./cagelens stats --agent claude --source remote:remotehost --aw --no-sync`
- `./cagelens stats --agent claude --source wsl:Ubuntu --aw --no-sync` (0 sessions, expected with no `wsl:Ubuntu` sources)
- `./cagelens stats --agent claude --source windows:kvsan --aw --no-sync`
- `./cagelens stats --agent gemini --source remote:remotehost --no-sync`
- `./cagelens stats --agent codex --source wsl:Ubuntu --no-sync`
- `./cagelens stats --tools --source remote:remotehost --no-sync`
- `./cagelens stats --tools --source wsl --aw --no-sync`
- `./cagelens stats --models --source wsl --aw --no-sync`
- `./cagelens stats --agent codex --source remote:remotehost --aw --no-sync` (0 sessions; no remote sync yet)
- `./cagelens stats --sync --agent codex --source remote:remotehost --aw` (syncs local only without `-r`)
- `./cagelens stats --sync -r user@remotehost --agent codex --source remote:remotehost --aw`
- `./cagelens stats --sync --ah --jobs 4 -r user@remotehost --no-windows`
- `./cagelens stats --sync --ah --jobs 4 -r user@remotehost --no-wsl`
- `./cagelens stats --agent codex --source remote:remotehost --aw --no-sync` (after sync)
- `./cagelens stats --by-day --source wsl --aw --no-sync`
- `./cagelens stats --by-workspace --source wsl --aw --no-sync`
- `./cagelens stats --time --source wsl --aw --no-sync`
- `./cagelens stats --by-day --source windows --aw --no-sync`
- `./cagelens stats --by-workspace --source windows --aw --no-sync`
- `./cagelens stats --time --source windows --aw --no-sync`
- `./cagelens stats --by-day --source remote:remotehost --aw --no-sync`
- `./cagelens stats --by-workspace --source remote:remotehost --aw --no-sync`
- `./cagelens stats --time --source remote:remotehost --aw --no-sync`
- `./cagelens export --by-day --source wsl --aw --no-sync` (expected error: unsupported flags)
- `./cagelens stats --by-day --source wsl --this --no-sync`
- `./cagelens lss --alias claude-history`
- `./cagelens export --alias claude-history --quiet -o /tmp/<temp>` (timed out at 20s; temp dir deleted)
- `./cagelens export --alias claude-history --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens lss --alias claude-history --agent codex`
- `./cagelens lsw claude-history`
- `./cagelens stats --by-workspace --source wsl --this --no-sync`
- `./cagelens stats --by-day --source windows --this --no-sync`
- `./cagelens stats --by-day --source remote:remotehost --this --no-sync`
- `./cagelens lss --alias claude-history --wsl --agent claude` (no sessions; alias has no WSL entries)
- `./cagelens lss --alias claude-history --windows --agent claude`
- `./cagelens export --alias claude-history --windows --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --alias claude-history --wsl --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no WSL entries)
- `./cagelens lss --alias claude-history --local --agent claude` (piped to `head`; BrokenPipeError on stdout flush)
- `./cagelens stats --agent codex --source windows --aw --no-sync`
- `./cagelens lss --alias claude-history -r user@remotehost --agent claude`
- `./cagelens export --alias claude-history -r user@remotehost --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no remote entries in range)
- `./cagelens stats --agent codex --source windows --this --no-sync`
- `./cagelens stats --agent gemini --source windows --this --no-sync` (no sessions)
- `./cagelens stats --agent gemini --source remote:remotehost --this --no-sync`
- `./cagelens lss --alias claude-history --agent gemini`
- `./cagelens stats --agent claude --source windows --this --no-sync`
- `./cagelens stats --agent codex --source wsl --this --no-sync`
- `./cagelens stats --agent gemini --source wsl --this --no-sync`
- `./cagelens lss --alias claude-history --windows --agent codex --since 2025-12-18`
- `./cagelens stats --agent codex --source remote:remotehost --this --no-sync`
- `./cagelens lss //wsl$/Ubuntu/home/user/projects/claude-history --agent claude`
- `./cagelens stats --alias claude-history --agent gemini --source wsl --by-day` (expected error: `--alias` not supported for stats)
- `./cagelens stats @claude-history --agent gemini --source wsl --by-day`
- `./cagelens stats @claude-history --agent gemini --source windows --by-day`
- `./cagelens stats @claude-history --agent codex --source wsl --by-day`
- `./cagelens lsw //wsl$/Ubuntu/home/user/projects/claude-history --agent claude`
- `./cagelens lss @claude-history --agent codex --wsl` (no sessions found)
- `./cagelens lss @claude-history --agent codex`
- `./cagelens lss @claude-history --agent codex --windows`
- `./cagelens lsw claude-history --agent codex`
- `./cagelens lsw claude-history --agent codex --windows`
- `./cagelens lsw claude-history --agent codex --wsl`
- `./cagelens lss --alias claude-history --local --agent codex`
- `./cagelens lss --alias claude-history -r user@remotehost --agent codex`
- `./cagelens stats @claude-history --source wsl --no-sync`
- `./cagelens stats @claude-history --source windows --no-sync`
- `./cagelens stats @claude-history --source remote:remotehost --no-sync`
- `./cagelens stats @claude-history --source windows --agent codex --no-sync`
- `./cagelens stats @claude-history --agent codex --source windows --by-workspace`
- `./cagelens stats @claude-history --agent codex --source windows --by-workspace --no-sync`
- `./cagelens stats @claude-history --agent codex --source remote:remotehost --by-workspace -r user@remotehost`
- `./cagelens stats @claude-history --agent codex --source remote:remotehost --by-workspace --no-sync`
- `./cagelens stats @claude-history --agent codex --source wsl --by-workspace`
- `./cagelens stats @claude-history --agent gemini --source windows --by-workspace`
- `./cagelens stats @claude-history --agent gemini --source wsl --by-workspace`
- `./cagelens stats @claude-history --agent gemini --source remote:remotehost --by-workspace -r user@remotehost`
- `./cagelens stats @claude-history --agent gemini --source remote:remotehost --by-workspace --no-sync`
- `./cagelens stats @claude-history --agent codex --tools --source wsl`
- `./cagelens stats @claude-history --agent gemini --models --source wsl`
- `./cagelens stats @claude-history --agent codex --time --source windows --no-sync`
- `./cagelens lsw --agent codex --ah --aw` (expected error: `--aw` not supported)
- `./cagelens lsw --agent codex --ah`
- `./cagelens lsw --agent gemini --ah`
- `./cagelens lsw --agent gemini --windows`
- `./cagelens lss @claude-history --agent gemini --local -r user@remotehost`
- `./cagelens lss @claude-history --agent codex --local -r user@remotehost`
- `./cagelens export --alias claude-history --flat --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --alias claude-history --split 200 --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --alias claude-history --windows --flat --since 2025-12-18 --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --alias claude-history -r user@remotehost --flat --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no remote entries in range)
- `./cagelens export --alias claude-history --wsl --flat --since 2025-12-18 --quiet -o /tmp/<temp>` (no output; no WSL entries)
- `./cagelens export --alias claude-history --agent codex --since 2025-12-18 --quiet -o /tmp/<temp>` (permission error on codex index; fixed later)
- `./cagelens export --alias claude-history --agent codex --flat --since 2025-12-18 --quiet -o /tmp/<temp>` (no output before fix)
- `./cagelens export --alias claude-history --agent gemini --since 2025-12-01 --quiet -o /tmp/<temp>` (no output; no entries in range)
- `./cagelens export --alias claude-history --agent codex --since 2025-12-18 --quiet -o /tmp/<temp>` (after fix: 5 exported)
- `./cagelens export --agent codex --aw --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent codex --ah --aw --quiet -o /tmp/<temp>` (export-all summary printed)
- `./cagelens export --agent codex --ah --aw --no-wsl --quiet -o /tmp/<temp>` (unexpected: Windows still included; fixed later)
- `./cagelens export --agent codex --ah --aw --no-windows --quiet -o /tmp/<temp>` (unexpected: Windows still included; fixed later)
- `./cagelens export --agent gemini --aw --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent gemini --ah --aw --quiet -o /tmp/<temp>` (export-all summary printed)
- `./cagelens export claude-history --agent codex --windows --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export claude-history --agent codex --wsl --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export claude-history --agent codex -r user@remotehost --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export claude-history --agent gemini -r user@remotehost --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent gemini --ah --aw --no-remote --quiet --jobs 4 -o /tmp/<temp>` (export-all summary printed)
- `./cagelens export --aw --no-remote --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent gemini --source remote:remotehost --quiet -o /tmp/<temp>` (expected error: `--source` not supported for export)
- `./cagelens export @claude-history --agent gemini --windows --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export claude-history --agent codex --split 200 --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export claude-history --agent gemini --minimal --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent codex --ah --aw --no-windows --quiet -o /tmp/<temp>` (after fix: Windows skipped)
- `./cagelens export --agent gemini --ah --aw --no-windows --quiet -o /tmp/<temp>` (after fix: Windows skipped)
- `./cagelens export --agent codex --ah --aw --no-remote -r user@remotehost --quiet -o /tmp/<temp>` (warns; remotes skipped)
- `./cagelens export --agent codex --this --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --agent gemini --this --quiet -o /tmp/<temp>` (no output; quiet mode)
- `./cagelens export --minimal -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens lss` (auto agent mode)
- `./cagelens lsh --wsl --agent claude` (after fix)
- `./cagelens lsh --agent codex`
- `./cagelens lsh --agent gemini`
- `./cagelens lsh --windows`
- `./cagelens lss --windows --agent claude --this` (after fix)
- `./cagelens lss --windows --agent codex --this`
- `./cagelens lss --windows --agent gemini --this` (no sessions found as expected)
- `./cagelens lss --agent codex --this`
- `./cagelens lss --agent gemini --this`
- `./cagelens lsw --windows --agent codex`
- `./cagelens lss --agent codex --counts`
- `./cagelens lss --agent gemini --counts`
- `./cagelens stats --agent codex --source windows --aw --no-sync`
- `./cagelens stats --agent codex --source windows --aw --sync`
- `/home/user/projects/claude-history/cagelens stats --aw --no-sync` (from `/`)
- `/home/user/projects/claude-history/cagelens stats --source remote:remotehost --no-sync` (from `/`)
- `./cagelens lss --wsl --agent codex`
- `./cagelens lss --wsl --agent gemini`
- `./cagelens lss --wsl --agent codex --since 2025-12-18`
- `./cagelens lss --wsl --agent codex --until 2025-12-18`
- `./cagelens lss --wsl --agent gemini --until 2025-12-09`
- `./cagelens lsh --windows --agent codex`
- `./cagelens lsh --windows --agent gemini`
- `./cagelens lsh --windows --agent claude`
- `./cagelens lsw --windows --agent gemini` (hash-only paths shown)
- `./cagelens export --windows --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --windows --agent gemini --aw --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --windows --agent claude --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens lss --agent codex --ah --aw`
- `./cagelens lss --agent gemini --ah --aw`
- `./cagelens lss --windows --agent codex --aw`
- `./cagelens lss --windows --agent gemini --aw`
- `./cagelens lss --windows --this`
- `./cagelens lss --windows --agent codex --since 2025-12-18 --aw`
- `./cagelens lss --windows --agent codex --until 2025-12-18 --aw`
- `./cagelens stats --agent gemini --source windows --aw --no-sync`
- `./cagelens stats --agent gemini --source windows --aw --sync`
- `./cagelens stats --sync --ah --agent codex --source windows --aw`
- `./cagelens stats --agent codex --source windows --aw --no-sync` (after fix)
- `./cagelens stats --agent gemini --source windows --aw --no-sync` (after fix)
- `./cagelens lss --wsl --agent codex --this`
- `./cagelens lss --wsl --agent gemini --this`
- `./cagelens stats --agent codex --source wsl --aw --no-sync`
- `./cagelens stats --agent gemini --source wsl --aw --no-sync`
- `./cagelens stats --agent claude --source wsl --aw --no-sync`
- `./cagelens stats --sync --ah --agent codex --source wsl --aw` (initial run timed out at 10s; reran with longer timeout)
- `./cagelens export --wsl --agent gemini --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --flat --wsl --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens export --wsl --agent claude --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens lss -r user@remotehost --aw`
- `./cagelens lss -r user@remotehost --aw --agent codex`
- `./cagelens export -r user@remotehost --agent codex --this --quiet -o /tmp/<temp>` (temp dir created and deleted)
- `./cagelens lss -r user@remotehost --local --this --agent codex`
- `uv run pytest tests/unit/test_claude_history.py -k "agent_flag_after_subcommand or windows_this_only"`
- `python3 /home/user/projects/claude-history/cagelens lss --aw` (from `/`)
- `python3 /home/user/projects/claude-history/cagelens lsw --ah` (from `/`)
- `python3 /home/user/projects/claude-history/cagelens stats --aw --no-sync` (from `/`)
- `python3 /home/user/projects/claude-history/cagelens stats --source remote:remotehost --no-sync` (from `/`)
- `python3 ./cagelens stats --sync`
- `python3 /home/user/projects/claude-history/cagelens export --aw --no-remote --quiet -o /tmp/cagelens-export-matrix` (from `/`)

Observations
------------
- `python3 /home/user/projects/claude-history/cagelens lss --this` (from `/`) correctly errors with "Not in a Claude Code workspace."
- `stats` does not accept `--alias`; use `stats @alias` instead.
- `./cagelens stats --aw --no-sync` (from `/`) fails because the relative path isn't available; use the absolute path instead.
- WSL export emitted: `Warning: Couldn't parse line in 2c4ad1bc-7ce9-405c-9b8c-d369178c901e.jsonl: Extra data: line 1 column 2 (char 1)` (left data unchanged).
  - Root cause: file contains a stray fragment line (`0,"cache_creation":...` at line 576) following a valid JSON line.
  - Fix: suppress warnings for non-JSON fragments and honor `--quiet`.

Ubuntu (remote)
---------------

Successful runs (expected behavior)
- `python3 ./cagelens lsh`
- `python3 ./cagelens lsw --ah`
- `python3 ./cagelens --agent codex lss --aw`
- `python3 ./cagelens --agent gemini lss --aw`
- `python3 /home/user/projects/claude-history/cagelens stats --no-sync` from `/` (expected error because no DB)
- `python3 /home/user/projects/claude-history/cagelens lss --aw` (from `/`)
- `python3 /home/user/projects/claude-history/cagelens lsw --ah` (from `/`)
- `python3 /home/user/projects/claude-history/cagelens stats --aw --no-sync` (from `/`)
- `python3 ./cagelens stats --sync`
- `python3 /home/user/projects/claude-history/cagelens export --aw --no-remote --quiet -o /tmp/cagelens-export-matrix` (from `/`)

Observations
------------
- `python3 /home/user/projects/claude-history/cagelens lss --this` (from `/`) correctly errors with "Not in a Claude Code workspace."

Unexpected behavior and fixes
-----------------------------
- `stats --agent gemini --source remote:remotehost` returned 0 sessions because it scoped to the current workspace when no pattern was provided.
  - Fix: `stats --source` now defaults to all workspaces for that source unless `--this` is set.
  - Added unit test and doc note.
- `uv run pytest tests/unit/test_claude_history.py -k "alias_export_uses_non_claude_sessions"` failed with `Permission denied` on `~/.cache/uv/sdists-v9/.git`.
  - Workaround: reran with `UV_NO_CACHE=1`.

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
- `export --alias <name> --agent codex|gemini` produced no output.
  - Fix: alias export now collects non-Claude sessions and uses agent-aware parsing during export.
- `export --alias <name> --agent codex` failed with `Permission denied` on `~/.cagelens/codex_index.json`.
  - Fix: Codex index writes now ignore permission errors and continue without aborting.
- `lss //wsl$/...` in WSL tried to use a Windows UNC projects dir and errored.
  - Fix: when running in WSL, UNC inputs now resolve to `/home/<user>/.claude/projects`.
- `export --ah --aw --no-windows` still exported Windows sessions.
  - Root cause: `_dispatch_export_all_homes` dropped `--no-wsl/--no-windows/--no-remote` flags from `ExportAllConfig`.
  - Fix: propagate those flags into `ExportAllConfig` so `cmd_export_all` respects them.

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
- `C:\\Users\\user\\projects\\claude-history\\tmp-export-matrix`
- `C:\\Users\\user\\projects\\claude-history\\tmp-export-matrix-2`
- `/tmp/cagelens-export-matrix` (WSL and remote)
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
- `UV_NO_CACHE=1 uv run pytest tests/unit/test_claude_history.py -k "alias_export_uses_non_claude_sessions"`
- `UV_NO_CACHE=1 uv run pytest tests/unit/test_claude_history.py -k "save_index_permission_error"`
- `uv run pytest tests/unit/test_claude_history.py -k "projects_dir_from_wsl_unc_in_wsl"`
- `uv run pytest tests/unit/test_claude_history.py -k "export_all_homes_args_includes_agent"`

Full test suite attempts
------------------------
- `.\.venv\Scripts\python -m pytest` (timed out twice near `tests\unit\test_cli_combinatorial.py`).
