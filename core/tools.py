"""External helper programs (ffmpeg, a JavaScript runtime for yt-dlp): taken from the PATH or downloaded once into the user data directory."""
import hashlib
import logging
import os
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from core.i18n import _
from core.utils import get_user_data_dir

logger = logging.getLogger(__name__)

Progress = Callable[[str], None]

DOWNLOAD_TIMEOUT = 60
FFMPEG_RELEASE = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest"
DENO_RELEASE = "https://github.com/denoland/deno/releases/latest/download"


@dataclass(frozen=True)
class Download:
    """A static build: the archive, where its sha256 is published and the executable inside of it (None: the only file)."""
    archive: str
    checksums: str
    member: str | None = None


def tools_dir() -> Path:
    return Path(os.environ.get("DT_TOOLS_DIR") or get_user_data_dir() / "tools")


def _machine() -> str:
    machine = platform.machine().lower()
    return "arm64" if machine in ("arm64", "aarch64") else "x64"


def _exe(name: str) -> str:
    return name + (".exe" if sys.platform == "win32" else "")


def _ffmpeg_download() -> Download | None:
    arch = _machine()
    if sys.platform == "win32":
        base = f"ffmpeg-master-latest-win{'arm64' if arch == 'arm64' else '64'}-gpl"
        return Download(f"{FFMPEG_RELEASE}/{base}.zip", f"{FFMPEG_RELEASE}/checksums.sha256", f"{base}/bin/ffmpeg.exe")
    if sys.platform.startswith("linux"):
        base = f"ffmpeg-master-latest-linux{'arm64' if arch == 'arm64' else '64'}-gpl"
        return Download(f"{FFMPEG_RELEASE}/{base}.tar.xz", f"{FFMPEG_RELEASE}/checksums.sha256", f"{base}/bin/ffmpeg")
    return None


def _deno_download() -> Download | None:
    arch = "aarch64" if _machine() == "arm64" else "x86_64"
    target = {"win32": f"{arch}-pc-windows-msvc", "darwin": f"{arch}-apple-darwin"}.get(sys.platform)
    if target is None and sys.platform.startswith("linux"):
        target = f"{arch}-unknown-linux-gnu"
    if target is None:
        return None
    return Download(f"{DENO_RELEASE}/deno-{target}.zip", f"{DENO_RELEASE}/deno-{target}.zip.sha256sum")


DOWNLOADS: dict[str, Callable[[], Download | None]] = {"ffmpeg": _ffmpeg_download, "deno": _deno_download}


def find_tool(name: str) -> str | None:
    """The executable on the PATH or in the tools directory, None if it is not installed."""
    found = shutil.which(name)
    if found:
        return found
    local = tools_dir() / _exe(name)
    return str(local) if local.is_file() else None


def _fetch(url: str, target) -> None:
    with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT) as response:
        shutil.copyfileobj(response, target, 1 << 20)


def _expected_hash(download: Download) -> str:
    with tempfile.TemporaryFile() as listing:
        _fetch(download.checksums, listing)
        listing.seek(0)
        text = listing.read().decode("utf-8", errors="replace")
    name = download.archive.rsplit("/", 1)[1]
    lines = [line for line in text.splitlines() if name in line] or text.splitlines()  # a list of files, or the hash of one file
    for line in lines:
        match = re.search(r"\b[0-9a-fA-F]{64}\b", line)
        if match:
            return match.group(0).lower()
    raise OSError(_("No checksum found for {0}").format(name))


def _extract(archive: Path, download: Download, name: str, target: Path):
    if archive.suffixes[-2:] == [".tar", ".xz"]:
        with tarfile.open(archive) as tar:
            source = tar.extractfile(download.member)
            with open(target, "wb") as out:
                shutil.copyfileobj(source, out)
    else:
        with zipfile.ZipFile(archive) as zipped:
            with zipped.open(download.member or _exe(name)) as source, open(target, "wb") as out:
                shutil.copyfileobj(source, out)


def ensure_tool(name: str, progress: Progress | None = None) -> str:
    """The path of a tool, downloading (and verifying) it into the tools directory when it is missing."""
    found = find_tool(name)
    if found:
        return found
    download = DOWNLOADS[name]()
    if download is None:
        raise OSError(_("{0} is not installed and cannot be downloaded for this system").format(name))
    if progress:
        progress(_("Downloading {0}...").format(name))
    directory = tools_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / _exe(name)
    with tempfile.TemporaryDirectory(prefix="dt-tool-", dir=directory) as tmp:
        archive = Path(tmp) / download.archive.rsplit("/", 1)[1]
        digest = hashlib.sha256()
        with open(archive, "wb") as out:
            _fetch(download.archive, out)
        with open(archive, "rb") as source:
            while chunk := source.read(1 << 20):
                digest.update(chunk)
        if digest.hexdigest() != _expected_hash(download):
            raise OSError(_("The downloaded {0} is corrupt (checksum mismatch)").format(name))
        partial = Path(tmp) / _exe(name)
        _extract(archive, download, name, partial)
        partial.chmod(0o755)
        os.replace(partial, target)
    logger.info("Installed {0} into {1}", name, directory)
    return str(target)
