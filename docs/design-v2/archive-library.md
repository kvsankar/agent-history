# Session Archive And Catalog Library

<!-- doc-meta
doc_role: design
audience: contributor
lifecycle: current
content_type: architecture
surface: internal
canonicality: canonical
-->

This document describes `agent_history.archive`, a library and set of `cagelens archive`
commands that:

1. collect agent session files from several machines and saved copies into one
   compressed archive that never loses content, and
2. keep a catalog database that describes every archived file and session.

The library holds no knowledge of any particular user's machines. Everything
specific to a deployment comes from a configuration file.

The library and commands are built. The sections marked **Not built yet** describe
planned work.

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
  Python 3.10 or later. `pyproject.toml` declares Python 3.8, but modules the package
  imports, such as `storage/metrics.py`, use annotations (`str | None`) that Python
  3.8 and 3.9 cannot evaluate. The catalog's PostgreSQL store is optional.

## Archive Layout

```
<archive root>/
  ARCHIVE.json                                  format version
  sources/<source>/SOURCE.json                  name, kind, platform, note
  sources/<source>/files/<home-relative path>.zst
  sources/<source>/versions/<home-relative path>.<run stamp>-<run suffix>.zst
  sources/<source>/manifests/<run id>.jsonl.zst
  sources/<source>/incoming/<run id>/           a run's files in transit (transient)
  sources/<source>/LOCK/owner.json              the lock of a run in progress (transient)
```

- Paths under `files/` mirror the source's home directory, for example
  `files/.claude/projects/-home-alex-shop/1f0c….jsonl.zst`. Someone who knows the
  original path can find the archived copy without a lookup.
- **Every archived file has `.zst` added**, including files that are already
  compressed. A Codex `rollout-….jsonl.zst` becomes `rollout-….jsonl.zst.zst`.
  This keeps the mapping from original path to archived path one-to-one.
- Each archived file keeps the original's modification time. A database snapshot
  keeps the database file's time. A row export (see Databases) has the time at which
  it was compressed.
- `versions/` holds a previous version of a file that was rewritten rather than
  appended to (see the content-loss guard below). The run stamp and run suffix come
  from the run ID: in `20261002T061500Z-laptop-linux-3f2a`, the run stamp is
  `20261002T061500Z` and the run suffix is `3f2a`, the last 4 characters.
- `incoming/<run id>/` holds a run's files while they are transferred. It is laid out
  like the source's folder, so a new copy's path under it is the same as its final
  path under `sources/<source>/`. The run removes it when it commits (see Steps of a
  run). Readers never use it.
- **Run IDs.** A run ID is `<run stamp>-<source>-<4 random hex characters>`. The run
  stamp is the run's start time in UTC to the second. When the source's newest
  committed run has a stamp at or after that time, the run stamp is one second after
  that newest stamp instead, so every run ID sorts after the runs before it. Readers
  apply a source's manifests in run ID order. Run IDs that do not start with a stamp
  are ignored for this comparison. The manifest's `started_at` records the real start
  time.
- `LOCK/` is the source's lock in the archive. A run holds it while it changes the
  source's folder (see Locks).
- The format version in `ARCHIVE.json` starts at 1. A collector refuses to write
  into an archive with a format version it does not know. A run creates
  `ARCHIVE.json` only when the archive holds no runs yet (see Destination checks).

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
    {"name": "laptop-linux-old-claude", "kind": "imported", "platform": "linux",
     "roots": {"claude": "/srv/old-archive/raw/laptop-linux/claude"},
     "note": "Older copy of the laptop's Claude folder"}
  ]
}
```

| Field | Meaning |
|---|---|
| `destination` | A local path (which may be a network mount) or `ssh://host/path`. |
| `compression_level` | The zstd level, 1–19. The default is 19. Higher levels make smaller files and compress more slowly; reading is about equally fast at every level. |
| `min_interval_hours` | A run exits without work if the source's last run without errors started more recently. A run that recorded errors does not count, so it is retried at the next start. A scheduler can then start the collector often (for example hourly) and still get one run a day, plus a catch-up run after a machine was off. A run that is not due still runs when an interrupted run waits to be finished (see Steps of a run). `--force` ignores it. The default is 0, so every start runs. |
| `workers` | Files compressed in parallel, an integer from 1 to 64. The default is the number of CPUs, at most 4. Each worker keeps its own compressor, so memory use grows with the number of workers. |
| `health_url` | Optional. The collector requests `<url>/start` at the beginning, `<url>` on success and `<url>/fail` on failure. Any service that accepts these requests works. |
| `sources[].home` | The home directory to read. Agent folders are found under it with the default layouts below. |
| `sources[].platform` | `linux`, `darwin` or `windows`. It selects platform-specific default folders, such as where VS Code keeps its chats. It describes the source, not the machine the collector runs on, so a Linux collector can read a Windows home through a mount. |
| `sources[].roots` | Optional per-agent folders that replace the defaults. They are used to bring in an existing tree whose layout differs from a home directory. |
| `sources[].agents` | Optional list of agents to include. The default is every agent below. An empty list (`[]`) means no agent folders: the entry reads only its `include` patterns. |
| `sources[].include`, `exclude` | Optional extra glob patterns, relative to the home. They may not leave the home. A file that an include selects inside an agent's folder follows that agent's layout (see Default Agent Layouts). |
| `sources[].note` | Optional text recorded in the source's `SOURCE.json`. |

