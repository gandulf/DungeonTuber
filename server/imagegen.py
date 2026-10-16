"""Image generation: a cloud function (agents/imagegen/modal_app.py on Modal, Stable Diffusion 3.5 Medium) turns a description into a
picture, for example the cover of an adventure block (see server/routes/adventures.py).

The description usually comes from the AI assistant ("image" mode in server/assistant.py). The endpoint URL and the key and secret
of its Modal proxy auth token are kept next to settings.json (see server/cloudconfig.py) and never sent back to the browser.
"""
import json
import threading
import urllib.error
import urllib.request

from core.i18n import _
from server.cloudconfig import CloudConfig, CloudError, auth_headers, error_detail

CONFIG = CloudConfig("imagegen-cloud.json", "DT_IMAGEGEN")

# Seconds for one image: a cold start of the container (the first one downloads the model) and the generation itself.
GENERATE_TIMEOUT = 900
MAX_BYTES = 8 * 1024 * 1024  # as large as an uploaded image of an adventure may be
MAX_PROMPT = 2000
SIZES = {"landscape": (1344, 768), "square": (1024, 1024), "portrait": (768, 1344)}

_gate = threading.Semaphore(2)  # parallel generations; the cloud side caps its containers as well


class ImageGenError(Exception):
    pass


def configured() -> bool:
    return CONFIG.load() is not None


def status() -> dict:
    return CONFIG.status()


def save_config(url: str, key: str, secret: str):
    CONFIG.save(url, key, secret)


def delete_config():
    CONFIG.delete()


def generate(prompt: str, size: str = "landscape", seed: int | None = None, negative_prompt: str = "") -> tuple[bytes, int | None]:
    """Posts the description to the cloud function; returns the image (JPEG) and its seed."""
    config = CONFIG.load()
    if config is None:
        raise ImageGenError(_("The image generation is not configured"))
    width, height = SIZES.get(size, SIZES["landscape"])
    body = {"prompt": prompt[:MAX_PROMPT], "negative_prompt": negative_prompt[:MAX_PROMPT], "width": width, "height": height,
            "format": "jpeg"}
    if seed is not None:
        body["seed"] = seed
    request = urllib.request.Request(config["url"], data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={**auth_headers(config), "Content-Type": "application/json"})
    with _gate:
        try:
            # a request that takes longer than 150 s is redirected by Modal to a URL that waits for the result; urllib follows it
            with urllib.request.urlopen(request, timeout=GENERATE_TIMEOUT) as response:
                data = response.read(MAX_BYTES + 1)
                answered_seed = response.headers.get("X-Seed")
        except urllib.error.HTTPError as e:
            detail = error_detail(e)
            if e.code in (401, 403):
                raise ImageGenError(_("The image generation rejected the key or the secret ({0})").format(detail)) from e
            raise ImageGenError(_("The image generation failed ({0}): {1}").format(e.code, detail)) from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise ImageGenError(_("The image generation is not reachable: {0}").format(e)) from e
    if not data or len(data) > MAX_BYTES:
        raise ImageGenError(_("The image generation sent an unexpected answer"))
    return data, int(answered_seed) if answered_seed and answered_seed.isdigit() else None


__all__ = ["CloudError", "ImageGenError", "SIZES", "configured", "delete_config", "generate", "save_config", "status"]
