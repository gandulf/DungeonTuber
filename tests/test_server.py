import io
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import write_mp3
from core.lights import fake_lights_mode, light_registry
from core.settings import AppSettings, SettingKeys
from server.app import create_app
from server.auth import set_password
from server.config import ServerConfig
from server.index import TrackIndex, get_index, set_index
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
    assert data["track"] is None
    assert client.patch(f"/api/tracks/{_id(song)}", json={"track": 4}).json()["track"] == 4
    assert client.get(f"/api/tracks/{_id(song)}").json()["track"] == 4
    assert client.patch(f"/api/tracks/{_id(song)}", json={"track": -1}).status_code == 422
    assert client.patch(f"/api/tracks/{_id(song)}", json={"track": None}).json()["track"] is None

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


def test_scene_names_are_kept_in_the_playlist(client, library):
    root = library["root"]
    fight, drums, inn = (_id((root / rel).as_posix()) for rel in ("Battle/fight.mp3", "Battle/drums.mp3", "Tavern/inn.mp3"))
    boss = client.post("/api/playlists", json={"path": (root / "Boss").as_posix(), "ids": [fight, drums]}).json()["path"]
    town = client.post("/api/playlists", json={"path": (root / "Town").as_posix(), "ids": [fight]}).json()["path"]

    def scenes(playlist):
        return {t["name"]: t["scene"] for t in client.get("/api/tracks", params={"playlist": playlist}).json()["tracks"]}

    assert scenes(boss) == {"fight": None, "drums": None}
    assert client.put("/api/playlists/scene", json={"playlist": boss, "id": fight, "scene": "Throne room\nfinale"}).status_code == 200
    assert client.put("/api/playlists/scene", json={"playlist": boss, "id": inn, "scene": "x"}).status_code == 404
    assert scenes(boss) == {"fight": "Throne room finale", "drums": None}
    assert scenes(town) == {"fight": None}  # the same song is named per playlist
    assert "#EXTINF:" in (root / "Boss.m3u").read_text() and ",Throne room finale\n" in (root / "Boss.m3u").read_text()

    # adding, reordering and removing songs keeps the names
    client.post("/api/playlists/entries", json={"playlist": boss, "ids": [inn], "index": 0})
    client.put("/api/playlists/order", json={"playlist": boss, "ids": [drums, fight, inn]})
    client.post("/api/playlists/remove", json={"playlist": boss, "ids": [drums]})
    assert scenes(boss) == {"fight": "Throne room finale", "inn": None}
    client.put("/api/playlists/scene", json={"playlist": boss, "id": fight, "scene": " "})
    assert scenes(boss) == {"fight": None, "inn": None}


def test_playlists_follow_renamed_and_moved_songs(client, library):
    root = library["root"]
    fight, inn = (_id((root / rel).as_posix()) for rel in ("Battle/fight.mp3", "Tavern/inn.mp3"))
    mix = client.post("/api/playlists", json={"path": (root / "Mix").as_posix(), "ids": [fight, inn]}).json()["path"]
    local = client.post("/api/playlists", json={"path": (root / "Battle" / "Local").as_posix(), "ids": [fight, inn]}).json()["path"]
    client.put("/api/playlists/scene", json={"playlist": mix, "id": fight, "scene": "Boss"})

    def names(playlist):
        return [(t["name"], t["scene"]) for t in client.get("/api/tracks", params={"playlist": playlist}).json()["tracks"]]

    # renaming a song in the song editor
    renamed = client.patch(f"/api/tracks/{fight}", json={"name": "duel"}).json()
    assert names(mix) == [("duel", "Boss"), ("inn", None)]
    assert names(local) == [("duel", None), ("inn", None)]

    # renaming the folder of a song
    client.post("/api/files/rename", json={"path": (root / "Tavern").as_posix(), "name": "Inn"})
    assert names(mix) == [("duel", "Boss"), ("inn", None)]

    # moving a folder together with a playlist inside that refers to a song outside of it
    client.post("/api/files/folder", data={"parent": root.as_posix(), "name": "Arc"})
    moved = client.post("/api/files/move", json={"source": (root / "Battle").as_posix(), "target_dir": (root / "Arc").as_posix()})
    assert moved.status_code == 200
    assert names(mix) == [("duel", "Boss"), ("inn", None)]
    assert names((root / "Arc" / "Battle" / "Local.m3u").as_posix()) == [("duel", None), ("inn", None)]
    assert "../../Inn/inn.mp3" in (root / "Arc" / "Battle" / "Local.m3u").read_text()
    assert renamed["name"] == "duel"


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


