# DungeonTuber

[![en](https://img.shields.io/badge/lang-en-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.md)
[![de](https://img.shields.io/badge/lang-de-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.de.md)
[![Build](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml)
[![Release](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/gandulf/DungeonTuber)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**DungeonTuber** is a specialized music player designed for Role-Playing Game Masters, streamers, and storytellers who need the perfect atmosphere at their fingertips. Unlike standard players, DungeonTuber allows you to categorize and filter your music based on emotional weight, intensity, and genre-specific metadata.

![Screenshot of application](docs/screen2.png)

---

## 🚀 Key Features

* **Atmospheric Sliders:** Fine-tune your search using sliders for  **customizable categories/features**.
* **Quick-Tag Filtering:** Instant toggles for common RPG scenarios like *Emotionale*, *Kampf* (Combat), *Magisches Ritual*, and *Reise* (Travel).
* **Intuitive Library View:** See your entire collection with its associated scores and tags in a single, scannable list.

---

## 📥 Installation note

> [!Tip]
>You will probably get the blue "Windows Smart Screen Notification" once you run the installer, this is because I do not _(yet)_ have a valid >signature to sign the installer. 
>Just click on *"More Info"* and then *"Run anyway"*

## 📖 Tutorial: How to Use DungeonTuber

### 1. Building Your Library
Use the **File** menu to import your audio files or navigate through the directory tree and open directories in the table below or play songs directly.
The app uses **Voxalyzer** to scan your tracks. Run the Voxalyzer agent (`agents/voxalyzer`) on a machine with the models and connect it to your server with the agent token (`voxalyzer --token <token>`). Without a connected agent analysis is disabled.
> [!Tip]
>If you want to analyze a huge library of mp3s locally have a look at a side project [Voxalyzer](https://github.com/gandulf/Voxalyzer).

### 2. Filtering by Mood
The power of DungeonTuber lies in the top control panel:
* **Adjust Sliders:** Move the sliders (e.g., increase *Mystik* and *Dunkelheit* for a spooky dungeon) to filter your list for songs that match that specific "score."
* **Toggle Tags:** Click the pill-shaped buttons (like **Fight** or **Travel**) to quickly filter for specific scene types.

### 3. Playback & Volume
* **Navigation:** Use the standard Play, Pause, and Skip buttons in the center console.
* **Progress Bar:** The waveform/timeline allows you to jump to specific moments in a track.
* **Volume Control:** Use the green wedge slider on the right to adjust audio levels smoothly.
* **Shuffle:** Click the shuffle icon to randomize the current filtered selection.

### 4. Search & Favorites
* **Search:** Just start typing to filter in the main list or directory tree to find a specific track by name.
* **Starring:** Click the **Gold Star** next to any track to mark it as a favorite for quick access during your sessions.

---

## 🛠 Category Reference 

> [!IMPORTANT]
> **WIP** Final default categories may change and also can be updated by yourself under settings to fit your personal needs

| Feature | Model Usage & Acoustic Description |
| :--- | :--- |
| **Valence** | The **emotional positivity** of a track. High valence sounds happy/cheerful; low valence sounds sad or angry. |
| **Arousal** | The **intensity and energy** level. High arousal is frantic and loud; low arousal is calm, quiet, or sleepy. |
| **Engagement** | The degree to which the music captures attention, typically driven by **rhythmic stability** and "danceability." |
| **Darkness** | Indicates **low-frequency density** and minor-key tonality; associated with somber or grim atmospheres. |
| **Aggressive** | High-intensity sound featuring **distortion**, fast transients, and heavy percussive "attack." |
| **Happy** | Predicts bright, **major-key tonality** and upbeat rhythmic patterns. |
| **Party** | Designed for dancing; characterized by **heavy bass**, steady beats, and high rhythmic energy. |
| **Relaxed** | Characterized by a **low dynamic range**, slower tempos, and soft, mellow timbral qualities. |
| **Sad** | Low valence and low energy; associated with **melancholic** melodies and slower, somber pacing. |

*Happy Adventuring!*

---

## 🧠 AI Analysis Details

> [!Update]
>  AI API Calls to public models were removed in favor of local analyzer (Voxalyzer) 

The process involves uploading the audio file to the Voxalyzer and there use local essentia models to analyze the provided files.

---

## 🌐 Installation & Deployment

DungeonTuber is a Python server with a web frontend; the music is played in the browser. Pick the variant that fits:

| You want… | Use |
|---|---|
| Play on your Windows PC (optionally tablets join) | **Desktop app** – the Windows installer from the [releases](https://github.com/gandulf/DungeonTuber/releases) |
| An always-on server (NAS, Raspberry Pi, VPS) | **Docker image** `ghcr.io/gandulf/dungeontuber` |
| Run it on any machine with Python 3.12 | **Python package** – the wheel from the releases |

### Desktop app
Install and start *Dungeon Tuber*. Only this computer can connect. To let tablets or phones at the table join, set a
password and enable **Settings → Security → Share on network**, restart the app and open the shown address on the
other device.

### Docker
```bash
docker run -d -p 8765:8765 -e DT_PASSWORD=change-me \
  -v /path/to/music:/music -v dungeontuber-data:/data ghcr.io/gandulf/dungeontuber
```
[`deploy/docker-compose.yml`](deploy/docker-compose.yml) adds automatic HTTPS with Caddy for access over the internet.
WiZ bulbs are discovered via UDP broadcast, which only works with `network_mode: host` on Linux – on Windows use the desktop app for lights. For a server that is not in the bulbs' network, run the [WiZ light agent](agents/wiz/README.md) next to the bulbs: it connects out to the server with its own token (Settings > Lights, or `DT_AGENT_TOKEN`).

### Python package
```bash
pipx install dungeontuber-<version>-py3-none-any.whl
DT_PASSWORD=change-me DT_LIBRARY=/srv/music dungeontuber-server --host 0.0.0.0
```
See [`deploy/dungeontuber.service`](deploy/dungeontuber.service) for a systemd unit.

### Server configuration
Options can be passed as arguments (`dungeontuber-server --help`) or environment variables:

| Variable | Meaning | Default |
|---|---|---|
| `DT_HOST` / `DT_PORT` | interface and port | `127.0.0.1` / `8765` |
| `DT_DATA_DIR` | `settings.json`, `library.db`, logs | `%APPDATA%/DungeonTuber` or `~/.config/DungeonTuber` |
| `DT_LIBRARY` | music folders (separated by `:` on Linux, `;` on Windows) | `~/Music` |
| `DT_PASSWORD` | SuperAdmin password, user name `admin` (without one only the server machine itself can connect) | – |
| `DT_FORWARDED_ALLOW_IPS` | reverse proxies whose `X-Forwarded-*` headers are trusted | `127.0.0.1` |

The SuperAdmin can add more users in **Settings → Security**; they sign in with their own name and password. Users cannot change server settings, and every uploaded song remembers who uploaded it (shown in the song details).

Only files inside the library folders are accessible. Run a single server process – it keeps the analysis queue,
lights and live updates in memory.

---

## 🛠️ Development & Build

```bash
pip install -e .[desktop,dev]
npm --prefix web ci
npm --prefix web run build        # writes server/static
python DungeonTuber.py --fake     # desktop window with simulated bulbs
```
Frontend development with hot reload: `python -m server --fake-lights` and `npm --prefix web run dev` (port 5173).

### Tests
```bash
python -m pytest
npm --prefix web test
```

### Packages
* Python wheel (includes the web frontend): `python -m build --wheel`
* Docker image: `docker build -t dungeontuber .`
* Windows desktop app (lint, tests, web frontend, PyInstaller): `python build_app.py`, then `DungeonTuber.iss` with Inno Setup

Releases (`v*` tags) are built by [`release-app.yml`](.github/workflows/release-app.yml): Windows installer, wheel and multi-arch Docker image.

### Translations
Translations live in `core/locales/<lang>.json` (message id = English text) and are used by both the server and the
web frontend. Add new strings to every locale file.
