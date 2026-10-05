import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import write_mp3
from core.lights import fake_lights_mode, light_registry
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from server.app import create_app
from server.auth import set_password
from server.config import ServerConfig
from server.index import TrackIndex, set_index
from server.paths import path_to_id


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    write_mp3(root / "Battle" / "drums.mp3")
    write_mp3(root / "Tavern" / "inn.mp3")
    (root / "notes.txt").write_text("ignored")
    outside = write_mp3(tmp_path / "secret" / "hidden.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    return {"root": root, "outside": outside}


@pytest.fixture
def client(tmp_path, library):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)
    light_registry.lights.clear()
    light_registry.fake_bulbs = False


def _id(path):
    return path_to_id(path)


def test_browse_and_roots(client, library):
    roots = client.get("/api/roots").json()
    assert roots[0]["path"] == library["root"].resolve().as_posix()

    listing = client.get("/api/browse", params={"path": roots[0]["path"]}).json()
    assert [item["name"] for item in listing["items"]] == ["Battle", "Tavern"]
    assert listing["parent"] is None

    battle = client.get("/api/browse", params={"path": listing["items"][0]["path"]}).json()
    assert [(item["name"], item["type"]) for item in battle["items"]] == [("drums", "mp3"), ("fight", "mp3")]


def test_paths_outside_library_are_rejected(client, library):
    assert client.get("/api/browse", params={"path": library["outside"].parent.as_posix()}).status_code == 403
    assert client.get(f"/media/tracks/{_id(library['outside'])}").status_code == 403
    assert client.get("/api/browse", params={"path": (library["root"] / ".." / "secret").as_posix()}).status_code == 403


def test_tracks_of_directory(client, library):
    data = client.get("/api/tracks", params={"dir": library["root"].as_posix()}).json()

    assert data["type"] == "dir"
    assert sorted(t["name"] for t in data["tracks"]) == ["drums", "fight", "inn"]
    assert all(t["has_cover"] is False for t in data["tracks"])


