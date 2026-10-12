"""Looks up the correct metadata of a song (title, artist, album, track number) in public databases:

- AcoustID (acoustid.org): identifies the recording by the audio fingerprint of the file. Needs the program fpcalc
  (Chromaprint) and a free application key from acoustid.org/new-application.
- MusicBrainz (musicbrainz.org): a text search by the current title and artist, or the file name ("Artist - Title").

Both return candidates; the user picks one, nothing is written here. MusicBrainz allows one request per second and asks for
a meaningful User-Agent.
"""
import json
import logging
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass

from core.tools import find_tool
from core.utils import get_current_version

logger = logging.getLogger(__file__)

MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2/recording"
ACOUSTID_URL = "https://api.acoustid.org/v2/lookup"
TIMEOUT = 15
MAX_CANDIDATES = 8
RETRY_DELAY = 1.5
# recordings found only on live albums, compilations or bootlegs rank below the studio recording
STUDIO_PENALTY = 15
# songs whose length differs more than this from the recording are probably another version
LENGTH_TOLERANCE = 10

_rate_lock = threading.Lock()
_last_request = 0.0


class MusicLookupError(Exception):
    """A database could not be asked (network, invalid key, missing fpcalc)."""


@dataclass
class Candidate:
    title: str
    artist: str
    album: str | None
    track: int | None
    year: str | None
    length: int | None  # seconds
    score: int  # 0-100, how sure the database is
    source: str  # "acoustid" or "musicbrainz"
    recording_id: str

    def to_dict(self) -> dict:
        return asdict(self)


def _user_agent() -> str:
    return f"DungeonTuber/{get_current_version()} ( https://github.com/gandulf/DungeonTuber )"


def _wait_for_turn():
    """MusicBrainz: at most one request per second."""
    global _last_request
    with _rate_lock:
        wait = 1.0 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _get_json(url: str, rate_limited: bool = False, form: dict | None = None) -> dict:
    """GET the url, or POST the form (fingerprints are too long for an url). A busy server (503) is asked once more."""
    body = urllib.parse.urlencode(form).encode("ascii") if form is not None else None
    request = urllib.request.Request(url, data=body, headers={"User-Agent": _user_agent(), "Accept": "application/json"})
    try:
        for attempt in range(2):
            if rate_limited:
                _wait_for_turn()
            try:
                with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code != 503 or attempt:
                    raise
                time.sleep(RETRY_DELAY)
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", {})
            detail = detail.get("message", "") if isinstance(detail, dict) else str(detail)
        except (ValueError, OSError):
            pass
        raise MusicLookupError(f"{urllib.parse.urlsplit(url).hostname}: HTTP {e.code} {detail}".strip()) from e
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise MusicLookupError(f"{urllib.parse.urlsplit(url).hostname}: {e}") from e


def _artist(credits: list[dict] | None) -> str:
    return "".join(f"{credit.get('name') or credit.get('artist', {}).get('name', '')}{credit.get('joinphrase', '')}"
                   for credit in credits or []).strip()


def _is_album(release: dict) -> bool:
    """An official studio album (not live, a compilation, a soundtrack of another kind or a bootleg)."""
    group = release.get("release-group") or {}
    return group.get("primary-type") == "Album" and not group.get("secondary-types") and release.get("status", "Official") == "Official"


def _best_release(releases: list[dict] | None) -> dict | None:
    """The original album of a recording rather than a compilation or single: official albums first, then the oldest."""
    def rank(release: dict):
        return (not _is_album(release), release.get("status", "Official") != "Official", release.get("date") or "9999")
    return min(releases, key=rank) if releases else None


def _track_number(release: dict) -> int | None:
    for medium in release.get("media") or []:
        for track in medium.get("track") or medium.get("tracks") or []:
            number = str(track.get("number") or track.get("position") or "")
            if number.isdigit():
                return int(number)
    return None


def _year(release: dict | None) -> str | None:
    return (release.get("date") or "")[:4] or None if release else None


def _length_penalty(candidate_length: int | None, length: float | None) -> int:
    if not candidate_length or not length:
        return 0
    return 30 if abs(candidate_length - length) > LENGTH_TOLERANCE else 0


def _dedupe(candidates: list[Candidate]) -> list[Candidate]:
    seen, result = set(), []
    # a fingerprint match is stronger evidence than a text match with the same score
    for candidate in sorted(candidates, key=lambda c: (-c.score, c.source != "acoustid")):
        key = (candidate.title.lower(), candidate.artist.lower(), (candidate.album or "").lower())
        if key not in seen:
            seen.add(key)
            result.append(candidate)
    return result[:MAX_CANDIDATES]


# --- MusicBrainz ----------------------------------------------------------------------------------------------------

def _quote(value: str) -> str:
    """A phrase for the Lucene query of MusicBrainz."""
    return '"' + re.sub(r'([\\"])', r"\\\1", value.strip()) + '"'


