"""MP3 data model, ID3 tag reading/writing and M3U playlists."""
import glob
import json
import logging
import os
import traceback
from os import PathLike
from pathlib import Path
from typing import TypedDict, Iterator, Iterable

from mutagen.id3 import ID3, TXXX, COMM, TIT2, TCON, TALB, TPE1, TBPM, APIC, Encoding, PictureType, CHAP, CTOC
from mutagen.mp3 import MP3

from core.lights import LightSetting

logger = logging.getLogger(__file__)

_TRUE_STRINGS = {"true", "1", "yes"}


class Chapter(TypedDict):
    title: str
    time: int
    light: LightSetting | None


def _read_cover_frame(tags) -> APIC | None:
    if not tags:
        return None
    if "APIC:Cover" in tags:
        return tags["APIC:Cover"]
    for key in tags.keys():
        # APIC tags often have suffixes like APIC:thumbnail etc
        if key.startswith("APIC"):
            return tags[key]
    return None


class Mp3Entry(object):
    __slots__ = ["index", "name", "path", "title", "artist", "album", "summary", "genres", "length", "favorite", "categories", "_tags",
                 "_has_cover", "bpm", "light", "chapters", "__weakref__"]

    index: int | None
    name: str | None
    path: Path
    title: str | None
    artist: str | None
    album: str | None
    summary: str | None
    genres: list[str]
    length: int
    favorite: bool
    _has_cover: bool | None
    bpm: int | None
    light: LightSetting | None

    categories: dict[str, int]
    _tags: list[str]

    chapters: list[Chapter]

    def __init__(self, path: PathLike[str], name: str | None = None, categories: dict[str, int] | None = None, tags: list[str] | None = None,
                 artist: str | None = None, album: str | None = None, title: str | None = None, genre: list[str] | str | None = None,
                 bpm: int | None = None):
        if name is not None:
            self.name = name.removesuffix(".mp3").removesuffix(".MP3").removesuffix(".Mp3")
        else:
            self.name = None
        self.path = path if isinstance(path, Path) else Path(path)
        self.title = title
        self.artist = artist
        self.album = album
        if isinstance(genre, str):
            self.genres = [genre]
        elif genre:
            self.genres = list(genre)
        else:
            self.genres = []
        self.summary = ""
        self.length = -1
        self.favorite = False
        self.categories = categories if categories else {}
        self._tags = list(tags) if tags else []
        self._has_cover = None
        self.bpm = bpm
        self.index = None
        self.light = None
        self.chapters = []

    @property
    def length_in_ms(self):
        if self.length:
            return int(self.length * 1000)
        else:
            return None

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, tags: list[str]):
        self._tags = tags

    def add_tag(self, tag: str):
        self.tags.append(tag)

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, Mp3Entry):
            return False
        return self.path == other.path

    def get_category_value(self, category_key: str):
        if self.categories is not None:
            return self.categories.get(category_key, None)
        return None

    # --- cover --------------------------------------------------------
    def cover_data(self) -> tuple[bytes, str] | None:
        """Raw embedded cover image and its mime type, read from the file on demand."""
        if self._has_cover is False:
            return None
        try:
            frame = _read_cover_frame(MP3(self.path, ID3=ID3).tags)
        except Exception as e:
            logger.warning("Unable to read cover of {0}: {1}", self.path, e)
            frame = None
        self._has_cover = frame is not None
        if frame is None:
            return None
        return frame.data, frame.mime or "image/jpeg"

    @property
    def has_cover(self) -> bool:
        if self._has_cover is None:
            self.cover_data()
        return bool(self._has_cover)

    def clear_cover(self):
        """Forget the cached cover state, e.g. after the cover was changed."""
        self._has_cover = None

    @property
    def color(self) -> str | None:
        if self.light and self.light.color:
            return self.light.color
        return None

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.name,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "summary": self.summary,
            "genres": list(self.genres),
            "tags": list(self.tags),
            "length": self.length,
            "favorite": self.favorite,
            "categories": dict(self.categories),
            "bpm": self.bpm,
            "light": self.light.to_dict() if self.light else None,
            "chapters": [{"title": c["title"], "time": c["time"], "light": c["light"].to_dict() if c.get("light") else None}
                         for c in self.chapters],
        }


