"""Metadata database: the source of truth for track data (tags, analysis results, covers) of every library root.

Local files are imported from their ID3 tags and edits are written back to the mp3 (re-imported when the file changes on disk).
Remote files (S3) are imported once by downloading them; afterwards the database is authoritative and edits stay there.
"""
import json
import logging
import posixpath
import sqlite3
import threading
import time
from pathlib import Path

from core.lights import LightSetting
from core.mp3 import (Mp3Entry, _audio, parse_mp3, update_mp3_album, update_mp3_artist, update_mp3_bpm, update_mp3_categories,
                      update_mp3_chapters, update_mp3_cover_data, update_mp3_favorite, update_mp3_genre, update_mp3_light, update_mp3_summary,
                      update_mp3_tags, update_mp3_title)
from core.storage import NotFound, StorageError
from core.utils import get_user_data_dir
from server.context import current_user_var
from server.paths import Location, path_to_id
from server.users import ADMIN

logger = logging.getLogger(__file__)

# update fields the database understands (see TrackIndex.update)
FIELDS = ("title", "artist", "album", "summary", "genres", "tags", "bpm", "favorite", "categories", "light")


def track_dict(entry: Mp3Entry, location: Location) -> dict:
    data = entry.to_dict()
    data["path"] = location.client_path
    data["id"] = location.id
    data["file"] = location.name
    data["name"] = location.stem
    data["has_cover"] = entry.has_cover
    data["index"] = entry.index
    return data


def stub_dict(location: Location) -> dict:
    """What the client sees of a remote track that has not been imported yet."""
    return {"path": location.client_path, "id": location.id, "file": location.name, "name": location.stem, "title": None, "artist": None,
            "album": None, "summary": "", "genres": [], "tags": [], "length": -1, "favorite": False, "categories": {}, "bpm": None,
            "light": None, "chapters": [], "has_cover": False, "index": None, "pending": True}


def _like_prefix(prefix: str) -> str:
    return prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "/%"


