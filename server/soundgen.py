"""Sound generation: a cloud function (agents/soundgen/modal_app.py on Modal, Stable Audio 3) turns a description into a sound effect,
an ambience or background music, and the sound is stored like an upload, usually in the effects folder.

The description usually comes from the AI assistant ("effects" mode in server/assistant.py). The endpoint URL and the key and secret
of its Modal proxy auth token are kept next to settings.json (see server/cloudconfig.py) and never sent back to the browser.
"""
import json
import threading
import urllib.error
import urllib.request

from core.i18n import _
from server.cloudconfig import CloudConfig, CloudError, auth_headers, error_detail
from server.musicgen import MAX_BYTES, MusicGenError, store
from server.paths import Location

CONFIG = CloudConfig("soundgen-cloud.json", "DT_SOUNDGEN")

ARTIST = "Stable Audio"
KINDS = ("sfx", "ambience", "music")
# Seconds for one sound: a cold start of the container (the first one downloads the model) and the generation itself.
GENERATE_TIMEOUT = 900
MIN_SECONDS, MAX_SECONDS = 1, 380

_gate = threading.Semaphore(2)  # parallel generations; the cloud side caps its containers as well


class SoundGenError(MusicGenError):
    pass


def configured() -> bool:
    return CONFIG.load() is not None


def status() -> dict:
    return CONFIG.status()


def save_config(url: str, key: str, secret: str):
    CONFIG.save(url, key, secret)


def delete_config():
    CONFIG.delete()


def generate(sound: dict) -> tuple[bytes, int | None]:
    """Posts the sound (caption, kind, duration, seed) to the cloud function; returns the mp3 and its seed."""
    config = CONFIG.load()
    if config is None:
        raise SoundGenError(_("The sound generation is not configured"))
    request = urllib.request.Request(config["url"], data=json.dumps(sound).encode("utf-8"), method="POST",
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
                raise SoundGenError(_("The sound generation rejected the key or the secret ({0})").format(detail)) from e
            raise SoundGenError(_("The sound generation failed ({0}): {1}").format(e.code, detail)) from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise SoundGenError(_("The sound generation is not reachable: {0}").format(e)) from e
    if len(data) > MAX_BYTES:
        raise SoundGenError(_("The sound generation sent an unexpected answer"))
    return data, int(seed) if seed and seed.isdigit() else None


def create(sound: dict, directory: Location, user: str) -> dict:
    """Generates the sound and stores it in `directory`; returns the track of the library and the seed. Sounds are not analyzed:
    they are effects, not songs to rate."""
    title = str(sound.get("title") or "").strip() or _("Sound")
    data, seed = generate({key: sound.get(key) for key in ("caption", "kind", "duration", "seed")})
    track = store(data, directory, user, title=title, artist=ARTIST, summary=str(sound.get("caption") or ""), analyze=False,
                  invalid=_("The sound generation sent an unexpected answer"))
    return {"track": track, "seed": seed}


__all__ = ["CloudError", "KINDS", "SoundGenError", "configured", "create", "delete_config", "generate", "save_config", "status"]
