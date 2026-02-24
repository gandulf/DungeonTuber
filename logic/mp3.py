import os

import sys
import glob
import json
import logging
from pathlib import Path
from os import PathLike

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap, QColor
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TXXX, COMM, TIT2, TCON, TALB, TPE1, TBPM, APIC, Encoding, PictureType

logger = logging.getLogger("main")

class Mp3Entry(object):
    __slots__ = ["index", "name", "path", "title", "artist", "album", "summary", "genres", "length", "favorite", "categories", "_tags", "_cover", "has_cover", "bpm","_moods", "color"]

    index: int
    name: str
    path: Path
    title: str
    artist: str
    album: str
    summary: str
    genres: list[str]
    length: int
    favorite: bool
    _cover: QPixmap | None
    has_cover: bool
    bpm: int
    color: QColor

    categories : dict[str,int]
    _tags: list[str]

    def __init__(self, name: str = None, path :PathLike[str] = None, categories : dict[str,int] = None, tags: list[str] = [], artist: str = None, album:str = None, title:str = None, genre:list[str] | str = [], bpm: int = None):
        if name is not None:
            self.name = name.removesuffix(".mp3").removesuffix(".MP3").removesuffix(".Mp3")
        else:
            self.name = None
        self.path = path
        self.path = path if isinstance(path, Path) else Path(path)
        self.title = title
        self.artist = artist
        self.album = album
        if isinstance(genre, str):
            self.genres = [genre]
        elif genre:
            self.genres = genre
        else:
            self.genres = []
        self.summary =""
        self.length =-1
        self.favorite = False
        if categories:
            self.categories = categories
        else:
            self.categories = {}

        if tags:
            self._tags = tags
        else:
            self._tags = []

        self._cover = None
        self.has_cover = None
        self.bpm = bpm
        self.index = None
        self.color = None

    @property
    def tags(self):
        return self._tags

    @tags.setter
    def tags(self, tags: list[str]):
        self._tags = tags

    def add_tag(self, tag:str):
        self.tags.append(tag)

    def _le(self, category, value) -> bool:
        return category in self.categories and self.get_category_value(category) <= value

    def _ge(self, category, value) -> bool:
        return category in self.categories and self.get_category_value(category) >= value

    def __hash__(self):
        return hash(self.path)

    def __eq__(self, other):
        if not isinstance(other, Mp3Entry):
            return False
        return self.path == other.path

    def get_category_value(self, category_key: str):
        if self.categories is not None and category_key in self.categories:
            return self.categories.get(category_key, None)
        else:
            return None

    @property
    def cover(self):
        self._load_cover()
        return self._cover

    def clear_cover(self):
        self._cover = None
        self.has_cover = None

    def _load_cover(self, audio: MP3 = None):
        if self.has_cover is None and self._cover is None:
            if audio is None:
                audio = MP3(self.path, ID3=ID3)
            self.has_cover = False
            for key in audio.tags.keys():
                # APIC tags often have suffixes like APIC:Cover
                if key.startswith("APIC"):
                    data = audio.tags[key].data
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    icon_pixmap = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
                    self._cover = icon_pixmap
                    self.has_cover = True

