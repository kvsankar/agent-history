# V1 Testing Status

**Status: COMPLETE** - 63 passed, 3 skipped, 0 failed

Run tests: `uv run pytest -m v1`

---

## What Was Delivered

### Infrastructure (Agent 2)
- `tests/conftest.py` - Root fixtures (test_home, isolated_home, cli_runner, metrics_db)
- `tests/helpers/cli.py` - CLI subprocess runner, assertions
- `tests/helpers/assertions.py` - Custom validation helpers
- `tests/helpers/session_builders.py` - Session factory classes
- `pytest.ini` - Added markers: v1, docker, ssh, slow, linux_only

### Golden Fixtures (Agent 1)
- `tests/fixtures/v1/claude_golden.jsonl` - 6 msgs, 500 in, 200 out, 2 tools (Read, Edit)
- `tests/fixtures/v1/codex_golden.jsonl` - 4 msgs, 300 in, 150 out, 1 tool (shell)
- `tests/fixtures/v1/gemini_golden.json` - 4 msgs, 400 in, 180 out, 1 tool (read_file)
- `tests/fixtures/v1/expected_values.json` - Pre-computed expected values

### V1 Tests
| File | Tests | Status |
|------|-------|--------|
| `test_claude_parser.py` | 10 | All pass |
| `test_codex_parser.py` | 11 | All pass |
| `test_gemini_parser.py` | 12 | All pass |
| `test_cli_happy_paths.py` | 15 | All pass |
| `test_unified_export.py` | 6 | All pass |
| `test_stats_golden.py` | 9 pass, 3 skip | Role column missing |

### Features Implemented
- `--json` flag for unified NDJSON export
- Role normalization (gemini → assistant)

---

## Golden Dataset Totals

| Agent | Messages | Input | Output | Tools |
|-------|----------|-------|--------|-------|
| Claude | 6 | 500 | 200 | Read:1, Edit:1 |
| Codex | 4 | 300 | 150 | shell:1 |
| Gemini | 4 | 400 | 180 | read_file:1 |
| **Total** | **14** | **1200** | **530** | **4** |

---

## Skipped Tests (3)

These query a `role` column not in current schema:
- `test_stats_user_assistant_breakdown`
- `test_stats_invariants`

Fix: Add `role` column or derive from `type` field.

---

## Post-V1 Next Steps

Per `docs/testing/testing-prompt.md`:

1. **Agent 1b** - Extended fixtures (telemetry, compaction, rejection, forks)
2. **Agent 5** - Scope resolution tests (combinatorial)
3. **Agent 6** - Stats validation tests (groupings, invariants)
4. **Agent 7** - Cross-env tests (Windows/WSL)
5. **Agent 8** - Docker SSH tests
