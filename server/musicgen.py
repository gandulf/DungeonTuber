"""Music generation: a cloud function (agents/musicgen/modal_app.py on Modal, ACE-Step 1.5) composes a piece from a description and
the piece is stored in the library like an upload.

The description usually comes from the AI assistant ("compose" mode in server/assistant.py), which turns a scene into the caption
ACE-Step understands. The endpoint URL and the key and secret of its Modal proxy auth token are kept next to settings.json (see
server/cloudconfig.py) and never sent back to the browser.
"""
import contextlib
import json
import logging
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path

from core.i18n import _
from core.mp3 import _audio, parse_mp3, update_mp3_artist, update_mp3_bpm, update_mp3_summary, update_mp3_title
from core.storage import AlreadyExists
from core.ytimport import file_name
from server.cloudconfig import CloudConfig, CloudError, auth_headers, error_detail
from server.events import hub
from server.index import get_index
from server.jobs import analysis_queue
from server.paths import Location
from server.voxagent import current_backend

logger = logging.getLogger(__file__)

CONFIG = CloudConfig("musicgen-cloud.json", "DT_MUSICGEN")

ARTIST = "ACE-Step"
# Seconds for one piece: a cold start of the container (the first one downloads the models) and the generation itself.
GENERATE_TIMEOUT = 900
MIN_SECONDS, MAX_SECONDS = 10, 600
MAX_BYTES = 100 * 1024 * 1024
MAX_SAME_NAME = 100

_gate = threading.Semaphore(2)  # parallel generations; the cloud side caps its containers as well


class MusicGenError(OSError):
    pass


def configured() -> bool:
    return CONFIG.load() is not None


def status() -> dict:
    return CONFIG.status()


def save_config(url: str, key: str, secret: str):
    CONFIG.save(url, key, secret)


def delete_config():
    CONFIG.delete()


def generate(piece: dict) -> tuple[bytes, int | None]:
    """Posts the piece (caption, lyrics, instrumental, duration, bpm, seed) to the cloud function; returns the mp3 and its seed."""
    config = CONFIG.load()
    if config is None:
        raise MusicGenError(_("The music generation is not configured"))
    body = json.dumps(piece).encode("utf-8")
    request = urllib.request.Request(config["url"], data=body, method="POST",
                                     headers={**auth_headers(config), "Content-Type": "application/json"})
    with _gate:
        try:
            # a request that takes longer than 150 s is redirected by Modal to a URL that waits for the result; urllib follows it
            with urllib.request.urlopen(request, timeout=GENERATE_TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
                seed = response.headers.get("X-Seed")
        except urllib.error.HTTPError as e:
            detail = error_detail(e)
            if e.code in (401, 403):
                raise MusicGenError(_("The music generation rejected the key or the secret ({0})").format(detail)) from e
            raise MusicGenError(_("The music generation failed ({0}): {1}").format(e.code, detail)) from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise MusicGenError(_("The music generation is not reachable: {0}").format(e)) from e
    if len(data) > MAX_BYTES:
        raise MusicGenError(_("The music generation sent an unexpected answer"))
    return data, int(seed) if seed and seed.isdigit() else None


def _target(directory: Location, title: str) -> Location:
    """A file of the title that does not exist yet: "Title.mp3", "Title (2).mp3", …"""
    base = file_name(title, "composition")[:-len(".mp3")]
    for number in range(1, MAX_SAME_NAME + 1):
        target = directory.child(f"{base}.mp3" if number == 1 else f"{base} ({number}).mp3")
        if not target.storage.exists(target.rel):
            return target
    raise MusicGenError(_("Too many files named {0}").format(base))


def compose(piece: dict, directory: Location, user: str, analyze: bool = True) -> dict:
    """Generates the piece and stores it in `directory`; returns the track of the library and the seed."""
    title = str(piece.get("title") or "").strip() or _("Composition")
    data, seed = generate({key: piece.get(key) for key in ("caption", "lyrics", "language", "instrumental", "duration", "bpm", "seed")})
    with tempfile.TemporaryDirectory(prefix="dt-musicgen-") as tmp:
        path = Path(tmp) / "piece.mp3"
        path.write_bytes(data)
        try:
            audio = _audio(path)
            update_mp3_title(audio, title, False)
            update_mp3_artist(audio, ARTIST, False)
            update_mp3_summary(audio, str(piece.get("caption") or ""), False)
            if isinstance(piece.get("bpm"), int):
                update_mp3_bpm(audio, piece["bpm"], False)
            audio.save()
        except Exception as e:  # mutagen raises its own errors for files that are not mp3
            raise MusicGenError(_("The music generation sent an unexpected answer")) from e
        entry = parse_mp3(path)
        if entry is None:
            raise MusicGenError(_("The music generation sent an unexpected answer"))
        target = _target(directory, title)
        with open(path, "rb") as source:
            try:
                target.storage.write(target.rel, source)
            except AlreadyExists:  # created meanwhile by somebody else
                raise MusicGenError(_("File already exists: {0}").format(target.name))
    index = get_index()
    if target.root.is_local:
        index.get(target)
    else:
        index.import_entry(target, entry, entry.cover_data())
    index.set_uploader(target, user)
    hub.publish("library.changed", {"path": directory.client_path})
    if analyze and current_backend() is not None:
        with contextlib.suppress(ConnectionError):  # the agent went away; the piece is stored anyway
            analysis_queue.submit([target])
    return {"track": index.known(target), "seed": seed}


__all__ = ["CloudError", "MusicGenError", "compose", "configured", "delete_config", "generate", "save_config", "status"]
