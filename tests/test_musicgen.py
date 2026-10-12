import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from server import assistant, musicgen
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

KEY, SECRET = "wk-test", "ws-test"
PIECE = {"title": "Tavern Brawl", "caption": "medieval folk, fiddle, lute, frantic, fast, rowdy", "duration": 30}


class FakeCloud(ThreadingHTTPServer):
    """Stands in for the Modal endpoint: answers with an mp3 and rejects requests without the proxy auth headers like Modal does."""

    def __init__(self, mp3: bytes):
        super().__init__(("127.0.0.1", 0), self.Handler)
        self.mp3 = mp3
        self.posts: list[tuple[dict, dict]] = []
        self.failure: tuple[int, str] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.posts.append((dict(self.headers), body))
            if (self.headers.get("Modal-Key"), self.headers.get("Modal-Secret")) != (KEY, SECRET):
                self._send(401, json.dumps({"detail": "Missing or invalid proxy auth token"}).encode(), "application/json")
            elif self.server.failure:
                self._send(self.server.failure[0], json.dumps({"detail": self.server.failure[1]}).encode(), "application/json")
            else:
                self._send(200, self.server.mp3, "audio/mpeg", {"X-Seed": "4711"})

        def _send(self, status: int, data: bytes, content_type: str, headers: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            for name, value in (headers or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
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
    assert client.get("/api/assistant/musicgen").json() == {"configured": False, "host": None, "source": None}
    assert client.get("/api/settings").json()["musicGenConfigured"] is False
    response = client.post("/api/assistant/compose", json={**PIECE, "dir": (library / "Battle").as_posix()})
    assert response.status_code == 409


def test_configuration_is_validated_and_the_secret_stays_private(client, cloud):
    assert client.put("/api/assistant/musicgen", json={"url": "not a url", "key": KEY, "secret": SECRET}).status_code == 400
    assert client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": " "}).status_code == 400

    saved = client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    assert saved.json() == {"configured": True, "host": f"127.0.0.1:{cloud.server_address[1]}", "source": "settings"}
    assert SECRET not in client.get("/api/assistant/musicgen").text
    assert client.get("/api/settings").json()["musicGenConfigured"] is True
    # the cloud analysis has a configuration of its own
    assert client.get("/api/analysis/cloud").json()["configured"] is False

    assert client.delete("/api/assistant/musicgen").json()["configured"] is False


def test_a_composed_piece_is_stored_in_the_library(client, library, cloud):
    client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    folder = (library / "Battle").as_posix()

    result = client.post("/api/assistant/compose", json={**PIECE, "dir": folder, "bpm": 140}).json()
    assert result["seed"] == 4711
    assert result["track"]["title"] == "Tavern Brawl"
    headers, body = cloud.posts[0]
    assert (headers["Modal-Key"], headers["Modal-Secret"]) == (KEY, SECRET)
    assert body == {"caption": PIECE["caption"], "lyrics": "", "language": "", "instrumental": True, "duration": 30, "bpm": 140,
                    "seed": None}

    entry = parse_mp3(library / "Battle" / "Tavern Brawl.mp3")
    assert entry.title == "Tavern Brawl" and entry.artist == musicgen.ARTIST and entry.bpm == 140
    assert entry.summary == PIECE["caption"]

    # the same title again gets a file of its own
    client.post("/api/assistant/compose", json={**PIECE, "dir": folder})
    assert (library / "Battle" / "Tavern Brawl (2).mp3").exists()
    tracks = client.get("/api/tracks", params={"dir": folder}).json()["tracks"]
    assert {track["title"] for track in tracks} >= {"Tavern Brawl"}


def test_compose_stays_inside_the_library(client, cloud, tmp_path):
    client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    assert client.post("/api/assistant/compose", json={**PIECE, "dir": outside.as_posix()}).status_code == 403
    assert not cloud.posts


def test_failures_are_reported(client, library, cloud):
    folder = (library / "Battle").as_posix()
    client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": "wrong"})
    response = client.post("/api/assistant/compose", json={**PIECE, "dir": folder})
    assert response.status_code == 502 and "rejected the key" in response.json()["detail"]

    client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    cloud.failure = (500, "CUDA out of memory")
    response = client.post("/api/assistant/compose", json={**PIECE, "dir": folder})
    assert response.status_code == 502 and "CUDA out of memory" in response.json()["detail"]

    cloud.failure = None
    cloud.mp3 = b"not an mp3"
    response = client.post("/api/assistant/compose", json={**PIECE, "dir": folder})
    assert response.status_code == 502
    assert sorted(path.name for path in (library / "Battle").iterdir()) == ["fight.mp3"]


def test_config_file_is_private(tmp_path):
    musicgen.save_config("https://example.modal.run", KEY, SECRET)
    file = musicgen.CONFIG.file()
    assert file.parent == tmp_path and file.name == "musicgen-cloud.json"
    if sys.platform != "win32":
        assert file.stat().st_mode & 0o077 == 0


def test_the_assistant_writes_the_description(client, monkeypatch):
    calls = []

    def post(payload):
        calls.append(payload)
        answer = {"message": "Ein wildes Stück", "title": "Kneipenschlägerei", "caption": "  medieval folk,\n fiddle, fast  ",
                  "lyrics": "[verse] la la", "bpm": 500}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}

    monkeypatch.setattr(assistant, "_post", post)
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    messages = [{"role": "user", "content": "Eine Kneipenschlägerei"}]

    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose"}).json()
    assert result["message"] == "Ein wildes Stück"
    assert result["piece"] == {"title": "Kneipenschlägerei", "caption": "medieval folk, fiddle, fast", "lyrics": "", "language": "",
                               "instrumental": True, "bpm": None}
    prompt = calls[0]["systemInstruction"]["parts"][0]["text"]
    assert assistant.INSTRUMENTAL_RULE in prompt
    assert calls[0]["generationConfig"]["responseSchema"] == assistant.COMPOSE_SCHEMA

    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": {"instrumental": False}}).json()
    assert result["piece"]["lyrics"] == "[verse] la la" and result["piece"]["instrumental"] is False
    assert result["piece"]["language"] == ""  # the answer named none
    assert assistant.VOCALS_RULE in calls[1]["systemInstruction"]["parts"][0]["text"]

    # the lyrics are as long as the piece allows
    context = {"instrumental": False, "duration": 120}
    client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": context})
    assert "The piece is 120 seconds long: write 140 to 220 words" in calls[2]["systemInstruction"]["parts"][0]["text"]
    client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": {"instrumental": True, "duration": 120}})
    assert "seconds long" not in calls[3]["systemInstruction"]["parts"][0]["text"]
    assert client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": {"duration": 5}}).status_code == 422
    assert assistant.lyrics_budget(10) == "The piece is 10 seconds long: write 20 to 30 words of lyrics in total, not more."
    assert assistant.lyrics_budget(None) == ""

    # the language the user chose for the lyrics wins over the language of the chat
    context = {"instrumental": False, "duration": 60, "language": "en"}
    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": context}).json()
    assert "Write the lyrics in English and set language to en" in calls[-1]["systemInstruction"]["parts"][0]["text"]
    assert result["piece"]["language"] == "en"
    client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": {"instrumental": True, "language": "en"}})
    assert "Write the lyrics in" not in calls[-1]["systemInstruction"]["parts"][0]["text"]
    bad = {"instrumental": False, "language": "Deutsch"}
    assert client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose", "context": bad}).status_code == 422


def test_the_language_of_the_lyrics_reaches_the_cloud_function(client, library, cloud):
    client.put("/api/assistant/musicgen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    piece = {**PIECE, "dir": (library / "Battle").as_posix(), "instrumental": False, "lyrics": "[Verse]\nHeja", "language": "de"}
    assert client.post("/api/assistant/compose", json=piece).status_code == 200
    assert cloud.posts[-1][1]["language"] == "de" and cloud.posts[-1][1]["instrumental"] is False
    assert client.post("/api/assistant/compose", json={**piece, "language": "Deutsch"}).status_code == 422
    assert assistant.to_piece({"caption": "folk", "language": "DE", "lyrics": "x"}, instrumental=False)["language"] == "de"
    assert assistant.to_piece({"caption": "folk", "language": "German"}, instrumental=False)["language"] == ""
    assert assistant.to_piece({"caption": "folk", "language": "de", "lyrics": "x"}, instrumental=True)["lyrics"] == ""
    # an instrumental piece keeps its structure: section tags without words
    structure = "[Intro - solo harp]\n\n[Main Theme - fiddle]\n\n[Outro - fade out]"
    assert assistant.to_piece({"caption": "folk", "lyrics": structure}, instrumental=True)["lyrics"] == structure
    assert assistant.to_piece({"caption": "folk", "lyrics": structure + "\nla la"}, instrumental=True)["lyrics"] == ""
    assert not assistant.structure_only("") and assistant.structure_only("[Instrumental]")


def test_the_music_generation_can_be_set_up_by_the_environment(client, library, cloud, monkeypatch):
    for name, value in (("DT_MUSICGEN_URL", cloud.url), ("DT_MUSICGEN_KEY", KEY), ("DT_MUSICGEN_SECRET", SECRET), ("DT_MODAL_KEY", "shared")):
        monkeypatch.setenv(name, value)
    assert client.get("/api/settings").json()["musicGenConfigured"] is True
    assert client.get("/api/assistant/musicgen").json()["source"] == "environment"
    result = client.post("/api/assistant/compose", json={**PIECE, "dir": (library / "Battle").as_posix()})
    assert result.status_code == 200 and cloud.posts[-1][0]["Modal-Key"] == KEY  # its own key wins over the shared one
