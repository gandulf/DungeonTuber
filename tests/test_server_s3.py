"""The server against an S3 backed library root (in-memory fake client): metadata lives in the database only."""
import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import write_mp3
from core.settings import AppSettings, SettingKeys
from core.storage.s3 import S3Storage
from fake_s3 import FakeS3Client
from server import roots as roots_module
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index
from server.paths import path_to_id

BASE = "s3://music"
ROOT_CONFIG = {"type": "s3", "id": "music", "name": "Cloud", "bucket": "b", "prefix": "rpg"}


@pytest.fixture
def s3(tmp_path, monkeypatch):
    fake = FakeS3Client()
    monkeypatch.setattr(roots_module, "create_storage",
                        lambda config: S3Storage(config["bucket"], prefix=config.get("prefix", ""), client=fake, name=config.get("name", "")))
    roots_module._remote_cache.clear()
    sample = write_mp3(tmp_path / "sample.mp3").read_bytes()
    for key in ("rpg/Battle/fight.mp3", "rpg/Battle/drums.mp3", "rpg/Tavern/inn.mp3"):
        fake.objects[key] = sample
    fake.objects["rpg/notes.txt"] = b"ignored"
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [])
    AppSettings.setValue(SettingKeys.STORAGE_ROOTS, [ROOT_CONFIG])
    return fake


@pytest.fixture
def client(tmp_path, s3):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)
    roots_module._remote_cache.clear()


def _id(path):
    return path_to_id(path)


def _wait_for_import(client, folder):
    for _ in range(100):
        tracks = client.get("/api/tracks", params={"dir": f"{BASE}/{folder}"}).json()["tracks"]
        if not any(t.get("pending") for t in tracks):
            return tracks
        time.sleep(0.05)
    raise AssertionError("import did not finish")


def test_roots_and_browse(client):
    roots = client.get("/api/roots").json()
    assert roots == [{"name": "Cloud", "path": BASE, "id": _id(BASE), "type": "dir", "storage": "s3"}]

    listing = client.get("/api/browse", params={"path": BASE}).json()
    assert [(i["name"], i["type"]) for i in listing["items"]] == [("Battle", "dir"), ("Tavern", "dir")]
    assert listing["parent"] is None

    battle = client.get("/api/browse", params={"path": f"{BASE}/Battle"}).json()
    assert [(i["name"], i["type"]) for i in battle["items"]] == [("drums", "mp3"), ("fight", "mp3")]
    assert battle["parent"] == BASE


def test_unknown_root_and_traversal_are_rejected(client):
    assert client.get("/api/browse", params={"path": "s3://other"}).status_code == 403
    assert client.get("/api/browse", params={"path": f"{BASE}/../x"}).status_code in (400, 403)


def test_tracks_are_imported_in_the_background(client):
    first = client.get("/api/tracks", params={"dir": f"{BASE}/Battle"}).json()["tracks"]
    assert sorted(t["name"] for t in first) == ["drums", "fight"]

    tracks = _wait_for_import(client, "Battle")
    assert all(t["length"] >= 0 and "pending" not in t for t in tracks)


def test_edits_stay_in_the_database_and_rename_follows(client, s3):
    song = f"{BASE}/Tavern/inn.mp3"
    before = s3.objects["rpg/Tavern/inn.mp3"]

    data = client.patch(f"/api/tracks/{_id(song)}", json={"title": "The Inn", "tags": ["Cozy"], "favorite": True,
                                                          "categories": {"Valence": 12}, "light": {"color": "#FF0000"}}).json()
    assert (data["title"], data["tags"], data["favorite"], data["categories"]) == ("The Inn", ["Cozy"], True, {"Valence": 10})
    assert data["light"]["color"] == "#ff0000"
    assert s3.objects["rpg/Tavern/inn.mp3"] == before  # the object itself is never rewritten

    renamed = client.patch(f"/api/tracks/{data['id']}", json={"name": "Inn Theme"}).json()
    assert renamed["file"] == "Inn Theme.mp3" and renamed["title"] == "The Inn"
    assert "rpg/Tavern/Inn Theme.mp3" in s3.objects and "rpg/Tavern/inn.mp3" not in s3.objects
    assert client.get(f"/api/tracks/{renamed['id']}").json()["favorite"] is True


def test_cover_is_stored_in_the_database(client):
    song = f"{BASE}/Battle/fight.mp3"
    image = io.BytesIO()
    Image.new("RGB", (600, 400), "red").save(image, format="PNG")

    assert client.put(f"/api/tracks/{_id(song)}/cover", files={"file": ("c.png", image.getvalue(), "image/png")}).json()["has_cover"] is True
    thumb = client.get(f"/media/covers/{_id(song)}", params={"size": 128})
    assert Image.open(io.BytesIO(thumb.content)).size == (128, 85)
    assert client.get(f"/media/covers/{_id(f'{BASE}/Battle/drums.mp3')}").status_code == 404


