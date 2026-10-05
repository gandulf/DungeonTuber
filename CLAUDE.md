# CLAUDE.md

DungeonTuber is an RPG music player: a Python (FastAPI) backend with a Svelte 5 + TypeScript web frontend, shown in a pywebview window on the desktop.

## Hard Rules
- Python 3.12 only (`>=3.12,<3.13`)
- Entry points: `DungeonTuber.py` (desktop: pywebview window + embedded local server), `python -m server` (FastAPI server)
- Packages: `core` (domain logic, framework independent), `server` (FastAPI routes), `web/` (Svelte 5 + TypeScript frontend)
- `core/` must not import GUI frameworks (enforced by `tests/test_core_is_qt_free.py`)
- Core code uses `from core.i18n import _` instead of the gettext builtin
- Settings live in `%APPDATA%/DungeonTuber/settings.json` (`core.settings.AppSettings`); legacy QSettings registry values are imported once (`core.legacy`)
- User-facing strings: gettext msgids in `locales/*.po`; the web uses them via `t()` (catalogs generated with `npm --prefix web run i18n`, extra German strings in `web/src/lib/i18n/extra.de.json`)
- Keep code flake8-clean
- Never commit or expose `docs/certificate.pfx`, `docs/certificate.b64` or `docs/SECRETS.md`
- Never commit `build/`, `dist/` or `__pycache__/`
- Do not edit `DungeonTuber.spec`, `DungeonTuber.iss` or `version.rc` unless the task is about packaging

## Authority & Links
- Web migration plan: `docs/MIGRATION_PLAN.md`
- Dependencies and version: `pyproject.toml`
- Build script: `build.py`
- Docs: `README.md` (English), `README.de.md` (German)
- Docs and images: `docs/`
- Translations: `locales/de`, `locales/en`
- Audio playback happens in the browser (Web Audio, `web/src/lib/audio/engine.ts`)

## Setup / Test
- Install: `pip install -e .[dev]` and `npm --prefix web ci`
- Lint: `python -m flake8`
- Test: `python -m pytest` (core + server) and `npm --prefix web test`; type-check the frontend with `npm --prefix web run check`
- Keep `web/src/lib/scoring.ts` in sync with `core/scoring.py` (parity tests on both sides)
- Server routes must resolve client paths with `server.paths.safe_path`/`safe_id` (library-root boundary)

## Workflow
- Run the app: `npm --prefix web run build` then `python DungeonTuber.py` (`--fake` simulates WiZ bulbs)
- Web dev: `python -m server --fake-lights` + `npm --prefix web run dev`; test data: `python scripts/make_test_library.py <dir>` and `python -m server --data-dir <dir2> --library <dir>`
- Lint: `python -m flake8`
- Test: `python -m pytest`
- Build (translations, flake8, tests, web build, PyInstaller): `python build.py`
- Build executable via Nuitka (after the web build): `python -m nuitka --include-data-dir=web/dist=web/dist --include-data-dir=locales=locales --jobs=16 DungeonTuber.py --product-version=0.2.0.0 --file-version=0.2.0.0`

## Stop Conditions
- Ask before adding or upgrading dependencies in `pyproject.toml`
- Ask before touching certificates, secrets or signing files
- Ask before running the packaging build (`python build.py`) or changing its config
- Ask before deleting or renaming files under `locales/`
- Ask before any destructive git operation or push
- Refuse to commit credentials or key material
- Ask when a request conflicts with this file
