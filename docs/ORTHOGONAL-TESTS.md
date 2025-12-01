# Orthogonal Test Matrix

This document defines the combinatorial test space for `claude-history` commands.

## Dimensions

| Dimension | Values |
|-----------|--------|
| **Context** | In-workspace (aliased), In-workspace (not aliased), Outside-workspace |
| **Command** | lss, export, stats |
| **Source Scope** | (default), --as, -r host, --wsl, --windows |
| **Workspace Scope** | (default), --aw, pattern, @alias |
| **Override** | (default), --this |

## Expected Behavior Matrix

### Key Behaviors

| Scenario | Expected Workspace | Expected Source |
|----------|-------------------|-----------------|
| No flags, in aliased workspace | Alias workspaces | Local only |
| --as, in aliased workspace | Alias workspaces | All sources |
| --this, in aliased workspace | Current workspace only | Local only |
| --as --this, in aliased workspace | Current workspace only | All sources |
| --aw | All workspaces | Local only |
| --as --aw | All workspaces | All sources |
| pattern specified | Pattern workspaces | Local only |
| @alias specified | Alias workspaces | All sources in alias |
| Outside workspace, no flags | ERROR | - |
| Outside workspace, --aw | All workspaces | Local only |
| Outside workspace, pattern | Pattern workspaces | Local only |

---

## Test Cases

### Section A: In Aliased Workspace

**Setup:** Run from a workspace that belongs to an alias (e.g., claude-history)

#### A.1 Default (no flags)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.1.1 | `lss` | Alias workspaces | Local | ⬜ |
| A.1.2 | `export -o /tmp/t` | Alias workspaces | Local | ⬜ |
| A.1.3 | `stats` | Alias workspaces | Local DB | ⬜ |

#### A.2 With --as (all sources)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.2.1 | `lss --as` | Alias workspaces | All sources | ⬜ |
| A.2.2 | `export --as -o /tmp/t` | Alias workspaces | All sources | ⬜ |
| A.2.3 | `stats --as` | Alias workspaces | Sync all, query alias | ⬜ |

#### A.3 With --this (override alias)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.3.1 | `lss --this` | Current workspace only | Local | ⬜ |
| A.3.2 | `export --this -o /tmp/t` | Current workspace only | Local | ⬜ |
| A.3.3 | `stats --this` | Current workspace only | Local DB | ⬜ |

#### A.4 With --as --this

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.4.1 | `lss --as --this` | Current workspace only | All sources | ⬜ |
| A.4.2 | `export --as --this -o /tmp/t` | Current workspace only | All sources | ⬜ |
| A.4.3 | `stats --as --this` | Current workspace only | Sync all, query current | ⬜ |

#### A.5 With --aw (all workspaces)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.5.1 | `lss --aw` | N/A (lss doesn't have --aw) | - | ⊘ |
| A.5.2 | `export --aw -o /tmp/t` | All workspaces | Local | ⬜ |
| A.5.3 | `stats --aw` | All workspaces | Local DB | ⬜ |

#### A.6 With --as --aw

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.6.1 | `export --as --aw -o /tmp/t` | All workspaces | All sources | ⬜ |
| A.6.2 | `stats --as --aw` | All workspaces | Sync all, query all | ⬜ |

#### A.7 With explicit pattern

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.7.1 | `lss otherproject` | otherproject | Local | ⬜ |
| A.7.2 | `export otherproject -o /tmp/t` | otherproject | Local | ⬜ |
| A.7.3 | `stats otherproject` | otherproject | Local DB | ⬜ |

#### A.8 With explicit @alias

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.8.1 | `lss @otheralias` | otheralias workspaces | All in alias | ⬜ |
| A.8.2 | `export @otheralias -o /tmp/t` | otheralias workspaces | All in alias | ⬜ |
| A.8.3 | `stats @otheralias` | otheralias workspaces | Local DB | ⬜ |

#### A.9 With -r (SSH remote)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.9.1 | `lss -r user@host` | Current/Alias on remote | Remote only | ⬜ |
| A.9.2 | `export -r user@host -o /tmp/t` | Current/Alias on remote | Remote only | ⬜ |

#### A.10 With --as -r (all sources + extra remote)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| A.10.1 | `lss --as -r user@host` | Alias workspaces | All + extra remote | ⬜ |
| A.10.2 | `export --as -r user@host -o /tmp/t` | Alias workspaces | All + extra remote | ⬜ |

