"""Converts locales/<lang>/LC_MESSAGES/DungeonTuber.po into JSON catalogs for the web frontend.

Usage: python scripts/po2json.py
"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES = ROOT / "locales"
OUT = ROOT / "web" / "src" / "lib" / "i18n"


def _unquote(line: str) -> str:
    return ast.literal_eval(line.strip())


def parse_po(path: Path) -> dict[str, str]:
    catalog: dict[str, str] = {}
    msgid, msgstr, target = None, None, None

    def flush():
        if msgid and msgstr:
            catalog[msgid] = msgstr

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr, target = _unquote(line[6:]), None, "id"
        elif line.startswith("msgstr "):
            msgstr, target = _unquote(line[7:]), "str"
        elif line.startswith('"'):
            if target == "id":
                msgid += _unquote(line)
            elif target == "str":
                msgstr += _unquote(line)
    flush()
    return catalog


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for po in sorted(LOCALES.glob("*/LC_MESSAGES/DungeonTuber.po")):
        lang = po.parent.parent.name
        catalog = parse_po(po)
        target = OUT / f"catalog.{lang}.json"
        target.write_text(json.dumps(catalog, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
        print(f"{lang}: {len(catalog)} messages -> {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