def test_patch_track_and_rename(client, library):
    song = library["root"] / "Tavern" / "inn.mp3"
    response = client.patch(f"/api/tracks/{_id(song)}", json={
        "title": "The Inn", "tags": ["Cozy", " "], "genres": ["Folk"], "bpm": 90, "favorite": True,
        "categories": {"Valence": 12, "Arousal": 3}, "light": {"color": "#FF0000", "brightness": 200},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "The Inn"
    assert data["tags"] == ["Cozy"]
    assert data["categories"] == {"Valence": 10, "Arousal": 3}
    assert data["light"]["color"] == "#ff0000"

    data = client.patch(f"/api/tracks/{data['id']}", json={"categories": {"Arousal": None}, "light": None}).json()
    assert data["categories"] == {"Valence": 10}
    assert data["light"] is None

    renamed = client.patch(f"/api/tracks/{data['id']}", json={"name": "Inn Theme"}).json()
    assert renamed["file"] == "Inn Theme.mp3"
    assert renamed["previous_id"] == data["id"]
    assert (library["root"] / "Tavern" / "Inn Theme.mp3").exists()

    assert client.patch(f"/api/tracks/{renamed['id']}", json={"name": "../evil"}).status_code == 400


def test_chapters(client, library):
    song = library["root"] / "Battle" / "fight.mp3"
    data = client.put(f"/api/tracks/{_id(song)}/chapters", json=[
        {"title": "Charge", "time": 1000, "light": {"color": "#00ff00"}}, {"title": "Start", "time": 0},
    ]).json()

    assert [c["title"] for c in data["chapters"]] == ["Start", "Charge"]
    assert data["chapters"][1]["light"]["color"] == "#00ff00"


def test_cover_upload_and_thumbnail(client, library):
    song = library["root"] / "Battle" / "fight.mp3"
    image = io.BytesIO()
    Image.new("RGB", (600, 400), "red").save(image, format="PNG")

    data = client.put(f"/api/tracks/{_id(song)}/cover", files={"file": ("cover.png", image.getvalue(), "image/png")}).json()
    assert data["has_cover"] is True

    thumb = client.get(f"/media/covers/{_id(song)}", params={"size": 128})
    assert thumb.status_code == 200
    assert Image.open(io.BytesIO(thumb.content)).size == (128, 85)

    assert client.put(f"/api/tracks/{_id(song)}/cover", files={"file": ("x.png", b"nope", "image/png")}).status_code == 400
    assert client.get(f"/media/covers/{_id(library['root'] / 'Tavern' / 'inn.mp3')}").status_code == 404


def test_media_supports_range_requests(client, library):
    song = library["root"] / "Battle" / "fight.mp3"
    response = client.get(f"/media/tracks/{_id(song)}", headers={"Range": "bytes=0-99"})

    assert response.status_code == 206
    assert len(response.content) == 100
    assert response.headers["content-type"] == "audio/mpeg"


def test_playlists(client, library):
    fight, drums = library["root"] / "Battle" / "fight.mp3", library["root"] / "Battle" / "drums.mp3"
    playlist = (library["root"] / "Battle Mix").as_posix()

    created = client.post("/api/playlists", json={"path": playlist, "ids": [_id(fight)]}).json()
    assert created["name"] == "Battle Mix"
    assert client.post("/api/playlists", json={"path": playlist}).status_code == 409

    client.post("/api/playlists/entries", json={"playlist": created["path"], "ids": [_id(drums)], "index": 0})
    tracks = client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"]
    assert [t["name"] for t in tracks] == ["drums", "fight"]
    assert [t["index"] for t in tracks] == [0, 1]

    client.put("/api/playlists/order", json={"playlist": created["path"], "ids": [_id(fight), _id(drums)]})
    assert [t["name"] for t in client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"]] == ["fight", "drums"]

    client.post("/api/playlists/remove", json={"playlist": created["path"], "ids": [_id(fight), _id(drums)]})
    assert client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"] == []


def test_upload_and_move(client, library):
    tavern = (library["root"] / "Tavern").as_posix()
    mp3_bytes = write_mp3(library["root"].parent / "tmp_upload.mp3").read_bytes()

    response = client.post("/api/upload", data={"dir": tavern}, files=[("files", ("new song.mp3", mp3_bytes, "audio/mpeg"))])
    assert response.status_code == 200
    assert response.json()["tracks"][0]["name"] == "new song"

    assert client.post("/api/upload", data={"dir": tavern}, files=[("files", ("x.wav", b"RIFF", "audio/wav"))]).status_code == 400
    assert client.post("/api/upload", data={"dir": tavern}, files=[("files", ("bad.mp3", b"garbage", "audio/mpeg"))]).status_code == 400
    assert not (library["root"] / "Tavern" / "bad.mp3").exists()

    moved = client.post("/api/files/move", json={"source": f"{tavern}/new song.mp3", "target_dir": (library["root"] / "Battle").as_posix()})
    assert moved.status_code == 200
    assert (library["root"] / "Battle" / "new song.mp3").exists()


def test_settings_categories_presets(client):
    settings = client.get("/api/settings").json()
    assert settings["lightsTimeout"] == 5.0

    assert client.put("/api/settings", json={"lightsTimeout": "abc"}).status_code == 400
    assert client.put("/api/settings", json={"unknown": 1}).status_code == 400
    assert client.put("/api/settings", json={"lightsTimeout": 3, "voxalyzerUrl": "http://x"}).json()["lightsTimeout"] == 3.0

    categories = client.get("/api/categories").json()
    assert len(categories) == 9
    assert client.put("/api/categories", json=[{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]).status_code == 400
    assert [c["key"] for c in client.put("/api/categories", json=[{"key": "spooky", "name": "Spooky", "levels": {"1": "low"}}]).json()] == ["spooky"]
    assert len(client.post("/api/categories/reset").json()) == 9

    presets = client.put("/api/presets", json=[{"name": "Fight", "categories": {"Arousal": 9, "Valence": None}, "bpm": 140}]).json()
    assert presets == [{"name": "Fight", "categories": {"Arousal": 9}, "tags": [], "genres": [], "bpm": 140}]


def test_effects(client, library, tmp_path):
    effects_dir = tmp_path / "effects"
    write_mp3(effects_dir / "Rain" / "1 light.mp3")
    write_mp3(effects_dir / "Rain" / "2 heavy.mp3")
    (effects_dir / "Rain" / "cover.jpg").write_bytes(b"jpg")
    write_mp3(effects_dir / "Thunder.mp3")
    AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, effects_dir.as_posix())

    data = client.get("/api/effects").json()

    assert [e["name"] for e in data["effects"]] == ["Rain", "Thunder"]
    rain = data["effects"][0]
    assert len(rain["intensities"]) == 2
    assert rain["cover_url"].startswith("/media/files/")
    assert client.get(rain["cover_url"]).status_code == 200
    # effects directory counts as library root, so its tracks can be streamed
    assert client.get(f"/media/tracks/{rain['intensities'][0]['id']}").status_code == 200


def test_analysis_with_mock_backend(client, library):
    song = library["root"] / "Battle" / "fight.mp3"
    response = client.post("/api/analysis", json={"paths": [song.as_posix()]})
    assert response.json()["queued"] == 1

    import time
    for _ in range(50):
        if client.get("/api/analysis").json()["pending"] == 0:
            break
        time.sleep(0.05)
    assert parse_mp3(song).categories


def test_fake_lights(client):
    fake_lights_mode()

    data = client.post("/api/lights/discover").json()
    assert len(data["lights"]) == 3
    mac = data["lights"][0]["mac"]

    light = client.patch(f"/api/lights/{mac}", json={"name": "Desk", "state": True, "color": "#00ff00"}).json()
    assert light["name"] == "Desk"
    assert light["color"] == "#00ff00"
    assert light["temperature"] is None

    light = client.patch(f"/api/lights/{mac}", json={"temperature": 3000}).json()
    assert light["color"] is None and light["temperature"] == 3000

    assert client.post("/api/lights/cue", json={"color": "#0000ff"}).json()["applied"] == 3
    assert client.patch("/api/lights/unknown", json={"state": True}).status_code == 404


def test_websocket_receives_events(client, library):
    song = library["root"] / "Tavern" / "inn.mp3"
    with client.websocket_connect("/ws") as ws:
        client.patch(f"/api/tracks/{_id(song)}", json={"title": "Live"})
        message = ws.receive_json()
    assert message["event"] == "track.updated"
    assert message["data"]["title"] == "Live"


def test_auth_required_once_password_is_set(client):
    assert client.get("/api/auth/me").json()["authenticated"] is True

    set_password("secret")
    assert client.get("/api/settings").status_code == 401
    assert client.post("/api/auth/login", json={"password": "wrong"}).status_code == 401

    assert client.post("/api/auth/login", json={"password": "secret"}).status_code == 200
    assert client.get("/api/settings").status_code == 200

    client.post("/api/auth/logout")
    client.cookies.clear()
    assert client.get("/api/settings").status_code == 401


def test_spa_fallback_without_build(client):
    assert client.get("/").status_code == 404
    assert client.get("/api/nope").status_code == 404
