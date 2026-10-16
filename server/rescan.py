"""Brings the metadata database in line with what is actually stored (new, replaced and deleted files)."""
import logging

from core.storage import StorageError
from server import playlists
from server.index import get_index
from server.jobs import import_queue
from server.paths import Location

logger = logging.getLogger(__file__)


def rescan(location: Location) -> dict:
    """Compares the storage with the database below ``location``.

    Deleted files are dropped from the database. For remote storages, new files are imported and files whose object changed
    (size or modification time) are re-imported, which replaces their stored tags. Local files are re-read lazily when they change.
    """
    index = get_index()
    storage = location.storage
    stored = index.stored_under(location)

    entry = storage.stat(location.rel)
    entries = [entry] if not entry.is_dir else storage.walk(location.rel)
    found = {}
    lists = []
    for item in entries:
        if item.path.lower().endswith(".mp3"):
            found[Location(location.root, item.path).client_path] = (Location(location.root, item.path), item)
        elif item.path.lower().endswith(".m3u"):
            lists.append(Location(location.root, item.path))

    removed = [path for path in stored if path not in found]
    index.forget_paths(removed)

    added, changed = [], []
    if not location.root.is_local:
        for path, (loc, item) in found.items():
            if path not in stored:
                added.append(loc)
            elif stored[path] != (item.mtime, item.size):
                changed.append(loc)
        import_queue.submit(added + changed)
    ids = assign_ids([loc for loc, _ in found.values()], lists)
    return {"added": len(added), "changed": len(changed), "removed": len(removed), "total": len(found), **ids}


def assign_ids(songs: list[Location], lists: list[Location]) -> dict:
    """Gives songs (UFID) and playlists (#DT-ID) that have no stable id one. Files that cannot be written are counted and keep working
    without an id; unknown remote songs get theirs when they are imported."""
    index = get_index()
    result = {"ids_assigned": 0, "ids_failed": 0}
    for song in songs:
        outcome = index.ensure_ufid(song)
        if outcome == "assigned":
            result["ids_assigned"] += 1
        elif outcome == "failed":
            result["ids_failed"] += 1
    for playlist in lists:
        try:
            if playlists.ensure_id(playlist) == "assigned":
                result["ids_assigned"] += 1
        except (StorageError, OSError) as e:
            logger.warning("Could not give {0} an id: {1}", playlist.client_path, e)
            result["ids_failed"] += 1
    return result
