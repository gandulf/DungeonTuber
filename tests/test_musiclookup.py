import io
import json
import urllib.error
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core import musiclookup
from core.settings import AppSettings, SettingKeys
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index
from server.paths import path_to_id


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


MUSICBRAINZ = {"recordings": [
    {"id": "rec-1", "score": 100, "title": "Clash of Steel", "length": 181000,
     "artist-credit": [{"name": "Bard", "joinphrase": " & "}, {"name": "Drums"}],
     "releases": [
         {"title": "Best of Battles", "date": "2001", "status": "Official",
          "release-group": {"primary-type": "Album", "secondary-types": ["Compilation"]}, "media": [{"track": [{"number": "9"}]}]},
         {"title": "Steel", "date": "1999-05-01", "status": "Official",
          "release-group": {"primary-type": "Album"}, "media": [{"track": [{"number": "3"}]}]},
     ]},
    {"id": "rec-2", "score": 90, "title": "Clash of Steel (Live)", "length": 400000, "artist-credit": [{"name": "Bard"}]},
]}

ACOUSTID = {"status": "ok", "results": [{"score": 0.97, "recordings": [
    {"id": "rec-1", "title": "Clash of Steel", "duration": 180.6, "artists": [{"name": "Bard"}],
     "releasegroups": [{"type": "Album", "title": "Steel", "releases": [
         {"date": {"year": 1999, "month": 5}, "mediums": [{"tracks": [{"position": 3}]}]}]}]},
    {"id": "rec-x"},  # recordings without metadata are skipped
]}]}


@pytest.fixture
def web(monkeypatch):
    """Answers MusicBrainz and AcoustID with prepared data and remembers the requests."""
    calls = []
    answers = {"musicbrainz.org": MUSICBRAINZ, "api.acoustid.org": ACOUSTID}

    def urlopen(request, timeout=None):
        calls.append(request)
        answer = answers[urllib.parse.urlsplit(request.full_url).hostname]
        if isinstance(answer, Exception):
            raise answer
        return _Response(json.dumps(answer).encode())

    monkeypatch.setattr(musiclookup.urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(musiclookup, "_last_request", 0.0)
    monkeypatch.setattr(musiclookup.time, "sleep", lambda seconds: None)
    return calls, answers


@pytest.fixture
def fpcalc(monkeypatch):
    monkeypatch.setattr(musiclookup, "find_tool", lambda name: "fpcalc" if name == "fpcalc" else None)
    monkeypatch.setattr(musiclookup, "fingerprint", lambda path: (181, "AQAAfingerprint"))


@pytest.mark.parametrize("name, expected", [
    ("Bard - Clash of Steel (Official Video).mp3", ("Bard", "Clash of Steel")),
    ("03 - Clash of Steel.mp3", (None, "Clash of Steel")),
    ("clash_of_steel.mp3", (None, "clash of steel")),
])
def test_guess_from_name(name, expected):
    assert musiclookup.guess_from_name(name) == expected


def test_musicbrainz_prefers_the_original_album_and_checks_the_length(web):
    calls, _ = web
    candidates = musiclookup.search_musicbrainz("Clash of Steel", "Bard", "x.mp3", length=180)
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)["query"][0]
    assert query == 'recording:"Clash of Steel" AND artist:"Bard"'
    assert calls[0].get_header("User-agent").startswith("DungeonTuber/")
    best, live = candidates
    assert (best.title, best.artist, best.album, best.track, best.year, best.score) == ("Clash of Steel", "Bard & Drums", "Steel", 3, "1999", 100)
    assert live.score == 45  # far longer than the song (-30) and on no studio album (-15): probably another version


def test_musicbrainz_prefers_the_recording_on_most_releases(web):
    _, answers = web
    album = {"title": "Steel", "status": "Official", "release-group": {"primary-type": "Album"}}
    answers["musicbrainz.org"] = {"recordings": [
        {"id": "bootleg", "score": 100, "title": "Clash", "artist-credit": [{"name": "Bard"}],
         "releases": [{"title": "Live in Ulm", "status": "Bootleg", "release-group": {"primary-type": "Album", "secondary-types": ["Live"]}}]},
        {"id": "single", "score": 100, "title": "Clash", "artist-credit": [{"name": "Bard"}], "releases": [dict(album, title="Clash EP")]},
        {"id": "original", "score": 100, "title": "Clash", "artist-credit": [{"name": "Bard"}], "releases": [album, album, album]},
    ]}
    candidates = musiclookup.search_musicbrainz("Clash", "Bard", "x.mp3")
    assert [(c.recording_id, c.score) for c in candidates] == [("original", 100), ("single", 100), ("bootleg", 85)]


def test_musicbrainz_uses_the_file_name_without_tags(web):
    calls, _ = web
    musiclookup.search_musicbrainz(None, None, "Bard - Clash of Steel.mp3")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)["query"][0]
    assert query == 'recording:"Clash of Steel" AND artist:"Bard"'


