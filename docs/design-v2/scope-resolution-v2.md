# Scope Resolution Architecture v2

## Critical Review of v1 Design

### Fundamental Gaps Identified

1. **No Specification Types** - Used raw strings and `All` sentinel without proper type hierarchy
2. **No Resolution Context** - Assumed resolution happens in vacuum; ignored platform, CWD, available homes
3. **No Platform Awareness** - `"wsl"` on Windows vs Linux means different things
4. **No Agent-Specific Handling** - Claude, Codex, Gemini have different storage/indexing
5. **Conflated Resolution and Expansion** - Two distinct operations treated as one
6. **No Encoding/Decoding** - Workspaces have multiple representations (path, encoded, hash)
7. **No Web Session Support** - Web sessions don't follow Home/Workspace/Session hierarchy
8. **No Error Handling** - Assumed resolution always succeeds
9. **Pattern vs Exact Match Unclear** - Critical for the original bug!
10. **No Current Context Detection** - Implicit context (CWD project) not captured

---

## v2 Architecture: Specification → Resolution → Concrete

### Core Principle

**Separation of Concerns:**
- **Specification**: How user/command expresses intent (may be symbolic, pattern-based, or concrete)
- **Resolution**: Converting specifications to concrete values using context
- **Expansion**: Breaking one record into multiple when specification matches multiple items

---

## 1. Specification Types

### 1.1 Home Specification

```
HomeSpec =
    | All                              # All available homes
    | Local                            # Local home (always available)
    | Current                          # Home containing CWD
    | Category(category)               # All of category: "wsl", "windows", "remote"
    | CategoryItem(category, id)       # Specific: wsl:Ubuntu, windows:alice, remote:server
    | Concrete(string)                 # Already resolved: "local", "wsl:Ubuntu"
```

**Examples:**
```python
HomeSpec.All                           # --ah flag
HomeSpec.Local                         # default when no flags
HomeSpec.Current                       # implicit from CWD
HomeSpec.Category("wsl")               # --wsl flag (all WSL distros)
HomeSpec.Category("windows")           # --windows flag (all Windows users)
HomeSpec.Category("remote")            # --remote flag (all configured remotes)
HomeSpec.CategoryItem("wsl", "Ubuntu") # --wsl=Ubuntu
HomeSpec.CategoryItem("remote", "dev") # --remote=dev
HomeSpec.Concrete("local")             # Already resolved
```

**Resolution Context Required:**
- Platform (linux, wsl, windows, darwin)
- Available WSL distros
- Available Windows users
- Configured remotes

---

### 1.2 Workspace Specification

```
WorkspaceSpec =
    | All                              # All workspaces in home
    | Current                          # Current working directory
    | Project(name)                    # Project reference → multiple workspaces
    | Path(path)                       # Full absolute path: /home/user/projects/auth
    | Encoded(encoded)                 # Encoded form: home-user-projects-auth
    | Pattern(pattern, match_type)     # Pattern with match semantics
    | Hash(hash)                       # Gemini hash reference
    | Web(url?, org?)                  # Web workspace
    | Concrete(string)                 # Already resolved path
```

**Pattern Match Types (CRITICAL):**
```
MatchType =
    | Exact                            # workspace == pattern (fixes the bug!)
    | Prefix                           # workspace.startswith(pattern)
    | Contains                         # pattern in workspace (old buggy behavior)
    | Glob                             # fnmatch-style: */projects/auth*
```

**Examples:**
```python
WorkspaceSpec.All                                    # --aw flag
WorkspaceSpec.Current                                # no args, use CWD
WorkspaceSpec.Project("testproj")                    # --project testproj or @testproj
WorkspaceSpec.Path("/home/user/projects/auth")       # explicit full path
WorkspaceSpec.Encoded("home-user-projects-auth")     # encoded form
WorkspaceSpec.Pattern("/home/user/projects/auth", Exact)  # exact match!
WorkspaceSpec.Pattern("auth", Contains)              # old buggy behavior (avoid!)
WorkspaceSpec.Hash("abc123def")                      # Gemini hash
WorkspaceSpec.Web(org="myorg")                       # Web workspace
```

