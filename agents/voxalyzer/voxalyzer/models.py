"""The analysis models (ONNX): not shipped with the app, downloaded on first start into a per-user folder.

Where they are looked for: ``DT_MODEL_DIR``, else the ``models`` folder next to the package when complete (development), else
``%LOCALAPPDATA%/DungeonTuber/models`` (``~/.cache/DungeonTuber/models`` elsewhere). The files are fetched from the repo through
raw.githubusercontent.com (``DT_MODELS_URL`` points to another location) and are verified by SHA-256.
"""
import hashlib
import logging
import os
import shutil
import urllib.request
from pathlib import Path

from voxalyzer.utils import get_path

logger = logging.getLogger(__name__)

DEFAULT_URL = "https://raw.githubusercontent.com/gandulf/DungeonTuber/master/agents/voxalyzer/models"
DOWNLOAD_TIMEOUT = 60

MODELS = {
    "danceability-discogs-effnet-1.onnx": "9ce9b8c44f1dd5df5ffc124e5d41d67acf254232c1b90c7e057e079ab7cead73",
    "deam-msd-musicnn-2.onnx": "2cb8f33f188d73fcb651f7c065b049959166c7852f454a59c13e66fe2c092bde",
    "discogs-effnet-bsdynamic-1.onnx": "a280825b334797cf677939db8cd5762c0392aedd0ca6415dbc1cd083f045e43c",
    "engagement_regression-discogs-effnet-1.onnx": "9551a6c162c9803aef5ce4e4d29a2e4fae99b5bfdc95dae9dd8fe5335e0fb567",
    "mood_aggressive-discogs-effnet-1.onnx": "de36550b5d1660791ad732ed6de6ebfdc3e65dcf50b928b2578ddf103dbfb400",
    "mood_happy-discogs-effnet-1.onnx": "0ca322819ef137b4b87e9866bffe7370a630e6f1165184ec106326cef6f81e06",
    "mood_party-discogs-effnet-1.onnx": "c50ac2106ec2f209dd04ad48756582df0e3f3512235310d1a4a3fcc453745f04",
    "mood_relaxed-discogs-effnet-1.onnx": "8ba6515a1e5943a72b3b475e3a25fc7a2ff04142c3eaa6aa0716fca371efdfff",
    "mood_sad-discogs-effnet-1.onnx": "1a50d11c23181bdfdeabc7d6032a2dad829dfc19c3776d2ee57ef1724cb08805",
    "moods_mirex-msd-musicnn-1.onnx": "7415f08c509cbb569616b4f5d72c6f5181f82ef5a137cbccf5283b8868edcd4b",
    "msd-msd-musicnn-1.onnx": "ba0f4dbf7b5e140704b5fc1eabda1f74fe392fa66fdae86a485376c1a03805e8",
    "msd-musicnn-1.onnx": "e9347e05e34e203ee09684cd2cc7b077e84042766fcd908a46abc73bc62a8d97",
    "mtg_jamendo_genre-discogs-effnet-1.onnx": "637acf45315191a2c9a87d5977d48f02da6fc823192fe794a1537c55e7c7ce6a",
    "mtg_jamendo_moodtheme-discogs-effnet-1.onnx": "7d6270acaa5f4bba4b115a0d6849aca05ed6bd153dcb6d9da4f6ab9f99ef10ff",
    "nsynth_bright_dark-discogs-effnet-1.onnx": "1adddde8c15ad77132be5474259730dcbf5aac7401c5b7a9627a199c74f5170c",
    "tonal_atonal-discogs-effnet-1.onnx": "39b9f73c23bec24c911cdb1370ae7b1aa387e69c97e256e83360b5560fd5f356",
}


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    return (Path(base) if base else Path.home() / ".cache") / "DungeonTuber" / "models"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        while chunk := file.read(1 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def _complete(directory: Path) -> bool:
    return all((directory / name).is_file() for name in MODELS)


def models_dir() -> Path:
    configured = os.environ.get("DT_MODEL_DIR")
    if configured:
        return Path(configured)
    bundled = Path(get_path("models"))
    return bundled if _complete(bundled) else cache_dir()


def model_path(name: str) -> str:
    return str(models_dir() / name)


def _download(url: str, target: Path):
    partial = target.with_name(target.name + ".part")
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response, open(partial, "wb") as file:
            shutil.copyfileobj(response, file, 1 << 20)
        expected = MODELS[target.name]
        if _sha256(partial) != expected:
            raise OSError(f"Checksum mismatch for {target.name}")
        partial.replace(target)
    finally:
        partial.unlink(missing_ok=True)


def ensure_models() -> Path:
    """Downloads the missing (or damaged) models; returns the models folder. Raises OSError when a download fails."""
    directory = models_dir()
    directory.mkdir(parents=True, exist_ok=True)
    base = os.environ.get("DT_MODELS_URL", DEFAULT_URL).rstrip("/")
    missing = [name for name, checksum in MODELS.items() if not (directory / name).is_file() or _sha256(directory / name) != checksum]
    for index, name in enumerate(missing, 1):
        logger.info("Downloading model %s (%d/%d) from %s", name, index, len(missing), base)
        try:
            _download(f"{base}/{name}", directory / name)
        except OSError as e:
            raise OSError(f"Could not download {name} from {base}: {e}. Download the models manually into {directory}.") from e
    if missing:
        logger.info("Models ready in %s", directory)
    return directory
