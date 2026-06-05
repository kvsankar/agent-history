# Reviews Index

<!-- doc-meta
doc_role: overview
audience: maintainer
lifecycle: current
content_type: index
surface: internal
canonicality: index
-->

Review documents are supporting or historical inputs. Actionable findings should
be promoted into [specs/todo.md](../specs/todo.md), tests, specs, or design docs
before a review is treated as closed.

## Current Or Recently Actionable

| Document | Status | Notes |
|----------|--------|-------|
| [AGENT_HISTORY_SPEC_DRIFT.md](AGENT_HISTORY_SPEC_DRIFT.md) | supporting | Append-only spec drift and user-input capture; promoted items should move to specs/todo. |
| [agent-history-spec-review.md](agent-history-spec-review.md) | historical/supporting | Earlier implementation/spec audit; verify before acting because several findings may be stale. |
| [implementation-review-2026-01-08.md](implementation-review-2026-01-08.md) | historical/supporting | Dated implementation review; promote durable gaps before editing specs. |
| [20260109-legacy_test_deprecation_report.md](20260109-legacy_test_deprecation_report.md) | superseded | Initial deprecation assessment, superseded by the approval report. |
| [20260109-legacy_test_deprecation_approval.md](20260109-legacy_test_deprecation_approval.md) | closed | Approval evidence for legacy test deprecation. |

## Historical Quality Reviews

| Document | Status | Notes |
|----------|--------|-------|
| [assessment_report.md](assessment_report.md) | historical | General codebase assessment. |
| [codex_review.md](codex_review.md) | historical | Early Codex integration review; validate against current implementation before acting. |
| [COVERAGE_REPORT.md](COVERAGE_REPORT.md) | historical | Coverage snapshot from 2025-12-16. |
| [FORMAT_REFACTORING_REVIEW.md](FORMAT_REFACTORING_REVIEW.md) | historical | Formatting/style refactoring review for older single-file implementation. |
| [REFACTORING_REVIEW.md](REFACTORING_REVIEW.md) | historical | Python refactoring review for older single-file implementation. |
| [RHODES_REVIEW.md](RHODES_REVIEW.md) | historical | Brandon Rhodes style review for older single-file implementation. |

## Completed Review Reports

Completed Python review reports live in [done/](done/). Keep them as historical
evidence unless a finding is explicitly promoted back into current specs, tests,
or architecture docs.
