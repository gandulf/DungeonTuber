"""Imports the audio of YouTube links (single videos and playlists) as tagged mp3 files, using yt-dlp."""
import io
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlsplit

from core.i18n import _
from core.mp3 import update_mp3_album, update_mp3_artist, update_mp3_chapters, update_mp3_cover_data, update_mp3_source, update_mp3_title
from core.settings import AppSettings, SettingKeys
from core.tools import ensure_tool, find_tool
from core.utils import get_user_data_dir

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]

ALLOWED_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")  # and their subdomains
DEFAULT_MAX_MINUTES = 240
MAX_NAME = 150
COOKIES_NAME = "youtube-cookies.txt"
PROXY_ENV = "DT_YT_PROXY"
PROXY_SCHEMES = ("http", "https", "socks4", "socks4a", "socks5", "socks5h")
MAX_COOKIES_BYTES = 2 * 1024 * 1024
COOKIE_DOMAINS = ("youtube.com", "youtube-nocookie.com", "google.com")  # nothing else of an exported browser session is kept


class ImportFailed(Exception):
    """A link that cannot be imported; the message is meant for the user."""


@dataclass
class RemoteEntry:
    url: str
    title: str
    duration: int | None = None
    uploader: str | None = None
    chapters: int | None = None  # known for single videos only


@dataclass
class Resolved:
    title: str
    is_playlist: bool
    entries: list[RemoteEntry] = field(default_factory=list)
    has_video: bool = False  # a video link of a playlist: both the video alone and the whole playlist can be imported


@dataclass
class Downloaded:
    path: Path  # the finished mp3, tags included
    name: str  # file name suggested for the library
    title: str
    parts: list["Downloaded"] = field(default_factory=list)  # one song per chapter when the video was split (then `path` is unused)


def check_url(url: str) -> str:
    """The cleaned link if it points to YouTube; yt-dlp supports far more sites (and local files) than we want to expose."""
    url = (url or "").strip()
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not any(host == allowed or host.endswith("." + allowed) for allowed in ALLOWED_HOSTS):
        raise ImportFailed(_("Only YouTube links can be imported"))
    return url


