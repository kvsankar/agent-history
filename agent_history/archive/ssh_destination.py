"""An archive destination on another host, reached over SSH.

The remote host needs only ``sh`` (with its ``test``/``[``, ``echo`` and ``printf``, and
``set -C``, whose exclusive create takes the lock where ``ln`` cannot), ``cat``,
``mkdir``, ``mv``, ``find``, ``tar``, ``ln`` (whose hard link takes the lock; optional),
``rm`` (which removes only a source's incoming folder and what its lock folder holds),
``rmdir`` (which removes the lock folder) and
``sync`` (which flushes each write to disk before the run goes on). Each
operation sends ssh one already-quoted command string: ssh joins its remote arguments with
spaces, so passing them separately would lose the quoting. The remote login shell runs
that string, and it need not be sh (csh, tcsh and fish parse differently), so the string
is always ``sh -c '<script>'``, which any of them runs as one simple command.
"""

from __future__ import annotations

import secrets
import shlex
import subprocess
import tarfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator
from urllib.parse import urlsplit

from agent_history.archive.errors import ArchiveError
from agent_history.archive.transport import (
    LOCK_OWNER,
    Destination,
    Keep,
    Put,
    _check_discardable,
    _check_lock,
    _check_rel,
)

_MISSING = 3
_EXISTS = 3
_CHUNK = 1 << 20


