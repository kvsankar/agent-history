# Pipeline Architecture

## Overview

Complete flow from command line to output:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INPUT                                      │
│                    $ agent-history session list --wsl                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                             CLI PARSER                                       │
│  • Parse command line arguments                                              │
│  • Validate syntax                                                           │
│  • Build CommandRequest                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          CONTEXT BUILDER                                     │
│  • Detect platform (linux, wsl, windows)                                     │
│  • Detect CWD workspace/project                                              │
│  • Enumerate available homes                                                 │
│  • Load configuration                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          SCOPE RESOLVER                                      │
│  Stage 0: Parse args → TemplateScope                                         │
│  Stage 1: Resolve Projects                                                   │
│  Stage 2: Resolve Homes                                                      │
│  Stage 3: Resolve Workspaces                                                 │
│  Stage 4: Resolve Sessions                                                   │
│  Output: ConcreteScope                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          VERB DISPATCHER                                     │
│  • Route to appropriate VerbHandler based on command                         │
│  • Pass ConcreteScope to handler                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           VERB HANDLER                                       │
│  • Execute command-specific logic                                            │
│  • ListHandler, ExportHandler, StatsHandler, etc.                            │
│  • Produce CommandResult                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         OUTPUT FORMATTER                                     │
│  • Format results (table, json, csv, markdown)                               │
│  • Apply output options (--format, --output)                                 │
│  • Write to stdout/file                                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              OUTPUT                                          │
│                    AGENT  HOME   WORKSPACE  FILE  ...                        │
│                    claude local  /home/...  ...                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. CLI Parser

### Responsibility
- Parse command line arguments using argparse
- Validate syntax and argument combinations
- Build structured CommandRequest

### Entity: `CLIParser`

```python
class CLIParser:
    """Parse command line into structured request."""

    def __init__(self):
        self.parser = self._build_parser()

    def parse(self, argv: List[str]) -> CommandRequest:
        """Parse command line arguments.

        Args:
            argv: Command line arguments (sys.argv[1:])

        Returns:
            CommandRequest with parsed command and options
        """
        args = self.parser.parse_args(argv)
        return self._build_request(args)

    def _build_parser(self) -> argparse.ArgumentParser:
        """Build argument parser with all subcommands."""
        parser = argparse.ArgumentParser(prog='agent-history')
        subparsers = parser.add_subparsers(dest='resource')

        # session subcommand
        session_parser = subparsers.add_parser('session')
        session_subparsers = session_parser.add_subparsers(dest='verb')

        # session list
        list_parser = session_subparsers.add_parser('list')
        self._add_scope_args(list_parser)
        self._add_output_args(list_parser)

        # session export
        export_parser = session_subparsers.add_parser('export')
        self._add_scope_args(export_parser)
        self._add_export_args(export_parser)

        # ... more subcommands

        return parser

    def _add_scope_args(self, parser):
        """Add scope-related arguments."""
        # Home selection
        home_group = parser.add_mutually_exclusive_group()
        home_group.add_argument('--wsl', nargs='?', const=True)
        home_group.add_argument('--windows', nargs='?', const=True)
        home_group.add_argument('--remote', nargs='?', const=True)
        home_group.add_argument('--ah', '--all-homes', action='store_true')

        # Workspace selection
        parser.add_argument('--project', '-p')
        parser.add_argument('--aw', '--all-workspaces', action='store_true')
        parser.add_argument('--this', action='store_true')
        parser.add_argument('patterns', nargs='*')

        # Session filters
        parser.add_argument('--agent', choices=['auto', 'claude', 'codex', 'gemini'])
        parser.add_argument('--since')
        parser.add_argument('--until')

    def _build_request(self, args) -> CommandRequest:
        """Convert parsed args to CommandRequest."""
        return CommandRequest(
            resource=args.resource,
            verb=args.verb,
            scope_args=ScopeArgs(
                home_spec=self._parse_home_spec(args),
                workspace_spec=self._parse_workspace_spec(args),
                session_spec=self._parse_session_spec(args),
            ),
            output_args=OutputArgs(
                format=getattr(args, 'format', None),
                output=getattr(args, 'output', None),
            ),
            verb_args=self._parse_verb_args(args),
        )
```

### Data Structures

