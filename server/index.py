"""SQLite cache of parsed tracks so large libraries load without re-reading every tag."""
import json
import logging
import os
import sqlite3
import threading
from pathlib import Path

from core.mp3 import parse_mp3, Mp3Entry
from core.lights import LightSetting
from core.utils import get_user_data_dir
from server.paths import path_to_id

logger = logging.getLogger(__file__)


def track_dict(entry: Mp3Entry) -> dict:
    data = entry.to_dict()
    data["id"] = path_to_id(entry.path)
    data["file"] = entry.path.name
    data["has_cover"] = entry.has_cover
    data["index"] = entry.index
    return data


class TrackIndex:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (get_user_data_dir() / "library.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS tracks (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, data TEXT)")
        self._conn.commit()

    def get(self, path: Path) -> dict | None:
        """Track data for a file, re-parsed only when the file changed."""
        try:
            stat = os.stat(path)
        except OSError:
            return None
        key = Path(path).as_posix()
        with self._lock:
            row = self._conn.execute("SELECT mtime, size, data FROM tracks WHERE path = ?", (key,)).fetchone()
        if row and row[0] == stat.st_mtime and row[1] == stat.st_size:
            return json.loads(row[2])

        entry = parse_mp3(path)
        if entry is None:
            return None
        data = track_dict(entry)
        with self._lock:
            self._conn.execute("INSERT OR REPLACE INTO tracks (path, mtime, size, data) VALUES (?, ?, ?, ?)",
                               (key, stat.st_mtime, stat.st_size, json.dumps(data, ensure_ascii=False)))
            self._conn.commit()
        return data

    def get_many(self, paths: list[Path]) -> list[dict]:
        result = []
        for index, path in enumerate(paths):
            data = self.get(path)
            if data is not None:
                data = dict(data)
                data["index"] = index
                result.append(data)
        return result

    def invalidate(self, path: Path):
        with self._lock:
            self._conn.execute("DELETE FROM tracks WHERE path = ?", (Path(path).as_posix(),))
            self._conn.commit()

    def close(self):
        self._conn.close()


def entry_from_dict(data: dict) -> Mp3Entry:
    """Rebuilds an Mp3Entry from track data (for scoring or playlist writing)."""
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