def file_name(title: str, fallback: str = "track") -> str:
    """A file name without characters the file systems of the library storages reject."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title or "")
    name = re.sub(r"\s+", " ", name).strip(" .")[:MAX_NAME].strip(" .")
    return (name or fallback) + ".mp3"


def _is_playlist(url: str) -> bool:
    """A playlist link, also a video link of a playlist (`watch?v=..&list=..`); auto generated mixes (list=RD..) are endless, so only their video counts."""
    parts = urlsplit(url)
    if parts.path.rstrip("/").endswith("/playlist"):
        return True
    return any(not value.startswith("RD") for value in parse_qs(parts.query).get("list", []))


def _has_video(url: str) -> bool:
    """A link of a video inside a (real) playlist."""
    query = parse_qs(urlsplit(url).query)
    return bool(query.get("v")) and any(not value.startswith("RD") for value in query.get("list", []))


def _runtime(progress: Progress | None) -> dict:
    """yt-dlp needs a JavaScript runtime for YouTube: deno or node when installed, otherwise deno is downloaded."""
    for name in ("deno", "node"):
        path = find_tool(name)
        if path:
            return {name: {"path": path}}
    return {"deno": {"path": ensure_tool("deno", progress)}}


_cookies_override: dict = {}  # set by an agent on a user's own machine: its own cookies.txt or the cookies of a browser profile


def use_cookies(file: str | None = None, browser: str | None = None):
    """Takes the cookies from a file or a browser (e.g. "firefox") instead of the cookies.txt of the server settings."""
    _cookies_override.clear()
    if browser:
        _cookies_override["cookiesfrombrowser"] = (browser,)
    elif file:
        _cookies_override["cookiefile"] = str(file)


def cookies_file() -> Path:
    """The cookies.txt of a signed-in YouTube session, next to settings.json (YouTube blocks anonymous downloads from many servers)."""
    path = AppSettings.path
    return (path.parent if path else get_user_data_dir()) / COOKIES_NAME


def clean_cookies(text: str) -> str:
    """The YouTube cookies of a Netscape cookies.txt export; everything else (other sites) is dropped."""
    if len(text.encode("utf-8")) > MAX_COOKIES_BYTES:
        raise ImportFailed(_("The cookies file is too large"))
    lines = []
    for line in text.splitlines():
        fields = line.split("\t")
        domain = fields[0].removeprefix("#HttpOnly_").lstrip(".").lower()
        if len(fields) == 7 and any(domain == allowed or domain.endswith("." + allowed) for allowed in COOKIE_DOMAINS):
            lines.append("\t".join(fields))
    if not lines:
        raise ImportFailed(_("No YouTube cookies found in this file (expected a cookies.txt in Netscape format)"))
    return "# Netscape HTTP Cookie File\n" + "\n".join(lines) + "\n"


def save_cookies(text: str):
    content = clean_cookies(text)
    path = cookies_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8", newline="\n") as out:
        out.write(content)


def delete_cookies():
    cookies_file().unlink(missing_ok=True)


def stored_proxy() -> str:
    return (AppSettings.value(SettingKeys.YOUTUBE_PROXY, "", type=str) or "").strip()


def proxy_url() -> str:
    """The proxy for all yt-dlp requests: the setting, otherwise the DT_YT_PROXY environment variable, otherwise none."""
    return stored_proxy() or os.environ.get(PROXY_ENV, "").strip()


def check_proxy(value: str) -> str:
    """The proxy url (http, https, socks4, socks4a, socks5 or socks5h with optional user:password@) or ImportFailed."""
    value = value.strip()
    try:
        parts = urlsplit(value)
        valid = parts.scheme in PROXY_SCHEMES and bool(parts.hostname) and parts.port != 0
    except ValueError:
        valid = False
    if not valid:
        raise ImportFailed(_("Invalid proxy address (expected e.g. http://user:password@host:port or socks5://host:port)"))
    return value


def _options(progress: Progress | None, **extra) -> dict:
    options = {"quiet": True, "no_warnings": True, "noprogress": True, "js_runtimes": _runtime(progress), **extra}
    if proxy_url():
        options["proxy"] = proxy_url()
    if _cookies_override:
        options.update(_cookies_override)
    elif cookies_file().is_file():
        options["cookiefile"] = str(cookies_file())
    return options


def resolve(url: str, progress: Progress | None = None, whole: bool | None = None) -> Resolved:
    """Looks up a link without downloading it: one entry for a video, one per video for a playlist.
    `whole` chooses between the playlist and just the video for a video link of a playlist (default: the playlist)."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = check_url(url)
    video = _has_video(url)
    playlist = _is_playlist(url) if whole is None or not video else whole
    try:
        with YoutubeDL(_options(progress, extract_flat="in_playlist", skip_download=True, noplaylist=not playlist)) as ydl:
            info = ydl.extract_info(url, download=False)
    except DownloadError as e:
        raise ImportFailed(_clean_error(e))
    if not info:
        raise ImportFailed(_("Nothing found at this link"))
    if info.get("_type") == "playlist":
        entries = [_entry(item) for item in info.get("entries") or [] if item]
        entries = [entry for entry in entries if entry]
        if not entries:
            raise ImportFailed(_("The playlist has no videos that can be imported"))
        return Resolved(info.get("title") or "", True, entries, video)
    entry = _entry(info) or RemoteEntry(url, info.get("title") or url)
    entry.chapters = len(info.get("chapters") or [])
    return Resolved(info.get("title") or "", False, [entry], video)


def _entry(item: dict) -> RemoteEntry | None:
    url = item.get("webpage_url") or item.get("url") or ""
    if "://" not in url and item.get("id"):
        url = f"https://www.youtube.com/watch?v={item['id']}"
    try:
        url = check_url(url)
    except ImportFailed:
        return None
    return RemoteEntry(url, item.get("title") or url, item.get("duration"), item.get("channel") or item.get("uploader"))


def _clean_error(error: Exception) -> str:
    message = re.sub(r"\x1b\[[0-9;]*m", "", str(error))  # colors
    if "Sign in to confirm" in message:
        if _cookies_override:
            return _("YouTube rejected the cookies of the download agent. Sign in to YouTube on the agent machine or export fresh cookies there.")
        if cookies_file().is_file():
            return _("YouTube rejected the stored cookies. Export a fresh cookies.txt and upload it again in the settings.")
        return _("YouTube asks for a sign-in because it treats this server as a bot. An administrator can upload a cookies.txt under Settings > Library.")
    return re.sub(r"^ERROR:\s*(\[[^\]]+\]\s*[\w-]+:\s*)?", "", message).strip() or type(error).__name__


def _artist(info: dict) -> str | None:
    artist = info.get("artist") or info.get("creator") or info.get("channel") or info.get("uploader")
    return re.sub(r"\s+-\s+Topic$", "", artist) if artist else None


def _cover(directory: Path, video_id: str) -> tuple[bytes, str] | None:
    """The thumbnail as jpeg (youtube serves webp, which not every player reads in id3 tags)."""
    from PIL import Image

    for image in directory.glob(f"{video_id}.*"):
        if image.suffix.lower() in (".webp", ".jpg", ".jpeg", ".png"):
            try:
                with Image.open(image) as picture:
                    out = io.BytesIO()
                    picture.convert("RGB").save(out, format="JPEG", quality=90)
                return out.getvalue(), "image/jpeg"
            except OSError as e:
                logger.warning("Unreadable thumbnail {0}: {1}", image, e)
    return None


