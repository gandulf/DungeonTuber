import json
import os
import random
import sys
import traceback
import logging
from queue import Queue
from typing import Any
from os import PathLike
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from google import genai
from google.genai.errors import ClientError
from google.genai.types import UploadFileConfig, Content, Part, GenerateContentConfig, Schema, Type, ThinkingConfig

from logic import mp3
from logic.mp3 import Mp3Entry

from config.settings import AppSettings, SettingKeys, CATEGORY_MIN, CATEGORY_MAX, MusicCategory, CATEGORIES, get_music_categories, get_music_tags

logger = logging.getLogger("main")

def is_analyzed(file_path: str | PathLike[str] | Mp3Entry) -> bool:
    if isinstance(file_path, Mp3Entry):
        entry= file_path
    else:
        entry = mp3.parse_mp3(file_path)

    return (set(CATEGORIES) == set(entry.categories.keys()) and entry.summary is not None
            and entry.summary != "This is a mock summary." and not "Voxalyzer" in entry.summary)

def is_voxalyzed(file_path: str | PathLike[str] | Mp3Entry) -> bool:
    if isinstance(file_path, Mp3Entry):
        entry= file_path
    else:
        entry = mp3.parse_mp3(file_path)

    return entry.summary is not None and "Voxalyzer" in entry.summary

class Analyzer(QObject):
    error = Signal(object)
    result = Signal(Path)
    progress = Signal(str)

    workerQueue = Queue()

    def __init__(self, /, api_key: str, mock_mode: bool):
        super().__init__()
        self.api_key = api_key
        self.mock_mode = mock_mode
        self.threadpool = QThreadPool(maxThreadCount=8)

        self.result.connect(self._try_next_worker)
        self.error.connect(self._try_next_worker)

    def active_worker(self) -> int:
        return self.threadpool.activeThreadCount()

    def categories_to_string(self, categories: list[MusicCategory]):
        lines = []
        # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
        for cat in categories:
            lines.append(f"{cat.name}: {cat.description}\n {cat.levels}")

        return "\n\n".join(lines)

    def tags_to_string(self, data: dict[str, str]):
        lines = []
        # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
        for cat in data.items():
            lines.append(f"{cat[0]}: {cat[1]}")

        return "\n".join(lines)

    def analyze_mp3_mock(self, file_path: str | PathLike[str]) -> Any:
        """Generates a mock response simulating a call to the Gemini API."""
        logger.debug("--- MOCK MODE: Simulating analysis for {0} ---", file_path)

        selected_tags = random.sample(sorted(get_music_tags().keys()), random.randint(0, len(get_music_tags())))

        mock_categories = []
        for category in CATEGORIES:
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

    def analyze_mp3(self, file_path: str | PathLike[str]) -> Any:

        if not self.api_key:
            logger.warning(_("API Key is missing"))
            self.error.emit(_("API Key is missing"))
            return None

        try:
            client = genai.Client(api_key=self.api_key)

            with open(file_path, "rb") as file_content:
                myfile = client.files.upload(file=file_content, config=UploadFileConfig(mime_type="audio/mpeg"))

            prompt =_("GeminiUserPrompt").format(CATEGORY_MIN, CATEGORY_MAX, self.categories_to_string(get_music_categories()), self.tags_to_string(get_music_tags()))

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    Content(
                        parts=[
                            Part(text=prompt),
                            Part(myfile)
                        ]
                    )
                ],
                config=GenerateContentConfig(
                    thinking_config=ThinkingConfig(thinking_budget=0),  # Disables thinking
                    response_mime_type="application/json",
                    system_instruction=_("GeminiSystemPrompt").format(CATEGORY_MIN,CATEGORY_MAX),
                    response_schema=Schema(
                        type=Type.OBJECT,
                        properties={
                            "summary": Schema(
                                type=Type.STRING,
                                description=_("GeminiSummaryDescription"),
                            ),
                            "categories": Schema(
                                type=Type.ARRAY,
                                description=_("GeminiCategoriesDescription").format(CATEGORY_MIN,CATEGORY_MAX),
                                items=Schema(
                                    type=Type.OBJECT,
                                    properties={
                                        "category": Schema(type=Type.STRING),
                                        "scale": Schema(type=Type.INTEGER)
                                    },
                                    required=["category", "scale"],
                                ),
                            ),
                            "tags": Schema(
                                type=Type.ARRAY,
                                description=_("GeminiTagsDescription"),
                                items=Schema(
                                    type=Type.STRING
                                )
                            ),
                        },
                        required=["summary", "categories", "tags"],
                    ),
                ),
            )

            logger.debug(response.text)

            # Parse the JSON response and add tags

            return json.loads(response.text)
        except json.JSONDecodeError as e:
            traceback.print_exc()
            logger.error("Failed to decode JSON from response: {0}",e)
        except ClientError as e:
            self.error.emit(e.message)
            logger.error("Failed to analyze file: {0}",e)
        except Exception as e:
            traceback.print_exc()
            logger.error("Failed to analyze file: {0}",e)
        return None

    def process(self, file_path: str | PathLike[str]) -> bool:
        try:

            logger.debug("Analyzing {0}", file_path)

            if Path(file_path).is_dir():
                return self.process_directory(file_path)
            else:
                return self._process_file(file_path)
        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while analyzing: {0}",e)
            return False
    def _process_file(self,file_path: PathLike[str]) -> bool:
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
            logger.error("An error occurred while fetching next worker: {0}",e)
            return False

    def process_directory(self, directory_path: str | PathLike[str]) -> bool:
        logger.debug("Processing {0}...",directory_path)
        files = mp3.list_mp3s(directory_path)

        result = False
        # Parses all MP3 files in a given directory.
        for filename in files:
            file_path =Path(os.path.join(directory_path, filename))
            result = self._process_file(file_path) or result
        return result

class Worker(QRunnable):
    analyzer: Analyzer

    def __init__(self, file_path: str | PathLike[str], analyzer: Analyzer):
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

    def process_file(self, file_path: str | PathLike[str]):
        logger.debug("Processing {0}...", file_path)

        if AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool) and is_analyzed(file_path):
            self.analyzer.progress.emit(_("Skipping already analyzed file {0}").format(Path(file_path).name))
            logger.debug("Skipping already analyzed file {0}", Path(file_path).name)
            return

        self.analyzer.progress.emit(_("Analyzing {0}...").format(Path(file_path).name))

        if self.analyzer.mock_mode:
            response_data = self.analyzer.analyze_mp3_mock(file_path)
        else:
            response_data = self.analyzer.analyze_mp3(file_path)

        if not response_data:
            return

        # add tags
        try:
            summary = response_data.get("summary")
            categories = response_data.get("categories")
            tags = response_data.get("tags")

            if summary and categories:
                mp3.add_tags_to_mp3(file_path, summary, categories, tags)
                mp3.print_mp3_tags(file_path)  # Print tags after adding them
            else:
                logger.warning("Could not find summary or categories for {0}.", file_path)

            self.analyzer.progress.emit(_("Processed {0}.").format(Path(file_path).name))
        except Exception as e:
            traceback.print_exc()
            logger.error("An error occurred while adding tags to {0}: {1}", file_path,e)
