# TODO

## Edge Case Tests

- [ ] Corrupted/malformed JSONL files (invalid JSON, missing fields)
- [ ] Empty workspaces (directory exists but no sessions)
- [ ] Very large sessions (>10k messages) with split
- [ ] Concurrent database access
- [ ] Import/export alias round-trip

## Remote Operations

- [ ] SSH timeout coordination (currently varies: 5s, 10s, 30s, 300s)
- [ ] Filenames with `|` character break remote parsing
- [ ] Check rsync availability on remote before operations
- [ ] Multiple Windows users enumeration

## Stats Database

- [ ] Schema migration atomicity (race condition possible)
- [ ] TOCTOU race (file deleted between stat and open)
- [ ] Query limits for large databases (>100k sessions)
- [ ] Codex cache semantics: consider per-turn vs cumulative token_count reporting

## Command Combinations

- [ ] Multiple `-r` flags only use first (document or warn)
- [ ] `--split --minimal` uses non-minimal line estimates
- [ ] `--alias` with pattern silently ignores pattern

## Record Type Support (moved from format docs)

### Claude Code

| Type | Status | Notes |
|------|--------|-------|
| `user` | ✅ Supported | User messages parsed and exported |
| `assistant` | ✅ Supported | Assistant messages parsed and exported |
| `summary` | ❓ Not handled | Compacted conversation summaries |
| `file-history-snapshot` | ❓ Not handled | File state snapshots |
| `queue-operation` | ❓ Not handled | Internal queue events |

### Codex CLI

| Type | Status | Notes |
|------|--------|-------|
| `session_meta` | ❓ Verify | ID, cwd, cli_version, source extracted |
| `turn_context` | ❓ Verify | Model name extracted for stats |
| `response_item.message` | ❓ Verify | User and assistant messages |
| `response_item.function_call` | ❓ Verify | Tool calls with arguments |
| `response_item.function_call_output` | ❓ Verify | Tool results |
| `response_item.custom_tool_call` | ❓ Verify | Custom/MCP tool calls |
| `response_item.custom_tool_call_output` | ❓ Verify | Custom tool results |
| `event_msg.token_count` | ✅ Supported | Token usage snapshots |
| `response_item.reasoning` | ❓ Not handled | Extended thinking summaries |
| `response_item.local_shell_call` | ❓ Not handled | Shell command executions |
| `response_item.web_search_call` | ❓ Not handled | Web search actions |
| `response_item.ghost_snapshot` | ❓ Not handled | Git snapshots |
| `compacted` | ❓ Not handled | Compacted conversation items |
| `event_msg` (other) | ❓ Not handled | Other event messages |

### Codex CLI Session Metadata Fields

| Field | Shown in Export | Used in Stats |
|-------|-----------------|---------------|
| `id` | ✅ Yes | ✅ Yes |
| `cwd` | ✅ Yes | ✅ Yes (workspace) |
| `cli_version` | ✅ Yes | ✅ Yes |
| `source` | ✅ Yes | ❌ No |
| `timestamp` | ✅ Yes | ✅ Yes |
| `originator` | ❌ No | ❌ No |
| `instructions` | ❌ No | ❌ No |
| `model_provider` | ❌ No | ❌ No |
| `git` (branch, commit) | ❌ No | ❌ No |
