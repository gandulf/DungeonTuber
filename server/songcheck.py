"""Checks the song suggestions of the AI assistant on YouTube: a song counts as found when one of the first videos YouTube lists for
"<title> <artist>" carries the words of its title. Searches go to a YouTube agent when one is connected (like the downloads), else
yt-dlp runs on the server.
"""
import logging
import re
import threading
import unicodedata

from core import ytimport
from core.ytimport import ImportFailed, RemoteEntry
from server import ytagent

logger = logging.getLogger(__file__)

MAX_CACHE = 1000

# words that say nothing about a song (kept in sync with web/src/lib/search.ts)
FILLER_WORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "at", "by", "for", "from", "with", "into", "is", "it", "its", "my", "your",
    "der", "die", "das", "den", "dem", "des", "ein", "eine", "einer", "eines", "einem", "einen", "und", "oder", "von", "vom", "zu", "zum",
    "zur", "im", "am", "auf", "mit", "fur", "aus", "bei",
    "le", "la", "les", "l", "un", "une", "de", "du", "et", "el", "los", "las", "y", "il", "lo", "gli", "e",
}

_cache: dict[tuple[str, str], dict] = {}
_cache_lock = threading.Lock()


def words(text: str) -> list[str]:
    """Lower case words without accents and punctuation."""
    text = unicodedata.normalize("NFD", text.lower().replace("ß", "ss"))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.findall(r"[^\W_]+", text)


def title_words(title: str) -> list[str]:
    """The words of a title that identify it: without an addition like "- Main Theme" or "(From the Film)" and without filler words."""
    base = re.split(r"\s[-–—|:]\s|[(\[]", title)[0]
    found = words(base) or words(title)
    return [word for word in found if word not in FILLER_WORDS] or found


def matches(title: str, video: RemoteEntry) -> bool:
    """Whether the video carries the words of the title (one word may be missing in titles of four words or more)."""
    wanted = title_words(title)
    if not wanted:
        return False
    present = set(words(f"{video.title} {video.uploader or ''}"))
    missing = sum(1 for word in wanted if word not in present)
    return missing <= len(wanted) // 4


def _search(queries: list[str]) -> list[list[RemoteEntry]]:
    if ytagent.available():
        try:
            return ytagent.search(queries)
        except ImportFailed as e:  # e.g. an agent of an older version that does not know the search
            logger.warning("The YouTube agent could not search: {0}", e)
    return ytimport.search(queries)


def _result(song: dict, videos: list[RemoteEntry]) -> dict:
    video = next((video for video in videos if matches(song["title"], video)), None)
    if video is None:
        return {"found": False}
    return {"found": True, "url": video.url, "title": video.title, "channel": video.uploader or "", "duration": video.duration}


def verify(songs: list[dict]) -> list[dict]:
    """For every song {"found": True, "url", "title", "channel", "duration"} of the matching video, {"found": False} when YouTube does
    not know it, or {"found": None} when YouTube could not be searched."""
    keys = [(song["title"].strip().lower(), (song.get("artist") or "").strip().lower()) for song in songs]
    with _cache_lock:
        results: list[dict | None] = [_cache.get(key) for key in keys]
    todo = [index for index, result in enumerate(results) if result is None]
    if todo:
        queries = [" ".join(filter(None, (songs[i]["title"], songs[i].get("artist")))) for i in todo]
        try:
            found = _search(queries)
        except ImportFailed as e:
            logger.warning("Unable to check the songs on YouTube: {0}", e)
            found = None
        with _cache_lock:
            for position, index in enumerate(todo):
                if found is None or position >= len(found):
                    results[index] = {"found": None}
                    continue
                results[index] = _result(songs[index], found[position])
                if len(_cache) >= MAX_CACHE:
                    _cache.clear()
                _cache[keys[index]] = results[index]
    return results