```python
@dataclass
class CommandRequest:
    """Structured representation of a command."""
    resource: str              # "session", "project", "ws"
    verb: str                  # "list", "export", "stats", "show"
    scope_args: ScopeArgs      # Scope-related arguments
    output_args: OutputArgs    # Output formatting arguments
    verb_args: Dict[str, Any]  # Verb-specific arguments

@dataclass
class ScopeArgs:
    """Arguments related to scope selection."""
    home_spec: HomeSpec
    workspace_spec: WorkspaceSpec
    session_spec: SessionSpec

@dataclass
class OutputArgs:
    """Arguments related to output formatting."""
    format: str | None         # "table", "json", "csv"
    output: Path | None        # Output file path
    legacy_format: bool        # Use legacy output format
```

### Algorithm

```
PARSE(argv):
    1. args = argparse.parse(argv)
    2. Validate argument combinations:
       - --this and --project are mutually exclusive
       - --aw and explicit patterns are mutually exclusive
       - etc.
    3. Build HomeSpec from args:
       - --ah → HomeSpec.All
       - --wsl → HomeSpec.Category("wsl") or HomeSpec.CategoryItem("wsl", value)
       - etc.
    4. Build WorkspaceSpec from args:
       - --project → WorkspaceSpec.Project(name)
       - --aw → WorkspaceSpec.All
       - patterns → [WorkspaceSpec.Pattern(p, Exact) for p in patterns]
       - (none) → WorkspaceSpec.Current (resolved later)
    5. Build SessionSpec from args:
       - Combine agent, since, until into SessionSpec.Filtered
    6. Return CommandRequest
```

---

## 2. Context Builder

### Responsibility
- Detect runtime environment (platform, WSL, etc.)
- Detect current workspace and project from CWD
- Enumerate available homes (WSL distros, Windows users, remotes)
- Load configuration files

### Entity: `ContextBuilder`

```python
class ContextBuilder:
    """Build resolution context from environment."""

    def build(self) -> ResolutionContext:
        """Build context by detecting environment."""
        ctx = ResolutionContext()

        # Platform detection
        ctx.platform = self._detect_platform()
        ctx.is_wsl = self._is_running_in_wsl()

        # Current location
        ctx.cwd = Path.cwd()
        ctx.cwd_home, ctx.cwd_workspace = self._detect_workspace_from_cwd()
        ctx.cwd_project = self._detect_project_from_workspace(
            ctx.cwd_workspace, ctx.cwd_home
        )

        # Available resources
        ctx.available_homes = self._enumerate_available_homes()

        # Configuration
        ctx.project_config = self._load_project_config()
        ctx.agent_config = self._load_agent_config()

        # Agent indices (lazy load on demand)
        ctx.claude_projects_dir = self._get_claude_projects_dir()
        ctx.codex_index = None  # Lazy
        ctx.gemini_index = None  # Lazy

        return ctx

    def _detect_platform(self) -> str:
        """Detect current platform."""
        if sys.platform == 'win32':
            return 'windows'
        elif self._is_running_in_wsl():
            return 'wsl'
        elif sys.platform == 'darwin':
            return 'darwin'
        else:
            return 'linux'

    def _detect_workspace_from_cwd(self) -> Tuple[str | None, str | None]:
        """Detect if CWD is within a workspace."""
        cwd = Path.cwd()

        # Check Claude projects
        claude_dir = Path.home() / '.claude' / 'projects'
        if claude_dir in cwd.parents or cwd == claude_dir:
            # Extract workspace from path
            relative = cwd.relative_to(claude_dir)
            workspace_encoded = relative.parts[0] if relative.parts else None
            if workspace_encoded:
                workspace = decode_workspace_path(workspace_encoded)
                return ('local', workspace)

        # Check if CWD itself is a workspace
        for agent in ['claude', 'codex', 'gemini']:
            workspace = self._find_workspace_for_path(cwd, agent)
            if workspace:
                return ('local', workspace)

        return (None, None)

    def _detect_project_from_workspace(self, workspace: str | None, home: str | None) -> str | None:
        """Check if workspace belongs to a project."""
        if not workspace or not home:
            return None

        projects = self._load_project_config()
        for project_name, project_def in projects.items():
            home_workspaces = project_def.get(home, [])
            if workspace in home_workspaces:
                return project_name

        return None

    def _enumerate_available_homes(self) -> Dict[str, List[str]]:
        """Enumerate all available homes by category."""
        homes = {
            'wsl': [],
            'windows': [],
            'remote': [],
        }

        # WSL distros (if on Windows or WSL)
        if self._can_access_wsl():
            homes['wsl'] = self._list_wsl_distros()

        # Windows users (if on WSL)
        if self._can_access_windows():
            homes['windows'] = self._list_windows_users()

        # Configured remotes
        homes['remote'] = self._list_configured_remotes()

        return homes
```

