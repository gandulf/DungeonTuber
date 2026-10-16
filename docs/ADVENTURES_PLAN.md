# Adventures (story blocks) – plan

An *adventure* organizes a campaign: blocks of formatted notes, each with linked music, effects and lights, connected into a
path. Songs and playlists stay the building blocks; adventures only reference them.

## Decisions

| Topic | Decision |
|---|---|
| Storage | `<name>.dtadv` (JSON) in a library root, uploaded images in `<name>.assets/`. Works with local and remote roots through `core.storage`. |
| Adventure identity | UUID inside the file; the file name is only a label. |
| Song identity | `UFID` frame with owner `dungeontuber` on every mp3 (random UUID). Independent of the MusicBrainz UFID (`core/mp3.py`, other owner). Remote files: id stored in the index only, the file is not rewritten. |
| Playlist identity | `#DT-ID:<uuid>` comment line in the extended M3U (ignored by other players). |
| Links between blocks | Default "next" plus optional labelled branches (graph). |
| Visibility | Per adventure `private` (owner only) or `public` (all users); the owner switches manually. |
| Played marker | Manual toggle per block. |
| Player | The persistent player dock plays block music through the existing queue; block music uses the main player's options (loop, shuffle, ...). Autoplay on entering a block is a per-block flag (default on). |
| Text | Markdown rendered with `marked` (approved), sanitized. `[[Block title]]` links are stored as block ids. |
| Effects | Ambient (looped) or one-shot sound effects per block, optionally started on entry. |
| Lights | Per block, reusing `core.lights.LightSetting`. |
| AI | New `story` mode of the assistant: song suggestions, light suggestions, text drafting, ambient/effect generation. |

## Data model (`.dtadv`)

```json
{
  "version": 1,
  "id": "uuid",
  "title": "The Sunken Crypt",
  "owner": "user",
  "visibility": "private",
  "blocks": [
    {
      "id": "uuid", "title": "Arrival at the tavern", "markdown": "...", "played": false, "pos": [120, 80],
      "autoplay": true,
      "music": [{"type": "song", "ufid": "uuid", "path": "last/known/path.mp3", "title": "Tavern"},
                {"type": "playlist", "id": "uuid", "path": "lists/tavern.m3u"}],
      "effects": [{"ufid": "uuid", "path": "...", "loop": true, "autostart": true}],
      "light": {},
      "images": ["Arrival.assets/map.png"]
    }
  ],
  "links": [{"from": "block-id", "to": "block-id", "label": null}]
}
```

Resolution of a song reference: UFID via the index first, last known path as fallback; if several files share a UFID the
first available one plays. A missing target shows a "missing, relink" chip and updates the stored path when relinked.

## Phases

### V0 – Stable identities (prerequisite)
- `core/mp3.py`: read/write the `dungeontuber` UFID frame (`update_mp3_ufid`), expose `ufid` on `Mp3Entry`.
- `server/index.py`: store `ufid` per track, lookup UFID → location, assign missing ids (random UUID).
- Assignment runs on **Refresh Library** (`server/rescan.py`) with progress, and automatically for new imports/uploads.
  Remote files get the id in the index only.
- Playlists: read/write `#DT-ID:` in `server/playlists.py`; assign on first write or refresh, keep it when moved or renamed.
- **Find duplicates** also reports files that share a UFID (copies), next to the audio-hash groups.
- API: resolve `ufid` → `{id, path}` for tracks and playlists.
- Tests: tag round trip, id kept on tag edit/move, remote index-only, duplicate UFID groups, M3U compatibility.

### V1 – Adventures: editor, list, play mode
- `core/adventures.py` (framework independent): model, validation, load/save, reference resolution; `server/adventures.py` + `server/routes/adventures.py`:
  list/create/read/update/delete, visibility toggle, ownership checks, `safe_path` boundary.
- Visibility: public adventures are readable by everyone; only the owner edits. **Publishing** warns about referenced
  private playlists; they then show as unavailable to other users.
- Web: new main tab and sidebar list of adventures; block list editor (title, markdown editor with formatting toolbar and
  preview, music/effects/light pickers, "link to ..." picker for next/branches, played toggle); autosave.
- Play mode: current block large, next/branch buttons, entering a block starts music (if autoplay), applies the light
  setting, starts auto effects; player dock stays; manual played marker.
- i18n strings in every `core/locales/*.json`, frontend tests for reference resolution and navigation, server tests for
  permissions and the publish warning.

### V2 – Graph canvas, images, note links
- Node canvas (pan/zoom, drag blocks, draw links, branch labels); list view remains the mobile layout.
- Image upload into `<name>.assets/` (size/type limits, served through a safe route), insert via the editor toolbar.
- `[[Block title]]` links with autocomplete, stored as ids; rename-safe; click jumps to the block (edit and play mode).
- Cleanup of unused images.

### V3 – AI assistance (assistant `story` mode)
- (a) Song suggestions from a block's text using tags, moods and scoring (`core/scoring.py`, kept in sync with `web/src/lib/scoring.ts`).
- (b) Light suggestion from the text (reuses the light agent).
- (c) Draft or expand block text from bullet points (read-aloud text, descriptions).
- (f) Generate ambient music or sound effects from a block's text via `musicgen`/`soundgen`; result attaches to the block.
- Always a suggestion the user accepts; nothing is changed silently.

### Later (not committed)
- Session recap from played blocks, "plausible next blocks" suggestions, export/import of an adventure as a bundle (file + assets), printable GM notes.

## Risks
- UFID backfill writes to every local mp3: must be resumable, skip read-only files and report failures.
- Copied files share a UFID by design; resolution takes the first available file and Find duplicates surfaces them.
- Remote roots: indexes are authoritative, so a UFID lives only in the database there.
- Adding `marked` needs a `package.json` change (approved) and sanitizing of the rendered HTML.