def parse_mp3(file_path : PathLike[str]) -> Mp3Entry | None:

    try:
        entry = Mp3Entry(name=Path(file_path).name, path=file_path)
        audio = MP3(file_path, ID3=ID3)

        entry.length = int(audio.info.length)

        if audio.tags:

            if "TIT2" in audio.tags:
                entry.title = audio.tags.get("TIT2").text[0]

            if "TPE1" in audio.tags:
                entry.artist = audio.tags.get("TPE1").text[0]

            if "TALB" in audio.tags:
                entry.album = audio.tags.get("TALB").text[0]

            if 'TCON' in audio:
                entry.genres = audio.tags.get('TCON').text

            if 'TBPM' in audio:
                entry.bpm = int(audio.tags.get('TBPM').text[0])

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
            if txxx_cats and txxx_cats.text:
                try:
                    cats_map = json.loads(txxx_cats.text[0])
                    if isinstance(cats_map, dict):
                        entry.categories = cats_map

                except json.JSONDecodeError:
                    pass

            # Get Tags
            txxx_tags = audio.tags.get("TXXX:ai_tags")
            if txxx_tags and txxx_tags.text:
                entry.tags = txxx_tags.text

            txxx_fav = audio.tags.get("TXXX:ai_favorite")
            if txxx_fav and txxx_fav.text:
                entry.favorite = bool(txxx_fav.text)

            color = audio.tags.get("TXXX:ai_color")
            if color and color.text:
                entry.color = QColor.fromString(color.text[0])

        return entry
    except Exception as e:
        logger.error("Error reading tags for {0}: {1}", file_path, e)
    return None

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
    update_mp3_genre(audio, data.genres, False)
    update_mp3_album(audio, data.album, False)
    update_mp3_artist(audio, data.artist, False)
    update_mp3_bpm(audio, data.bpm, False)
    update_mp3_genre(audio, data.genres, False)
    update_mp3_summary(audio, data.summary, False)
    update_mp3_favorite(audio, data.favorite, False)
    update_mp3_categories(audio, data.categories, False)
    update_mp3_tags(audio, data.tags, False)
    update_mp3_color(audio, data.color, False)

    audio.save()

def update_mp3(path : PathLike[str], title: str, summary: str, favorite: bool, categories: dict[str,int], tags: list[str], genre:str = None):
    audio = _audio(path)

    update_mp3_title(audio, title, False)
    update_mp3_genre(audio, genre, False)
    update_mp3_summary(audio,summary,False)
    update_mp3_favorite(audio,favorite,False)
    update_mp3_categories(audio,categories,False)
    update_mp3_tags(audio,tags,False)

    audio.save()

def update_mp3_favorite(path : PathLike[str] | MP3, favorite: bool, save: bool = True):
    audio = _audio(path)

    audio.tags.add(TXXX(Encoding.UTF8, desc='ai_favorite', text=[favorite]))

    if save:
        audio.save()
        logger.debug("Updated favorite to {0} for {1}", favorite, path)

def update_mp3_summary(path : str| PathLike[str] | MP3, new_summary :str, save : bool = True):
    audio = _audio(path)

    if new_summary:
        audio.tags.add(COMM(Encoding.UTF8, text=[new_summary]))
    else:
        audio.tags.add(COMM(Encoding.UTF8, text=""))

    if (save):
        audio.save()
        logger.debug("Updated summary to {0} for {1}", new_summary,path)

def update_mp3_title(path : str| PathLike[str]| MP3, new_title :str, save : bool = True):
    audio = _audio(path)

    audio.tags.add(TIT2(Encoding.UTF8, text=[new_title]))
    if save:
        audio.save()
        logger.debug("Updated title to {0} for {1}", new_title,path)

def update_mp3_album(path : str| PathLike[str]| MP3, new_album :str, save : bool = True):
    audio = _audio(path)

    audio.tags.add(TALB(Encoding.UTF8, text=[new_album]))
    if save:
        audio.save()
        logger.debug("Updated album to {0} for {1}", new_album,path)

def update_mp3_artist(path : str| PathLike[str]| MP3, new_artist :str, save : bool = True):
    audio = _audio(path)

    audio.tags.add(TPE1(Encoding.UTF8, text=[new_artist]))
    if save:
        audio.save()
        logger.debug("Updated artist to {0} for {1}", new_artist, path)

def update_mp3_bpm(path : str| PathLike[str]| MP3, new_bpm :int | None, save : bool = True):
    audio = _audio(path)

    if new_bpm is None:
        if "TBPM" in audio.tags:
            audio.tags.pop("TBPM")
    else:
        audio.tags.add(TBPM(Encoding.UTF8, text=[new_bpm]))
    if save:
        audio.save()
        logger.debug("Updated bpm to {0} for {1}", new_bpm, path)

def update_mp3_genre(path : str| PathLike[str]| MP3, new_genre : list[str] | str, save : bool = True):
    audio = _audio(path)

    if isinstance(new_genre, str):
        audio.tags.add(TCON(Encoding.UTF8, text=[new_genre]))
    else:
        audio.tags.add(TCON(Encoding.UTF8, text=new_genre))

    if save:
        audio.save()
        logger.debug("Updated genre to {0} for {1}", new_genre, path)


