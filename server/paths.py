"""Opaque ids for files and the library-root security boundary."""
import base64
import posixpath
from pathlib import Path

from fastapi import HTTPException

from core.storage import InvalidPath, NotFound, Storage, normalize
from server.roots import REMOTE_PREFIX, Root, get_roots


def path_to_id(path: Path | str) -> str:
    text = path if isinstance(path, str) else Path(path).as_posix()
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


def id_to_path(file_id: str) -> str:
    try:
        padded = file_id + "=" * (-len(file_id) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid id")


class Location:
    """A file or directory inside a library root."""
    __slots__ = ("root", "rel")

    def __init__(self, root: Root, rel: str = ""):
        self.root = root
        self.rel = normalize(rel)

    @property
    def storage(self) -> Storage:
        return self.root.storage

    @property
    def client_path(self) -> str:
        return self.root.client_path(self.rel)

    @property
    def id(self) -> str:
        return path_to_id(self.client_path)

    @property
    def name(self) -> str:
        return posixpath.basename(self.rel) or self.root.name

    @property
    def stem(self) -> str:
        return posixpath.splitext(self.name)[0]

    @property
    def suffix(self) -> str:
        return posixpath.splitext(self.name)[1].lower()

    @property
    def is_root(self) -> bool:
        return not self.rel

    @property
    def parent(self) -> "Location | None":
        return None if self.is_root else Location(self.root, posixpath.dirname(self.rel))

    @property
    def local_path(self) -> Path | None:
        """The file on disk for local roots, None for remote ones."""
        return self.storage.resolve(self.rel) if self.root.is_local else None

    def child(self, name: str) -> "Location":
        return Location(self.root, f"{self.rel}/{name}")

    def sibling(self, name: str) -> "Location":
        return Location(self.root, f"{posixpath.dirname(self.rel)}/{name}")

    def is_relative_to(self, other: "Location") -> bool:
        return self.root == other.root and (not other.rel or self.rel == other.rel or self.rel.startswith(other.rel + "/"))

    def __eq__(self, other):
        return isinstance(other, Location) and self.root == other.root and self.rel == other.rel

    def __hash__(self):
        return hash((self.root.id, self.rel))

    def __repr__(self):
        return f"Location({self.client_path!r})"


def locate(path: Path | str) -> Location | None:
    """The location of a client path (or an absolute local path) if it lies in a library root; never touches the filesystem content."""
    text = path if isinstance(path, str) else Path(path).as_posix()
    if text.startswith(REMOTE_PREFIX):
        root_id, _, rel = text[len(REMOTE_PREFIX):].partition("/")
        for root in get_roots():
            if root.id == root_id and not root.is_local:
                try:
                    return Location(root, rel)
                except InvalidPath:
                    return None
        return None
    try:
        resolved = Path(text).expanduser().resolve()
    except OSError:
        return None
    best: Root | None = None
    for root in get_roots():
        if root.is_local and (resolved == root.storage.root or resolved.is_relative_to(root.storage.root)):
            if best is None or len(root.storage.root.parts) > len(best.storage.root.parts):
                best = root
    return Location(best, best.storage.relative(resolved)) if best else None


def safe_path(path: Path | str, must_exist: bool = True, kind: str | None = None) -> Location:
    """Resolves a client supplied path and makes sure it is inside a library root."""
    if path is None or str(path) == "":
        raise HTTPException(status_code=400, detail="Missing path")
    location = locate(path)
    if location is None:
        raise HTTPException(status_code=403, detail="Path is outside of the library")
    if must_exist:
        try:
            entry = location.storage.stat(location.rel)
        except NotFound:
            raise HTTPException(status_code=404, detail="Not found")
        except InvalidPath:
            raise HTTPException(status_code=403, detail="Path is outside of the library")
        if kind == "dir" and not entry.is_dir:
            raise HTTPException(status_code=400, detail="Not a directory")
        if kind == "file" and entry.is_dir:
            raise HTTPException(status_code=400, detail="Not a file")
    return location


def safe_id(file_id: str, kind: str | None = "file") -> Location:
    return safe_path(id_to_path(file_id), kind=kind)


def safe_name(name: str) -> str:
    """A single file name component without directory parts."""
    name = (name or "").strip()
    if not name or name in (".", "..") or any(c in name for c in '/\\:*?"<>|') or "\0" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    return name
