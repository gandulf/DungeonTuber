"""Music analysis (the backends themselves are the Voxalyzer agents, see server/voxagent.py) without any threading framework.

Callers decide how to run ``analyze_file`` (thread pool, asyncio.to_thread, ...).
"""
import logging
from os import PathLike
from pathlib import Path
from typing import Callable

from core.i18n import _
from core.mp3 import Mp3Entry, parse_mp3, update_categories_and_tags, print_mp3_tags, list_mp3s
from core.settings import AppSettings, SettingKeys, MusicCategory, get_category_keys

logger = logging.getLogger(__file__)

# Seconds to wait for an analysis response; analyzing a long track can take a while.
ANALYZE_TIMEOUT = 600


def _entry(file_path: PathLike[str] | Mp3Entry) -> Mp3Entry | None:
    return file_path if isinstance(file_path, Mp3Entry) else parse_mp3(file_path)


def is_analyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    entry = _entry(file_path)
    if entry is None:
        return False

    return (set(get_category_keys()) == set(entry.categories.keys()) and entry.summary is not None
            and "Voxalyzer" not in entry.summary)


def is_voxalyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    entry = _entry(file_path)
    return entry is not None and entry.summary is not None and "Voxalyzer" in entry.summary


def categories_to_string(categories: list[MusicCategory]) -> str:
    return "\n\n".join(f"{cat.name}: {cat.description}\n {cat.levels}" for cat in categories)


def tags_to_string(data: dict[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in data.items())


class AnalyzerBackend:
    """Turns an mp3 file into ``{"summary": str, "categories": {...}, "tags": [...], "genres": [...], "bpm": int}``."""

    name = "base"

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        raise NotImplementedError


def collect_files(path: PathLike[str]) -> list[Path]:
    """The mp3 files to analyze for a file or a directory (recursive)."""
    path = Path(path)
    if path.is_dir():
        return [path / name for name in list_mp3s(path)]
    return [path]


def analyze_file(file_path: PathLike[str], backend: AnalyzerBackend, progress: Callable[[str], None] = lambda message: None,
                 skip_analyzed: bool | None = None) -> bool:
    """Analyzes one file and writes summary/categories/tags back. Returns True if the file was updated.

    Raises on backend/network errors so callers can report them.
    """
    logger.debug("Processing {0}...", file_path)
    name = Path(file_path).name

    if skip_analyzed is None:
        skip_analyzed = AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool)

    if skip_analyzed and is_analyzed(file_path):
        progress(_("Skipping already analyzed file {0}").format(name))
        logger.debug("Skipping already analyzed file {0}", name)
        return False

    progress(_("Analyzing {0}...").format(name))

    response_data = backend.analyze_mp3(file_path)
    if not response_data:
        return False

    categories = response_data.get("categories")
    if not categories:
        logger.warning("Could not find categories for {0}.", file_path)
        return False

    update_categories_and_tags(file_path, response_data.get("summary"), categories, response_data.get("tags"), response_data.get("genres"),
                               response_data.get("bpm"))
    print_mp3_tags(file_path)

    progress(_("File {0} processed.").format(name))
    return True


__all__ = ["is_analyzed", "is_voxalyzed", "categories_to_string", "tags_to_string", "AnalyzerBackend", "collect_files", "analyze_file"]