def update_mp3_categories(path: PathLike[str] | MP3, categories: dict[str, int], save: bool = True):
    audio = _audio(path)

    if categories:
        if isinstance(categories, list):
            categories = {item['category']: item['scale'] for item in categories}

        audio.tags.add(TXXX(Encoding.UTF8, desc='ai_categories', text=[json.dumps(categories, ensure_ascii=False)]))
    else:
        audio.tags.add(TXXX(Encoding.UTF8, desc='ai_categories', text=""))
    #audio.tags.add(TXXX(Encoding.UTF8, desc='ai_tags', text=calculate_tags_from_categories(categories)))

    if save:
        audio.save()
def update_mp3_category(path: str| PathLike[str] | MP3, category : str, new_value : int | None, save : bool = True):
    audio = _audio(path)

    cats = {}
    txxx_cats = audio.tags.get("TXXX:ai_categories")
    if txxx_cats:
        try:
            cats = json.loads(txxx_cats.text[0])
        except Exception:
            pass

    if new_value is None:
        if category in cats:
            del cats[category]
    else:
        cats[category] = new_value

    audio.tags.add(TXXX(Encoding.UTF8, desc='ai_categories', text=[json.dumps(cats)]))
    if save:
        audio.save()
        logger.debug("Updated {} to {1} for {2}", category, new_value,path)

def update_mp3_tags(path: str| PathLike[str] | MP3, tags : list[str], save : bool = True):
    audio = _audio(path)

    if tags:
        audio.tags.add(
            TXXX(
                Encoding.UTF8,
                desc='ai_tags',
                text=tags
            )
        )

    if save:
        audio.save()
        logger.debug("Updated tags to {0} for {1}", tags,path)

def update_mp3_color(path: str| PathLike[str] | MP3, color:QColor, save : bool = True):
    audio = _audio(path)

    if color:
        audio.tags.add(
            TXXX(
                Encoding.UTF8,
                desc='ai_color',
                text=[color.name()]
            )
        )

    if save:
        audio.save()
        logger.debug("Updated color to {0} for {1}", color,path)

def list_mp3s(path : PathLike[str]):
    return glob.glob("**/*.mp3", root_dir=path, recursive=True)

def update_categories_and_tags(path : PathLike[str] | ID3, summary : str, categories: dict[str,int] = None, tags: list[str] = None):
    """Adds categories and summary as MP3 tags to the file."""
    audio = _audio(path)

    update_mp3_summary(audio, summary, False)
    update_mp3_categories(audio, categories, False)

    update_mp3_tags(audio, tags, False)

    audio.save()
    logger.debug("Tags added to {0}", path)

def update_mp3_cover(path : PathLike[str] | MP3, image_path: PathLike[str]):
    audio = _audio(path)

    # 2. Read the image data
    with open(image_path, 'rb') as img:
        img_data = img.read()

    image_path = image_path.lower()
    if image_path.endswith(".jpg") or image_path.endswith(".jpeg"):
        mimeType = 'image/jpeg'
    elif image_path.endswith(".png"):
        mimeType = 'image/png'
    elif image_path.endswith(".bmp"):
        mimeType = 'image/bmp'
    else:
        mimeType = 'image/jpeg'

    # 3. Add the APIC frame
    # mime='image/jpeg' or 'image/png'
    # type=3 is 'Front Cover'
    audio.tags.add(
        APIC(
            encoding=Encoding.UTF8,
            mime=mimeType,
            type=PictureType.COVER_FRONT,
            desc='Cover',
            data=img_data
        )
    )

    audio.save()

def print_mp3_tags(file_path: PathLike[str]):
    """Prints all ID3 tags from an MP3 file."""
    try:
        if logger.isEnabledFor(logging.DEBUG):
            audio = MP3(file_path, ID3=ID3)
            if audio.tags:
                logger.debug("\n--- Tags for {0} ---", file_path)
                for key, value in audio.tags.items():
                    if not key.startswith("APIC"):
                        logger.debug("{0}: {1}", key,value)
                logger.debug("---------------------------------\n")
            else:
                logger.warning("No tags found in {}", file_path)
    except Exception as e:
        logger.error("An error occurred while reading tags: {0}",e)


