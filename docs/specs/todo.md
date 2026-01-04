# Specs TODO

Items that need investigation or clarification before full specification.

## Pending Investigation

### Web Sessions (Claude.ai)

**Status:** Uncertain whether to keep or remove

**Current state in implementation:**
- `web list` - List Claude.ai web sessions
- `web export` - Export web sessions
- `--web` flag on various commands
- Requires authentication (token + org-uuid)
- Auto-auth on macOS via keychain

**Questions:**
1. Is Claude.ai web session access still a priority feature?
2. Should `--web` be a home type or a separate command group?
3. Authentication flow needs documentation if kept

**Action:** Confirm with stakeholder whether web sessions remain in scope.

---

### ws list Output Fields

**Status:** Spec differs from implementation

**Spec says:**
- WORKSPACE, SESSIONS, LAST_MODIFIED columns

**Implementation currently outputs:**
- HOME, WORKSPACE columns (no session count or last_modified)

**Questions:**
1. Should session counts be included in `ws list` output?
2. Should last_modified be included?
3. Performance impact of computing these for large workspaces?

**Action:** Decide whether to update spec to match impl, or update impl to match spec.