def test_upload_keeps_directory_structure(client, library):
    tavern = (library["root"] / "Tavern").as_posix()
    mp3_bytes = write_mp3(library["root"].parent / "tmp_upload.mp3").read_bytes()
    files = [("files", ("a.mp3", mp3_bytes, "audio/mpeg")), ("files", ("b.mp3", mp3_bytes, "audio/mpeg"))]

    response = client.post("/api/upload", data={"dir": tavern, "paths": ["Album/Disc 1/a.mp3", "Album/b.mp3"]}, files=files)
    assert response.status_code == 200
    assert (library["root"] / "Tavern" / "Album" / "Disc 1" / "a.mp3").exists()
    assert (library["root"] / "Tavern" / "Album" / "b.mp3").exists()

    escape = client.post("/api/upload", data={"dir": tavern, "paths": ["../evil/a.mp3", "b.mp3"]}, files=files)
    assert escape.status_code == 400
    assert not (library["root"] / "evil").exists()
    assert client.post("/api/upload", data={"dir": tavern, "paths": ["only-one.mp3"]}, files=files).status_code == 400


def test_settings_categories_presets(client):
    settings = client.get("/api/settings").json()
    assert settings["lightsTimeout"] == 5.0

    assert client.put("/api/settings", json={"lightsTimeout": "abc"}).status_code == 400
    assert client.put("/api/settings", json={"unknown": 1}).status_code == 400
    assert client.put("/api/settings", json={"lightsTimeout": 3}).json()["lightsTimeout"] == 3.0

    categories = client.get("/api/categories").json()
    assert len(categories) == 12
    assert client.put("/api/categories", json=[{"key": "a", "name": "A"}, {"key": "a", "name": "B"}]).status_code == 400
    assert [c["key"] for c in client.put("/api/categories", json=[{"key": "spooky", "name": "Spooky", "levels": {"1": "low"}}]).json()] == ["spooky"]
    assert len(client.post("/api/categories/reset").json()) == 12

    presets = client.put("/api/presets", json=[{"name": "Fight", "categories": {"Arousal": 9, "Valence": None}, "bpm": 140}]).json()
    assert presets == [{"name": "Fight", "categories": {"Arousal": 9}, "tags": [], "genres": [], "bpm": 140}]


def test_users_start_with_the_default_presets(client):
    defaults = client.get("/api/presets", headers={"Accept-Language": "de-DE,de;q=0.9"}).json()
    assert [p["name"] for p in defaults] == ["Taverne", "Reise & Erkundung", "Dungeon", "Kampf", "Drama & Verlust"]
    assert defaults[3]["categories"]["Aggressive"] == 8
    assert [p["name"] for p in client.get("/api/presets").json()][0] == "Tavern"

    # once changed, the own presets are kept (even an empty list); a reset brings the defaults back
    assert client.put("/api/presets", json=[]).json() == []
    assert client.get("/api/presets").json() == []
    assert len(client.post("/api/presets/reset").json()) == 5
    assert len(client.get("/api/presets").json()) == 5


def _login_as_anna(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})


def test_presets_and_view_settings_belong_to_the_user(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.put("/api/presets", json=[{"name": "Admin", "categories": {}}])
    client.put("/api/user/state", json={"view": {"rowStyle": "large", "unknown": 1}, "locale": "de"})
    state = client.get("/api/user/state").json()
    assert state["view"] == {"rowStyle": "large"} and state["locale"] == "de"
    assert client.put("/api/user/state", json={"locale": "xx"}).status_code == 400
    assert client.put("/api/user/state", json={"view": {"columns": {"a": "x" * 30000}}}).status_code == 413

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert "Admin" not in [p["name"] for p in client.get("/api/presets").json()]  # anna gets the defaults, not the presets of the admin
    assert client.get("/api/user/state").json()["view"] is None and client.get("/api/user/state").json()["locale"] == ""
    assert [p["name"] for p in client.put("/api/presets", json=[{"name": "Anna", "categories": {}}]).json()] == ["Anna"]

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"password": "secret"})
    assert [p["name"] for p in client.get("/api/presets").json()] == ["Admin"]


