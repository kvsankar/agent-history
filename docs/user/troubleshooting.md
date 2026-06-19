# Troubleshooting & FAQ

<!-- doc-meta
doc_role: troubleshooting
audience: user
lifecycle: current
content_type: troubleshooting
surface: public
canonicality: primary
-->

## Frequently Asked Questions

### Where are Claude Code conversations stored?

Claude Code stores local sessions under its projects directory. For exact
storage locations across all supported agents, see
[cagelens-spec.md](../specs/cagelens-spec.md#supported-agents).

---

### What if I don't know my workspace name?

List all workspaces:
```bash
cagelens ws list
```

Or try a partial match:
```bash
cagelens session list --glob "*projects*"  # Match any workspace with "projects"
```

---

### Can I extract conversations from multiple workspaces?

Yes! Use multiple patterns or the `--aw` flag:
```bash
cagelens session export /abs/path/proj1 /abs/path/proj2 -o ./exports  # Exact workspaces
cagelens session export --glob "*django*" -o ./exports                # Matching workspaces
cagelens session export --aw -o ./exports                             # All workspaces
```

---

### What about privacy/sensitive data?

This tool is read-only against agent session stores and does not modify raw
agent files. It can read configured local, WSL, Windows, SSH, and web sources
when you request those scopes. Review generated export files before sharing.

---

### What's the difference between main sessions and agent sessions?

- **Main sessions** (UUID filenames): Your primary conversations with Claude
- **Agent sessions** (`agent-*` filenames): Task subagents spawned during conversations

Both are extracted and converted.

---

### How do I find conversations from a specific date range?

Use `--since` and `--until`:
```bash
cagelens session list --glob "*myproject*" --since 2025-11-01 --until 2025-11-30
cagelens session export --glob "*myproject*" --since 2025-11-01 -o ./exports
```

---

### Export or stats sync takes a long time

Large histories across multiple homes can take several minutes, especially with remotes.

Tips:
```bash
# Parallelize work
cagelens session export --ah --aw --jobs 4 -o ./exports
cagelens stats --sync --ah

# Skip sources that are slow or offline
cagelens session export --ah --aw --no-remote -o ./exports
cagelens stats --sync --ah --no-wsl

# Reduce output noise
cagelens session export --ah --aw --quiet -o ./exports
```

---

### How do I access WSL workspaces from Windows?

Use the `--wsl` flag:
```powershell
python cagelens home --wsl              # Find WSL distributions
python cagelens session list --glob "*myproject*" --wsl    # List sessions
python cagelens session export --glob "*myproject*" --wsl -o ./exports # Export
python cagelens session --wsl --agent codex
python cagelens session --wsl --agent gemini
```

No SSH or rsync needed - uses direct filesystem access.

---

### Can I access workspaces from multiple sources?

Yes! Combine flags:
```bash
cagelens ws list --ah                    # All homes
cagelens session myproject --wsl         # WSL
cagelens session myproject --windows     # Windows (from WSL)
cagelens session myproject -r user@host  # SSH remote
```

---

## Common Issues

### "Claude projects directory not found"

**Problem:** `~/.claude/projects/` doesn't exist

**Solution:**
1. Install Claude Code: https://claude.com/claude-code
2. Log in: `claude login`
3. Create at least one conversation
4. If your Claude data lives somewhere else (e.g., another drive or a mounted backup), set the `CLAUDE_PROJECTS_DIR` environment variable before running `cagelens`:

   ```bash
   export CLAUDE_PROJECTS_DIR=/mnt/windows/Users/me/.claude/projects
   cagelens ws list
   ```

---

### "No sessions found matching 'pattern'"

**Problem:** No workspaces match your pattern

**Solution:**
1. List all workspaces: `cagelens ws list`
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
   cagelens session export path/to/file.jsonl -o ./exports
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
wsl python cagelens session export -r user@host --aw -o ./exports
```

Alternative options (Chocolatey, Git Bash) may have SSH integration issues.

---

### "dup() in/out/err failed" rsync error

**Problem:** Windows rsync builds don't integrate well with Windows OpenSSH

**Solution:** Use WSL:
```powershell
wsl python cagelens session export -r user@host --aw -o ./exports
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
5. Run `cagelens ws list --wsl` to verify discovery

---

### WSL user lookup fails or hangs

If `wsl -d <distro> whoami` fails or hangs, `cagelens` falls back to UNC home scanning (e.g., `\\wsl.localhost\<distro>\home`) to find users and session paths. If discovery still fails:

**Solution:**
1. Ensure the UNC path is accessible in File Explorer
2. Restart WSL: `wsl --shutdown` then `wsl -d Ubuntu`
3. Re-run `cagelens home --wsl`

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

- Remote: `~/.cagelens/remote-cache/<host>/<agent>/<workspace>`
- WSL: Direct filesystem access (no caching)

---

## Reset & Data Management

### Where does cagelens store its data?

`cagelens` stores its own cache/config under `~/.cagelens/`. Homes, projects,
and project tags live in `~/.cagelens/config.json`; metrics and remote caches
are stored separately. For the complete file list and migration behavior, see
[cagelens-spec.md](../specs/cagelens-spec.md#file-locations).

### How do I start fresh?

Use the reset command:
```bash
# Delete everything (prompts for confirmation)
cagelens reset

# Delete only specific data
cagelens reset db        # Metrics only
cagelens reset config    # Homes/projects/project tags only
cagelens reset cache     # Remote/web caches only

# Skip confirmation (for scripts)
cagelens reset -y
```

### Stats showing incorrect data?

Try resetting the metrics database:
```bash
cagelens reset db
cagelens stats --sync
```