### Algorithm

```
BUILD_CONTEXT():
    1. Detect platform:
       - Check sys.platform
       - Check /proc/version for WSL
       - Return "linux", "wsl", "windows", or "darwin"

    2. Detect CWD workspace:
       - Check if CWD is under ~/.claude/projects/
       - Check if CWD matches any workspace in indices
       - Return (home, workspace) or (None, None)

    3. Detect CWD project:
       - If workspace found, search project config
       - Return project name or None

    4. Enumerate available homes:
       - WSL: Run `wsl -l -q` or check /mnt/wsl
       - Windows: Check /mnt/c/Users/* or C:\Users\*
       - Remote: Read from config file

    5. Load configurations:
       - Project config from ~/.agent-history/projects.yaml
       - Agent config (paths, patterns)

    6. Return ResolutionContext
```

---

## 3. Scope Resolver

### Responsibility
- Convert CommandRequest.scope_args to ConcreteScope
- Progressive resolution through stages
- Handle errors and partial resolution

### Entity: `ScopeResolver`

```python
class ScopeResolver:
    """Resolve scope specifications to concrete scope."""

    def __init__(self, context: ResolutionContext):
        self.context = context
        self.project_resolver = ProjectResolver(context)
        self.home_resolver = HomeResolver(context)
        self.workspace_resolver = WorkspaceResolver(context)
        self.session_resolver = SessionResolver(context)

    def resolve(self, scope_args: ScopeArgs) -> ResolutionResult:
        """Resolve scope args through full pipeline.

        Args:
            scope_args: Scope arguments from command

        Returns:
            ResolutionResult with concrete scope or errors
        """
        errors = []
        warnings = []

        # Stage 0: Build initial template
        template = self._build_template(scope_args)
        self._log_stage("Initial template", template)

        # Stage 1: Resolve projects
        template, stage_errors = self.project_resolver.resolve(template)
        errors.extend(stage_errors)
        self._log_stage("After project resolution", template)

        # Stage 2: Resolve homes
        template, stage_errors = self.home_resolver.resolve(template)
        errors.extend(stage_errors)
        self._log_stage("After home resolution", template)

        # Stage 3: Resolve workspaces
        template, stage_errors = self.workspace_resolver.resolve(template)
        errors.extend(stage_errors)
        self._log_stage("After workspace resolution", template)

        # Stage 4: Resolve sessions
        concrete, stage_errors = self.session_resolver.resolve(template)
        errors.extend(stage_errors)
        self._log_stage("Final concrete scope", concrete)

        return ResolutionResult(
            scope=concrete,
            errors=errors,
            warnings=warnings,
        )

    def _build_template(self, scope_args: ScopeArgs) -> TemplateScope:
        """Convert scope args to initial template."""
        # Handle implicit project detection
        if (scope_args.workspace_spec == WorkspaceSpec.Current and
            self.context.cwd_project):
            # Implicit project - use project's workspaces
            return [ProjectRecord(
                self.context.cwd_project,
                scope_args.session_spec
            )]

        # Explicit scope
        return [ScopeRecord(
            scope_args.home_spec,
            scope_args.workspace_spec,
            scope_args.session_spec,
        )]
```

### Stage Resolvers