def _chapters(info: dict) -> list[dict]:
    return [{"title": chapter.get("title") or "", "time": int(float(chapter.get("start_time") or 0) * 1000), "light": None}
            for chapter in info.get("chapters") or []]


def download(url: str, directory: Path, progress: Progress | None = None, max_minutes: int = DEFAULT_MAX_MINUTES,
             album: str | None = None, percent: Callable[[int], None] | None = None, split: bool = False) -> Downloaded:
    """Downloads one video as mp3 into `directory` (a scratch folder of the caller) and writes title, artist, cover, chapters and the source.
    With `split` a video with chapters becomes one tagged mp3 per chapter (`Downloaded.parts`) instead of one file."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    url = check_url(url)

    def check(info, *, incomplete=False):  # rejects before anything is downloaded
        if info.get("is_live") or info.get("live_status") in ("is_live", "is_upcoming"):
            raise ImportFailed(_("Live streams cannot be imported"))
        if info.get("duration") and info["duration"] > max_minutes * 60:
            raise ImportFailed(_("Longer than {0} minutes: {1}").format(max_minutes, info.get("title") or url))

    def hook(status):
        total = status.get("total_bytes") or status.get("total_bytes_estimate")
        if percent and status.get("status") == "downloading" and total:
            percent(min(100, int(status.get("downloaded_bytes", 0) * 100 / total)))

    ffmpeg = ensure_tool("ffmpeg", progress)
    options = _options(progress, format="bestaudio/best", noplaylist=True, writethumbnail=True, ffmpeg_location=ffmpeg,
                       outtmpl={"default": str(directory / "%(id)s.%(ext)s")}, match_filter=check, progress_hooks=[hook],
                       postprocessors=[{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}])
    try:
        with YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as e:
        cause = e.exc_info[1] if e.exc_info else None
        raise cause if isinstance(cause, ImportFailed) else ImportFailed(_clean_error(e))
    path = directory / f"{info['id']}.mp3" if info else None
    if path is None or not path.is_file():
        raise ImportFailed(_("The download produced no mp3 file"))

    title = info.get("track") or info.get("title") or info["id"]
    cover = _cover(directory, info["id"])
    chapters = _chapters(info)
    if split and len(chapters) > 1:
        if progress:
            progress(_("Splitting {0}...").format(title))
        parts = _split(path, info, chapters, directory, ffmpeg, album or info.get("title") or title, cover)
        return Downloaded(path, file_name(title, info["id"]), title, parts)

    if progress:
        progress(_("Tagging {0}...").format(info.get("title") or url))
    update_mp3_title(path, title)
    if _artist(info):
        update_mp3_artist(path, _artist(info))
    if album or info.get("album"):
        update_mp3_album(path, album or info["album"])
    update_mp3_source(path, info.get("webpage_url") or url)
    if cover:
        update_mp3_cover_data(path, *cover)
    if chapters:
        update_mp3_chapters(path, chapters)
    return Downloaded(path, file_name(title, info["id"]), title)


def _split(path: Path, info: dict, chapters: list[dict], directory: Path, ffmpeg: str, album: str,
           cover: tuple[bytes, str] | None) -> list[Downloaded]:
    """Cuts the mp3 at the chapter marks (no re-encoding) and tags every piece."""
    source = info.get("webpage_url") or ""
    artist = _artist(info)
    parts = []
    for index, chapter in enumerate(chapters):
        title = chapter["title"] or f"{index + 1}"
        name = f"{index + 1:02d} {file_name(title)}"
        target = directory / f"part{index + 1}.mp3"
        command = [ffmpeg, "-v", "error", "-y", "-i", str(path), "-ss", f"{chapter['time'] / 1000:.3f}"]
        if index + 1 < len(chapters):
            command += ["-to", f"{chapters[index + 1]['time'] / 1000:.3f}"]
        command += ["-map", "0:a", "-map_metadata", "-1", "-map_chapters", "-1", "-c", "copy", str(target)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(command, capture_output=True, text=True, creationflags=flags)
        if result.returncode != 0 or not target.is_file():
            raise ImportFailed(_("Splitting failed: {0}").format(result.stderr.strip().splitlines()[-1] if result.stderr.strip() else title))
        update_mp3_title(target, title)
        if artist:
            update_mp3_artist(target, artist)
        update_mp3_album(target, album)
        if source:
            update_mp3_source(target, source)
        if cover:
            update_mp3_cover_data(target, *cover)
        parts.append(Downloaded(target, name, title))
    return parts
