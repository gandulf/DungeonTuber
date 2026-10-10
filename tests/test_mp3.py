from mutagen.id3 import ID3, TRCK, Encoding
from mutagen.mp3 import MP3

from conftest import write_mp3
from core.lights import LightSetting
from core.mp3 import (EffectEntry, Mp3Entry, list_mp3s, parse_mp3, parse_track_number, update_categories_and_tags, update_mp3_category, update_mp3_chapters,
                      update_mp3_cover_data, update_mp3_data, update_mp3_favorite, update_mp3_light, update_mp3_tags,
                      update_mp3_track)


def test_parse_untagged_file(mp3_file):
    entry = parse_mp3(mp3_file)

    assert entry is not None
    assert entry.name == "song"
    assert entry.length == 2
    assert entry.title is None
    assert entry.tags == []
    assert entry.favorite is False
    assert entry.chapters == []


def test_parse_invalid_file_returns_none(tmp_path):
    broken = tmp_path / "broken.mp3"
    broken.write_bytes(b"not an mp3")

    assert parse_mp3(broken) is None


def test_update_and_read_all_fields(mp3_file):
    data = Mp3Entry(mp3_file, name="song.mp3", title="Tavern", artist="Bard", album="Inn", genre=["Folk", "Celtic"], bpm=120,
                    tags=["Tavern festivity", "Happy"], categories={"Valence": 7, "Arousal": 4})
    data.summary = "A cheerful tune"
    data.favorite = True
    data.light = LightSetting(brightness=128, color="#FF8800")

    update_mp3_data(mp3_file, data)
    entry = parse_mp3(mp3_file)

    assert entry.title == "Tavern"
    assert entry.artist == "Bard"
    assert entry.album == "Inn"
    assert entry.genres == ["Folk", "Celtic"]
    assert entry.bpm == 120
    assert entry.tags == ["Tavern festivity", "Happy"]
    assert entry.categories == {"Valence": 7, "Arousal": 4}
    assert entry.summary == "A cheerful tune"
    assert entry.favorite is True
    assert entry.light.brightness == 128
    assert entry.light.color == "#ff8800"


def test_favorite_can_be_reset(mp3_file):
    update_mp3_favorite(mp3_file, True)
    assert parse_mp3(mp3_file).favorite is True

    update_mp3_favorite(mp3_file, False)
    assert parse_mp3(mp3_file).favorite is False


def test_legacy_favorite_frame_is_read(mp3_file):
    # Older versions wrote the python bool, which mutagen stores as text
    from mutagen.id3 import TXXX, Encoding
    audio = MP3(mp3_file, ID3=ID3)
    audio.add_tags()
    audio.tags.add(TXXX(Encoding.UTF8, desc="ai_favorite", text=[str(False)]))
    audio.save()

    assert parse_mp3(mp3_file).favorite is False


def test_clearing_values_removes_frames(mp3_file):
    update_mp3_tags(mp3_file, ["Dark"])
    update_mp3_light(mp3_file, LightSetting(color="#112233"))
    entry = parse_mp3(mp3_file)
    assert entry.tags == ["Dark"]
    assert entry.light is not None

    update_mp3_tags(mp3_file, [])
    update_mp3_light(mp3_file, None)
    entry = parse_mp3(mp3_file)
    assert entry.tags == []
    assert entry.light is None


def test_update_single_category(mp3_file):
    update_mp3_category(mp3_file, "Darkness", 8)
    update_mp3_category(mp3_file, "Happy", 2)
    assert parse_mp3(mp3_file).categories == {"Darkness": 8, "Happy": 2}

    update_mp3_category(mp3_file, "Darkness", None)
    assert parse_mp3(mp3_file).categories == {"Happy": 2}


