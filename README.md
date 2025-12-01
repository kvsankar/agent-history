# claude-history

A CLI tool to browse and export Claude Code conversation history with multi-environment support.

## Features

- **Workspace filtering** - Export by project, not just session IDs
- **Multi-environment** - Access local, WSL, Windows, and SSH remotes
- **Workspace aliases** - Group related workspaces across platforms
- **Usage metrics** - Track time spent, tokens used, tool usage
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

## Commands

| Command | Description |
|---------|-------------|
| `lsh` | List hosts (local, WSL, Windows) |
| `lsw` | List workspaces |
| `lss` | List sessions |
| `export` | Export to markdown |
| `alias` | Manage workspace aliases |
| `sources` | Manage SSH remotes |
| `stats` | Usage statistics |

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
# Discover all Claude installations
./claude-history lsh

# Access WSL (from Windows)
python claude-history lss --wsl

# Access Windows (from WSL)
./claude-history lss --windows

# Access SSH remote
./claude-history lss -r user@server

# All sources at once
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
