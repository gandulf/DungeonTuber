# DungeonTuber

[![en](https://img.shields.io/badge/lang-en-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.md)
[![de](https://img.shields.io/badge/lang-de-green.svg)](https://github.com/gandulf/DungeonTuber/blob/master/README.de.md)
![GitHub release (latest by date)](https://img.shields.io/github/v/release/gandulf/DungeonTuber)

**DungeonTuber** ist ein spezialisierter Musikplayer für Game Master (Spielleiter), Streamer und Storyteller, die per Knopfdruck die perfekte Atmosphäre schaffen wollen. Im Gegensatz zu Standard-Playern ermöglicht DungeonTuber das Kategorisieren und Filtern deiner Musik basierend auf emotionalem Gewicht, Intensität und genre-spezifischen Metadaten.

![Screenshot der Anwendung](docs/screen1.png)

---

## 🚀 Hauptmerkmale

* **Atmosphären-Regler:** Verfeinere deine Suche mit Schiebereglern für **Tempo**, **Dunkelheit**, **Emotional**, **Mystik**, **Spannung** und **Heroik**.
* **Gemini-Integration:** Tracks werden analysiert, um objektive Bewertungen (1–10) für deine Musikbibliothek über mehrere thematische Dimensionen hinweg zu liefern.
* **Quick-Tag Filterung:** Sofort-Schalter für gängige RPG-Szenarien wie *Emotionale Momente*, *Kampf*, *Magisches Ritual* und *Reise*.
* **Intuitive Bibliotheksansicht:** Überblicke deine gesamte Sammlung mit den zugehörigen Bewertungen und Tags in einer einfach scanbaren Liste.

---

## 📥 Installationshinweis
> [!Tip]
> Wahrscheinlich erscheint beim Ausführen des Installers die blaue Meldung „Der Computer wurde durch Windows geschützt“ (SmartScreen). Dies liegt daran, dass ich (noch) über keine gültige Signatur verfüge, um den Installer zu zertifizieren. Klicke einfach auf „Weitere Informationen“ und anschließend auf „Trotzdem ausführen“.

## 📖 Tutorial: So nutzt du DungeonTuber

### 1. Bibliothek aufbauen
Nutze das **Datei**-Menü, um deine Audiodateien zu importieren, oder navigiere durch den Verzeichnisbaum, um Ordner in der Tabelle zu öffnen oder Songs direkt abzuspielen.
Die App nutzt **Gemini**, um deine Tracks zu scannen. Um dies zu nutzen, musst du einen Gemini API-Key oder AI Studio Key erstellen und unter **Settings** (Einstellungen) einfügen.
> [!Note]
> Informationen zum Erhalt eines API-Keys findest du im **Internet**, z.B. [How to Generate Gemini API Key for Free in 2025](https://wedevs.com/blog/510096/how-to-generate-gemini-api-key/)

### 2. Nach Stimmung filtern
Die Stärke von DungeonTuber liegt im oberen Bedienfeld:
* **Regler anpassen:** Bewege die Schieberegler (z. B. erhöhe *Mystik* und *Dunkelheit* für einen unheimlichen Dungeon), um die Liste nach Songs zu filtern, die genau diesen Werten entsprechen.
* **Tags umschalten:** Klicke auf die pillenförmigen Buttons (wie **Kampf** oder **Reise**), um schnell nach bestimmten Szenentypen zu filtern.

### 3. Wiedergabe & Lautstärke
* **Navigation:** Nutze die Standardtasten für Wiedergabe, Pause und Überspringen in der Mittelkonsole.
* **Fortschrittsbalken:** Die Wellenform/Zeitachse ermöglicht es dir, zu bestimmten Momenten in einem Track zu springen.
* **Lautstärkeregelung:** Nutze den grünen Keilschieber auf der rechten Seite, um den Audiopegel stufenlos anzupassen.
* **Shuffle:** Klicke auf das Shuffle-Symbol, um die aktuell gefilterte Auswahl zufällig wiederzugeben.

### 4. Suche & Favoriten
* **Suchleiste:** Nutze die "Filter songs..." Leiste über der Hauptliste, um einen bestimmten Track namentlich zu finden.
* **Favoriten:** Klicke auf den **goldenen Stern** neben einem Track, um ihn als Favoriten für den schnellen Zugriff während deiner Sessions zu markieren.

---

## 🛠 Kategorie-Referenz 

> [!IMPORTANT]
> **WIP** – Die finalen Standardkategorien können sich ändern und können von dir selbst unter den Einstellungen angepasst werden, um deinen persönlichen Bedürfnissen zu entsprechen.

| Kategorie     | Beschreibung                                  |
|:--------------|:--------------------------------------------|
| **Tempo** | Die Geschwindigkeit und Energie des Tracks. |
| **Dunkelheit**| Düstere, grimmige oder schwermütige Töne.    |
| **Emotional** | Emotionale, sanfte Klänge.                  |
| **Mystik** | Ätherische, magische oder geheimnisvolle Qualitäten. |
| **Spannung** | Anspannung und Suspense.                    |
| **Heroik** | Epische, triumphale und orchestrale Energie. |

*Viel Spaß beim Abenteuer!*

---

## 🧠 Details zur KI-Analyse

DungeonTuber nutzt Googles **Gemini 2.5 Flash** Modell, um Audiodateien zu analysieren und zu kategorisieren. 
Der Prozess beinhaltet das Hochladen der Audiodatei an die Gemini-API und die Verwendung eines spezifischen Prompts zur Generierung von Metadaten.

### System-Anweisung
Der System-Prompt definiert die Persona und die Bewertungsphilosophie:
> Du bist ein erfahrener Hörer von Fantasy-, Film- und Rollenspielmusik. Du bewertest Musik so, wie sie von einem durchschnittlichen Hörer wahrgenommen wird – nicht technisch oder analytisch, sondern emotional und szenisch.
>
> * Deine Bewertungen müssen über viele hundert Tracks hinweg konsistent bleiben.
> * Eine 3 bedeutet immer dasselbe, unabhängig davon, welcher Track zuvor bewertet wurde.
> * Die Werte sollten im Verhältnis zueinander sinnvoll verteilt sein (nicht alles ist eine 1 oder 10).
> * Nutze die volle Skala von 1 bis 10, wenn es angemessen ist.
> * Halte dich strikt an die vorgegebenen Kategorien, Tags und deren Beschreibungen.
> * Gib nur JSON zurück, ohne zusätzliche Erklärungen.

### Benutzer-Prompt
Der Benutzer-Prompt liefert den Kontext (speziell zugeschnitten auf RPGs wie "Das Schwarze Auge" oder "D&D") sowie die Definitionen für Kategorien und Tags:
> Aufgabe: Kategorisiere das folgende Musikstück für die Verwendung in einem Rollenspiel.
> Bewerte das Stück basierend auf den unten stehenden Kategorien mit jeweils einem Wert von 1 bis 10.
>
> Hier ist die Liste der Kategorien zur Bewertung, zusammen mit ihren Beschreibungen:<br/>
> *[Dynamische Liste von Kategorien, Beschreibungen und Intensitätsstufen]*
>
> Weise anschließend einige Tags aus der folgenden Liste zu, die am besten passen. Hier ist keine Skala erforderlich:<br/>
> *[Dynamische Liste von Tags und Beschreibungen]*

---

## 🛠️ Build-Anweisungen


## Übersetzungen aktualisieren:
Bearbeite die Übersetzungen in den Dateien `_locales/**/LC_MESSAGES/DungeonTuber.po` und führe dann die folgenden Befehle aus, um die .mo-Dateien zu aktualisieren. 
```bash
msgfmt -o locales/en/LC_MESSAGES/DungeonTuber.mo locales/en/LC_MESSAGES/DungeonTuber.po
msgfmt -o locales/de/LC_MESSAGES/DungeonTuber.mo locales/de/LC_MESSAGES/DungeonTuber.po
```


## Verwendung von PyInstaller (Empfohlen)

```bash
pyinstaller DungeonTuber.spec
```

## Verwendung von Nuitka

Der folgende Befehl nutzt MinGW64. Wenn die Kompilierung langsam ist, stelle sicher, dass dein Build-Verzeichnis vom Antiviren-Scan ausgeschlossen ist.

```bash
python -m nuitka --jobs=16 DungeonTuber.py --product-version=0.0.1.0 --file-version=0.0.1.0
```

> [!Note]
> Füge --product-version=X.Y.Z.Q und --file-version=X.Y.Z.Q hinzu, um die Version der erstellten .exe zu definieren.

> [!Note]
> Das Flag --jobs legt die Anzahl der parallelen Kompilierungsprozesse fest. Passe dies basierend auf deinen CPU-Kernen an.