**Resolution Context Required:**
- Home (to enumerate workspaces)
- Agent indices (Claude dirs, Codex index, Gemini index)
- Project definitions
- CWD for Current resolution

---

### 1.3 Session Specification

```
SessionSpec =
    | All                              # All sessions (apply filters)
    | Filtered(filters)                # All sessions matching filters
    | List([sessions])                 # Concrete session list
    | ByFile(filename)                 # Single session by filename
    | ById(session_id)                 # Single session by ID
    | ByIndex(index)                   # Nth session (for commands like "show 1")
```

**Filter Specification:**
```
SessionFilters = {
    agent: AgentSpec,                  # claude | codex | gemini | auto
    since: datetime?,                  # --since
    until: datetime?,                  # --until
    min_messages: int?,                # Minimum message count
    has_tool: string?,                 # Sessions using specific tool
}

AgentSpec =
    | Auto                             # All available agents
    | Single(agent_name)               # Specific agent
    | Multiple([agent_names])          # Multiple specific agents
```

**Examples:**
```python
SessionSpec.All                                      # All sessions
SessionSpec.Filtered({agent: Auto, since: "2025-01-01"})
SessionSpec.List([session1, session2])               # Concrete
SessionSpec.ByFile("session-001.jsonl")              # By filename
SessionSpec.ById("abc123")                           # By session ID
```

---

## 2. Record Types

### 2.1 Scope Record

```python
@dataclass
class ScopeRecord:
    home: HomeSpec
    workspace: WorkspaceSpec
    sessions: SessionSpec
```

### 2.2 Project Record (Special)

```python
@dataclass
class ProjectRecord:
    project: str                       # Project name
    sessions: SessionSpec = All        # Session spec applied after expansion
```

**Note:** ProjectRecord is a convenience that expands to multiple ScopeRecords.

### 2.3 Record Union

```python
Record = ScopeRecord | ProjectRecord
```

---

## 3. Scope Types

### 3.1 Template Scope

Contains specifications that may need resolution:

```python
TemplateScope = List[Record]
```

**Examples:**
```python
# "session list" from project workspace
[ProjectRecord("testproj")]

# "session list --wsl"
[ScopeRecord(Category("wsl"), All, All)]

# "session list /home/user/projects/auth"
[ScopeRecord(All, Path("/home/user/projects/auth"), All)]

# "session list --ah --aw"
[ScopeRecord(All, All, All)]
```

### 3.2 Concrete Scope

Fully resolved - no specifications, only values:

```python
@dataclass
class ConcreteRecord:
    home: str                          # "local", "wsl:Ubuntu", etc.
    workspace: str                     # Full workspace path
    sessions: List[SessionDict]        # Actual session objects

ConcreteScope = List[ConcreteRecord]
```

---

## 4. Resolution Context

Resolution needs environment context:

```python
@dataclass
class ResolutionContext:
    # Platform
    platform: str                      # "linux", "wsl", "windows", "darwin"
    is_wsl: bool                       # Running inside WSL?

    # Current location
    cwd: Path                          # Current working directory
    cwd_home: str | None               # Home of CWD if in workspace
    cwd_workspace: str | None          # Workspace path of CWD if in workspace
    cwd_project: str | None            # Project name if CWD is in a project

    # Available resources
    available_homes: Dict[str, List[str]]  # category → [items]
    # e.g., {"wsl": ["Ubuntu", "Debian"], "windows": ["alice", "bob"], "remote": ["dev", "prod"]}

    # Configuration
    project_config: Dict[str, ProjectDef]  # project name → definition
    agent_config: Dict[str, AgentConfig]   # agent name → config

    # Agent indices (lazy-loaded)
    claude_projects_dir: Path
    codex_index: CodexIndex | None
    gemini_index: GeminiIndex | None
```