```python
class ProjectResolver:
    """Stage 1: Resolve ProjectRecords to ScopeRecords."""

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[Error]]:
        result = []
        errors = []

        for record in scope:
            if isinstance(record, ProjectRecord):
                expanded, err = self._expand_project(record)
                if err:
                    errors.append(err)
                else:
                    result.extend(expanded)
            else:
                result.append(record)

        return result, errors

    def _expand_project(self, record: ProjectRecord) -> Tuple[List[ScopeRecord], Error | None]:
        project_def = self.context.project_config.get(record.project)
        if not project_def:
            return [], ResolutionError(
                stage="project",
                spec=record,
                reason=f"Project '{record.project}' not found",
                suggestions=list(self.context.project_config.keys())
            )

        records = []
        for home_key, workspaces in project_def.items():
            for ws in workspaces:
                records.append(ScopeRecord(
                    home=HomeSpec.Concrete(home_key),
                    workspace=WorkspaceSpec.Path(ws),
                    sessions=record.sessions,
                ))

        return records, None


class HomeResolver:
    """Stage 2: Resolve HomeSpecs to concrete home strings."""

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[Error]]:
        result = []
        errors = []

        for record in scope:
            homes, err = self._expand_home(record.home)
            if err:
                errors.append(err)
                continue

            for home in homes:
                result.append(ScopeRecord(
                    home=HomeSpec.Concrete(home),
                    workspace=record.workspace,
                    sessions=record.sessions,
                ))

        return result, errors

    def _expand_home(self, spec: HomeSpec) -> Tuple[List[str], Error | None]:
        match spec:
            case HomeSpec.All:
                return self._get_all_homes(), None
            case HomeSpec.Local:
                return ["local"], None
            case HomeSpec.Current:
                if self.context.cwd_home:
                    return [self.context.cwd_home], None
                return ["local"], None
            case HomeSpec.Category(cat):
                items = self.context.available_homes.get(cat, [])
                if not items:
                    return [], ResolutionError(
                        stage="home",
                        spec=spec,
                        reason=f"No {cat} homes available",
                    )
                return [f"{cat}:{item}" for item in items], None
            case HomeSpec.CategoryItem(cat, item):
                return [f"{cat}:{item}"], None
            case HomeSpec.Concrete(home):
                return [home], None


class WorkspaceResolver:
    """Stage 3: Resolve WorkspaceSpecs to concrete paths."""

    def resolve(self, scope: TemplateScope) -> Tuple[TemplateScope, List[Error]]:
        result = []
        errors = []

        for record in scope:
            home = record.home.value  # Concrete from Stage 2
            workspaces, err = self._expand_workspace(record.workspace, home)
            if err:
                errors.append(err)
                continue

            for ws in workspaces:
                result.append(ScopeRecord(
                    home=record.home,
                    workspace=WorkspaceSpec.Concrete(ws),
                    sessions=record.sessions,
                ))

        return result, errors

    def _expand_workspace(self, spec: WorkspaceSpec, home: str) -> Tuple[List[str], Error | None]:
        match spec:
            case WorkspaceSpec.All:
                return self._enumerate_workspaces(home), None
            case WorkspaceSpec.Current:
                if self.context.cwd_workspace:
                    return [self.context.cwd_workspace], None
                return [], ResolutionError(
                    stage="workspace",
                    spec=spec,
                    reason="Not in a workspace",
                )
            case WorkspaceSpec.Path(path):
                return [path], None
            case WorkspaceSpec.Encoded(encoded):
                return [decode_workspace_path(encoded)], None
            case WorkspaceSpec.Pattern(pattern, match_type):
                return self._match_workspaces(home, pattern, match_type), None
            case WorkspaceSpec.Hash(hash):
                ws = self._resolve_hash(hash)
                return [ws] if ws else [], None
            case WorkspaceSpec.Concrete(ws):
                return [ws], None


class SessionResolver:
    """Stage 4: Resolve SessionSpecs to concrete session lists."""

    def resolve(self, scope: TemplateScope) -> Tuple[ConcreteScope, List[Error]]:
        result = []
        errors = []

        for record in scope:
            home = record.home.value
            workspace = record.workspace.value
            sessions, err = self._collect_sessions(home, workspace, record.sessions)

            if err:
                errors.append(err)
                continue

            if sessions:  # Only include if sessions exist
                result.append(ConcreteRecord(
                    home=home,
                    workspace=workspace,
                    sessions=sessions,
                ))

        return result, errors

    def _collect_sessions(self, home, workspace, spec) -> Tuple[List[dict], Error | None]:
        # Collect from all agents
        all_sessions = []

        for agent in ['claude', 'codex', 'gemini']:
            agent_sessions = self._collect_agent_sessions(home, workspace, agent)
            # EXACT match filter
            for s in agent_sessions:
                ws = s.get('workspace_readable') or s.get('workspace', '')
                if ws == workspace:  # EXACT MATCH - THE FIX!
                    all_sessions.append(s)

        # Apply session spec filters
        match spec:
            case SessionSpec.All:
                return all_sessions, None
            case SessionSpec.Filtered(filters):
                return self._apply_filters(all_sessions, filters), None
            case SessionSpec.List(sessions):
                return sessions, None
```

