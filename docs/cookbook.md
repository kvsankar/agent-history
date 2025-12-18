# Cookbook

Common workflows and recipes for managing Claude Code conversations across environments.

## Recipe 1: Set Up a Cross-Environment Alias

Create an alias to manage a project that exists on Windows, WSL, and a remote VM:

```bash
# Create the alias
agent-history alias create myproject

# Add workspaces interactively from all homes
agent-history alias add myproject --ah -r user@vm01 --pick

# Or add by pattern (non-interactive)
agent-history alias add myproject myproject                    # local
agent-history alias add myproject --windows myproject          # Windows
agent-history alias add myproject -r user@vm01 myproject       # remote

# View the alias
agent-history alias show myproject
```

---

## Recipe 2: Daily Backup of All Sessions

Export all sessions from all environments to a backup directory:

```bash
# One-time: create an alias for everything
agent-history alias create all-projects
agent-history alias add all-projects --ah -r vm01 -r vm02 --pick

# Daily backup (incremental - only exports new/changed files)
agent-history export @all-projects -o ~/backups/claude-history/

# Force re-export everything
agent-history export @all-projects -o ~/backups/claude-history/ --force
```

---

## Recipe 3: Export a Single Project from Multiple Machines

```bash
# List sessions from all homes matching "myproject"
agent-history lss myproject --ah -r user@vm01

# Export from all homes
agent-history export myproject --ah -r user@vm01 -o ./exports/
```

---

## Recipe 4: Search Across All Environments

```bash
# List all workspaces from everywhere
agent-history lsw --ah -r user@vm01 -r user@vm02

# Find sessions mentioning a specific project
agent-history lsw --ah | grep django

# List sessions from matching workspaces
agent-history lss django --ah
```

---

## Recipe 5: Sync Remote Sessions for Offline Access

```bash
# Fetch and cache remote sessions locally
agent-history export myproject -r user@vm01

# Later, work with cached data (no network needed)
agent-history lss remote_vm01_home-user-myproject
```

---

## Recipe 6: Export for Sharing (Minimal Mode)

Create clean exports without metadata for blog posts or documentation:

```bash
# Export without UUIDs, token counts, and navigation links
agent-history export myproject --minimal -o ./blog-posts/

# Split long conversations into manageable parts
agent-history export myproject --minimal --split 500 -o ./blog-posts/
```

---

## Recipe 7: Move Aliases Between Machines

```bash
# On source machine: export aliases
agent-history alias export aliases.json

# Copy to target machine
scp aliases.json user@newmachine:~/

# On target machine: import aliases
agent-history alias import aliases.json
```

---

## Recipe 8: List Recent Sessions Across Everything

```bash
# Sessions from last week across all homes
agent-history lss --ah --since 2025-11-24

# Export recent sessions only
agent-history export @myproject --since 2025-11-01 -o ./recent/
```

---

## Recipe 9: Configure SSH Remotes (One-Time Setup)

Configure SSH remotes once so `--ah` uses them automatically:

```bash
# Add your SSH remotes (WSL/Windows are auto-detected)
agent-history lsh add user@vm01
agent-history lsh add user@vm02

# Verify saved sources
agent-history lsh

# Now --ah includes saved remotes automatically
agent-history lsw --ah              # includes vm01 and vm02
agent-history stats --time --ah     # syncs from vm01 and vm02
```

---

## Recipe 10: Track Usage Metrics Across All Environments

```bash
# Initial sync from all homes (uses saved remotes)
agent-history stats --sync --ah

# View overall statistics (current workspace)
agent-history stats

# View all workspaces
agent-history stats --aw

# See tool usage patterns
agent-history stats --tools

# Daily breakdown
agent-history stats --by-day

# Filter to specific project
agent-history stats myproject
```

---

## Recipe 11: Monthly Usage Report

```bash
# Sync latest data
agent-history stats --sync --ah

# Get stats for November 2025
agent-history stats --since 2025-11-01 --until 2025-11-30

# Per-workspace breakdown for the month
agent-history stats --by-workspace --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 12: Compare Tool Usage Across Projects

```bash
# Overall tool usage
agent-history stats --tools

# Tool usage for specific project
agent-history stats --tools myproject

# Compare by looking at different workspaces
agent-history stats --tools frontend-app
agent-history stats --tools backend-api
```

---

## Recipe 13: Time Tracking with Daily Breakdown

Track how much time you've spent with Claude Code:

```bash
# Current workspace, sync all homes first
agent-history stats --time --ah

# All workspaces, sync all homes first
agent-history stats --time --ah --aw

# Filter by date range
agent-history stats --time --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 14: Analyze Alias Usage

Aliases are automatically aggregated in stats output:

```bash
# Create alias for a project across environments
agent-history alias create myproject
agent-history alias add myproject --ah myproject

# View aggregated stats (shows @myproject with combined metrics)
agent-history stats

# Detailed workspace view shows aliases separately
agent-history stats --by-workspace
```

---

## Recipe 15: Automatic Alias Scoping

Once a workspace is part of an alias, commands automatically use the alias scope:

```bash
# Set up: create alias and add current workspace
agent-history alias create myproject
agent-history alias add myproject myproject

# Now running from this workspace automatically uses the alias
agent-history lss        # 📎 Using alias @myproject
agent-history export     # 📎 Using alias @myproject
agent-history stats      # 📎 Using alias @myproject

# Force current workspace only when needed
agent-history lss --this
agent-history export --this
agent-history stats --this
```

---

## Use Cases

### Blog Post Material

Extract conversation history for writing blog posts:

```bash
# Initial export
agent-history export my-project -o ./blog-material

# Later - only exports new/updated conversations
agent-history export my-project -o ./blog-material
```

### Project Documentation

Document development decisions and iterations:

```bash
agent-history export backend-api -o ./docs/development-log
```

### Analysis & Learning

Review problem-solving approaches across sessions:

```bash
# Export all sessions for a project
agent-history export ml-pipeline

# Analyze patterns
grep -r "Error:" claude-conversations/
```

### Archival

Archive conversation history by date/project:

```bash
agent-history export project-2024 -o archives/2024-11/
```

### Multi-Environment Consolidation

Consolidate conversations from multiple environments:

```bash
# Export all homes: local + WSL + Windows + SSH remotes
agent-history export myproject --ah -o ./backups -r user@vm01

# Or all workspaces from all homes
agent-history export --ah --aw -o ./backups -r user@vm01
```