**Building Context:**
```python
def build_resolution_context() -> ResolutionContext:
    """Build context from current environment."""
    ctx = ResolutionContext()
    ctx.platform = detect_platform()
    ctx.is_wsl = is_running_in_wsl()
    ctx.cwd = Path.cwd()
    ctx.cwd_home, ctx.cwd_workspace = detect_workspace_from_cwd()
    ctx.cwd_project = get_alias_for_workspace(ctx.cwd_workspace, ctx.cwd_home)
    ctx.available_homes = enumerate_available_homes()
    ctx.project_config = load_project_config()
    # ... etc
    return ctx
```

---

## 5. Resolution Pipeline

### 5.1 Pipeline Stages

```
Stage 0: Parse      → TemplateScope        (command args → initial scope)
Stage 1: Projects   → TemplateScope        (expand ProjectRecords)
Stage 2: Homes      → TemplateScope        (resolve HomeSpecs)
Stage 3: Workspaces → TemplateScope        (resolve WorkspaceSpecs)
Stage 4: Sessions   → ConcreteScope        (resolve SessionSpecs)
```

### 5.2 Stage 0: Parse Command to Template

```python
def parse_command_to_template(args, context: ResolutionContext) -> TemplateScope:
    """Convert command arguments to initial template scope."""

    # Determine home spec
    if args.all_homes:
        home = HomeSpec.All
    elif args.wsl:
        home = HomeSpec.Category("wsl") if args.wsl == True else HomeSpec.CategoryItem("wsl", args.wsl)
    elif args.windows:
        home = HomeSpec.Category("windows") if args.windows == True else HomeSpec.CategoryItem("windows", args.windows)
    elif args.remote:
        home = HomeSpec.Category("remote") if args.remote == True else HomeSpec.CategoryItem("remote", args.remote)
    else:
        home = HomeSpec.Local  # Default

    # Determine workspace spec
    if args.project:
        return [ProjectRecord(args.project, session_spec)]
    elif args.all_workspaces:
        workspace = WorkspaceSpec.All
    elif args.patterns:
        # Explicit patterns - use EXACT matching
        return [ScopeRecord(home, WorkspaceSpec.Pattern(p, MatchType.Exact), session_spec)
                for p in args.patterns]
    elif args.this_only:
        workspace = WorkspaceSpec.Current
    elif context.cwd_project and not args.this_only:
        # Implicit project detection - KEY FIX!
        return [ProjectRecord(context.cwd_project, session_spec)]
    elif context.cwd_workspace:
        workspace = WorkspaceSpec.Current
    else:
        workspace = WorkspaceSpec.All

    # Determine session spec
    session_spec = build_session_spec(args)

    return [ScopeRecord(home, workspace, session_spec)]
```

### 5.3 Stage 1: Resolve Projects

```python
def resolve_projects(scope: TemplateScope, context: ResolutionContext) -> TemplateScope:
    """Expand ProjectRecords to ScopeRecords."""
    result = []
    for record in scope:
        if isinstance(record, ProjectRecord):
            project_def = context.project_config.get(record.project)
            if not project_def:
                raise ResolutionError(f"Project '{record.project}' not found")

            # Expand project to its workspace definitions
            for home_key, workspaces in project_def.items():
                home = HomeSpec.Concrete(home_key)
                for ws in workspaces:
                    # Use EXACT path from project definition
                    workspace = WorkspaceSpec.Path(ws)
                    result.append(ScopeRecord(home, workspace, record.sessions))
        else:
            result.append(record)
    return result
```

### 5.4 Stage 2: Resolve Homes

```python
def resolve_homes(scope: TemplateScope, context: ResolutionContext) -> TemplateScope:
    """Resolve HomeSpecs to concrete home strings."""
    result = []
    for record in scope:
        homes = expand_home_spec(record.home, context)
        for home in homes:
            result.append(ScopeRecord(
                HomeSpec.Concrete(home),
                record.workspace,
                record.sessions
            ))
    return result

def expand_home_spec(spec: HomeSpec, context: ResolutionContext) -> List[str]:
    """Expand a HomeSpec to list of concrete home strings."""
    match spec:
        case HomeSpec.All:
            return get_all_available_homes(context)
        case HomeSpec.Local:
            return ["local"]
        case HomeSpec.Current:
            if context.cwd_home:
                return [context.cwd_home]
            return ["local"]  # Default if not in workspace
        case HomeSpec.Category(cat):
            return [f"{cat}:{item}" for item in context.available_homes.get(cat, [])]
        case HomeSpec.CategoryItem(cat, item):
            return [f"{cat}:{item}"]
        case HomeSpec.Concrete(home):
            return [home]
```

