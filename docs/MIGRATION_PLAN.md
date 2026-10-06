# DungeonTuber – Web Frontend Migration Plan

Target: **FastAPI backend (Python) + Svelte/TypeScript web frontend**, audio played **in the browser**, one GM per server, reachable on LAN and internet. Clean cut: new code in `core/`, `server/`, `web/`; the Qt app keeps working until switch-over.

---

## 1. Target architecture

```
 Browser / pywebview window (Svelte SPA)
   ├─ Web Audio: music deck A/B (crossfade), effects bus
   ├─ REST  /api/*      library, metadata, playlists, settings, presets, analysis
   ├─ GET   /media/*    audio stream (HTTP range) + covers
   └─ WS    /ws         events: analysis progress, library changes, light state
        │
 FastAPI server (uvicorn)            ── core/ (Qt-free Python)
   ├─ auth (password → session cookie)   mp3 tags (mutagen), m3u, scoring
   ├─ library index (SQLite)             analyzer client (voxalyzer, later LLM)
   ├─ job queue (analysis)               lights (pywizlight, asyncio)
   └─ settings store (JSON/SQLite)       categories, presets, settings
        │
 Light agent (optional, runs next to the bulbs; see §7)
```

Principles:
- **MP3 tags stay the source of truth** (categories, tags, summary, favorite, light, chapters). SQLite is only an index/cache for fast filtering of large libraries.
- **Scoring/filtering runs in the client** on the loaded track list (instant slider feedback, works for 10k rows); the server provides the data.
- **Settings move server-side** (they belong to the GM, not a machine); pure view prefs (column widths, panel collapse) live in `localStorage`.

---

## 2. Feature inventory → new home

Legend: **S** = server/core, **C** = client, **S+C** = both.

### Library & files
| Feature (today) | New home | Notes |
|---|---|---|
| Directory tree, only `.mp3`/`.m3u`, hidden files filtered, dirs first | S+C | `GET /api/browse?path=` restricted to configured **library roots** (no arbitrary FS access over internet) |
| Root dir / back / go-into / parent navigation, expanded dirs persisted | C | history + expanded state in localStorage |
| Smart filter (hide folders without music) | S | precomputed by index |
| Favorites (folder bookmarks) | S | settings |
| Move files via drag & drop in tree | S | `POST /api/files/move` – keep, guarded to roots |
| File cache (`%TEMP%` JSON, currently broken) | — | replaced by SQLite index |
| Open folder / playlist as tab, tabs persisted, lazy loading of non-active tabs | C | open tabs stored in settings; lazy fetch on activate |
| Tab context menu: refresh, close, close others, close all | C | |
| Welcome page when no tab open | C | rewrite as onboarding screen (links currently stubs) |

### Song table
| Feature | New home | Notes |
|---|---|---|
| Columns: index, fav, cover, file/title, summary, artist, album, genre, BPM, score, one per category | C | virtualized table (TanStack Virtual) |
| Header menu: show/hide each column, categories submenu, dynamic columns, title-vs-filename, summary under title, tags, row style S/M/L | C | prefs → settings |
| Auto-hide score column when no filter | C | |
| Score formula (squared category diff, +100 missing tag/genre, BPM diff) | C (+S lib) | port 1:1 to TS; keep Python version in `core/` for future LLM/server use |
| Cell coloring by distance to filter (BPM, genre, category), score color bands | C | |
| Delegates: cover crop, category bars, star, title+summary+tag pills, light bulb tint | C | |
| Sort by any column; filter → auto sort by score + select first row | C | |
| Text filter (name + summary) and type-to-search pill | C | |
| Enter = play, Delete = remove, F2/double-click = inline edit | C | |
| Inline edit title/summary/artist/album/genre/BPM/categories → write tags | S+C | `PATCH /api/tracks/{id}` |
| Double-click fav toggles favorite; cover opens image popup | C | |
| Context menu: edit song, analyze, add to playlist (new / existing), remove | S+C | |
| Drag reorder (playlists), drop folders/m3u to open, drop files into playlist, drop tag chip onto song | S+C | browser DnD; OS file drop = upload to library (new capability) |
| Lazy batch loading | S+C | paginated/streamed JSON |