Unknown settings are rejected, so a misspelt name fails instead of being ignored.

A source name may appear more than once. The entries merge into one source in the
archive. They must agree on kind and platform, and no two of them may cover the same
agent. An entry covers the agents in its `agents` list (every agent when the list is
absent) for which it has a `home` or a `roots` override. A `roots` override for an
agent outside the entry's `agents` list does not count. When two entries cover one
agent, their files would map to the same archive paths, so loading the configuration
fails. The error tells the user to give the other copy its own source name, for
example with kind `imported`. The example above does this for an older copy of a
Claude folder, `laptop-linux-old-claude`.

Include patterns of different entries can still map different files to the same
archive path. Then the first entry's file is archived. A differing file from another
entry is not archived; the run records an error entry for it instead. Files of the
same size and modification time count as the same file. Files of the same size with
different modification times are compared byte by byte. The fix is to give that folder
its own source name.

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
| Copilot in VS Code (`copilot-vscode`) | `<VS Code user dir>/workspaceStorage/*/GitHub.copilot-chat/**`, `workspaceStorage/*/chatSessions/**` | `*.sqlite`, `*.sqlite3` and `*.db` under `workspaceStorage/*/GitHub.copilot-chat/`: indexes of the workspace's files that Copilot rebuilds, with no chat content |
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
- The global denylist removes these names whatever the configuration says. It
  applies to file names everywhere, and to every folder name on the path of a file
  that a configuration include selects. Folder names are not checked for files that
  the default layouts select, because Claude project folders are named after working
  folders: a project in a folder called `oauth-proxy` keeps its sessions. Names are
  compared case-insensitively.
  - Agent credentials and tokens: `auth.json`, `*oauth*`, `*.token`, `*tokens.json`,
    `.credentials.json`, `credentials*`, `google_accounts.json`.
  - Keys and certificate stores: `*.pem`, `*.key`, `id_rsa*`, `id_dsa*`, `id_ecdsa*`
    and `id_ed25519*` (public `.pub` keys included), `*.ppk`, `*.p12`, `*.pfx`.
  - Other tools' password and token files: `.netrc`, `_netrc`, `.git-credentials`,
    `.pgpass`, `.npmrc`, `.pypirc`.
  - Browser credential stores: `*cookies` (such as `Cookies`, `Extension Cookies` and
    `Safe Browsing Cookies`), `cookies.txt`, `cookies.sqlite*`, `Login Data*`,
    `Web Data*`, `Local State`, `key4.db`, `logins.json`.
- **Browser profiles are skipped whole.** Agents that drive a browser can leave a
  profile inside a session folder. A Copilot session folder can hold a Chrome profile
  of several hundred MB, with cookies and saved logins. A folder counts as a profile,
  and is not descended into, if it holds any of `Local State`, `Login Data`, `Cookies`,
  `Web Data`, `cookies.sqlite`, `logins.json` or `key4.db`; or both `Preferences` and
  `Secure Preferences`; or a `Network/` subfolder holding `Cookies`. `Preferences`
  alone does not count. Names are compared case-insensitively.
- **Configuration includes follow the agent's layout.** A file that a configuration
  include selects inside an agent's folder gets that agent's rules, as if the layout
  had selected it: the layout's exclusions apply, and a database that a layout rule
  names is snapshotted and blanked, or exported by rows. So an include can add files
  to an agent folder, such as a settings file, but cannot copy a database raw or bring
  back what the layout leaves out. A SQLite file that no layout rule names, inside or
  outside an agent folder, is copied as a plain file.
