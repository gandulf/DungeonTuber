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

## 🌐 Desktop-App & Server

DungeonTuber besteht aus einem Python-Server und einer Weboberfläche. Es läuft als Desktop-App oder als Server für
andere Geräte (Tablet, Handy, zweiter PC) – die Musik wird im Browser abgespielt.

```bash
pip install -e .[dev]
npm --prefix web ci
npm --prefix web run build
```

* **Desktop-App** (eigenes Fenster, nur dieser Computer kann sich verbinden): `python DungeonTuber.py` (`--fake` simuliert WiZ-Lampen)
* **Server** im Netzwerk: einmalig ein Passwort setzen mit `python -m server --set-password`, dann
  `python -m server --host 0.0.0.0 --port 8765` starten und `http://<dein-pc>:8765` im Browser öffnen.
  Nur Ordner unter *Einstellungen → Bibliothek* sind erreichbar. Für den Zugriff über das Internet den Server hinter einen
  HTTPS-Reverse-Proxy (z. B. Caddy) stellen. WiZ-Lampen lassen sich nur steuern, wenn der Server im selben Netzwerk läuft.

Die Einstellungen liegen in `%APPDATA%/DungeonTuber/settings.json` (Einstellungen älterer Versionen werden beim ersten Start übernommen).

## 🛠️ Build-Anweisungen

### Tests
```bash
python -m pytest
npm --prefix web test
```

### Kompletter Build (Übersetzungen, Lint, Tests, Weboberfläche, PyInstaller)
```bash
python build.py
```

### Übersetzungen aktualisieren:
Bearbeite die Übersetzungen in den Dateien `_locales/**/LC_MESSAGES/DungeonTuber.po` und führe dann die folgenden Befehle aus, um die `.mo`-Dateien zu aktualisieren. 
```bash
msgfmt -o locales/en/LC_MESSAGES/DungeonTuber.mo locales/en/LC_MESSAGES/DungeonTuber.po
msgfmt -o locales/de/LC_MESSAGES/DungeonTuber.mo locales/de/LC_MESSAGES/DungeonTuber.po
```


## Verwendung von PyInstaller (Empfohlen)

Vorher die Weboberfläche bauen (`npm --prefix web run build`).
```bash
pyinstaller DungeonTuber.spec
```

## Verwendung von Nuitka

Der folgende Befehl nutzt MinGW64. Wenn die Kompilierung langsam ist, stelle sicher, dass dein Build-Verzeichnis vom Antiviren-Scan ausgeschlossen ist.

```bash
python -m nuitka --jobs=16 --include-data-dir=web/dist=web/dist --include-data-dir=locales=locales DungeonTuber.py --product-version=0.0.1.0 --file-version=0.0.1.0
```

> [!Note]
> Füge --product-version=X.Y.Z.Q und --file-version=X.Y.Z.Q hinzu, um die Version der erstellten .exe zu definieren.

> [!Note]
> Das Flag --jobs legt die Anzahl der parallelen Kompilierungsprozesse fest. Passe dies basierend auf deinen CPU-Kernen an.