### Filter panel
| Feature | New home | Notes |
|---|---|---|
| Category sliders grouped in tabs by `category.group` | C | |
| Russell circumplex (valence/arousal) with song scatter, clear, apply on release | C | canvas/SVG component |
| BPM dial (0–200, step 20, 0 = off) | C | |
| Tag & genre chips from current table, drag tag chip | C | |
| Presets: save (name), apply, remove, reset, clear values | S+C | `/api/presets` |
| View modes Simple / Player / Complex + per-widget toggles | C | settings |

### Player
| Feature | New home | Notes |
|---|---|---|
| Play/pause, prev/next (row order of current view), shortcuts Ctrl+P/B/N | C | |
| Repeat none/single (all exists but unreachable) | C | expose all three |
| Seek slider with click-jump, live drag | C | |
| Chapters: ticks + labels + light-color dot, tooltip, snap, fire within 3 s, add/edit/remove via right-click | S+C | chapters stored in CHAP frames via API |
| Volume 0–150 (v²/100 curve), mute, Ctrl+M / Ctrl+Up/Down, persisted | C | GainNode; >100 % via gain > 1 |
| Crossfade (1 s linear, two players) | C | two `<audio>` → MediaElementSource → GainNodes |
| Normalize volume (VLC compressor) | C | DynamicsCompressorNode |
| Visualizer: none / fake bars / VLC spectrum | — | dropped for v1 (decision §11.6) |
| Current song survives connection drops | C | whole file fetched as Blob before playback (decision §11.2) |
| Now playing label, error state | C | + MediaSession API (OS media keys, lock screen) |

### Effects
| Feature | New home | Notes |
|---|---|---|
| Effects directory scan (folders = effect with up to 5 intensities, cover.jpg) | S | `/api/effects` |
| Parallel looped playback, own play/pause (Ctrl+E) and volume | C | separate Web Audio bus, `loop=true` |
| List / grid (1–3 cols) view, title-vs-filename, search | C | |
| Intensity buttons 1..N switching variant while playing | C | |
| Effect light setting applied on play | S+C | see §7 |

### Lights (WiZ)
| Feature | New home | Notes |
|---|---|---|
| Discovery (broadcast IP, timeout), fake mode | S / agent | must run on the bulbs' LAN |
| Light list, rename, on/off, brightness, temperature (per-bulb range), color, scene (exclusive) | S+C | `/api/lights/*`, state via WS |
| Multi-select apply | C | |
| "Controlled by songs" (scenable) – song/chapter/effect light cues | S+C | client sends cue on play/chapter; server/agent applies |
| Light settings persisted (LIGHTS_CONFIG) | S | |

### Analysis
| Feature | New home | Notes |
|---|---|---|
| Voxalyzer local exe (port discovery) / remote URL / mock | S | async httpx client; add timeouts |
| Analyze file(s), skip already analyzed, 8 parallel workers, queue | S | job queue + WS progress |
| Write summary/categories/tags back to file | S | |
| Future LLM features | S | natural home in `core/` |

### App shell, settings, misc
| Feature | New home | Notes |
|---|---|---|
| Panel layout (tree / center / effects+lights), toggles, collapsible | C | resizable panes |
| Light / dark / system theme, font size S/M/L | C | CSS variables + `prefers-color-scheme` |
| Fullscreen F11/Esc | C | Fullscreen API |
| Locale switching (de/en, gettext) | S+C | server keeps gettext for category names; client uses JSON catalogs generated from the `.po` files |
| Settings dialog: language, voxalyzer URL/local, debug, normalize, song table options, categories editor (key/name/group/description/levels), lights IP/timeout | S+C | validate server-side (fixes crashes) |
| Edit song dialog: name (rename), title, album, artist, genre, BPM, tags, summary, favorite, cover upload, light setting | S+C | multipart for cover |
| Save favorites as playlist, add to playlist, create playlist | S | |
| About, update check (GitHub releases) | S+C | |
| Guided tour (9 steps) | C | e.g. driver.js |
| Status messages + progress bar | C | toast + WS progress |
| Logging to `%APPDATA%` | S | platformdirs |
| **New**: login, library roots config, upload | S+C | required for internet access |

