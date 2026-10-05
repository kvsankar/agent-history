"""Tests for the SSH destination, using a stand-in ssh that runs commands locally."""

from __future__ import annotations

import json
import os
import shutil
import stat
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest
import zstandard

from agent_history.archive.collect import collect_source
from agent_history.archive.config import parse_config
from agent_history.archive.errors import ArchiveError
from agent_history.archive.ssh_destination import SshDestination
from agent_history.archive.transport import open_destination
from agent_history.archive.verify import verify_source

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or shutil.which("sh") is None, reason="needs a POSIX sh"
)

# Like ssh: skip options and the host, then run the remaining words joined by spaces.
FAKE_SSH = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-p) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
shift
exec sh -c "$*"
"""

T0 = datetime(2026, 10, 2, 6, 15, tzinfo=timezone.utc)
SESSION = ".claude/projects/-home-alex-shop/a1.jsonl"


@pytest.fixture
def fake_ssh(tmp_path):
    path = tmp_path / "bin" / "ssh"
    path.parent.mkdir()
    path.write_text(FAKE_SSH, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


@pytest.fixture
def remote(tmp_path, fake_ssh):
    root = tmp_path / "remote archive"  # a space, to exercise quoting
    return SshDestination("nas", str(root), ssh=[fake_ssh]), root


def test_parses_ssh_urls():
    dest = SshDestination.from_url("ssh://alex@nas:2222/volume1/agent-archive")

    assert dest.host == "alex@nas"
    assert dest.port == 2222
    assert dest.root == "/volume1/agent-archive"


def test_open_destination_selects_ssh():
    dest = open_destination("ssh://nas/srv/archive")

    assert isinstance(dest, SshDestination)
    assert dest.root == "/srv/archive"


def test_basic_operations(remote):
    dest, root = remote

    assert dest.read_bytes("a/b.txt") is None
    dest.write_bytes("a/b.txt", b"hello")
    assert (root / "a" / "b.txt").read_bytes() == b"hello"
    assert dest.read_bytes("a/b.txt") == b"hello"
    assert dest.exists("a/b.txt")
    assert dest.list_files("a") == ["b.txt"]
    assert dest.list_files("missing") == []
    assert dest.move("a/b.txt", "c/d e.txt")
    assert not dest.move("a/b.txt", "x.txt")
    assert dest.read_bytes("c/d e.txt") == b"hello"
    with dest.open_binary("c/d e.txt") as handle:
        assert handle.read() == b"hello"


def test_lock_folder_is_created_once(remote):
    dest, root = remote

    assert dest.create_lock("sources/src/LOCK", b'{"host": "a"}')
    assert not dest.create_lock("sources/src/LOCK", b'{"host": "b"}')
    assert dest.read_bytes("sources/src/LOCK/owner.json") == b'{"host": "a"}'
    dest.remove_lock("sources/src/LOCK")
    dest.remove_lock("sources/src/LOCK")  # already gone
    assert not (root / "sources" / "src" / "LOCK").exists()
    assert (root / "sources" / "src").is_dir()
    with pytest.raises(ArchiveError):
        dest.remove_lock("sources/src/files")


# Like uutils coreutils mkdir 0.8.0 when another process creates the same folder at the
# same time: it reports success although the folder was not its own.
LAX_MKDIR = """#!/bin/sh
{real} -p "$@" 2>/dev/null
exit 0
"""


@pytest.fixture
def lax_remote(tmp_path):
    """A remote host whose ``mkdir`` succeeds even when the folder exists already."""
    tools = tmp_path / "lax-bin"
    tools.mkdir()
    mkdir = tools / "mkdir"
    mkdir.write_text(LAX_MKDIR.format(real=shutil.which("mkdir")), encoding="utf-8")
    mkdir.chmod(mkdir.stat().st_mode | stat.S_IEXEC)
    ssh = tmp_path / "lax-ssh"
    ssh.write_text(
        FAKE_SSH.replace('exec sh -c "$*"', f'PATH={tools}:$PATH exec sh -c "$*"'),
        encoding="utf-8",
    )
    ssh.chmod(ssh.stat().st_mode | stat.S_IEXEC)
    root = tmp_path / "remote archive"
    return SshDestination("nas", str(root), ssh=[str(ssh)]), root


def test_lock_does_not_rely_on_mkdir_reporting_an_existing_folder(lax_remote):
    dest, _root = lax_remote

    assert dest.create_lock("sources/src/LOCK", b'{"token": "a"}')
    assert not dest.create_lock("sources/src/LOCK", b'{"token": "b"}')
    assert dest.read_bytes("sources/src/LOCK/owner.json") == b'{"token": "a"}'


def _contend(dest, rel, contenders):
    """``contenders`` runs call create_lock at once; returns (winners, recorded token)."""
    barrier = threading.Barrier(contenders)
    results: dict[int, bool] = {}

    def contend(number):
        barrier.wait()
        results[number] = dest.create_lock(rel, json.dumps({"token": str(number)}).encode())

    threads = [threading.Thread(target=contend, args=(n,)) for n in range(contenders)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    owner = json.loads(dest.read_bytes(f"{rel}/owner.json"))
    return [n for n, got in sorted(results.items()) if got], owner["token"]


def test_only_one_of_many_concurrent_runs_gets_the_lock_over_ssh(lax_remote):
    dest, _root = lax_remote

    for _ in range(5):
        winners, token = _contend(dest, "sources/src/LOCK", 6)
        assert len(winners) == 1
        assert token == str(winners[0])
        dest.remove_lock("sources/src/LOCK")


def test_only_one_of_many_concurrent_runs_gets_the_lock_in_a_local_archive(tmp_path):
    dest = open_destination(str(tmp_path / "archive"))

    for _ in range(5):
        winners, token = _contend(dest, "sources/src/LOCK", 6)
        assert len(winners) == 1
        assert token == str(winners[0])
        dest.remove_lock("sources/src/LOCK")


def test_a_lock_folder_without_an_owner_file_is_taken_and_emptied_over_ssh(remote):
    dest, root = remote
    lock = root / "sources" / "src" / "LOCK"
    (lock / "a folder").mkdir(parents=True)
    (lock / "a folder" / "file").write_bytes(b"x")
    for name in ("._owner.json", "owner.json.part", "..odd", "-dash"):
        (lock / name).write_bytes(b"x")

    assert dest.create_lock("sources/src/LOCK", b'{"token": "a"}')
    dest.remove_lock("sources/src/LOCK")

    assert not lock.exists()


def test_a_lock_taken_over_ssh_keeps_out_a_run_on_a_mounted_share(remote):
    """An archive reached over SSH by one machine and mounted by another has one lock."""
    dest, root = remote
    mounted = open_destination(str(root))

    assert dest.create_lock("sources/src/LOCK", b'{"token": "ssh"}')
    assert not mounted.create_lock("sources/src/LOCK", b'{"token": "mount"}')
    dest.remove_lock("sources/src/LOCK")
    assert mounted.create_lock("sources/src/LOCK", b'{"token": "mount"}')
    assert not dest.create_lock("sources/src/LOCK", b'{"token": "ssh"}')
    assert dest.read_bytes("sources/src/LOCK/owner.json") == b'{"token": "mount"}'


# Like ln on a filesystem without hard links, such as exFAT.
NO_LINKS = """#!/bin/sh
echo "ln: failed to create hard link: Operation not permitted" >&2
exit 1
"""


def _remote_with(tmp_path, name, tools=None, prelude=""):
    """A remote host whose PATH starts with ``tools`` and whose scripts run after ``prelude``."""
    folder = tmp_path / f"{name}-bin"
    folder.mkdir()
    for tool, script in (tools or {}).items():
        (folder / tool).write_text(script, encoding="utf-8")
        (folder / tool).chmod(0o755)
    ssh = tmp_path / f"{name}-ssh"
    ssh.write_text(
        FAKE_SSH.replace('exec sh -c "$*"', f'{prelude}PATH={folder}:$PATH exec sh -c "$*"'),
        encoding="utf-8",
    )
    ssh.chmod(0o755)
    return SshDestination("nas", str(tmp_path / "remote archive"), ssh=[str(ssh)])


@pytest.mark.parametrize("tools", [{}, {"ln": NO_LINKS}], ids=["hard-links", "no-hard-links"])
def test_a_failed_owner_write_leaves_no_lock_over_ssh(tmp_path, tools):
    """A full disk or quota lets the create succeed and the write fail; no lock remains."""
    full = _remote_with(tmp_path, "full", tools, prelude="ulimit -f 0; ")
    roomy = _remote_with(tmp_path, "roomy", tools)
    lock = tmp_path / "remote archive" / "sources" / "src" / "LOCK"

    with pytest.raises(ArchiveError):
        full.create_lock("sources/src/LOCK", b'{"token": "a"}')

    assert not (lock / "owner.json").exists()
    assert roomy.create_lock("sources/src/LOCK", b'{"token": "b"}')
    assert roomy.read_bytes("sources/src/LOCK/owner.json") == b'{"token": "b"}'
    roomy.remove_lock("sources/src/LOCK")
    assert not lock.exists()


def test_only_one_run_gets_the_lock_where_the_remote_has_no_hard_links(tmp_path):
    lax_mkdir = LAX_MKDIR.format(real=shutil.which("mkdir"))
    dest = _remote_with(tmp_path, "nolinks", {"ln": NO_LINKS, "mkdir": lax_mkdir})

    for _ in range(3):
        winners, token = _contend(dest, "sources/src/LOCK", 6)
        assert len(winners) == 1
        assert token == str(winners[0])
        dest.remove_lock("sources/src/LOCK")


def test_overlapping_run_over_ssh_is_kept_out_by_the_destination_lock(
    remote, tmp_path, monkeypatch
):
    from agent_history.archive import collect as collect_module
    from agent_history.archive.state import CollectLockedError

    dest, root = remote
    home = tmp_path / "home"
    (home / SESSION).parent.mkdir(parents=True)
    (home / SESSION).write_bytes(b"a\n")
    os.utime(home / SESSION, (1_790_000_000, 1_790_000_000))
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    real = collect_module._Run._check_transfer
    refused = []

    def check_then_overlap(self):
        real(self)
        if not refused:
            with pytest.raises(CollectLockedError):
                collect_source(
                    config, "src", state_dir=tmp_path / "other-state", now=T0, destination=dest
                )
            refused.append(True)

    monkeypatch.setattr(collect_module._Run, "_check_transfer", check_then_overlap)

    summary = collect_source(config, "src", state_dir=tmp_path / "state", now=T0, destination=dest)

    assert refused
    assert summary.written == 1
    assert verify_source(dest, "src").ok
    assert not (root / "sources" / "src" / "LOCK").exists()


def test_list_files_keeps_names_with_line_breaks(remote):
    dest, root = remote
    names = ["plain.jsonl", "new\nline.jsonl", "sep\u2028arator.jsonl", "cr\rhere.jsonl"]
    for name in names:
        (root / "d" / "sub").mkdir(parents=True, exist_ok=True)
        (root / "d" / "sub" / name).write_bytes(b"x")

    assert dest.list_files("d") == sorted(f"sub/{name}" for name in names)


def test_list_dirs_lists_only_the_folders_directly_inside(remote):
    from agent_history.archive.catalog.sync import list_sources

    dest, root = remote
    for name in ("alpha", "new\nline", "beta"):
        (root / "sources" / name / "files" / "deep").mkdir(parents=True)
        (root / "sources" / name / "files" / "deep" / "x.zst").write_bytes(b"x")
    for name in ("alpha", "new\nline"):
        (root / "sources" / name / "SOURCE.json").write_text("{}", encoding="utf-8")
    (root / "sources" / "stray.txt").write_text("not a source", encoding="utf-8")

    assert dest.list_dirs("sources") == ["alpha", "beta", "new\nline"]
    assert dest.list_dirs("missing") == []
    assert list_sources(dest) == ["alpha", "new\nline"]


def test_put_tree_keeps_times(remote, tmp_path):
    dest, root = remote
    staging = tmp_path / "staging"
    (staging / "sources" / "s").mkdir(parents=True)
    staged = staging / "sources" / "s" / "f.zst"
    staged.write_bytes(b"data")
    os.utime(staged, (1_790_000_000, 1_790_000_000))

    dest.put_tree(staging)

    copied = root / "sources" / "s" / "f.zst"
    assert copied.read_bytes() == b"data"
    assert int(copied.stat().st_mtime) == 1_790_000_000


def test_collect_and_verify_over_ssh(remote, tmp_path):
    dest, root = remote
    home = tmp_path / "home"
    session = home / SESSION
    session.parent.mkdir(parents=True)
    session.write_bytes(b"original\n")
    os.utime(session, (1_790_000_000, 1_790_000_000))
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    state = tmp_path / "state"

    collect_source(config, "src", state_dir=state, now=T0, destination=dest)
    session.write_bytes(b"new\n")
    os.utime(session, (1_790_000_100, 1_790_000_100))
    second = collect_source(
        config, "src", state_dir=state, now=T0 + timedelta(hours=1), destination=dest
    )

    assert second.versioned == 1
    archived = root / "sources" / "src" / "files" / f"{SESSION}.zst"
    assert zstandard.ZstdDecompressor().decompress(archived.read_bytes()) == b"new\n"
    assert verify_source(dest, "src").ok
    for state_file in state.rglob("*.json"):
        state_file.unlink()
    third = collect_source(
        config, "src", state_dir=state, now=T0 + timedelta(hours=2), destination=dest
    )
    assert third.written == 0


# Like FAKE_SSH, but the connection drops part way through any tar stream.
FAKE_SSH_DROPPING = FAKE_SSH.replace(
    'exec sh -c "$*"',
    'case "$*" in\n  *"tar -x"*) head -c 20000 | sh -c "$*" ;;\n  *) exec sh -c "$*" ;;\nesac',
)


def test_dropped_connection_leaves_the_committed_copy(remote, tmp_path):
    """tar must never rewrite an archived file in place: a cut stream would truncate it."""
    dest, root = remote
    dropping = tmp_path / "bin" / "ssh-dropping"
    dropping.write_text(FAKE_SSH_DROPPING, encoding="utf-8")
    dropping.chmod(dropping.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    session = home / SESSION
    session.parent.mkdir(parents=True)
    first = os.urandom(100_000)  # incompressible, so the stream is long
    session.write_bytes(first)
    os.utime(session, (1_790_000_000, 1_790_000_000))
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    state = tmp_path / "state"
    collect_source(config, "src", state_dir=state, now=T0, destination=dest)
    with session.open("ab") as handle:
        handle.write(os.urandom(100_000))
    os.utime(session, (1_790_000_100, 1_790_000_100))
    cut = SshDestination("nas", dest.root, ssh=[str(dropping)])

    with pytest.raises((ArchiveError, OSError)):
        collect_source(config, "src", state_dir=state, now=T0 + timedelta(hours=1), destination=cut)

    archived = root / "sources" / "src" / "files" / f"{SESSION}.zst"
    assert zstandard.ZstdDecompressor().decompress(archived.read_bytes()) == first
    report = verify_source(dest, "src")
    assert (report.missing, report.mismatched, report.unlisted) == ([], [], [])
    third = collect_source(
        config, "src", state_dir=state, now=T0 + timedelta(hours=2), destination=dest
    )
    assert third.written == 1
    assert zstandard.ZstdDecompressor().decompress(archived.read_bytes()) == session.read_bytes()
    report = verify_source(dest, "src")
    assert (report.missing, report.mismatched, report.unlisted) == ([], [], [])


def test_interrupted_rewrite_over_ssh_keeps_versions_consistent(remote, tmp_path):
    dest, root = remote
    home = tmp_path / "home"
    session = home / SESSION
    session.parent.mkdir(parents=True)
    session.write_bytes(b"original\n")
    os.utime(session, (1_790_000_000, 1_790_000_000))
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    state = tmp_path / "state"
    collect_source(config, "src", state_dir=state, now=T0, destination=dest)
    session.write_bytes(b"rewritten\n")
    os.utime(session, (1_790_000_100, 1_790_000_100))

    class FailingCommit(SshDestination):
        def move(self, src, dst):
            if "/manifests/" in dst:
                raise ArchiveError("connection dropped")
            return super().move(src, dst)

    failing = FailingCommit("nas", dest.root, ssh=dest.ssh)
    with pytest.raises(ArchiveError):
        collect_source(
            config, "src", state_dir=state, now=T0 + timedelta(hours=1), destination=failing
        )
    collect_source(config, "src", state_dir=state, now=T0 + timedelta(hours=2), destination=dest)

    report = verify_source(dest, "src")
    assert (report.missing, report.mismatched, report.unlisted) == ([], [], [])
    (version,) = (root / "sources" / "src" / "versions").rglob("*.zst")
    assert zstandard.ZstdDecompressor().decompress(version.read_bytes()) == b"original\n"
    assert not (root / "sources" / "src" / "incoming").exists()


# Like FAKE_SSH, but the remote login shell is not sh (csh, tcsh or fish, say): it runs only
# one simple command with single-quoted arguments, here `sh -c '<script>'`.
FAKE_SSH_OTHER_LOGIN_SHELL = FAKE_SSH.replace(
    'exec sh -c "$*"',
    'case "$*" in\n'
    '  "sh -c \'"*) eval "set -- $*" ;;\n'
    '  *) echo "login shell cannot parse: $*" >&2; exit 127 ;;\n'
    "esac\n"
    '[ $# -eq 3 ] || { echo "not one script: $*" >&2; exit 127; }\n'
    'exec sh -c "$3"',
)


def test_commands_do_not_depend_on_the_remote_login_shell(tmp_path):
    ssh = tmp_path / "bin" / "ssh"
    ssh.parent.mkdir()
    ssh.write_text(FAKE_SSH_OTHER_LOGIN_SHELL, encoding="utf-8")
    ssh.chmod(ssh.stat().st_mode | stat.S_IEXEC)
    root = tmp_path / "remote archive"
    dest = SshDestination("nas", str(root), ssh=[str(ssh)])
    home = tmp_path / "home"
    (home / SESSION).parent.mkdir(parents=True)
    (home / SESSION).write_bytes(b"a\n")
    os.utime(home / SESSION, (1_790_000_000, 1_790_000_000))
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    state = tmp_path / "state"

    collect_source(config, "src", state_dir=state, now=T0, destination=dest)
    (home / SESSION).write_bytes(b"rewritten\n")
    os.utime(home / SESSION, (1_790_000_100, 1_790_000_100))
    second = collect_source(
        config, "src", state_dir=state, now=T0 + timedelta(hours=1), destination=dest
    )

    assert second.versioned == 1
    assert verify_source(dest, "src").ok
    assert not dest.exists("sources/src/LOCK")


def test_unsafe_paths_are_refused(remote):
    from agent_history.archive.errors import ArchiveError

    dest, _root = remote
    with pytest.raises(ArchiveError):
        dest.write_bytes("../escape", b"x")


# Every remote command is `sh -c '<script>'`; this sets $3 to the script.
UNWRAP = 'eval "set -- $*"\n'

# Like FAKE_SSH, but each script (and a script read from standard input) is logged.
FAKE_SSH_LOGGING = FAKE_SSH.replace(
    'exec sh -c "$*"',
    UNWRAP + 'printf "%s\\n" "--- $3" >> "$SSH_LOG"\n'
    'case "$3" in\n  "sh -s") tee -a "$SSH_LOG" | sh -s ;;\n  *) exec sh -c "$3" ;;\nesac',
)


def test_remote_writes_are_flushed_before_the_commit(remote, tmp_path, monkeypatch):
    dest, _root = remote
    logging_ssh = tmp_path / "bin" / "ssh-logging"
    logging_ssh.write_text(FAKE_SSH_LOGGING, encoding="utf-8")
    logging_ssh.chmod(logging_ssh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("SSH_LOG", str(log))
    home = tmp_path / "home"
    (home / SESSION).parent.mkdir(parents=True)
    (home / SESSION).write_bytes(b"a\n")
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    logged = SshDestination("nas", dest.root, ssh=[str(logging_ssh)])

    collect_source(config, "src", state_dir=tmp_path / "state", now=T0, destination=logged)

    commands = log.read_text(encoding="utf-8").split("--- ")[1:]
    tar = next(command for command in commands if "tar -xf" in command)
    placing = next(c for c in commands if c.startswith("sh -s") and " mv " in c)
    commit = next(command for command in commands if "/manifests/" in command)
    writes = [command for command in commands if "cat >" in command]
    for command in [tar, placing, commit, *writes]:
        assert command.rstrip().endswith("sync"), command


def test_remote_write_is_flushed_before_the_rename(remote, tmp_path, monkeypatch):
    """A rename that reaches the disk before the content can expose an empty file."""
    dest, _root = remote
    logging_ssh = tmp_path / "bin" / "ssh-logging"
    logging_ssh.write_text(FAKE_SSH_LOGGING, encoding="utf-8")
    logging_ssh.chmod(logging_ssh.stat().st_mode | stat.S_IEXEC)
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("SSH_LOG", str(log))
    logged = SshDestination("nas", dest.root, ssh=[str(logging_ssh)])

    logged.write_bytes("a/b.txt", b"hello")

    (command,) = [c for c in log.read_text(encoding="utf-8").split("--- ")[1:] if "cat >" in c]
    _mkdir, rest = command.split("cat >", 1)
    assert "&& sync && mv " in rest, command
    assert rest.rstrip().endswith("sync"), command
    assert logged.read_bytes("a/b.txt") == b"hello"


# Like FAKE_SSH, but after a cat the connection stays open until $SSH_RELEASE exists.
FAKE_SSH_LINGERING = FAKE_SSH.replace(
    'exec sh -c "$*"',
    UNWRAP + 'sh -c "$3"; status=$?\n'
    'case "$3" in\n'
    '  cat*) while [ ! -e "$SSH_RELEASE" ]; do sleep 0.05; done ;;\n'
    "esac\n"
    "exit $status",
)


def test_open_binary_streams_instead_of_reading_the_whole_file(remote, tmp_path, monkeypatch):
    import threading
    import time

    dest, _root = remote
    dest.write_bytes("big.bin", b"x" * 100_000)
    lingering = tmp_path / "bin" / "ssh-lingering"
    lingering.write_text(FAKE_SSH_LINGERING, encoding="utf-8")
    lingering.chmod(lingering.stat().st_mode | stat.S_IEXEC)
    release = tmp_path / "release"
    monkeypatch.setenv("SSH_RELEASE", str(release))
    timer = threading.Timer(3, release.touch)  # in case the read waits for the end
    timer.start()
    streaming = SshDestination("nas", dest.root, ssh=[str(lingering)])
    try:
        started = time.monotonic()
        with streaming.open_binary("big.bin") as handle:
            first = handle.read(10)
            waited = time.monotonic() - started
            release.touch()
            rest = handle.read()
    finally:
        timer.cancel()

    assert waited < 2, "open_binary waited for the whole transfer before returning data"
    assert first + rest == b"x" * 100_000


def test_open_binary_reports_a_failed_read(remote):
    dest, _root = remote

    with pytest.raises(ArchiveError, match=r"missing\.bin"):
        with dest.open_binary("missing.bin") as handle:
            handle.read()


@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root reads anything")
def test_verify_reports_transport_errors_apart_from_mismatches(remote, tmp_path):
    dest, root = remote
    home = tmp_path / "home"
    (home / SESSION).parent.mkdir(parents=True)
    (home / SESSION).write_bytes(b"a\n")
    config = parse_config(
        {
            "archive": {"destination": "ssh://nas/unused", "compression_level": 3},
            "sources": [{"name": "src", "kind": "live", "platform": "linux", "home": str(home)}],
        }
    )
    collect_source(config, "src", state_dir=tmp_path / "state", now=T0, destination=dest)
    archived = root / "sources" / "src" / "files" / f"{SESSION}.zst"
    archived.chmod(0)  # unreadable: the read fails on the remote host

    try:
        report = verify_source(dest, "src")
    finally:
        archived.chmod(0o644)

    assert report.mismatched == []
    assert len(report.errors) == 1
    assert report.errors[0].startswith(f"{SESSION}: ")
    assert not report.ok
