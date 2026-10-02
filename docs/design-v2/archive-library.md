# Session Archive And Catalog Library

<!-- doc-meta
doc_role: design
audience: contributor
lifecycle: proposed
content_type: architecture
surface: internal
canonicality: canonical
-->

This document designs `agent_history.archive`, a library and set of `cagelens archive`
commands that:

1. collect agent session files from several machines and saved copies into one
   compressed archive that never loses content, and
2. keep a catalog database that describes every archived file and session.

The library holds no knowledge of any particular user's machines. Everything
specific to a deployment comes from a configuration file.

## Terms

| Term | Meaning |
|---|---|
| Agent home | The folders an agent writes under a user's home directory, such as `~/.claude` or `~/.codex`. |
| Source | One home directory to archive, with a unique name. A live machine's home, a saved copy of a retired machine's home, and a restored backup are each a source. |
| Source kind | `live` (a home in use), `imported` (a saved copy that will not change), or `restored` (files recovered from a backup). |
| Archive | A directory tree, local or on a remote host over SSH, that holds compressed copies of every source's files. |
| Collector | The `cagelens archive collect` command. It copies new and changed files from a source into the archive. |
| Run | One execution of the collector for one source. |
| Manifest | The record a run writes when it finishes. It lists what the run wrote. |
| Catalog | A database (SQLite or PostgreSQL) that describes the archive's files and sessions. It holds metadata only, never message text. |

## Requirements

- **Never lose content.** The archive never deletes a file. If a source file is
  deleted, the archive keeps it. If a source file is rewritten rather than appended
  to, the archive keeps the previous version too.
- **Lossless compression.** Every archived file is the original bytes compressed
  with Zstandard (zstd). Decompressing it gives back a file with the same SHA-256
  hash.
- **One archived file per source file.** Any single session can be read without
  unpacking anything else.
- **Incremental.** A run reads, compresses and sends only files that changed since
  the last run.
- **Configuration only.** Hostnames, paths, schedules and alerting addresses come
  from the configuration file. The code and its defaults name no real machine.
- **No credentials.** The collector copies files on an allowlist per agent, and a
  denylist removes known credential files even if a user adds them to the
  allowlist.
- **Metadata-only catalog.** The catalog stores paths, sizes, hashes, times, IDs,
  counts and similar fields. It does not store prompts, responses, tool output or
  session titles.
- **Cross-platform.** The collector runs on Linux, macOS and Windows with
  Python 3.8 or later. The catalog's PostgreSQL store is optional.

## Archive Layout

```
<archive root>/
  ARCHIVE.json                                  format version
  sources/<source>/SOURCE.json                  name, kind, platform, note
  sources/<source>/files/<home-relative path>.zst
  sources/<source>/versions/<home-relative path>.<UTC time>.zst
  sources/<source>/manifests/<run id>.jsonl.zst
```

- Paths under `files/` mirror the source's home directory, for example
  `files/.claude/projects/-home-alex-shop/1f0c….jsonl.zst`. Someone who knows the
  original path can find the archived copy without a lookup.
- **Every archived file has `.zst` added**, including files that are already
  compressed. A Codex `rollout-….jsonl.zst` becomes `rollout-….jsonl.zst.zst`.
  This keeps the mapping from original path to archived path one-to-one.
- Each archived file keeps the original's modification time.
- `versions/` holds a previous version of a file that was rewritten rather than
  appended to (see the content-loss guard below).
- The format version in `ARCHIVE.json` starts at 1. A collector refuses to write
  into an archive with a format version it does not know.

## Configuration

The default path is `~/.cagelens/archive.json`. `--config` overrides it. The file
uses JSON, like the existing `~/.cagelens/config.json`.