- **Session files.** Each layout also names the files that hold sessions, which the
  catalog reads (see Catalog). For Claude Code these are `projects/*/*.jsonl`,
  `projects/*/*/subagents/*.jsonl`, and the sub-agent transcripts of workflows,
  `projects/*/*/subagents/workflows/*/agent-*.jsonl`. The `journal.jsonl` beside
  those transcripts holds workflow steps and is not a session.
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
the folder). The destination hash is taken from the destination as written: the
configured one, or the `--destination` value. So a run with `--destination` keeps its
own state and its own local lock. For each
archived path it records the original size, modification time (nanoseconds) and
SHA-256 hash.

A file is **changed** if its size or modification time differs from the state.
The collector hashes only changed files. A changed file whose hash equals the recorded
hash is recorded as `touched` and is not written again.

The state also lists the IDs of the runs whose manifests it includes. Each run applies,
oldest first, every manifest in the archive that the state does not include yet. When
the state file is missing, for example on a new machine, this rebuilds the whole state
from the source's manifests. A state file without the list counts as including every
run up to the last run ID it records.

**Destination checks.** A network mount that is not mounted looks like an empty
folder, and a restored archive can be older than the state. So before it writes
anything, a run refuses to continue when:

- `ARCHIVE.json` is missing but runs exist, either as this source's manifests or in
  any state file for this destination; or
- a run that the state records has no manifest at the destination. The destination
  may be an older copy. Removing the state file rebuilds it from the manifests that
  are there.

`ARCHIVE.json` is created only on a first run.

**Recently modified files.** A file can change again within the same filesystem
timestamp tick without its size changing, for example a database's last write. A file
modified less than 2 seconds before the collector starts reading it is marked `racy`
in the manifest, and its
state is not trusted: the next run reads it again and compares hashes. This is the same
problem and remedy as Git's "racy clean" files.

### Content-loss guard

Most session files only grow. Before overwriting an archived file, the collector
checks that the new content extends the old:

- the new size is at least the recorded size, and
- the SHA-256 of the new file's first *recorded size* bytes equals the recorded
  hash.

If either check fails, the file was rewritten. When the run commits, it moves the
archived copy to `versions/<path>.<run stamp>-<run suffix>.zst` before it moves the new
copy into place. Nothing is deleted.

If the archived copy is missing at that point, for example because it was removed
outside the collector, it cannot be kept. The file's entry then gets action `added`
and no version, and the run records an error entry for it.

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
   or of its `-wal` side file changed. An empty `-wal` file counts as none, because
   opening a WAL database, even read-only, can create one;
2. copies it with SQLite's backup API, from a read-only connection, into a temporary
   file, which gives a consistent copy that includes the `-wal` content. Some
   filesystems, such as `/mnt/c` in the Windows Subsystem for Linux (WSL), cannot open
   a WAL database read-only; then the file and
   its WAL are copied to local disk, the copy is retried if the source changed while
   being copied, and the copy must pass `PRAGMA quick_check` before it is used;
3. blanks credential columns in the copy (see below), then runs `VACUUM` so that
   the blanked values do not survive in free pages of the file;
4. hashes, compresses and archives the copy like any other file, under the
   database's own path.

A snapshot is never treated as an append of the previous one, so every snapshot
after the first whose content differs goes through `versions/` as a rewrite.

**Credential columns.** The layout lists, per database, the columns that hold
credentials. For example, Copilot's `data.db` holds GitHub access tokens in
`accounts.access_token` and `settings.github_access_token`. In addition, any
column in any database whose name contains `access_token`, `refresh_token`,
`id_token`, `api_key`, `apikey`, `secret` or `password`, ignoring case, is blanked.
Token-count columns, such as `input_tokens`, do not match. The manifest records which
columns were blanked.

Blanking keeps every row valid:

- A column that allows NULL is set to NULL.
- A `NOT NULL` column gets an empty value of its declared type: `''`, an empty blob,
  `0` or `0.0`.
- A column in a primary key or a UNIQUE index, or one whose CHECK constraint refuses
  the empty value, gets a random value per row.

Random values differ on every run, so a database with such a column gets a new
version whenever its file changes.

**Log databases.** Codex keeps its diagnostic logs in `logs_*.sqlite`, about
400 MB holding roughly the last 10 days; Codex deletes older rows itself. A daily
snapshot would repeat about nine days of rows each time. Instead, the collector
exports only new rows:

