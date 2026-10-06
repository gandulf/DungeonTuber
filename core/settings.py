import json
import logging
import os
from dataclasses import dataclass, asdict
from enum import StrEnum
from functools import total_ordering

from core.i18n import _
from core.settings_backend import JsonSettings
from core.utils import get_executable_path, get_user_data_dir

logger = logging.getLogger(__file__)

# --- Configuration ---
CATEGORY_MIN = 0
CATEGORY_MAX = 10

CAT_VALENCE = "Valence"
CAT_AROUSAL = "Arousal"

CAT_ENGAGEMENT = "Engagement"
CAT_DARKNESS = "Darkness"

CAT_AGGRESSIVE = "Aggressive"
CAT_HAPPY = "Happy"
CAT_PARTY = "Party"
CAT_RELAXED = "Relaxed"
CAT_SAD = "Sad"

_DEFAULT_CATEGORIES = [CAT_VALENCE, CAT_AROUSAL, CAT_ENGAGEMENT, CAT_DARKNESS, CAT_AGGRESSIVE, CAT_HAPPY, CAT_PARTY, CAT_RELAXED, CAT_SAD]
_MOOD_CATEGORIES = [CAT_SAD, CAT_AGGRESSIVE, CAT_RELAXED, CAT_HAPPY, CAT_PARTY]


class SettingKeys(StrEnum):
    """Keys of the per-server settings document (settings.json)."""
    LOCALE = "locale"
    LIBRARY_ROOTS = "libraryRoots"
    # Non-local library roots, e.g. S3 buckets: list of dicts accepted by core.storage.create_storage (+ "id", "direct")
    STORAGE_ROOTS = "storageRoots"
    FAVORITES = "favorites"
    EFFECTS_DIRECTORY = "effectsDirectory"
    # Accounts besides the SuperAdmin (see server/users.py): list of dicts with name, hash, created
    USERS = "users"

    CATEGORIES = "categories"
    PRESETS = "presets"

    SKIP_ANALYZED_MUSIC = "skipAnalyzedMusic"
    VOXALYZER_URL = "voxalyzerUrl"
    VOXALYZER_LOCAL = "voxalyzerLocal"

    LIGHTS_ENABLED = "lightsEnabled"
    LIGHTS_CONFIG = "lightsConfig"
    LIGHTS_BROADCAST_IP = "lightsBroadcastIP"
    LIGHTS_TIMEOUT = "lightsTimeout"

    SHARE_ON_NETWORK = "shareOnNetwork"
    SHARE_PORT = "sharePort"
    SERVER_PASSWORD_HASH = "serverPasswordHash"
    SERVER_SECRET = "serverSecret"


def default_settings_path() -> str:
    return str(get_user_data_dir() / "settings.json")


# Shared application-wide key/value store. Point it elsewhere with AppSettings.set_path().
AppSettings: JsonSettings = JsonSettings(default_settings_path())


def has_voxalyzer():
    return has_local_voxalyzer() or AppSettings.value(SettingKeys.VOXALYZER_URL, type=str, defaultValue='') != ''


def has_local_voxalyzer():
    return os.path.isfile(get_executable_path("voxalyzer.exe")) and AppSettings.value(SettingKeys.VOXALYZER_LOCAL, True, type=bool)


@total_ordering
@dataclass
class MusicCategory:
    key: str
    name: str
    description: str
    levels: dict[int, str]
    group: str = None

    def __init__(self, name: str, description: str, levels: dict[int, str], group: str = '', key: str = None):
        self.key = name if key is None else key
        self.name = name
        self.description = description
        self.levels = levels
        self.group = group

    def __hash__(self):
        return hash(self.key)

    def __lt__(self, other):
        return self.key < other.key

    def __eq__(self, other):
        if not isinstance(other, MusicCategory):
            return False
        return self.key == other.key or self.name == other.name

    def json_dump(self):
        return json.dumps(asdict(self))

    @classmethod
    def json_dump_list(cls, categories: list):
        return json.dumps([asdict(mc) for mc in categories])

    @classmethod
    def json_load(cls, json_string: str):
        return MusicCategory(**json.loads(json_string))

    @classmethod
    def from_key(cls, key: str):
        name = _(key)
        description = _(key + " Description")
        levels = {1: _(key + " Low"),
                  5: _(key + " Medium"),
                  10: _(key + " High")
                  }

        group = "Mood" if key in _MOOD_CATEGORIES else ""

        return MusicCategory(name, description, levels, key=key, group=group)

    def equals(self, name_or_key: str):
        return self.name == name_or_key or self.key == name_or_key or self.name == _(name_or_key)

    def get_detailed_description(self):
        tooltip = self.description + "\n"

        for level, descr in self.levels.items():
            tooltip += str(level) + ": " + descr + "\n"

        return tooltip.removesuffix("\n")


@dataclass
class Preset:
    name: str
    categories: dict[str, int] | None
    tags: list[str]
    genres: list[str]
    bpm: int

    def __init__(self, name: str, categories: dict[str, int], tags: list[str] = None, genres: list[str] = None, bpm: int = None):
        self.name = name
        self.categories = categories.copy() if categories is not None else {}
        self.tags = tags.copy() if tags is not None else []
        self.genres = genres.copy() if genres is not None else []
        self.bpm = bpm

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        # Equality must match the hash logic
        if not isinstance(other, Preset):
            return False
        return self.name == other.name

    @classmethod
    def json_dump_list(cls, presets: list):
        return json.dumps([asdict(mc) for mc in presets])

    def json_dump(self):
        return json.dumps(asdict(self))

    @classmethod
    def json_load(cls, json_string: str):
        return Preset(**json.loads(json_string))