### 5.5 Stage 3: Resolve Workspaces

```python
def resolve_workspaces(scope: TemplateScope, context: ResolutionContext) -> TemplateScope:
    """Resolve WorkspaceSpecs to concrete workspace paths."""
    result = []
    for record in scope:
        home = record.home.value  # Already concrete from Stage 2
        workspaces = expand_workspace_spec(record.workspace, home, context)
        for ws in workspaces:
            result.append(ScopeRecord(
                record.home,
                WorkspaceSpec.Concrete(ws),
                record.sessions
            ))
    return result

def expand_workspace_spec(spec: WorkspaceSpec, home: str, context: ResolutionContext) -> List[str]:
    """Expand a WorkspaceSpec to list of concrete workspace paths."""
    match spec:
        case WorkspaceSpec.All:
            return enumerate_workspaces_in_home(home, context)
        case WorkspaceSpec.Current:
            if context.cwd_workspace:
                return [context.cwd_workspace]
            raise ResolutionError("Not in a workspace")
        case WorkspaceSpec.Project(name):
            # Should have been resolved in Stage 1
            raise ResolutionError("Unresolved project reference")
        case WorkspaceSpec.Path(path):
            return [path]  # Already concrete
        case WorkspaceSpec.Encoded(encoded):
            return [decode_workspace_path(encoded)]
        case WorkspaceSpec.Pattern(pattern, match_type):
            return match_workspaces(home, pattern, match_type, context)
        case WorkspaceSpec.Hash(hash):
            return [resolve_gemini_hash(hash, context)]
        case WorkspaceSpec.Web(url, org):
            return [f"web:{org or 'default'}"]
        case WorkspaceSpec.Concrete(ws):
            return [ws]

def match_workspaces(home: str, pattern: str, match_type: MatchType, context) -> List[str]:
    """Match workspaces against pattern with specified match semantics."""
    all_workspaces = enumerate_workspaces_in_home(home, context)

    match match_type:
        case MatchType.Exact:
            # THE FIX: Exact equality, no substring!
            return [ws for ws in all_workspaces if ws == pattern]
        case MatchType.Prefix:
            return [ws for ws in all_workspaces if ws.startswith(pattern)]
        case MatchType.Contains:
            # Old buggy behavior - use sparingly!
            return [ws for ws in all_workspaces if pattern in ws]
        case MatchType.Glob:
            import fnmatch
            return [ws for ws in all_workspaces if fnmatch.fnmatch(ws, pattern)]
```

### 5.6 Stage 4: Resolve Sessions

```python
def resolve_sessions(scope: TemplateScope, context: ResolutionContext) -> ConcreteScope:
    """Resolve SessionSpecs to concrete session lists."""
    result = []
    for record in scope:
        home = record.home.value      # Concrete string
        workspace = record.workspace.value  # Concrete string
        sessions = collect_sessions(home, workspace, record.sessions, context)
        if sessions:  # Only include if sessions exist
            result.append(ConcreteRecord(home, workspace, sessions))
    return result

def collect_sessions(home: str, workspace: str, spec: SessionSpec, context) -> List[dict]:
    """Collect sessions matching specification."""
    match spec:
        case SessionSpec.All:
            return collect_all_sessions(home, workspace, context)
        case SessionSpec.Filtered(filters):
            sessions = collect_all_sessions(home, workspace, context)
            return apply_filters(sessions, filters)
        case SessionSpec.List(sessions):
            return sessions  # Already concrete
        case SessionSpec.ByFile(filename):
            return [find_session_by_file(home, workspace, filename, context)]
        case SessionSpec.ById(session_id):
            return [find_session_by_id(home, workspace, session_id, context)]

def collect_all_sessions(home: str, workspace: str, context) -> List[dict]:
    """Collect all sessions for a specific home/workspace.

    CRITICAL: Uses EXACT workspace matching, not substring!
    """
    sessions = []

    # Claude sessions
    claude_sessions = scan_claude_sessions(home, workspace, context)
    for s in claude_sessions:
        if s['workspace'] == workspace:  # EXACT match!
            sessions.append(s)

    # Codex sessions
    codex_sessions = scan_codex_sessions(home, workspace, context)
    for s in codex_sessions:
        ws = s.get('workspace_readable') or s.get('workspace', '')
        if ws == workspace:  # EXACT match!
            sessions.append(s)

    # Gemini sessions
    gemini_sessions = scan_gemini_sessions(home, workspace, context)
    for s in gemini_sessions:
        ws = s.get('workspace_readable') or s.get('workspace', '')
        if ws == workspace:  # EXACT match!
            sessions.append(s)

    return sessions
```