```json
{
  "archive": {
    "destination": "ssh://backup-host/srv/agent-archive",
    "compression_level": 19,
    "min_interval_hours": 20,
    "health_url": "https://healthchecks.example/ping/0000"
  },
  "sources": [
    {"name": "laptop-linux", "kind": "live", "platform": "linux", "home": "~"},
    {"name": "laptop-windows", "kind": "live", "platform": "windows",
     "home": "/mnt/c/Users/alex"},
    {"name": "old-vm", "kind": "imported", "platform": "linux",
     "home": "/archives/old-vm/home/alex",
     "note": "Saved copy of a retired VM's home"},
    {"name": "laptop-linux", "kind": "live", "platform": "linux",
     "roots": {"claude": "/srv/old-archive/raw/laptop-linux/claude"}}
  ]
}
```

| Field | Meaning |
|---|---|
| `destination` | A local path (which may be a network mount) or `ssh://host/path`. |
| `compression_level` | The zstd level, 1–19. The default is 19. Higher levels make smaller files and compress more slowly; reading is about equally fast at every level. |
| `min_interval_hours` | A run exits without work if the source's last successful run was more recent. A scheduler can then start the collector often (for example hourly) and still get one run a day, plus a catch-up run after a machine was off. `--force` ignores it. |
| `workers` | Files compressed in parallel. The default is the number of CPUs, at most 8. |
| `health_url` | Optional. The collector requests `<url>/start` at the beginning, `<url>` on success and `<url>/fail` on failure. Any service that accepts these requests works. |
| `sources[].home` | The home directory to read. Agent folders are found under it with the default layouts below. |
| `sources[].platform` | `linux`, `darwin` or `windows`. It selects platform-specific default folders, such as where VS Code keeps its chats. It describes the source, not the machine the collector runs on, so a Linux collector can read a Windows home through a mount. |
| `sources[].roots` | Optional per-agent folders that replace the defaults. They are used to bring in an existing tree whose layout differs from a home directory. |
| `sources[].agents` | Optional list of agents to include. The default is every agent below. |
| `sources[].include`, `exclude` | Optional extra glob patterns, relative to the home. They may not leave the home. |
| `sources[].note` | Optional text recorded in the source's `SOURCE.json`. |

Unknown settings are rejected, so a misspelt name fails instead of being ignored.

A source name may appear more than once if each entry covers different agents or
roots. The entries merge into one source in the archive.

## Default Agent Layouts

Each agent has an allowlist of paths relative to the home. Paths that do not exist
are skipped.

| Agent | Included | Excluded |
|---|---|---|
| Claude Code | `.claude/projects`, `sessions`, `history.jsonl`, `todos`, `plans`, `tasks`, `file-history`, `usage-data` | — |
| Codex | `.codex/sessions`, `archived_sessions`, `history.jsonl`, `session_index.jsonl`; databases `state_*.sqlite`, `memories_*.sqlite`, `goals_*.sqlite`, `queue_*.sqlite`; new rows of `logs_*.sqlite` | everything else, including `auth.json` and `thread_history_*.sqlite` |
| Gemini CLI | `.gemini/history`, `tmp`, `antigravity` | `tmp/*/tool-outputs/**`, `tmp/bin/**`, `oauth_creds.json`, `google_accounts.json` |
| Pi | `.pi/agent/sessions` | `.pi/agent/auth.json` |
| Copilot CLI (`copilot-cli`) | `.copilot/session-state`, `chats`, `history-session-state`; databases `session-store.db`, `data.db`, `data.db.pre-update-backup-*`, `session-state/*/session.db` | everything else, including `mcp-oauth-config`, `config.json` and `repo-metadata-cache.db` |
| Copilot in VS Code (`copilot-vscode`) | `<VS Code user dir>/workspaceStorage/*/GitHub.copilot-chat/**`, `workspaceStorage/*/chatSessions/**` | — |
| cagelens | `config.json`, `aliases*.json` and `project_tags*` in `.cagelens` and the older `.agent-history` | caches, which hold copies of other machines' sessions |

Agent names are the cagelens backend ids, as used by `--agent`.

- The VS Code user directory depends on `platform`: `AppData/Roaming/Code/User`
  on Windows, `Library/Application Support/Code/User` on macOS, and
  `.config/Code/User` and `.vscode-server/data/User` on Linux. The `Code - Insiders`
  variants are included too.