def test_analyzer_result_format_is_accepted(mp3_file):
    update_categories_and_tags(mp3_file, "Summary", [{"category": "Valence", "scale": 3}], ["Calm"])

    entry = parse_mp3(mp3_file)
    assert entry.summary == "Summary"
    assert entry.categories == {"Valence": 3}
    assert entry.tags == ["Calm"]


def test_chapters_roundtrip_and_replace(mp3_file):
    chapters = [
        {"title": "Fight", "time": 1000, "light": LightSetting(color="#ff0000")},
        {"title": "Intro", "time": 0, "light": None},
    ]
    update_mp3_chapters(mp3_file, chapters)

    entry = parse_mp3(mp3_file)
    assert [c["title"] for c in entry.chapters] == ["Intro", "Fight"]
    assert entry.chapters[0]["light"] is None
    assert entry.chapters[1]["light"].color == "#ff0000"

    update_mp3_chapters(mp3_file, [{"title": "Only", "time": 500, "light": None}])
    entry = parse_mp3(mp3_file)
    assert [c["title"] for c in entry.chapters] == ["Only"]

    update_mp3_chapters(mp3_file, [])
    assert parse_mp3(mp3_file).chapters == []


def test_cover_data(mp3_file):
    entry = parse_mp3(mp3_file)
    assert entry.has_cover is False
    assert entry.cover_data() is None

    update_mp3_cover_data(mp3_file, b"\x89PNG fake", "image/png")
    entry.clear_cover()

    assert entry.has_cover is True
    assert entry.cover_data() == (b"\x89PNG fake", "image/png")


def test_list_mp3s_recursive(tmp_path):
    write_mp3(tmp_path / "a.mp3")
    write_mp3(tmp_path / "sub" / "b.mp3")

    assert list_mp3s(tmp_path, recursive=False) == ["a.mp3"]
    assert sorted(p.replace("\\", "/") for p in list_mp3s(tmp_path)) == ["a.mp3", "sub/b.mp3"]


def test_effect_from_directory(tmp_path):
    folder = tmp_path / "Rain"
    for name in ("2 heavy.mp3", "1 light.mp3"):
        write_mp3(folder / name)
    (folder / "cover.jpg").write_bytes(b"jpg")

    effect = EffectEntry.from_file(folder)

    assert effect.name == "Rain"
    assert effect.has_intensities()
    assert [e.name for e in effect.intensities] == ["1 light", "2 heavy"]
    assert effect.cover_path == folder / "cover.jpg"
    assert effect.title == "Rain"


def test_effect_folder_with_too_many_files_is_ignored(tmp_path):
    folder = tmp_path / "Crowd"
    for i in range(EffectEntry.MAX_INTENSITIES + 1):
        write_mp3(folder / f"{i}.mp3")

    assert EffectEntry.from_directory(folder) is None


def test_to_dict(mp3_file):
    update_mp3_chapters(mp3_file, [{"title": "A", "time": 0, "light": LightSetting(color="#010203")}])
    data = parse_mp3(mp3_file).to_dict()

    assert data["name"] == "song"
    assert data["chapters"] == [{"title": "A", "time": 0, "light": {"scene": None, "brightness": 255, "temperature": None, "color": "#010203"}}]


def test_track_number_is_read_and_written(mp3_file):
    assert parse_mp3(mp3_file).track is None
    audio = MP3(mp3_file, ID3=ID3)
    audio.add_tags()
    audio.tags.add(TRCK(Encoding.UTF8, text=["3/12"]))
    audio.save()
    assert parse_mp3(mp3_file).track == 3

    update_mp3_track(mp3_file, 7)  # the total is kept
    assert str(MP3(mp3_file, ID3=ID3).tags["TRCK"].text[0]) == "7/12"
    assert parse_mp3(mp3_file).to_dict()["track"] == 7
    update_mp3_track(mp3_file, None)
    assert parse_mp3(mp3_file).track is None
    assert [parse_track_number(v) for v in ("05", " 2 / 9", "x", "0", None)] == [5, 2, None, None, None]
