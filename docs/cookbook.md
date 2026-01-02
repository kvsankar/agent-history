# Cookbook

Common workflows and recipes for managing Claude Code conversations across environments.

Tip: When targeting Codex or Gemini sessions (including in WSL), pass `--agent codex` or `--agent gemini`.

## Recipe 1: Set Up a Cross-Environment Project

Create a project to manage workspaces that exist on Windows, WSL, and a remote VM:

```bash
# Create the project
agent-history project create myproject

# Add workspaces interactively from all homes
agent-history project add myproject --ah -r user@vm01 --pick

# Or add by pattern (non-interactive)
agent-history project add myproject myproject                    # local
agent-history project add myproject --windows myproject          # Windows
agent-history project add myproject -r user@vm01 myproject       # remote

# View the project
agent-history project show myproject
```

---

## Recipe 2: Daily Backup of All Sessions

Export all sessions from all environments to a backup directory:

```bash
# One-time: create a project for everything
agent-history project create all-projects
agent-history project add all-projects --ah -r vm01 -r vm02 --pick

# Daily backup (incremental - only exports new/changed files)
agent-history export @all-projects -o ~/backups/claude-history/

# Force re-export everything
agent-history export @all-projects -o ~/backups/claude-history/ --force

# Faster and quieter backups (parallel workers, less console noise)
agent-history export @all-projects -o ~/backups/claude-history/ --jobs 4 --quiet
```

---

## Recipe 3: Export a Single Project from Multiple Machines

```bash
# List sessions from all homes matching "myproject"
agent-history ss myproject --ah -r user@vm01
agent-history ss myproject --ah --no-wsl    # exclude WSL if it is slow

# Export from all homes
agent-history export myproject --ah -r user@vm01 -o ./exports/

# Skip remote sources if a host is offline
agent-history export myproject --ah --no-remote -o ./exports/
```

---

## Recipe 4: Search Across All Environments

```bash
# List all workspaces from everywhere
agent-history ws --ah -r user@vm01 -r user@vm02

# Find sessions mentioning a specific project
agent-history ws --ah | grep django

# List sessions from matching workspaces
agent-history ss django --ah
agent-history ss django --ah --counts       # force counts on all sources
```

---

## Recipe 5: Sync Remote Sessions for Offline Access

```bash
# Fetch and cache remote sessions locally
agent-history export myproject -r user@vm01

# Later, work with cached data (no network needed)
agent-history ss remote_vm01_home-user-myproject
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

## Recipe 7: Move Projects Between Machines

```bash
# On source machine: export projects
agent-history project export projects.json

# Copy to target machine
scp projects.json user@newmachine:~/

# On target machine: import projects
agent-history project import projects.json
```

---

## Recipe 8: List Recent Sessions Across Everything

```bash
# Sessions from last week across all homes
agent-history ss --ah --since 2025-11-24
agent-history ss --ah --wsl-counts          # count WSL messages on Windows

# Export recent sessions only
agent-history export @myproject --since 2025-11-01 -o ./recent/
```

---

## Recipe 9: Configure Homes (One-Time Setup)

Configure homes once so `--ah` uses them automatically:

```bash
# Add homes (explicit model - must add for --ah to include)
agent-history home add --wsl                 # add WSL
agent-history home add --windows             # add Windows
agent-history home add user@vm01             # add SSH remote
agent-history home add user@vm02             # add another remote

# Verify saved sources
agent-history home

# Now --ah includes configured homes automatically
agent-history ws --ah              # includes configured sources
agent-history stats --time --ah     # syncs from all homes
```

---

## Recipe 10: Track Usage Metrics Across All Environments

```bash
# Initial sync from all homes (uses saved remotes)
agent-history stats --sync --ah --jobs 4

# View overall statistics (current workspace)
agent-history stats

# View all workspaces
agent-history stats --aw

# See tool usage patterns
agent-history stats --by tool

# Daily breakdown
agent-history stats --by day

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
agent-history stats --by workspace --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 12: Compare Tool Usage Across Projects

```bash
# Overall tool usage
agent-history stats --by tool

# Tool usage for specific project
agent-history stats --by tool myproject

# Compare by looking at different workspaces
agent-history stats --by tool frontend-app
agent-history stats --by tool backend-api
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

## Recipe 14: Analyze Project Usage

Projects are automatically aggregated in stats output:

```bash
# Create project for workspaces across environments
agent-history project create myproject
agent-history project add myproject --ah myproject

# View aggregated stats (shows @myproject with combined metrics)
agent-history stats

# Detailed workspace view shows projects separately
agent-history stats --by workspace
```

---

## Recipe 15: Automatic Project Scoping

Once a workspace is part of a project, commands automatically use the project scope:

```bash
# Set up: create project and add current workspace
agent-history project create myproject
agent-history project add myproject myproject

# Now running from this workspace automatically uses the project
agent-history ss         # Using project @myproject
agent-history ss --counts
agent-history export     # Using project @myproject
agent-history stats      # Using project @myproject

# Force current workspace only when needed
agent-history ss --this
agent-history ss --this --no-windows
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
grep -r "Error:" ai-chats/
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