- Every layout also excludes `*.tmp`, `*.part`, `*.lock`, and SQLite side files
  (`*-wal`, `*-shm`, `*-journal`). A database snapshot already contains what those
  side files hold.
- The rule for databases: keep a database when it holds information that is not in
  the agent's JSONL or JSON files, and skip it when it is built entirely from them.
  For example, Copilot's `session-store.db` keeps sessions after Copilot has
  deleted their JSONL folders, so it is kept. Codex's `thread_history_*.sqlite` is
  built from the rollout files and records how far into each one it has read, so it
  is skipped. Caches are skipped.
- The global denylist removes `auth.json`, `*oauth*`, `*.pem`, `*.key`,
  `.credentials.json`, `credentials*` and browser credential stores (`Cookies`,
  `Login Data`, `Web Data`, `Local State`, `cookies.sqlite`, `logins.json`, `key4.db`)
  everywhere, whatever the configuration says. Names are compared case-insensitively.
- **Browser profiles are skipped whole.** Agents that drive a browser can leave a
  profile inside a session folder: Copilot sessions were found holding Chrome profiles
  of several hundred MB, with cookies and saved logins. A folder holding `Local State`,
  `cookies.sqlite`, `logins.json` or `key4.db` is not descended into.
- **The walk only descends where a pattern can match.** Patterns are followed folder by
  folder, and only a `**` segment walks a whole subtree, so a pattern such as
  `state_*.sqlite` lists one folder instead of walking all of `.codex`. Symbolic links
  are never followed.
- The layouts live in one module (`archive/layouts.py`). When an agent changes its
  storage, that module and its tests change, and nothing else.

## Collector

### Change detection

The collector keeps a state file per source and destination at
`~/.cagelens/archive-state/<destination hash>/<source>.json` (`--state-dir` overrides
the folder). For each
archived path it records the original size, modification time (nanoseconds) and
SHA-256 hash.

A file is **changed** if its size or modification time differs from the state.
The collector hashes only changed files.

If the state file is missing, for example on a new machine, the collector rebuilds
it by reading the source's manifests from the archive.

**Recently modified files.** A file can change again within the same filesystem
timestamp tick without its size changing, for example a database's last write. A file
modified within 2 seconds of being read is marked `racy` in the manifest, and its
state is not trusted: the next run reads it again and compares hashes. This is the same
problem and remedy as Git's "racy clean" files.

### Content-loss guard

Most session files only grow. Before overwriting an archived file, the collector
checks that the new content extends the old:

- the new size is at least the recorded size, and
- the SHA-256 of the new file's first *recorded size* bytes equals the recorded
  hash.

If either check fails, the file was rewritten. The collector first moves the
archived copy to `versions/<path>.<UTC time>.zst`, then writes the new one. Nothing
is deleted.

Some files are rewritten by design every time they change, such as to-do lists,
index files and database snapshots. They keep every version too. The volume is
small. For example, the database snapshots of one machine with Codex and Copilot
(about 5 MB a day after compression) add roughly 2 GB a year.

### Databases

Some agents keep SQLite databases that hold information found nowhere else. The
layout marks each kept database as a **snapshot** database or a **log** database.

**Snapshot databases.** Copying a database file while the agent writes to it can
produce a broken copy. So for each changed snapshot database the collector:

1. treats the database as changed when the size or modification time of the file
   or of its `-wal` side file changed;