---

## 3. Backend: make the core Qt-free (`core/`)

Today `logic/` and `config/` depend on Qt (QSettings, QThread, Signal, QPixmap, QColor, QApplication). Plan:

| Module | Change |
|---|---|
| `config/settings.py` | `QSettings` → `SettingsStore` backed by JSON (or SQLite) in `platformdirs.user_data_dir`; one-time importer reads existing QSettings values. Fix: load saved categories/presets at startup. Replace mutable defaults in `FilterConfig`. |
| `logic/mp3.py` | Covers as raw bytes + mime (thumbnail via Pillow) instead of QPixmap; drop `Mp3FileLoader(QThread)` → generator/async; fix favorite read/write, `update_mp3_light(None)`, chapter `None` light crash, `list_mp3s` recursion. |
| `logic/analyzer.py` | `asyncio` + `httpx` with timeouts; events via callback/async queue instead of Qt signals; `_winapi` only on Windows. |
| `logic/lightengine.py` | `QColor` → hex string / `(r,g,b)`; native asyncio (pywizlight is async already) instead of `QThread` + blocking loop; fix hash/eq mismatch and the `PRESETS` removal on lights-config error. |
| `config/utils.py` | Split: pure helpers → `core/utils.py`; Qt helpers stay with the Qt app. `kelvin_to_rgb` returns hex. |
| `logic/audioengine.py`, `config/theme.py` | Not ported (browser playback / CSS). Stay for the Qt app until switch-over. |
| gettext | Explicit translator object instead of global `_` builtin in core. |

Approach: create `core/` by **moving and de-Qt-ing** modules, then make the Qt app import from `core/` with thin Qt adapters. Both frontends run on the same core during the transition.

---

## 4. Data & storage

- **Library roots**: configured list of directories the server may expose (security boundary for internet use).
- **SQLite index** (`tracks`: path, mtime, size, title, artist, album, genres, bpm, length, summary, favorite, categories JSON, tags JSON, light JSON, has_cover, chapters JSON). Rebuilt incrementally by mtime; watchdog for live changes (optional).
- **Settings**: one JSON document per server (single GM) + presets + categories; import from QSettings once.
- **Playlists**: stay `.m3u` files inside library roots.

---

## 5. API surface (first cut)

```
POST   /api/auth/login | /logout              GET /api/me
GET    /api/browse?path=                      (tree, roots, smart filter)
GET    /api/tracks?dir=|playlist=             (paginated or streamed)
GET    /api/tracks/{id}       PATCH /api/tracks/{id}       (tags, rename)
PUT    /api/tracks/{id}/cover POST /api/tracks/{id}/favorite
PUT    /api/tracks/{id}/chapters
GET    /media/tracks/{id}     (Range)         GET /media/covers/{id}?size=
GET/POST/PUT/DELETE /api/playlists[/...]      (create, add, insert, reorder, remove)
POST   /api/files/move        POST /api/upload
GET    /api/effects           GET /media/effects/{id}/{intensity}
GET/PUT /api/settings         GET/PUT /api/categories     CRUD /api/presets
POST   /api/analysis/jobs     GET /api/analysis/jobs/{id}
GET    /api/lights  POST /api/lights/discover  PATCH /api/lights/{mac}  POST /api/lights/cue
GET    /api/version           (update check)
WS     /ws                    (analysis.progress, analysis.done, library.changed, lights.state)
```

Track ids: stable hash of the path relative to its library root.

---

## 6. Frontend (`web/`)