class EffectEntry(object):
    """An effect: a single mp3, or a folder with up to 5 mp3s used as intensities."""
    __slots__ = ["intensities", "intensity", "name", "cover_path", "__weakref__"]

    MAX_INTENSITIES = 5

    intensities: list[Mp3Entry]
    intensity: int
    name: str
    cover_path: Path | None

    def __init__(self, datas: list[Mp3Entry], name: str, cover_path: PathLike[str] | None = None):
        datas.sort(key=lambda x: x.name, reverse=False)
        self.intensities = datas
        self.name = name
        self.cover_path = Path(cover_path) if cover_path else None
        self.intensity = 0

    def __hash__(self):
        return hash(self.mp3_entry)

    def __eq__(self, other):
        if isinstance(other, Mp3Entry):
            return self.mp3_entry == other
        elif not isinstance(other, EffectEntry):
            return False
        return self.intensities == other.intensities

    @property
    def light(self):
        if self.mp3_entry is not None and self.mp3_entry.light is not None:
            return self.mp3_entry.light
        return None

    @property
    def mp3_entry(self):
        if len(self.intensities) > 0:
            return self.intensities[self.intensity]
        return None

    @property
    def has_cover(self) -> bool:
        if self.mp3_entry is not None and self.mp3_entry.has_cover:
            return True
        return self.cover_path is not None

    def has_intensities(self):
        return len(self.intensities) > 1

    @property
    def title(self):
        if self.has_intensities():
            return self.name
        elif self.mp3_entry is not None:
            return self.mp3_entry.title
        return None

    @property
    def color(self):
        if self.mp3_entry is not None:
            return self.mp3_entry.color
        return None

    @classmethod
    def from_directory(cls, directory: PathLike[str]):
        cover_file = os.path.join(directory, "cover.jpg")
        cover_path = cover_file if os.path.isfile(cover_file) else None

        mp3_files = list_mp3s(directory, recursive=False)
        if len(mp3_files) <= cls.MAX_INTENSITIES:
            effects = [parse_mp3(os.path.join(directory, entry)) for entry in mp3_files]
            effects = [effect for effect in effects if effect is not None]
            return EffectEntry(effects, Path(directory).name, cover_path=cover_path)
        return None

    @classmethod
    def from_file(cls, file: PathLike[str]):
        if os.path.isdir(file):
            return EffectEntry.from_directory(file)
        elif os.path.isfile(file):
            mp3_entry = parse_mp3(file)
            if mp3_entry is None:
                return None
            return EffectEntry([mp3_entry], mp3_entry.name)
        return None


def _parse_favorite(frame) -> bool:
    if not frame or not frame.text:
        return False
    return str(frame.text[0]).strip().lower() in _TRUE_STRINGS


