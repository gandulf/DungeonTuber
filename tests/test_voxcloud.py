import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from server import voxcloud
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

KEY, SECRET = "wk-test", "ws-test"
RESULT = {"categories": {"Energy": 7, "Valence": 3}, "tags": ["epic"], "genres": ["Rock"], "bpm": 120}


class FakeCloud(ThreadingHTTPServer):
    """Stands in for the Modal endpoint: records the posts and rejects them without the proxy auth headers like Modal does."""

    def __init__(self):
        super().__init__(("127.0.0.1", 0), self.Handler)
        self.posts: list[tuple[dict, bytes]] = []
        self.failure: tuple[int, str] | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.server_address[1]}/"

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            self.server.posts.append((dict(self.headers), body))
            if (self.headers.get("Modal-Key"), self.headers.get("Modal-Secret")) != (KEY, SECRET):
                status, payload = 401, {"detail": "Missing or invalid proxy auth token"}
            elif self.server.failure:
                status, payload = self.server.failure[0], {"detail": self.server.failure[1]}
            else:
                status, payload = 200, RESULT
            data = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass


@pytest.fixture
def cloud():
    server = FakeCloud()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    return root


@pytest.fixture
def client(tmp_path, library):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)


def _wait(condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_nothing_is_configured_by_default(client):
    assert client.get("/api/analysis/cloud").json() == {"configured": False, "host": None}
    assert client.get("/api/analysis").json()["backend"] is None
    assert client.get("/api/settings").json()["voxalyzerActive"] is False


def test_configuration_is_validated_and_the_secret_stays_private(client, cloud):
    assert client.put("/api/analysis/cloud", json={"url": "not a url", "key": KEY, "secret": SECRET}).status_code == 400
    assert client.put("/api/analysis/cloud", json={"url": cloud.url, "key": KEY, "secret": " "}).status_code == 400
    assert client.put("/api/analysis/cloud", json={"url": cloud.url, "key": "", "secret": SECRET}).status_code == 400

    saved = client.put("/api/analysis/cloud", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    assert saved.status_code == 200
    assert saved.json() == {"configured": True, "host": f"127.0.0.1:{cloud.server_address[1]}"}
    assert SECRET not in json.dumps(client.get("/api/analysis/cloud").json())
    assert client.get("/api/analysis").json()["backend"] == "cloud"
    assert client.get("/api/settings").json()["voxalyzerActive"] is True

    assert client.delete("/api/analysis/cloud").json()["configured"] is False
    assert client.get("/api/analysis").json()["backend"] is None


def test_analysis_runs_in_the_cloud_function(client, library, cloud):
    client.put("/api/analysis/cloud", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    song = library / "Battle" / "fight.mp3"
    original = song.read_bytes()

    assert client.post("/api/analysis", json={"paths": [song.as_posix()]}).json()["queued"] == 1
    assert _wait(lambda: client.get("/api/analysis").json()["pending"] == 0 and cloud.posts)

    headers, body = cloud.posts[0]
    assert body == original
    assert (headers["Modal-Key"], headers["Modal-Secret"]) == (KEY, SECRET) and headers["Content-Type"] == "audio/mpeg"
    entry = parse_mp3(song)
    assert entry.categories == RESULT["categories"] and entry.tags == RESULT["tags"]
    assert entry.genres == RESULT["genres"] and entry.bpm == RESULT["bpm"]
    assert client.get("/api/analysis").json()["failed"] == 0


def test_failures_are_reported(tmp_path, mp3_file, cloud):
    voxcloud.save_config(cloud.url, KEY, SECRET)
    backend = voxcloud.current_backend()

    cloud.failure = (500, "boom")
    with pytest.raises(voxcloud.CloudError, match="boom"):
        backend.analyze_mp3(mp3_file)

    wrong = voxcloud.CloudVoxalyzerBackend({"url": cloud.url, "key": KEY, "secret": "wrong"})
    with pytest.raises(voxcloud.CloudError, match="rejected the key"):
        wrong.analyze_mp3(mp3_file)

    cloud.shutdown()
    cloud.server_close()  # the port refuses connections now
    with pytest.raises(voxcloud.CloudError, match="not reachable"):
        backend.analyze_mp3(mp3_file)


def test_config_file_is_private(tmp_path):
    voxcloud.save_config("https://example.modal.run", KEY, SECRET)
    assert voxcloud.config_file().parent == tmp_path
    if sys.platform != "win32":
        assert voxcloud.config_file().stat().st_mode & 0o077 == 0