- **Stack**: Svelte 5 + TypeScript + Vite, TanStack Virtual (table), plain CSS variables (light/dark tokens from the new Qt theme), driver.js (tour), svelte-i18n with catalogs generated from `locales/*.po`.
- **Modules**: `api/` (typed client, generated from FastAPI OpenAPI), `audio/` (engine: decks, crossfade, effects bus, analyser, MediaSession), `stores/` (library, filter, player, settings, lights), `components/` (FileTree, SongTable, FilterPanel, Circumplex, BpmDial, Chips, Player, SeekBar+Chapters, Effects, Lights, dialogs, Tour).
- **Performance on old hardware**: virtualization, covers as small cached thumbnails, scoring in a Web Worker if needed, no heavy UI framework.

---

## 7. Lights constraint

WiZ bulbs are controlled by UDP broadcast on the local network; a browser cannot send UDP, and an internet-hosted server cannot reach the table's LAN.

- **Server on the same LAN as the bulbs** (home server, laptop at the table): server controls lights directly – works out of the box.
- **Server remote**: ship a small **light agent** (Python, same `core.lights`) that runs on a machine at the table, connects *outbound* to the server via WebSocket, and executes cues. The pywebview desktop build can embed the agent automatically.

Decision: the server runs on the bulbs' LAN; the agent is not planned for now.

---

## 8. Desktop & server packaging

- **Desktop**: pywebview window + embedded uvicorn on `127.0.0.1` (random port, auth bypass for local mode), WebView2 runtime (preinstalled on Win 10/11). Built with PyInstaller (Nuitka dropped); voxalyzer.exe bundling and Inno Setup/signing pipeline reused.
- **Server**: `pip install` / Docker image; HTTPS via Caddy reverse proxy; config file for library roots and password.
- CI: add `npm ci && npm run build` (web assets bundled into the Python package), pytest for `core/` and API, Playwright smoke test.

---

## 9. Phases

