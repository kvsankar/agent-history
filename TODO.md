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

## Command Combinations

- [ ] Multiple `-r` flags only use first (document or warn)
- [ ] `--split --minimal` uses non-minimal line estimates
- [ ] `--alias` with pattern silently ignores pattern
