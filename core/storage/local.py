"""Local directory backend."""
from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path
from typing import BinaryIO, Iterator

from core.storage.base import AlreadyExists, InvalidPath, NotFound, Storage, StorageEntry, copy_stream, normalize

CHUNK = 1024 * 1024


class LocalStorage(Storage):
    type = "local"

    def __init__(self, root: Path | str, name: str = ""):
        self.root = Path(root).expanduser().resolve()
        super().__init__(name or self.root.name or self.root.as_posix())

    def resolve(self, path: str) -> Path:
        """Absolute path of a relative storage path; symlinks pointing out of the root are rejected."""
        resolved = (self.root / normalize(path)).resolve()
        if resolved != self.root and not resolved.is_relative_to(self.root):
            raise InvalidPath("Path is outside of the library")
        return resolved

    def relative(self, absolute: Path | str) -> str:
        """Storage path for an absolute path inside the root."""
        resolved = Path(absolute).resolve()
        if resolved == self.root:
            return ""
        try:
            return resolved.relative_to(self.root).as_posix()
        except ValueError:
            raise InvalidPath("Path is outside of the library")

    def _entry(self, path: Path) -> StorageEntry:
        try:
            stat = path.stat()
        except OSError:
            raise NotFound(path.name)
        return StorageEntry(self.relative(path), path.is_dir(), 0 if path.is_dir() else stat.st_size, stat.st_mtime)

    def stat(self, path: str) -> StorageEntry:
        return self._entry(self.resolve(path))

    def list(self, path: str = "") -> list[StorageEntry]:
        directory = self.resolve(path)
        if not directory.is_dir():
            raise NotFound(path)
        entries = []
        with os.scandir(directory) as it:
            for item in it:
                try:
                    entries.append(self._entry(Path(item.path)))
                except (NotFound, InvalidPath):
                    continue
        return entries

    def read(self, path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        file = self.resolve(path)
        if not file.is_file():
            raise NotFound(path)
        remaining = None if end is None else end - start + 1
        with open(file, "rb") as f:
            f.seek(start)
            while remaining is None or remaining > 0:
                chunk = f.read(CHUNK if remaining is None else min(CHUNK, remaining))
                if not chunk:
                    break
                if remaining is not None:
                    remaining -= len(chunk)
                yield chunk

    @contextlib.contextmanager
    def local_file(self, path: str) -> Iterator[Path]:
        file = self.resolve(path)
        if not file.is_file():
            raise NotFound(path)
        yield file

    def write(self, path: str, data: BinaryIO | bytes, overwrite: bool = False):
        target = self.resolve(path)
        if target == self.root:
            raise InvalidPath("Invalid path")
        if target.exists() and not overwrite:
            raise AlreadyExists(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".part")
        try:
            with open(tmp, "wb") as out:
                if isinstance(data, bytes):
                    out.write(data)
                else:
                    copy_stream(data, out, CHUNK)
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)

    def mkdir(self, path: str):
        target = self.resolve(path)
        if target.exists():
            raise AlreadyExists(path)
        target.mkdir(parents=True)

    def delete(self, path: str):
        target = self.resolve(path)
        if target == self.root:
            raise InvalidPath("Cannot delete the library root")
        if not target.exists():
            raise NotFound(path)
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()

    def move(self, source: str, target: str):
        src, dst = self.resolve(source), self.resolve(target)
        if src == self.root or dst == self.root:
            raise InvalidPath("Invalid path")
        if not src.exists():
            raise NotFound(source)
        if dst.exists():
            raise AlreadyExists(target)
        if src.is_dir() and dst.is_relative_to(src):
            raise InvalidPath("Cannot move a folder into itself")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
