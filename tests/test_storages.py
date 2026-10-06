"""Storage configuration API: credentials are write-only and kept when an edit omits them."""
import pytest
from fastapi.testclient import TestClient

from core.settings import AppSettings, SettingKeys
from core.storage.s3 import S3Storage
from fake_s3 import FakeS3Client
from server import roots as roots_module
from server.app import create_app
from server.config import ServerConfig


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    roots_module.reset_remote_cache()


def test_save_list_and_hide_credentials(client):
    saved = client.put("/api/storages", json=[{"name": "Cloud Music", "bucket": "music", "prefix": "/rpg/", "endpoint_url": "https://r2.test",
                                               "access_key": "AK", "secret_key": "SK", "direct": True}]).json()

    storage = saved["storages"][0]
    assert storage == {"id": "cloud-music", "name": "Cloud Music", "bucket": "music", "prefix": "rpg", "endpoint_url": "https://r2.test",
                       "public_endpoint_url": "", "region": "", "direct": True, "has_credentials": True}
    assert "SK" not in client.get("/api/storages").text
    stored = AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list)[0]
    assert (stored["access_key"], stored["secret_key"], stored["direct"]) == ("AK", "SK", True)


def test_edit_keeps_credentials_unless_replaced_or_cleared(client):
    client.put("/api/storages", json=[{"name": "Cloud", "bucket": "music", "access_key": "AK", "secret_key": "SK"}])

    client.put("/api/storages", json=[{"id": "cloud", "name": "Cloud", "bucket": "other"}])
    stored = AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list)[0]
    assert (stored["id"], stored["bucket"], stored["secret_key"]) == ("cloud", "other", "SK")

    client.put("/api/storages", json=[{"id": "cloud", "bucket": "other", "secret_key": "NEW"}])
    assert AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list)[0]["secret_key"] == "NEW"

    client.put("/api/storages", json=[{"id": "cloud", "bucket": "other", "access_key": "", "secret_key": ""}])
    assert client.get("/api/storages").json()["storages"][0]["has_credentials"] is False


def test_ids_are_unique_and_stable(client):
    saved = client.put("/api/storages", json=[{"name": "Music", "bucket": "a"}, {"name": "Music", "bucket": "b"}]).json()
    assert [s["id"] for s in saved["storages"]] == ["music", "music-2"]

    renamed = client.put("/api/storages", json=[{"id": "music", "name": "Renamed", "bucket": "a"}, {"id": "music-2", "name": "Music", "bucket": "b"}])
    assert [s["id"] for s in renamed.json()["storages"]] == ["music", "music-2"]


def test_remove_all_and_validation(client):
    client.put("/api/storages", json=[{"name": "x", "bucket": "a"}])
    assert client.put("/api/storages", json=[]).json()["storages"] == []
    assert client.put("/api/storages", json=[{"bucket": "  "}]).status_code == 400


def test_connection_test(client, monkeypatch):
    fake = FakeS3Client()
    fake.objects["rpg/a.mp3"] = b"x"
    monkeypatch.setattr("server.routes.storages.create_storage", lambda config: S3Storage(config["bucket"], prefix=config["prefix"], client=fake))
    assert client.post("/api/storages/test", json={"bucket": "b", "prefix": "rpg"}).json() == {"ok": True, "entries": 1}

    def broken(config):
        raise RuntimeError("S3 storage needs boto3")
    monkeypatch.setattr("server.routes.storages.create_storage", broken)
    failed = client.post("/api/storages/test", json={"bucket": "b"})
    assert failed.status_code == 400 and "boto3" in failed.json()["detail"]



def test_storage_without_id_keeps_its_credentials_when_edited(client):
    # as written by hand or from DT_S3_* variables of older versions: no id
    AppSettings.setValue(SettingKeys.STORAGE_ROOTS, [{"type": "s3", "name": "S3 (RustFS)", "bucket": "music", "access_key": "AK", "secret_key": "SK"}])

    listed = client.get("/api/storages").json()["storages"][0]
    assert listed["id"] == "s3-rustfs" and listed["has_credentials"] is True

    client.put("/api/storages", json=[{**{k: listed[k] for k in ("id", "name", "bucket")}, "direct": True}])
    stored = AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list)[0]
    assert (stored["id"], stored["secret_key"], stored["direct"]) == ("s3-rustfs", "SK", True)


def test_environment_storage_keeps_storages_from_the_dialog(monkeypatch, tmp_path):
    from server.__main__ import main
    import server.__main__ as entry

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    AppSettings.set_path(data_dir / "settings.json")  # --data-dir switches to this settings file
    AppSettings.setValue(SettingKeys.STORAGE_ROOTS, [{"id": "mine", "bucket": "own"}, {"id": "env-bucket", "bucket": "old"}])
    monkeypatch.setenv("DT_S3_BUCKET", "env-bucket")
    monkeypatch.setenv("DT_S3_ACCESS_KEY", "AK")
    monkeypatch.setattr(entry.uvicorn, "run", lambda *args, **kwargs: None)
    monkeypatch.setattr(entry, "create_app", lambda config: None)
    monkeypatch.setattr(entry, "setup_logging", lambda: None)

    assert main(["--data-dir", str(data_dir)]) == 0
    stored = AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list)
    assert [c["id"] for c in stored] == ["mine", "env-bucket"]
    assert stored[1]["access_key"] == "AK" and stored[1]["bucket"] == "env-bucket"