- The layout names the table and its increasing key: `logs` and `id` for Codex.
- Each run reads the rows whose key is above the last exported key and writes them
  as JSON Lines to `<path>.rows/<run stamp>-<run suffix>.jsonl.zst`, for example
  `.codex/logs_2.sqlite.rows/20261002T061500Z-3f2a.jsonl.zst`.
- Exported rows have credential-named columns, and columns the layout names, set to
  null. The manifest lists those columns under `blanked`. Other columns are exported
  as stored. Codex's log message text can hold token-shaped strings that its debug
  logging writes; blanking works by column name, so it does not remove them.
- The state file records the last exported key for each database and table, and the
  table's identity (below).
- A table counts as recreated (a reset) if its newest key is below the last exported
  key, or its smallest key went down, or both recorded rows still exist and both
  differ. The recorded rows are the rows at the previous smallest key and at the last
  exported key. A reset run exports from the start and records `reset` in the
  manifest. The agent deleting its oldest rows is not a reset.
- For that check, each `rows` entry carries `identity`: the smallest key
  (`first_key`) and the SHA-256 hashes of the rows at that key and at the last
  exported key (`first_sha256`, `last_sha256`). Credential-named columns are left out
  of the hashes. The state keeps the identity for the next run.
- A new file name, such as `logs_3.sqlite` after an agent upgrade, starts its own
  export.

**Failures.** If a database cannot be read, for example because of a lock held
across a network mount, the run records an error for that file, keeps going, and
retries on the next run.

**Unreadable folders.** A configured home or configured root that is missing or cannot
be read fails the run: the run writes no manifest, does not change the state, and
marks nothing gone. A default agent folder that does not exist is skipped without a
message. A folder inside a source that cannot be read gives an error entry whose path
is that folder, and nothing at or below it is marked gone. A run never marks a path
gone if it could not read it.

### Steps of a run

1. Take the local lock: an exclusive lock for the source and destination in the
   state directory. If another run holds it, exit without work; `collect` reports the
   source as skipped.
2. If the state file is missing, rebuild it from the source's manifests.
3. Skip the run if `min_interval_hours` has not passed, unless `--force` is given or
   an interrupted run's manifest waits in `incoming/`. A dry run does not look in
   `incoming/`.
4. Run the destination checks. They only read.
5. Take the source's lock in the archive (see Locks). A dry run skips this step.
6. Send the start request to `health_url`.
7. Create `ARCHIVE.json` on a first run, finish or discard interrupted runs (see
   below), apply the manifests the state lacks, and name the run (see Run IDs). A dry
   run only applies the manifests and names the run.
8. Write `SOURCE.json` (not in a dry run), and remove `staging-*` and `db-*` folders
   that an earlier run left in the source's work folder, `work/<source>/` in the state
   folder.
9. Walk the layout's included paths, apply exclusions and collect file sizes and
   times.
10. For each changed file: copy and redact it if it is a snapshot database, or
    export its new rows if it is a log database; then hash it, apply the
    content-loss guard, and compress it into a staging folder laid out like the
    archive. `workers` files are processed in parallel; entries are recorded as files
    finish and sorted by path at the end. Each worker keeps one single-threaded
    compressor. A file of 64 MB or more is compressed with `workers` zstd threads by a
    compressor built for that file alone, and only one such file is compressed at a
    time, which bounds memory. The staging folder is in `work/<source>/`, never the
    system temp folder, which is often a small in-memory filesystem.
11. Whenever about 512 MB is staged, and at the end, transfer the staging folder to
    `sources/<source>/incoming/<run id>/`. That folder is laid out like the source's
    folder, so no committed path changes during the transfer.
    - **Local destination:** write each file as `<name>.part`, then rename it into
      place.
    - **SSH destination:** stream a tar archive into `tar -xf -` on the remote host.
12. Check that every new copy arrived and that every archived copy to keep as a
    version exists.
13. Write the manifest into the incoming folder. Move the archived copies of rewritten
    files to `versions/`, then move the new copies into place.
14. Move the manifest to `manifests/`. This move commits the run: a file counts as
    archived only when a manifest in `manifests/` lists it.
15. Remove the incoming folder, save the local state file, and send the success
    request to `health_url`, or the failure request if the run recorded errors.
16. Release the lock in the archive. This also happens after a failure.

**Health requests.** A failure after the start request sends the failure request. A
failure before it, while rebuilding the state, checking the destination or taking the
lock in the archive, sends only the failure request. A run skipped for
`min_interval_hours`, or because another run holds a lock, sends no request. A dry run
sends none.