2. copies it with SQLite's backup API, from a read-only connection, into a temporary
   file, which gives a consistent copy that includes the `-wal` content. Some
   filesystems (WSL's `/mnt/c`) cannot open a WAL database read-only; then the file and
   its WAL are copied to local disk, the copy is retried if the source changed while
   being copied, and the copy must pass `PRAGMA quick_check` before it is used;
3. blanks credential columns in the copy (see below), then runs `VACUUM` so that
   the blanked values do not survive in free pages of the file;
4. hashes, compresses and archives the copy like any other file, under the
   database's own path.

A snapshot is never an append of the previous one, so every snapshot after the
first goes through `versions/` as a rewrite. An empty `-wal` file counts as none, because
opening a WAL database, even read-only, can create one.

**Credential columns.** The layout lists, per database, the columns that hold
credentials. For example, Copilot's `data.db` holds GitHub access tokens in
`accounts.access_token` and `settings.github_access_token`. In addition, any
column in any database whose name matches `access_token`, `refresh_token`,
`id_token`, `api_key`, `secret` or `password` is blanked. Token-count columns, such
as `input_tokens`, do not match. The manifest records which columns were blanked.

**Log databases.** Codex keeps its diagnostic logs in `logs_*.sqlite`, about
400 MB holding roughly the last 10 days; Codex deletes older rows itself. A daily
snapshot would repeat about nine days of rows each time. Instead, the collector
exports only new rows:

- The layout names the table and its increasing key: `logs` and `id` for Codex.
- Each run reads the rows whose key is above the last exported key and writes them
  as JSON Lines to `<path>.rows/<UTC time>.jsonl.zst`, for example
  `.codex/logs_2.sqlite.rows/20261002T061500Z.jsonl.zst`.
- The state file records the last exported key for each database and table.
- If the newest key in the database is below the recorded key, the database was
  recreated. The run then exports from the start and records that in the manifest.
- A new file name, such as `logs_3.sqlite` after an agent upgrade, starts its own
  export.

**Failures.** If a database cannot be read, for example because of a lock held
across a network mount, the run records an error for that file, keeps going, and
retries on the next run.

### Steps of a run

1. Take an exclusive lock for the source in the state directory. If another run
   holds it, exit without work.
2. Skip the run if `min_interval_hours` has not passed, unless `--force` is given.
3. Walk the layout's included paths, apply exclusions and collect file sizes and
   times.
4. For each changed file: copy and redact it if it is a snapshot database, or
   export its new rows if it is a log database; then hash it, apply the
   content-loss guard, and compress it into a staging folder laid out like the
   archive. `workers` files are processed in parallel, and entries are recorded in
   walk order. The staging folder is under the state folder, never the system temp
   folder, which is often a small in-memory filesystem.
5. Whenever about 512 MB is staged, and at the end, transfer the staging folder,
   after first moving aside the archived copies that rewrites will replace:
   - **Local destination:** write each file as `<name>.part`, then rename it into
     place.
   - **SSH destination:** run the `versions/` moves as one remote shell command,
     then stream a tar archive into `tar -xf -` on the remote host. The remote host
     needs only `sh`, `mkdir`, `mv` and `tar`.
6. After the last transfer, write the manifest. The manifest is the commit record: a file counts as archived
   only when a manifest lists it. If a run stops before step 6, the next run
   rewrites the same files, and readers ignore files no manifest lists.
7. Update the local state file and send the success request to `health_url`.

### Manifest format

A manifest is a compressed JSON Lines file. The first line describes the run, and
each following line describes one path.

```json
{"type": "run", "run_id": "20261002T061500Z-laptop-linux-3f2a", "source": "laptop-linux",
 "collector_host": "laptop", "tool_version": "2.1.0", "format": 1,
 "started_at": "2026-10-02T06:15:00Z", "finished_at": "2026-10-02T06:16:12Z",
 "written": 214, "bytes_original": 81234567, "bytes_compressed": 14567890, "errors": 0}
{"type": "file", "path": ".claude/projects/-home-alex-shop/1f0c.jsonl", "action": "updated",
 "size": 512345, "mtime_ns": 1790000000000000000, "sha256": "…", "compressed_size": 98765}
{"type": "file", "path": ".codex/history.jsonl", "action": "versioned",
 "previous_sha256": "…", "version_path": "versions/.codex/history.jsonl.20261002T061500Z.zst"}
{"type": "file", "path": ".copilot/data.db", "action": "versioned", "kind": "sqlite-snapshot",
 "blanked": ["accounts.access_token", "settings.github_access_token"], "sha256": "…", "…": "…"}
{"type": "rows", "path": ".codex/logs_2.sqlite", "table": "logs", "key": "id",
 "from_key": 98921, "to_key": 101544, "rows": 2623,
 "export_path": ".codex/logs_2.sqlite.rows/20261002T061500Z.jsonl.zst"}
{"type": "file", "path": ".claude/todos/old.json", "action": "gone"}
{"type": "error", "path": ".copilot/session-store.db", "message": "database is locked"}
```

`action` is `added`, `updated`, `versioned` (a previous version was moved aside)
or `gone`. `gone` means the path is in the state but no longer in the source. The
archive keeps the file; the manifest only records that the source deleted it.

### Verification

`cagelens archive verify` decompresses archived files and compares each one's
SHA-256 hash and size with its manifest entry. `--all` checks every file, and
`--sample N` checks N random files. It also reports files that no manifest lists,
such as leftovers from a run that was interrupted.

## Catalog

### What it records

The catalog has one row per source, per run, per archived file and per session.

| Table | Key | Main columns |
|---|---|---|
| `sources` | `name` | kind, platform, note, first and last run time |
| `runs` | `run_id` | source, collector host, tool version, start and finish, counts, errors |
| `files` | `source`, `path` | agent, kind (file, database snapshot or row export), size, modification time, SHA-256, compressed size, archive path, first run, last written run, run in which it went `gone` |
| `file_versions` | `source`, `path`, `run_id` | SHA-256, size, modification time, archive path (kept versions only), the run that superseded it |
| `row_exports` | `source`, `archive_path` | database path, table, first and last key, row count, whether the database was recreated, run, SHA-256, size |
| `sessions` | `source`, `path`, `session_id` | agent, workspace, working directory, project, git branch, models, first and last message time, message counts by role, tool-use count, token totals, parent session ID, lineage kind, file SHA-256 |
| `schema_meta` | — | schema version |

Sessions are read from session files by the agent's cagelens parser (`extract_stats`),
and from databases by a query in the layout that returns each session's id, working
directory, branch, first and last time, and message count. Timestamps are stored as
ISO 8601 UTC; epoch seconds and milliseconds are converted.

A session can be known only from a database. For example, Copilot's
`session-store.db` keeps sessions whose JSONL folders Copilot deleted. Such a
session's row has the database's path and is marked as coming from a database.

The view `session_copies` groups `sessions` by agent and session ID. It shows how
many sources hold each session and which copy is the longest. The same session can
appear in several sources, for example in a live home and in a restored backup,
and a copy can be an earlier, shorter state of the same session.

### Updating

`cagelens archive catalog sync` reads manifests that the catalog has not yet
ingested, oldest first. For each run it:

1. records the run,
2. updates `files` and `file_versions`,
3. decompresses each added or updated session file and extracts its session
   metadata with the agent's existing parser in `backends/`,
4. marks `gone` paths.

All changes for one run go into one transaction. Because sync follows manifests
rather than walking the archive, a daily update reads only that day's files, even
when the archive is on a network mount.

`cagelens archive catalog rebuild` drops the catalog's tables and replays every
manifest. `cagelens archive catalog status` prints counts per source and the
newest run per source.

### Stores

The catalog code talks to a small `CatalogStore` interface. Two implementations
exist:

- **SQLite** through the standard library. It is the default, at
  `~/.cagelens/archive-catalog.db`.
- **PostgreSQL** through psycopg 3, installed with the `postgres` extra. The
  connection is a libpq connection string, such as `dbname=agent_archive`, so
  socket and peer authentication work without a password in the configuration.

Both stores use the same table definitions, written in the SQL that SQLite and
PostgreSQL share, plus small per-store type mappings (`jsonb` and `timestamptz` in
PostgreSQL, `TEXT` in SQLite). The store creates and migrates its own tables, and
records the schema version in `schema_meta`.

## Reading The Archive With cagelens

- **A new home type, `archive:<config source name>` or `archive:<path>`.** It
  resolves each agent's folder inside `sources/<name>/files/`. Every existing
  command (`session list`, `export`, `stats`) then works on archived and saved
  copies as it does on a live machine.
- **Transparent decompression.** A helper, `utils/io.py:open_session_text`, opens
  `x` or `x.zst` and returns text. All backends read through it, and session
  scanners also look for the `.zst` names. The Codex backend's own `.zst` handling
  moves into this helper.

## Changes To Existing Code

- **Backends stop importing storage and export code.** The Claude and Codex
  backends read cached message counts from `metrics.db` directly. They will take an
  optional lookup function instead. The Pi and Copilot backends import
  `export.markdown`; that code moves to `export/`, which calls the backends rather
  than the reverse.
- **Session metadata extraction becomes a backend function** that takes an open
  text stream and returns a plain record. The catalog and `storage/metrics.py` both
  use it.
- `zstandard` becomes a declared dependency of the `archive` extra. It is
  currently imported without being declared.

## Package Layout And Commands

```
agent_history/archive/
  __init__.py          public API: load_config, collect_source, verify_source, ...
  errors.py            ArchiveError and ArchiveConfigError
  config.py            configuration loading and validation
  layouts.py           per-agent file lists, session patterns, the credential denylist,
                       browser-profile skipping, and archive path mapping
  codec.py             zstd compression, hashing, and the open-either-name helper
  state.py             collector state, rebuilding it from manifests, the source lock
  manifest.py          manifest writing and reading
  transport.py         the destination interface and the local destination
  ssh_destination.py   the SSH destination
  databases.py         SQLite snapshots, credential blanking and log row export
  collect.py           the run steps
  verify.py            verification
  cli.py               the `cagelens archive` commands
  catalog/
    schema.py          table definitions for SQLite and PostgreSQL
    store.py           the CatalogStore interface and both stores
    sync.py            manifest ingestion, session extraction, status
```

```
cagelens archive collect [--source NAME]... [--force] [--dry-run] [--state-dir DIR]
cagelens archive verify  [--source NAME]... [--all | --sample N]
cagelens archive catalog sync | rebuild | status [--store sqlite:PATH | postgres:CONNINFO]
```

Every command also takes `--config PATH`, `--destination` (overrides the configured one)
and `--json`. Exit codes: 0 success; 1 the command failed; 2 it finished but found
problems (files that could not be read, or verification differences). The catalog
defaults to `sqlite:~/.cagelens/archive-catalog.db`. `archive` must be the first word
after `cagelens`, because it does not use the session-scope options.

`--dry-run` lists what a run would write and which files the content-loss guard
would version, without writing. It hashes changed files that are already archived and
compresses nothing.

Packaging: `pip install "cagelens[archive]"`, or `cagelens[archive,postgres]` for a
PostgreSQL catalog.

## Scheduling

The library does not schedule anything. A deployment runs `cagelens archive
collect` from cron, launchd, systemd or Task Scheduler. With `min_interval_hours`
it can run hourly, so a machine that was off at the usual time catches up when it
next runs.

## Testing

- **Unit tests:**
  - path mapping, including the round trip from original to archived path and
    back (property tests with Hypothesis);
  - change detection and rebuilding the state from manifests;
  - the content-loss guard for appends, rewrites and truncation;
  - the credential denylist overriding user includes;
  - SQLite snapshots of a database with a write-ahead log;
  - credential blanking: after `VACUUM`, the token value occurs nowhere in the
    archived bytes, and token-count columns are untouched;
  - row export: only new rows on the next run, a full export after the database
    is recreated, and a separate export for a new file name;
  - compression round trips with hash comparison.
- **Interrupted runs:** a run killed between transfer and manifest leaves files
  that `verify` reports and the next run rewrites.
- **SSH destination:** extend the existing Docker end-to-end setup
  (`tests/e2e_docker`) with a destination node that has only `sh` and `tar`.
- **Catalog:**
  - SQLite tests always run.
  - PostgreSQL tests run when server binaries are on the machine. Otherwise they
    are skipped.
  - Both stores run the same test suite.
- **Fixtures** are synthetic homes built in temporary directories. They contain no
  real session content.

## Open Questions

- Whether VS Code's per-workspace `state.vscdb` databases hold Copilot chat
  information that is not in the `chatSessions` and `GitHub.copilot-chat` files.
  This design leaves them out until that is checked.
- Whether the catalog should also hold session titles, which can contain
  sensitive text. This design leaves them out.
