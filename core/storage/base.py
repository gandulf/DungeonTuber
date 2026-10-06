"""Storage abstraction: one interface for a library root, whether it is a local directory or an object store.

Paths handed to a ``Storage`` are always relative to its root, use forward slashes and never contain ``..``.
The empty path ``""`` is the root itself. Containment is enforced by the storage, not by the callers.
"""
from __future__ import annotations

import contextlib
import posixpath
import shutil
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator


class StorageError(Exception):
    pass


class NotFound(StorageError):
    pass


class AlreadyExists(StorageError):
    pass


class InvalidPath(StorageError):
    pass


@dataclass(frozen=True)
class StorageEntry:
    path: str  # relative to the storage root
    is_dir: bool
    size: int = 0
    mtime: float = 0.0

    @property
    def name(self) -> str:
        return posixpath.basename(self.path)


def normalize(path: str | None) -> str:
    """Normalizes a client supplied relative path; rejects anything that could leave the root."""
    if not path:
        return ""
    if "\0" in path:
        raise InvalidPath("Invalid path")
    parts = []
    for part in path.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == ".." or (len(parts) == 0 and part.endswith(":")):
            raise InvalidPath("Path is outside of the library")
        parts.append(part)
    return "/".join(parts)


def join(parent: str, name: str) -> str:
    return normalize(f"{parent}/{name}")


def parent_of(path: str) -> str:
    return posixpath.dirname(normalize(path))


class Storage(ABC):
    """A library root. Implementations must be safe to call from multiple threads."""

    #: short identifier of the backend type, used in settings ("local", "s3")
    type: str = ""

    def __init__(self, name: str = ""):
        self.name = name

    # --- queries ---------------------------------------------------------

    @abstractmethod
    def stat(self, path: str) -> StorageEntry:
        """Entry for a file or directory; raises NotFound."""

    @abstractmethod
    def list(self, path: str = "") -> list[StorageEntry]:
        """Direct children of a directory (no recursion); raises NotFound if it is not a directory."""

    def exists(self, path: str) -> bool:
        try:
            self.stat(path)
            return True
        except NotFound:
            return False

    def walk(self, path: str = "") -> Iterator[StorageEntry]:
        """All files below a directory, recursively (directories are not yielded)."""
        for entry in self.list(path):
            if entry.is_dir:
                yield from self.walk(entry.path)
            else:
                yield entry

    # --- reading ---------------------------------------------------------

    @abstractmethod
    def read(self, path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        """Streams the bytes ``[start, end]`` (inclusive, like an HTTP range) in chunks; the whole file by default."""

    def read_bytes(self, path: str) -> bytes:
        return b"".join(self.read(path))

    def url(self, path: str, expires: int = 3600) -> str | None:
        """A time limited direct URL a browser can stream from, or None if the backend cannot provide one."""
        return None

    @contextlib.contextmanager
    def local_file(self, path: str) -> Iterator[Path]:
        """A local filesystem path for libraries that need one (tag parsing, analysis). Remote backends download a
        temporary copy that is removed afterwards; do not modify it."""
        entry = self.stat(path)
        if entry.is_dir:
            raise NotFound(path)
        suffix = posixpath.splitext(path)[1]
        with tempfile.TemporaryDirectory(prefix="dt-storage-") as tmp:
            target = Path(tmp) / f"file{suffix}"
            with open(target, "wb") as out:
                for chunk in self.read(path):
                    out.write(chunk)
            yield target

    # --- writing ---------------------------------------------------------

    @abstractmethod
    def write(self, path: str, data: BinaryIO | bytes, overwrite: bool = False):
        """Stores a file; raises AlreadyExists unless ``overwrite``."""

    @abstractmethod
    def mkdir(self, path: str):
        """Creates a directory; raises AlreadyExists if it exists."""

    @abstractmethod
    def delete(self, path: str):
        """Deletes a file or a directory with everything in it; raises NotFound."""

    @abstractmethod
    def move(self, source: str, target: str):
        """Moves or renames a file or directory; raises NotFound / AlreadyExists."""


def copy_stream(source: BinaryIO, target: BinaryIO, chunk: int = 1024 * 1024):
    shutil.copyfileobj(source, target, chunk)