def test_only_the_admin_changes_the_categories(client):
    _login_as_anna(client)

    assert len(client.get("/api/categories").json()) == 12
    assert client.put("/api/categories", json=[{"key": "a", "name": "A"}]).status_code == 403
    assert client.post("/api/categories/reset").status_code == 403


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


def test_analysis_needs_an_agent(client, library):
    song = library["root"] / "Battle" / "fight.mp3"

    assert client.get("/api/analysis").json()["backend"] is None
    assert client.get("/api/settings").json()["voxalyzerActive"] is False
    assert client.post("/api/analysis", json={"paths": [song.as_posix()]}).status_code == 409


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


def test_health_needs_no_login(client):
    set_password("secret")
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/settings").status_code == 401


def test_desktop_mode_never_asks_this_computer_for_a_password(client):
    from server.config import configure, get_config

    previous = get_config()
    configure(ServerConfig(local_mode=True, web_dir=previous.web_dir))
    try:
        set_password("secret")
        assert client.get("/api/settings").status_code == 200  # TestClient counts as this computer
        assert client.get("/api/auth/me").json()["local"] is True
    finally:
        configure(previous)


def test_share_on_network_settings(client):
    assert client.get("/api/settings").json()["shareOnNetwork"] is False
    assert client.put("/api/settings", json={"sharePort": 80}).status_code == 400
    data = client.put("/api/settings", json={"shareOnNetwork": True, "sharePort": 9000}).json()
    assert data["shareOnNetwork"] is True
    assert data["networkUrl"].endswith(":9000")


def test_environment_library_paths(monkeypatch, tmp_path):
    import os
    from server.__main__ import _env_paths

    monkeypatch.setenv("DT_LIBRARY", os.pathsep.join([str(tmp_path / "a"), str(tmp_path / "b")]))
    assert _env_paths("DT_LIBRARY") == [tmp_path / "a", tmp_path / "b"]
    monkeypatch.delenv("DT_LIBRARY")
    assert _env_paths("DT_LIBRARY") is None


def test_effects_directory_inside_library_is_no_extra_root(client, library):
    AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, (library["root"] / "Battle").as_posix())
    assert len(client.get("/api/roots").json()) == 1


def test_users_are_managed_by_the_superadmin(client, library):
    assert client.post("/api/users", json={"name": "anna", "password": "pw1234"}).status_code == 400  # no admin password yet
    set_password("secret")
    assert client.post("/api/auth/login", json={"password": "secret"}).json()["is_admin"] is True

    assert client.post("/api/users", json={"name": "anna", "password": "pw1234"}).status_code == 200
    assert client.post("/api/users", json={"name": "Anna", "password": "pw1234"}).status_code == 409
    assert client.post("/api/users", json={"name": "admin", "password": "pw1234"}).status_code == 409
    assert client.post("/api/users", json={"name": "x y", "password": "pw1234"}).status_code == 400
    assert client.post("/api/users", json={"name": "bob", "password": "12"}).status_code == 400
    assert [u["name"] for u in client.get("/api/users").json()] == ["admin", "anna"]
    assert "hash" not in client.get("/api/users").json()[1]
    assert client.put("/api/auth/password", json={"password": None}).status_code == 400  # users still exist

    # a regular user can sign in, but not administrate
    client.post("/api/auth/logout")
    assert client.get("/api/users").status_code == 401
    assert client.post("/api/auth/login", json={"username": "anna", "password": "secret"}).status_code == 401
    assert client.post("/api/auth/login", json={"username": "ANNA", "password": "pw1234"}).json() == {"authenticated": True, "user": "anna", "is_admin": False}
    assert client.get("/api/auth/me").json()["user"] == "anna"
    assert client.get("/api/users").status_code == 403
    assert client.put("/api/settings", json={"locale": "en"}).status_code == 403
    assert client.get("/api/roots").status_code == 200
    assert client.put("/api/auth/me/password", json={"password": "newpass"}).status_code == 200

    # deleting the user ends the session
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"password": "secret"})
    assert client.delete("/api/users/anna").status_code == 200
    assert client.post("/api/auth/login", json={"username": "anna", "password": "newpass"}).status_code == 401


