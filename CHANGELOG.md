# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Markdown export detail levels via `--markdown-level 1..4`.
- Single-session Markdown export to stdout via `agent-history export SESSION.jsonl -o -`.
- Clearer CLI help, docs, and validation errors for stdout exports, including the
  requirement to pass exactly one full `.jsonl`/`.json` session file path.

### Changed

- Default export directory changed from `./ai-chats` to `./.agent-history/exports`.

## [2.0.0-alpha.2] - 2026-05-26

### Added

- **Offline HTML export** with turn-centered conversation rendering, light/dark mode, per-turn controls, raw views, trimmed long-output toggles, markdown rendering, syntax highlighting, and improved tool/file/diff presentation.
- **Pi coding agent support** across local, WSL, Windows, SSH, aliases, exports, stats, and unified session parsing.
- **Semantic message origin annotations** to distinguish real human input from agent/system-injected user-role messages.

### Changed

- HTML exports now prioritize conversational readability while still allowing progressive disclosure of action snippets, full tool I/O, trace data, and subagent details.
- Turn numbering is session-aware and can be renumbered consistently across combined workspace exports.
- README supported-agent documentation now includes Pi.

### Fixed

- WSL probing now treats inaccessible `wsl` command execution as unavailable instead of failing.
- Regression tests isolate Codex, Gemini, and Pi homes to avoid scanning real user history during local-only tests.
- HTML exports preserve raw text access wherever friendly rendering is applied.

## [2.0.0-alpha.1] - 2025-12-25

### Added

- **Multi-agent support**: Now supports Claude Code, Codex CLI, and Gemini CLI
  - Use `--agent claude`, `--agent codex`, `--agent gemini`, or `--agent auto` (default)
  - The `--agent` flag can appear anywhere in the command
- **Gemini hash index**: `gemini-index` command to manage hash-to-path mappings for Gemini workspaces
- **Docker E2E testing**: Infrastructure for testing real SSH remote operations
- **Coverage orchestration**: Cross-platform coverage merging (Windows + WSL + Docker)
- **CLI combinatorial tests**: Comprehensive flag combination testing
- **Type checking**: Added `ty` (Astral's Python type checker) to pre-commit hooks

### Changed

- **Renamed**: Project renamed from `claude-history` to `agent-history`
  - Wrapper script `claude-history` provided for backward compatibility
- **Config directory**: Now uses `~/.agent-history/` (migrates from `~/.claude-history/`)
- **Default export directory**: Changed from `claude-conversations` to `ai-chats`
- **Documentation**: Standardized doc filenames to lowercase

### Fixed

- Windows compatibility for wrapper script and Gemini paths
- WSL UNC path handling and normalization
- Remote Codex session scanning with correct glob patterns
- Alias operations now include Codex/Gemini sessions
- Stats scoping and WSL session listing improvements
- Agent flag propagation throughout codebase

## [1.0.0] - 2025-12-25

First stable release of claude-history (now agent-history).

### Features

- **Workspace browsing**: `lsw` to list workspaces, `lss` to list sessions
- **Markdown export**: Convert JSONL sessions to readable markdown
- **Multi-environment support**: Local, WSL, Windows, and SSH remotes
- **Workspace aliases**: Group related workspaces across environments
- **Usage statistics**: Token usage, tool stats, time tracking with `stats` command
- **Date filtering**: `--since` and `--until` flags for all commands
- **Export options**: `--minimal`, `--split`, `--flat` modes
- **Incremental export**: Only re-exports changed files
- **Install command**: Self-install CLI, Claude skill, and retention settings

### Highlights

- Single-file Python script with no external dependencies (stdlib only)
- UNIX philosophy: minimal output, tab-separated data, errors to stderr
- Full information preservation from JSONL to markdown
- Navigation links between related messages
- Agent conversation detection and labeling

[Unreleased]: https://github.com/kvsankar/agent-history/compare/v2.0.0-alpha.2...HEAD
[2.0.0-alpha.2]: https://github.com/kvsankar/agent-history/compare/v2.0.0-alpha.1...v2.0.0-alpha.2
[2.0.0-alpha.1]: https://github.com/kvsankar/agent-history/compare/v1.0...v2.0.0-alpha.1
[1.0.0]: https://github.com/kvsankar/agent-history/releases/tag/v1.0