**Locks.** The local lock keeps apart runs that share a state folder and write the
destination the same way. Runs with another state folder, another spelling of the
destination, or on another machine with the same source name share only the archive.
So a run also holds `sources/<source>/LOCK` while it changes the source's folder.

- The lock is a folder, created with one atomic `mkdir`, so of two runs that try at
  the same time only one gets it. Its `owner.json` records the host, the process ID,
  the start time, a token for the run, and a hash of the host name and the local lock
  file's path.
- The run takes the lock after the destination checks, so a refused destination stays
  untouched. Only the run whose token the lock records removes it.
- A lock that a killed run on the same machine left (same host and local lock file) is
  taken over, with a message.
- A lock that another run holds makes the run a skip. `collect` reports the source as
  skipped, names the holder, and goes on; a skip alone gives exit code 0.
  `collect --break-lock` removes the lock first and prints whose it was.
- A dry run neither takes nor checks the lock.

**Interrupted runs.** Each placement step is safe to repeat. The next run finishes an
incoming run that has a manifest, and deletes incoming folders without one. A manifest
in the incoming folder that does not decode was cut short while it was written.
Placing starts only after that write, so such a run placed nothing; the next run
discards it with a warning. A dry run neither finishes nor discards runs.

A run that stops before its manifest is in the incoming folder has changed no
committed path, so `verify` reports nothing for it. The exceptions are `SOURCE.json`,
and `ARCHIVE.json` on a first run, which a run writes at their final paths before the
scan. A run that stops while placing files is listed by `verify` as `pending` until
the next run finishes it, after which `verify` is clean. The next run finishes it even
when `min_interval_hours` has not passed.

**Durability.** Files are flushed to disk (fsync) before each rename into place. The
folders a run changed are flushed before the commit and before the state is saved.
Folder flushes are skipped on Windows and where the filesystem refuses them. Over SSH,
a file is written as `cat > <name>.part && sync && mv <name>.part <name> && sync`, so
its content is on disk before the rename, and every other command that writes or moves
files ends with `sync`.

**SSH destination.** The remote host needs `sh` (with `test`, `[` and `echo`), `cat`,
`mkdir`, `mv`, `find`, `printf`, `tar`, `rm`, `rmdir` and `sync`. `rm` removes only a
source's incoming folder and the owner file of its lock; `rmdir` removes the lock
folder. ssh hands each command to the remote user's login shell, which need not be
`sh`, so every command is sent as `sh -c '<script>'`. Placing a run's files is one
script sent over standard input to `sh -s`, because a first run can move more files
than a command line can hold. Listings run `find` with `-exec printf '%s\0' {} +`, so
names are separated by NUL bytes and a name that holds a line break stays whole. Reads
are streamed from `cat`.

### Manifest format

A manifest is a compressed JSON Lines file. The first line describes the run, and
each following line describes one path.

```json
{"type": "run", "run_id": "20261002T061500Z-laptop-linux-3f2a", "source": "laptop-linux",
 "collector_host": "laptop", "tool_version": "2.1.0", "format": 1,
 "started_at": "2026-10-02T06:15:00+00:00", "finished_at": "2026-10-02T06:16:12+00:00",
 "written": 214, "errors": 0}
{"type": "file", "path": ".claude/projects/-home-alex-shop/1f0c.jsonl", "agent": "claude",
 "action": "updated", "size": 512345, "mtime_ns": 1790000000000000000, "sha256": "…",
 "compressed_size": 98765}
{"type": "file", "path": ".codex/history.jsonl", "action": "versioned",
 "previous_sha256": "…", "previous_size": 40960,
 "version_path": "versions/.codex/history.jsonl.20261002T061500Z-3f2a.zst", "…": "…"}
{"type": "file", "path": ".copilot/data.db", "action": "versioned", "kind": "sqlite-snapshot",
 "blanked": ["accounts.access_token", "settings.github_access_token"], "sha256": "…", "…": "…"}
{"type": "rows", "path": ".codex/logs_2.sqlite", "table": "logs", "key": "id",
 "from_key": 98921, "to_key": 101544, "rows": 2623, "reset": false,
 "identity": {"first_key": 61200, "first_sha256": "…", "last_sha256": "…"},
 "export_path": ".codex/logs_2.sqlite.rows/20261002T061500Z-3f2a.jsonl", "sha256": "…", "…": "…"}
{"type": "file", "path": ".claude/todos/old.json", "action": "gone"}
{"type": "error", "path": ".copilot/session-store.db", "message": "database is locked"}
```

