import os

import sys
import glob
import json
import logging
from io import TextIOWrapper

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TXXX, COMM, TIT2
from pathlib import Path
from os import PathLike

logger = logging.getLogger("main")

class Mp3Entry:

    name: str = None
    path: Path = None
    title: str = None
    artist: str = None
    album: str = None
    summary: str = None
    length: int = 0
    favorite: bool = False

    categories : dict[str,int]
    tags: list[str]
    all_tags: None | set[str] = None

    def __init__(self, name: str = None, path :str | Path = None, categories : dict[str,int] = None, tags: list[str] = None, artist: str = None, album:str = None, title:str = None):
        self.name = name
        self.title = title
        self.path = path if isinstance(path,Path) else Path(path)
        self.artist = artist
        self.album = album
        if categories:
            self.categories = categories
        else:
            self.categories = {}

        if tags:
            self.tags = tags
        else:
            self.tags = []

    def setTags(self, tags: list[str]):
        self.tags = tags
        self.all_tags = None

    def _le(self, category, value) -> bool:
        return category in self.categories and self.categories.get(category, None) <= value

    def _ge(self, category, value) -> bool:
        return category in self.categories and self.categories.get(category, None) >= value

    def allTags(self):
        if self.all_tags is None:
            self.all_tags = set(self.tags)
            if self._ge("Tempo",7) and self._ge("Spannung",7) and self._ge("Heroik",6):
                self.all_tags.add("Kampf")

            if self._le("Tempo",5) and self._le("Spannung",3) and self._le("Heroik",3) and self._le("Mystik",4):
                self.all_tags.add("Reise")

            self.all_tags = sorted(self.all_tags)

        return self.all_tags


def parse_mp3(f : Path) -> Mp3Entry | None:

    try:
        entry = Mp3Entry(name=f.name, path=str(f))
        audio = MP3(f, ID3=ID3)

        entry.length = int(audio.info.length)

        if audio.tags:

            if "TIT2" in audio.tags:
                entry.title = audio.tags.get("TIT2").text[0]

            if "TPE1" in audio.tags:
                entry.artist = audio.tags.get("TPE1").text[0]

            if "TALB" in audio.tags:
                entry.album = audio.tags.get("TALB").text[0]

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

        return entry
    except Exception as e:
        logger.error(f"Error reading tags for {f}: {e}")
    return None


def update_mp3_favorite(path : str | Path, favorite: bool):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    audio.tags.add(TXXX(encoding=3, desc='ai_favorite', text=[favorite]))
    audio.save()

def update_mp3_summary(path : str| Path, new_summary :str):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(COMM(encoding=3, text=[new_summary]))
    audio.save()
    logger.debug(f"Updated summary to {new_summary} for {path}")

def update_mp3_title(path : str| Path, new_title :str):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=[new_title]))
    audio.save()
    logger.debug(f"Updated title to {new_title} for {path}")

def update_mp3_categories(path: str | Path, categories: dict[str, int]):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    audio.tags.add(TXXX(encoding=3, desc='ai_categories', text=[json.dumps(categories)]))

    #audio.tags.add(TXXX(encoding=3, desc='ai_tags', text=calculate_tags_from_categories(categories)))

    audio.tags.add(COMM(encoding=3, text=["processed by Voxalyzer 1.0"]))

    audio.save()
def update_mp3_category(path: str| Path, category : str, new_value : int | None):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    cats = {}
    txxx_cats = audio.tags.get("TXXX:ai_categories")
    if txxx_cats:
        try:
            cats = json.loads(txxx_cats.text[0])
        except:
            pass

    if new_value is None:
        if category in cats:
            del cats[category]
    else:
        cats[category] = new_value

    audio.tags.add(TXXX(encoding=3, desc='ai_categories', text=[json.dumps(cats)]))
    audio.save()
    logger.debug(f"Updated {category} to {new_value} for {path}")

def update_mp3_tags(path: str| Path, tags : list[str]):
    audio = MP3(path, ID3=ID3)
    if audio.tags is None:
        audio.add_tags()

    if tags:
        audio.tags.add(
            TXXX(
                encoding=3,
                desc='ai_tags',
                text=tags
            )
        )
    audio.save()
    logger.debug(f"Updated tags to {tags} for {path}")