def parse_mp3(file_path: PathLike[str]) -> Mp3Entry | None:
    try:
        entry = Mp3Entry(file_path, name=Path(file_path).name)
        audio = MP3(file_path, ID3=ID3)

        entry.length = int(audio.info.length)

        if audio.tags:
            if "TIT2" in audio.tags:
                entry.title = audio.tags.get("TIT2").text[0]

            if "TPE1" in audio.tags:
                entry.artist = audio.tags.get("TPE1").text[0]

            if "TALB" in audio.tags:
                entry.album = audio.tags.get("TALB").text[0]

            if 'TCON' in audio.tags:
                entry.genres = list(audio.tags.get('TCON').text)

            if 'TBPM' in audio.tags:
                try:
                    entry.bpm = int(float(str(audio.tags.get('TBPM').text[0])))
                except (ValueError, IndexError):
                    entry.bpm = None

            # Get Summary (COMM)
            if "COMM::XXX" in audio.tags:
                comm_frame = audio.tags.get("COMM::XXX")
                if comm_frame.text:
                    entry.summary = comm_frame.text[0]
            else:
                for key in audio.tags.keys():
                    if key.startswith("COMM"):
                        comm_frame = audio.tags[key]
                        if comm_frame.text:
                            entry.summary = comm_frame.text[0]
                        break

            # Get Categories (TXXX:ai_categories)
            txxx_cats = audio.tags.get("TXXX:ai_categories")
            if txxx_cats and txxx_cats.text and txxx_cats.text[0]:
                try:
                    cats_map = json.loads(txxx_cats.text[0])
                    if isinstance(cats_map, dict):
                        entry.categories = cats_map
                except json.JSONDecodeError:
                    pass

            txxx_tags = audio.tags.get("TXXX:ai_tags")
            if txxx_tags and txxx_tags.text:
                entry.tags = [tag for tag in txxx_tags.text if tag]

            entry.favorite = _parse_favorite(audio.tags.get("TXXX:ai_favorite"))

            light = audio.tags.get("TXXX:ai_light")
            if light and light.text and light.text[0]:
                entry.light = LightSetting.json_load(light.text[0])

            chapter_list: list[Chapter] = []
            for key in audio.tags.keys():
                if key.startswith("CHAP"):
                    frame = audio.tags[key]
                    # sub_frames contains TIT2 (Title)
                    title = frame.sub_frames.get("TIT2", ["Unknown"])[0]
                    chapter_light_frame = frame.sub_frames.get("TXXX:ai_light")
                    chapter_light: LightSetting | None = None
                    if chapter_light_frame and chapter_light_frame.text and chapter_light_frame.text[0]:
                        chapter_light = LightSetting.json_load(chapter_light_frame.text[0])

                    chapter_list.append({
                        "time": frame.start_time,
                        "title": str(title),
                        "light": chapter_light,
                    })

            chapter_list.sort(key=lambda c: c["time"])
            entry.chapters = chapter_list

        return entry
    except Exception as e:
        logger.error("Error reading tags for {0}: {1}", file_path, e)
        traceback.print_exc()
    return None


def iter_mp3_entries(files: Iterable[PathLike[str]], is_interrupted=lambda: False) -> Iterator[Mp3Entry]:
    """Parses the given files lazily, skipping unreadable ones."""
    for file_path in files:
        if is_interrupted():
            break
        entry = parse_mp3(file_path)
        if entry is not None:
            yield entry


def _audio(path: PathLike[str] | MP3) -> MP3:
    if isinstance(path, MP3):
        audio = path
    else:
        audio = MP3(path, ID3=ID3)

    if audio.tags is None:
        audio.add_tags()

    return audio


def update_mp3_data(path: PathLike[str], data: Mp3Entry):
    audio = _audio(path)

    update_mp3_title(audio, data.title, False)
    update_mp3_album(audio, data.album, False)
    update_mp3_artist(audio, data.artist, False)
    update_mp3_bpm(audio, data.bpm, False)
    update_mp3_genre(audio, data.genres, False)
    update_mp3_summary(audio, data.summary, False)
    update_mp3_favorite(audio, data.favorite, False)
    update_mp3_categories(audio, data.categories, False)
    update_mp3_tags(audio, data.tags, False)
    update_mp3_light(audio, data.light, False)

    audio.save()


def update_mp3(path: PathLike[str], title: str, summary: str, favorite: bool, categories: dict[str, int], tags: list[str], genre: str = None):
    audio = _audio(path)

    update_mp3_title(audio, title, False)
    update_mp3_genre(audio, genre, False)
    update_mp3_summary(audio, summary, False)
    update_mp3_favorite(audio, favorite, False)
    update_mp3_categories(audio, categories, False)
    update_mp3_tags(audio, tags, False)

    audio.save()