| # | Phase | Deliverable |
|---|---|---|
| 0 | Spikes | Web Audio crossfade from Blob-cached tracks + 10k-row virtual table on old hardware |
| 1 ✅ | `core/` extraction | Qt-free core with tests (mp3 tags, m3u, scoring, settings, analyzer client, lights); Qt app running on `core/`; listed bugs fixed |
| 2 ✅ | Server MVP | FastAPI: auth, roots, browse, tracks list/edit, media streaming, covers, settings, presets, categories; SQLite index |
| 3 ✅ | Web MVP | Shell + tree + tabs + song table + filter panel (sliders, chips, BPM, circumplex, presets) + player (crossfade, repeat, volume, chapters view) |
| 4 ✅ | Editing & playlists | Inline edit, edit dialog, cover upload, favorites, playlists (create/add/reorder/remove), DnD, chapters edit, mp3 upload into library roots |
| 5 ✅ | Effects & analysis | Effects panel and bus; analysis jobs with WS progress; voxalyzer local/remote |
| 6 ✅ | Lights | LAN light control (server on bulbs' LAN), cues from songs/chapters/effects |
| 7 ✅ | Desktop build | pywebview packaging, installer, signing, update check; migration of existing QSettings |
| 8 ✅ | Parity & switch-over | Tour, i18n, themes, settings dialog; parity checklist (§2) ticked; remove Qt UI |

---

## 9a. Implementation status (2026-10-05)

- `server/` – FastAPI app (`python -m server`): auth (password + signed cookie, loopback-only without password, `--local` desktop mode), library-root boundary for every path, browse/smart filter, tracks (SQLite tag cache), PATCH edits incl. rename, chapters, cover upload + Pillow thumbnails, range streaming, playlists (create/add/insert/reorder/remove), move, folders, mp3 upload, effects, settings/categories/presets, analysis queue with WebSocket progress, WiZ lights (discover, patch, cues), version/locales. 16 API tests in `tests/test_server.py`.
- `web/` – Svelte 5 + TypeScript SPA: file tree (drag-move, upload drop, favorites, smart filter), tabs (lazy, persisted, context menu), virtualized song table (all columns/options of the Qt table, score colors, inline edit, type-to-search, multi-select, reorder, tag drop, tree/file drop), filter panel (presets, grouped sliders, circumplex, BPM, chips), player (Web Audio crossfade, normalize, repeat none/all/single, chapters with light cues and editing, in-memory copy of the current song, MediaSession), effects bus (grid/list, intensities), lights panel, edit/settings/about dialogs, tour, light/dark/system theme, font size, de/en i18n (`locales/*.json`, shared with the server), responsive drawer layout for phones. Vitest parity tests for scoring and ids.
- `DungeonTuber.py` – pywebview window + embedded local server; packaged by `DungeonTuber.spec` / `python build_app.py`; "Share on network" lets other devices join.
- Deployment: Python wheel (frontend + translations inside the packages), Docker image on GHCR (amd64/arm64, `deploy/docker-compose.yml` with Caddy), systemd example; the release workflow builds installer, wheel and image.
- Legacy QSettings migration was dropped (fresh start with `settings.json`).
- gettext `.po`/`.mo` files were replaced by `locales/<lang>.json` as the single translation source.

### Switch-over (done)
- The Qt UI (`components/`, `config/`, `logic/`, VLC, PySide6) was removed. `DungeonTuber.py` is now the desktop launcher (pywebview + embedded server); `DungeonTuber.spec`, `build.py` and `release-app.yml` build it (web frontend included). The exe name and the Inno Setup installer are unchanged.
- **Not ported (by decision)**: VLC/fake visualizer. Native "Open Directory/Playlist" file dialogs are replaced by the file tree (a browser cannot open server-side dialogs).
- `assets/icons` (Qt theme icons) was removed.

## 10. Existing bugs (fix in `core/` or don't port)

Phase 1 status: fixed in `core/` or the Qt adapters – favorite tag, light/chapter `None` crashes, stale chapters on rewrite, `list_mp3s` recursion, presets/categories reload, lights-config error removing presets, Light hash/eq, analyzer timeouts, artist→album edit, genre split, edit return values, `FilterConfig` shared defaults and `toggle_tag`, empty-playlist removal, append to new playlist without header. Still open (UI-only, not ported): settings dialog delegate, tab close bookkeeping, save-favorites/add-to-playlist edge cases, `QMessageBox` signature, REPEAT_ALL, inconsistent defaults, file cache.


- Favorite tag always reads `True` once written (mp3.py:391/470).
- `update_mp3_light(None)` and chapters with `light=None` crash (mp3.py:612/630).
- `list_mp3s(recursive=True)` doesn't recurse (mp3.py:654).
- Saved custom categories/presets not reloaded from settings in `config/` (verify UI-side loading).
- Lights config load error removes `PRESETS` (lightengine.py:281); Light hash/eq mismatch.
- No HTTP timeouts in analyzer calls.
- File cache `load_cache` always resets (files.py:72).
- Edit artist writes album (songs.py:193); genre split reversed (songs.py:78); some edits don't return True.
- Settings dialog: category table delegate columns off by one + bad `super` call; no validation of timeout/levels JSON.
- Tab "close others/all" don't update open tabs; "Save favorites" passes `checked` as entries; "add to playlist" with no tab open crashes; wrong `QMessageBox.warning` signature.
- REPEAT_ALL unreachable; inconsistent defaults for summary column and effects title setting.

---

## 11. Decisions (confirmed)

1. **Lights**: server runs on the same LAN as the bulbs. No light agent planned for now (§7 agent stays a future option).
2. **Offline resilience**: only the **currently playing song** is pre-cached – the client downloads the whole file (`fetch` → Blob → object URL) before/while playing, so a connection drop doesn't interrupt the current track. No service worker / playlist caching.
3. **Upload**: browser upload of mp3 files into a library root folder is in scope (Phase 4).
4. **Formats**: mp3 only (as today).
5. **Settings scope**: view preferences per device (localStorage); data settings (categories, presets, favorites, library roots, lights, analyzer) per server.
6. **Visualizer**: not important – dropped for v1 (no VLC/fake/spectrum visualizer). Can be added later via AnalyserNode if wanted.