def guess_from_name(name: str) -> tuple[str | None, str]:
    """Artist and title from a file name like "Artist - Title (Official Video)"."""
    name = re.sub(r"\.mp3$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[\[(][^\])]*(official|video|audio|lyrics?|hd|hq|remaster(ed)?)[^\])]*[\])]", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^\d{1,3}[\s.\-_]+", "", name).replace("_", " ").strip()
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return artist.strip() or None, title.strip()
    return None, name


def search_musicbrainz(title: str | None, artist: str | None, name: str, length: float | None = None) -> list[Candidate]:
    """Recordings that match the title and artist of the song (from its tags, else from its file name)."""
    if not title:
        guessed_artist, title = guess_from_name(name)
        artist = artist or guessed_artist
    if not title:
        return []
    query = f"recording:{_quote(title)}" + (f" AND artist:{_quote(artist)}" if artist else "")
    url = f"{MUSICBRAINZ_URL}?{urllib.parse.urlencode({'query': query, 'fmt': 'json', 'limit': 15})}"
    result = _get_json(url, rate_limited=True)
    ranked = []
    for recording in result.get("recordings") or []:
        releases = recording.get("releases") or []
        release = _best_release(releases)
        seconds = round(recording["length"] / 1000) if recording.get("length") else None
        penalty = _length_penalty(seconds, length) + (0 if release and _is_album(release) else STUDIO_PENALTY)
        candidate = Candidate(
            title=recording.get("title", ""), artist=_artist(recording.get("artist-credit")),
            album=release.get("title") if release else None, track=_track_number(release) if release else None,
            year=_year(release), length=seconds, score=max(0, int(recording.get("score", 0)) - penalty), source="musicbrainz",
            recording_id=recording.get("id", ""))
        if candidate.title:
            ranked.append((candidate, len(releases)))
    # of equally good matches the recording on the most releases first: usually the original rather than a bootleg
    ranked.sort(key=lambda item: (-item[0].score, -item[1]))
    return _dedupe([candidate for candidate, _ in ranked])


# --- AcoustID ---------------------------------------------------------------------------------------------------------

def fpcalc_available() -> bool:
    return find_tool("fpcalc") is not None


def fingerprint(path: str) -> tuple[int, str]:
    """Duration and Chromaprint fingerprint of an audio file (the program fpcalc)."""
    fpcalc = find_tool("fpcalc")
    if fpcalc is None:
        raise MusicLookupError("fpcalc (Chromaprint) is not installed")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run([fpcalc, "-json", "--", path], capture_output=True, text=True, timeout=120, creationflags=flags)
        data = json.loads(result.stdout)
        return int(data["duration"]), data["fingerprint"]
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as e:
        raise MusicLookupError(f"fpcalc: {e}") from e


def _acoustid_release(group: dict, release: dict) -> dict:
    """A release of AcoustID in the shape of MusicBrainz (see _best_release)."""
    date = release.get("date")
    if isinstance(date, dict):
        date = "-".join(f"{date[part]:02d}" if part != "year" else str(date[part]) for part in ("year", "month", "day") if date.get(part))
    return {"title": release.get("title") or group.get("title"), "date": date or None, "media": release.get("mediums"),
            "release-group": {"primary-type": group.get("type"), "secondary-types": group.get("secondarytypes")}}


def lookup_acoustid(path: str, api_key: str, length: float | None = None) -> list[Candidate]:
    """Recordings whose fingerprint matches the file."""
    duration, print_ = fingerprint(path)
    result = _get_json(ACOUSTID_URL, form={"client": api_key, "meta": "recordings releases releasegroups compress",
                                           "duration": duration, "fingerprint": print_, "format": "json"})
    if result.get("status") != "ok":
        raise MusicLookupError("AcoustID: " + str((result.get("error") or {}).get("message", "lookup failed")))
    candidates = []
    for match in result.get("results") or []:
        for recording in match.get("recordings") or []:
            if not recording.get("title"):
                continue
            release = _best_release([_acoustid_release(group, release) for group in recording.get("releasegroups") or []
                                     for release in group.get("releases") or [{}]])
            seconds = round(recording["duration"]) if recording.get("duration") else None
            candidates.append(Candidate(
                title=recording["title"], artist=_artist(recording.get("artists")),
                album=release.get("title") if release else None, track=_track_number(release) if release else None,
                year=_year(release), length=seconds,
                score=max(0, round(float(match.get("score", 0)) * 100) - _length_penalty(seconds, length)), source="acoustid",
                recording_id=recording.get("id", "")))
    return _dedupe(candidates)


def lookup(path: str | None, title: str | None, artist: str | None, name: str, length: float | None,
           acoustid_key: str | None) -> dict:
    """The candidates of both databases, the best first, and the errors of a database that could not be asked."""
    candidates: list[Candidate] = []
    errors: list[str] = []
    if acoustid_key and path and fpcalc_available():
        try:
            candidates += lookup_acoustid(path, acoustid_key, length)
        except MusicLookupError as e:
            logger.warning("AcoustID lookup failed: %s", e)
            errors.append(str(e))
    try:
        candidates += search_musicbrainz(title, artist, name, length)
    except MusicLookupError as e:
        logger.warning("MusicBrainz search failed: %s", e)
        errors.append(str(e))
    return {"candidates": [candidate.to_dict() for candidate in _dedupe(candidates)], "errors": errors}