def _set_text_frame(audio: MP3, frame_id: str, frame_cls, value):
    if value is None or value == "" or value == []:
        audio.tags.delall(frame_id)
    else:
        audio.tags.add(frame_cls(Encoding.UTF8, text=value if isinstance(value, list) else [value]))


def update_mp3_favorite(path: PathLike[str] | MP3, favorite: bool, save: bool = True):
    audio = _audio(path)

    audio.tags.add(TXXX(Encoding.UTF8, desc='ai_favorite', text=["True" if favorite else "False"]))

    if save:
        audio.save()
        logger.debug("Updated favorite to {0} for {1}", favorite, path)


def update_mp3_summary(path: str | PathLike[str] | MP3, new_summary: str, save: bool = True):
    audio = _audio(path)

    audio.tags.add(COMM(Encoding.UTF8, text=[new_summary] if new_summary else ""))

    if save:
        audio.save()
        logger.debug("Updated summary to {0} for {1}", new_summary, path)


def update_mp3_title(path: str | PathLike[str] | MP3, new_title: str, save: bool = True):
    audio = _audio(path)

    _set_text_frame(audio, "TIT2", TIT2, new_title)
    if save:
        audio.save()
        logger.debug("Updated title to {0} for {1}", new_title, path)


def update_mp3_album(path: str | PathLike[str] | MP3, new_album: str, save: bool = True):
    audio = _audio(path)

    _set_text_frame(audio, "TALB", TALB, new_album)
    if save:
        audio.save()
        logger.debug("Updated album to {0} for {1}", new_album, path)


def update_mp3_artist(path: str | PathLike[str] | MP3, new_artist: str, save: bool = True):
    audio = _audio(path)

    _set_text_frame(audio, "TPE1", TPE1, new_artist)
    if save:
        audio.save()
        logger.debug("Updated artist to {0} for {1}", new_artist, path)


def update_mp3_bpm(path: str | PathLike[str] | MP3, new_bpm: int | None, save: bool = True):
    audio = _audio(path)

    _set_text_frame(audio, "TBPM", TBPM, str(new_bpm) if new_bpm is not None else None)
    if save:
        audio.save()
        logger.debug("Updated bpm to {0} for {1}", new_bpm, path)


def update_mp3_genre(path: str | PathLike[str] | MP3, new_genre: list[str] | str | None, save: bool = True):
    audio = _audio(path)

    _set_text_frame(audio, "TCON", TCON, new_genre)

    if save:
        audio.save()
        logger.debug("Updated genre to {0} for {1}", new_genre, path)


def update_mp3_categories(path: PathLike[str] | MP3, categories: dict[str, int] | list[dict] | None, save: bool = True):
    audio = _audio(path)

    if categories:
        if isinstance(categories, list):
            categories = {item['category']: item['scale'] for item in categories}

        audio.tags.add(TXXX(Encoding.UTF8, desc='ai_categories', text=[json.dumps(categories, ensure_ascii=False)]))
    else:
        audio.tags.delall("TXXX:ai_categories")

    if save:
        audio.save()


def update_mp3_category(path: str | PathLike[str] | MP3, category: str, new_value: int | None, save: bool = True):
    audio = _audio(path)

    cats = {}
    txxx_cats = audio.tags.get("TXXX:ai_categories")
    if txxx_cats and txxx_cats.text and txxx_cats.text[0]:
        try:
            cats = json.loads(txxx_cats.text[0])
        except json.JSONDecodeError:
            pass

    if new_value is None:
        cats.pop(category, None)
    else:
        cats[category] = new_value

    audio.tags.add(TXXX(Encoding.UTF8, desc='ai_categories', text=[json.dumps(cats, ensure_ascii=False)]))
    if save:
        audio.save()
        logger.debug("Updated {0} to {1} for {2}", category, new_value, path)


