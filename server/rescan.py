"""Brings the metadata database in line with what is actually stored (new, replaced and deleted files)."""
from server.index import get_index
from server.jobs import import_queue
from server.paths import Location


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
    for item in entries:
        if item.path.lower().endswith(".mp3"):
            found[Location(location.root, item.path).client_path] = (Location(location.root, item.path), item)

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
    return {"added": len(added), "changed": len(changed), "removed": len(removed), "total": len(found)}
