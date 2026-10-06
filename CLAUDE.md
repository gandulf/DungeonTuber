# CLAUDE.md

DungeonTuber is an RPG music player: a Python (FastAPI) backend with a Svelte 5 + TypeScript web frontend, shown in a pywebview window on the desktop.

## Hard Rules
- Python 3.12 only (`>=3.12,<3.13`)
- Entry points: `DungeonTuber.py` (desktop: pywebview window + embedded local server), `python -m server` (FastAPI server)
- Packages: `core` (domain logic, framework independent), `server` (FastAPI routes), `web/` (Svelte 5 + TypeScript frontend)
- `core/` must not import GUI frameworks (enforced by `tests/test_core_is_qt_free.py`)
- Settings live in `%APPDATA%/DungeonTuber/settings.json` (`core.settings.AppSettings`, keys in `SettingKeys`); per-device view preferences live in the browser (`web/src/lib/prefs.svelte.ts`)
- Translations: `core/locales/<lang>.json` is the single source of truth (message id = English text). The web uses `t()` (`web/src/lib/i18n.svelte.ts`), the server `from core.i18n import _`. Add new strings to every locale file.
- Keep code flake8-clean
- Never commit or expose `docs/certificate.pfx`, `docs/certificate.b64` or `docs/SECRETS.md`
- Never commit `build/`, `dist/` or `__pycache__/`
- Do not edit `DungeonTuber.spec`, `DungeonTuber.iss`, `version.rc`, `Dockerfile` or `deploy/` unless the task is about packaging
- The server runs as a single process (in-memory analysis queue, lights, WebSocket hub); configuration via `DT_*` environment variables (`server/__main__.py`)

## Authority & Links
- Web migration plan: `docs/MIGRATION_PLAN.md`
- Dependencies and version: `pyproject.toml`
- Build script: `build_app.py`
- Docs: `README.md` (English), `README.de.md` (German)
- Docs and images: `docs/`
- Translations: `core/locales/de.json`, `core/locales/en.json`
- Audio playback happens in the browser (Web Audio, `web/src/lib/audio/engine.ts`)

## Setup / Test
- Install: `pip install -e .[desktop,dev]` and `npm --prefix web ci`
- Lint: `python -m flake8`
- Test: `python -m pytest` (core + server) and `npm --prefix web test`; type-check the frontend with `npm --prefix web run check`
- Keep `web/src/lib/scoring.ts` in sync with `core/scoring.py` (parity tests on both sides)
- Server routes must resolve client paths with `server.paths.safe_path`/`safe_id` (library-root boundary)

## Workflow
- Run the app: `npm --prefix web run build` (writes `server/static`) then `python DungeonTuber.py` (`--fake` simulates WiZ bulbs)
- Web dev: `python -m server --fake-lights` + `npm --prefix web run dev`; test data: `python scripts/make_test_library.py <dir>` and `python -m server --data-dir <dir2> --library <dir>`
- Lint: `python -m flake8`
- Test: `python -m pytest`
- Build (flake8, tests, web build, PyInstaller): `python build_app.py`
- Python wheel (frontend included): `python -m build --wheel`; Docker image: `docker build -t dungeontuber .`; deployment examples in `deploy/`

## Stop Conditions
- Ask before adding or upgrading dependencies in `pyproject.toml`
- Ask before touching certificates, secrets or signing files
- Ask before running the packaging build (`python build_app.py`) or changing its config
- Ask before deleting or renaming files under `core/locales/`
- Ask before any destructive git operation or push
- Refuse to commit credentials or key material
- Ask when a request conflicts with this file