def test_upload_remembers_the_user(client, library):
    set_password("secret")
    tavern = (library["root"] / "Tavern").as_posix()
    mp3_bytes = write_mp3(library["root"].parent / "tmp_upload.mp3").read_bytes()
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})

    def upload(name):
        return client.post("/api/upload", data={"dir": tavern}, files=[("files", (name, mp3_bytes, "audio/mpeg"))]).json()["tracks"][0]

    assert upload("by admin.mp3")["uploaded_by"] == "admin"
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    track = upload("by anna.mp3")
    assert track["uploaded_by"] == "anna" and track["uploaded_at"]

    listing = {t["name"]: t for t in client.get("/api/tracks", params={"dir": tavern}).json()["tracks"]}
    assert listing["by anna"]["uploaded_by"] == "anna" and listing["by admin"]["uploaded_by"] == "admin"
    assert "uploaded_by" not in listing["inn"]

    # edits keep the uploader, and a move follows the file
    assert client.patch(f"/api/tracks/{track['id']}", json={"title": "x"}).json()["uploaded_by"] == "anna"
    moved = client.post("/api/files/move", json={"source": f"{tavern}/by anna.mp3", "target_dir": (library["root"] / "Battle").as_posix()}).json()
    assert client.get(f"/api/tracks/{moved['id']}").json()["uploaded_by"] == "anna"


def test_favorites_and_open_tabs_are_per_user(client, library):
    set_password("secret")
    song = library["root"] / "Battle" / "fight.mp3"
    root = library["root"].as_posix()
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})

    assert client.patch(f"/api/tracks/{_id(song)}", json={"favorite": True}).json()["favorite"] is True
    assert client.put("/api/user/state", json={"favorites": [f"{root}/Battle", f"{root}/Battle"],
                                               "tabs": {"open": [{"type": "dir", "path": f"{root}/Battle"}], "active": f"dir:{root}/Battle"}}).status_code == 200
    state = client.get("/api/user/state").json()
    assert state["favorites"] == [f"{root}/Battle"] and state["tabs"]["open"][0]["path"] == f"{root}/Battle"

    # anna starts with nothing and her changes do not touch the SuperAdmin's
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert client.get(f"/api/tracks/{_id(song)}").json()["favorite"] is False
    assert client.get("/api/user/state").json() == {"favorites": [], "tabs": None, "accent": "", "tour_done": False, "tour_seen": [], "news_off": False, "player": None, "view": None, "locale": ""}
    assert client.patch(f"/api/tracks/{_id(song)}", json={"favorite": True}).json()["favorite"] is True
    client.put("/api/user/state", json={"favorites": [f"{root}/Tavern"]})
    drums = library["root"] / "Battle" / "drums.mp3"
    assert client.patch(f"/api/tracks/{_id(drums)}", json={"favorite": True}).status_code == 200
    assert client.patch(f"/api/tracks/{_id(song)}", json={"favorite": False}).json()["favorite"] is False

    client.post("/api/auth/login", json={"password": "secret"})
    assert client.get(f"/api/tracks/{_id(song)}").json()["favorite"] is True
    assert client.get(f"/api/tracks/{_id(drums)}").json()["favorite"] is False
    assert client.get("/api/user/state").json()["favorites"] == [f"{root}/Battle"]
    listing = {t["name"]: t["favorite"] for t in client.get("/api/tracks", params={"dir": f"{root}/Battle"}).json()["tracks"]}
    assert listing == {"fight": True, "drums": False}

    # a deleted user takes the personal data along
    client.delete("/api/users/anna")
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert client.get("/api/user/state").json() == {"favorites": [], "tabs": None, "accent": "", "tour_done": False, "tour_seen": [], "news_off": False, "player": None, "view": None, "locale": ""}
    assert client.get(f"/api/tracks/{_id(drums)}").json()["favorite"] is False


def test_adding_a_song_twice_to_a_playlist_is_ignored(client, library):
    fight, drums = library["root"] / "Battle" / "fight.mp3", library["root"] / "Battle" / "drums.mp3"
    created = client.post("/api/playlists", json={"path": (library["root"] / "Mix.m3u").as_posix(), "ids": [_id(fight)]}).json()

    def add(*ids, index=-1):
        return client.post("/api/playlists/entries", json={"playlist": created["path"], "ids": list(ids), "index": index}).json()["added"]

    assert add(_id(fight)) == 0
    assert add(_id(fight), _id(drums), _id(drums), index=0) == 1
    names = [t["name"] for t in client.get("/api/tracks", params={"playlist": created["path"]}).json()["tracks"]]
    assert names == ["drums", "fight"]