class SshDestination(Destination):
    def __init__(
        self,
        host: str,
        root: str,
        port: int | None = None,
        ssh: list[str] | None = None,
    ):
        self.host = host
        self.root = root.rstrip("/") or "/"
        self.port = port
        self.ssh = list(ssh or ["ssh"])
        self.description = f"ssh://{host}{self.root}"

    @classmethod
    def from_url(cls, url: str) -> SshDestination:
        parts = urlsplit(url)
        if parts.scheme != "ssh" or not parts.hostname or not parts.path:
            raise ArchiveError(f"Invalid SSH destination: {url}")
        host = parts.hostname
        if parts.username:
            host = f"{parts.username}@{host}"
        return cls(host, parts.path, port=parts.port)

    # -- helpers ----------------------------------------------------------------------

    def _remote(self, rel: str) -> str:
        return shlex.quote(f"{self.root}/{_check_rel(rel)}")

    def _command(self, script: str) -> list[str]:
        args = [*self.ssh, "-o", "BatchMode=yes"]
        if self.port:
            args += ["-p", str(self.port)]
        return [*args, self.host, f"sh -c {shlex.quote(script)}"]

    def _run(self, script: str, data: bytes | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            self._command(script),
            input=data if data is not None else b"",
            capture_output=True,
            check=False,
        )

    def _check(self, result: subprocess.CompletedProcess, what: str) -> None:
        if result.returncode != 0:
            message = result.stderr.decode("utf-8", "replace").strip()
            raise ArchiveError(f"{what} failed on {self.host}: {message}")

    # -- Destination ------------------------------------------------------------------

    def read_bytes(self, rel: str) -> bytes | None:
        path = self._remote(rel)
        result = self._run(f"test -f {path} || exit {_MISSING}; cat {path}")
        if result.returncode == _MISSING:
            return None
        self._check(result, f"Reading {rel}")
        return result.stdout

    def write_bytes(self, rel: str, data: bytes) -> None:
        path = self._remote(rel)
        part = self._remote(rel + ".part")
        parent = shlex.quote(f"{self.root}/{rel}".rsplit("/", 1)[0])
        # The content reaches the disk before the rename, so the name never shows an
        # empty or partial file after a power loss.
        script = f"mkdir -p {parent} && cat > {part} && sync && mv {part} {path} && sync"
        self._check(self._run(script, data), f"Writing {rel}")

    def list_files(self, rel_dir: str) -> list[str]:
        path = self._remote(rel_dir)
        # NUL-separated, because a file name can hold a line break of any kind.
        result = self._run(
            f"test -d {path} || exit 0; cd {path} && find . -type f -exec printf '%s\\0' {{}} +"
        )
        self._check(result, f"Listing {rel_dir}")
        names = [raw.decode("utf-8", "surrogateescape") for raw in result.stdout.split(b"\0")]
        return sorted(name[2:] for name in names if name.startswith("./"))

    def list_dirs(self, rel_dir: str) -> list[str]:
        path = self._remote(rel_dir)
        # POSIX find has no -maxdepth: -prune stops it below each entry of the folder.
        result = self._run(
            f"test -d {path} || exit 0; cd {path} && "
            f"find . ! -name . -prune -type d -exec printf '%s\\0' {{}} +"
        )
        self._check(result, f"Listing {rel_dir}")
        names = [raw.decode("utf-8", "surrogateescape") for raw in result.stdout.split(b"\0")]
        return sorted(name[2:] for name in names if name.startswith("./"))

    def exists(self, rel: str) -> bool:
        return self._run(f"test -e {self._remote(rel)}").returncode == 0

    def move(self, src: str, dst: str) -> bool:
        source, target = self._remote(src), self._remote(dst)
        parent = shlex.quote(f"{self.root}/{_check_rel(dst)}".rsplit("/", 1)[0])
        result = self._run(
            f"test -e {source} || exit {_MISSING}; mkdir -p {parent} && mv {source} {target} && sync"
        )
        if result.returncode == _MISSING:
            return False
        self._check(result, f"Moving {src}")
        return True

    def missing(self, rels: list[str]) -> list[str]:
        if not rels:
            return []
        script = "".join(
            f"[ -e {self._remote(rel)} ] || echo {index}\n" for index, rel in enumerate(rels)
        )
        result = self._run_script(script)
        self._check(result, "Checking archived files")
        return [rels[int(line)] for line in result.stdout.decode("ascii").split()]

    def place(self, keeps: list[Keep], puts: list[Put]) -> None:
        """Run every move as one shell script, read from standard input.

        The script is sent on standard input rather than as the command, because a first
        run can move thousands of files, more than a command line can hold. Each target
        folder is created once, before the moves.
        """
        if not keeps and not puts:
            return
        targets = [version for _, version, _ in keeps] + [current for _, current in puts]
        lines = [
            f"mkdir -p {parent} || exit 1\n" for parent in sorted(set(map(self._parent, targets)))
        ]
        for current, version, incoming in keeps:
            cur, ver, inc = self._remote(current), self._remote(version), self._remote(incoming)
            lines.append(
                f"if [ ! -e {ver} ] && [ -e {inc} ]; then "
                f"[ -e {cur} ] || {{ echo {shlex.quote(current)} is missing >&2; exit 1; }}; "
                f"mv {cur} {ver} || exit 1; fi\n"
            )
        for incoming, current in puts:
            inc, cur = self._remote(incoming), self._remote(current)
            lines.append(f"if [ -e {inc} ]; then mv {inc} {cur} || exit 1; fi\n")
        lines.append("sync\n")
        self._check(self._run_script("".join(lines)), "Moving files into place")

    def discard_tree(self, rel: str) -> None:
        path = self._remote(_check_discardable(rel))
        self._check(self._run(f"rm -rf {path}"), f"Removing {rel}")

    def create_lock(self, rel: str, owner: bytes) -> bool:
        """Create the owner file with its whole content in one step, then read it back.

        The owner is written to a temporary file of this call's own, flushed, and linked
        to the owner file's name with ``ln``. Creating a hard link is atomic and fails
        when the name exists, so the remote ``mkdir`` need not report a folder that
        exists (uutils mkdir does not, under a race), and the owner file never exists
        empty or partial: a write that fails (a full disk or quota) or a run killed
        during it leaves at most the temporary file, which is no lock.

        Where ``ln`` fails although the name is free (a filesystem without hard links,
        or no ``ln``), the owner file is created with the shell's exclusive create
        (``set -C``) and written through the same descriptor, and removed if that write
        fails. The owner travels in the script, not on standard input, so a dropped
        connection cannot cut it short.
        """
        lock = _check_lock(rel)
        script = _create_lock_script(
            folder=self._remote(lock),
            owner=self._remote(f"{lock}/{LOCK_OWNER}"),
            tmp=self._remote(f"{lock}/{LOCK_OWNER}.{secrets.token_hex(8)}.tmp"),
            content=shlex.quote(owner.decode("utf-8")),
        )
        result = self._run(script)
        if result.returncode == _EXISTS:
            return False
        self._check(result, f"Creating the lock {rel}")
        return result.stdout == owner  # it holds another run's owner only if broken at once

    def remove_lock(self, rel: str) -> None:
        path = self._remote(_check_lock(rel))
        # Everything but the owner file first, then the owner file, which is the lock.
        script = (
            f"[ -d {path} ] || exit 0; cd {path} || exit 1; "
            "for f in * .[!.]* ..?*; do "
            f'[ "$f" = {LOCK_OWNER} ] && continue; '
            '{ [ -e "$f" ] || [ -L "$f" ]; } || continue; '
            'rm -rf -- "$f" || exit 1; '
            "done; "
            f"rm -rf -- {LOCK_OWNER} || exit 1; "
            f"cd / && {{ rmdir {path} 2>/dev/null || :; }}; sync"
        )
        self._check(self._run(script), f"Removing the lock {rel}")

    def _parent(self, rel: str) -> str:
        return shlex.quote(f"{self.root}/{_check_rel(rel)}".rsplit("/", 1)[0])

    def _run_script(self, script: str) -> subprocess.CompletedProcess:
        return self._run("sh -s", script.encode("utf-8", "surrogateescape"))

    def put_tree(self, staging: Path) -> None:
        """Stream the staging folder into ``tar -xf -`` on the remote host.

        A dropped connection can leave the last file partial, so the collector sends only
        to its run's incoming folder and moves files into place after the transfer.
        """
        root = shlex.quote(self.root)
        process = subprocess.Popen(
            self._command(f"mkdir -p {root} && tar -xf - -C {root} && sync"),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stderr: list[bytes] = []
        reader = threading.Thread(target=lambda: stderr.append(process.stderr.read()))  # type: ignore[union-attr]
        reader.start()
        try:
            with tarfile.open(fileobj=process.stdin, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                for path in sorted(Path(staging).rglob("*")):
                    if path.is_file():
                        tar.add(path, arcname=path.relative_to(staging).as_posix(), recursive=False)
        finally:
            process.stdin.close()  # type: ignore[union-attr]
            process.wait()
            reader.join()
        if process.returncode != 0:
            message = b"".join(stderr).decode("utf-8", "replace").strip()
            raise ArchiveError(f"Copying files to {self.host} failed: {message}")

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        """Stream a file from ``cat`` on the remote host, without holding it in memory.

        A failure on the remote host or of the connection raises ArchiveError, also when
        the reader stopped early because the stream was cut short.
        """
        process = subprocess.Popen(
            self._command(f"cat {self._remote(rel)}"),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout: IO[bytes] = process.stdout  # type: ignore[assignment]
        stderr: list[bytes] = []
        reader = threading.Thread(target=lambda: stderr.append(process.stderr.read()))  # type: ignore[union-attr]
        reader.start()
        try:
            yield stdout
            if not stdout.closed:  # a decompressor may close it when its frame ends
                while stdout.read(_CHUNK):  # read what the caller left, so cat can finish
                    pass
        except BaseException as exc:
            status = _finished(process)
            if status is None:
                process.kill()
            _close(process, stdout, reader)
            if status not in (None, 0):
                raise self._read_error(rel, stderr) from exc
            raise
        _close(process, stdout, reader)
        if process.returncode != 0:
            raise self._read_error(rel, stderr)

    def _read_error(self, rel: str, stderr: list[bytes]) -> ArchiveError:
        message = b"".join(stderr).decode("utf-8", "replace").strip()
        return ArchiveError(f"Reading {rel} failed on {self.host}: {message}")


def _create_lock_script(folder: str, owner: str, tmp: str, content: str) -> str:
    """The remote script of create_lock; every argument is already quoted.

    A run that releases the lock can remove the folder, and the temporary file with it,
    at any moment, so a failed step is tried again, up to 5 times, unless the owner file
    exists. Exit status _EXISTS means another run holds the lock.
    """
    exclusive_create = (
        f"(set -C; exec 3> {owner} || exit 1; "
        f"printf '%s' {content} >&3 || {{ rm -f {owner}; exit 1; }})"
    )
    return (
        "n=0; while :; do "
        f"mkdir -p {folder} || exit 1; "
        f"[ -e {owner} ] && exit {_EXISTS}; "
        f"if err=$( {{ printf '%s' {content} > {tmp} && sync; }} 2>&1 ); then "
        f"if ln {tmp} {owner} 2>/dev/null; then rm -f {tmp}; break; fi; "
        f"if [ ! -e {owner} ] && [ -e {tmp} ]; then "  # ln failed, not the race
        f"rm -f {tmp}; "
        f"if err=$( {exclusive_create} 2>&1 ); then break; fi; "
        "fi; "
        "fi; "
        f"rm -f {tmp}; "
        f"[ -e {owner} ] && exit {_EXISTS}; "
        'n=$((n + 1)); [ "$n" -lt 5 ] || '
        '{ echo "${err:-could not write the owner file}" >&2; exit 1; }; '
        "done; "
        f"sync; cat {owner}"
    )


def _close(process: subprocess.Popen, stdout: IO[bytes], reader: threading.Thread) -> None:
    stdout.close()
    process.wait()
    reader.join()


def _finished(process: subprocess.Popen, timeout: float = 0.5) -> int | None:
    """The exit status, waiting briefly for a process whose output has just ended."""
    try:
        return process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        return None
