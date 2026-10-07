import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core import ytimport
from core.settings import AppSettings, SettingKeys
from server import downloads, ytagent as server_agent
from server.agents import set_agent_token
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "youtube"))
import dt_youtube_agent as ytagent  # noqa: E402

TOKEN = "secret-agent-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        test_client.root = root
        test_client.mp3 = write_mp3(tmp_path / "upload.mp3").read_bytes()
        yield test_client
    index.close()
    set_index(None)


class Pump(threading.Thread):
    """Plays the YouTube agent: answers lookups and uploads the given mp3 for every download."""

    def __init__(self, client, websocket, parts=0):
        super().__init__(daemon=True)
        self.client = client
        self.websocket = websocket
        self.parts = parts
        self.requests: list[dict] = []

    def run(self):
        try:
            while True:
                request = json.loads(self.websocket.receive_text())
                self.requests.append(request)
                if request["op"] == "resolve":
                    entries = [{"url": "https://www.youtube.com/watch?v=abc", "title": "From the agent", "duration": 60, "uploader": "me", "chapters": None}]
                    result = {"title": "Agent lookup", "is_playlist": False, "entries": entries, "has_video": False}
                elif "broken" in request["url"]:
                    self.websocket.send_text(json.dumps({"id": request["id"], "ok": False, "error": "Video unavailable"}))
                    continue
                else:
                    self.websocket.send_text(json.dumps({"type": "progress", "id": request["id"], "percent": 40, "message": "Converting"}))
                    count = self.parts or 1
                    for index in range(count):
                        response = self.client.put(f"{request['upload']}/{index}", content=self.client.mp3, headers=AUTH)
                        assert response.status_code == 200
                    names = [f"0{n + 1} Part {n + 1}.mp3" for n in range(count)] if self.parts else ["Agent Song.mp3"]
                    result = {"title": "Agent Song", "name": "Agent Song.mp3", "split": bool(self.parts),
                              "files": [{"name": name, "title": name[:-4]} for name in names]}
                self.websocket.send_text(json.dumps({"id": request["id"], "ok": True, "result": result}))
        except Exception:
            pass  # connection closed


def connect(client):
    set_agent_token(TOKEN)
    return client.websocket_connect("/ws/agent", headers=AUTH)


def hello(websocket):
    websocket.send_text(json.dumps({"type": "hello", "kind": "youtube", "name": "home-pc"}))
    assert json.loads(websocket.receive_text()) == {"type": "welcome"}


def wait_idle():
    for _ in range(200):
        status = downloads.download_queue.status()
        if status["pending"] == 0:
            return status
        time.sleep(0.05)
    raise AssertionError("the import did not finish")


def test_lookup_and_download_go_through_the_agent(client, monkeypatch):
    monkeypatch.setattr(downloads, "download", lambda *a, **k: pytest.fail("the server must not download itself"))
    monkeypatch.setattr("server.routes.imports.resolve", lambda *a, **k: pytest.fail("the server must not look up itself"))
    with connect(client) as websocket:
        hello(websocket)
        pump = Pump(client, websocket)
        pump.start()
        target = client.root.resolve().as_posix()

        found = client.post("/api/import/resolve", json={"url": "https://www.youtube.com/watch?v=abc"}).json()
        assert found["title"] == "Agent lookup" and found["entries"][0]["title"] == "From the agent"

        response = client.post("/api/import", json={"dir": target, "entries": [{"url": "https://www.youtube.com/watch?v=abc", "title": "x"}]})
        assert response.status_code == 200
        status = wait_idle()
        assert (status["done"], status["failed"]) == (1, 0) and status["items"][0]["state"] == "done"
        assert (client.root / "Agent Song.mp3").read_bytes() == client.mp3
        download = [r for r in pump.requests if r["op"] == "download"][0]
        assert download["max_minutes"] == 240 and download["split"] is False


def test_split_parts_and_errors_of_the_agent(client):
    with connect(client) as websocket:
        hello(websocket)
        Pump(client, websocket, parts=2).start()
        target = client.root.resolve().as_posix()
        entries = [{"url": "https://www.youtube.com/watch?v=abc"}, {"url": "https://www.youtube.com/watch?v=broken"}]
        client.post("/api/import", json={"dir": target, "entries": entries, "split": True})
        status = wait_idle()
        assert (status["done"], status["failed"]) == (1, 1)
        assert status["items"][1]["message"] == "Video unavailable"
        assert sorted(p.name for p in (client.root / "Agent Song").glob("*.mp3")) == ["01 Part 1.mp3", "02 Part 2.mp3"]


def test_uploads_need_the_token_and_a_ticket(client, tmp_path):
    set_agent_token(TOKEN)
    assert client.put("/api/agents/uploads/nope/0", content=b"x", headers=AUTH).status_code == 404
    assert client.put("/api/agents/uploads/nope/0", content=b"x").status_code == 401
    server_agent._uploads["ticket"] = tmp_path
    try:
        assert client.put("/api/agents/uploads/ticket/0", content=b"x").status_code == 401
        assert client.put("/api/agents/uploads/ticket/5000", content=b"x", headers=AUTH).status_code == 404
        assert client.put("/api/agents/uploads/ticket/0", content=b"abc", headers=AUTH).json() == {"size": 3}
        assert (tmp_path / "0.mp3").read_bytes() == b"abc"
    finally:
        server_agent._uploads.pop("ticket")


def test_without_an_agent_the_server_reports_it(client):
    with pytest.raises(ytimport.ImportFailed):
        server_agent.resolve("https://www.youtube.com/watch?v=abc")


def test_agent_urls_and_cookie_options():
    assert ytagent.agent_url("https://music.example.com/") == "wss://music.example.com/ws/agent"
    assert ytagent.http_url("http://host:8765/dt", "/api/agents/uploads/t/0") == "http://host:8765/dt/api/agents/uploads/t/0"
    try:
        ytimport.use_cookies(browser="firefox")
        assert ytimport._cookies_override == {"cookiesfrombrowser": ("firefox",)}
        ytimport.use_cookies(file="c.txt")
        assert ytimport._cookies_override == {"cookiefile": "c.txt"}
    finally:
        ytimport.use_cookies()
    assert ytimport._cookies_override == {}
    assert ytagent.build_parser().parse_args(["--token", "t", "--cookies-from-browser", "edge"]).cookies_from_browser == "edge"
