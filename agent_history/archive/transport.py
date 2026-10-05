"""Archive destinations: a local folder (which may be a network mount) or SSH."""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import IO, Iterator, Tuple

from agent_history.archive.errors import ArchiveError


def _check_rel(rel: str) -> str:
    parts = rel.split("/")
    if rel.startswith("/") or any(part in ("", ".", "..") for part in parts):
        raise ArchiveError(f"Unsafe archive path: {rel!r}")
    return rel


def fsync_file(path: Path) -> None:
    """Flush a file's content to disk, so a rename that follows cannot expose an empty file."""
    fd = os.open(path, os.O_RDWR)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def fsync_dir(path: Path) -> None:
    """Flush a folder's entries (renames and new names) to disk.

    Windows cannot open a folder for flushing, and some network filesystems refuse it;
    there the rename is as durable as the filesystem makes it.
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _check_discardable(rel: str) -> str:
    """Only a source's ``incoming`` folder, which holds no committed file, may be removed."""
    parts = _check_rel(rel).split("/")
    if len(parts) < 3 or parts[0] != "sources" or parts[2] != "incoming":
        raise ArchiveError(f"Refusing to remove {rel!r}: only incoming folders can be removed")
    return rel


# A rewritten file's archived copy to keep as a version: (current path, version path,
# incoming path of the new copy). The move is due while the new copy is still incoming.
Keep = Tuple[str, str, str]
# A new copy to move into place: (incoming path, current path).
Put = Tuple[str, str]


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

    def missing(self, rels: list[str]) -> list[str]:
        """The paths among ``rels`` that do not exist."""
        return [rel for rel in rels if not self.exists(rel)]

    def move(self, src: str, dst: str) -> bool:
        """Rename within the archive; False when ``src`` does not exist."""
        raise NotImplementedError

    def put_tree(self, staging: Path) -> None:
        """Copy every file under ``staging`` to the same relative path, keeping times.

        A failed transfer can leave a partial file at its target path, so callers send
        only to paths that no manifest lists (a run's incoming folder).
        """
        raise NotImplementedError

    def place(self, keeps: list[Keep], puts: list[Put]) -> None:
        """Move kept copies to their version paths, then move new copies into place.

        Every step can be repeated: a keep is skipped once its version path exists or its
        incoming copy has gone, and a put once its incoming copy has gone. So a run that
        stopped part way is finished by calling this again with the same lists.
        """
        raise NotImplementedError

    def discard_tree(self, rel: str) -> None:
        """Remove a source's incoming folder and everything in it, if it exists."""
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
        folders = _make_parent(path)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        fsync_file(tmp)
        os.replace(tmp, path)
        _sync_dirs(folders)

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
        folders = _make_parent(target) | {source.parent}
        os.replace(source, target)
        _sync_dirs(folders)
        return True

    def put_tree(self, staging: Path) -> None:
        folders = set()
        for dirpath, _dirnames, filenames in os.walk(staging):
            for filename in sorted(filenames):
                src = Path(dirpath) / filename
                rel = src.relative_to(staging).as_posix()
                target = self._path(rel)
                folders |= _make_parent(target)
                tmp = target.with_name(target.name + ".part")
                shutil.copy2(src, tmp)
                fsync_file(tmp)
                os.replace(tmp, target)
        _sync_dirs(folders)

    def place(self, keeps: list[Keep], puts: list[Put]) -> None:
        folders: set[Path] = set()
        try:
            for current, version, incoming in keeps:
                if self.exists(version) or not self.exists(incoming):
                    continue
                if not self.exists(current):
                    raise ArchiveError(
                        f"The archived copy {current} to keep as {version} is missing"
                    )
                self._rename(current, version, folders)
            for incoming, current in puts:
                if self.exists(incoming):
                    self._rename(incoming, current, folders)
        finally:
            _sync_dirs(folders)

    def _rename(self, src: str, dst: str, folders: set[Path]) -> None:
        source, target = self._path(src), self._path(dst)
        folders |= _make_parent(target) | {source.parent}
        os.replace(source, target)

    def discard_tree(self, rel: str) -> None:
        path = self._path(_check_discardable(rel))
        if path.exists():
            shutil.rmtree(path)

    @contextmanager
    def open_binary(self, rel: str) -> Iterator[IO[bytes]]:
        with self._path(rel).open("rb") as handle:
            yield handle


def _make_parent(path: Path) -> set[Path]:
    """Create ``path``'s folder; return the folders whose entries change and need a flush.

    Those are the folder itself, and the parent of every folder that had to be created.
    """
    folder = path.parent
    created = []
    while not folder.exists():
        created.append(folder)
        folder = folder.parent
    path.parent.mkdir(parents=True, exist_ok=True)
    return {path.parent, *(new.parent for new in created)}


def _sync_dirs(folders: set[Path]) -> None:
    """Flush folders, deepest first, so a new folder is on disk before its parent's entry."""
    for folder in sorted(folders, key=lambda path: len(path.parts), reverse=True):
        fsync_dir(folder)


def open_destination(destination: str) -> Destination:
    """Open a destination given as a local path or ``ssh://host/path``."""
    if destination.startswith("ssh://"):
        from agent_history.archive.ssh_destination import SshDestination

        return SshDestination.from_url(destination)
    return LocalDestination(Path(destination).expanduser())