### Algorithm

```
RESOLVE_SCOPE(scope_args, context):
    1. Build initial template:
       - If CWD in project AND no explicit workspace:
           template = [ProjectRecord(cwd_project)]
       - Else:
           template = [ScopeRecord(home_spec, workspace_spec, session_spec)]

    2. Stage 1 - Resolve Projects:
       FOR each record in template:
           IF ProjectRecord:
               project_def = context.project_config[record.project]
               FOR each (home, workspaces) in project_def:
                   FOR each ws in workspaces:
                       EMIT ScopeRecord(Concrete(home), Path(ws), record.sessions)
           ELSE:
               EMIT record

    3. Stage 2 - Resolve Homes:
       FOR each record in template:
           homes = expand_home_spec(record.home, context)
           FOR each home in homes:
               EMIT ScopeRecord(Concrete(home), record.workspace, record.sessions)

    4. Stage 3 - Resolve Workspaces:
       FOR each record in template:
           home = record.home.value  # Now concrete
           workspaces = expand_workspace_spec(record.workspace, home, context)
           FOR each ws in workspaces:
               EMIT ScopeRecord(record.home, Concrete(ws), record.sessions)

    5. Stage 4 - Resolve Sessions:
       FOR each record in template:
           home = record.home.value
           workspace = record.workspace.value
           sessions = collect_sessions(home, workspace, record.sessions)
           sessions = filter(s => s.workspace == workspace, sessions)  # EXACT!
           IF sessions:
               EMIT ConcreteRecord(home, workspace, sessions)

    6. Return ResolutionResult(concrete_scope, errors, warnings)
```

---

## 4. Verb Dispatcher

### Responsibility
- Route command to appropriate handler based on resource and verb
- Validate handler exists
- Pass scope and verb args to handler

### Entity: `VerbDispatcher`

```python
class VerbDispatcher:
    """Dispatch commands to appropriate verb handlers."""

    def __init__(self):
        self.handlers: Dict[str, Dict[str, VerbHandler]] = {
            'session': {
                'list': SessionListHandler(),
                'export': SessionExportHandler(),
                'stats': SessionStatsHandler(),
                'show': SessionShowHandler(),
            },
            'project': {
                'list': ProjectListHandler(),
                'show': ProjectShowHandler(),
                'stats': ProjectStatsHandler(),
                'create': ProjectCreateHandler(),
                'delete': ProjectDeleteHandler(),
            },
            'ws': {
                'list': WorkspaceListHandler(),
                'show': WorkspaceShowHandler(),
            },
        }

    def dispatch(self, request: CommandRequest, scope: ConcreteScope) -> CommandResult:
        """Dispatch command to appropriate handler.

        Args:
            request: Parsed command request
            scope: Resolved concrete scope

        Returns:
            CommandResult from handler
        """
        resource_handlers = self.handlers.get(request.resource)
        if not resource_handlers:
            raise DispatchError(f"Unknown resource: {request.resource}")

        handler = resource_handlers.get(request.verb)
        if not handler:
            raise DispatchError(f"Unknown verb: {request.verb} for {request.resource}")

        return handler.execute(scope, request.verb_args, request.output_args)
```

### Algorithm

```
DISPATCH(request, scope):
    1. handlers = registry[request.resource]
       IF handlers is None:
           ERROR "Unknown resource"

    2. handler = handlers[request.verb]
       IF handler is None:
           ERROR "Unknown verb"

    3. RETURN handler.execute(scope, verb_args, output_args)
```

---

## 5. Verb Handlers

### Responsibility
- Execute command-specific logic on concrete scope
- Produce CommandResult with data or status

### Entity: `VerbHandler` (Abstract)

```python
class VerbHandler(ABC):
    """Abstract base for verb handlers."""

    @abstractmethod
    def execute(self, scope: ConcreteScope, verb_args: dict, output_args: OutputArgs) -> CommandResult:
        """Execute the verb on the given scope."""
        pass
```

