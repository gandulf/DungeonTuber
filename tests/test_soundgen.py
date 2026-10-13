import json
import threading

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from server import assistant, soundgen
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index
from test_musicgen import KEY, SECRET, FakeCloud

SOUND = {"title": "Rain on the tent", "caption": "rain drumming on a canvas tent, distant thunder", "kind": "ambience", "duration": 60}


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    (root / "Effects").mkdir()
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    AppSettings.setValue(SettingKeys.EFFECTS_DIRECTORY, (root / "Effects").as_posix())
    return root


@pytest.fixture
def cloud(tmp_path):
    server = FakeCloud(write_mp3(tmp_path / "generated.mp3").read_bytes())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def client(tmp_path, library):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)


def test_nothing_is_configured_by_default(client, library):
    assert client.get("/api/assistant/soundgen").json() == {"configured": False, "host": None, "source": None}
    assert client.get("/api/settings").json()["soundGenConfigured"] is False
    response = client.post("/api/assistant/sound", json={**SOUND, "dir": (library / "Effects").as_posix()})
    assert response.status_code == 409


def test_the_sound_generation_has_a_configuration_of_its_own(client, cloud, monkeypatch):
    saved = client.put("/api/assistant/soundgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    assert saved.json() == {"configured": True, "host": f"127.0.0.1:{cloud.server_address[1]}", "source": "settings"}
    assert SECRET not in client.get("/api/assistant/soundgen").text
    assert client.get("/api/settings").json()["soundGenConfigured"] is True
    assert client.get("/api/assistant/musicgen").json()["configured"] is False
    assert soundgen.CONFIG.file().name == "soundgen-cloud.json"
    assert client.delete("/api/assistant/soundgen").json()["configured"] is False

    monkeypatch.setenv("DT_SOUNDGEN_URL", cloud.url)
    monkeypatch.setenv("DT_MODAL_KEY", KEY)
    monkeypatch.setenv("DT_MODAL_SECRET", SECRET)
    assert client.get("/api/assistant/soundgen").json()["source"] == "environment"


def test_a_sound_is_stored_in_the_effects_folder(client, library, cloud):
    client.put("/api/assistant/soundgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    folder = (library / "Effects").as_posix()

    result = client.post("/api/assistant/sound", json={**SOUND, "dir": folder}).json()
    assert result["seed"] == 4711 and result["track"]["title"] == "Rain on the tent"
    assert cloud.posts[0][1] == {"caption": SOUND["caption"], "kind": "ambience", "duration": 60, "seed": None}

    entry = parse_mp3(library / "Effects" / "Rain on the tent.mp3")
    assert entry.artist == soundgen.ARTIST and entry.summary == SOUND["caption"]
    effects = client.get("/api/effects").json()["effects"]
    assert [effect["name"] for effect in effects] == ["Rain on the tent"]

    # without a duration the cloud function chooses the default of the kind
    client.post("/api/assistant/sound", json={**SOUND, "kind": "sfx", "duration": None, "dir": folder})
    assert cloud.posts[1][1]["duration"] is None and cloud.posts[1][1]["kind"] == "sfx"
    assert (library / "Effects" / "Rain on the tent (2).mp3").exists()


def test_sounds_stay_inside_the_library_and_failures_are_reported(client, library, cloud, tmp_path):
    client.put("/api/assistant/soundgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert client.post("/api/assistant/sound", json={**SOUND, "dir": outside.as_posix()}).status_code == 403
    assert client.post("/api/assistant/sound", json={**SOUND, "kind": "speech", "dir": outside.as_posix()}).status_code == 422
    assert not cloud.posts

    cloud.failure = (500, "CUDA out of memory")
    response = client.post("/api/assistant/sound", json={**SOUND, "dir": (library / "Effects").as_posix()})
    assert response.status_code == 502 and "sound generation failed" in response.json()["detail"]
    assert not any((library / "Effects").iterdir())


def test_the_assistant_describes_the_sound(client, monkeypatch):
    calls = []

    def post(payload):
        calls.append(payload)
        answer = {"message": "Ein Gewitter", "title": "Gewitter", "caption": " heavy rain,\n rolling thunder ", "duration": 9999}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}

    monkeypatch.setattr(assistant, "_post", post)
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234", "effectsInstructions": "Wir spielen in Aventurien."})
    messages = [{"role": "user", "content": "Ein Gewitter über dem Lager"}]

    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "effects", "context": {"kind": "ambience"}}).json()
    assert result["sound"] == {"title": "Gewitter", "caption": "heavy rain, rolling thunder", "kind": "ambience", "duration": None}
    prompt = calls[0]["systemInstruction"]["parts"][0]["text"]
    assert assistant.EFFECTS_PROMPT in prompt and assistant.EFFECT_KINDS["ambience"] in prompt
    assert prompt.endswith("Wir spielen in Aventurien.")
    assert calls[0]["generationConfig"]["responseSchema"] == assistant.EFFECTS_SCHEMA
    assert client.get("/api/assistant/config").json()["effectsInstructions"] == "Wir spielen in Aventurien."
    assert any(entry["name"] == "effects.system" for entry in client.get("/api/assistant/config").json()["prompts"])

    # an unknown kind is a sound effect; the effects mode runs on Groq like the compose mode
    assert assistant.to_sound({"caption": "a door", "duration": 3}, "speech") == {"title": "a door", "caption": "a door",
                                                                                 "kind": "sfx", "duration": 3}
    assert "effects" in assistant.GROQ_MODES
