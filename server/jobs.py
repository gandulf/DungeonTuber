"""Background jobs (thread pools) reporting through the event hub: music analysis and importing remote tracks."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from core.analyzer import analyze_file, get_backend, is_analyzed
from core.i18n import _
from core.settings import AppSettings, SettingKeys
from server.events import hub
from server.index import entry_from_dict, get_index
from server.paths import Location

logger = logging.getLogger(__file__)


def collect_locations(location: Location) -> list[Location]:
    """The mp3 files to process for a file or a directory (recursive)."""
    entry = location.storage.stat(location.rel)
    if not entry.is_dir:
        return [location]
    return sorted((Location(location.root, e.path) for e in location.storage.walk(location.rel) if e.path.lower().endswith(".mp3")),
                  key=lambda item: item.rel)


class AnalysisQueue:
    MAX_WORKERS = 8

    def __init__(self):
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()
        self.pending = 0
        self.done = 0
        self.failed = 0

    def status(self) -> dict:
        with self._lock:
            return {"pending": self.pending, "done": self.done, "failed": self.failed}

    def submit(self, locations: list[Location]) -> int:
        backend = get_backend()
        files = [file for location in locations for file in collect_locations(location)]
        with self._lock:
            if self.pending == 0:
                self.done = self.failed = 0
            self.pending += len(files)
        if self._executor is None:
            self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="analysis")
        for file in files:
            self._executor.submit(self._run, file, backend)
        hub.publish("analysis.status", self.status())
        return len(files)

    @staticmethod
    def _analyze(location: Location, backend, progress) -> bool:
        if location.root.is_local:
            return analyze_file(location.local_path, backend, progress=progress)

        # remote: analyze a temporary copy; the result is stored in the metadata database only
        index = get_index()
        data = index.get(location)
        if data is None:
            return False
        if AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool) and is_analyzed(entry_from_dict(data)):
            progress(_("Skipping already analyzed file {0}").format(location.name))
            return False
        progress(_("Analyzing {0}...").format(location.name))
        with location.storage.local_file(location.rel) as tmp:
            response = backend.analyze_mp3(tmp)
        if not response or not response.get("categories"):
            return False
        index.update(location, {"summary": response.get("summary"), "categories": response["categories"], "tags": response.get("tags")})
        progress(_("File {0} processed.").format(location.name))
        return True

    def _run(self, location: Location, backend):
        try:
            changed = self._analyze(location, backend, lambda message: hub.publish("analysis.progress", {"message": message}))
            if changed:
                if location.root.is_local:
                    get_index().invalidate(location)
                hub.publish("track.updated", get_index().get(location))
            with self._lock:
                self.done += 1
            hub.publish("analysis.result", {"id": location.id, "changed": changed})
        except Exception as e:
            logger.error("Analysis of {0} failed: {1}", location, e)
            with self._lock:
                self.failed += 1
            hub.publish("analysis.error", {"id": location.id, "message": str(e)})
        finally:
            with self._lock:
                self.pending -= 1
            hub.publish("analysis.status", self.status())

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


class ImportQueue:
    """Reads the tags of remote tracks that are new to the metadata database (needs a download each)."""
    MAX_WORKERS = 4

    def __init__(self):
        self._executor: ThreadPoolExecutor | None = None
        self._lock = threading.Lock()

    def submit(self, locations: list[Location]):
        index = get_index()
        with self._lock:
            if self._executor is None:
                self._executor = ThreadPoolExecutor(max_workers=self.MAX_WORKERS, thread_name_prefix="import")
            for location in locations:
                if index.begin_import(location):
                    self._executor.submit(self._run, location)

    @staticmethod
    def _run(location: Location):
        index = get_index()
        try:
            data = index.import_remote(location)
            if data is not None:
                hub.publish("track.updated", data)
        except Exception as e:
            logger.error("Import of {0} failed: {1}", location, e)
        finally:
            index.end_import(location)

    def shutdown(self):
        with self._lock:
            if self._executor is not None:
                self._executor.shutdown(wait=False, cancel_futures=True)
                self._executor = None


analysis_queue = AnalysisQueue()
import_queue = ImportQueue()