---

## 6. Agent-Specific Resolution

Different agents need different handling:

### 6.1 Agent Configuration

```python
@dataclass
class AgentConfig:
    name: str                          # "claude", "codex", "gemini"
    home_dir: Path                     # Base directory
    session_pattern: str               # Glob pattern for session files
    index_file: Path | None            # Index file if exists
    workspace_encoding: str            # "directory", "metadata", "hash"

AGENT_CONFIGS = {
    "claude": AgentConfig(
        name="claude",
        home_dir=Path.home() / ".claude" / "projects",
        session_pattern="*.jsonl",
        index_file=None,  # Directory structure is the index
        workspace_encoding="directory",  # Workspace = directory name
    ),
    "codex": AgentConfig(
        name="codex",
        home_dir=Path.home() / ".codex" / "sessions",
        session_pattern="**/rollout-*.jsonl",
        index_file=Path.home() / ".codex" / "sessions" / "codex_index.json",
        workspace_encoding="metadata",  # Workspace in session metadata
    ),
    "gemini": AgentConfig(
        name="gemini",
        home_dir=Path.home() / ".gemini" / "tmp",
        session_pattern="*.json",
        index_file=Path.home() / ".gemini" / "tmp" / "gemini_index.json",
        workspace_encoding="hash",  # Workspace is hash-based
    ),
}
```

### 6.2 Workspace Enumeration by Agent

```python
def enumerate_workspaces_in_home(home: str, context: ResolutionContext) -> List[str]:
    """Enumerate all workspaces in a home, combining all agents."""
    workspaces = set()

    for agent_name, config in AGENT_CONFIGS.items():
        agent_workspaces = enumerate_agent_workspaces(home, agent_name, config, context)
        workspaces.update(agent_workspaces)

    return sorted(workspaces)

def enumerate_agent_workspaces(home: str, agent: str, config: AgentConfig, context) -> List[str]:
    """Enumerate workspaces for a specific agent in a home."""
    match config.workspace_encoding:
        case "directory":
            # Claude: directory names are encoded workspaces
            return enumerate_claude_workspaces(home, config, context)
        case "metadata":
            # Codex: workspaces extracted from session metadata via index
            return enumerate_codex_workspaces(home, config, context)
        case "hash":
            # Gemini: hash-based workspace IDs via index
            return enumerate_gemini_workspaces(home, config, context)
```

---

## 7. Workspace Representation Forms

### 7.1 Representation Types

A workspace can have multiple representations:

```python
@dataclass
class WorkspaceRepresentations:
    canonical: str                     # Canonical form (full path): /home/user/projects/auth
    encoded: str | None                # Claude-style encoding: home-user-projects-auth
    hash: str | None                   # Gemini hash: abc123def
    display: str                       # Human-readable: ~/projects/auth
    basename: str                      # Just the name: auth
```

### 7.2 Resolution Between Forms

