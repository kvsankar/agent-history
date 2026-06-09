# Subagent and Lineage Analysis

<!-- doc-meta
doc_role: research
audience: contributor
lifecycle: proposed
content_type: decision
surface: integration
canonicality: supporting
-->

How supported coding agents record delegated child-agent work and how
`cagelens` should normalize it for timeline and export features.

> **Refresh 2026-06-09**: This document combines public documentation checks,
> local history inspection, and a live Codex subagent probe. Current parsers do
> not yet emit a first-class lineage model for all agents.

## Summary

| Agent | Native or Extension | Parent Invocation | Child Session | Completion / Merge |
|-------|---------------------|-------------------|---------------|--------------------|
| Claude Code | Native | Task tool / task records | `agent-*.jsonl` or `<sessionId>/subagents/agent-<task-id>.jsonl` | `<task-notification>` with `task-id`, `tool-use-id`, `status`, `result`, `usage` |
| Codex CLI | Native in current Codex subagent runtime | `spawn_agent` tool call and returned `agent_id` | `thread_source: "subagent"` rollout with `source.subagent.thread_spawn` | `event_msg.task_complete` plus parent `subagent_notification` in Codex harness sessions |
| Gemini CLI | Native tool-style subagents | `toolCalls[]` entry such as `codebase_investigator` | Usually parent-side result only in observed local data; nested child JSONL may exist in current formats | `status`, `result`, `resultDisplay`, termination reason |
| Pi | Extension-provided | Registered extension tool such as `subagent` | Extension-dependent child Pi process/session | Extension-dependent tool result/progress records |

## Normalized Lineage Target

Timeline export should not rely on agent-specific field names directly. Add a
normalized lineage layer with these fields where available:

| Field | Meaning |
|-------|---------|
| `session_id` | Main or child session identifier |
| `parent_session_id` | Parent/root session identifier |
| `kind` | `main`, `subagent`, or `branch` |
| `agent` | Source backend: `claude`, `codex`, `gemini`, `pi` |
| `agent_id` | Agent/task/thread identifier inside the source agent |
| `agent_name` | Display name, nickname, role, or subagent name |
| `invocation_message_id` | Parent message that requested the child |
| `invocation_tool_call_id` | Parent tool call that spawned the child |
| `start_ts` | Child/session start timestamp |
| `end_ts` | Child/session completion timestamp |
| `status` | Completion state such as `completed`, `success`, `error`, `interrupted` |
| `duration_ms` | Agent-reported or derived duration |
| `last_agent_message` | Final child message/result summary when available |
| `merge_message_id` | Parent message carrying the returned result |
| `confidence` | `confirmed`, `inferred`, or `weak` |
| `evidence` | Source file, record type, and field path used for the join |

Render confirmed child tracks as normal subagent tracks. Render inferred or
extension-dependent tracks with a distinct style and explanatory detail in the
session metadata panel.

## Claude Code

Claude has two observed storage layouts:

```text
~/.claude/projects/<workspace>/agent-<agent-id>.jsonl
~/.claude/projects/<workspace>/<sessionId>/subagents/agent-<task-id>.jsonl
```

Child records include `isSidechain: true`, `sessionId`, `agentId`, `uuid`,
`parentUuid`, timestamps, messages, and tool calls. Newer parent sessions also
record queued `<task-notification>` payloads containing:

- `task-id`
- `tool-use-id`
- `output-file`
- `status`
- `summary`
- `result`
- `usage` with token, tool-use, and duration fields

The direct join is:

```text
parent task notification task-id
  -> subagents/agent-<task-id>.jsonl
  -> child agentId / timestamps / tools
  -> task notification result and usage
```

Older top-level `agent-*.jsonl` files can still be grouped by shared
`sessionId` and `agentId`, but the exact parent tool call may require inference
from surrounding Task tool calls and timestamps.

## Codex CLI

A live Codex subagent probe on 2026-06-09 produced a child rollout whose
`session_meta.payload` contained:

```json
{
  "id": "019eabfc-870d-7281-b28f-72cd2f24bfd0",
  "forked_from_id": "019eab05-b062-7a33-aaa9-fa6be57caec8",
  "thread_source": "subagent",
  "agent_nickname": "Confucius",
  "agent_role": "explorer",
  "source": {
    "subagent": {
      "thread_spawn": {
        "parent_thread_id": "019eab05-b062-7a33-aaa9-fa6be57caec8",
        "depth": 1,
        "agent_nickname": "Confucius",
        "agent_role": "explorer"
      }
    }
  }
}
```