def test_users_delete_only_what_they_uploaded(client, library):
    set_password("secret")
    root = library["root"]
    tavern = (root / "Tavern").as_posix()
    mp3_bytes = write_mp3(root.parent / "tmp_upload.mp3").read_bytes()
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/users", json={"name": "bob", "password": "pw1234"})

    def upload(path):
        return client.post("/api/upload", data={"dir": tavern, "paths": [path]}, files=[("files", ("x.mp3", mp3_bytes, "audio/mpeg"))])

    def delete(path):
        return client.delete("/api/files", params={"path": path})

    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert upload("Album/one.mp3").status_code == 200
    assert upload("single.mp3").status_code == 200
    listing = {i["name"]: i.get("uploaded_by") for i in client.get("/api/browse", params={"path": tavern}).json()["items"]}
    assert listing == {"Album": "anna", "inn": None, "single": "anna"}

    # somebody else's and pre-existing files are protected
    client.post("/api/auth/login", json={"username": "bob", "password": "pw1234"})
    assert delete(f"{tavern}/single.mp3").status_code == 403
    assert delete(f"{tavern}/Album").status_code == 403
    assert delete(f"{tavern}/inn.mp3").status_code == 403
    assert client.post("/api/files/folder", data={"parent": tavern, "name": "Bobs"}).status_code == 200
    assert delete(f"{tavern}/Bobs").status_code == 200
    assert delete(root.as_posix()).status_code in (400, 403)

    # a folder anna filled together with somebody else is not hers to delete
    assert upload("Album/two.mp3").status_code == 200
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert delete(f"{tavern}/Album").status_code == 403
    assert delete(f"{tavern}/Album/one.mp3").status_code == 200
    assert not (root / "Tavern" / "Album" / "one.mp3").exists()
    assert delete(f"{tavern}/single.mp3").status_code == 200
    assert "single" not in [t["name"] for t in client.get("/api/tracks", params={"dir": tavern}).json()["tracks"]]

    # the SuperAdmin may delete anything
    client.post("/api/auth/login", json={"password": "secret"})
    assert delete(f"{tavern}/Album").status_code == 200
    assert delete(f"{tavern}/inn.mp3").status_code == 200
    assert not (root / "Tavern" / "Album").exists()


def test_private_playlists_are_only_visible_to_their_creator(client, library):
    set_password("secret")
    root = library["root"]
    battle = (root / "Battle").as_posix()
    fight = _id((root / "Battle" / "fight.mp3").as_posix())
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/users", json={"name": "bob", "password": "pw1234"})

    def names():
        return {i["name"]: i.get("private", False) for i in client.get("/api/browse", params={"path": battle}).json()["items"] if i["type"] == "m3u"}

    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    secret = client.post("/api/playlists", json={"path": f"{battle}/Secret", "ids": [fight], "private": True}).json()
    shared = client.post("/api/playlists", json={"path": f"{battle}/Shared", "ids": [fight]}).json()
    assert secret["private"] and not shared["private"]
    assert names() == {"Secret": True, "Shared": False}
    listing = client.get("/api/tracks", params={"playlist": secret["path"]}).json()
    assert listing["private"] and listing["uploaded_by"] == "anna" and len(listing["tracks"]) == 1

    # nobody else sees, plays, changes, renames or deletes it, not even the SuperAdmin
    for login in ({"username": "bob", "password": "pw1234"}, {"password": "secret"}):
        client.post("/api/auth/login", json=login)
        assert names() == {"Shared": False}
        assert client.get("/api/tracks", params={"playlist": secret["path"]}).status_code == 404
        assert client.post("/api/playlists/entries", json={"playlist": secret["path"], "ids": [fight]}).status_code == 404
        assert client.post("/api/files/rename", json={"path": secret["path"], "name": "Mine.m3u"}).status_code == 404
        assert client.delete("/api/files", params={"path": secret["path"]}).status_code == 404
        assert client.put("/api/playlists/visibility", json={"playlist": secret["path"], "private": False}).status_code == 404

    # only the creator changes the visibility
    client.post("/api/auth/login", json={"username": "bob", "password": "pw1234"})
    assert client.put("/api/playlists/visibility", json={"playlist": shared["path"], "private": True}).status_code == 403
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert client.put("/api/playlists/visibility", json={"playlist": shared["path"], "private": True}).status_code == 200
    assert client.put("/api/playlists/visibility", json={"playlist": secret["path"], "private": False}).status_code == 200
    renamed = client.post("/api/files/rename", json={"path": shared["path"], "name": "Hidden.m3u"}).json()
    assert names() == {"Secret": False, "Hidden": True}
    client.post("/api/auth/login", json={"username": "bob", "password": "pw1234"})
    assert names() == {"Secret": False}
    assert client.get("/api/tracks", params={"playlist": renamed["path"]}).status_code == 404


