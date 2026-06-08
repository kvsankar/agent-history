# Cookbook

<!-- doc-meta
doc_role: guide
audience: user
lifecycle: current
content_type: workflow
surface: public
canonicality: primary
-->

Common workflows and recipes for managing coding-agent conversations across environments.

Tip: When targeting Codex or Gemini sessions (including in WSL), pass `--agent codex` or `--agent gemini`.

## Recipe 1: Set Up a Cross-Environment Project

Create a project to manage workspaces that exist on Windows, WSL, and a remote VM:

```bash
# Create the project
cagelens project create myproject

# Add workspaces interactively from all homes
cagelens project add myproject --ah -r user@vm01 --pick

# Or add by pattern (non-interactive)
cagelens project add myproject myproject                    # local
cagelens project add myproject --windows myproject          # Windows
cagelens project add myproject -r user@vm01 myproject       # remote

# View the project
cagelens project show myproject
```

---

## Recipe 2: Daily Backup of All Sessions

Export all sessions from all environments to a backup directory:

```bash
# One-time: create a project for everything
cagelens project create all-projects
cagelens project add all-projects --ah -r vm01 -r vm02 --pick

# Daily backup (incremental - only exports new/changed files)
cagelens export @all-projects -o ~/backups/cagelens/

# Force re-export everything
cagelens export @all-projects -o ~/backups/cagelens/ --force

# Faster and quieter backups (parallel workers, less console noise)
cagelens export @all-projects -o ~/backups/cagelens/ --jobs 4 --quiet
```

---

## Recipe 3: Export a Single Project from Multiple Machines

```bash
# List sessions from all homes matching "myproject"
cagelens ss myproject --ah -r user@vm01
cagelens ss myproject --ah --no-wsl    # exclude WSL if it is slow

# Export from all homes
cagelens export myproject --ah -r user@vm01 -o ./exports/

# Skip remote sources if a host is offline
cagelens export myproject --ah --no-remote -o ./exports/
```

---

## Recipe 4: Search Across All Environments

```bash
# List all workspaces from everywhere
cagelens ws --ah -r user@vm01 -r user@vm02

# Find sessions mentioning a specific project
cagelens ws --ah | grep django

# List sessions from matching workspaces
cagelens ss django --ah
cagelens ss django --ah --counts       # force counts on all sources
```

---

## Recipe 5: Sync Remote Sessions for Offline Access

```bash
# Fetch and cache remote sessions locally
cagelens export myproject -r user@vm01

# Later, work with cached data (no network needed)
cagelens ss remote_vm01_home-user-myproject
```

---

## Recipe 6: Export for Sharing (Minimal Mode)

Create clean exports without metadata for blog posts or documentation:

```bash
# Export without UUIDs, token counts, and navigation links
cagelens export myproject --minimal -o ./blog-posts/

# Split long conversations into manageable parts
cagelens export myproject --minimal --split 500 -o ./blog-posts/
```

---

## Recipe 7: Move Projects Between Machines

```bash
# On source machine: export projects
cagelens project export projects.json

# Copy to target machine
scp projects.json user@newmachine:~/

# On target machine: import projects
cagelens project import projects.json
```

---

## Recipe 8: List Recent Sessions Across Everything

```bash
# Sessions from last week across all homes
cagelens ss --ah --since 2025-11-24
cagelens ss --ah --wsl-counts          # count WSL messages on Windows

# Export recent sessions only
cagelens export @myproject --since 2025-11-01 -o ./recent/
```

---

## Recipe 9: Configure Homes (One-Time Setup)

Configure homes once so `--ah` uses them automatically:

```bash
# Add homes (explicit model - must add for --ah to include)
cagelens home add --wsl                 # add WSL
cagelens home add --windows             # add Windows
cagelens home add user@vm01             # add SSH remote
cagelens home add user@vm02             # add another remote

# Verify saved sources
cagelens home

# Now --ah includes configured homes automatically
cagelens ws --ah              # includes configured sources
cagelens stats --time --ah     # cached stats from all homes
```

---

## Recipe 10: Track Usage Metrics Across All Environments

```bash
# Initial sync from all homes (uses saved remotes)
cagelens stats --sync --ah --jobs 4

# View overall statistics (current workspace)
cagelens stats

# View all workspaces
cagelens stats --aw

# See tool usage patterns
cagelens stats --by tool

# Daily breakdown
cagelens stats --by day

# Filter to specific project
cagelens stats myproject
```

---

## Recipe 11: Monthly Usage Report

```bash
# Sync latest data
cagelens stats --sync --ah

# Get stats for November 2025
cagelens stats --since 2025-11-01 --until 2025-11-30

# Per-workspace breakdown for the month
cagelens stats --by workspace --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 12: Compare Tool Usage Across Projects

```bash
# Overall tool usage
cagelens stats --by tool

# Tool usage for specific project
cagelens stats --by tool myproject

# Compare by looking at different workspaces
cagelens stats --by tool frontend-app
cagelens stats --by tool backend-api
```

---

## Recipe 13: Time Tracking with Daily Breakdown

Track how much time you've spent with Claude Code:

```bash
# Current workspace, sync all homes first
cagelens stats --time --ah

# All workspaces, sync all homes first
cagelens stats --time --ah --aw

# Filter by date range
cagelens stats --time --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 14: Analyze Project Usage

Projects are automatically aggregated in stats output:

```bash
# Create project for workspaces across environments
cagelens project create myproject
cagelens project add myproject --ah myproject

# View aggregated stats (shows @myproject with combined metrics)
cagelens stats

# Detailed workspace view shows projects separately
cagelens stats --by workspace
```

---

## Recipe 15: Automatic Project Scoping

Once a workspace is part of a project, commands automatically use the project scope:

```bash
# Set up: create project and add current workspace
cagelens project create myproject
cagelens project add myproject myproject

# Now running from this workspace automatically uses the project
cagelens ss         # Using project @myproject
cagelens ss --counts
cagelens export     # Using project @myproject
cagelens stats      # Using project @myproject

# Force current workspace only when needed
cagelens ss --this
cagelens ss --this --no-windows
cagelens export --this
cagelens stats --this
```

---

## Use Cases

### Blog Post Material

Extract conversation history for writing blog posts:

```bash
# Initial export
cagelens export my-project -o ./blog-material

# Later - only exports new/updated conversations
cagelens export my-project -o ./blog-material
```

### Project Documentation

Document development decisions and iterations:

```bash
cagelens export backend-api -o ./docs/development-log
```

### Analysis & Learning

Review problem-solving approaches across sessions:

```bash
# Export all sessions for a project
cagelens export ml-pipeline

# Analyze patterns
grep -r "Error:" .cagelens/exports/
```

### Archival

Archive conversation history by date/project:

```bash
cagelens export project-2024 -o archives/2024-11/
```

### Multi-Environment Consolidation

Consolidate conversations from multiple environments:

```bash
# Export all homes: local + WSL + Windows + SSH remotes
cagelens export myproject --ah -o ./backups -r user@vm01

# Or all workspaces from all homes
cagelens export --ah --aw -o ./backups -r user@vm01
```
