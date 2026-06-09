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
# Preview workspaces from all homes
cagelens project add myproject --glob "*myproject*" --ah -r user@vm01 --dry-run

# Or add by pattern (non-interactive)
cagelens project add myproject --glob "*myproject*"                    # local
cagelens project add myproject --glob "*myproject*" --windows          # Windows
cagelens project add myproject --glob "*myproject*" -r user@vm01       # remote

# View the project
cagelens project show myproject
```

---

## Recipe 2: Daily Backup of All Sessions

Export all sessions from all environments to a backup directory:

```bash
# One-time: create a project from all known workspaces
cagelens project add all-projects --ah -r vm01 -r vm02 --aw

# Daily backup (incremental - only exports new/changed files)
cagelens project export all-projects -o ~/backups/cagelens/

# Force re-export everything
cagelens project export all-projects -o ~/backups/cagelens/ --force

# Faster and quieter backups (parallel workers, less console noise)
cagelens project export all-projects -o ~/backups/cagelens/ --jobs 4 --quiet
```

---

## Recipe 3: Export a Single Project from Multiple Machines

```bash
# List sessions from all homes matching "myproject"
cagelens session list --glob "*myproject*" --ah -r user@vm01
cagelens session list --glob "*myproject*" --ah --no-wsl    # exclude WSL if it is slow

# Export from all homes
cagelens session export --glob "*myproject*" --ah -r user@vm01 -o ./exports/

# Skip remote sources if a host is offline
cagelens session export --glob "*myproject*" --ah --no-remote -o ./exports/
```

---

## Recipe 4: Search Across All Environments

```bash
# List all workspaces from everywhere
cagelens ws --ah -r user@vm01 -r user@vm02

# Find sessions mentioning a specific project
cagelens ws --ah | grep django

# List sessions from matching workspaces
cagelens session list --glob "*django*" --ah
cagelens session list --glob "*django*" --ah --counts       # force counts on all sources
```

---

## Recipe 5: Sync Remote Sessions for Offline Access

```bash
# Fetch and cache remote sessions locally
cagelens fetch --glob "*myproject*" -r user@vm01

# Later, work with cached data (no network needed)
cagelens session list --glob "*myproject*"
```

---

## Recipe 6: Export for Sharing (Minimal Mode)

Create clean exports without metadata for blog posts or documentation:

```bash
# Export without UUIDs, token counts, and navigation links
cagelens session export --glob "*myproject*" --minimal -o ./blog-posts/

# Split long conversations into manageable parts
cagelens session export --glob "*myproject*" --minimal --split 500 -o ./blog-posts/
```

---

## Recipe 7: Move Projects Between Machines

```bash
# On source machine: inspect project membership
cagelens project show myproject

# On target machine: recreate membership from discoverable workspaces
cagelens project add myproject --glob "*myproject*" --dry-run
cagelens project add myproject --glob "*myproject*"
```

---

## Recipe 8: List Recent Sessions Across Everything

```bash
# Sessions from last week across all homes
cagelens session list --ah --since 2025-11-24
cagelens session list --ah --counts          # count messages where needed

# Export recent sessions only
cagelens session export --project myproject --since 2025-11-01 -o ./recent/
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
cagelens stats --sync --ah

# View overall statistics (current workspace)
cagelens stats

# View all workspaces
cagelens stats --aw

# See tool usage patterns
cagelens stats --by tool

# Daily breakdown
cagelens stats --by day

# Filter to specific project
cagelens stats --project myproject
```

---

## Recipe 11: Monthly Usage Report

```bash
# Sync latest data
cagelens stats --sync --ah

# Get stats for November 2025
cagelens stats --since 2025-11-01 --until 2025-11-30

# Per-workspace breakdown for the month
cagelens stats rollup --metric time --by workspace,month --since 2025-11-01 --until 2025-11-30
```

---

## Recipe 12: Compare Tool Usage Across Projects

```bash
# Overall tool usage
cagelens stats --by tool

# Tool usage for specific project
cagelens stats --project myproject --tools

# Compare by looking at different workspaces
cagelens stats --glob "*frontend-app*" --tools
cagelens stats --glob "*backend-api*" --tools
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
cagelens project add myproject --glob "*myproject*" --ah

# View aggregated stats
cagelens stats --project myproject

# Detailed workspace view shows projects separately
cagelens stats --by workspace
```

---

## Recipe 15: Automatic Project Scoping

Once a workspace is part of a project, commands automatically use the project scope:

```bash
# Set up: create project and add current workspace
cagelens project add myproject --this

# Now running from this workspace automatically uses the project
cagelens session list         # Using project myproject
cagelens session list --counts
cagelens session export -o ./exports     # Using project myproject
cagelens stats      # Using project @myproject

# Force current workspace only when needed
cagelens session list --this
cagelens session list --this --no-windows
cagelens session export --this -o ./exports
cagelens stats --this
```

---

## Use Cases

### Blog Post Material

Extract conversation history for writing blog posts:

```bash
# Initial export
cagelens session export --glob "*my-project*" -o ./blog-material

# Later - only exports new/updated conversations
cagelens session export --glob "*my-project*" -o ./blog-material
```

### Project Documentation

Document development decisions and iterations:

```bash
cagelens session export --glob "*backend-api*" -o ./docs/development-log
```

### Analysis & Learning

Review problem-solving approaches across sessions:

```bash
# Export all sessions for a project
cagelens session export --glob "*ml-pipeline*"

# Analyze patterns
grep -r "Error:" .cagelens/exports/
```

### Archival

Archive conversation history by date/project:

```bash
cagelens session export --glob "*project-2024*" -o archives/2024-11/
```

### Multi-Environment Consolidation

Consolidate conversations from multiple environments:

```bash
# Export all homes: local + WSL + Windows + SSH remotes
cagelens session export --glob "*myproject*" --ah -o ./backups -r user@vm01

# Or all workspaces from all homes
cagelens session export --ah --aw -o ./backups -r user@vm01
```
