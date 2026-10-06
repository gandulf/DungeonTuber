"""Translations from core/locales/<lang>.json – the single source of truth for the server and the web frontend.

Message ids are the English texts; a missing entry falls back to the id itself.
"""
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__file__)

_catalog: dict[str, str] = {}
_language: str | None = None



def locales_dir() -> str:
    # shipped inside the package so it works from source, an installed wheel and a PyInstaller bundle
    return str(Path(__file__).resolve().parent / "locales")


def available_locales() -> list[str]:
    try:
        return sorted(name[:-5] for name in os.listdir(locales_dir()) if name.endswith(".json"))
    except OSError:
        return []


def load_catalog(language: str) -> dict[str, str]:
    try:
        with open(os.path.join(locales_dir(), f"{language}.json"), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError) as e:
        logger.warning("Unable to load locale {0}: {1}", language, e)
        return {}


FALLBACK_LANGUAGE = "en"


def set_language(language: str | None):
    """Activates a language; None or an unknown language falls back to English."""
    global _catalog, _language
    language = (language or "").split("_")[0].split("-")[0].lower() or None
    locales = available_locales()
    _language = language if language in locales else (FALLBACK_LANGUAGE if FALLBACK_LANGUAGE in locales else None)
    _catalog = load_catalog(_language) if _language else {}


def language() -> str | None:
    return _language


def _(message: str) -> str:
    if _language is None and not _catalog:
        set_language(None)  # lazily load the English texts
    return _catalog.get(message, message)
