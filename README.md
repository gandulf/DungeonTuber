# DungeonTuber

[![en](https://img.shields.io/badge/lang-en-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.md)
[![de](https://img.shields.io/badge/lang-de-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.de.md)
![es](https://img.shields.io/badge/lang-es-green.svg)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/gandulf/DungeonTuber)

**DungeonTuber** is a specialized music player designed for Role-Playing Game Masters, streamers, and storytellers who need the perfect atmosphere at their fingertips. Unlike standard players, DungeonTuber allows you to categorize and filter your music based on emotional weight, intensity, and genre-specific metadata.

![Screenshot of application](docs/screen1.png)

---

## 🚀 Key Features

* **Atmospheric Sliders:** Fine-tune your search using sliders for **Tempo**, **Dunkelheit** (Darkness), **Emotional**, **Mystik**, **Spannung** (Tension), and **Heroik**.
* **Gemini Integration:** Tracks are analyzed to provide objective scoring (1–10) for your music library across multiple thematic dimensions.
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
The app uses **Gemini** to scan your tracks, to use it you have to create a Gemini API Key or AI Studio Key and insert it under **Settings**.
> [!Note]
> For information how to obtain an API Key please consult the **Internet** e.g. [How to Generate Gemini API Key for Free in 2025](https://wedevs.com/blog/510096/how-to-generate-gemini-api-key/)


### 2. Filtering by Mood
The power of DungeonTuber lies in the top control panel:
* **Adjust Sliders:** Move the sliders (e.g., increase *Mystik* and *Dunkelheit* for a spooky dungeon) to filter your list for songs that match that specific "score."
* **Toggle Tags:** Click the pill-shaped buttons (like **Kampf** or **Reise**) to quickly filter for specific scene types.

### 3. Playback & Volume
* **Navigation:** Use the standard Play, Pause, and Skip buttons in the center console.
* **Progress Bar:** The waveform/timeline allows you to jump to specific moments in a track.
* **Volume Control:** Use the green wedge slider on the right to adjust audio levels smoothly.
* **Shuffle:** Click the shuffle icon to randomize the current filtered selection.

### 4. Search & Favorites
* **Search Bar:** Use the "Filter songs..." bar above the main list to find a specific track by name.
* **Starring:** Click the **Gold Star** next to any track to mark it as a favorite for quick access during your sessions.

---

## 🛠 Category Reference 

> [!IMPORTANT]
> **WIP** Final default categories may change and also can be updated by yourself under settings to fit your personal needs

| Category      | Description                                 |
|:--------------|:--------------------------------------------|
| **Tempo**     | The speed and energy of the track.          |
| **Darkness**  | Dark, grim, or somber tones.                |
| **Emotional** | Emotional soft tones.                       |
| **Mysticism** | Ethereal, magical, or mysterious qualities. |
| **Tension**   | Tension and suspense.                       |
| **Heroism**   | Epic, triumphant, and orchestral energy.    |

*Happy Adventuring!*

---

## 🧠 AI Analysis Details

DungeonTuber leverages Google's **Gemini 2.5 Flash** model to analyze and categorize audio files. 
The process involves uploading the audio file to the Gemini API and providing a specific prompt to generate metadata.

### System Instruction
The system prompt defines the persona and scoring philosophy:
> You are an experienced listener of fantasy, film, and role-playing music. You evaluate music as perceived by an average listener, not technically or analytically, but emotionally and scenically.
>
> * Your ratings must remain consistent across many hundreds of tracks.
> * A 3 always means the same thing, regardless of which track was rated before.
> * Values should be meaningfully distributed relative to each other (not everything 1 or 10).
> * Use the full scale from 1 to 10 when appropriate.
> * Strictly adhere to the specified categories, tags, and their descriptions.
> * Return only JSON, without additional explanations.

### User Prompt
The user prompt provides the context (specifically tailored for RPGs like "The Dark Eye" or "D&D) and the definitions for categories and tags:
> Task: Categorize the following piece of music for use in a role-playing game
> Rate the piece based on the categories below with a value from 1 to 10 each.
>
> Here is the list of categories to rate the music piece by, along with their descriptions:<br/>
> *[Dynamic list of categories, descriptions, and intensity levels]*
>
> Then, assign a few tags from the following list that fit best. No scale is necessary here:<br/>
> *[Dynamic list of tags and descriptions]*

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
python -m nuitka --jobs=16 DungeonTuber.py --product-version=0.0.1.0 --file-version=0.0.1.0
```
> [!Note]
> Add `--product-version=X.Y.Z.Q` and `--file-version=X.Y.Z.Q` to define version of created exe

> [!Note]
> The `--jobs` flag sets the number of parallel compilation jobs. Adjust based on your CPU cores.*
