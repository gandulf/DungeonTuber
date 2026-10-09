import json

from core.settings import (AppSettings, FilterConfig, MusicCategory, Preset, SettingKeys, get_category_keys, get_music_categories,
                           set_music_categories, settings)
from core.settings_backend import JsonSettings


def test_json_settings_persist_and_coerce(tmp_path):
    path = tmp_path / "s.json"
    store = JsonSettings(path)
    store.setValue("flag", "true")
    store.setValue("count", "3")
    store.setValue("items", "single")
    store.setValue(SettingKeys.LIGHTS_TIMEOUT, 70)

    reopened = JsonSettings(path)
    assert reopened.value("flag", type=bool) is True
    assert reopened.value("count", type=int) == 3
    assert reopened.value("items", type=list) == ["single"]
    assert reopened.value("lightsTimeout", type=int) == 70
    assert reopened.value("missing", 5, type=int) == 5
    assert reopened.value("missing", defaultValue="x") == "x"


def test_json_settings_invalid_value_falls_back_to_default(tmp_path):
    store = JsonSettings(tmp_path / "s.json")
    store.setValue("count", "abc")

    assert store.value("count", 7, type=int) == 7


def test_json_settings_remove(tmp_path):
    store = JsonSettings(tmp_path / "s.json")
    store.setValue("a", 1)
    store.setValue("b", 3)

    store.remove("a")
    assert not store.contains("a")
    assert set(store.allKeys()) == {"b"}


def test_corrupt_settings_file_is_ignored(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json", encoding="utf-8")

    assert JsonSettings(path).allKeys() == []


def test_default_categories():
    keys = get_category_keys()

    assert keys[:2] == ["Valence", "Arousal"]
    assert len(get_music_categories()) == 9


def test_custom_categories_are_loaded_from_settings():
    custom = [MusicCategory("Spooky", "How spooky", {1: "a bit", 10: "very"}, key="spooky")]
    AppSettings.setValue(SettingKeys.CATEGORIES, MusicCategory.json_dump_list(custom))
    settings.reload()

    assert get_category_keys() == ["spooky"]


def test_invalid_custom_categories_are_dropped():
    AppSettings.setValue(SettingKeys.CATEGORIES, "{broken")
    settings.reload()

    assert len(get_music_categories()) == 9
    assert not AppSettings.contains(SettingKeys.CATEGORIES)


def test_set_music_categories_resets_key_cache():
    get_category_keys()
    set_music_categories([MusicCategory("Epic", "", {}, key="epic")])

    assert get_category_keys() == ["epic"]

    set_music_categories(None)
    assert len(get_category_keys()) == 9


def test_preset_json_round_trip():
    preset = Preset("Fight", {"Arousal": 9}, tags=["Combat skirmish"], bpm=140)
    assert Preset.json_load(preset.json_dump()) == preset
    assert json.loads(Preset.json_dump_list([])) == []



def test_filter_config_defaults_are_not_shared():
    a = FilterConfig()
    b = FilterConfig()
    a.tags.append("Dark")
    a.categories["Valence"] = 3

    assert b.tags == []
    assert b.categories == {}


def test_filter_config_toggle_and_empty():
    config = FilterConfig()
    assert config.empty()

    config.toggle_tag("Dark", 0)  # unchecking an unknown tag must not add it
    assert config.tags == []

    config.toggle_tag("Dark", 2)
    config.toggle_genre("Rock", 2)
    assert config.tags == ["Dark"]
    assert config.genres == ["Rock"]
    assert not config.empty()

    config.clear()
    assert config.empty()
    assert config.get_category("Valence") is None


def test_translations_from_json_locales():
    from core import i18n
    from core.i18n import _

    assert {"de", "en"} <= set(i18n.available_locales())
    i18n.set_language("de_DE")
    try:
        assert i18n.language() == "de"
        assert _("Analyzing {0}...") != "Analyzing {0}..."
        assert _("not a known message") == "not a known message"
        i18n.set_language(None)  # falls back to English texts
        assert i18n.language() == "en"
        assert _("Valence Description") != "Valence Description"
    finally:
        i18n.set_language("xx")
    assert i18n.language() == "en"