class SettingsStore:
    """Holds the presets and music categories and persists them through the settings backend."""

    def __init__(self, backend: JsonSettings):
        self._backend = backend
        self._presets: list[Preset] | None = None
        self._music_categories: list[MusicCategory] | None = None
        self._custom_categories_loaded = False
        self._category_keys: list[str] | None = None

    def reload(self):
        """Forget cached values so they are read from the backend again."""
        self._presets = None
        self._music_categories = None
        self._custom_categories_loaded = False
        self._category_keys = None

    # presets
    def get_presets(self) -> list[Preset]:
        if self._presets is None:
            self._presets = self._load_presets()
        return self._presets

    def _load_presets(self) -> list[Preset]:
        raw = self._backend.value(SettingKeys.PRESETS)
        if not raw:
            return []
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return [Preset(**d) for d in data if d.get("name") is not None]
        except (TypeError, ValueError, AttributeError) as e:
            logger.error("Failed to load presets: {0}", e)
            return []

    def set_presets(self, presets: list[Preset] | None):
        if presets is None:
            self._presets = []
            self._backend.remove(SettingKeys.PRESETS)
        else:
            self._presets = [preset for preset in presets if preset.name is not None]
            self._save_presets()

    def add_preset(self, preset: Preset):
        self.get_presets().append(preset)
        self._save_presets()

    def remove_preset(self, preset: Preset):
        self.get_presets().remove(preset)
        self._save_presets()

    def reset_presets(self):
        self._presets = []
        self._backend.remove(SettingKeys.PRESETS)

    def _save_presets(self):
        self._backend.setValue(SettingKeys.PRESETS, Preset.json_dump_list(self.get_presets()))

    # music categories
    def get_music_categories(self) -> list[MusicCategory]:
        if self._music_categories is None and not self._custom_categories_loaded:
            self._custom_categories_loaded = True
            self._music_categories = self._load_custom_categories()
        if self._music_categories is None:
            self._music_categories = [MusicCategory.from_key(key) for key in _DEFAULT_CATEGORIES]
        return self._music_categories

    def _load_custom_categories(self) -> list[MusicCategory] | None:
        raw = self._backend.value(SettingKeys.CATEGORIES)
        if not raw:
            return None
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return [MusicCategory(**d) for d in data] or None
        except (TypeError, ValueError) as e:
            logger.error("Failed to load custom categories: {0}", e)
            self._backend.remove(SettingKeys.CATEGORIES)
            return None

    def set_music_categories(self, categories: list[MusicCategory] | None):
        if categories is None:
            self._backend.remove(SettingKeys.CATEGORIES)
        else:
            self._backend.setValue(SettingKeys.CATEGORIES, MusicCategory.json_dump_list(categories))

        self._custom_categories_loaded = True
        self._category_keys = None  # rebuilt lazily from the music categories
        self._music_categories = categories

    def get_music_category(self, key: str, additional_categories: list[MusicCategory] | None = None) -> MusicCategory | None:
        for cat in self.get_music_categories() + (additional_categories or []):
            if cat.key == key:
                return cat
        return None

    def get_category_keys(self) -> list[str]:
        if self._category_keys is None:
            self._category_keys = [cat.key for cat in self.get_music_categories()]
        return self._category_keys


# Shared application-wide store; the module-level functions below delegate to it.
settings = SettingsStore(AppSettings)


def get_presets() -> list[Preset]:
    return settings.get_presets()


def set_presets(presets: list[Preset] | None):
    settings.set_presets(presets)


def add_preset(preset: Preset):
    settings.add_preset(preset)


def remove_preset(preset: Preset):
    settings.remove_preset(preset)


def reset_presets():
    settings.reset_presets()


def get_music_categories() -> list[MusicCategory]:
    return settings.get_music_categories()


def set_music_categories(categories: list[MusicCategory] | None):
    settings.set_music_categories(categories)


def get_music_category(key: str, additional_categories: list[MusicCategory] | None = None) -> MusicCategory | None:
    return settings.get_music_category(key, additional_categories)


def get_category_keys() -> list[str]:
    return settings.get_category_keys()


class FilterConfig:
    categories: dict[str, int]
    tags: list[str]
    bpm: int | None
    genres: list[str]

    def __init__(self, categories: dict[str, int] | None = None, tags: list[str] | None = None, bpm: int | None = None,
                 genres: list[str] | None = None):
        self.categories = categories if categories is not None else {}
        self.tags = tags if tags is not None else []
        self.bpm = bpm
        self.genres = genres if genres is not None else []

    def get_category(self, category_key: str, default: int = None) -> int:
        value = self.categories.get(category_key, default)
        return value if value is not None and value >= 0 else None

    def toggle_tag(self, tag: str, state: int):
        if state == 0:
            if tag in self.tags:
                self.tags.remove(tag)
        elif tag not in self.tags:
            self.tags.append(tag)

    def toggle_genre(self, genre: str, state: int):
        if state == 0:
            if genre in self.genres:
                self.genres.remove(genre)
        elif genre not in self.genres:
            self.genres.append(genre)

    def clear(self):
        self.genres.clear()
        self.tags.clear()
        self.bpm = None
        self.categories.clear()

    def empty(self) -> bool:
        no_categories = all(value is None for value in self.categories.values())
        return no_categories and not self.tags and self.bpm is None and not self.genres
