"""Opaque ids for files and the library-root security boundary."""
import base64
from pathlib import Path

from fastapi import HTTPException

from server.config import get_library_roots


def path_to_id(path: Path | str) -> str:
    raw = Path(path).as_posix().encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def id_to_path(file_id: str) -> Path:
    try:
        padded = file_id + "=" * (-len(file_id) % 4)
        return Path(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="Invalid id")


def is_within_roots(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in get_library_roots():
        if resolved == root or resolved.is_relative_to(root):
            return True
    return False


def safe_path(path: Path | str, must_exist: bool = True, kind: str | None = None) -> Path:
    """Resolves a client supplied path and makes sure it is inside a library root."""
    if path is None or str(path) == "":
        raise HTTPException(status_code=400, detail="Missing path")
    resolved = Path(path).expanduser().resolve()
    if not is_within_roots(resolved):
        raise HTTPException(status_code=403, detail="Path is outside of the library")
    if must_exist and not resolved.exists():
        raise HTTPException(status_code=404, detail="Not found")
    if kind == "dir" and must_exist and not resolved.is_dir():
        raise HTTPException(status_code=400, detail="Not a directory")
    if kind == "file" and must_exist and not resolved.is_file():
        raise HTTPException(status_code=400, detail="Not a file")
    return resolved


def safe_id(file_id: str, kind: str | None = "file") -> Path:
    return safe_path(id_to_path(file_id), kind=kind)


def safe_name(name: str) -> str:
    """A single file name component without directory parts."""
    name = (name or "").strip()
    if not name or name in (".", "..") or any(c in name for c in '/\\:*?"<>|') or "\0" in name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    return name
