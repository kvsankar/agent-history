# Workspace and Scope Navigation Hub

<!-- doc-meta
doc_role: overview
audience: contributor
lifecycle: current
content_type: architecture
surface: internal
canonicality: index
-->

Use this page as the entry point for workspace, home, source, and session scope
questions. It is intentionally a navigation hub, not another specification.

## Reader Paths

| Need | Go To | Owns |
|------|-------|------|
| User commands for listing, exporting, stats, homes, and projects | [usage.md](../user/usage.md) | Command syntax, flags, examples, output expectations. |
| Recipes for cross-machine and multi-home workflows | [cookbook.md](../user/cookbook.md) | Task-oriented workflows and command sequences. |
| Common failures and recovery | [troubleshooting.md](../user/troubleshooting.md) | User-facing diagnosis and fixes. |
| Product source model and supported agent storage locations | [cagelens-spec.md](../specs/cagelens-spec.md) | Canonical source, workspace, project, metrics, cache, and file-location model. |
| Scope resolver architecture | [scope-resolution-v2.md](scope-resolution-v2.md) | Typed home/workspace/session specs, resolution stages, matching semantics. |
| Command pipeline architecture | [pipeline-architecture.md](pipeline-architecture.md) | CLI parsing, context building, scope resolution, execution, and output flow. |
| Local agent session storage details | [agent format specs](../specs/agents/formats/) | Per-agent concrete storage layouts and record formats. |
| Remote and SSH validation | [docker-e2e.md](../testing/docker-e2e.md) | Docker E2E setup and remote-operation test coverage. |

## Concept Map

`cagelens` resolves commands through four related concepts:

- **Home/source**: where sessions are read from, such as local, WSL, Windows,
  SSH remote, or web.
- **Workspace**: the project directory or source-specific workspace identifier
  that sessions belong to.
- **Project**: a user-defined group of related workspaces across homes.
- **Session**: a concrete conversation file or web session selected after home
  and workspace resolution.

The durable behavior belongs in [cagelens-spec.md](../specs/cagelens-spec.md).
Implementation detail belongs in [scope-resolution-v2.md](scope-resolution-v2.md)
and [pipeline-architecture.md](pipeline-architecture.md). User docs should link
here or to those owners instead of restating the model.

## Common Routing Rules

- Put command examples and user-facing flag explanations in
  [usage.md](../user/usage.md) or [cookbook.md](../user/cookbook.md).
- Put exact source layout, config, cache, and metrics storage details in
  [cagelens-spec.md](../specs/cagelens-spec.md).
- Put matching rules, encoded/hash workspace handling, and resolver stages in
  [scope-resolution-v2.md](scope-resolution-v2.md).
- Put concrete agent session file shapes in the per-agent format specs.
- Put SSH/Docker validation details in [docker-e2e.md](../testing/docker-e2e.md).
- Keep troubleshooting focused on symptoms and recovery, with links back to the
  canonical model when details matter.