---

### Section B: In Non-Aliased Workspace

**Setup:** Run from a workspace that does NOT belong to any alias

#### B.1 Default (no flags)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| B.1.1 | `lss` | Current workspace | Local | ⬜ |
| B.1.2 | `export -o /tmp/t` | Current workspace | Local | ⬜ |
| B.1.3 | `stats` | Current workspace | Local DB | ⬜ |

#### B.2 With --as

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| B.2.1 | `lss --as` | Current workspace | All sources | ⬜ |
| B.2.2 | `export --as -o /tmp/t` | Current workspace | All sources | ⬜ |
| B.2.3 | `stats --as` | Current workspace | Sync all, query current | ⬜ |

#### B.3 With --this (no effect in non-aliased)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| B.3.1 | `lss --this` | Current workspace | Local | ⬜ |
| B.3.2 | `export --this -o /tmp/t` | Current workspace | Local | ⬜ |
| B.3.3 | `stats --this` | Current workspace | Local DB | ⬜ |

#### B.4 With --aw

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| B.4.1 | `export --aw -o /tmp/t` | All workspaces | Local | ⬜ |
| B.4.2 | `stats --aw` | All workspaces | Local DB | ⬜ |

#### B.5 With --as --aw

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| B.5.1 | `export --as --aw -o /tmp/t` | All workspaces | All sources | ⬜ |
| B.5.2 | `stats --as --aw` | All workspaces | Sync all, query all | ⬜ |

---

### Section C: Outside Workspace

**Setup:** Run from a directory that is NOT a Claude workspace (e.g., /tmp)

#### C.1 Default (no flags) - Should ERROR

| ID | Command | Expected Result | Status |
|----|---------|-----------------|--------|
| C.1.1 | `lss` | ERROR: Not in a workspace | ⬜ |
| C.1.2 | `export` | ERROR: Not in a workspace | ⬜ |
| C.1.3 | `stats` | ERROR: Not in a workspace | ⬜ |

#### C.2 With --aw (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| C.2.1 | `export --aw -o /tmp/t` | All workspaces | Local | ⬜ |
| C.2.2 | `stats --aw` | All workspaces | Local DB | ⬜ |

#### C.3 With --as --aw (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| C.3.1 | `export --as --aw -o /tmp/t` | All workspaces | All sources | ⬜ |
| C.3.2 | `stats --as --aw` | All workspaces | Sync all, query all | ⬜ |

#### C.4 With explicit pattern (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| C.4.1 | `lss myproject` | myproject | Local | ⬜ |
| C.4.2 | `export myproject -o /tmp/t` | myproject | Local | ⬜ |
| C.4.3 | `stats myproject` | myproject | Local DB | ⬜ |

#### C.5 With @alias (should work)

| ID | Command | Expected Workspace Scope | Expected Source Scope | Status |
|----|---------|-------------------------|----------------------|--------|
| C.5.1 | `lss @myalias` | Alias workspaces | All in alias | ⬜ |
| C.5.2 | `export @myalias -o /tmp/t` | Alias workspaces | All in alias | ⬜ |
| C.5.3 | `stats @myalias` | Alias workspaces | Local DB | ⬜ |

#### C.6 With --as only (ambiguous - what workspace?)

| ID | Command | Expected Result | Status |
|----|---------|-----------------|--------|
| C.6.1 | `lss --as` | ERROR or list all? | ⬜ |
| C.6.2 | `export --as -o /tmp/t` | ERROR or export all? | ⬜ |
| C.6.3 | `stats --as` | ERROR or stats all? | ⬜ |

---

## Running the Tests

```bash
# Set up test environment
cd /path/to/claude-history  # Aliased workspace

# Run Section A tests
./claude-history lss                           # A.1.1
./claude-history export -o /tmp/t && ls /tmp/t # A.1.2
# ... etc

# Move to non-aliased workspace for Section B
cd /path/to/non-aliased-project
# Run Section B tests

# Move outside workspace for Section C
cd /tmp
# Run Section C tests
```

## Bug Found: 2025-12-01

**Test ID:** A.2.2 (equivalent)
**Command:** `export --as` in aliased workspace
**Expected:** Export alias workspaces from all sources
**Actual:** Exported ALL workspaces from all sources
**Root Cause:** Condition `not args.all_sources` incorrectly skipped workspace detection
**Fix:** Removed `and not args.all_sources` from the condition check