The child rollout ended with:

```json
{
  "type": "task_complete",
  "turn_id": "019eabfc-872d-7d23-8724-b0e7f27bd27f",
  "last_agent_message": "LINEAGE_PROBE_DONE /home/sankar/sankar/projects/claude-history",
  "completed_at": 1781001934,
  "duration_ms": 19969,
  "time_to_first_token_ms": 6124
}
```

The parent rollout recorded a `spawn_agent` function call and a matching
function-call output containing the child `agent_id`. The reliable join is:

```text
parent session id
  -> parent response_item.function_call name=spawn_agent
  -> matching function_call_output.agent_id
  -> child session_meta.payload.id
  -> child session_meta.payload.source.subagent.thread_spawn.parent_thread_id
  -> child event_msg.task_complete
```

Current `cagelens` parser code preserves some linkage on parsed messages, but
stats, session listing, Markdown, and HTML export do not yet promote the child
rollout itself into a first-class subagent session. `task_complete` is also not
currently emitted as a normalized event.

## Gemini CLI

Gemini records subagent-style delegation as parent-side tool calls. Observed
local records include `toolCalls[]` entries such as:

```json
{
  "id": "codebase_investigator-1763516562153-a1b849419aa01",
  "name": "codebase_investigator",
  "displayName": "Codebase Investigator Agent",
  "status": "success",
  "resultDisplay": "Subagent codebase_investigator Finished\n\nTermination Reason:\n GOAL\n\nResult:\n..."
}
```

For timeline purposes this is enough to draw a child-agent span when the tool
call timestamp and result timestamp are available, but a separate child
transcript may not exist in older/local JSON sessions. Current JSONL paths may
also contain nested child sessions under a parent chat directory; when present,
those should be linked by parent session path and child agent/session id.

## Pi

Pi core supports extension tools and packages. Public Pi docs describe
extensions as TypeScript modules that can register custom LLM-callable tools,
and packages as bundles of extensions, skills, prompts, and themes. Published
Pi subagent packages then provide delegation by installing an extension that
registers a `subagent` tool.

This means Pi subagent support is extension-provided, not a stable native
session-file relationship in the base format. Examples:

- `pi-subagents` describes Pi as the parent session and the subagent as a
  focused child Pi session, but this behavior comes from the package extension.
- `pi-sub-agent` runs delegated tasks in separate `pi --mode json -p
  --no-session` subprocesses and streams progress, usage, final Markdown
  output, failures, and structured result details.

`cagelens` should therefore treat Pi as:

- confirmed `branch` lineage when records use `id` / `parentId` tree links;
- confirmed tool/result spans for normal Pi tool calls;
- extension-dependent subagent lineage only when a `subagent` tool call/result
  exposes enough structured fields to identify child sessions and completion.

Do not infer native Pi subagent tracks from ordinary branch tree records alone.

## Implementation Notes

1. Add a `lineage` extraction stage per backend.
2. Keep raw evidence paths for explainability and debugging.
3. Promote child sessions into stats and timeline data before HTML rendering.
4. Keep branch lineage separate from subagent lineage.
5. Add fixtures for:
   - Codex `thread_source: "subagent"` plus `task_complete`.
   - Claude nested `subagents/agent-<task-id>.jsonl` plus parent
     `<task-notification>`.
   - Gemini parent-side `toolCalls[]` subagent result.
   - Pi extension-dependent `subagent` tool calls, once a real fixture is
     available.

## Sources

- Pi extension docs: <https://pi.dev/docs/latest/extensions>
- Pi package docs: <https://pi.dev/docs/latest/packages>
- Pi `pi-subagents` package: <https://pi.dev/packages/pi-subagents>
- Pi `pi-sub-agent` package: <https://pi.dev/packages/pi-sub-agent>
- Gemini CLI subagents docs:
  <https://github.com/google-gemini/gemini-cli/blob/main/docs/core/subagents.md>
- Claude Code subagents docs: <https://code.claude.com/docs/en/sub-agents>
- Local Codex live probe:
  `~/.codex/sessions/2026/06/09/rollout-2026-06-09T16-15-14-019eabfc-870d-7281-b28f-72cd2f24bfd0.jsonl`
