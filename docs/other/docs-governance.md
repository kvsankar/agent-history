# Documentation Governance

<!-- doc-meta
doc_role: guide
audience: contributor
lifecycle: current
content_type: workflow
surface: internal
canonicality: primary
-->

This page defines where documentation maintenance artifacts belong. It keeps
indexes, specs, dated analysis, generated reports, and local review output from
competing with each other.

## Canonical Owners

| Area | Owner |
|------|-------|
| Public docs map | [docs/README.md](../README.md) |
| Specs map | [docs/specs/README.md](../specs/README.md) |
| User commands and examples | [usage.md](../user/usage.md), [cookbook.md](../user/cookbook.md), [troubleshooting.md](../user/troubleshooting.md) |
| Product behavior and storage model | [agent-history-spec.md](../specs/agent-history-spec.md) |
| CLI syntax and output contracts | [cli-spec.md](../specs/cli-spec.md) |
| Unified export schema | [unified-json-schema.md](../specs/schema/unified-json-schema.md) |
| Release/spec follow-ups | [todo.md](../specs/todo.md) |
| Workspace/scope navigation | [workspace-scope-hub.md](../design-v2/workspace-scope-hub.md) |

## Metadata Facets

Use a lightweight HTML comment near the top of docs that are easy to confuse:

```markdown
<!-- doc-meta
doc_role: guide
audience: contributor
lifecycle: current
content_type: workflow
surface: internal
canonicality: primary
-->
```

Recommended dimensions:

- `doc_role`: `guide`, `reference`, `spec`, `architecture`, `research`, `status`, `plan`, `troubleshooting`, `overview`
- `audience`: `user`, `contributor`, `maintainer`, `operator`, `internal`, `agent`
- `lifecycle`: `current`, `proposed`, `draft`, `historical`
- `content_type`: `workflow`, `api`, `architecture`, `requirements`, `troubleshooting`, `decision`, `benchmark`, `example`
- `surface`: `public`, `internal`, `integration`, `generated`, `extension`, `package`
- `canonicality`: `primary`, `supporting`, `index`, `archive`

## Generated And Local Output

Keep generated or local review artifacts out of version control:

- `.dryscope/` contains raw Dryscope reports and remains ignored.
- `docs/reviews/` is local review output and remains ignored.
- `docs/*review*.md` is ignored for one-off review reports.

Commit curated summaries instead of raw generated output. For Dryscope, use a
dated summary under `docs/analysis/` when the findings should affect the repo.

## Promotion Rules

- Promote durable behavior into specs, tests, or architecture docs.
- Promote release follow-ups into [todo.md](../specs/todo.md).
- Keep dated analysis as evidence and context, not as the only home for current
  behavior.
- Keep user docs task-focused; link to specs for storage, schema, metrics, and
  implementation details.
- Keep review outputs local unless a specific finding is promoted into a
  committed owner.

## Dryscope Reruns

Run a docs Dryscope scan after structural IA changes, large doc moves, or
schema-refresh rounds:

```bash
/home/sankar/.local/share/dryscope/skill-venv/bin/dryscope scan docs --docs --stage full --backend codex-cli --llm-model gpt-5.5 --embedding-model all-MiniLM-L6-v2 -f markdown
```

Do not commit `.dryscope/` raw reports. Record only the result summary and
actionable follow-ups in `docs/analysis/` or `docs/specs/todo.md`.
