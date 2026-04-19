import ctypes
import ipaddress
import json
import logging
import math
import os
import subprocess
import sys
import socket
from ctypes import wintypes
from dataclasses import is_dataclass, fields
from os import PathLike
from pathlib import Path

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication
from packaging import version

logger = logging.getLogger(__file__)

DOWNLOAD_LINK = "https://github.com/gandulf/DungeonTuber/releases/latest"

def clear_layout(layout):
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()

def children_layout(layout):
    return [ layout.itemAt(i).widget() for i in range(layout.count()) ]

def get_executable_path(path:str) -> PathLike[str]:
    # os.path.realpath handles symlinks; sys.argv[0] is the binary location in Nuitka
    path = os.path.join(os.path.dirname(os.path.realpath(sys.argv[0])), path)
    return Path(path).as_posix()

def get_path(path:str) -> PathLike[str]:
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        if sys._MEIPASS is not None:
            icon_path = os.path.join(sys._MEIPASS, path)
        elif "__compiled__" in globals():
            icon_path = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0]), path))
        else:
            icon_path = os.path.join(os.path.dirname(sys.executable), path)
            if not os.path.exists(icon_path):
                icon_path = os.path.join(os.getcwd(), path)
    else:
        # Running as Python script
        icon_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
    return Path(icon_path).as_posix()


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

def get_current_version()->str:
    # Get the path to the current running .exe
    if "__compiled__" in globals():
        # sys.argv[0] is generally the reliable way to find the outer .exe in Nuitka
        exe_path = os.path.abspath(sys.argv[0])
    elif getattr(sys, 'frozen', False):
        exe_path = sys.executable
    else:
        return "Dev"

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

def is_latest_version() -> bool:
    current_version = QApplication.instance().applicationVersion()
    if current_version == "Dev" or current_version == "Unknown":
        return True

    latest_version = get_latest_version()
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        return False
    else:
        return True

_latest_version : str | None = None

def get_latest_version() -> str:
    global _latest_version
    if _latest_version is None:
        url = "https://api.github.com/repos/gandulf/DungeonTuber/releases/latest"
        headers = {"User-Agent": "Python-urllib/3.x"}
        try:
            req = Request(url, headers=headers)

            with urlopen(req) as response:
                # urllib raises an HTTPError for non-200 codes automatically
                status = response.getcode()
                raw_data = response.read().decode("utf-8")
                data = json.loads(raw_data)

                # Check if tag_name exists and is not None
                tag = data.get("tag_name")
                _latest_version = tag.lstrip("v") if tag else ""

        except HTTPError as e:
            logger.error("HTTP Error {0}: Unable to fetch version info", e.code)
            _latest_version = ""
        except Exception as e:
            logger.error("Unable to fetch latest version info: {0}", e)
            _latest_version = ""


    if _latest_version is not None and _latest_version != "":
        return _latest_version
    else:
        return None


def get_available_locales() -> list[str]:
    locales_path = get_path("locales")
    if not os.path.exists(locales_path):
        return ["de","en"]

    # Gehe durch alle Unterordner in /locales
    locales = []
    for lang_code in os.listdir(locales_path):
        mo_file = os.path.join(locales_path, lang_code, 'LC_MESSAGES', 'DungeonTuber.mo')

        # Nur hinzufügen, wenn der Ordner existiert und eine kompilierte .mo Datei enthält
        if os.path.isfile(mo_file):
            locales.append(lang_code)

    return locales

def restart_application():
    """Restarts the current program, compatible with PyInstaller."""
    try:
        # Get the path to the current executable
        executable = sys.executable

        # In a PyInstaller bundle, sys.executable points to the .exe
        # In a script, it points to python.exe

        # Start a new process
        subprocess.Popen([executable] + sys.argv)

        # Exit the current process
        sys.exit()
    except Exception as e:
        logger.exception("Failed to restart. {0}",e)

def is_frozen() -> bool:
    # Returns True if running as a PyInstaller bundle
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')


def ms_to_promille(current_ms: int, total_ms: int) -> int:
    """
    Converts a timestamp and total duration into a promille value (0-1000).
    """
    # Prevent division by zero
    if total_ms <= 0:
        return 0

    # Calculate the ratio
    ratio = current_ms / total_ms

    # Calculate promille and clamp it between 0 and 1000
    promille = int(ratio * 1000)

    return max(0, min(1000, promille))

def promille_to_ms(promille: int, total_ms: int) -> int:
    return int(total_ms / 1000.0  * promille)

def timestamp_to_ms(timestamp: str) -> int:
    """
    Converts 'mm:ss' or 'hh:mm:ss' string to total milliseconds.
    Example: '01:30' -> 90000
    """
    try:
        # Split by colon and reverse so [0] is always seconds, [1] is minutes, etc.
        parts = list(map(int, timestamp.split(':')))[::-1]

        seconds = parts[0]
        minutes = parts[1] if len(parts) > 1 else 0
        hours = parts[2] if len(parts) > 2 else 0

        total_seconds = seconds + (minutes * 60) + (hours * 3600)
        return total_seconds * 1000

    except (ValueError, IndexError):
        # Return 0 or handle malformed strings (like "abc:def")
        return 0

def format_time(ms: int):
    """Converts milliseconds to MM:SS string."""
    if ms < 0:
        return "00:00"
    seconds = round(ms / 1000)
    mins = seconds // 60
    secs = seconds % 60
    return f"{mins:02d}:{secs:02d}"


def asdict_filtered(obj):
    if is_dataclass(obj):
        skip_keys = [
            f.name for f in fields(obj) if not f.metadata.get('export', True)
        ]

        res = {}
        for f in fields(obj):
            if f.name in skip_keys:
                continue
            val = getattr(obj, f.name)
            res[f.name] = asdict_filtered(val)
        return res
    elif isinstance(obj, QColor):
        return obj.name()
    return obj


def kelvin_to_rgb(kelvin):
    temp = kelvin / 100

    # Calculate Red
    if temp <= 66:
        red = 255
    else:
        red = temp - 60
        red = 329.698727446 * (red ** -0.1332047592)
        red = clip(red)

    # Calculate Green
    if temp <= 66:
        green = temp
        green = 99.4708025861 * math.log(green) - 161.1195681661
    else:
        green = temp - 60
        green = 288.1221695283 * (green ** -0.0755148492)
    green = clip(green)

    # Calculate Blue
    if temp >= 66:
        blue = 255
    elif temp <= 19:
        blue = 0
    else:
        blue = temp - 10
        blue = 138.5177312231 * math.log(blue) - 305.0447927307
    blue = clip(blue)


    color = QColor(int(red), int(green), int(blue))
    return color.name()


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
    broadcast_ip = interface.network.broadcast_address
    return str(broadcast_ip)
