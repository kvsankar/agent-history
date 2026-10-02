"""An archive destination on another host, reached over SSH.

The remote host needs only ``sh``, ``cat``, ``mkdir``, ``mv``, ``find`` and ``tar``. Each
operation sends ssh one already-quoted command string: ssh joins its remote arguments with
spaces, so passing them separately would lose the quoting.
"""

from __future__ import annotations

import io
import shlex
import subprocess
import tarfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator
from urllib.parse import urlsplit

from agent_history.archive.errors import ArchiveError
from agent_history.archive.transport import Destination, _check_rel

_MISSING = 3


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
        return [*args, self.host, script]

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
        script = f"mkdir -p {parent} && cat > {part} && mv {part} {path}"
        self._check(self._run(script, data), f"Writing {rel}")

    def list_files(self, rel_dir: str) -> list[str]:
        path = self._remote(rel_dir)
        result = self._run(f"test -d {path} || exit 0; cd {path} && find . -type f")
        self._check(result, f"Listing {rel_dir}")
        names = result.stdout.decode("utf-8", "surrogateescape").splitlines()
        return sorted(name[2:] for name in names if name.startswith("./"))

    def exists(self, rel: str) -> bool:
        return self._run(f"test -e {self._remote(rel)}").returncode == 0

    def move(self, src: str, dst: str) -> bool:
        source, target = self._remote(src), self._remote(dst)
        parent = shlex.quote(f"{self.root}/{_check_rel(dst)}".rsplit("/", 1)[0])
        result = self._run(
            f"test -e {source} || exit {_MISSING}; mkdir -p {parent} && mv {source} {target}"
        )
        if result.returncode == _MISSING:
            return False
        self._check(result, f"Moving {src}")
        return True

    def put_tree(self, staging: Path) -> None:
        root = shlex.quote(self.root)
        process = subprocess.Popen(
            self._command(f"mkdir -p {root} && tar -xf - -C {root}"),
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
        result = self._run(f"cat {self._remote(rel)}")
        self._check(result, f"Reading {rel}")
        yield io.BytesIO(result.stdout)