def test_static_files_stay_inside_the_web_directory(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html>app</html>")
    (web / "icon.png").write_bytes(b"png")
    (tmp_path / "secret.txt").write_text("secret")
    with TestClient(create_app(ServerConfig(web_dir=web))) as test_client:
        assert test_client.get("/icon.png").content == b"png"
        assert test_client.get("/some/route").text == "<html>app</html>"
        for attack in ("/%2e%2e/secret.txt", "/..%2fsecret.txt", "/%2e%2e%2fsecret.txt"):
            assert "secret" not in test_client.get(attack).text


def test_accent_color_is_kept_per_user(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})

    assert client.put("/api/user/state", json={"accent": "blue"}).json()["accent"] == "blue"
    assert client.put("/api/user/state", json={"accent": "#ff0000"}).status_code == 400
    assert client.put("/api/user/state", json={"favorites": []}).json()["accent"] == "blue"  # other changes keep it

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert client.get("/api/user/state").json()["accent"] == ""
    assert client.put("/api/user/state", json={"accent": "red"}).json()["accent"] == "red"
    assert client.put("/api/user/state", json={"accent": ""}).json()["accent"] == ""


def test_rename_folder(client, library):
    root = library["root"]
    response = client.post("/api/files/rename", json={"path": (root / "Tavern").as_posix(), "name": "Inn"})
    assert response.status_code == 200 and response.json()["path"] == (root / "Inn").as_posix()
    assert (root / "Inn").is_dir() and not (root / "Tavern").exists()

    assert client.post("/api/files/rename", json={"path": (root / "Inn").as_posix(), "name": "Battle"}).status_code == 409
    assert client.post("/api/files/rename", json={"path": (root / "Inn").as_posix(), "name": "a/b"}).status_code == 400
    assert client.post("/api/files/rename", json={"path": root.as_posix(), "name": "x"}).status_code == 400


def test_library_folders_are_fixed_in_server_mode(client, library):
    from server.config import get_config
    config = get_config()
    previous, config.local_mode = config.local_mode, False
    try:
        assert client.put("/api/settings", json={"libraryRoots": [library["root"].as_posix()]}).status_code == 403
        assert client.put("/api/settings", json={"lightsTimeout": 4}).status_code == 200
        config.local_mode = True
        assert client.put("/api/settings", json={"libraryRoots": [library["root"].as_posix()]}).status_code == 200
    finally:
        config.local_mode = previous


def test_changing_the_library_folders_tells_the_clients(client, library, monkeypatch):
    from server.config import get_config
    events = []
    monkeypatch.setattr("server.routes.settings.hub.publish", lambda event, data=None: events.append(event))
    config = get_config()
    previous, config.local_mode = config.local_mode, True
    try:
        assert client.put("/api/settings", json={"lightsTimeout": 4}).status_code == 200
        assert "library.roots" not in events
        assert client.put("/api/settings", json={"libraryRoots": [library["root"].as_posix()]}).status_code == 200
        assert events == ["library.roots"]
    finally:
        config.local_mode = previous


def test_tour_done_is_remembered(client):
    assert client.get("/api/user/state").json()["tour_done"] is False
    assert client.put("/api/user/state", json={"tour_done": True}).json()["tour_done"] is True
    assert client.get("/api/user/state").json()["tour_done"] is True


def test_seen_tour_steps_are_remembered(client):
    assert client.get("/api/user/state").json()["tour_seen"] == []
    assert client.put("/api/user/state", json={"tour_seen": ["tree", "search", "tree"]}).json()["tour_seen"] == ["tree", "search"]
    assert client.get("/api/user/state").json()["tour_seen"] == ["tree", "search"]


def test_news_can_be_switched_off(client):
    assert client.get("/api/user/state").json()["news_off"] is False
    assert client.put("/api/user/state", json={"news_off": True}).json()["news_off"] is True
    assert client.get("/api/user/state").json()["news_off"] is True


