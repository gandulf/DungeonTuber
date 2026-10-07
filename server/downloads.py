"""Background queue that imports YouTube links into the library (one download at a time), reporting through the event hub."""
import contextlib
import logging
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from core.i18n import _
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from core.storage import AlreadyExists
from core.ytimport import DEFAULT_MAX_MINUTES, ImportFailed, download, file_name
from server import playlists
from server.events import hub
from server.index import get_index
from server.jobs import analysis_queue
from server.paths import Location

logger = logging.getLogger(__file__)

QUEUED, DOWNLOADING, DONE, SKIPPED, FAILED = "queued", "downloading", "done", "skipped", "failed"


@dataclass
class Item:
    id: int
    url: str
    title: str
    state: str = QUEUED
    percent: int = 0
    message: str = ""  # what is happening, or why it failed

    def to_dict(self) -> dict:
        return {"id": self.id, "url": self.url, "title": self.title, "state": self.state, "percent": self.percent, "message": self.message}


@dataclass
class Batch:
    directory: Location
    entries: list[tuple[str, str]]  # (url, title shown until the real title is known)
    user: str
    album: str | None = None
    playlist: str | None = None  # name of an m3u playlist to create from the imported songs
    analyze: bool = False  # hand every imported song to the analysis agent
    split: bool = False  # one song per chapter, in a folder named after the video
    items: list[Item] = field(default_factory=list)


def max_minutes() -> int:
    return max(1, AppSettings.value(SettingKeys.IMPORT_MAX_MINUTES, DEFAULT_MAX_MINUTES, type=int))


def make_folder(directory: Location, name: str, user: str) -> Location:
    """The subfolder of a playlist (created when missing)."""
    folder = directory.child(file_name(name, "playlist")[:-len(".mp3")])
    if not folder.storage.exists(folder.rel):
        with contextlib.suppress(AlreadyExists):
            folder.storage.mkdir(folder.rel)
        get_index().set_uploader(folder, user)
        hub.publish("library.changed", {"path": directory.client_path})
    return folder


def store(directory: Location, path: Path, name: str, user: str) -> Location | None:
    """Puts a finished mp3 into the library (any storage); None if a file of that name is already there."""
    target = directory.child(name)
    if target.storage.exists(target.rel):
        return None
    entry = parse_mp3(path)
    if entry is None:
        raise ImportFailed(_("Not a valid mp3 file: {0}").format(name))
    cover = entry.cover_data()
    with open(path, "rb") as source:
        target.storage.write(target.rel, source)
    index = get_index()
    if target.root.is_local:
        index.get(target)
    else:
        index.import_entry(target, entry, cover)
    index.set_uploader(target, user)
    return target


class DownloadQueue:
    def __init__(self):
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self._next_id = 0
        self.items: list[Item] = []
        self.pending = 0
        self.done = 0
        self.failed = 0

    def status(self) -> dict:
        """Counters and every item of the current run (finished ones stay until the next run starts)."""
        with self._lock:
            return self._status()

    def _status(self) -> dict:
        return {"pending": self.pending, "done": self.done, "failed": self.failed, "items": [item.to_dict() for item in self.items]}

    def _publish(self):
        hub.publish("import.items", self.status())

    def _update(self, item: Item, **changes):
        with self._lock:
            for key, value in changes.items():
                setattr(item, key, value)
        self._publish()

    def submit(self, batch: Batch) -> int:
        with self._lock:
            if self.pending == 0:
                self.items = []
                self.done = self.failed = 0
            for url, title in batch.entries:
                self._next_id += 1
                item = Item(self._next_id, url, title or url)
                batch.items.append(item)
                self.items.append(item)
            self.pending += len(batch.items)
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="download")
            self._executor.submit(self._run, batch)
        self._publish()
        return len(batch.items)

    def _item(self, batch: Batch, item: Item) -> list[Location]:
        """Downloads one video; returns the songs that were stored (none if they all existed already)."""
        last = [-1]

        def percent(value: int):
            if value != last[0]:
                last[0] = value
                self._update(item, percent=value)

        self._update(item, state=DOWNLOADING, message="")
        with tempfile.TemporaryDirectory(prefix="dt-import-") as tmp:
            result = download(item.url, Path(tmp), lambda message: self._update(item, message=message), max_minutes(), batch.album, percent,
                              batch.split)
            self._update(item, title=result.title, message=_("Saving..."))
            directory = make_folder(batch.directory, result.title, batch.user) if result.parts else batch.directory
            stored = []
            for song in result.parts or [result]:
                target = store(directory, song.path, song.name, batch.user)
                if target is not None:
                    stored.append(target)
        if not stored:
            self._update(item, state=SKIPPED, percent=100, message=_("{0} already exists").format(result.name))
            return stored
        self._update(item, state=DONE, percent=100, message="")
        hub.publish("library.changed", {"path": directory.client_path})
        for target in stored:
            hub.publish("track.updated", get_index().get(target))
            if batch.analyze:
                self._analyze(target)
        return stored

    @staticmethod
    def _analyze(target: Location):
        try:
            analysis_queue.submit([target])
        except ConnectionError as e:  # the agent went away; the song is imported anyway
            hub.publish("import.error", {"url": "", "message": str(e)})

    def _run(self, batch: Batch):
        imported: list[Location] = []
        for item in batch.items:
            try:
                imported.extend(self._item(batch, item))
                with self._lock:
                    self.done += 1
            except Exception as e:
                if not isinstance(e, ImportFailed):
                    logger.exception("Import of {0} failed", item.url)
                message = str(e) or type(e).__name__
                with self._lock:
                    self.failed += 1
                self._update(item, state=FAILED, message=message)
                hub.publish("import.error", {"url": item.url, "message": message})
            finally:
                with self._lock:
                    self.pending -= 1
                self._publish()
        if batch.playlist and imported:
            self._playlist(batch, imported)

    @staticmethod
    def _playlist(batch: Batch, tracks: list[Location]):
        name = file_name(batch.playlist, "playlist")[:-len(".mp3")] + ".m3u"
        playlist = batch.directory.child(name)
        try:
            if playlist.storage.exists(playlist.rel):
                playlists.append(playlist, tracks)
                hub.publish("playlist.changed", {"path": playlist.client_path})
            else:
                playlists.write(playlist, tracks)
                get_index().set_uploader(playlist, batch.user)
            hub.publish("library.changed", {"path": batch.directory.client_path})
        except Exception as e:
            logger.error("Playlist {0} could not be written: {1}", name, e)
            hub.publish("import.error", {"url": "", "message": str(e)})

    def shutdown(self):
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None


download_queue = DownloadQueue()
