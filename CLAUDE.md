# CLAUDE.md

See `docs/specs/` for all specifications.

## Testing

Use the cross-platform runner:

```bash
python scripts/run_tests.py
```

Run `uv sync --dev` first on a fresh checkout. On Windows, the runner sets temp
dirs and disables pytest cache by default.