def test_identical_audio_is_found_whatever_the_tags_say(client, library):
    root = library["root"]  # fight, drums and inn are the same silent frames
    copy = write_mp3(root / "Copies" / "Inn copy.mp3", frames=60)
    write_mp3(root / "Taverns" / "Inn.mp3", frames=60)
    write_mp3(root / "Copies" / "Other.mp3", frames=61)  # its own audio size: never read
    tracks = client.get("/api/library/tracks").json()["tracks"]  # the songs are known to the index
    names = {t["id"]: t["name"] for t in tracks}

    def groups() -> list[list[str]]:
        found = client.get("/api/library/duplicates").json()["groups"]
        return sorted(sorted(names[i] for i in group) for group in found)

    assert groups() == [["Inn", "Inn copy"], ["drums", "fight", "inn"]]

    # the tags of one copy are edited (this rewrites the ID3 tag of the file): the audio is still the same
    copy_id = next(i for i, name in names.items() if name == "Inn copy")
    assert client.patch(f"/api/tracks/{copy_id}", json={"title": "Edited title", "artist": "Somebody else"}).status_code == 200
    assert copy.stat().st_size > 60 * 417
    assert groups() == [["Inn", "Inn copy"], ["drums", "fight", "inn"]]

    copy.write_bytes(copy.read_bytes() + bytes([0]))  # changed audio: no longer the same
    names = {t["id"]: t["name"] for t in client.get("/api/library/tracks").json()["tracks"]}
    assert groups() == [["drums", "fight", "inn"]]


def test_audio_span_skips_the_tags(tmp_path):
    from server.index import audio_hash, audio_span
    audio = b"\xff\xfb\x90\x64" * 100
    v2 = b"ID3\x04\x00\x00" + bytes([0, 0, 0, 20]) + b"x" * 20  # 10 byte header and 20 bytes of frames
    v1 = b"TAG" + b"y" * 125
    ape = b"z" * 10 + b"APETAGEX" + bytes(4) + (42).to_bytes(4, "little") + bytes(4) + bytes(4) + bytes(8)  # footer: 32 bytes, tag size 42
    plain = tmp_path / "plain.mp3"
    plain.write_bytes(audio)
    tagged = tmp_path / "tagged.mp3"
    tagged.write_bytes(v2 + audio + ape + v1)

    assert audio_span(plain) == (0, len(audio))
    assert audio_span(tagged) == (len(v2), len(v2) + len(audio))
    assert audio_hash(plain) == audio_hash(tagged)


def test_the_logins_of_the_users_are_counted(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})

    def anna() -> dict:
        return next(u for u in client.get("/api/users").json() if u["name"] == "anna")

    assert (anna()["last_login"], anna()["logins"]) == (None, 0)
    assert client.post("/api/auth/login", json={"username": "anna", "password": "wrong"}).status_code == 401  # a failed attempt does not count
    for _ in range(2):
        client.post("/api/auth/logout")
        assert client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"}).status_code == 200
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"password": "secret"})

    assert anna()["logins"] == 2 and time.time() - anna()["last_login"] < 60
    admin = next(u for u in client.get("/api/users").json() if u["name"] == "admin")
    assert admin["logins"] == 2  # the sign in before and the one after

    client.delete("/api/users/anna")  # what is kept for a user goes with the user
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    assert anna()["logins"] == 0


def test_visits_are_counted_for_every_page_load_after_a_pause(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})

    def anna() -> dict:
        client.post("/api/auth/logout")
        client.post("/api/auth/login", json={"password": "secret"})
        return next(u for u in client.get("/api/users").json() if u["name"] == "anna")

    assert client.get("/api/auth/me").json()["user"] == "anna"  # a page load with the session of the login
    client.get("/api/auth/me")  # and a reload: the same visit
    assert anna()["visits"] == 1 and time.time() - anna()["last_seen"] < 60

    index = get_index()
    assert index.record_visit("anna", now=time.time() + 10 * 60) is False  # still the same visit
    assert index.record_visit("anna", now=time.time() + 3 * 3600) is True  # a new one hours later
    assert anna()["visits"] == 2
    assert client.get("/api/auth/me").status_code == 200 and anna()["visits"] == 2  # the page load of the SuperAdmin is not Anna's


def test_player_settings_are_kept_per_user(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    settings = {"shuffle": True, "repeat": "all", "volume": 40, "muted": True, "effectsVolume": 25, "normalize": False, "crossfade": False, "dynamicScore": False, "dynamicColumns": True}

    assert client.put("/api/user/state", json={"player": {**settings, "repeat": "forever"}}).status_code == 422
    assert client.put("/api/user/state", json={"player": {**settings, "volume": 200}}).status_code == 422
    assert client.put("/api/user/state", json={"player": settings}).json()["player"] == settings

    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})
    assert client.get("/api/user/state").json()["player"] is None


