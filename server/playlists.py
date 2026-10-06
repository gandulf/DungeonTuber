"""Extended M3U playlists read and written through the storage of their library root (local or remote)."""
import os
import posixpath
from pathlib import Path

from core.storage import InvalidPath, normalize
from server.index import get_index
from server.paths import Location, locate
from server.roots import REMOTE_PREFIX


def read(playlist: Location) -> list[Location] | None:
    """The tracks of a playlist, or None if the file is not an extended M3U."""
    text = playlist.storage.read_bytes(playlist.rel).decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].lstrip("﻿").startswith("#EXTM3U"):
        return None
    result = []
    for line in lines[1:]:
        line = line.strip()
        if line and not line.startswith("#"):
            location = _resolve(playlist, line)
            if location is not None:
                result.append(location)
    return result


def _is_absolute(entry: str) -> bool:
    return entry.startswith(REMOTE_PREFIX) or Path(entry).is_absolute() or posixpath.isabs(entry)


def _resolve(playlist: Location, entry: str) -> Location | None:
    if _is_absolute(entry) and (entry.startswith(REMOTE_PREFIX) or not playlist.root.is_local):
        return locate(entry)  # a song of another library (local or remote) is stored with its full path
    if playlist.root.is_local:
        base = playlist.local_path.parent
        return locate(Path(entry) if Path(entry).is_absolute() else base / entry)
    try:
        return Location(playlist.root, normalize(posixpath.normpath(posixpath.join(posixpath.dirname(playlist.rel), entry))))
    except InvalidPath:
        return None


def _relative(playlist: Location, track: Location) -> str:
    """How a playlist refers to a song: relative inside the same library, with the full path when the song lives elsewhere."""
    if playlist.root.is_local and track.root.is_local:
        try:
            return os.path.relpath(track.local_path, playlist.local_path.parent).replace('\\', "/")
        except ValueError:  # another drive
            return track.client_path
    if track.root == playlist.root:
        return posixpath.relpath(track.rel, posixpath.dirname(playlist.rel) or ".")
    return track.client_path


def write(playlist: Location, tracks: list[Location]):
    lines = ["#EXTM3U"]
    index = get_index()
    for track in tracks:
        relative = _relative(playlist, track)
        data = index.known(track) or {}
        lines.append(f"#EXTINF:{data.get('length', -1)},{track.stem}")
        lines.append(relative)
    playlist.storage.write(playlist.rel, ("\n".join(lines) + "\n").encode("utf-8"), overwrite=True)


def append(playlist: Location, tracks: list[Location], index: int = -1) -> int:
    """Adds tracks that are not in the playlist yet (at `index`, default the end) and returns how many were added."""
    current = read(playlist) or []
    known = set(current)
    new = []
    for track in tracks:
        if track not in known:
            known.add(track)
            new.append(track)
    if not new:
        return 0
    if index < 0:
        current.extend(new)
    else:
        for track in reversed(new):
            current.insert(index, track)
    write(playlist, current)
    return len(new)


def remove(playlist: Location, tracks: list[Location]):
    removed = set(tracks)
    write(playlist, [track for track in (read(playlist) or []) if track not in removed])
