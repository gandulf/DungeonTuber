"""Writes a sample adventure that uses every feature of the adventure blocks into a library: "Unter dem Nordlicht (Beispiel)".

It is an original short adventure in the far north of Thorwal (Das Schwarze Auge), not the text of the published adventure of
the same name: it shows what a prepared adventure can look like. The songs and effects are taken from the library itself (matched
by keywords in their titles, tags, genres and folders), the covers and a map are painted here.

Usage: python scripts/make_sample_adventure.py <library-root> [--effects <effects-folder>] [--owner <user>]

Songs need their stable id (UFID): refresh the library in the app once (it assigns them) before running this. The adventure appears
in the app after a restart of the server or a click on the adventures (the list is read again).
"""
import argparse
import json
import math
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import adventures as model  # noqa: E402
from core.mp3 import parse_mp3  # noqa: E402

TITLE = "Unter dem Nordlicht"

# grid of the stored block positions (see web/src/lib/adventures.ts: NODE_W + gap, NODE_H + gap)
COLUMN, ROW = 250, 86


# --- the library: songs and effects ------------------------------------------

def songs_of(root: Path, skip: Path | None) -> list[dict]:
    found = []
    for path in sorted(root.rglob("*.mp3")):
        if ".adventures" in path.parts or (skip and skip in path.parents):
            continue
        entry = parse_mp3(path)
        if entry and entry.ufid:
            words = " ".join([entry.title or path.stem, *entry.tags, *entry.genres, path.parent.name]).lower()
            found.append({"ufid": entry.ufid, "path": path.as_posix(), "title": entry.title or path.stem, "words": words})
    return found


def effects_of(folder: Path | None) -> list[dict]:
    if not folder or not folder.is_dir():
        return []
    return [{"path": item.as_posix(), "name": item.stem, "words": item.stem.lower()}
            for item in sorted(folder.iterdir()) if item.is_dir() or item.suffix.lower() == ".mp3"]


class Picker:
    """Chooses songs and effects by keywords; the same song is not chosen twice while others fit."""

    def __init__(self, songs: list[dict], effects: list[dict]):
        self.songs, self.effects, self.used = songs, effects, set()

    def song(self, *keywords: str) -> dict | None:
        fitting = [song for song in self.songs if any(word in song["words"] for word in keywords)]
        fresh = [song for song in fitting if song["ufid"] not in self.used] or fitting
        rest = [song for song in self.songs if song["ufid"] not in self.used] or self.songs
        choice = (fresh or rest or [None])[0]
        if choice:
            self.used.add(choice["ufid"])
        return choice

    def effect(self, *keywords: str) -> dict | None:
        fitting = [effect for effect in self.effects if any(word in effect["words"] for word in keywords)]
        return (fitting or self.effects or [None])[0]


def song_ref(song: dict | None) -> list[dict]:
    return [{"type": "song", "ufid": song["ufid"], "path": song["path"], "title": song["title"]}] if song else []


def effect_ref(effect: dict | None, loop: bool, autostart: bool) -> list[dict]:
    return [{"path": effect["path"], "name": effect["name"], "loop": loop, "autostart": autostart}] if effect else []


def song_link(song: dict | None, text: str) -> str:
    return f"[{text}](song:{song['ufid']})" if song else text


# --- pictures -----------------------------------------------------------------