def update_mp3_tags(path: str | PathLike[str] | MP3, tags: list[str] | None, save: bool = True):
    audio = _audio(path)

    if tags:
        audio.tags.add(TXXX(Encoding.UTF8, desc='ai_tags', text=list(tags)))
    else:
        audio.tags.delall("TXXX:ai_tags")

    if save:
        audio.save()
        logger.debug("Updated tags to {0} for {1}", tags, path)


def update_mp3_light(path: str | PathLike[str] | MP3, light: LightSetting | None, save: bool = True):
    audio = _audio(path)

    if light:
        audio.tags.add(TXXX(Encoding.UTF8, desc='ai_light', text=[light.json_dump()]))
    else:
        audio.tags.delall("TXXX:ai_light")

    if save:
        audio.save()
        logger.debug("Updated light to {0} for {1}", light.json_dump() if light else None, path)


def update_mp3_chapters(path: str | PathLike[str] | MP3, chapters: list[Chapter], save: bool = True):
    audio = _audio(path)

    # Replace all existing chapters, otherwise removed chapters would survive in the file
    audio.tags.delall("CHAP")
    audio.tags.delall("CTOC")

    if chapters:
        chapters.sort(key=lambda x: x["time"])

        total_chapters = len(chapters)
        for index, chapter in enumerate(chapters):
            if index < total_chapters - 1:
                end_time = chapters[index + 1]["time"]
            else:
                end_time = int(audio.info.length * 1000)

            sub_frames = [TIT2(text=[chapter["title"]])]
            if chapter.get("light") is not None:
                sub_frames.append(TXXX(Encoding.UTF8, desc='ai_light', text=[chapter["light"].json_dump()]))

            audio.tags.add(CHAP(
                element_id=f"ch{index}",
                start_time=chapter["time"],
                end_time=end_time,
                sub_frames=sub_frames
            ))

        # Table of contents (required for navigation)
        audio.tags.add(CTOC(
            element_id="toc",
            flags=0x03,  # Top-level & ordered
            child_element_ids=[f"ch{i}" for i in range(len(chapters))]
        ))

    if save:
        audio.save()
        logger.debug("Updated chapters to {0} for {1}", chapters, path)


def list_mp3s(path: PathLike[str], recursive: bool = True) -> list[str]:
    """Mp3 files below path, relative to path."""
    if isinstance(path, os.DirEntry):
        path = path.path

    pattern = os.path.join("**", "*.mp3") if recursive else "*.mp3"
    return sorted(glob.glob(pattern, root_dir=path, recursive=recursive))


def update_categories_and_tags(path: PathLike[str] | MP3, summary: str, categories: dict[str, int] | list[dict] = None, tags: list[str] = None,
                               genres: list[str] | None = None, bpm: int | None = None):
    """Adds categories and summary as MP3 tags to the file; genres and bpm are only replaced when the analysis found some."""
    audio = _audio(path)

    update_mp3_summary(audio, summary, False)
    update_mp3_categories(audio, categories, False)
    update_mp3_tags(audio, tags, False)
    if genres:
        update_mp3_genre(audio, genres, False)
    if bpm:
        update_mp3_bpm(audio, int(round(bpm)), False)

    audio.save()
    logger.debug("Tags added to {0}", path)


def guess_image_mime(image_path: str) -> str:
    lower = str(image_path).lower()
    if lower.endswith(".png"):
        return 'image/png'
    if lower.endswith(".bmp"):
        return 'image/bmp'
    if lower.endswith(".gif"):
        return 'image/gif'
    return 'image/jpeg'


def update_mp3_cover_data(path: PathLike[str] | MP3, data: bytes, mime: str):
    audio = _audio(path)
    audio.tags.delall("APIC")
    audio.tags.add(APIC(encoding=Encoding.UTF8, mime=mime, type=PictureType.COVER_FRONT, desc='Cover', data=data))
    audio.save()


