"""Creates a small library of silent, tagged mp3 files for manual UI testing.

Usage: python scripts/make_test_library.py <target-dir>
"""
import io
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lights import LightSetting  # noqa: E402
from core.mp3 import Mp3Entry, create_m3u, parse_mp3, update_mp3_chapters, update_mp3_cover_data, update_mp3_data  # noqa: E402

# One silent MPEG-1 Layer III frame (128 kbit/s, 44.1 kHz)
FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413
FRAMES_PER_SECOND = 38

SONGS = {
    "Tavern": [("Merry Inn", ["Tavern festivity", "Happy"], ["Folk"], 110), ("Bard's Tale", ["Calm", "Happy"], ["Folk"], 90),
               ("Drinking Song", ["Tavern festivity", "Energetic"], ["Folk", "Celtic"], 130)],
    "Battle": [("Clash of Steel", ["Combat skirmish", "Aggressive"], ["Metal"], 160), ("Siege", ["Industrial siege", "Dark"], ["Orchestral"], 140),
               ("Last Stand", ["Combat skirmish", "Dark"], ["Orchestral"], 150)],
    "Dungeon": [("Dripping Caves", ["Dark", "Calm"], ["Ambient"], 60), ("Crypt", ["Dark", "Sad"], ["Ambient"], 70)],
}

COLORS = {"Tavern": "#ffaa33", "Battle": "#ff2222", "Dungeon": "#3344ff"}


def cover(color: str) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (300, 300), color).save(out, format="JPEG")
    return out.getvalue()


def main(target: Path):
    random.seed(7)
    for folder, songs in SONGS.items():
        entries = []
        for title, tags, genres, bpm in songs:
            path = target / folder / f"{title}.mp3"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(FRAME * FRAMES_PER_SECOND * random.randint(40, 90))
            data = Mp3Entry(path, name=path.name, title=title, artist="Test Bard", album=folder, genre=genres, bpm=bpm, tags=tags,
                            categories={key: random.randint(0, 10) for key in ("Valence", "Arousal", "Engagement", "Darkness",
                                                                                "Aggressive", "Happy", "Party", "Relaxed", "Sad")})
            data.summary = f"A {tags[0].lower()} piece for the {folder.lower()}."
            data.light = LightSetting(color=COLORS[folder], brightness=200)
            update_mp3_data(path, data)
            update_mp3_cover_data(path, cover(COLORS[folder]), "image/jpeg")
            if title == "Clash of Steel":
                update_mp3_chapters(path, [{"title": "Charge", "time": 10000, "light": LightSetting(color="#ff0000")},
                                           {"title": "Retreat", "time": 30000, "light": LightSetting(temperature=2700)}])
            entries.append(parse_mp3(path))
        create_m3u(entries, target / f"{folder} Mix.m3u")

    effects = target / "Effects"
    for name in ("Rain", "Fire"):
        for level in (1, 2):
            path = effects / name / f"{level} {name.lower()}.mp3"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(FRAME * FRAMES_PER_SECOND * 10)
    print(f"Test library created in {target}")


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "test-library").resolve())