### Concrete Handlers

```python
class SessionListHandler(VerbHandler):
    """Handle 'session list' command."""

    def execute(self, scope: ConcreteScope, verb_args: dict, output_args: OutputArgs) -> CommandResult:
        # Flatten scope to session list
        sessions = []
        for record in scope:
            for session in record.sessions:
                session['home'] = record.home
                sessions.append(session)

        # Sort by modified time (newest first)
        sessions.sort(key=lambda s: s.get('modified', ''), reverse=True)

        return CommandResult(
            success=True,
            data=sessions,
            data_type='session_list',
            metadata={
                'total_count': len(sessions),
                'homes': list(set(r.home for r in scope)),
                'workspaces': list(set(r.workspace for r in scope)),
            }
        )


class SessionExportHandler(VerbHandler):
    """Handle 'session export' command."""

    def execute(self, scope: ConcreteScope, verb_args: dict, output_args: OutputArgs) -> CommandResult:
        output_dir = verb_args.get('output_dir', Path.cwd())
        format = verb_args.get('format', 'markdown')
        split = verb_args.get('split', 'workspace')

        exported_files = []

        for record in scope:
            for session in record.sessions:
                output_path = self._compute_output_path(
                    output_dir, record.home, record.workspace, session, split
                )
                content = self._convert_session(session, format)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(content)
                exported_files.append(output_path)

        return CommandResult(
            success=True,
            data=exported_files,
            data_type='exported_files',
            metadata={'count': len(exported_files)},
        )


class SessionStatsHandler(VerbHandler):
    """Handle 'session stats' command."""

    def execute(self, scope: ConcreteScope, verb_args: dict, output_args: OutputArgs) -> CommandResult:
        stats = {
            'total_sessions': 0,
            'total_messages': 0,
            'by_agent': defaultdict(int),
            'by_home': defaultdict(int),
            'by_workspace': defaultdict(int),
        }

        for record in scope:
            for session in record.sessions:
                stats['total_sessions'] += 1
                stats['total_messages'] += session.get('message_count', 0)
                stats['by_agent'][session.get('agent', 'unknown')] += 1
                stats['by_home'][record.home] += 1
                stats['by_workspace'][record.workspace] += 1

        return CommandResult(
            success=True,
            data=stats,
            data_type='stats',
        )


class ProjectShowHandler(VerbHandler):
    """Handle 'project show' command."""

    def execute(self, scope: ConcreteScope, verb_args: dict, output_args: OutputArgs) -> CommandResult:
        project_name = verb_args.get('project_name')

        # Group scope by home
        by_home = defaultdict(list)
        for record in scope:
            by_home[record.home].append({
                'workspace': record.workspace,
                'session_count': len(record.sessions),
            })

        total_sessions = sum(len(r.sessions) for r in scope)

        return CommandResult(
            success=True,
            data={
                'project': project_name,
                'workspaces_by_home': dict(by_home),
                'total_sessions': total_sessions,
            },
            data_type='project_details',
        )
```

### Data Structures

```python
@dataclass
class CommandResult:
    """Result of command execution."""
    success: bool
    data: Any                  # Command-specific data
    data_type: str             # Type hint for formatter
    metadata: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
```

---

## 6. Output Formatter

### Responsibility
- Format CommandResult for display
- Support multiple output formats (table, json, csv, markdown)
- Handle output destination (stdout, file)

### Entity: `OutputFormatter`

