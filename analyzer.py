import json
import os
import random
import sys
import traceback
import logging
from queue import Queue
from typing import Any

from PySide6.QtCore import QObject, Signal, QRunnable, QThreadPool

from os import PathLike
from google import genai
from google.genai.errors import ClientError
from google.genai.types import UploadFileConfig, Content, Part, GenerateContentConfig, Schema, Type, ThinkingConfig

import mp3
from mp3 import Mp3Entry
from pathlib import Path

from settings import settings, SettingKeys, MUSIC_CATEGORIES, MUSIC_TAGS, CATEGORY_MIN, CATEGORY_MAX, MusicCategory

logger = logging.getLogger("main")

def is_analyzed(file_path: str | PathLike[str] | Mp3Entry) -> bool:
    categories = MUSIC_CATEGORIES.keys()

    if isinstance(file_path, Mp3Entry):
        entry= file_path
    else:
        entry = mp3.parse_mp3(file_path)

    return set(categories) == set(entry.categories.keys()) and entry.summary != "This is a mock summary." and not entry.summary.__contains__("Voxalyzer")

def is_voxalyzed(file_path: str | PathLike[str] | Mp3Entry) -> bool:
    if isinstance(file_path, Mp3Entry):
        entry= file_path
    else:
        entry = mp3.parse_mp3(file_path)

    return entry.summary.__contains__("Voxalyzer")

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

    def categories_to_string(self, list: dict[str, MusicCategory]):
        lines = []
        # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
        for key,cat in list.items():
            lines.append(f"{cat.name}: {cat.description}\n {cat.levels}")

        return "\n\n".join(lines)

    def tags_to_string(self, data: dict[str, str]):
        lines = []
        # Iteriere über die Einträge und zähle mit, um Absätze zu setzen
        for i, (cat) in enumerate(data.items()):
            lines.append(f"{cat[0]}: {cat[1]}")

        return "\n".join(lines)

    def analyze_mp3_mock(self, file_path: str | PathLike[str]) -> Any:
        """Generates a mock response simulating a call to the Gemini API."""
        logger.debug(f"--- MOCK MODE: Simulating analysis for {file_path} ---")

        categories = MUSIC_CATEGORIES.keys()

        selected_tags = random.sample(sorted(MUSIC_TAGS.keys()), random.randint(0, len(MUSIC_TAGS)))

        mock_categories = []
        for category in categories:
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
            logger.warning("API Key is missing")
            return None

        try:
            client = genai.Client(api_key=self.api_key)

            with open(file_path, "rb") as file_content:
                myfile = client.files.upload(file=file_content, config=UploadFileConfig(mime_type="audio/mpeg"))

            prompt = f"""Aufgabe:
Ordne das folgende Musikstück für die Nutzung im Rollenspiel „Das Schwarze Auge“ ein.
Bewerte das Stück anhand der untenstehenden Kategorien jeweils mit einem Wert von {CATEGORY_MIN} bis {CATEGORY_MAX}.

Hier ist die Liste der Kategorien nach denen du das Musikstück bewerten sollst mit zugehörigen Beschreibungen:
{self.categories_to_string(MUSIC_CATEGORIES)}

Danach vergib noch ein paar Tags aus folgender Liste, die am besten passen. Hier ist keine Skala notwendig:
{self.tags_to_string(MUSIC_TAGS)}
"""
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
                    system_instruction=f"""Du bist ein erfahrener Hörer von Fantasy-, Film- und Rollenspielmusik.
Du bewertest Musik so, wie sie von einem durchschnittlichen Hörer wahrgenommen wird,
nicht technisch und nicht analytisch, sondern emotional und szenisch.

Deine Bewertungen müssen über viele hundert Tracks hinweg konsistent bleiben.
Eine 3 bedeutet immer dasselbe, egal welcher Track zuvor bewertet wurde.
Werte sollen relativ zueinander sinnvoll verteilt sein (nicht alles {CATEGORY_MIN} oder {CATEGORY_MAX}).
Nutze die gesamte Skala von {CATEGORY_MIN} bis {CATEGORY_MAX}, wenn passend.
Du hältst dich strikt an die vorgegebenen Kategorien, Tags und deren Beschreibungen.
Du gibst ausschließlich JSON zurück, ohne zusätzliche Erklärungen.""",
                    response_schema=Schema(
                        type=Type.OBJECT,
                        properties={
                            "summary": Schema(
                                type=Type.STRING,
                                description="Eine kurze Zusammenfassung des Musikstückes bezüglich Stimmung (ca. 20 Wörter).",
                            ),
                            "categories": Schema(
                                type=Type.ARRAY,
                                description=f"Liste alle Kategorien auf und bewerte sie auf eine Skala von {CATEGORY_MIN} bis {CATEGORY_MAX}",
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
                                description="Eine Liste von Tags die auf das Musikstück am besten zutreffen.",
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
            logger.error(f"Failed to decode JSON from response: {e}")
        except ClientError as e:
            self.error.emit(e.message)
            logger.error(f"Failed to analyze file: {e}")
        except Exception as e:
            traceback.print_exc()
            logger.error(f"Failed to analyze file: {e}")

    def process(self, file_path: str | PathLike[str]) -> bool:
        try:

            logger.debug(f"Analyzing {file_path}")

            if Path(file_path).is_dir():
                self.process_directory(file_path)
            else:
                return self._process_file(file_path)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"An error occurred while analyzing: {e}")
            return False
    def _process_file(self,file_path: PathLike[str]) -> bool:
        worker = Worker(file_path, self)
        worker.setAutoDelete(True)
        return self._try_worker(worker)

    def _try_worker(self, worker):
        success = self.threadpool.tryStart(worker)
        if success:
            logger.debug(f"Success: {success}")
            return True
        else:
            logger.info(f"Queue full waiting")
            self.workerQueue.put(worker)
            return False

    def _try_next_worker(self):
        try:
            if not self.workerQueue.empty():
                logger.info(f"Trying next worker")
                worker = self.workerQueue.get_nowait()
                return self._try_worker(worker)
        except Exception as e:
            traceback.print_exc()
            logger.error(f"An error occurred while fetching next worker: {e}")
            return False

    def process_directory(self, directory_path: str | PathLike[str]):
        logger.debug(f"Processing {directory_path}...")
        files = mp3.list_mp3s(directory_path)

        # Parses all MP3 files in a given directory.
        for filename in files:
            file_path =Path(os.path.join(directory_path, filename))
            self._process_file(file_path)

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
        logger.debug(f"Processing {file_path}...")

        if (settings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool) and is_analyzed(file_path)):
            self.analyzer.progress.emit(f"Skipping already analyzed file {Path(file_path).name}")
            logger.debug(f"Skipping already analyzed file {Path(file_path).name}")
            return

        self.analyzer.progress.emit(f"Analyzing {Path(file_path).name}...")

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
                logger.warning(f"Could not find summary or categories for {file_path}.")

            self.analyzer.progress.emit(f"Processed {Path(file_path).name}.")
        except Exception as e:
            traceback.print_exc()
            logger.error(f"An error occurred while adding tags to {file_path}: {e}")
