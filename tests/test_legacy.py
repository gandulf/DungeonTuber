from core import legacy
from core.legacy import REG_BINARY, REG_DWORD, REG_MULTI_SZ, REG_SZ, convert_registry_value, migrate_legacy_settings
from core.settings import AppSettings, get_presets


def test_convert_registry_values():
    assert convert_registry_value("true", REG_SZ) == "true"
    assert convert_registry_value(70, REG_DWORD) == 70
    assert convert_registry_value(["a", "b"], REG_MULTI_SZ) == ["a", "b"]
    assert convert_registry_value("@Size(1200 700)", REG_SZ) == [1200, 700]
    assert convert_registry_value("@Variant(\\0\\0)", REG_SZ) is None
    assert convert_registry_value(b"\x00", REG_BINARY) is None


def test_migration_runs_once(monkeypatch, tmp_path):
    AppSettings.set_path(tmp_path / "fresh.json")
    monkeypatch.setattr(legacy, "read_registry", lambda: {"volume": 80, "presets": '[{"name": "Fight", "categories": {}}]'})

    assert migrate_legacy_settings() == 2
    assert AppSettings.value("volume", type=int) == 80
    assert [p.name for p in get_presets()] == ["Fight"]

    monkeypatch.setattr(legacy, "read_registry", lambda: {"volume": 10})
    assert migrate_legacy_settings() == 0
    assert AppSettings.value("volume", type=int) == 80
