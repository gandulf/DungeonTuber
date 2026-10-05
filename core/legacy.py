"""Qt-free import of the settings older versions stored with QSettings in the Windows registry
(HKEY_CURRENT_USER\\Software\\Gandulf\\DungeonTuber)."""
import logging
import re
import sys

from core.settings import AppSettings, settings

logger = logging.getLogger(__file__)

REGISTRY_PATH = r"Software\Gandulf\DungeonTuber"
_SIZE = re.compile(r"^@Size\((\d+) (\d+)\)$")

# winreg value types (kept here so the conversion is testable on any platform)
REG_SZ, REG_EXPAND_SZ, REG_BINARY, REG_DWORD, REG_MULTI_SZ, REG_QWORD = 1, 2, 3, 4, 7, 11


def convert_registry_value(value, value_type: int):
    """Converts a QSettings registry value to a JSON compatible value (None = skip)."""
    if value_type in (REG_DWORD, REG_QWORD):
        return int(value)
    if value_type == REG_MULTI_SZ:
        return [str(v) for v in value]
    if value_type in (REG_SZ, REG_EXPAND_SZ):
        text = str(value)
        size = _SIZE.match(text)
        if size:
            return [int(size.group(1)), int(size.group(2))]
        if text.startswith("@"):  # other serialized Qt types (@Variant, @ByteArray, ...)
            return None
        return text
    return None


def read_registry() -> dict:
    if sys.platform != "win32":
        return {}
    import winreg

    values = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH) as key:
            index = 0
            while True:
                try:
                    name, value, value_type = winreg.EnumValue(key, index)
                except OSError:
                    break
                index += 1
                converted = convert_registry_value(value, value_type)
                if converted is not None:
                    values[name] = converted
    except OSError:
        return {}
    return values


def migrate_legacy_settings() -> int:
    """Imports legacy values once, when no settings file exists yet. Returns the number of imported values."""
    if AppSettings.exists():
        return 0
    values = read_registry()
    AppSettings.import_values(values)
    settings.reload()
    if values:
        logger.info("Imported {0} legacy settings into {1}", len(values), AppSettings.path)
    return len(values)