A `rows` entry's export is archived at `files/<export_path>.zst`.

`action` is one of:

- `added`: a new path, or a rewritten file whose archived copy was missing;
- `updated`: the new content extends the archived copy;
- `versioned`: the file was rewritten, and the previous copy was moved to
  `version_path`;
- `touched`: the modification time changed but the content did not, so nothing was
  written;
- `returned`: a path that an earlier run recorded as `gone` is back with the same
  size and modification time as before, so nothing was written;
- `gone`: the path is in the state but no longer in the source. The archive keeps
  the file; the manifest only records that the source deleted it.

Only `added`, `updated` and `versioned` write a file. An entry marked `racy` is
checked again by the next run.

### Verification

`cagelens archive verify` decompresses archived files and compares each one's
SHA-256 hash and size with its manifest entry. `--all` (the default) checks every
file, and `--sample N` checks N random files. The report has five lists:

- `mismatched`: the decompressed content differs from the manifest entry;
- `missing`: a manifest lists the file, but the archive does not hold it;
- `unlisted`: a file under `files/` or `versions/` that no manifest lists;
- `errors`: a file that could not be read, for example because the connection
  dropped. Such a file is not counted as mismatched;
- `pending`: the IDs of interrupted runs whose manifest waits in `incoming/`. The next
  `collect` finishes them.

Verify reads the manifests of pending runs. A file that a pending run places may hold
its committed content or the pending run's new content, or be missing while the run
has moved it to `versions/`; none of these is reported. The pending run's new files
and versions are not reported as unlisted. Any other content is a mismatch.

A source is `ok` only when all five lists are empty. The text and JSON output list
each of them.

## Catalog

### What it records

The catalog has one row per source, per run, per archived file and per session.

| Table | Key | Main columns |
|---|---|---|
| `sources` | `name` | kind, platform, note, first and last run time |
| `runs` | `run_id` | source, collector host, tool version, start and finish, counts, errors |
| `files` | `source`, `path` | agent, kind (`file`, `sqlite-snapshot`, or `sqlite-log` for a log database: that row describes the database itself, and its exports are in `row_exports`), size, modification time, SHA-256, compressed size, archive path, first run, last written run, run in which it went `gone` |
| `file_versions` | `source`, `path`, `run_id` | SHA-256, size, modification time, archive path (kept versions only), the run that superseded it |
| `row_exports` | `source`, `archive_path` | database path, table, first and last key, row count, whether the database was recreated, run, SHA-256, size |
| `sessions` | `source`, `path`, `session_id` | agent, whether the row comes from a database, workspace, working directory, git branch, models, first and last message time, message count, user and assistant message counts, tool-use count, input, output, cache-read and cache-creation token totals, parent session ID, whether it is a sub-agent (`is_subagent`), file SHA-256 |
| `pending_sessions` | `source`, `path` | the manifest's SHA-256 for the file, and the class name of the exception that stopped its last read |
| `schema_meta` | `key` | schema version (`version`) and reader version (`reader_version`) |

Session files are the paths each layout names as such (see Default Agent Layouts).
For Claude Code they include the sub-agent transcripts of workflows; the
`journal.jsonl` beside them is not a session. Sessions are read from session files by
the agent's cagelens stats parser, which the catalog looks up through
`backends/registry.py` (`extract_stats`); the Claude, Codex and Gemini parsers are in
`storage/metrics.py`. Sessions are read from databases by a query in the layout that
returns each session's id, working directory, branch, first and last time, and message
count. Timestamps are stored as ISO 8601 UTC; epoch seconds and milliseconds are
converted.

A session's workspace comes from its archived path for Claude Code
(`.claude/projects/<workspace>/`) and Gemini CLI (`.gemini/tmp/<project>/`). The
catalog passes it to the backend's workspace resolver. Resolvers that read a working
directory from the file, such as the Codex resolver, prefer that directory. The Gemini
resolver first looks the project folder up in the local machine's Gemini project
index.

The rules for a session's ID, parent and `is_subagent` live in one module,
`agent_history/utils/session_identity.py`. The stats readers, the lineage model and
the export use it, so a session has one ID everywhere.

The Claude Code reader works as follows:

- A sub-agent transcript is a file whose name starts with `agent-`, or one whose lines
  carry an `agentId`. Its agent ID is that `agentId`, or else the file name without
  `agent-`. Its parent is the session named by the folder above `subagents/`, when
  the file's lines name that session or carry no `sessionId`; otherwise its parent is
  the last `sessionId` in the file. Agent IDs are short and repeat across sessions, so
  its session ID is `<parent>:<agent ID>`, or the bare agent ID when it has no parent.
  `parent_session_id` is the bare parent ID. `is_subagent` is true.
