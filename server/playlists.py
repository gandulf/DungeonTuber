"""Extended M3U playlists read and written through the storage of their library root (local or remote).

The title of an `#EXTINF` line is the scene name of the entry when it differs from the file name: the same song can be
"Boss fight" in one playlist and "Arrival at the tavern" in another without touching the mp3.
"""
import logging
import os
import posixpath
import uuid
from pathlib import Path

from core.storage import InvalidPath, StorageError, normalize
from server.index import get_index
from server.paths import Location, locate
from server.roots import REMOTE_PREFIX, get_roots

logger = logging.getLogger(__file__)

ID_PREFIX = "#DT-ID:"  # comment line with the stable id of a playlist; other players ignore it


def read_entries(playlist: Location, base: Location | None = None) -> list[tuple[Location, str | None]] | None:
    """The tracks of a playlist with their scene names (None if unnamed), or None if the file is not an extended M3U.
    Relative entries are resolved against `base` (default: the playlist itself), e.g. where a moved playlist was before."""
    text = playlist.storage.read_bytes(playlist.rel).decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    if not lines or not lines[0].lstrip("﻿").startswith("#EXTM3U"):
        return None
    result = []
    title = None
    for line in lines[1:]:
        line = line.strip()
        if line.startswith("#EXTINF:"):
            title = line[len("#EXTINF:"):].partition(",")[2].strip() or None
        elif line and not line.startswith("#"):
            location = _resolve(base or playlist, line)
            if location is not None:
                result.append((location, title if title and title != location.stem else None))
            title = None
    return result


def _read_text(playlist: Location) -> str:
    return playlist.storage.read_bytes(playlist.rel).decode("utf-8-sig", errors="replace")


def read_id(playlist: Location) -> str | None:
    """The stable id of an extended M3U playlist, or None if it has none (yet)."""
    for line in _read_text(playlist).splitlines()[1:]:
        if line.startswith(ID_PREFIX):
            return line[len(ID_PREFIX):].strip() or None
    return None


def ensure_id(playlist: Location) -> str | None:
    """Gives an extended M3U playlist a stable id (kept when it is moved, renamed or rewritten) and records it in the index.
    Returns "assigned" or "present", or None if the file is not an extended M3U."""
    text = _read_text(playlist)
    lines = text.splitlines()
    if not lines or not lines[0].lstrip("﻿").startswith("#EXTM3U"):
        return None
    index = get_index()
    for line in lines[1:]:
        if line.startswith(ID_PREFIX) and line[len(ID_PREFIX):].strip():
            index.set_playlist_id(playlist.client_path, line[len(ID_PREFIX):].strip())
            return "present"
    playlist_id = str(uuid.uuid4())
    lines.insert(1, ID_PREFIX + playlist_id)
    playlist.storage.write(playlist.rel, ("\n".join(lines) + "\n").encode("utf-8"), overwrite=True)
    index.set_playlist_id(playlist.client_path, playlist_id)
    return "assigned"


def find(playlist_id: str) -> list[Location]:
    """The playlists with this id. The index knows where they were; if none is there any more (moved outside of Dungeon Tuber), the
    libraries are searched."""
    index = get_index()
    found = []
    for path in index.find_playlist(playlist_id):
        try:
            location = locate(path)
            if location and location.storage.exists(location.rel) and read_id(location) == playlist_id:
                found.append(location)
        except (StorageError, InvalidPath, OSError):
            continue
    if found:
        return found
    for root in get_roots():
        base = Location(root)
        try:
            entries = [e for e in base.storage.walk(base.rel) if e.path.lower().endswith(".m3u")]
        except StorageError:
            continue
        for entry in entries:
            location = Location(root, entry.path)
            try:
                current = read_id(location)
            except (StorageError, OSError):
                continue
            if current:
                index.set_playlist_id(location.client_path, current)
                if current == playlist_id:
                    found.append(location)
    return found


def read(playlist: Location) -> list[Location] | None:
    """The tracks of a playlist, or None if the file is not an extended M3U."""
    entries = read_entries(playlist)
    return None if entries is None else [location for location, _ in entries]


def scenes(playlist: Location) -> dict[Location, str]:
    """The scene names of the entries of a playlist that have one."""
    return {location: scene for location, scene in (read_entries(playlist) or []) if scene}


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


def write(playlist: Location, tracks: list[Location], names: dict[Location, str] | None = None):
    """Writes the playlist; the scene names of the entries are kept unless `names` replaces them."""
    if names is None:
        names = scenes(playlist) if playlist.storage.exists(playlist.rel) else {}
    existing = read_id(playlist) if playlist.storage.exists(playlist.rel) else None
    playlist_id = existing or str(uuid.uuid4())
    lines = ["#EXTM3U", ID_PREFIX + playlist_id]
    index = get_index()
    index.set_playlist_id(playlist.client_path, playlist_id)
    for track in tracks:
        relative = _relative(playlist, track)
        data = index.known(track) or {}
        title = " ".join((names.get(track) or track.stem).split())  # one line, whatever was typed
        lines.append(f"#EXTINF:{data.get('length', -1)},{title}")
        lines.append(relative)
    playlist.storage.write(playlist.rel, ("\n".join(lines) + "\n").encode("utf-8"), overwrite=True)


def append(playlist: Location, tracks: list[Location], index: int = -1) -> int:
    """Adds tracks that are not in the playlist yet (at `index`, default the end) and returns how many were added."""
    entries = read_entries(playlist) or []
    current = [location for location, _ in entries]
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
    write(playlist, current, {location: scene for location, scene in entries if scene})
    return len(new)


def remove(playlist: Location, tracks: list[Location]):
    removed = set(tracks)
    write(playlist, [track for track in (read(playlist) or []) if track not in removed])


def set_scene(playlist: Location, track: Location, scene: str | None) -> bool:
    """Names (or with an empty name unnames) an entry of the playlist; False if the song is not in it."""
    entries = read_entries(playlist) or []
    if track not in [location for location, _ in entries]:
        return False
    names = {location: name for location, name in entries if name}
    scene = " ".join((scene or "").split())
    if scene:
        names[track] = scene
    else:
        names.pop(track, None)
    write(playlist, [location for location, _ in entries], names)
    return True


def _moved(location: Location, old: Location, new: Location) -> Location | None:
    """Where `location` is after `old` was moved to `new`; None if the move did not touch it."""
    if location == old:
        return new
    if not old.is_root and location.is_relative_to(old):
        return Location(new.root, new.rel + location.rel[len(old.rel):])
    return None


def follow_move(old: Location, new: Location) -> list[Location]:
    """Rewrites every playlist of every library that refers to a song moved or renamed from `old` to `new` (a file or
    a whole folder), keeping order and scene names; returns the playlists that changed."""
    changed = []
    for root in get_roots():
        try:
            files = [entry.path for entry in root.storage.walk("") if entry.name.lower().endswith(".m3u")]
        except StorageError as e:
            logger.warning("Playlists of {0} could not be checked: {1}", root.name, e)
            continue
        for path in files:
            playlist = Location(root, path)
            previous = _moved(playlist, new, old)  # a playlist that moved along resolves its entries from where it was
            try:
                entries = read_entries(playlist, previous)
                if not entries:
                    continue
                moved = [(_moved(location, old, new) or location, scene) for location, scene in entries]
                if moved == entries and (previous is None or previous.parent == playlist.parent):
                    continue
                write(playlist, [location for location, _ in moved], {location: scene for location, scene in moved if scene})
                changed.append(playlist)
            except (StorageError, OSError) as e:
                logger.warning("Playlist {0} could not be updated: {1}", playlist.client_path, e)
    return changed