def aurora(seed: int, size=(960, 540)) -> bytes:
    """A northern light over a dark sky with stars and a snowy horizon."""
    import io

    from PIL import Image, ImageChops, ImageDraw, ImageFilter

    rng = random.Random(seed)
    width, height = size
    image = Image.new("RGB", size)
    draw = ImageDraw.Draw(image)
    for y in range(height):  # night sky: deep blue to near black
        t = y / height
        draw.line([(0, y), (width, y)], fill=(int(8 + 10 * t), int(14 + 22 * t), int(38 + 30 * t)))
    for _ in range(220):
        x, y = rng.randrange(width), rng.randrange(int(height * 0.7))
        light = rng.randrange(150, 255)
        draw.point((x, y), fill=(light, light, light))
    glow = Image.new("RGB", size, (0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    palette = [(60, 255, 160), (90, 220, 255), (170, 110, 255)]
    for band in range(3):
        color = palette[(band + seed) % 3]
        phase, amplitude, base = rng.random() * 6.28, 30 + 25 * band, height * (0.22 + 0.12 * band)
        for x in range(0, width, 3):
            y = base + amplitude * math.sin(x / (120 + 40 * band) + phase)
            for step in range(0, 120, 6):
                fade = 1 - step / 120
                glow_draw.line([(x, y - step), (x + 3, y - step)], fill=tuple(int(c * fade * 0.6) for c in color))
    image = ImageChops.add(image, glow.filter(ImageFilter.GaussianBlur(10)))
    draw = ImageDraw.Draw(image)
    hills = [(0, height)] + [(x, height * 0.82 - 30 * math.sin(x / 140 + seed)) for x in range(0, width + 40, 40)] + [(width, height)]
    draw.polygon(hills, fill=(214, 226, 240))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def sketch_map(size=(640, 420)) -> bytes:
    """A small hand-drawn map: coast, ice, camp and cave."""
    import io

    from PIL import Image, ImageDraw

    width, height = size
    image = Image.new("RGB", size, (236, 226, 200))
    draw = ImageDraw.Draw(image)
    coast = [(0, 300), (90, 280), (160, 310), (240, 270), (330, 300), (420, 260), (520, 290), (640, 250), (640, 420), (0, 420)]
    draw.polygon(coast, fill=(150, 185, 210))
    for x, y, label in ((80, 330, "Olport"), (300, 170, "Lager"), (520, 90, "Eishoehle")):
        draw.ellipse((x - 7, y - 7, x + 7, y + 7), fill=(120, 40, 30))
        draw.text((x + 12, y - 8), label, fill=(60, 40, 30))
    draw.line([(80, 330), (190, 240), (300, 170), (420, 130), (520, 90)], fill=(120, 40, 30), width=3)
    draw.rectangle((2, 2, width - 3, height - 3), outline=(90, 70, 50), width=3)
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


# --- the adventure ------------------------------------------------------------

def build(pick: Picker, images: dict[str, str]) -> tuple[list[dict], list[dict]]:
    tavern, travel = pick.song("tavern", "festivity", "folk", "happy"), pick.song("calm", "travel", "ambient", "folk")
    mystery, battle = pick.song("dark", "mystery", "crypt", "ambient"), pick.song("combat", "battle", "aggressive", "metal")
    finale, sad = pick.song("orchestral", "epic", "standing"), pick.song("sad", "emotional", "calm")
    fire, wind = pick.effect("fire", "feuer", "kamin"), pick.effect("wind", "sturm", "storm", "rain", "regen")
    water = pick.effect("water", "wasser", "sea", "meer", "rain", "regen")

    def block(block_id, title, column, row, markdown, music=(), effects=(), autoplay=True, cover=None):
        return {"id": block_id, "title": title, "pos": [column * COLUMN, row * ROW], "markdown": markdown.strip(), "played": False,
                "autoplay": autoplay, "music": [ref for song in music for ref in song_ref(song)], "effects": list(effects), "images": [],
                "cover": images.get(cover) if cover else None}

    blocks = [
        block("olport", "Ankunft in Olport", 0, 2, f"""
> Der Wind treibt feinen Schnee durch die Gassen der Hafenstadt. Aus der Langhalle *Zum Walfänger* dringen Gelächter, der Duft von gebratenem Fisch und das Prasseln eines mächtigen Herdfeuers. Über den Dächern flackert ein grünlicher Schein am Himmel – das Nordlicht, heller als die Alten es je gesehen haben.

### Wer ist da?
- **Ragna Eisbart**, Kapitänin einer Otta, laut, großzügig, sucht eine Mannschaft
- **Kaija**, eine junge Nivesin am Rand der Halle, die niemanden anzusprechen wagt
- Ein Skalde, der {song_link(tavern, 'ein Lied über Swafnirs Wale')} anstimmt

Die Helden kommen ins Gespräch, als Kaija mit zitternder Stimme nach „Menschen, die keine Angst vor dem Eis haben" fragt.
Weiter mit [Kaijas Bitte](block:bitte).
""", music=[tavern, travel], effects=effect_ref(fire, loop=True, autostart=True), cover="olport"),

        block("bitte", "Kaijas Bitte", 1, 2, """
> „Der Leuchtstein meiner Sippe ist fort. Ohne ihn finden die Herden im Winter nicht heim, und die Ahnen sprechen nicht mehr durch das Nordlicht zu uns.“

- Der Stein verschwand vor drei Nächten aus dem Lager, zwei Tagesreisen nach Norden.
- Kaija bietet Felle, Bernstein und das Wohlwollen ihrer Sippe.
- Ragna Eisbart bietet an, die Gruppe mit ihrer Otta die Küste entlang zu bringen – gegen einen Anteil an der Ehre.

**Entscheidung:** Über das Packeis oder die Küste entlang?
""", music=[tavern], autoplay=False),

        block("packeis", "Über das Packeis", 2, 1, """
> Die Hunde ziehen, der Schlitten knirscht über blankes Eis. Am Horizont verschwimmen Himmel und Schnee zu einem einzigen Weiß.

- **Gefahr:** eine verschneite Eisspalte (*Sinnesschärfe*-Probe, sonst *Körperbeherrschung* für den Lenker)
- Nachts: Firuns Kälte – wer kein Feuer hat, erleidet Erschöpfung
- Ein Rabe folgt der Gruppe seit Olport …
""", music=[travel], effects=effect_ref(wind, loop=True, autostart=True), cover="eis"),

        block("kueste", "Entlang der Küste", 2, 3, """
> Ragnas Otta schneidet durch graue Wellen, Eisschollen schlagen gegen die Planken. Die Mannschaft singt gegen den Sturm an.

- **Sturm:** *Seefahrt*-Probe oder das Boot treibt auf eine Untiefe
- Ragna erzählt von einem verstoßenen Thorwaler, der „mit einem Stein voller Lichter“ prahlte
- Anlegen in einer Bucht, ein halber Tagesmarsch zum Lager
""", music=[travel], effects=effect_ref(water, loop=True, autostart=True)),

        block("lager", "Das Lager der Nivesen", 3, 2, f"""
> Rauch steigt aus den Zelten, die Karene scharren unruhig im Schnee. Die Älteste empfängt euch schweigend am Feuer.

Die Älteste **Uukka** erzählt:
- In der Nacht des Diebstahls tanzte das Nordlicht „rot wie Blut“.
- Fremde Stiefelspuren führen nach Nordosten – siehe [[Die Spuren im Schnee]].
- Der Schamane **Tarvo** will mit den Helden in der Schwitzhütte die Ahnen befragen.

![Karte des Nordens|320](image:{images.get('map', '')})
""", music=[sad, mystery], effects=effect_ref(fire, loop=True, autostart=False) + effect_ref(wind, loop=True, autostart=True), cover="lager"),

        block("spuren", "Die Spuren im Schnee", 4, 1, """
- *Fährtensuche*-Probe: schwere Stiefel, ein Mann, ein Hundeschlitten
- An einem Lagerplatz: Asche, ein zerbrochenes Amulett mit Swafnir-Zeichen – der Dieb ist Thorwaler
- Die Spur führt zu einem Gletscher; dort wartet [der Firnwolf](block:wolf)
""", music=[mystery], effects=effect_ref(wind, loop=True, autostart=True)),

        block("schwitzhuette", "Die Schwitzhütte", 4, 3, """
> Heißer Dampf, der Rhythmus der Trommel, Tarvos raue Stimme. Hinter geschlossenen Augen seht ihr Lichter, die sich zu einem Weg formen – und am Ende des Weges eine Höhle aus blauem Eis.

- Vision: der Dieb heißt **Brandulf**, er will das Licht nutzen, um seine Schiffe durch die Winternacht zu führen
- Tarvo warnt: „Wer das Licht einsperrt, den holt die Kälte.“
""", music=[mystery], effects=effect_ref(fire, loop=True, autostart=True), autoplay=False),

        block("wolf", "Der Firnwolf", 5, 2, """
> Aus dem Schneetreiben tritt ein Wolf, größer als ein Pferd, sein Fell weiß wie frischer Firn. Er knurrt nicht – er wartet.

- Der Wolf bewacht den Weg zur Eishöhle; er greift nur an, wenn man ihn bedroht
- Kampfwerte: wie ein Firnwolf aus dem Bestiarium, aber erschöpft und verwundet
- Ein Pfeil mit thorwalscher Befiederung steckt in seiner Flanke

### Wie gehen die Helden vor?
""", music=[battle], effects=effect_ref(wind, loop=True, autostart=False)),

        block("gnade", "Ifirns Gnade", 6, 1, """
> Ihr zieht den Pfeil, der Wolf hält still. Dann leckt er eure Hand und verschwindet im Weiß – nur seine Spur zeigt den Weg.

- Belohnung: Der Wolf führt die Gruppe auf einem sicheren Pfad (keine Proben beim Abstieg)
- Gläubige spüren Ifirns Segen (+1 auf die nächste Probe gegen Kälte)
""", music=[sad], autoplay=False),

        block("hoehle", "Die Eishöhle", 7, 2, """
> Blaues Licht bricht sich in den Wänden aus Eis. Irgendwo tropft Wasser, und tief im Berg pulsiert ein grünes Leuchten.

- **Rätsel am Tor:** Drei Runen – Wal, Wolf, Licht. Die richtige Reihenfolge erzählt die Reise der Helden.
- **Falle:** brüchiger Boden über einem unterirdischen Fluss
- Am Ende des Gangs: Brandulf mit dem Leuchtstein
""", music=[mystery], effects=effect_ref(water, loop=True, autostart=True), cover="hoehle"),

        block("verhandlung", "Verhandeln mit Brandulf", 8, 1, """
- Brandulf wurde aus seiner Ottajasko verstoßen; mit dem Licht will er seine Ehre zurückgewinnen
- Argumente, die wirken: Ragnas Angebot, ihn in ihre Mannschaft aufzunehmen; die Warnung des Schamanen
- Gelingt die Verhandlung, gibt er den Stein freiwillig heraus
""", music=[sad], autoplay=False),

        block("kampf", "Kampf im Nordlicht", 8, 3, """
> Brandulf reißt den Stein hoch, und das Licht flutet die Höhle. Die Schatten der Helden tanzen grün und violett über das Eis.

- Brandulf und zwei Gefährten; das Licht blendet (Abzüge auf Fernkampf)
- Fällt der Stein zu Boden, bekommt er Risse – der Himmel draußen flackert
""", music=[battle, finale], effects=effect_ref(wind, loop=False, autostart=True)),

        block("nordlicht", "Unter dem Nordlicht", 9, 2, f"""
> Als der Stein in das Lager zurückkehrt, legt sich das Flackern am Himmel. Das Nordlicht fließt ruhig und hell über die Tundra, und die Nivesen singen ein Lied, das älter ist als Thorwal.

- Fest im Lager: {song_link(finale, 'das Lied der Ahnen')}
- Kaija schenkt jedem Helden ein Bernsteinamulett
- Ragna Eisbart bietet einen Platz auf ihrer Otta an – das nächste Abenteuer wartet
""", music=[finale], effects=effect_ref(fire, loop=True, autostart=True), cover="nordlicht"),

        block("epilog", "Epilog und Belohnung", 10, 2, """
- **Abenteuerpunkte:** 150 AP, +20 für eine friedliche Lösung mit Brandulf, +10 für die Gnade gegenüber dem Firnwolf
- **Spezielle Erfahrungen:** Wildnisleben, Fährtensuche, Überleben (Eis)
- **Kontakte:** die Sippe der Nivesen, Ragna Eisbart
""", autoplay=False),

        block("spielleitung", "Für die Spielleitung: Figuren", 0, 4, f"""
| Figur | Rolle |
|---|---|
| Ragna Eisbart | Kapitänin, Verbündete |
| Kaija | Auftraggeberin |
| Uukka, Tarvo | Älteste und Schamane der Nivesen |
| Brandulf | der Dieb, verstoßener Thorwaler |

Themen zum Anspielen: {song_link(tavern, 'Olport')}, {song_link(mystery, 'die Höhle')}, {song_link(battle, 'Kampf')}.

*Dieser Block ist mit keinem anderen verbunden: er ist ein Nachschlagezettel und wird im Spiel über die Blockauswahl geöffnet.*
""", autoplay=False),
    ]

    links = [
        ("olport", "bitte", None),
        ("bitte", "packeis", "Mit dem Hundeschlitten über das Eis"), ("bitte", "kueste", "Mit Ragnas Otta die Küste entlang"),
        ("packeis", "lager", None), ("kueste", "lager", None),
        ("lager", "spuren", None), ("lager", "schwitzhuette", "Den Schamanen begleiten"),
        ("spuren", "wolf", None), ("schwitzhuette", "wolf", None),
        ("wolf", "gnade", "Den Wolf verschonen"), ("wolf", "hoehle", "Am Wolf vorbei zur Eishöhle"),
        ("gnade", "hoehle", None),
        ("hoehle", "verhandlung", "Mit Brandulf reden"), ("hoehle", "kampf", "Den Stein mit Gewalt nehmen"),
        ("verhandlung", "nordlicht", None), ("kampf", "nordlicht", None),
        ("nordlicht", "epilog", None),
    ]
    return blocks, [{"from": a, "to": b, "label": label} for a, b, label in links]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path, help="the library root (its .adventures folder receives the adventure)")
    parser.add_argument("--effects", type=Path, help="the effects folder (default: <root>/Effects if it exists)")
    parser.add_argument("--owner", default="admin", help="the user the adventure belongs to (default: admin, the user of a single-user setup)")
    args = parser.parse_args()

    root = args.root.resolve()
    effects_folder = (args.effects or root / "Effects").resolve()
    songs = songs_of(root, effects_folder if effects_folder.is_dir() else None)
    effects = effects_of(effects_folder)
    if not songs:
        print("No songs with a stable id found: refresh the library in the app first (it assigns them).", file=sys.stderr)

    adventure_id = str(uuid.uuid4())
    folder = root / ".adventures"
    assets = folder / f"{adventure_id}.assets"
    assets.mkdir(parents=True, exist_ok=True)
    images = {}
    for key, data in (("olport", aurora(1)), ("eis", aurora(2)), ("lager", aurora(3)), ("hoehle", aurora(4)), ("nordlicht", aurora(5)),
                      ("map", sketch_map())):
        name = f"{uuid.uuid4().hex[:12]}.png"
        (assets / name).write_bytes(data)
        images[key] = name

    pick = Picker(songs, effects)
    blocks, links = build(pick, images)
    # the adventure's own playlist: what the blocks play plus a few spare songs the game master can add to blocks later
    spare = [song for song in songs if song["ufid"] not in pick.used][:4]
    music = [ref for block in blocks for ref in block["music"]] + [ref for song in spare for ref in song_ref(song)]
    data = {"id": adventure_id, "title": TITLE, "visibility": "private", "blocks": blocks, "links": links, "music": music}
    adventure = model.normalize(data, owner=args.owner)  # the same checks as the server: what is written here is what it accepts
    target = folder / f"unter-dem-nordlicht-beispiel-{adventure_id[:8]}.dtadv"
    target.write_text(json.dumps(adventure, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"{target}: {len(adventure['blocks'])} blocks, {len(adventure['links'])} links, {len(adventure['music'])} songs, "
          f"{sum(len(block['effects']) for block in adventure['blocks'])} effects, {len(images)} pictures")


if __name__ == "__main__":
    main()
