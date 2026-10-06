# DungeonTuber

[![en](https://img.shields.io/badge/lang-en-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.md)
[![de](https://img.shields.io/badge/lang-de-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.de.md)
[![Build](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/build-app.yml)
[![Release](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml/badge.svg)](https://github.com/gandulf/DungeonTuber/actions/workflows/release-app.yml)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/gandulf/DungeonTuber)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**DungeonTuber** ist ein spezialisierter Musikplayer für Rollenspiel-Spielleiter (GMs), Streamer und Geschichtenerzähler, die die perfekte Atmosphäre sofort griffbereit brauchen. Im Gegensatz zu Standard-Playern ermöglicht DungeonTuber die Kategorisierung und Filterung deiner Musik basierend auf emotionalem Gewicht, Intensität und genre-spezifischen Metadaten.
 
![Screenshot der Anwendung](docs/screen1.png)

---

## 🚀 Hauptmerkmale

* **Atmosphärische Slider:** Verfeinere deine Suche mit Schiebereglern für **anpassbare Kategorien/Merkmale**.
* **Schnell-Tag-Filter:** Sofortige Umschalter für gängige RPG-Szenarien wie *Emotionale*, *Kampf*, *Magisches Ritual* und *Reise*.
* **Intuitive Bibliotheksansicht:** Überblicke deine gesamte Sammlung mit den zugehörigen Scores und Tags in einer einzigen, scannbaren Liste.

---

## 📥 Installationshinweis

> [!Tip]
> Wahrscheinlich erhältst du beim Ausführen des Installers die blaue "Windows SmartScreen-Benachrichtigung". Dies liegt daran, dass ich _(noch)_ keine gültige Signatur besitze, um den Installer zu signieren. 
> Klicke einfach auf *"Weitere Informationen"* und dann auf *"Trotzdem ausführen"*.

## 📖 Tutorial: So benutzt du DungeonTuber

### 1. Bibliothek aufbauen
Nutze das **Datei**-Menü, um deine Audiodateien zu importieren, oder navigiere durch den Verzeichnisbaum, um Ordner in der Tabelle unten zu öffnen oder Songs direkt abzuspielen.
Die App nutzt **Voxalyzer**, um deine Tracks zu scannen. Um dies zu verwenden, musst du eine lokale Instanz davon ausführen und die Basis-URL unter **Einstellungen** hinterlegen.
> [!Tip]
> Wenn du eine große MP3-Bibliothek lokal analysieren möchtest, schau dir das Nebenprojekt [Voxalyzer](https://github.com/gandulf/Voxalyzer) an.

### 2. Nach Stimmung filtern
Die Stärke von DungeonTuber liegt im oberen Bedienfeld:
* **Regler anpassen:** Bewege die Regler (z. B. erhöhe *Mystik* und *Dunkelheit* für einen gruseligen Dungeon), um deine Liste nach Songs zu filtern, die genau diesem "Score" entsprechen.
* **Tags umschalten:** Klicke auf die pillenförmigen Buttons (wie **Kampf** oder **Reise**), um schnell nach bestimmten Szenentypen zu filtern.

### 3. Wiedergabe & Lautstärke
* **Navigation:** Nutze die Standardtasten für Play, Pause und Überspringen in der Mittelkonsole.
* **Fortschrittsbalken:** Die Wellenform/Timeline ermöglicht es dir, zu bestimmten Momenten in einem Track zu springen.
* **Lautstärkeregelung:** Nutze den grünen Keil-Schieberegler auf der rechten Seite, um den Audiopegel stufenlos anzupassen.
* **Shuffle:** Klicke auf das Shuffle-Symbol, um die aktuell gefilterte Auswahl zufällig wiederzugeben.

### 4. Suche & Favoriten
* **Suche:** Tippe einfach los, um in der Hauptliste oder im Verzeichnisbaum nach einem bestimmten Titelnamen zu filtern.
* **Favoriten:** Klicke auf den **Goldenen Stern** neben einem Track, um ihn als Favoriten zu markieren und während deiner Sessions schnell darauf zugreifen zu können.

---

## 🛠 Kategorie-Referenz 

> [!IMPORTANT]
> **WIP** (In Arbeit). Die endgültigen Standardkategorien können sich noch ändern und können von dir selbst in den Einstellungen angepasst werden, um deinen persönlichen Bedürfnissen zu entsprechen.

| Merkmal | Modell-Nutzung & Akustische Beschreibung |
| :--- | :--- |
| **Valence** | Die **emotionale Positivität** eines Tracks. Hohe Valence klingt glücklich/fröhlich; niedrige Valence klingt traurig oder wütend. |
| **Arousal** | Das **Intensitäts- und Energieniveau**. Hohes Arousal ist hektisch und laut; niedriges Arousal ist ruhig, leise oder schläfrig. |
| **Engagement** | Der Grad, in dem die Musik Aufmerksamkeit erregt, meist getrieben durch **rhythmische Stabilität** und "Tanzbarkeit". |
| **Darkness** | Zeigt **Tieffrequenzdichte** und Moll-Tonalität an; assoziiert mit düsteren oder grimmigen Atmosphären. |
| **Aggressive** | Intensiver Sound mit **Verzerrung**, schnellen Transienten und hartem perkussivem "Attack". |
| **Happy** | Prognostiziert helle **Dur-Tonalität** und fröhliche rhythmische Muster. |
| **Party** | Zum Tanzen geeignet; charakterisiert durch **starken Bass**, stetige Beats und hohe rhythmische Energie. |
| **Relaxed** | Gekennzeichnet durch eine **geringe Dynamik**, langsamere Tempi und sanfte, weiche klangliche Qualitäten. |
| **Sad** | Niedrige Valence und niedrige Energie; assoziiert mit **melancholischen** Melodien und langsamerem, ernstem Tempo. |

*Viel Spaß beim Abenteuer!*

---

## 🧠 Details zur KI-Analyse

> [!Update]
> KI-API-Aufrufe an öffentliche Modelle wurden zugunsten des lokalen Analyzers (Voxalyzer) entfernt. 

Der Prozess umfasst das Hochladen der Audiodatei an den Voxalyzer, wo lokale Essentia-Modelle verwendet werden, um die bereitgestellten Dateien zu analysieren.

---

## 🌐 Installation & Betrieb

DungeonTuber besteht aus einem Python-Server und einer Weboberfläche; die Musik wird im Browser abgespielt. Wähle die passende Variante:

| Du möchtest… | Verwende |
|---|---|
| Auf deinem Windows-PC spielen (optional mit Tablets) | **Desktop-App** – den Windows-Installer aus den [Releases](https://github.com/gandulf/DungeonTuber/releases) |
| Einen dauerhaft laufenden Server (NAS, Raspberry Pi, VPS) | **Docker-Image** `ghcr.io/gandulf/dungeontuber` |
| Es auf einem beliebigen Rechner mit Python 3.12 betreiben | **Python-Paket** – das Wheel aus den Releases |

### Desktop-App
Installieren und *Dungeon Tuber* starten. Nur dieser Computer kann sich verbinden. Damit Tablets oder Handys am
Spieltisch mitmachen können, ein Passwort setzen und **Einstellungen → Sicherheit → Im Netzwerk freigeben** aktivieren,
die App neu starten und die angezeigte Adresse auf dem anderen Gerät öffnen.

### Docker
```bash
docker run -d -p 8765:8765 -e DT_PASSWORD=aendern \
  -v /pfad/zur/musik:/music -v dungeontuber-data:/data ghcr.io/gandulf/dungeontuber
```
[`deploy/docker-compose.yml`](deploy/docker-compose.yml) ergänzt automatisches HTTPS mit Caddy für den Zugriff über das Internet.
WiZ-Lampen werden per UDP-Broadcast gefunden – das funktioniert nur mit `network_mode: host` unter Linux; unter Windows für Licht die Desktop-App nutzen. Für einen Server außerhalb des Lampen-Netzwerks läuft der [WiZ-Licht-Agent](agents/wiz/README.md) neben den Lampen: er verbindet sich mit einem eigenen Token (Einstellungen > Lichter oder `DT_AGENT_TOKEN`) nach außen zum Server.

### Python-Paket
```bash
pipx install dungeontuber-<version>-py3-none-any.whl
DT_PASSWORD=aendern DT_LIBRARY=/srv/music dungeontuber-server --host 0.0.0.0
```
Eine systemd-Unit liegt unter [`deploy/dungeontuber.service`](deploy/dungeontuber.service).

### Server-Konfiguration
Als Argumente (`dungeontuber-server --help`) oder Umgebungsvariablen: `DT_HOST`, `DT_PORT`, `DT_DATA_DIR`
(Einstellungen, Bibliotheks-Cache, Logs), `DT_LIBRARY` (Musikordner), `DT_PASSWORD` (SuperAdmin-Passwort, Benutzername `admin`; ohne Passwort kann
sich nur der Server-Rechner selbst verbinden), `DT_FORWARDED_ALLOW_IPS` (vertrauenswürdige Reverse-Proxys).
Der SuperAdmin kann unter **Einstellungen → Sicherheit** weitere Benutzer anlegen, die sich mit eigenem Namen und Passwort anmelden. Benutzer können keine Servereinstellungen ändern, und jeder hochgeladene Song merkt sich, wer ihn hochgeladen hat (sichtbar in den Song-Details).
Nur Dateien in den Bibliotheksordnern sind erreichbar. Es läuft genau ein Server-Prozess.

---

## 🛠️ Entwicklung & Build

```bash
pip install -e .[desktop,dev]
npm --prefix web ci
npm --prefix web run build        # schreibt server/static
python DungeonTuber.py --fake     # Desktop-Fenster mit simulierten Lampen
```

### Tests
```bash
python -m pytest
npm --prefix web test
```

### Pakete
* Python-Wheel (inklusive Weboberfläche): `python -m build --wheel`
* Docker-Image: `docker build -t dungeontuber .`
* Windows-Desktop-App (Lint, Tests, Weboberfläche, PyInstaller): `python build_app.py`, danach `DungeonTuber.iss` mit Inno Setup

Releases (`v*`-Tags) baut [`release-app.yml`](.github/workflows/release-app.yml): Windows-Installer, Wheel und Docker-Image (amd64/arm64).

### Übersetzungen
Die Übersetzungen liegen in `core/locales/<sprache>.json` (Schlüssel = englischer Text) und werden von Server und
Weboberfläche gemeinsam genutzt. Neue Texte in jede Sprachdatei eintragen.