class TrackIndex:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (get_user_data_dir() / "library.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._importing: set[str] = set()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS tracks (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, data TEXT)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS covers (path TEXT PRIMARY KEY, mime TEXT, data BLOB)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS uploads (path TEXT PRIMARY KEY, user TEXT, at REAL)")
        self._conn.execute("CREATE TABLE IF NOT EXISTS favorites (user TEXT, path TEXT, value INTEGER, PRIMARY KEY (user, path))")
        self._conn.execute("CREATE TABLE IF NOT EXISTS user_state (user TEXT, key TEXT, value TEXT, PRIMARY KEY (user, key))")
        self._conn.commit()

    # --- reading ---------------------------------------------------------

    def _row(self, key: str):
        with self._lock:
            return self._conn.execute("SELECT mtime, size, data FROM tracks WHERE path = ?", (key,)).fetchone()

    def _decorated(self, key: str, data: dict) -> dict:
        """Track data plus who uploaded the file (kept apart from the tags, so it survives re-imports)."""
        user = current_user_var.get() or ADMIN
        with self._lock:
            row = self._conn.execute("SELECT user, at FROM uploads WHERE path = ?", (key,)).fetchone()
            favorite = self._conn.execute("SELECT value FROM favorites WHERE user = ? AND path = ?", (user, key)).fetchone()
        # the SuperAdmin still sees the favorites that were stored in the mp3 before favorites became per user
        data = {**data, "favorite": bool(favorite[0]) if favorite else (user == ADMIN and bool(data.get("favorite")))}
        return {**data, "uploaded_by": row[0], "uploaded_at": row[1]} if row else data

    def set_favorite(self, location: Location, favorite: bool, user: str | None = None):
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO favorites (user, path, value) VALUES (?, ?, ?)",
                               (user or current_user_var.get() or ADMIN, location.client_path, int(favorite)))
            self._conn.commit()

    def user_state(self, user: str, key: str):
        with self._lock:
            row = self._conn.execute("SELECT value FROM user_state WHERE user = ? AND key = ?", (user, key)).fetchone()
        return json.loads(row[0]) if row else None

    def set_user_state(self, user: str, key: str, value):
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO user_state (user, key, value) VALUES (?, ?, ?)", (user, key, json.dumps(value)))
            self._conn.commit()

    def forget_user(self, user: str):
        with self._lock:
            for table in ("favorites", "user_state"):
                self._conn.execute(f"DELETE FROM {table} WHERE user = ?", (user,))
            self._conn.commit()

    def uploads_under(self, location: Location) -> dict[str, str]:
        """Client path -> user for everything at or below a location that somebody uploaded or created."""
        key = location.client_path
        with self._lock:
            rows = self._conn.execute("SELECT path, user FROM uploads WHERE path = ? OR path LIKE ? ESCAPE '\\'", (key, _like_prefix(key))).fetchall()
        return dict(rows)

    def set_uploader(self, location: Location, user: str):
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO uploads (path, user, at) VALUES (?, ?, ?)", (location.client_path, user, time.time()))
            self._conn.commit()

    def _store(self, key: str, data: dict, mtime: float, size: int, cover: tuple[bytes, str] | None = None):
        data = {k: v for k, v in data.items() if k not in ("uploaded_by", "uploaded_at")}
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO tracks (path, mtime, size, data) VALUES (?, ?, ?, ?)",
                               (key, mtime, size, json.dumps(data, ensure_ascii=False)))
            if cover is not None:
                self._conn.execute("INSERT OR REPLACE INTO covers (path, mime, data) VALUES (?, ?, ?)", (key, cover[1], cover[0]))
            self._conn.commit()

    def get(self, location: Location) -> dict | None:
        """Track data for a file. Local files are re-imported when they changed, remote files are imported when unknown."""
        key = location.client_path
        try:
            stat = location.storage.stat(location.rel)
        except NotFound:
            return None
        if stat.is_dir:
            return None
        row = self._row(key)
        if location.root.is_local:
            if row and row[0] == stat.mtime and row[1] == stat.size:
                return self._decorated(key, json.loads(row[2]))
            entry = parse_mp3(location.local_path)
            if entry is None:
                return None
            data = track_dict(entry, location)
            self._store(key, data, stat.mtime, stat.size)
            return self._decorated(key, data)
        if row:
            return self._decorated(key, json.loads(row[2]))
        data = self.import_remote(location)
        return self._decorated(key, data) if data else None

    def known(self, location: Location) -> dict | None:
        """Stored data without touching the storage (None for unknown files)."""
        row = self._row(location.client_path)
        return self._decorated(location.client_path, json.loads(row[2])) if row else None

    def import_remote(self, location: Location) -> dict | None:
        """Downloads a remote file once, reads its tags and stores them."""
        key = location.client_path
        try:
            stat = location.storage.stat(location.rel)
            with location.storage.local_file(location.rel) as tmp:
                entry = parse_mp3(tmp)
                if entry is None:
                    return None
                cover = entry.cover_data()
                entry._has_cover = cover is not None
                data = track_dict(entry, location)
        except NotFound:
            return None
        self._store(key, data, stat.mtime, stat.size, cover)
        return data

    def import_entry(self, location: Location, entry: Mp3Entry, cover: tuple[bytes, str] | None = None) -> dict:
        """Stores an already parsed entry (e.g. right after an upload)."""
        stat = location.storage.stat(location.rel)
        entry._has_cover = cover is not None if not location.root.is_local else entry.has_cover
        data = track_dict(entry, location)
        self._store(location.client_path, data, stat.mtime, stat.size, cover if not location.root.is_local else None)
        return data

    def get_many(self, locations: list[Location]) -> list[dict]:
        """Track data in order; unknown remote files appear as stubs and are imported in the background."""
        result, missing = [], []
        for index, location in enumerate(locations):
            if location.root.is_local:
                data = self.get(location)
            else:
                data = self.known(location)
                if data is None:
                    data = stub_dict(location)
                    missing.append(location)
            if data is not None:
                data = dict(data)
                data["index"] = index
                result.append(data)
        if missing:
            from server.jobs import import_queue
            import_queue.submit(missing)
        return result

    def begin_import(self, location: Location) -> bool:
        """False if this file is already being imported."""
        with self._lock:
            if location.client_path in self._importing:
                return False
            self._importing.add(location.client_path)
            return True

    def end_import(self, location: Location):
        with self._lock:
            self._importing.discard(location.client_path)

    def cover(self, location: Location) -> tuple[bytes, str] | None:
        if location.root.is_local:
            entry = parse_mp3(location.local_path)
            return entry.cover_data() if entry else None
        with self._lock:
            row = self._conn.execute("SELECT data, mime FROM covers WHERE path = ?", (location.client_path,)).fetchone()
        return (bytes(row[0]), row[1]) if row else None

    def invalidate(self, location: Location):
        with self._lock:
            self._conn.execute("DELETE FROM tracks WHERE path = ?", (location.client_path,))
            self._conn.commit()

    # --- writing ---------------------------------------------------------

    def update(self, location: Location, changes: dict) -> dict | None:
        """Applies field changes (see FIELDS) and returns the new track data; local files get their tags rewritten as well."""
        if "favorite" in changes:  # favorites belong to the user, not to the file
            changes = dict(changes)
            self.set_favorite(location, bool(changes.pop("favorite")))
            if not changes:
                return self.get(location)
        if location.root.is_local:
            self._write_tags(location.local_path, changes)
            self.invalidate(location)
        else:
            data = self.get(location)
            if data is None:
                return None
            self._merge(data, changes)
            stat = location.storage.stat(location.rel)
            self._store(location.client_path, data, stat.mtime, stat.size)
        return self.get(location)

    @staticmethod
    def _write_tags(path: Path, changes: dict):
        audio = _audio(path)
        writers = {"title": update_mp3_title, "artist": update_mp3_artist, "album": update_mp3_album, "summary": update_mp3_summary,
                   "genres": update_mp3_genre, "tags": update_mp3_tags, "bpm": update_mp3_bpm, "favorite": update_mp3_favorite,
                   "categories": update_mp3_categories, "light": update_mp3_light}
        for field, write in writers.items():
            if field in changes:
                write(audio, changes[field], False)
        audio.save()

    @staticmethod
    def _merge(data: dict, changes: dict):
        for field in FIELDS:
            if field not in changes:
                continue
            value = changes[field]
            if field == "light":
                value = value.to_dict() if isinstance(value, LightSetting) else value
            elif field in ("genres", "tags"):
                value = list(value or [])
            elif field == "categories":
                if isinstance(value, list):
                    value = {item["category"]: item["scale"] for item in value}
                value = dict(value or {})
            elif field == "favorite":
                value = bool(value)
            data[field] = value

    def set_chapters(self, location: Location, chapters: list[dict]) -> dict | None:
        """``chapters`` are dicts with title, time and an optional LightSetting under ``light``."""
        if location.root.is_local:
            update_mp3_chapters(location.local_path, chapters)
            self.invalidate(location)
        else:
            data = self.get(location)
            if data is None:
                return None
            data["chapters"] = [{"title": c["title"], "time": c["time"], "light": c["light"].to_dict() if c.get("light") else None}
                                for c in chapters]
            stat = location.storage.stat(location.rel)
            self._store(location.client_path, data, stat.mtime, stat.size)
        return self.get(location)

    def set_cover(self, location: Location, image: bytes, mime: str) -> dict | None:
        if location.root.is_local:
            update_mp3_cover_data(location.local_path, image, mime)
            self.invalidate(location)
        else:
            data = self.get(location)
            if data is None:
                return None
            data["has_cover"] = True
            stat = location.storage.stat(location.rel)
            self._store(location.client_path, data, stat.mtime, stat.size, (image, mime))
        return self.get(location)

    def relocate(self, old: Location, new: Location):
        """Follows a moved or renamed file or directory."""
        old_key, new_key = old.client_path, new.client_path
        self._move_uploads(old_key, new_key)
        if old.root.is_local:
            self.invalidate(old)
            return
        base = new.root.client_path("")
        with self._lock:
            rows = self._conn.execute("SELECT path, mtime, size, data FROM tracks WHERE path = ? OR path LIKE ? ESCAPE '\\'",
                                      (old_key, _like_prefix(old_key))).fetchall()
        moved_rows = []
        for path, mtime, size, raw in rows:
            moved = new_key + path[len(old_key):]
            try:  # a moved object is a copy with its own modification time; keep rescans from seeing it as changed
                stat = new.storage.stat(moved[len(base):].lstrip("/"))
                mtime, size = stat.mtime, stat.size
            except StorageError:
                pass
            data = json.loads(raw)
            data.update(path=moved, id=path_to_id(moved), file=posixpath.basename(moved), name=posixpath.splitext(posixpath.basename(moved))[0])
            moved_rows.append((path, moved, mtime, size, data))
        with self._lock:
            for path, moved, mtime, size, data in moved_rows:
                self._conn.execute("DELETE FROM tracks WHERE path = ?", (path,))
                self._conn.execute("INSERT OR REPLACE INTO tracks (path, mtime, size, data) VALUES (?, ?, ?, ?)",
                                   (moved, mtime, size, json.dumps(data, ensure_ascii=False)))
                self._conn.execute("UPDATE covers SET path = ? WHERE path = ?", (moved, path))
            self._conn.commit()

    def _move_uploads(self, old_key: str, new_key: str):
        with self._lock:
            for table in ("uploads", "favorites"):
                self._conn.execute(f"UPDATE {table} SET path = ? || substr(path, ?) WHERE path = ? OR path LIKE ? ESCAPE '\\'",
                                   (new_key, len(old_key) + 1, old_key, _like_prefix(old_key)))
            self._conn.commit()

    def stored_under(self, location: Location) -> dict[str, tuple[float, int]]:
        """Client path -> (mtime, size) of every stored track at or below a location."""
        key = location.client_path
        with self._lock:
            rows = self._conn.execute("SELECT path, mtime, size FROM tracks WHERE path = ? OR path LIKE ? ESCAPE '\\'",
                                      (key, _like_prefix(key))).fetchall()
        return {path: (mtime, size) for path, mtime, size in rows}

    def forget_paths(self, paths: list[str]):
        with self._lock:
            for table in ("tracks", "covers", "uploads", "favorites"):
                self._conn.executemany(f"DELETE FROM {table} WHERE path = ?", [(path,) for path in paths])
            self._conn.commit()

    def forget(self, location: Location):
        """Drops a deleted file or directory."""
        key = location.client_path
        with self._lock:
            for table in ("tracks", "covers", "uploads", "favorites"):
                self._conn.execute(f"DELETE FROM {table} WHERE path = ? OR path LIKE ? ESCAPE '\\'", (key, _like_prefix(key)))
            self._conn.commit()

    def close(self):
        self._conn.close()


def entry_from_dict(data: dict) -> Mp3Entry:
    """Rebuilds an Mp3Entry from track data (for scoring or analysis checks)."""
    entry = Mp3Entry(data["path"], name=data.get("file"), categories=data.get("categories"), tags=data.get("tags"), artist=data.get("artist"),
                     album=data.get("album"), title=data.get("title"), genre=data.get("genres"), bpm=data.get("bpm"))
    entry.summary = data.get("summary") or ""
    entry.length = data.get("length", -1)
    entry.favorite = data.get("favorite", False)
    if data.get("light"):
        entry.light = LightSetting(**data["light"])
    return entry


_index: TrackIndex | None = None


def get_index() -> TrackIndex:
    global _index
    if _index is None:
        from server.config import get_config
        data_dir = get_config().data_dir
        _index = TrackIndex(data_dir / "library.db" if data_dir else None)
    return _index


def set_index(index: TrackIndex | None):
    global _index
    _index = index


__all__ = ["TrackIndex", "get_index", "set_index", "entry_from_dict", "track_dict", "stub_dict"]