def list_mp3s(path : str | PathLike[str]):
    return glob.glob("**/*.mp3", root_dir=path, recursive=True)

def add_tags_to_mp3(file_path : str | PathLike[str], summary : str, categories: dict[str,int] = None, tags: list[str] = None):
    """Adds categories and summary as MP3 tags to the file."""
    audio = MP3(file_path, ID3=ID3)

    # Add a comment tag for the summary
    audio.tags.add(
        COMM(
            encoding=3,
            text=[summary]
        )
    )

    # Create a map of category names to scales and store it in a single tag
    if  categories:
        categories_map = {item['category']: item['scale'] for item in categories}
        all_categories_str = json.dumps(categories_map, ensure_ascii=False)
        audio.tags.add(
            TXXX(
                encoding=3,
                desc='ai_categories',
                text=[all_categories_str]
            )
        )
    else:
        audio.tags.add(
            TXXX(
                encoding=3,
                desc='ai_categories',
                text=""
            )
        )


    if tags:
        audio.tags.add(
            TXXX(
                encoding=3,
                desc='ai_tags',
                text=tags
            )
        )

    audio.save()
    logger.debug(f"Tags added to {file_path}")

def print_mp3_tags(file_path: str | PathLike[str]):
    """Prints all ID3 tags from an MP3 file."""
    try:
        audio = MP3(file_path, ID3=ID3)
        if audio.tags:
            logger.debug(f"\n--- Tags for {file_path} ---")
            for key, value in audio.tags.items():
                if not key.startswith("APIC"):
                    logger.debug(f"{key}: {value}")
            logger.debug("---------------------------------\n")
        else:
            logger.warning(f"No tags found in {file_path}")
    except Exception as e:
        logger.error(f"An error occurred while reading tags: {e}")


def create_m3u(entries: list[Mp3Entry], playlist : str | PathLike[str]):

    try:
        logger.debug("Processing directory '%s'..." % dir)

        if len(entries) > 0:
            logger.debug("Writing playlist '%s'..." % playlist)

            # write the playlist
            of = open(playlist, 'w')
            of.write("#EXTM3U\n")

            # sorted by track number
            for mp3 in entries:

                relpath = os.path.relpath(mp3.path, str(Path(playlist).parent)).replace("\\", "/")
                of.write("#EXTINF:%s,%s\n" % (mp3.length, mp3.name))
                of.write(relpath + "\n")

            of.close()
        else:
            logger.warning("No mp3 files found in '%s'." % dir)

    except:
        logger.error("ERROR occured when processing directory '%s'. Ignoring." % dir)
        logger.error("Text: ", sys.exc_info()[0])

class track():
    def __init__(self, length, title, path):
        self.length = length
        self.title = title
        self.path = path

def parse_m3u(infile : TextIOWrapper | str | PathLike[str]) -> list[Path] | None:
    try:
        assert(type(infile) == '_io.TextIOWrapper')
    except AssertionError:
        infile = open(infile,'r')

    """
        All M3U files start with #EXTM3U.
        If the first line doesn't start with this, we're either
        not working with an M3U or the file we got is corrupted.
    """

    line = infile.readline()
    if not line.startswith('#EXTM3U'):
       return

    # initialize playlist variables before reading file
    playlist=[]
    #song=track(None,None,None)

    baseDir = Path(Path(infile.name)).parent

    for line in infile:
        line=line.strip()
        if line.startswith('#EXTINF:'):
            continue
            #pull length and title from #EXTINF line
            #length,title=line.split('#EXTINF:')[1].split(',',1)
            #song=track(length,title,None)
        elif (len(line) != 0):
            # pull song path from all other, non-blank lines
            #song.path=line
            if Path(line).is_absolute():
                playlist.append(Path(line))
            else:
                playlist.append(Path(baseDir, line))
            # reset the song variable so it doesn't use the same EXTINF more than once


    infile.close()

    return playlist
