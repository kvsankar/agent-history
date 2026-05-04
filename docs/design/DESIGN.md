# Design Overview

This document explains the architecture and data flow of `agent-history`.

## Goals

- Provide a single CLI to browse, export, and analyze AI coding sessions.
- Support Claude Code, Codex CLI, and Gemini CLI across local, WSL, Windows, and SSH.
- Keep reads safe and non-destructive; never modify raw agent data.
- Favor predictable scope rules with orthogonal flags (`--ah`, `--aw`, `--this`).

## Non-Goals

- Live editing of session data.
- Real-time streaming of agent output.
- Rewriting source history in place.

## High-Level Architecture

`agent-history` is a single-file Python CLI with these layers:

1. **Argument parsing**: Defines commands and flags, normalizes scope rules.
2. **Source discovery**: Finds local/WSL/Windows/SSH homes and workspaces.
3. **Session collection**: Resolves patterns to session files and metadata.
4. **Action pipelines**: Export or stats flows that operate on sessions.
5. **Storage**: SQLite metrics DB and lightweight JSON config files.

## Data Sources and Formats

Supported agents:
- Claude Code: JSONL files under `~/.claude/projects/`.
- Codex CLI: JSONL files under `~/.codex/sessions/`.
- Gemini CLI: JSON files under `~/.gemini/tmp/<hash>/`.

Agent detection:
- Path-based detection for `.claude`, `.codex`, `.gemini`.
- Cached remote folders (`remote_*`, `wsl_*`) are recognized for routing and filtering.

## Workspace and Session Resolution

Key steps:
- **Workspace naming**: Claude uses encoded workspace paths; Codex uses `cwd` metadata;
  Gemini uses SHA-256 hashes with an index for path resolution.
- **Pattern matching**: Workspace patterns are applied across selected sources.
- **Deduplication**: Session lists are deduplicated by file path to avoid duplicates
  when multiple patterns overlap.

## Scope Model

Two orthogonal dimensions:
- **Workspace scope**: current workspace or alias, `--aw`, explicit patterns, `--this`.
- **Source scope**: local, WSL, Windows, SSH, `--ah` (all homes).

This ensures predictable behavior:
- `--aw` only changes workspace scope.
- `--ah` only expands sources.
- `--this` overrides alias scoping.

## Export Pipeline

1. Resolve sources and workspace scope.
2. Collect sessions (with dedup and optional date filters).
3. For each session:
   - Read messages once (agent-specific parsing).
   - Build output path (flat or workspace-organized).
   - Skip if output is up to date (unless `--force`).
   - Write markdown (full or `--minimal`).
   - Optionally split long conversations (`--split`).

Concurrency:
- `--jobs` parallelizes per-session exports.
- `--quiet` suppresses per-file output.
- Periodic progress output is printed for long runs.

## Stats Pipeline

1. Optional sync step (`--sync` or `--ah` auto-sync):
   - Scan sources and insert session metrics into SQLite.
   - Incremental by default; `--force` ignores mtimes.
   - `--jobs` parallelizes remote sync.
2. Query and render:
   - Summary dashboard and breakdowns (`--by tool`, `--by model`, `--by day`).
   - Filters (`--source`, `--since`, `--until`).

## Remote and Cross-OS Access

- **SSH remotes**: Use rsync/scp for fetch or direct access (list vs export).
- **Windows from WSL**: Access via `/mnt/c/Users/<user>`.
- **WSL from Windows**: Access via `\\wsl.localhost\<distro>\...`.
- Cache paths for remote exports are prefixed to avoid collisions.
- Cached workspaces (`remote_*`, `wsl_*`) are filtered to prevent circular sync.

## Configuration and Storage

User config lives under `~/.agent-history/`:
- `metrics.db`: SQLite database for stats and time tracking.
- `config.json`: saved SSH remotes and settings.
- `aliases.json`: workspace alias definitions.
- `gemini_hash_index.json`: hash to path mappings for Gemini.
- On first run, any legacy `~/.claude-history/` directory is migrated to this location and cleaned up.

## Error Handling and Resilience

- Missing sources surface actionable messages.
- Remote connection failures are handled per source.
- Empty matches are non-fatal in `--ah` mode (lenient exports).
- Output directories are created as needed.

## Performance Notes

- Incremental export skips unchanged files by mtime.
- `--jobs` enables parallel processing for large exports and remote sync.
- Date filters reduce scanning and export scope.
