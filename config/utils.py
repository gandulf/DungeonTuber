import json
import logging
import os
import subprocess
import sys

from urllib.error import HTTPError
from urllib.request import Request, urlopen

from PySide6.QtWidgets import QApplication
from packaging import version

logger = logging.getLogger("main")

DOWNLOAD_LINK = "https://github.com/gandulf/DungeonTuber/releases/latest"

def clear_layout(layout):
    while layout.count():
        child = layout.takeAt(0)
        if child.widget():
            child.widget().deleteLater()

def get_path(path:str):
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
    return icon_path

def get_current_version() -> str | None:
    try:
        return str(open(get_path("version.txt"), "r").readline())
    except FileNotFoundError:
        return "v0.1.0"

def is_latest_version():
    latest_version = get_latest_version()
    current_version = QApplication.instance().applicationVersion()
    if latest_version and version.parse(latest_version) > version.parse(current_version):
        return False
    else:
        return True

_latest_version : str | None = None

def get_latest_version():
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


def get_available_locales():
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



def is_frozen():
    # Returns True if running as a PyInstaller bundle
    return getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')