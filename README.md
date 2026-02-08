# DungeonTuber

[![en](https://img.shields.io/badge/lang-en-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.md)
[![de](https://img.shields.io/badge/lang-de-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.de.md)
[![Build](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml)
[![Release](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/gandulf/DungeonTuber)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**DungeonTuber** is a specialized music player designed for Role-Playing Game Masters, streamers, and storytellers who need the perfect atmosphere at their fingertips. Unlike standard players, DungeonTuber allows you to categorize and filter your music based on emotional weight, intensity, and genre-specific metadata.
 
![Screenshot of application](docs/screen1.png)

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
The app uses **Voxalyzer** to scan your tracks, to use it you have to run a local instance of it  and insert is base url under **Settings**.
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

## 🛠️ Build Instructions


## Update translations:
Edit translations in _locales/**/LC_MESSAGES/DungeonTuber.po_ files and then run the following commands to update mo files. 
```bash
msgfmt -o locales/en/LC_MESSAGES/DungeonTuber.mo locales/en/LC_MESSAGES/DungeonTuber.po
msgfmt -o locales/de/LC_MESSAGES/DungeonTuber.mo locales/de/LC_MESSAGES/DungeonTuber.po
```

### Using PyInstaller (Recommended)
```bash
pyinstaller DungeonTuber.spec
```

### Using Nuitka 
The following command uses MinGW64. If you experience slow compilation, ensure your build directory is excluded from Antivirus scanning.

```bash
python -m nuitka --jobs=16 DungeonTuber.py --product-version=0.1.7.0 --file-version=0.1.7.0
```
> [!Note]
> Add `--product-version=X.Y.Z.Q` and `--file-version=X.Y.Z.Q` to define version of created exe

> [!Note]
> The `--jobs` flag sets the number of parallel compilation jobs. Adjust based on your CPU cores.*
