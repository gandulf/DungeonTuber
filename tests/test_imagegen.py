import io
import json
import threading

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import write_mp3
from core.settings import AppSettings, SettingKeys
from server import assistant, imagegen
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index
from test_musicgen import KEY, SECRET, FakeCloud


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 4), "navy").save(buffer, "JPEG")
    return buffer.getvalue()


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    return root


@pytest.fixture
def cloud():
    server = FakeCloud(_jpeg())  # answers with these bytes whatever they are
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


def test_the_image_generation_has_a_configuration_of_its_own(client, cloud):
    assert client.get("/api/assistant/imagegen").json() == {"configured": False, "host": None, "source": None}
    assert client.get("/api/settings").json()["imageGenConfigured"] is False
    adventure = client.post("/api/adventures", json={"title": "Crypt"}).json()
    assert client.post(f"/api/adventures/{adventure['id']}/images/generate", json={"prompt": "a crypt"}).status_code == 409

    saved = client.put("/api/assistant/imagegen", json={"url": cloud.url, "key": KEY, "secret": SECRET}).json()
    assert saved["configured"] is True and saved["source"] == "settings"
    assert SECRET not in client.get("/api/assistant/imagegen").text
    assert client.get("/api/settings").json()["imageGenConfigured"] is True
    assert imagegen.CONFIG.file().name == "imagegen-cloud.json"
    assert client.delete("/api/assistant/imagegen").json()["configured"] is False


def test_a_generated_image_becomes_the_cover_of_a_block(client, library, cloud):
    client.put("/api/assistant/imagegen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    adventure = client.post("/api/adventures", json={"title": "Crypt"}).json()
    base = f"/api/adventures/{adventure['id']}"

    result = client.post(f"{base}/images/generate", json={"prompt": "a torch-lit crypt", "size": "portrait"}).json()
    assert result["seed"] == 4711 and result["name"].endswith(".jpg")
    assert cloud.posts[0][1] == {"prompt": "a torch-lit crypt", "negative_prompt": "", "width": 768, "height": 1344, "format": "jpeg"}
    assert client.get(f"{base}/images/{result['name']}").content == _jpeg()

    # the cover is kept by the cleanup; a name that is no image of the adventure is dropped
    block = adventure["blocks"][0]
    saved = client.put(base, json={"blocks": [{**block, "cover": result["name"]}], "links": []}).json()
    assert saved["blocks"][0]["cover"] == result["name"]
    assert client.post(f"{base}/images/cleanup").json() == {"removed": 0}
    assert client.put(base, json={"blocks": [{**block, "cover": "../secret.png"}], "links": []}).json()["blocks"][0]["cover"] is None
    assert client.post(f"{base}/images/cleanup").json() == {"removed": 1}

    assert client.post(f"{base}/images/generate", json={"prompt": "x", "size": "huge"}).status_code == 422
    cloud.failure = (500, "CUDA out of memory")
    response = client.post(f"{base}/images/generate", json={"prompt": "a crypt"})
    assert response.status_code == 502 and "image generation failed" in response.json()["detail"]


def test_an_answer_that_is_no_image_is_rejected(client, library, cloud):
    cloud.mp3 = b"no picture"
    client.put("/api/assistant/imagegen", json={"url": cloud.url, "key": KEY, "secret": SECRET})
    adventure = client.post("/api/adventures", json={"title": "Crypt"}).json()
    assert client.post(f"/api/adventures/{adventure['id']}/images/generate", json={"prompt": "a crypt"}).status_code == 502


def test_the_assistant_describes_the_picture(client, monkeypatch):
    calls = []

    def post(payload):
        calls.append(payload)
        answer = {"message": "Eine Gruft", "caption": " A dark crypt,\n lit by torches. "}
        return {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]}

    monkeypatch.setattr(assistant, "_post", post)
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234"})
    messages = [{"role": "user", "content": "Die Gruft unter dem Tempel"}]

    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "image"}).json()
    assert result["caption"] == "A dark crypt, lit by torches." and result["message"] == "Eine Gruft"
    assert assistant.IMAGE_PROMPT in calls[0]["systemInstruction"]["parts"][0]["text"]
    assert calls[0]["generationConfig"]["responseSchema"] == assistant.IMAGE_SCHEMA
    assert "image" in assistant.GROQ_MODES


def test_the_description_of_a_picture_stays_within_the_words_the_generator_reads():
    limit = assistant.MAX_IMAGE_WORDS
    words = lambda count: " ".join(f"w{i}" for i in range(count))  # noqa: E731
    assert assistant.limit_words(" Short,\n description. ") == "Short, description."
    assert assistant.limit_words(words(limit)) == words(limit)
    # too long: cut at the last end of a sentence within the limit when that keeps most of it
    long = f"{words(50)}. {words(30)}"
    assert assistant.limit_words(long) == f"{words(50)}."
    # otherwise after the last word that fits, with a full stop instead of a trailing comma
    run_on = " ".join(f"w{i}," for i in range(80))
    cut = assistant.limit_words(run_on)
    assert len(cut.split()) == limit and cut.endswith("w59.")
    early = f"{words(5)}. {words(80)}"
    assert len(assistant.limit_words(early).split()) == limit


def test_a_too_long_answer_of_the_assistant_is_cut(client, monkeypatch):
    long_caption = "Detailed fantasy oil painting of a crypt. " + " ".join(["torches"] * 80)
    answer = {"message": "Eine Gruft", "caption": long_caption}
    monkeypatch.setattr(assistant, "_post", lambda payload: {"candidates": [{"content": {"parts": [{"text": json.dumps(answer)}]}}]})
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234"})
    result = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Gruft"}], "mode": "image"}).json()
    assert len(result["caption"].split()) <= assistant.MAX_IMAGE_WORDS
    assert result["caption"].startswith("Detailed fantasy oil painting of a crypt.")