def remove_m3u(entries: list[Mp3Entry], playlist : PathLike[str]):
    files = parse_m3u(playlist)

    filtered = [file for file in files if file not in entries]

    create_m3u(filtered, playlist)

def append_m3u(entries: list[Mp3Entry], playlist : PathLike[str], index: int = -1):
    try:
        if len(entries) > 0:

            if index<0:
                logger.debug("Appending playlist '{0}'...", playlist)

                # write the playlist
                with open(playlist, 'a', encoding="utf-8") as of:
                    for mp3 in entries:
                        relpath = os.path.relpath(mp3.path, str(Path(playlist).parent)).replace("\\", "/")
                        of.write(f"#EXTINF:{mp3.length},{mp3.name}\n")
                        of.write(relpath + "\n")
            else:
                mp3s = parse_m3u(playlist)
                for i in reversed(entries):
                    mp3s.insert(index,i)
                create_m3u(mp3s, playlist)

        else:
            logger.warning("No mp3 files found.")

    except Exception:
        logger.error("ERROR occurred when processing entries.")
        logger.error("Text: {0}", sys.exc_info()[0])

def create_m3u(entries: list[Mp3Entry], playlist : PathLike[str]):

    try:
        if len(entries) > 0:
            logger.debug("Writing playlist '{0}'...", playlist)

            # write the playlist
            with open(playlist, 'w', encoding="utf-8") as of:
                of.write("#EXTM3U\n")

                # sorted by track number
                for mp3 in entries:

                    relpath = os.path.relpath(mp3.path, str(Path(playlist).parent)).replace("\\", "/")
                    of.write(f"#EXTINF:{mp3.length},{mp3.name}\n")
                    of.write(relpath + "\n")
        else:
            logger.warning("No mp3 files found.")

    except Exception:
        logger.error("ERROR occurred when processing entries.")
        logger.error("Text: {0}", sys.exc_info()[0])

def get_m3u_paths(file_path : PathLike[str]) -> list[Path] | None:
    with open(file_path,'r', encoding="utf-8") as infile:

        # All M3U files start with #EXTM3U.
        # If the first line doesn't start with this, we're either
        # not working with an M3U or the file we got is corrupted.

        line = infile.readline()
        if not line.startswith('#EXTM3U'):
            return None

        paths = []
        base_dir = Path(Path(infile.name)).parent

        for line in infile:
            line=line.strip()
            if line.startswith('#EXTINF:'):
                continue
                # pull length and title from #EXTINF line
                # length,title=line.split('#EXTINF:')[1].split(',',1)
                # song=track(length,title,None)
            elif len(line) != 0:
                # pull song path from all other, non-blank lines
                # song.path=line

                if Path(line).is_absolute():
                    paths.append(Path(line))
                else:
                    paths.append(Path(base_dir, line))
                # reset the song variable so it doesn't use the same EXTINF more than once
    return paths

def parse_m3u(file_path : PathLike[str]) -> list[Mp3Entry] | None:
    paths = get_m3u_paths(file_path)
    if paths is None:
        return None

    playlist = [parse_mp3(f) for f in paths]
    playlist = [song for song in playlist if song is not None]
    return playlist



class Mp3FileLoader(QThread):
    files_loaded = Signal(list)
    finished = Signal()

    def __init__(self, files: list[Path], parent=None):
        super().__init__(parent)
        self.files = files
        self.is_interrupted = False

    def run(self):
        chunk = []
        for file_path in self.files:
            if self.is_interrupted:
                break
            try:
                entry = parse_mp3(file_path)
                if entry:
                    chunk.append(entry)
            except Exception:
                pass

            if len(chunk) >= 20:  # Chunk size
                self.files_loaded.emit(chunk)
                chunk = []

        if chunk:
            self.files_loaded.emit(chunk)

        self.finished.emit()

    def stop(self):
        self.is_interrupted = True
        self.wait()

def save_playlist(playlist_path, entries: list[Mp3Entry]) -> bool:
    if entries and len(entries) > 0:
        create_m3u(entries, playlist_path)
        return True
    else:
        return False