- A main transcript's session ID is the ID in its file name when that ID appears in
  its lines, and otherwise its first `sessionId`. It has no parent.

The Codex reader works as follows:

- The first `session_meta` line describes the rollout: its ID, working directory and
  git branch. A later `session_meta` line only supplies a parent that the first did
  not name.
- `is_subagent` is true when that line's `source` has a `subagent` entry in any form,
  such as `{"thread_spawn": ...}`, `{"other": "guardian"}`, `"review"` or
  `"compact"`, or its `thread_source` is `subagent`.
- The parent is the first of `parent_thread_id`, `source.subagent.thread_spawn.parent_thread_id`,
  `forked_from_id`, and the ID of a later `session_meta` line whose ID differs. A
  forked rollout is not a sub-agent, but it names its parent.
- A `.jsonl.zst` rollout is read like a plain one when the `zstandard` package is
  installed. Without it, the cagelens stats cache does not store compressed rollouts,
  and its sync counts them as errors.

Both readers skip lines that are not JSON objects and treat a nested value that is not
an object as empty. Bytes that are not valid UTF-8 become U+FFFD instead of failing the
file.

A session can be known only from a database. For example, Copilot's
`session-store.db` keeps sessions whose JSONL folders Copilot deleted. Such a
session's row has the database's path and is marked as coming from a database.

The view `session_copies` groups `sessions` by agent and session ID. Its columns are
`agent`, `session_id`, `sources` (how many sources hold the session), `copies`,
`max_file_messages` (the largest message count among session-file rows),
`max_database_count` (the largest count among database rows, which can count turns
rather than messages) and `last_timestamp` (the latest message time). The view
`session_longest_copy` picks one copy per session. It prefers session-file rows over
database rows, because a database's count can be of turns rather than messages. Then
it prefers the most messages, then the latest message, and then the first source and
path in byte order. Missing counts and times sort last, and the byte-order comparison
is the same, on both SQLite and PostgreSQL. The same session can
appear in several sources, for example in a live home and in a restored backup,
and a copy can be an earlier, shorter state of the same session.

### Updating

`cagelens archive catalog sync` reads manifests that the catalog has not yet
ingested, oldest first. By default it covers every source found in the archive (each
folder directly in `sources/` that holds a `SOURCE.json`; it lists those folders
without walking their files), not the configuration's sources. `--source` can name any
source in the archive; a name that is not in the archive is an error (exit code 1).
For each source it:

1. decompresses each session file that those runs added or updated, and each file in
   `pending_sessions`, once; checks the content's SHA-256 against the manifest; and
   extracts its session metadata with the agent's stats parser (see What it records),
   replacing that file's earlier session rows;
2. then, for each run, records the run, updates `files` and `file_versions`,
   and marks `gone` paths.

A session file that cannot be read, or whose content does not match the manifest's
SHA-256, is recorded in `pending_sessions`. Every later sync reads it again. A newer
run's hash replaces the pending one, and a successful read removes the entry. Until
then, every sync reports the file as an error.

`schema_meta` records `reader_version`: the metrics parser version
(`METRICS_PARSER_VERSION` in `storage/metrics.py`) plus the catalog's own extraction
revision. When a sync finds a different or missing reader version, it queues every
session file listed in `files` in `pending_sessions` at its current SHA-256 (a file
that is already pending keeps its hash), and records the new version in the same
transaction. The queued files are then read like other pending files, so rows that an
older reader wrote are replaced.

Each session file and each run is one transaction. Runs are recorded last, so a
sync that stops part way leaves its runs unrecorded, and the next sync reads the
same session files again. Because sync follows manifests
rather than walking the archive, a daily update reads only that day's files, even
when the archive is on a network mount.

A `versioned` manifest entry without a `version_path` stops the sync with an error
that names the run and the path. That run's transaction is rolled back, so the run
stays unrecorded.

`cagelens archive catalog rebuild` empties every table and replays every source's
manifests. With `--source X`, it deletes and replays only the rows of source X.

`cagelens archive catalog status` prints counts per source and the newest run per
source. With `--source`, it shows only the named sources. It reads only the catalog.