def test_media_is_proxied_with_range_support(client, s3):
    song = f"{BASE}/Battle/fight.mp3"
    whole = client.get(f"/media/tracks/{_id(song)}")
    assert whole.status_code == 200 and whole.content == s3.objects["rpg/Battle/fight.mp3"]

    part = client.get(f"/media/tracks/{_id(song)}", headers={"Range": "bytes=10-19"})
    assert part.status_code == 206 and part.content == whole.content[10:20]
    assert part.headers["content-range"] == f"bytes 10-19/{len(whole.content)}"
    assert client.get(f"/media/tracks/{_id(song)}", headers={"Range": "bytes=999999999-"}).status_code == 416


def test_media_redirects_to_presigned_url_when_direct(client):
    AppSettings.setValue(SettingKeys.STORAGE_ROOTS, [{**ROOT_CONFIG, "direct": True}])

    response = client.get(f"/media/tracks/{_id(f'{BASE}/Battle/fight.mp3')}", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://example.test/b/rpg/Battle/fight.mp3")


def test_playlists(client, s3):
    fight, drums = f"{BASE}/Battle/fight.mp3", f"{BASE}/Battle/drums.mp3"
    created = client.post("/api/playlists", json={"path": f"{BASE}/Mix", "ids": [_id(fight)]}).json()
    assert created["path"] == f"{BASE}/Mix.m3u"
    assert client.post("/api/playlists", json={"path": f"{BASE}/Mix"}).status_code == 409

    client.post("/api/playlists/entries", json={"playlist": created["path"], "ids": [_id(drums)], "index": 0})
    assert b"Battle/drums.mp3" in s3.objects["rpg/Mix.m3u"]
    names = [t["name"] for t in client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"]]
    assert names == ["drums", "fight"]

    client.post("/api/playlists/remove", json={"playlist": created["path"], "ids": [_id(fight)]})
    assert [t["name"] for t in client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"]] == ["drums"]


def test_upload_move_and_folder(client, s3, tmp_path):
    content = write_mp3(tmp_path / "new.mp3").read_bytes()
    uploaded = client.post("/api/upload", data={"dir": f"{BASE}/Tavern"}, files={"files": ("new.mp3", content, "audio/mpeg")}).json()
    assert uploaded["tracks"][0]["file"] == "new.mp3" and "pending" not in uploaded["tracks"][0]
    assert s3.objects["rpg/Tavern/new.mp3"] == content
    assert client.post("/api/upload", data={"dir": f"{BASE}/Tavern"}, files={"files": ("new.mp3", content, "audio/mpeg")}).status_code == 409
    assert client.post("/api/upload", data={"dir": f"{BASE}/Tavern"}, files={"files": ("bad.mp3", b"nope", "audio/mpeg")}).status_code == 400

    assert client.post("/api/files/folder", data={"parent": BASE, "name": "Boss"}).status_code == 200
    moved = client.post("/api/files/move", json={"source": f"{BASE}/Tavern/new.mp3", "target_dir": f"{BASE}/Boss"}).json()
    assert moved["path"] == f"{BASE}/Boss/new.mp3" and "rpg/Boss/new.mp3" in s3.objects
    assert client.get(f"/api/tracks/{moved['id']}").status_code == 200


def test_cannot_move_between_roots(client, tmp_path):
    local = tmp_path / "local"
    local.mkdir()
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [local.as_posix()])

    assert client.post("/api/files/move", json={"source": f"{BASE}/Tavern/inn.mp3", "target_dir": local.as_posix()}).status_code == 400


def test_analysis_is_stored_in_the_database(client, s3):
    song = f"{BASE}/Battle/fight.mp3"
    before = s3.objects["rpg/Battle/fight.mp3"]
    assert client.post("/api/analysis", json={"paths": [f"{BASE}/Battle"]}).json()["queued"] == 2

    for _ in range(100):
        if client.get("/api/analysis").json()["pending"] == 0:
            break
        time.sleep(0.05)
    assert client.get(f"/api/tracks/{_id(song)}").json()["categories"]
    assert s3.objects["rpg/Battle/fight.mp3"] == before


def test_effects_folder_inside_a_remote_root(client, s3):
    sample = s3.objects["rpg/Battle/fight.mp3"]
    s3.objects["rpg/Effects/Rain/1 light.mp3"] = sample
    s3.objects["rpg/Effects/Rain/2 heavy.mp3"] = sample
    s3.objects["rpg/Effects/Rain/cover.jpg"] = b"jpg"
    s3.objects["rpg/Effects/Thunder.mp3"] = sample
    AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, f"{BASE}/Effects")

    data = client.get("/api/effects").json()

    assert data["directory"] == f"{BASE}/Effects"
    assert [e["name"] for e in data["effects"]] == ["Rain", "Thunder"]
    rain = data["effects"][0]
    assert [i["file"] for i in rain["intensities"]] == ["1 light.mp3", "2 heavy.mp3"]
    assert client.get(rain["cover_url"]).content == b"jpg"
    assert client.get(f"/media/tracks/{rain['intensities'][0]['id']}").status_code == 200


def test_rescan_picks_up_bucket_changes(client, s3, tmp_path):
    _wait_for_import(client, "Battle")
    _wait_for_import(client, "Tavern")
    client.patch(f"/api/tracks/{_id(f'{BASE}/Battle/fight.mp3')}", json={"title": "Edited"})
    client.patch(f"/api/tracks/{_id(f'{BASE}/Battle/drums.mp3')}", json={"title": "Kept"})

    # nothing changed in the bucket: edits survive and nothing is queued
    assert client.post("/api/library/rescan", json={"path": BASE}).json() == {"added": 0, "changed": 0, "removed": 0, "total": 3}

    sample = s3.objects["rpg/Battle/fight.mp3"]
    s3.objects["rpg/Tavern/new.mp3"] = sample                      # new
    s3.objects["rpg/Battle/fight.mp3"] = sample + b"\0" * 417      # replaced
    del s3.objects["rpg/Tavern/inn.mp3"]                           # deleted

    assert client.post("/api/library/rescan").json() == {"added": 1, "changed": 1, "removed": 1, "total": 3}
    tracks = {t["file"]: t for t in _wait_for_import(client, "Tavern")}
    assert sorted(tracks) == ["new.mp3"]
    battle = {t["file"]: t for t in _wait_for_import(client, "Battle")}
    assert battle["drums.mp3"]["title"] == "Kept"
    assert client.get(f"/api/tracks/{_id(f'{BASE}/Tavern/inn.mp3')}").status_code == 404


def test_rescan_rejects_paths_outside_the_library(client):
    assert client.post("/api/library/rescan", json={"path": "s3://other"}).status_code == 403


def test_moving_a_directory_carries_all_its_tracks(client, s3):
    _wait_for_import(client, "Battle")
    client.patch(f"/api/tracks/{_id(f'{BASE}/Battle/fight.mp3')}", json={"title": "Edited"})
    client.post("/api/files/folder", data={"parent": BASE, "name": "50%_off"})

    moved = client.post("/api/files/move", json={"source": f"{BASE}/Battle", "target_dir": f"{BASE}/50%_off"}).json()

    assert moved["path"] == f"{BASE}/50%_off/Battle"
    tracks = {t["file"]: t for t in client.get("/api/tracks", params={"dir": moved["path"]}).json()["tracks"]}
    assert sorted(tracks) == ["drums.mp3", "fight.mp3"] and tracks["fight.mp3"]["title"] == "Edited"
    assert client.get("/api/tracks", params={"dir": f"{BASE}/Tavern"}).status_code == 200
    # rescan right after a move finds nothing new or changed
    assert client.post("/api/library/rescan", json={"path": BASE}).json()["changed"] == 0


def test_playlists_can_mix_local_and_remote_songs(client, s3, tmp_path):
    local_root = tmp_path / "local"
    write_mp3(local_root / "Camp" / "fire.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [local_root.as_posix()])
    local_song = (local_root / "Camp" / "fire.mp3").resolve().as_posix()
    remote_song = f"{BASE}/Battle/fight.mp3"

    def names(playlist):
        return [t["name"] for t in client.get("/api/tracks", params={"playlist": playlist}).json()["tracks"]]

    # local playlist: a local song stays relative, the remote one is stored with its full path
    local_playlist = client.post("/api/playlists", json={"path": (local_root / "Mix").resolve().as_posix(), "ids": [_id(local_song)]}).json()["path"]
    client.post("/api/playlists/entries", json={"playlist": local_playlist, "ids": [_id(remote_song)]})
    text = (local_root / "Mix.m3u").read_text(encoding="utf-8")
    assert "Camp/fire.mp3" in text and remote_song in text
    assert names(local_playlist) == ["fire", "fight"]

    # remote playlist with a local song
    remote_playlist = client.post("/api/playlists", json={"path": f"{BASE}/Mix", "ids": [_id(remote_song)]}).json()["path"]
    client.post("/api/playlists/entries", json={"playlist": remote_playlist, "ids": [_id(local_song)]})
    assert b"Battle/fight.mp3" in s3.objects["rpg/Mix.m3u"] and local_song.encode() in s3.objects["rpg/Mix.m3u"]
    assert names(remote_playlist) == ["fight", "fire"]

    # and removing works across storages as well
    client.post("/api/playlists/remove", json={"playlist": local_playlist, "ids": [_id(remote_song)]})
    assert names(local_playlist) == ["fire"]
