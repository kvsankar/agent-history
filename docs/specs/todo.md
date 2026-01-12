# Specs TODO

Items that need investigation or clarification before full specification.

## Pending Investigation

### Web Sessions (Claude.ai)

**Status:** Implemented

**Current state in implementation:**
- `--web`/`--no-web` control scope resolution
- `--ah` includes web by default
- Sessions are fetched via Claude API and cached to `~/.agent-history/web-cache`

**Action:** Spec updated to reflect web support.

---

### ws list Output Fields

**Status:** Resolved

**Current state:**
- `ws list` outputs HOME, WORKSPACE, SESSIONS, STATUS, LAST_MODIFIED

**Action:** Spec updated to match current output.
