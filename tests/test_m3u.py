from conftest import write_mp3
from core.mp3 import append_m3u, create_m3u, get_m3u_paths, parse_m3u, parse_mp3, remove_m3u, save_playlist


def _songs(tmp_path, *names):
    return [parse_mp3(write_mp3(tmp_path / "music" / name)) for name in names]


def test_create_and_parse_relative_paths(tmp_path):
    songs = _songs(tmp_path, "a.mp3", "b.mp3")
    playlist = tmp_path / "list.m3u"

    create_m3u(songs, playlist)

    content = playlist.read_text(encoding="utf-8")
    assert content.startswith("#EXTM3U\n")
    assert "music/a.mp3" in content
    assert [e.name for e in parse_m3u(playlist)] == ["a", "b"]


def test_non_extended_m3u_is_rejected(tmp_path):
    playlist = tmp_path / "plain.m3u"
    playlist.write_text("a.mp3\n", encoding="utf-8")

    assert get_m3u_paths(playlist) is None
    assert parse_m3u(playlist) is None


def test_append_to_new_playlist_writes_header(tmp_path):
    songs = _songs(tmp_path, "a.mp3")
    playlist = tmp_path / "new.m3u"

    append_m3u(songs, playlist)

    assert [e.name for e in parse_m3u(playlist)] == ["a"]


def test_append_and_insert(tmp_path):
    a, b, c = _songs(tmp_path, "a.mp3", "b.mp3", "c.mp3")
    playlist = tmp_path / "list.m3u"
    create_m3u([a], playlist)

    append_m3u([c], playlist)
    append_m3u([b], playlist, index=1)

    assert [e.name for e in parse_m3u(playlist)] == ["a", "b", "c"]


def test_remove_all_entries_leaves_empty_playlist(tmp_path):
    a, b = _songs(tmp_path, "a.mp3", "b.mp3")
    playlist = tmp_path / "list.m3u"
    create_m3u([a, b], playlist)

    remove_m3u([a], playlist)
    assert [e.name for e in parse_m3u(playlist)] == ["b"]

    remove_m3u([b], playlist)
    assert parse_m3u(playlist) == []


def test_missing_files_are_skipped(tmp_path):
    a, b = _songs(tmp_path, "a.mp3", "b.mp3")
    playlist = tmp_path / "list.m3u"
    create_m3u([a, b], playlist)
    b.path.unlink()

    assert [e.name for e in parse_m3u(playlist)] == ["a"]


def test_save_playlist(tmp_path):
    playlist = tmp_path / "favorites.m3u"

    assert save_playlist(playlist, []) is False
    assert not playlist.exists()

    assert save_playlist(playlist, _songs(tmp_path, "a.mp3")) is True
    assert playlist.exists()