```python
class OutputFormatter:
    """Format command results for output."""

    def __init__(self):
        self.formatters: Dict[str, DataFormatter] = {
            'table': TableFormatter(),
            'json': JsonFormatter(),
            'csv': CsvFormatter(),
            'markdown': MarkdownFormatter(),
        }

    def format(self, result: CommandResult, output_args: OutputArgs) -> None:
        """Format and output command result.

        Args:
            result: Command execution result
            output_args: Output formatting options
        """
        # Determine format
        format_name = output_args.format or 'table'
        formatter = self.formatters.get(format_name)
        if not formatter:
            raise FormatterError(f"Unknown format: {format_name}")

        # Format data
        output = formatter.format(result.data, result.data_type, result.metadata)

        # Write output
        if output_args.output:
            output_args.output.write_text(output)
        else:
            print(output)

        # Write warnings to stderr
        for warning in result.warnings:
            sys.stderr.write(f"Warning: {warning}\n")


class TableFormatter(DataFormatter):
    """Format data as ASCII table."""

    def format(self, data: Any, data_type: str, metadata: dict) -> str:
        match data_type:
            case 'session_list':
                return self._format_session_list(data)
            case 'stats':
                return self._format_stats(data)
            case 'project_details':
                return self._format_project_details(data)
            case _:
                return str(data)

    def _format_session_list(self, sessions: List[dict]) -> str:
        headers = ['AGENT', 'HOME', 'WORKSPACE', 'FILE', 'MESSAGES', 'DATE']
        rows = []
        for s in sessions:
            rows.append([
                s.get('agent', ''),
                s.get('home', ''),
                s.get('workspace_readable', s.get('workspace', '')),
                s.get('filename', ''),
                str(s.get('message_count', '')),
                s.get('modified', '').strftime('%Y-%m-%d') if s.get('modified') else '',
            ])
        return self._render_table(headers, rows)


class JsonFormatter(DataFormatter):
    """Format data as JSON."""

    def format(self, data: Any, data_type: str, metadata: dict) -> str:
        return json.dumps({
            'data': data,
            'metadata': metadata,
        }, indent=2, default=str)
```

### Algorithm

```
FORMAT_OUTPUT(result, output_args):
    1. Determine format:
       format = output_args.format OR 'table'

    2. Get formatter:
       formatter = formatters[format]

    3. Format data:
       output = formatter.format(result.data, result.data_type, result.metadata)

    4. Write output:
       IF output_args.output:
           write_file(output_args.output, output)
       ELSE:
           print(output)

    5. Write warnings to stderr
```

---

## 7. Error Handler

### Responsibility
- Catch and handle errors at each pipeline stage
- Format error messages
- Determine exit codes

### Entity: `ErrorHandler`

```python
class ErrorHandler:
    """Handle errors throughout the pipeline."""

    def handle_resolution_errors(self, result: ResolutionResult) -> bool:
        """Handle resolution errors. Returns True if should continue."""
        if not result.errors:
            return True

        for error in result.errors:
            self._print_error(error)

        # Continue if partial success and data exists
        return result.partial

    def handle_dispatch_error(self, error: DispatchError) -> NoReturn:
        """Handle dispatch errors."""
        sys.stderr.write(f"Error: {error.message}\n")
        sys.exit(1)

    def handle_execution_error(self, error: Exception) -> NoReturn:
        """Handle execution errors."""
        sys.stderr.write(f"Error: {str(error)}\n")
        if os.environ.get('DEBUG'):
            traceback.print_exc()
        sys.exit(1)

    def _print_error(self, error: ResolutionError) -> None:
        sys.stderr.write(f"Error in {error.stage}: {error.reason}\n")
        if error.suggestions:
            sys.stderr.write(f"  Did you mean: {', '.join(error.suggestions)}\n")
```

---

## 8. Main Orchestrator

### Responsibility
- Orchestrate the full pipeline
- Coordinate between all entities

### Entity: `CommandOrchestrator`

```python
class CommandOrchestrator:
    """Main orchestrator for command execution."""

    def __init__(self):
        self.parser = CLIParser()
        self.context_builder = ContextBuilder()
        self.dispatcher = VerbDispatcher()
        self.formatter = OutputFormatter()
        self.error_handler = ErrorHandler()

    def run(self, argv: List[str]) -> int:
        """Run command pipeline.

        Args:
            argv: Command line arguments

        Returns:
            Exit code
        """
        try:
            # 1. Parse command line
            request = self.parser.parse(argv)

            # 2. Build context
            context = self.context_builder.build()

            # 3. Resolve scope
            resolver = ScopeResolver(context)
            resolution = resolver.resolve(request.scope_args)

            # Handle resolution errors
            if not self.error_handler.handle_resolution_errors(resolution):
                return 1

            # 4. Dispatch to handler
            result = self.dispatcher.dispatch(request, resolution.scope)

            # 5. Format and output
            self.formatter.format(result, request.output_args)

            return 0 if result.success else 1

        except DispatchError as e:
            self.error_handler.handle_dispatch_error(e)
        except Exception as e:
            self.error_handler.handle_execution_error(e)


def main():
    orchestrator = CommandOrchestrator()
    sys.exit(orchestrator.run(sys.argv[1:]))
```