```python
def resolve_workspace_representation(input: str, context: ResolutionContext) -> str:
    """Resolve any workspace representation to canonical form."""

    # Already canonical (full path)?
    if input.startswith('/') or (len(input) > 1 and input[1] == ':'):
        return input

    # Encoded form (contains hyphens, looks like path)?
    if looks_like_encoded_workspace(input):
        return decode_workspace_path(input)

    # Hash form (hex string)?
    if looks_like_hash(input):
        return resolve_gemini_hash(input, context)

    # Basename only - ambiguous, need context
    if '/' not in input and '-' not in input:
        # Try to find unique match
        matches = find_workspaces_by_basename(input, context)
        if len(matches) == 1:
            return matches[0]
        elif len(matches) == 0:
            raise ResolutionError(f"No workspace found matching '{input}'")
        else:
            raise ResolutionError(f"Ambiguous workspace '{input}': {matches}")

    return input  # Return as-is, let later stages handle
```

---

## 8. Web Sessions

Web sessions don't follow Home/Workspace/Session hierarchy:

```python
@dataclass
class WebScopeRecord:
    organization: str | None
    conversation_id: str | None
    filters: SessionFilters

def resolve_web_scope(spec: WebScopeRecord, context) -> List[WebSession]:
    """Resolve web scope to concrete web sessions."""
    # Web sessions fetched via API, not filesystem
    return fetch_web_sessions(spec.organization, spec.conversation_id, spec.filters)
```

**Integration with main scope:**
```python
Record = ScopeRecord | ProjectRecord | WebScopeRecord
```

---

## 9. Error Handling

### 9.1 Error Types

```python
@dataclass
class ResolutionError:
    stage: str                         # "project", "home", "workspace", "session"
    spec: Any                          # The spec that failed
    reason: str                        # Human-readable reason
    suggestions: List[str]             # Possible corrections

@dataclass
class ResolutionWarning:
    stage: str
    message: str
```

### 9.2 Resolution Result

```python
@dataclass
class ResolutionResult:
    scope: ConcreteScope               # Resolved scope (may be partial)
    errors: List[ResolutionError]      # Errors encountered
    warnings: List[ResolutionWarning]  # Warnings (non-fatal)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def partial(self) -> bool:
        return len(self.errors) > 0 and len(self.scope) > 0
```

---

## 10. Full Pipeline Example

### Command: `session list` (from project workspace)

**Step 0: Build Context**
```python
context = ResolutionContext(
    platform="linux",
    is_wsl=True,
    cwd=Path("/home/user/projects/auth"),
    cwd_home="local",
    cwd_workspace="/home/user/projects/auth",
    cwd_project="testproj",  # Auto-detected!
    available_homes={"wsl": ["Ubuntu"], "windows": [], "remote": ["dev"]},
    project_config={
        "testproj": {
            "local": ["/home/user/projects/auth"],
            "wsl:Ubuntu": ["/home/user/projects/auth"]
        }
    },
    ...
)
```

**Step 1: Parse Command (Stage 0)**
```python
# No explicit args, but in project workspace
# OLD BUGGY: [ScopeRecord(Local, Current, All)]  # Uses CWD, then substring match
# NEW FIXED: [ProjectRecord("testproj", All)]    # Uses project definition!

template = [ProjectRecord("testproj", SessionSpec.All)]
```

**Step 2: Resolve Projects (Stage 1)**
```python
# ProjectRecord("testproj") expands to project's defined workspaces
template = [
    ScopeRecord(Concrete("local"), Path("/home/user/projects/auth"), All),
    ScopeRecord(Concrete("wsl:Ubuntu"), Path("/home/user/projects/auth"), All),
]
```

**Step 3: Resolve Homes (Stage 2)**
```python
# Already concrete, no change
template = [
    ScopeRecord(Concrete("local"), Path("/home/user/projects/auth"), All),
    ScopeRecord(Concrete("wsl:Ubuntu"), Path("/home/user/projects/auth"), All),
]
```

**Step 4: Resolve Workspaces (Stage 3)**
```python
# Path specs are already concrete
template = [
    ScopeRecord(Concrete("local"), Concrete("/home/user/projects/auth"), All),
    ScopeRecord(Concrete("wsl:Ubuntu"), Concrete("/home/user/projects/auth"), All),
]
```

