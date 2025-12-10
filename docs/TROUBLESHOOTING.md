# Troubleshooting & FAQ

## Frequently Asked Questions

### Where are Claude Code conversations stored?

`~/.claude/projects/` - each workspace has its own subdirectory.

---

### What if I don't know my workspace name?

List all workspaces:
```bash
agent-history lsw
# or
ls ~/.claude/projects/
```

Or try a partial match:
```bash
agent-history lss projects  # Match any workspace with "projects"
```

---

### Can I extract conversations from multiple workspaces?

Yes! Use multiple patterns or the `--aw` flag:
```bash
agent-history export proj1 proj2         # Multiple specific patterns
agent-history export django              # All workspaces containing "django"
agent-history export --aw                # All workspaces
```

---

### What about privacy/sensitive data?

This tool only reads from your local `~/.claude/` directory. No data is sent anywhere. Review generated markdown files before sharing.

---

### What's the difference between main sessions and agent sessions?

- **Main sessions** (UUID filenames): Your primary conversations with Claude
- **Agent sessions** (`agent-*` filenames): Task subagents spawned during conversations

Both are extracted and converted.

---

### How do I find conversations from a specific date range?

Use `--since` and `--until`:
```bash
agent-history lss myproject --since 2025-11-01 --until 2025-11-30
agent-history export myproject --since 2025-11-01
```

---

### How do I access Claude Code workspaces in WSL from Windows?

Use the `--wsl` flag:
```powershell
python agent-history lsh --wsl              # Find WSL distributions
python agent-history lss myproject --wsl    # List sessions
python agent-history export myproject --wsl # Export
```

No SSH or rsync needed - uses direct filesystem access.

---

### Can I access workspaces from multiple sources?

Yes! Combine flags:
```bash
agent-history lsw --ah                    # All homes
agent-history lss myproject --wsl         # WSL
agent-history lss myproject --windows     # Windows (from WSL)
agent-history lss myproject -r user@host  # SSH remote
```

---

## Common Issues

### "Claude projects directory not found"

**Problem:** `~/.claude/projects/` doesn't exist

**Solution:**
1. Install Claude Code: https://claude.com/claude-code
2. Log in: `claude login`
3. Create at least one conversation
4. If your Claude data lives somewhere else (e.g., another drive or a mounted backup), set the `CLAUDE_PROJECTS_DIR` environment variable before running `agent-history`:

   ```bash
   export CLAUDE_PROJECTS_DIR=/mnt/windows/Users/me/.claude/projects
   agent-history lsw
   ```

---

### "No sessions found matching 'pattern'"

**Problem:** No workspaces match your pattern

**Solution:**
1. List all workspaces: `agent-history lsw`
2. Try a partial match
3. Check spelling and case-sensitivity

---

### Permission denied errors

**Problem:** Can't read from `~/.claude/projects/`

**Solution:**
```bash
ls -la ~/.claude/projects/
chmod 700 ~/.claude/projects/  # Fix if needed
```

---

### Empty or incomplete markdown files

**Problem:** Generated markdown files are empty or cut off

**Solution:**
1. Check the source `.jsonl` file isn't corrupted
2. Ensure the conversation wasn't interrupted mid-session
3. Try converting individual files for better error messages:
   ```bash
   agent-history export path/to/file.jsonl
   ```

---

## Windows-Specific Issues

### "python: command not found"

**Solution:**
1. Install Python from [python.org](https://www.python.org/downloads/)
2. During installation, check "Add Python to PATH"
3. Restart terminal
4. Verify: `python --version`

---

### UnicodeEncodeError or codec errors

**Solution:**
- Use the latest version of the tool
- The tool automatically uses UTF-8 encoding on all platforms

---

### Remote operations fail with "rsync not found"

**Problem:** Windows doesn't include rsync

**Solution:** Use WSL (most reliable):
```powershell
wsl python agent-history export -r user@host
```

Alternative options (Chocolatey, Git Bash) may have SSH integration issues.

---

### "dup() in/out/err failed" rsync error

**Problem:** Windows rsync builds don't integrate well with Windows OpenSSH

**Solution:** Use WSL:
```powershell
wsl python agent-history export -r user@host
```

---

### SSH connection fails

**Solution:**
1. Verify OpenSSH: `ssh -V`
2. If missing: Settings → Apps → Optional Features → OpenSSH Client
3. Set up SSH key:
   ```powershell
   ssh-keygen -t ed25519
   type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh user@host "cat >> .ssh/authorized_keys"
   ```
4. Test: `ssh user@host echo ok`

---

## WSL-Specific Issues

### "No WSL distributions found"

**Solution:**
1. Check WSL: `wsl --version`
2. If not installed: `wsl --install` (requires restart)
3. Install a distribution from Microsoft Store
4. Launch WSL at least once

---

### "Claude projects directory not found" (in WSL)

**Solution:**
1. Launch WSL: `wsl`
2. Install Claude Code
3. Log in: `claude login`
4. Create at least one conversation
5. Verify: `ls ~/.claude/projects/`

---

### Permission denied accessing WSL from Windows

**Solution:**
1. Ensure WSL is running: `wsl echo ok`
2. Try File Explorer: `\\wsl.localhost\Ubuntu\home\yourusername\.claude\projects`
3. Restart WSL: `wsl --shutdown` then `wsl -d Ubuntu`

---

## Remote Operations

### SSH key setup

```bash
# Generate key
ssh-keygen -t ed25519

# Copy to remote
ssh-copy-id user@server

# Test
ssh -o BatchMode=yes user@server echo ok
```

### Circular fetching prevention

When syncing between machines (P1 ↔ P2), the tool automatically filters out cached remote data (`remote_*`, `wsl_*` directories) to prevent infinite loops.

### Cache locations

- Remote: `~/.claude/projects/remote_hostname_workspace`
- WSL: Direct filesystem access (no caching)

---

## Reset & Data Management

### Where does agent-history store its data?

All data is stored in `~/.claude-history/`:
- `metrics.db` - SQLite database for stats and time tracking
- `config.json` - Settings (saved SSH remotes)
- `aliases.json` - Workspace alias definitions

### How do I start fresh?

Use the reset command:
```bash
# Delete everything (prompts for confirmation)
agent-history reset

# Delete only specific data
agent-history reset db        # Metrics only
agent-history reset aliases   # Aliases only
agent-history reset settings  # SSH remotes only

# Skip confirmation (for scripts)
agent-history reset -y
```

### Stats showing incorrect data?

Try resetting the metrics database:
```bash
agent-history reset db
agent-history stats --sync
```