### Algorithm

```
RUN(argv):
    1. request = CLIParser.parse(argv)

    2. context = ContextBuilder.build()

    3. resolver = ScopeResolver(context)
       resolution = resolver.resolve(request.scope_args)

    4. IF resolution has errors AND not partial:
           print errors
           EXIT 1

    5. result = VerbDispatcher.dispatch(request, resolution.scope)

    6. OutputFormatter.format(result, request.output_args)

    7. EXIT 0 if success else 1
```

---

## 9. Entity Summary

| Entity | Responsibility | Input | Output |
|--------|---------------|-------|--------|
| **CLIParser** | Parse command line | `argv` | `CommandRequest` |
| **ContextBuilder** | Build resolution context | Environment | `ResolutionContext` |
| **ScopeResolver** | Resolve scope specs | `ScopeArgs`, `Context` | `ConcreteScope` |
| **ProjectResolver** | Expand project records | `TemplateScope` | `TemplateScope` |
| **HomeResolver** | Resolve home specs | `TemplateScope` | `TemplateScope` |
| **WorkspaceResolver** | Resolve workspace specs | `TemplateScope` | `TemplateScope` |
| **SessionResolver** | Collect sessions | `TemplateScope` | `ConcreteScope` |
| **VerbDispatcher** | Route to handler | `Request`, `Scope` | `CommandResult` |
| **VerbHandler** | Execute command logic | `Scope`, `Args` | `CommandResult` |
| **OutputFormatter** | Format for display | `Result`, `OutputArgs` | stdout/file |
| **ErrorHandler** | Handle errors | Various errors | Error output |
| **CommandOrchestrator** | Orchestrate pipeline | `argv` | Exit code |

---

## 10. Data Flow Diagram

```
argv: ["session", "list", "--wsl"]
            │
            ▼
    ┌───────────────┐
    │   CLIParser   │
    └───────┬───────┘
            │ CommandRequest {
            │   resource: "session",
            │   verb: "list",
            │   scope_args: {
            │     home: Category("wsl"),
            │     workspace: Current,
            │     session: All
            │   }
            │ }
            ▼
    ┌───────────────┐
    │ContextBuilder │
    └───────┬───────┘
            │ ResolutionContext {
            │   platform: "wsl",
            │   cwd_project: "testproj",
            │   available_homes: {wsl: ["Ubuntu"]},
            │   ...
            │ }
            ▼
    ┌───────────────┐
    │ ScopeResolver │
    │  ├─ Stage 1   │ [ProjectRecord("testproj")]
    │  ├─ Stage 2   │ [ScopeRecord(Concrete("wsl:Ubuntu"), Path(...), All)]
    │  ├─ Stage 3   │ [ScopeRecord(..., Concrete("/home/user/auth"), All)]
    │  └─ Stage 4   │ [ConcreteRecord("wsl:Ubuntu", "/home/user/auth", [sessions])]
    └───────┬───────┘
            │ ConcreteScope
            ▼
    ┌───────────────┐
    │VerbDispatcher │────► SessionListHandler
    └───────┬───────┘
            │ CommandResult {
            │   success: true,
            │   data: [session1, session2, ...],
            │   data_type: "session_list"
            │ }
            ▼
    ┌───────────────┐
    │OutputFormatter│
    └───────┬───────┘
            │
            ▼
    AGENT  HOME       WORKSPACE              FILE           MESSAGES  DATE
    claude wsl:Ubuntu /home/user/projects/auth session-01.jsonl 15     2025-01-09
    ...
```

---

## 11. Key Design Principles

### 1. **Single Responsibility**
Each entity has one job. Scope resolution doesn't know about output formatting.

### 2. **Dependency Injection**
Context is built once and passed through. No global state.

### 3. **Progressive Refinement**
Scope resolution happens in stages. Each stage has clear input/output.

### 4. **Explicit Over Implicit**
All scope resolution is explicit. No hidden substring matching.

### 5. **Error Propagation**
Errors are collected and propagated, not thrown mid-pipeline.

### 6. **Testability**
Each entity can be tested in isolation with mock inputs.

### 7. **Extensibility**
New verbs, formatters, or resolvers can be added without changing existing code.
