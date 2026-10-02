# Branch Behavior Comparison - 2026-06-01

Compared `origin/master` from `/tmp/cagelens-compare/master` against
`feature/2.0-exploration` from this worktree. Outputs are saved under
`/tmp/cagelens-compare/outputs`.

## Scope

- Local, Windows-from-WSL, and SSH remote (`sankar@ubuntuvm01`) homes.
- Project/alias, workspace, session, and home list commands.
- Agent-specific apples-to-apples checks use `--agent claude` where both CLIs
  support it.

## Fixed Regressions

- Legacy aliases were hidden when `projects.json` existed with an empty
  `projects` object. The feature branch now falls back to populated
  `aliases.json` data.
- Parent-level CLI flags could be overwritten by subcommand defaults. This
  broke shapes such as `session --windows --agent claude list ...`.
- `home list --remotes` collided with the remote-host scope destination and
  raised a bool-iteration error.
- `home list --windows` and sibling filters parsed but did not filter output.
- `ws list` loaded sessions even when counts were not requested, causing remote
  and Windows comparisons to hang or take much longer than master.
- Explicit `--agent` filters were applied after backend scans; remote/window
  scans now enumerate and collect only the requested backend.
- Remote Claude workspaces decoded dash-containing path segments incorrectly
  (`claude/history` instead of `claude-history`). Claude remote workspace
  decoding now happens on the remote host where the filesystem can preserve
  dashed segments.
- Windows Claude workspace inventory included cached remote/WSL folders as
  real workspaces. Cached workspace folders are now excluded from normal Claude
  workspace listings.
- Windows encoded workspace display fell back to `/C/...` and lost dashed path
  segments in project output. Display now prefers mounted `/mnt/<drive>/...`
  paths and verifies Windows workspaces when available.
- Session tables showed `MESSAGES=0` for skipped local counts. Skipped counts
  now render blank unless the user requests `--counts`.

## Remaining Intentional Or Deferred Differences

- Feature output uses the v2 table model with explicit `HOME`, `STATUS`, and
  ISO `MODIFIED` fields. Master output often prints bare paths or legacy home
  labels.
- `project list` is compact in v2 (one row per project) instead of expanding
  every source/workspace block like `alias list` on master.
- `home list --remotes` in v2 lists configured SSH remotes only. Master also
  displayed `windows:kvsan` under "SSH Remotes" because it came from the legacy
  sources list.
- Both branches timed out on `project/alias show cagelens` within the
  30-second comparison timeout. This is not a new feature-branch-only
  regression, but project-show performance still needs separate follow-up.
- `session list` with no matches exits `0` in v2 and exits `1` on master. This
  appears to be a v2 command-contract decision, but it is worth confirming
  before release.

## Final Matrix Summary

After fixes, core local/Windows/remote workspace and session comparisons no
longer time out. Key line-count checks:

- Remote Claude sessions for `claude-history`: master `77`, feature `77`.
- Windows Claude sessions for `claude-history`: master `64`, feature `64`.
- Remote Claude workspace for `claude-history`: both report
  `/home/sankar/sankar/projects/claude-history`.
- Windows Claude workspace for `claude-history`: both report
  `/mnt/c/sankar/projects/claude-history`.
