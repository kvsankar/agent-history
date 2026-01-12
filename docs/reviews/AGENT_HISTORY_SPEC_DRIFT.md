# agent-history spec drift review

Summary of places where the implementation in `agent-history` diverges from the written specs in `docs/specs/`. Each item notes the expected behavior from the spec, what the code currently does, and the suggested follow-up.

- Config schema mismatch for homes: spec defines `~/.agent-history/config.json` with a `homes` array that includes WSL/Windows/remote entries (`docs/specs/agent-history-spec.md:80-105`). The code initializes and persists `config.json` with a `sources` list instead, auto-importing only legacy project/alias files and never emitting a `homes` key (`agent-history:7613-7658`). Downstream helpers (e.g., `get_saved_sources`) also read `sources`, not `homes`, so the documented JSON shape does not match what the CLI writes.
- Home scope ignores explicit configuration for implicit sources: spec (now updated) says `--ah` automatically includes local + detected WSL/Windows/web + configured remotes, with opt-outs via `--no-wsl/--no-windows/--no-web`. Code matches this behavior (`agent-history:11253-11331`, `agent-history:14877-14908`), so the drift was purely documentation and has been corrected.
- Legacy CLI aliases: after recent removal, the code no longer accepts `lsw`, `workspaces`, `lss`, or `sessions` aliases. Original spec still listed only modern aliases; behavior now matches spec (doc and code aligned).

## User Inputs (Append-Only)

- Web session support must be implemented (not just documented). Current v2 code only has placeholders (`--web`, `home list` entry) with no web session backend; treat as a gap to close.
- Implement full web session support and update documentation when done.
- When remote sessions are refreshed, delete cached files that no longer exist on the remote.
- Honor `--no-wsl`, `--no-windows`, `--no-remote`, and `--no-web` flags in scope resolution.
- Implement conversation fork detection and define its impact on JSON and markdown exports.
- Include web sessions implicitly when using `--ah` (all homes).
- Distinguish encoded vs decoded workspace names in output directory naming; use dashes only when the workspace field is explicitly encoded.
- `session export` should support exporting a specific list of sessions (single or multiple session filenames/ids).
- `session stats` should always refresh to the latest data (auto-sync by default).
- Support multiple `--project` flags by combining workspaces across projects.
- `project add` should support multi-home sources (`--ah`, `--web`, `--wsl`, `--windows`, `-r user@host`) and allow selecting workspaces from those homes.
- Prefer `--by` grouping and remove legacy stats flags (`--by-day`, `--by-workspace`, `--tools`, `--models`) once `--by` fully covers the cases.
