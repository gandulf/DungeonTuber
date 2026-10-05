import ctypes
import ipaddress
import json
import logging
import math
import os
import socket
import subprocess
import sys
from dataclasses import is_dataclass, fields
from os import PathLike
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from packaging import version

logger = logging.getLogger(__file__)

APP_NAME = "DungeonTuber"
DOWNLOAD_LINK = "https://github.com/gandulf/DungeonTuber/releases/latest"


def get_executable_path(path: str) -> PathLike[str]:
    # os.path.realpath handles symlinks; sys.argv[0] is the binary location in Nuitka
    path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), path)
    return Path(path).as_posix()


def get_path(path: str) -> PathLike[str]:
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if getattr(sys, "_MEIPASS", None) is not None:
            resource_path = os.path.join(sys._MEIPASS, path)
        elif "__compiled__" in globals():
            resource_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), path)
        else:
            resource_path = os.path.join(os.path.dirname(sys.executable), path)
            if not os.path.exists(resource_path):
                resource_path = os.path.join(os.getcwd(), path)
    else:
        # Running as Python script
        resource_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    return Path(resource_path).as_posix()


def get_user_data_dir() -> Path:
    """Per-user directory for settings and logs."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / APP_NAME


def get_current_version() -> str:
    # Get the path to the current running .exe
    if "__compiled__" in globals():
        # sys.argv[0] is generally the reliable way to find the outer .exe in Nuitka
        exe_path = os.path.abspath(sys.argv[0])
    elif getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        return "Dev"

    if sys.platform != "win32":
        return "Unknown"

    from ctypes import wintypes

    class VS_FIXEDFILEINFO(ctypes.Structure):
        _fields_ = [
            ("dwSignature", wintypes.DWORD),
            ("dwStrucVersion", wintypes.DWORD),
            ("dwFileVersionMS", wintypes.DWORD),
            ("dwFileVersionLS", wintypes.DWORD),
            ("dwProductVersionMS", wintypes.DWORD),
            ("dwProductVersionLS", wintypes.DWORD),
            ("dwFileFlagsMask", wintypes.DWORD),
            ("dwFileFlags", wintypes.DWORD),
            ("dwFileOS", wintypes.DWORD),
            ("dwFileType", wintypes.DWORD),
            ("dwFileSubtype", wintypes.DWORD),
            ("dwFileDateMS", wintypes.DWORD),
            ("dwFileDateLS", wintypes.DWORD),
        ]

    size = ctypes.windll.version.GetFileVersionInfoSizeW(exe_path, None)
    if not size:
        return "Unknown"

    buffer = ctypes.create_string_buffer(size)
    ctypes.windll.version.GetFileVersionInfoW(exe_path, 0, size, buffer)

    fixed_info_ptr = ctypes.POINTER(VS_FIXEDFILEINFO)()
    u_len = ctypes.c_uint()

    # Query the root block
    if ctypes.windll.version.VerQueryValueW(buffer, "\\", ctypes.byref(fixed_info_ptr), ctypes.byref(u_len)):
        fixed_info = fixed_info_ptr.contents

        # Versions are packed as (Major << 16) | Minor
        ms = fixed_info.dwProductVersionMS
        ls = fixed_info.dwProductVersionLS

        return f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"

    return "Unknown"


class UpdateChecker:
    """Looks up the latest GitHub release once and caches the result."""

    URL = "https://api.github.com/repos/gandulf/DungeonTuber/releases/latest"

    def __init__(self):
        self._latest_version: str | None = None

    def get_latest_version(self) -> str | None:
        if self._latest_version is None:
            headers = {"User-Agent": "Python-urllib/3.x"}
            try:
                req = Request(self.URL, headers=headers)

                with urlopen(req, timeout=5) as response:
                    # urllib raises an HTTPError for non-200 codes automatically
                    raw_data = response.read().decode("utf-8")
                    data = json.loads(raw_data)

                    # Check if tag_name exists and is not None
                    tag = data.get("tag_name")
                    self._latest_version = tag.lstrip("v") if tag else ""

            except HTTPError as e:
                logger.error("HTTP Error {0}: Unable to fetch version info", e.code)
                self._latest_version = ""
            except Exception as e:
                logger.error("Unable to fetch latest version info: {0}", e)
                self._latest_version = ""

        return self._latest_version or None


update_checker = UpdateChecker()


def get_latest_version() -> str | None:
    return update_checker.get_latest_version()


def is_newer_version_available(current_version: str) -> bool:
    if current_version in ("Dev", "Unknown", None, ""):
        return False

    latest_version = get_latest_version()
    try:
        return bool(latest_version) and version.parse(latest_version) > version.parse(current_version)
    except version.InvalidVersion:
        return False


def get_available_locales() -> list[str]:
    locales_path = get_path("locales")
    if not os.path.exists(locales_path):
        return ["de", "en"]

    locales = []
    for lang_code in os.listdir(locales_path):
        mo_file = os.path.join(locales_path, lang_code, 'LC_MESSAGES', 'DungeonTuber.mo')

        # Only add the language if it contains a compiled .mo file
        if os.path.isfile(mo_file):
            locales.append(lang_code)

    return locales


def restart_application():
    """Restarts the current program, compatible with PyInstaller."""
    try:
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit()
    except Exception as e:
        logger.exception("Failed to restart. {0}", e)


def is_frozen() -> bool:
    # Returns True if running as a PyInstaller bundle
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def ms_to_promille(current_ms: int, total_ms: int) -> int:
    """Converts a timestamp and total duration into a promille value (0-1000)."""
    if total_ms <= 0:
        return 0

    promille = int(current_ms / total_ms * 1000)
    return max(0, min(1000, promille))


def promille_to_ms(promille: int, total_ms: int) -> int:
    return int(total_ms / 1000.0 * promille)


def timestamp_to_ms(timestamp: str) -> int:
    """Converts 'mm:ss' or 'hh:mm:ss' string to total milliseconds. Example: '01:30' -> 90000"""
    try:
        # Split by colon and reverse so [0] is always seconds, [1] is minutes, etc.
        parts = list(map(int, timestamp.split(':')))[::-1]

        seconds = parts[0]
        minutes = parts[1] if len(parts) > 1 else 0
        hours = parts[2] if len(parts) > 2 else 0

        return (seconds + minutes * 60 + hours * 3600) * 1000
    except (ValueError, IndexError):
        return 0


def format_time(ms: int):
    """Converts milliseconds to MM:SS string."""
    if ms < 0:
        return "00:00"
    seconds = round(ms / 1000)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def asdict_filtered(obj):
    """dataclasses.asdict that skips fields marked with metadata={'export': False}."""
    if is_dataclass(obj):
        res = {}
        for f in fields(obj):
            if not f.metadata.get('export', True):
                continue
            res[f.name] = asdict_filtered(getattr(obj, f.name))
        return res
    return obj


def to_hex_color(color) -> str | None:
    """Normalizes a color to '#rrggbb'. Accepts hex strings, (r, g, b) tuples and objects with a name() method (e.g. QColor)."""
    if color is None or color == "":
        return None
    if isinstance(color, str):
        value = color.strip()
        if not value.startswith("#"):
            value = "#" + value
        if len(value) == 9:  # '#aarrggbb' -> drop alpha
            value = "#" + value[3:]
        return value.lower()
    if isinstance(color, (tuple, list)) and len(color) >= 3:
        r, g, b = (int(clip(c)) for c in color[:3])
        return f"#{r:02x}{g:02x}{b:02x}"
    if hasattr(color, "name"):
        return str(color.name()).lower()
    raise ValueError(f"Unsupported color value: {color!r}")


def hex_to_rgb(color: str | None) -> tuple[int, int, int] | None:
    color = to_hex_color(color)
    if color is None:
        return None
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def kelvin_to_rgb(kelvin) -> str:
    """Approximates the color of a black-body radiator, returned as '#rrggbb'."""
    temp = kelvin / 100

    if temp <= 66:
        red = 255
    else:
        red = clip(329.698727446 * ((temp - 60) ** -0.1332047592))

    if temp <= 66:
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)
    green = clip(green)

    if temp >= 66:
        blue = 255
    elif temp <= 19:
        blue = 0
    else:
        blue = clip(138.5177312231 * math.log(temp - 10) - 305.0447927307)

    return to_hex_color((red, green, blue))


def clip(value):
    return max(0, min(255, value))


def get_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(0)
    try:
        # doesn't even have to be reachable
        s.connect(('10.254.254.254', 1))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def get_broadcast_ip():
    interface = ipaddress.IPv4Interface(f"{get_ip()}/24")
    return str(interface.network.broadcast_address)