def test_musicbrainz_quotes_the_query(web):
    calls, _ = web
    musiclookup.search_musicbrainz('Say "hi"', None, "x.mp3")
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(calls[0].full_url).query)["query"][0]
    assert query == r'recording:"Say \"hi\""'


def test_acoustid_posts_the_fingerprint(web, fpcalc):
    calls, _ = web
    [candidate] = musiclookup.lookup_acoustid("song.mp3", "app-key", length=181)
    form = urllib.parse.parse_qs(calls[0].data.decode())
    assert form["client"] == ["app-key"] and form["fingerprint"] == ["AQAAfingerprint"] and form["duration"] == ["181"]
    assert "app-key" not in calls[0].full_url
    assert (candidate.title, candidate.album, candidate.track, candidate.year, candidate.score, candidate.source) == \
        ("Clash of Steel", "Steel", 3, "1999", 97, "acoustid")


def test_lookup_merges_both_and_reports_errors(web, fpcalc):
    _, answers = web
    result = musiclookup.lookup("song.mp3", "Clash of Steel", "Bard", "x.mp3", 181, "app-key")
    sources = [(c["title"], c["artist"], c["source"], c["score"]) for c in result["candidates"]]
    assert sources[:2] == [("Clash of Steel", "Bard & Drums", "musicbrainz", 100), ("Clash of Steel", "Bard", "acoustid", 97)]
    assert result["errors"] == []

    answers["api.acoustid.org"] = urllib.error.URLError("offline")
    result = musiclookup.lookup("song.mp3", "Clash of Steel", "Bard", "x.mp3", 181, "app-key")
    assert result["candidates"][0]["source"] == "musicbrainz"
    assert result["errors"] == ["api.acoustid.org: <urlopen error offline>"]


def test_lookup_skips_acoustid_without_key_or_fpcalc(web, monkeypatch):
    calls, _ = web
    monkeypatch.setattr(musiclookup, "find_tool", lambda name: None)
    musiclookup.lookup("song.mp3", "Clash of Steel", None, "x.mp3", None, "app-key")
    assert [urllib.parse.urlsplit(c.full_url).hostname for c in calls] == ["musicbrainz.org"]


@pytest.fixture
def client(tmp_path):
    root = tmp_path / "music"
    song = write_mp3(root / "Bard - Clash of Steel.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        test_client.song = song
        yield test_client
    index.close()
    set_index(None)


def test_lookup_route(client, web):
    response = client.get(f"/api/tracks/{path_to_id(client.song)}/lookup")
    assert response.status_code == 200
    assert response.json()["candidates"][0]["album"] == "Steel"


def test_lookup_route_rejects_files_outside_the_library(client, tmp_path, web):
    outside = write_mp3(tmp_path / "secret" / "song.mp3")
    assert client.get(f"/api/tracks/{path_to_id(outside)}/lookup").status_code in (403, 404)


def test_the_acoustid_key_is_never_sent_back(client):
    status = client.put("/api/metadata/config", json={"key": "acoustid-secret-1234"}).json()
    assert status["configured"] is True and status["keyHint"] == "1234"
    assert "acoustid-secret" not in json.dumps(client.get("/api/metadata/config").json())
    assert client.delete("/api/metadata/config").json()["configured"] is False


def test_normalized_flag_is_written_into_the_file(client):
    from mutagen.id3 import ID3

    from core.mp3 import parse_mp3

    track_id = path_to_id(client.song)
    recording = "b1a9c0e9-d987-4042-ae91-78d6a3267d69"
    data = client.patch(f"/api/tracks/{track_id}", json={"title": "Clash of Steel", "normalized": {"source": "acoustid", "recording_id": recording}}).json()
    assert data["normalized"]["source"] == "acoustid" and data["normalized"]["recording_id"] == recording and data["normalized"]["at"]
    tags = ID3(client.song)
    assert json.loads(tags["TXXX:dt_normalized"].text[0])["recording_id"] == recording
    assert tags["UFID:http://musicbrainz.org"].data == recording.encode()
    assert parse_mp3(client.song).normalized["source"] == "acoustid"

    # a later edit keeps the flag, an explicit null removes it
    assert client.patch(f"/api/tracks/{track_id}", json={"album": "Steel"}).json()["normalized"]["recording_id"] == recording
    assert client.patch(f"/api/tracks/{track_id}", json={"normalized": None}).json()["normalized"] is None
    assert "TXXX:dt_normalized" not in ID3(client.song) and "UFID:http://musicbrainz.org" not in ID3(client.song)


def test_normalized_flag_is_validated(client):
    track_id = path_to_id(client.song)
    assert client.patch(f"/api/tracks/{track_id}", json={"normalized": {"source": "spotify"}}).status_code == 422
    assert client.patch(f"/api/tracks/{track_id}", json={"normalized": {"source": "musicbrainz", "recording_id": "<script>"}}).status_code == 422


def test_skip_normalized_music_setting(client):
    assert client.get("/api/settings").json()["skipNormalizedMusic"] is True
    assert client.put("/api/settings", json={"skipNormalizedMusic": False}).status_code == 200
    assert client.get("/api/settings").json()["skipNormalizedMusic"] is False
