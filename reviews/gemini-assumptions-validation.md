# Gemini Assumptions – Validation Plan

## Current State
- No Gemini backend exists; CLI rejects `--agent gemini`.
- `detect_agent_from_path` only knows `.claude` / `.codex` and defaults to Claude, so any Gemini path would be misclassified today.
- No Gemini fixtures or JSONL samples in the repo.

## Working Assumptions (need confirmation)
- **Home/path:** Sessions stored under `~/.gemini/sessions/YYYY/MM/DD/rollout-*.jsonl` (mirroring Codex layout).
- **Envelope:** JSONL lines with `timestamp`, `type`, `payload`, with `response_item` entries for messages/tool calls/tool results similar to Codex.
- **Metadata:** A `session_meta` line containing `id`, `cwd`, `cli_version`, `source`; a `turn_context` line with `model`.
- **Messages:** `payload.type == "message"` with `role` (`user`/`assistant`) and `content` blocks using `input_text` / `output_text` and `text` fields.
- **Tools:** Tool calls/results encoded via `function_call` / `function_call_output` (or similar) with `name`, `arguments`, `call_id`, `output`.
- **Workspace derivation:** `cwd` in `session_meta` usable with `path_to_encoded_workspace`.

## What must be validated with real Gemini CLI data
1) **Session location & naming**
   - Actual base dir and file naming pattern (rollout-*? date-based?).
   - Any env overrides (e.g., `GEMINI_SESSIONS_DIR`) used by the CLI.
2) **Line envelope**
   - Values of `type` (e.g., `session_meta`, `turn_context`, `response_item`, others?).
   - Field names inside `payload` for messages and tool calls/results.
3) **Content blocks**
   - `content` structure: list vs string; block `type` values and field names.
   - Presence of system messages or other roles.
4) **Tool calls/results**
   - Exact keys for tool calls (name/arguments/call_id?) and outputs (call_id/output/is_error?).
5) **Metadata**
   - Where `cwd`, `model`, `cli_version`, and `source` live (session_meta vs turn_context vs elsewhere).
   - Any additional identifiers (agent/session ids) needed for DB.
6) **Workspace rules**
   - Confirm `cwd` semantics (local, remote, WSL/Windows paths) and whether encoding matches existing helpers.

## Validation Approach (requires Gemini artifacts)
- Collect one or more real Gemini rollout JSONL files (redact content if needed).
- Verify directory layout and naming.
- Inspect 3–5 lines per file to map field names/types to Codex/Claude expectations.
- Derive a minimal fixture set:
  - Session with user/assistant messages.
  - Session with tool call + result.
  - Session with model/turn_context present.
  - Session lacking optional fields (missing cwd/model) to define fallbacks.

## Integration/Test Readiness
- Once the shape is known, mirror Codex test pattern:
  - Unit: parsing, metrics extraction, scanner, agent detection.
  - Integration: lsw/lss/export/stats with synthetic `.gemini` tree and HOME override/monkeypatch of `get_home_dir`.

## Next Steps (blocked on data)
- Provide/locate a sample Gemini JSONL (or CLI docs describing the logging format and location).
- If unavailable, we can implement a feature-flagged scaffold (agent constants, detection, scanners) but parsers/fixtures will remain speculative until real data is supplied.
