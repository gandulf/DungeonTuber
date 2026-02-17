import json
import os
import random
import sys
import traceback
import logging
import urllib.request
import urllib.error
from abc import abstractmethod

from queue import Queue
from typing import Any
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from logic.mp3 import Mp3Entry, parse_mp3, update_categories_and_tags, print_mp3_tags, list_mp3s

from config.settings import AppSettings, SettingKeys, CATEGORY_MIN, CATEGORY_MAX, MusicCategory, get_music_tags, get_category_keys

logger = logging.getLogger("main")


def is_analyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    if isinstance(file_path, Mp3Entry):
        entry = file_path
    else:
        entry = parse_mp3(file_path)

    return (set(get_category_keys()) == set(entry.categories.keys()) and entry.summary is not None
            and entry.summary != "This is a mock summary." and not "Voxalyzer" in entry.summary)


def is_voxalyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    if isinstance(file_path, Mp3Entry):
        entry = file_path
    else:
        entry = parse_mp3(file_path)

    return entry.summary is not None and "Voxalyzer" in entry.summary


def categories_to_string(categories: list[MusicCategory]) -> str:
    lines = []
    # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
    for cat in categories:
        lines.append(f"{cat.name}: {cat.description}\n {cat.levels}")

    return "\n\n".join(lines)


def tags_to_string(data: dict[str, str]) -> str:
    lines = []
    # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
    for cat in data.items():
        lines.append(f"{cat[0]}: {cat[1]}")

    return "\n".join(lines)


class Analyzer(QObject):
    error = Signal(object)
    result = Signal(Path)
    progress = Signal(str)

    workerQueue = Queue()

    @classmethod
    def get_analyzer(cls):
        baseUrl = AppSettings.value(SettingKeys.VOXALYZER_URL, None, type=str)

        if baseUrl is None or baseUrl == "":
            return MockAnalyzer()
        else:
            return VoxalyzerAnalyzer()

    def __init__(self):
        super().__init__()

        self.threadpool = QThreadPool(maxThreadCount=8)

        self.result.connect(self._try_next_worker)
        self.error.connect(self._try_next_worker)

    def active_worker(self) -> int:
        return self.threadpool.activeThreadCount()

    @abstractmethod
    def analyze_mp3(self, file_path: PathLike[str]) -> Any:
        pass

    def process(self, file_path: PathLike[str]) -> bool:
        try:

            logger.debug("Analyzing {0}", file_path)

            if Path(file_path).is_dir():
                return self.process_directory(file_path)
            else:
                return self._process_file(file_path)
        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while analyzing: {0}", e)
            return False

    def _process_file(self, file_path: PathLike[str]) -> bool:
        worker = Worker(file_path, self)
        worker.setAutoDelete(True)
        return self._try_worker(worker)

    def _try_worker(self, worker):
        success = self.threadpool.tryStart(worker)
        if success:
            logger.debug("Success: {0}", success)
            return True
        else:
            logger.info("Queue full waiting")
            self.workerQueue.put(worker)
            return False

    def _try_next_worker(self):
        try:
            if not self.workerQueue.empty():
                logger.info("Trying next worker")
                worker = self.workerQueue.get_nowait()
                return self._try_worker(worker)
        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while fetching next worker: {0}", e)
            return False

    def process_directory(self, directory_path: PathLike[str]) -> bool:
        logger.debug("Processing {0}...", directory_path)
        files = list_mp3s(directory_path)

        result = False
        # Parses all MP3 files in a given directory.
        for filename in files:
            file_path = Path(os.path.join(directory_path, filename))
            result = self._process_file(file_path) or result
        return result


class MockAnalyzer(Analyzer):

    def analyze_mp3(self, file_path: PathLike[str]) -> Any:
        logger.debug("--- MOCK MODE: Simulating analysis for {0} ---", file_path)

        selected_tags = random.sample(sorted(get_music_tags().keys()), random.randint(0, len(get_music_tags())))

        mock_categories = []
        for category in get_category_keys():
            mock_categories.append({
                "category": category,
                "scale": random.randint(CATEGORY_MIN, CATEGORY_MAX)
            })

        mock_response = {
            "summary": "This is a mock summary.",
            "categories": mock_categories,
            "tags": selected_tags
        }

        return mock_response


class VoxalyzerAnalyzer(Analyzer):

    def analyze_mp3(self, file_path: PathLike[str]) -> Any:
        baseUrl: str = AppSettings.value(SettingKeys.VOXALYZER_URL, "", type=str)
        if not baseUrl or baseUrl == "":
            logger.error("Voxalyzer URL not set.")
            return None

        if baseUrl.endswith("/"):
            url = f"{baseUrl}analyze"
        else:
            url = f"{baseUrl}/analyze"

        logger.debug(f"Sending request to {url} for file {file_path}")

        try:
            with open(file_path, 'rb') as f:
                file_content = f.read()

            req = urllib.request.Request(url, data=file_content, method='POST')
            req.add_header('Content-Type', 'application/octet-stream')

            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    response_body = response.read()
                    return json.loads(response_body)
                else:
                    logger.error(f"Error: {response.status} - {response.reason}")
                    return None

        except urllib.error.URLError as e:
            logger.error(f"URLError: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"An error occurred: {e}")
            return None


class Worker(QRunnable):
    analyzer: Analyzer

    def __init__(self, file_path: PathLike[str], analyzer: Analyzer):
        super(Worker, self).__init__()
        self.file_path = file_path
        self.analyzer = analyzer

        logger.debug("Worker initialized")

    def run(self):
        logger.debug("Worker run")
        try:
            self.process_file(self.file_path)
        except Exception:
            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.analyzer.error.emit(value)
        else:
            self.analyzer.result.emit(self.file_path)  # Return the result of the processing

    def process_file(self, file_path: PathLike[str]):
        logger.debug("Processing {0}...", file_path)

        if AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool) and is_analyzed(file_path):
            self.analyzer.progress.emit(_("Skipping already analyzed file {0}").format(Path(file_path).name))
            logger.debug("Skipping already analyzed file {0}", Path(file_path).name)
            return

        self.analyzer.progress.emit(_("Analyzing {0}...").format(Path(file_path).name))

        response_data = self.analyzer.analyze_mp3(file_path)

        if not response_data:
            return

        # add tags
        try:
            summary = response_data.get("summary")
            categories = response_data.get("categories")
            tags = response_data.get("tags")

            if categories:
                update_categories_and_tags(file_path, summary, categories, tags)
                print_mp3_tags(file_path)  # Print tags after adding them
            else:
                logger.warning("Could not find categories for {0}.", file_path)

            self.analyzer.progress.emit(_("File {0} processed.").format(Path(file_path).name))
        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while adding tags to {0}: {1}", file_path, e)
