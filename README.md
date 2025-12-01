# claude-history

A CLI tool to browse and export Claude Code conversation history with multi-environment support.

Claude Code stores your conversations locally, but accessing them for analysis, searching past solutions, or tracking usage patterns requires parsing JSONL files scattered across project directories. This tool makes that data accessible through a simple command-line interface.

## Features

- **Markdown export** - Export conversations to readable markdown files with optional size control
- **Workspace filtering** - Export by project, not just session IDs
- **Multi-environment** - Access local, WSL, Windows, and SSH remotes
- **Workspace aliases** - Group related workspaces across platforms
- **Usage metrics** - Track time spent, tokens used, tool usage
- **Claude Code skill** - Enable Claude to search your conversation history ([SKILL.md](SKILL.md))
- **Zero dependencies** - Single Python file, stdlib only

## Quick Start

```bash
# Make executable
chmod +x claude-history

# List sessions from current project
./claude-history lss

# Export to markdown
./claude-history export

# Output goes to ./claude-conversations/
```

**Windows:**
```powershell
python claude-history lss
python claude-history export
```

## Installation

```bash
# Download
curl -O https://raw.githubusercontent.com/kvsankar/claude-history/main/claude-history
chmod +x claude-history

# Optional: add to PATH
sudo mv claude-history /usr/local/bin/
```

**Requirements:** Python 3.6+ (stdlib only, no pip install needed)

## Help

```
$ claude-history --help
usage: claude-history [-h] [--version]
                      {lsw,lss,lsh,export,alias,stats,reset} ...

Browse and export Claude Code conversation history

positional arguments:
  {lsw,lss,lsh,export,alias,stats,reset}
                        Command to execute
    lsw                 List workspaces
    lss                 List sessions
    lsh                 List hosts and manage SSH remotes
    export              Export to markdown
    alias               Manage workspace aliases
    stats               Show usage statistics and metrics
    reset               Reset stored data (database, settings, aliases)

options:
  -h, --help            show this help message and exit
  --version             show program's version number and exit

EXAMPLES:

  List workspaces:
    claude-history lsw                        # all local workspaces
    claude-history lsw myproject              # filter by pattern
    claude-history lsw -r user@server         # remote workspaces

  List sessions:
    claude-history lss                        # current workspace
    claude-history lss myproject              # specific workspace
    claude-history lss myproject -r user@server    # remote sessions

  Export (unified interface with orthogonal flags):
    claude-history export                     # current workspace, local source
    claude-history export --as                # current workspace, all sources
    claude-history export --aw                # all workspaces, local source
    claude-history export --as --aw           # all workspaces, all sources

    claude-history export myproject           # specific workspace, local
    claude-history export myproject --as      # specific workspace, all sources
    claude-history export file.jsonl         # export single file

    claude-history export -o /tmp/backup      # current workspace, custom output
    claude-history export myproject -o ./out  # specific workspace, custom output

    claude-history export -r user@server      # current workspace, specific remote
    claude-history export --as -r user@vm01   # current workspace, all sources + SSH

  Date filtering:
    claude-history lss myproject --since 2025-11-01
    claude-history export myproject --since 2025-11-01 --until 2025-11-30

  Export options:
    claude-history export myproject --minimal       # minimal mode
    claude-history export myproject --split 500     # split long conversations
    claude-history export myproject --flat          # flat structure (no subdirs)

  WSL access (Windows):
    claude-history lsh --wsl                        # list WSL distributions
    claude-history lsw --wsl                        # list WSL workspaces
    claude-history lsw --wsl Ubuntu                 # list from specific distro
    claude-history lss myproject --wsl              # list WSL sessions
    claude-history export myproject --wsl           # export from WSL

  Windows access (from WSL):
    claude-history lsh --windows                    # list Windows users with Claude
    claude-history lsw --windows                    # list Windows workspaces
    claude-history lss myproject --windows          # list Windows sessions
    claude-history export myproject --windows       # export from Windows
```

## Commands

| Command | Description |
|---------|-------------|
| `lsh` | List hosts and manage SSH remotes |
| `lsw` | List workspaces |
| `lss` | List sessions |
| `export` | Export to markdown |
| `alias` | Manage workspace aliases |
| `stats` | Usage statistics |
| `reset` | Reset stored data |

## Common Examples

```bash
# List all workspaces
./claude-history lsw

# Export specific project
./claude-history export myproject

# Export from all sources (local + WSL + Windows + remotes)
./claude-history export myproject --as

# Date filtering
./claude-history lss --since 2025-11-01

# Minimal export (no metadata, for sharing)
./claude-history export myproject --minimal

# Time tracking
./claude-history stats --time
```

## Multi-Environment Access

```bash
# Discover all Claude installations and SSH remotes
./claude-history lsh

# Add/remove SSH remotes
./claude-history lsh add user@server
./claude-history lsh remove user@server

# Access WSL (from Windows)
python claude-history lss --wsl

# Access Windows (from WSL)
./claude-history lss --windows

# Access SSH remote
./claude-history lss -r user@server

# All sources at once (includes saved SSH remotes)
./claude-history export --as
```

## Workspace Aliases

Group related workspaces across environments:

```bash
# Create alias
./claude-history alias create myproject

# Add workspaces
./claude-history alias add myproject myproject
./claude-history alias add myproject --windows myproject
./claude-history alias add myproject -r user@vm myproject

# Use with @ prefix
./claude-history lss @myproject
./claude-history export @myproject
```

## Important: Preserve Your History

By default, Claude Code deletes conversation history after 30 days. Add this to `~/.claude/settings.json`:

```json
{
  "cleanupPeriodDays": 99999
}
```

## Documentation

- **[Command Reference](docs/USAGE.md)** - Detailed options for all commands
- **[Cookbook](docs/COOKBOOK.md)** - Recipes and workflows
- **[Troubleshooting](docs/TROUBLESHOOTING.md)** - FAQ and common issues
- **[CLAUDE.md](CLAUDE.md)** - Development guidelines

## License

MIT License - See [LICENSE](LICENSE) file.

## Acknowledgments

- Inspired by [Simon Willison's](https://simonwillison.net/) writing on Claude conversation extraction
- Built with [Claude Code](https://claude.com/claude-code)
