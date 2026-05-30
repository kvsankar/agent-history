# agent-history

A CLI tool to browse and export AI coding assistant conversation history with multi-environment support.

> **Note:** This tool was previously named `claude-history`. A wrapper script `claude-history` is provided for backward compatibility.

See [agent-history-process-image.md](docs/agent-history-process-image.md) for the process diagram brief.

## Supported Agents

| Agent | Status | Format | Documentation |
|-------|--------|--------|---------------|
| [Claude Code](https://github.com/anthropics/claude-code) | ✅ Full support | JSONL | [claude-code-format.md](docs/specs/agents/formats/claude-code-format.md) |
| [Codex CLI](https://github.com/openai/codex) | ✅ Full support | JSONL | [codex-cli-format.md](docs/specs/agents/formats/codex-cli-format.md) |
| [Gemini CLI](https://github.com/google-gemini/gemini-cli) | ✅ Full support | JSON | [gemini-cli-format.md](docs/specs/agents/formats/gemini-cli-format.md) |
| Pi | ✅ Full support | JSONL | [pi-format.md](docs/specs/agents/formats/pi-format.md) |

Use `--agent claude`, `--agent codex`, `--agent gemini`, `--agent pi`, or `--agent auto` (default) to select which agent's sessions to query. The `--agent` flag can appear anywhere in the command.

See [AGENTS.md](AGENTS.md) for a detailed comparison of storage locations, features, and behaviors.

## Why This Tool?

Claude Code, Codex CLI, Gemini CLI, and Pi leave conversation data fragmented across session files. This tool solves the pain points:
- Finding past work by project, not by opaque session IDs.
- Getting readable exports for sharing, backup, or audits.
- Seeing where and how you code across homes (local/WSL/Windows/SSH) with session/token/tool/time metrics.
- Surviving moves/renames with projects and “closest match” `[missing]` hints.
- Staying lightweight: a Python CLI plus a small SQLite database for metrics.

## Features

- **Markdown and offline HTML export** – Export whole workspaces or single sessions; Markdown minimal/flat/split modes; HTML renders turn-centered conversations with progressive detail controls.
- **Workspace-aware filtering** – Target workspaces by name or path (slashes ok); matches encoded names automatically.
- **Multi-environment reach** – Local, WSL (UNC or Linux paths), Windows from WSL, and SSH remotes; `[missing]` marker shows closest match for renamed workspaces.
- **Projects** – Group related workspaces across homes/sources; apply projects to `session`, `ws`, and `project` commands.
- **Usage metrics** – Summaries, homes/workspaces breakdown, token/tool stats, time tracking (with daily breakdown via `--time`), top workspaces limit via `--top-ws`.
- **Cross-home sync** – Sync metrics from all homes (`--ah`), all workspaces (`--aw`), or current workspace only (`--this`).
- **WSL/Windows helpers** – Auto-detect WSL distros/Windows users; UNC path inference for session listing without `--wsl`; converts path separators safely.
- **Claude Code skill** – Enables Claude to search your history ([SKILL.md](SKILL.md)).
- **Backend registry** – Agent-specific parsing and paths live in registered backends, keeping handlers and scope resolution agent-agnostic where practical.

## Quick Start

```bash
# Make executable
chmod +x /path/to/agent-history

# Go to your project directory
cd /path/to/project

# List sessions from current project
/path/to/agent-history session list

# Export to markdown
/path/to/agent-history session export

# Export offline HTML
/path/to/agent-history session export --format html

# Output goes to ./ai-chats/
```

**Windows:**
```powershell
cd \path\to\project
python \path\to\agent-history session list
python \path\to\agent-history session export
```

## Installation

```bash
# Download
curl -O https://raw.githubusercontent.com/kvsankar/agent-history/main/agent-history

# Install (cli + skill + retention settings)
python agent-history install
```

By default the installer:
- Copies the CLI to `~/.local/bin/agent-history` (no sudo needed).
- Installs the Claude skill into `~/.claude/skills/agent-history` (CLI + SKILL.md).
- Ensures `~/.claude/settings.json` has `cleanupPeriodDays` set to `99999` so conversations aren’t purged.
  - If the existing `settings.json` contains additional preferences, they are preserved; only `cleanupPeriodDays` is adjusted.
  - If the installer encounters malformed JSON, it first renames the original file to `settings.json.<timestamp>.bak` before writing the corrected copy.

Pass `--bin-dir`, `--skill-dir`, `--skip-cli`, `--skip-skill`, or `--skip-settings` for custom setups.

**Requirements:** Python 3.11+ and project dependencies from `pyproject.toml`.

> **Note:** Examples below assume `agent-history` is in your PATH.

## Help

<!-- help-snippet:start -->
```
usage: agent-history [-h] [--version] [--agent {auto,claude,codex,gemini,pi}] COMMAND ...

Browse and export AI coding assistant conversation history (Claude Code, Codex CLI, Gemini CLI)

positional arguments:
  COMMAND                     Command to execute
    session                   Session commands
    ws                        Workspace commands
    project                   Manage projects
    home                      Manage homes
    gemini-index              Manage Gemini session index
    install                   Install CLI and Claude skill
    reset                     Reset stored data
    fetch                     Fetch remote sessions into cache

options:
  -h, --help                  show this help message and exit
  --version                   show program's version number and exit
  --agent {auto,claude,codex,gemini,pi}
                              Agent backend to use (default: auto-detect based on available data)
```
<!-- help-snippet:end -->

## Scope Defaults by Command

| Command | Remote/Home Options | Workspace Options | Default Scope |
|---------|---------------------|-------------------|----------------|
| `session list` | `--wsl`, `--windows`, `--no-wsl`, `--no-windows`, `-r HOST`, `--ah`, `--local`, `--counts`, `--wsl-counts` | Patterns, projects (`@name` / `--project`), `--aw`, `--this` | Uses the current workspace (or its project) even when you target other homes. Pass `--aw` or explicit patterns to broaden results; `--ah` fans out to every saved home. |
| `ws list` | Same as `session list` (`--wsl`, `--windows`, `-r`, `--ah`, `--local`) | Optional patterns | Lists every workspace in the selected homes that matches your patterns (default pattern = `""`, so you see all). |
| `export` | `--wsl`, `--windows`, `-r`, `--ah`, `--local` | Targets (`export <pattern>`), projects, `--aw`, `--this` | Exports the current workspace (or project) unless you pass `--aw` or explicit targets. Running outside a workspace requires `--aw`/patterns. |
| `stats` | `--wsl`, `--windows`, `-r`, `--ah` (to sync), `--source` | Workspace patterns/projects, `--aw`, `--this` | Defaults to the current workspace (or project). If not in a workspace, pass a pattern or use `--aw`. Use `--aw` for every workspace in the metrics DB, or pass patterns/projects to filter. `--source` limits results to a specific home and defaults to all workspaces for that source unless `--this` is set. |

When in doubt: `--aw` means "all workspaces"; `--ah` means "all homes." Without those switches the CLI sticks to the current workspace/project, even if you add Windows/WSL/remote flags, so you get predictable, scoped results.

## Testing

Use pytest to run unit and integration tests. By default, `pytest` runs everything.

Quick commands:

```bash
# Default suite (excludes legacy tests)
uv run pytest

# Unit only
uv run pytest -m "not integration"

# Integration only
uv run pytest -m integration tests/integration

# Makefile shortcuts
make test
make test-unit
make test-integration

# Tests are organized by surface area:
# - tests/cli (CLI behavior and scope)
# - tests/formats (agent session formats)
# - tests/legacy (v1 script compatibility)
# - tests/unit (package internals)
# - tests/e2e_docker (Docker + SSH E2E)

# Windows PowerShell helper
scripts\run-tests.ps1              # all
scripts\run-tests.ps1 -Unit        # unit
scripts\run-tests.ps1 -Integration # integration

Notes:
- Full suite runtime can exceed 5 minutes on Windows; set CI timeouts accordingly.
```

Cross-boundary flows (optional overrides):

```powershell
# Windows simulating WSL (for tests)
set CLAUDE_WSL_TEST_DISTRO=TestWSL
set CLAUDE_WSL_PROJECTS_DIR=C:\path\to\synthetic\projects

# WSL simulating Windows
export CLAUDE_WINDOWS_PROJECTS_DIR=/mnt/c/path/to/synthetic/projects

# Isolate config/DB during tests
set USERPROFILE=C:\temp\cfg       # Windows
export HOME=/tmp/cfg               # WSL/Linux
```

### Docker E2E Tests

For testing real SSH remote operations, use the Docker-based E2E test suite:

```bash
cd docker
docker-compose up -d --build      # Start 2 SSH nodes + test runner
docker-compose run test-runner    # Run E2E tests
docker-compose down -v            # Cleanup
```

This creates containers with:
- **node-alpha**: Users alice, bob with synthetic Claude/Codex/Gemini sessions
- **node-beta**: Users charlie, dave with synthetic sessions
- **test-runner**: Executes tests with real SSH connections between nodes

See [docker/README.md](docker/README.md) for details.

CI: GitHub Actions runs unit and integration tests on `ubuntu-latest` and `windows-latest`.
Hosted Windows runners do not include WSL; WSL flows are exercised via env overrides.

## Contributing

Thanks for considering a contribution! A few quick notes to get you productive:

- Discuss: Open an issue for feature ideas or larger changes.
- Scope: Keep PRs focused; add tests that demonstrate behavior.
- Tests: Ensure both unit and integration suites pass.
  - All tests: `uv run pytest`
  - Unit only: `uv run pytest -m "not integration"`
  - Integration only: `uv run pytest -m integration tests/integration`
  - Make targets: `make test`, `make test-unit`, `make test-integration`
  - Windows helper: `scripts\\run-tests.ps1 [-Unit | -Integration]`
- Cross‑boundary flows (optional):
  - On Windows, simulate WSL: set `CLAUDE_WSL_TEST_DISTRO`, `CLAUDE_WSL_PROJECTS_DIR`
  - On WSL, simulate Windows: set `CLAUDE_WINDOWS_PROJECTS_DIR`
  - Isolate config/DB during tests: set `USERPROFILE` (Windows) or `HOME` (WSL/Linux)
- Style: Match existing patterns (stdlib only, explicit errors, platform‑safe paths).
- Commits: Use descriptive messages; include a brief rationale. Example:
  - `fix(wsl): tolerate UTF-16 BOM in distro list`

We run CI on GitHub Actions for Linux and Windows. Hosted Windows machines do not include WSL, so WSL flows are validated via the environment overrides described above.

## Additional Resources

- [Claude Collaboration Playbook](https://github.com/kvsankar/agent-history/blob/main/docs/claude-collaboration-playbook.md) – distilled lessons from hundreds of Claude Code sessions. Great to drop into your repo's `CLAUDE.md` or share with new collaborators.

## Commands

| Command | Description |
|---------|-------------|
| `home` | List homes and manage sources (WSL, Windows, SSH) |
| `ws` | List workspaces |
| `session` | List sessions |
| `session export` | Export sessions to Markdown or HTML |
| `project` | Manage workspace projects |
| `session stats` | Usage statistics |
| `reset` | Reset stored data |
| `install` | Install CLI + Claude skill and update retention settings |

## Common Examples

```bash
# List all workspaces
agent-history ws list

# Export specific project
agent-history session export myproject

# Export from all homes (local + WSL + Windows + remotes)
agent-history session export myproject --ah

# Date filtering
agent-history session list --since 2025-11-01

# Minimal export (no metadata, for sharing)
agent-history session export myproject --minimal

# Faster sync/export
agent-history session stats --sync --ah --jobs 4
agent-history session export myproject --jobs 4 --quiet

# Time tracking
agent-history session stats --time
```

## Multi-Environment Access

```bash
# Discover all Claude installations
agent-history home list

# Add homes (explicit model - must add for --ah to include)
agent-history home add --wsl              # add WSL
agent-history home add --windows          # add Windows
agent-history home add user@server        # add SSH remote
agent-history home remove user@server     # remove a source

# Access WSL (from Windows)
agent-history session list --wsl

# Access Windows (from WSL)
agent-history session list --windows

# Access SSH remote
agent-history session list -r user@server

# All homes at once (includes configured sources)
agent-history session export --ah
```

## Projects

Group related workspaces across environments:

```bash
# Add workspaces
agent-history project add myproject myproject
agent-history project add myproject --windows myproject
agent-history project add myproject -r user@vm myproject

# Use with @ prefix or --project flag
agent-history session list @myproject
agent-history session list --project myproject
agent-history session export @myproject
agent-history session export --project myproject

# Remove entries using paths from any home
agent-history project remove myproject -r user@vm /home/user/myproject
agent-history project remove myproject --windows /mnt/c/Users/me/projects/myproject
```

## Important: Preserve Your History

By default, Claude Code deletes conversation history after 30 days. Add this to `~/.claude/settings.json`:

```json
{
  "cleanupPeriodDays": 99999
}
```

## Environment Overrides

Set `CLAUDE_PROJECTS_DIR` to point the CLI at a different `.claude/projects` root. This is handy when running inside containers, CI pipelines, or when your Claude data lives on another drive:

```bash
CLAUDE_PROJECTS_DIR=/mnt/windows/Users/me/.claude/projects agent-history ws list
```

The directory must mirror Claude's standard layout (`<root>/<encoded-workspace>/*.jsonl`).

## Documentation

- **[Command Reference](docs/usage.md)** - Detailed options for all commands
- **[Cookbook](docs/cookbook.md)** - Recipes and workflows
- **[Troubleshooting](docs/troubleshooting.md)** - FAQ and common issues
- **[CLAUDE.md](CLAUDE.md)** - Development guidelines

## License

MIT License - See [LICENSE](LICENSE) file.

## Acknowledgments

- Inspired by [Simon Willison's](https://simonwillison.net/) writing on Claude conversation extraction
- Built with [Claude Code](https://claude.com/claude-code)
- Maintained with Codex (GPT-5) tooling

Related projects worth exploring:
- [ZeroSumQuant/claude-conversation-extractor](https://github.com/ZeroSumQuant/claude-conversation-extractor) – JSON→Markdown converter with a UI and filtering.
- [thejud/claude-history](https://github.com/thejud/claude-history) – simple CLI to extract/format session files.
- [raine/claude-history](https://github.com/raine/claude-history) – fuzzy-search across Claude history from the terminal.
