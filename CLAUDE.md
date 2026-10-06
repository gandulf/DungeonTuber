# CLAUDE.md

This is a python project that uses PySide6 and native vlc

## Hard Rules
- Python 3.12 only (`>=3.12,<3.13`)
- Entry point is `DungeonTuber.py`; it uses the `logic`, `config` and `components` packages
- Put UI code in `components`, config in `config`, and non-UI logic in `logic`
- Wrap all user-facing strings in gettext; translations live in `locales/`
- Keep code flake8-clean
- Never commit or expose `docs/certificate.pfx`, `docs/certificate.b64` or `docs/SECRETS.md`
- Never commit `build/`, `dist/` or `__pycache__/`
- Do not edit `DungeonTuber.spec`, `DungeonTuber.iss` or `version.rc` unless the task is about packaging

## Authority & Links
- Project instructions: `AGENTS.md`
- Dependencies and version: `pyproject.toml`
- Build script: `build.py`
- Docs: `README.md` (English), `README.de.md` (German)
- Assets and docs: `assets/`, `docs/`
- Translations: `locales/de`, `locales/en`
- Audio playback uses native VLC via `python-vlc`

## Setup / Test
- Install: `pip install -e .[dev]`
- Lint: `python -m flake8`
- No test suite is configured; verify changes by running the app

## Workflow
- Run the app: `python DungeonTuber.py`
- Lint: `python -m flake8`
- Build (runs flake8, compiles translations, then packages): `python build.py`
- Build executable via Nuitka: `python -m nuitka --jobs=16 DungeonTuber.py --product-version=0.2.0.0 --file-version=0.2.0.0`

## Stop Conditions
- Ask before adding or upgrading dependencies in `pyproject.toml`
- Ask before touching certificates, secrets or signing files
- Ask before running the packaging build (`python build.py`) or changing its config
- Ask before deleting or renaming files under `assets/` or `locales/`
- Ask before any destructive git operation or push
- Refuse to commit credentials or key material
- Ask when a request conflicts with this file or `AGENTS.md`
