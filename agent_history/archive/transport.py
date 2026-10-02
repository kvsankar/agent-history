"""Archive destinations: a local folder (which may be a network mount) or SSH."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator

from agent_history.archive.errors import ArchiveError


def _check_rel(rel: str) -> str:
    parts = rel.split("/")
    if rel.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ArchiveError(f"Unsafe archive path: {rel!r}")
    return rel


class Destination:
    """Operations the collector, verifier and catalog need from an archive root."""

    description: str

    def read_bytes(self, rel: str) -> bytes | None:
        raise NotImplementedError

    def write_bytes(self, rel: str, data: bytes) -> None:
        raise NotImplementedError

    def list_files(self, rel_dir: str) -> list[str]:
        """Paths of all files under ``rel_dir``, relative to it, "/"-separated."""
        raise NotImplementedError

    def exists(self, rel: str) -> bool:
        raise NotImplementedError

    def move(self, src: str, dst: str) -> bool:
        """Rename within the archive; False when ``src`` does not exist."""
        raise NotImplementedError

    def put_tree(self, staging: Path) -> None:
        """Copy every file under ``staging`` to the same relative path, keeping times."""
        raise NotImplementedError

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        raise NotImplementedError
        yield  # pragma: no cover


class LocalDestination(Destination):
    def __init__(self, root: Path):
        self.root = Path(root)
        self.description = str(self.root)

    def _path(self, rel: str) -> Path:
        return self.root / _check_rel(rel)

    def read_bytes(self, rel: str) -> bytes | None:
        try:
            return self._path(rel).read_bytes()
        except FileNotFoundError:
            return None

    def write_bytes(self, rel: str, data: bytes) -> None:
        path = self._path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    def list_files(self, rel_dir: str) -> list[str]:
        base = self._path(rel_dir)
        if not base.is_dir():
            return []
        found = []
        for dirpath, _dirnames, filenames in os.walk(base):
            for filename in filenames:
                found.append((Path(dirpath) / filename).relative_to(base).as_posix())
        return sorted(found)

    def exists(self, rel: str) -> bool:
        return self._path(rel).exists()

    def move(self, src: str, dst: str) -> bool:
        source = self._path(src)
        if not source.exists():
            return False
        target = self._path(dst)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(source, target)
        return True

    def put_tree(self, staging: Path) -> None:
        for dirpath, _dirnames, filenames in os.walk(staging):
            for filename in sorted(filenames):
                src = Path(dirpath) / filename
                rel = src.relative_to(staging).as_posix()
                target = self._path(rel)
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(target.name + ".part")
                shutil.copy2(src, tmp)
                os.replace(tmp, target)

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        with self._path(rel).open("rb") as handle:
            yield handle


def open_destination(destination: str) -> Destination:
    """Open a destination given as a local path or ``ssh://host/path``."""
    if destination.startswith("ssh://"):
        from agent_history.archive.ssh_destination import SshDestination

        return SshDestination.from_url(destination)
    return LocalDestination(Path(destination).expanduser())
