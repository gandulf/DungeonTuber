"""Background analysis jobs (thread pool) reporting through the event hub."""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from core.analyzer import analyze_file, collect_files, get_backend
from server.events import hub
from server.index import get_index
from server.paths import path_to_id

logger = logging.getLogger(__file__)


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

    def submit(self, paths: list[Path]) -> int:
        backend = get_backend()
        files = [file for path in paths for file in collect_files(path)]
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

    def _run(self, file: Path, backend):
        try:
            changed = analyze_file(file, backend, progress=lambda message: hub.publish("analysis.progress", {"message": message}))
            if changed:
                get_index().invalidate(file)
                track = get_index().get(file)
                hub.publish("track.updated", track)
            with self._lock:
                self.done += 1
            hub.publish("analysis.result", {"id": path_to_id(file), "changed": changed})
        except Exception as e:
            logger.error("Analysis of {0} failed: {1}", file, e)
            with self._lock:
                self.failed += 1
            hub.publish("analysis.error", {"id": path_to_id(file), "message": str(e)})
        finally:
            with self._lock:
                self.pending -= 1
            hub.publish("analysis.status", self.status())

    def shutdown(self):
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None


analysis_queue = AnalysisQueue()