def test_the_whole_library_for_the_global_search(client, library, tmp_path):
    effects_dir = tmp_path / "effects"
    write_mp3(effects_dir / "Rain.mp3")
    AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, effects_dir.as_posix())
    client.get("/api/effects")  # the effects are known to the index, but are no songs of the library

    tracks = client.get("/api/library/tracks").json()["tracks"]  # also the songs of folders that were never opened
    fight = next(t for t in tracks if t["name"] == "fight")
    client.patch(f"/api/tracks/{fight['id']}", json={"favorite": True})

    tracks = client.get("/api/library/tracks").json()["tracks"]
    assert sorted(t["name"] for t in tracks) == ["drums", "fight", "inn"]  # neither the effects nor files outside the library
    assert next(t for t in tracks if t["name"] == "fight")["favorite"] is True


def _ufid(client, path):
    return client.get(f"/api/tracks/{_id(path)}").json()["ufid"]


def test_refresh_gives_songs_and_playlists_stable_ids(client, library):
    root = library["root"]
    fight, inn = root / "Battle" / "fight.mp3", root / "Tavern" / "inn.mp3"
    mix = client.post("/api/playlists", json={"path": (root / "Mix").as_posix(), "ids": [_id(fight)]}).json()["path"]
    (root / "Plain.m3u").write_text("#EXTM3U\nBattle/drums.mp3\n")  # an older playlist without an id

    assert client.get(f"/api/tracks/{_id(fight)}").json()["ufid"] is None
    done = client.post("/api/library/rescan").json()
    assert done["ids_assigned"] == 4 and done["ids_failed"] == 0  # three songs and the playlist without id
    assert client.post("/api/library/rescan").json()["ids_assigned"] == 0

    ufid = _ufid(client, fight)
    assert ufid and ufid != _ufid(client, inn)
    assert (root / "Plain.m3u").read_text().splitlines()[:2] == ["#EXTM3U", f"#DT-ID:{client.get('/api/tracks', params={'playlist': (root / 'Plain.m3u').as_posix()}).json()['playlist_id']}"]

    # the ids survive tag edits, renames and moves
    client.patch(f"/api/tracks/{_id(fight)}", json={"title": "Duel"})
    assert _ufid(client, fight) == ufid
    client.post("/api/files/rename", json={"path": fight.as_posix(), "name": "duel.mp3"})
    client.post("/api/files/rename", json={"path": (root / "Battle").as_posix(), "name": "Fights"})
    moved = client.get("/api/library/resolve", params={"song": ufid}).json()
    assert moved["path"] == (root / "Fights" / "duel.mp3").as_posix() and moved["count"] == 1

    playlist_id = client.get("/api/tracks", params={"playlist": mix}).json()["playlist_id"]
    client.post("/api/files/rename", json={"path": mix, "name": "Renamed.m3u"})
    client.post("/api/playlists/remove", json={"playlist": (root / "Renamed.m3u").as_posix(), "ids": []})  # rewriting keeps the id
    found = client.get("/api/library/resolve", params={"playlist": playlist_id}).json()
    assert found["path"] == (root / "Renamed.m3u").as_posix()
    assert client.get("/api/library/resolve", params={"song": "unknown"}).status_code == 404
    assert client.get("/api/library/resolve").status_code == 400


def test_copies_share_an_id_and_show_up_as_duplicates(client, library):
    root = library["root"]
    fight = root / "Battle" / "fight.mp3"
    client.post("/api/library/rescan")
    copy = root / "Tavern" / "fight copy.mp3"
    copy.write_bytes(fight.read_bytes())
    client.post("/api/library/rescan")

    assert _ufid(client, copy) == _ufid(client, fight)
    ufid = _ufid(client, fight)
    assert client.get("/api/library/resolve", params={"song": ufid}).json()["count"] == 2
    groups = client.get("/api/library/duplicates").json()
    assert sorted(groups["ufid_groups"][0]) == sorted([_id(fight.as_posix()), _id(copy.as_posix())])
    fight.unlink()
    assert client.get("/api/library/resolve", params={"song": ufid}).json()["path"] == copy.as_posix()