**Step 5: Resolve Sessions (Stage 4)**
```python
# Collect sessions with EXACT workspace match
concrete = [
    ConcreteRecord(
        home="local",
        workspace="/home/user/projects/auth",
        sessions=[
            {"file": "auth-session-00.jsonl", "workspace": "/home/user/projects/auth", ...},
            {"file": "auth-session-01.jsonl", "workspace": "/home/user/projects/auth", ...},
            {"file": "rollout-codex-00.jsonl", "workspace": "/home/user/projects/auth", ...},
        ]
    ),
    ConcreteRecord(
        home="wsl:Ubuntu",
        workspace="/home/user/projects/auth",
        sessions=[
            {"file": "auth-session-02.jsonl", "workspace": "/home/user/projects/auth", ...},
        ]
    ),
]
```

**Result: 4 sessions** (not 9+ with substring bug!)

---

## 11. Key Fixes for Original Bug

### The Bug
```
session list (from project workspace) → 312 sessions
project stats (same workspace)        → 302 sessions
```

### Root Cause in v1
1. `session list` used CWD workspace as pattern
2. Pattern matching used substring: `pattern in workspace`
3. `"/home/user/projects/auth"` matched `"/home/user/projects/auth-infra"`

### Fix in v2
1. `session list` detects project from CWD → `ProjectRecord("testproj")`
2. Project expands to concrete `Path("/home/user/projects/auth")` specs
3. Session collection uses EXACT match: `workspace == "/home/user/projects/auth"`
4. `"/home/user/projects/auth-infra"` does NOT match

---

## 12. Command Integration Pattern

All commands use the same pattern:

```python
def cmd_session_list(args):
    # 1. Build context
    context = build_resolution_context()

    # 2. Parse to template
    template = parse_command_to_template(args, context)

    # 3. Resolve through pipeline
    result = resolve_scope(template, context)

    # 4. Handle errors
    if not result.success:
        for error in result.errors:
            sys.stderr.write(f"Error: {error.reason}\n")
        if not result.partial:
            sys.exit(1)

    # 5. Use concrete scope
    sessions = flatten_sessions(result.scope)
    print_sessions_output(sessions, ...)

def cmd_session_export(args):
    context = build_resolution_context()
    template = parse_command_to_template(args, context)
    result = resolve_scope(template, context)
    # ... same pattern

def cmd_session_stats(args):
    context = build_resolution_context()
    template = parse_command_to_template(args, context)
    result = resolve_scope(template, context)
    # ... same pattern
```

**Consistency guaranteed** - all commands use same resolution pipeline!

---

## 13. Implementation Phases

### Phase 1: Core Types
- Define specification types (HomeSpec, WorkspaceSpec, SessionSpec)
- Define record types (ScopeRecord, ProjectRecord)
- Define context structure

### Phase 2: Resolution Functions
- Implement each stage resolver
- Implement workspace matching with proper match types
- Implement agent-specific workspace enumeration

### Phase 3: Command Integration
- Refactor `session list` to use pipeline
- Refactor `session export` to use pipeline
- Refactor `session stats` to use pipeline
- Refactor `project show` to use pipeline

### Phase 4: Test & Validate
- Run existing consistency tests (should pass!)
- Add unit tests for each resolution stage
- Add integration tests for full pipeline

---

## 14. Summary

### Key Architectural Improvements

1. **Typed Specifications** - HomeSpec, WorkspaceSpec, SessionSpec with proper variants
2. **Resolution Context** - Platform, CWD, available homes, project config
3. **Progressive Pipeline** - Parse → Projects → Homes → Workspaces → Sessions
4. **Match Type Control** - Explicit Exact vs Contains vs Glob
5. **Agent Awareness** - Different handling for Claude/Codex/Gemini
6. **Multiple Representations** - Path, encoded, hash, display forms
7. **Web Support** - Separate handling for web sessions
8. **Error Handling** - Structured errors with suggestions

### The Fix

**Before:** Commands resolved context differently, some using substring matching
**After:** All commands use same pipeline with EXACT matching by default

**Result:** Consistent behavior across all commands!