def update_mp3_cover(path: PathLike[str] | MP3, image_path: PathLike[str]):
    with open(image_path, 'rb') as img:
        img_data = img.read()

    update_mp3_cover_data(path, img_data, guess_image_mime(str(image_path)))


def print_mp3_tags(file_path: PathLike[str]):
    """Logs all ID3 tags from an MP3 file at debug level."""
    try:
        if logger.isEnabledFor(logging.DEBUG):
            audio = MP3(file_path, ID3=ID3)
            if audio.tags:
                logger.debug("\n--- Tags for {0} ---", file_path)
                for key, value in audio.tags.items():
                    if not key.startswith("APIC"):
                        logger.debug("{0}: {1}", key, value)
                logger.debug("---------------------------------\n")
            else:
                logger.warning("No tags found in {0}", file_path)
    except Exception as e:
        logger.error("An error occurred while reading tags: {0}", e)


# --- M3U playlists ------------------------------------------------------

def _write_m3u_entries(of, entries: list[Mp3Entry], playlist: PathLike[str]):
    base = str(Path(playlist).parent)
    for mp3 in entries:
        relpath = os.path.relpath(mp3.path, base).replace("\\", "/")
        of.write(f"#EXTINF:{mp3.length},{mp3.name}\n")
        of.write(relpath + "\n")


def remove_m3u(entries: list[Mp3Entry], playlist: PathLike[str]):
    files = parse_m3u(playlist) or []
    filtered = [file for file in files if file not in entries]
    create_m3u(filtered, playlist, allow_empty=True)


def append_m3u(entries: list[Mp3Entry], playlist: PathLike[str], index: int = -1):
    if len(entries) == 0:
        logger.warning("No mp3 files found.")
        return

    try:
        if index < 0 and os.path.isfile(playlist):
            logger.debug("Appending playlist '{0}'...", playlist)
            with open(playlist, 'a', encoding="utf-8") as of:
                _write_m3u_entries(of, entries, playlist)
        else:
            mp3s = parse_m3u(playlist) if os.path.isfile(playlist) else []
            mp3s = mp3s or []
            if index < 0:
                mp3s.extend(entries)
            else:
                for entry in reversed(entries):
                    mp3s.insert(index, entry)
            create_m3u(mp3s, playlist)
    except OSError as e:
        logger.error("Unable to update playlist {0}: {1}", playlist, e)


def create_m3u(entries: list[Mp3Entry], playlist: PathLike[str], allow_empty: bool = False):
    if len(entries) == 0 and not allow_empty:
        logger.warning("No mp3 files found.")
        return

    try:
        logger.debug("Writing playlist '{0}'...", playlist)
        with open(playlist, 'w', encoding="utf-8") as of:
            of.write("#EXTM3U\n")
            _write_m3u_entries(of, entries, playlist)
    except OSError as e:
        logger.error("Unable to write playlist {0}: {1}", playlist, e)


def get_m3u_paths(file_path: PathLike[str]) -> list[Path] | None:
    with open(file_path, 'r', encoding="utf-8") as infile:
        # All M3U files start with #EXTM3U, otherwise it is not an extended M3U or corrupted.
        line = infile.readline()
        if not line.lstrip("﻿").startswith('#EXTM3U'):
            return None

        paths = []
        base_dir = Path(file_path).parent

        for line in infile:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            paths.append(Path(line) if Path(line).is_absolute() else Path(base_dir, line))
    return paths


def parse_m3u(file_path: PathLike[str]) -> list[Mp3Entry] | None:
    paths = get_m3u_paths(file_path)
    if paths is None:
        return None

    return list(iter_mp3_entries(paths))


def save_playlist(playlist_path, entries: list[Mp3Entry]) -> bool:
    if entries and len(entries) > 0:
        create_m3u(entries, playlist_path)
        return True
    return False