`catalog sync` and `catalog rebuild` read the configuration file only when
`--destination` is absent, so a machine without an archive configuration can keep a
catalog.

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
PostgreSQL, `TEXT` in SQLite). The store creates its own tables and records the
schema version in `schema_meta`. The schema version is 2. Opening a version 1 catalog
upgrades it in place by adding the `pending_sessions` table; a catalog of any other
version is refused. Opening a catalog also drops and creates every view, on both
stores, so a view's query and columns can change without a new schema version.

## Reading The Archive With cagelens

**Not built yet.** This section describes planned behaviour. There is no `archive:`
home type and no `open_session_text` helper yet.

- **A new home type, `archive:<config source name>` or `archive:<path>`.** It
  resolves each agent's folder inside `sources/<name>/files/`. Every existing
  command (`session list`, `export`, `stats`) then works on archived and saved
  copies as it does on a live machine.
- **Transparent decompression.** A helper, `utils/io.py:open_session_text`, opens
  `x` or `x.zst` and returns text. All backends read through it, and session
  scanners also look for the `.zst` names. The Codex backend's own `.zst` handling
  moves into this helper.

## Changes To Existing Code

**Not built yet.** This section describes planned changes to existing code.

- **Backends stop importing storage and export code.** The Claude and Codex
  backends read cached message counts from `metrics.db` directly. They will take an
  optional lookup function instead. The Pi and Copilot backends import
  `export.markdown`; that code moves to `export/`, which calls the backends rather
  than the reverse.
- **Session metadata extraction becomes a backend function** that takes an open
  text stream and returns a plain record. The catalog and `storage/metrics.py` both
  use it.

## Package Layout And Commands

```
agent_history/archive/
  __init__.py          public API: load_config, collect_source, verify_source, ...
  errors.py            ArchiveError and ArchiveConfigError
  config.py            configuration loading and validation
  layouts.py           per-agent file lists, session patterns, the credential denylist,
                       browser-profile skipping, and archive path mapping
  codec.py             zstd compression, hashing, and open_maybe_compressed, which
                       opens the name it is given as text; no production code calls it
  state.py             collector state, applying manifests to it, the local lock and
                       the lock in the archive
  manifest.py          manifest writing and reading, run IDs, committed_run_ids,
                       read_manifest
  transport.py         the destination interface (including place, missing,
                       discard_tree, create_lock, remove_lock and list_dirs), the
                       local destination, fsync_file, fsync_dir
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
cagelens archive collect [--source NAME]... [--force] [--dry-run] [--state-dir DIR] [--break-lock]
cagelens archive verify  [--source NAME]... [--all | --sample N]
cagelens archive catalog sync | rebuild | status [--source NAME]... [--store sqlite:PATH | postgres:CONNINFO]
```

Every command also takes `--config PATH`, `--destination` (overrides the configured one)
and `--json`. Exit codes: 0 success; 1 the command failed; 2 it finished but found
problems (files that could not be read, or verification differences). The catalog
defaults to `sqlite:~/.cagelens/archive-catalog.db`. `archive` must be the first word
after `cagelens`, because it does not use the session-scope options.

`collect` runs the selected sources in turn. A source whose local lock or lock in the
archive another run holds is reported as skipped, and collection continues. Any other
failure of a source is reported, and the next source runs. An unexpected exception is
reported as `<type>: <message>`. A damaged manifest raises `ManifestError`, and a
damaged `ARCHIVE.json` raises `ArchiveError`; each message names the file. The exit
code is 1 when any source failed, once every source has been tried. Otherwise it is 2
if a run recorded file errors, and 0 if not.

`--break-lock` removes each selected source's lock in the archive before its run, and
prints whose lock it was. It is meant for a lock that a run killed on another machine
left behind.

`--dry-run` lists what a run would write and which files the content-loss guard
would version, without writing. It hashes changed files that are already archived and
compresses nothing. For a log database, it reports the number of new rows it would
export. It takes no lock in the archive, finishes or discards no interrupted run, and
sends no health request.

Packaging: `pip install "cagelens[archive]"`, or `cagelens[archive,postgres]` for a
PostgreSQL catalog. The `archive` extra declares `zstandard`.

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
- **Interrupted runs:** a run stopped during transfer, at the manifest write, while
  placing files, or at the commit is finished or discarded by the next run, and every
  version is kept. After the next run, `verify` reports nothing and no incoming
  folder remains.
- **SSH destination:** unit tests run the SSH destination through a stand-in `ssh`
  that runs each command with the local `sh`.
- **Not built yet:** an archive test in `tests/e2e_docker`, with a destination node
  that has only the tools the SSH destination needs.
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
