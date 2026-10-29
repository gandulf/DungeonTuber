// The open adventure: editing (autosaved), the path through its blocks in play mode and what a block starts (music, effects).
// Adventures are tabs next to folders and playlists (see stores/library.svelte.ts); the one of the active tab is `adventures.current`.
import { untrack } from 'svelte';
import { adventureExportUrl, api, pathToId } from '../api';
import { addAdventureMusic, addMusic, appendBlock, assignMusic, refKey, removeBlock } from '../adventures';
import { blockPrompt } from '../adventureAi';
import { data } from './data.svelte';
import { t } from '../i18n.svelte';
import { prefs } from '../prefs.svelte';
import type { Adventure, AdventureBlock, AdventureImport, AdventureSummary, EffectRef, MusicRef, PlaylistRef, ComposePiece, SmartFilter, SongRef, SoundDescription, SoundKind, Track } from '../types';
import { applyFilter } from './assistant.svelte';
import { effects, loadEffects } from './effects.svelte';
import { closeTab, library, openTab, setGlobal } from './library.svelte';
import { playEffect, playQueue } from './player.svelte';
import ImportAdventureDialog from '../../components/adventure/ImportAdventureDialog.svelte';
import { askConfirm, askText, errorToast, openDialog, toast } from './ui.svelte';

export const adventures = $state({
  list: [] as AdventureSummary[],
  loaded: false,
  current: null as Adventure | null,
  /** The block shown in the editor. */
  selected: null as string | null,
  mode: 'play' as 'edit' | 'play',
  /** The block of play mode and the blocks visited before it (for "back"). */
  playing: null as string | null,
  history: [] as string[],
  saving: false,
  /** "Search…" of a block's music: the whole library is shown, and the + of the song table adds a song to this block. */
  pickFor: null as { blockId: string } | null,
  /** Blocks (`adventureId/blockId`) whose cover is still being painted in the background (see applyCoverWhenReady). */
  pendingCovers: [] as string[],
  /** The import of an adventure book (PDF) that runs on the server, shown in the list of adventures until it is done. */
  /** The imports of adventure books (PDF) of the user, running and finished, with their logs: the progress popup shows them. */
  imports: [] as AdventureImport[],
  /** The words of the header search to mark in the notes of the block it went to (see goToBlock). */
  highlight: null as { blockId: string; terms: string[] } | null,
});

/** The block the song table adds songs to while its music is searched in the whole library. */
export function pickBlock(): AdventureBlock | null {
  const id = adventures.pickFor?.blockId;
  return (id && adventures.current?.editable && adventures.current.blocks.find((block) => block.id === id)) || null;
}

/** Searches the whole library for music of a block (with the filters, tags and search of the song table). */
export async function searchSongsForBlock(blockId: string) {
  adventures.pickFor = { blockId };
  await setGlobal(true);
}

/** "Suggest songs" of the AI dialog: the whole library opens for the block like "Search…", filtered and ranked by the choice of the
 *  smart search (sliders, tags, genres, BPM). */
export async function searchSongsWithFilter(blockId: string, chosen: SmartFilter) {
  await searchSongsForBlock(blockId);
  applyFilter(chosen);
}

/** Back from the search to the adventure; the search text was for the library and would filter the folders otherwise. */
export async function endSongSearch() {
  adventures.pickFor = null;
  library.search = '';
  await setGlobal(false);
}

/** The + of the song table: adds the song to the block it searches for, and to the adventure's music. */
export function addTrackToPickBlock(track: Track) {
  const block = pickBlock();
  if (!block) return;
  if (!track.ufid) {
    toast(t('This song has no stable id yet. Refresh the library first.'), 'error');
    return;
  }
  const ref: SongRef = { type: 'song', ufid: track.ufid, path: track.path, title: track.title || track.name };
  change((adventure) => assignMusic(adventure, block, ref));
}

export const pickBlockHas = (track: Track) => !!track.ufid && !!pickBlock()?.music.some((ref) => ref.type === 'song' && ref.ufid === track.ufid);

const SAVE_DELAY = 700;
let saveTimer: ReturnType<typeof setTimeout> | undefined;
let unsaved: Adventure | null = null; // the adventure with changes that are not saved yet
let inflight: Promise<void> | null = null; // the save that is running

const tabKey = (id: string) => `adventure:${id}`;

/** The tabs of adventures follow the list: renamed ones get the new title, deleted (or no longer visible) ones are closed. */
function syncTabs() {
  for (const tab of [...library.tabs]) {
    if (tab.type !== 'adventure') continue;
    const entry = adventures.list.find((item) => item.id === tab.path);
    if (entry) tab.name = entry.title;
    else closeTab(tab.key);
  }
}

export async function loadAdventures() {
  try {
    adventures.list = (await api.adventures()).adventures;
    adventures.loaded = true;
    syncTabs();
  } catch (e) {
    errorToast(e);
  }
}

/** Opens an adventure in its tab (the tab shows it, see Shell.svelte). */
export function openAdventureTab(id: string, title?: string) {
  const entry = adventures.list.find((item) => item.id === id);
  return openTab('adventure', id, true, false, title ?? entry?.title);
}

/** Loads the adventure of the active tab; it opens in play mode. */
export async function openAdventure(id: string) {
  await flushSave();
  try {
    const adventure = await api.adventure(id);
    adventures.current = adventure;
    adventures.selected = adventure.blocks[0]?.id ?? null;
    adventures.mode = 'play';
    adventures.playing = null;
    adventures.history = [];
    const tab = library.tabs.find((item) => item.key === tabKey(id));
    if (tab) tab.name = adventure.title;
  } catch (e) {
    errorToast(e);
    const tab = library.tabs.find((item) => item.key === tabKey(id));
    if (tab) closeTab(tab.key);
    void loadAdventures();
  }
}

/** Downloads an adventure as a ZIP file with its images and its book (the browser or the app asks where to save it). */
export function exportAdventure(id: string) {
  const link = document.createElement('a');
  link.href = adventureExportUrl(id);
  link.download = '';
  document.body.append(link);
  link.click();
  link.remove();
}

/** "Import from a file": the user picks an adventure file (ZIP). An adventure with the same id that exists already is only overwritten after a
 *  question (only its owner may; others can import it as a copy). */
export function importAdventureFile() {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.zip,application/zip';
  input.onchange = () => {
    const file = input.files?.[0];
    if (file) void importPackage(file);
  };
  input.click();
}

async function importPackage(file: File) {
  try {
    let result = await api.importAdventurePackage(file);
    if (result.status === 'exists') {
      if (result.editable) {
        if (!(await askConfirm(t('"{0}" exists already. Overwrite it?', result.title)))) return;
        await flushSave(); // a save that is waiting must not come after the new content
        result = await api.importAdventurePackage(file, { overwrite: true });
      } else {
        if (!(await askConfirm(t('"{0}" exists already and belongs to somebody else, so it cannot be overwritten. Import it as a copy?', result.title)))) return;
        result = await api.importAdventurePackage(file, { copy: true });
      }
    }
    await loadAdventures();
    if (adventures.current?.id === result.id) await openAdventure(result.id); // the open adventure shows the new content
    toast(result.overwritten ? t('"{0}" was overwritten.', result.title) : t('"{0}" was imported.', result.title), 'success');
    await openAdventureTab(result.id, result.title);
  } catch (e) {
    errorToast(e);
  }
}

/** Opens the book (PDF) the adventure was imported from, at `page`. The viewer is loaded when it is first needed. */
export async function openPdf(page = 1) {
  const adventure = adventures.current;
  if (!adventure?.pdf) {
    toast(t('This adventure has no PDF'), 'error');
    return;
  }
  const { default: PdfViewerDialog } = await import('../../components/dialogs/PdfViewerDialog.svelte');
  openDialog(PdfViewerDialog, { adventureId: adventure.id, title: adventure.pdf, page });
}

/** Lets the user choose a page of the book (PDF) of the current adventure in the viewer, for a link in the notes: the page, or null when
 *  the dialog is closed without a choice (or the adventure has no PDF). */
export async function pickPdfPage(): Promise<number | null> {
  const adventure = adventures.current;
  if (!adventure?.pdf) {
    toast(t('This adventure has no PDF'), 'error');
    return null;
  }
  const { default: PdfViewerDialog } = await import('../../components/dialogs/PdfViewerDialog.svelte');
  return new Promise((resolve) => openDialog(PdfViewerDialog, { adventureId: adventure.id, title: adventure.pdf, page: 1, onpick: resolve }));
}

const IMPORT_POLL_MS = 2000;

/** "Import from PDF": the AI (Gemini) reads an adventure book and makes a private adventure of it, one block per scene. It runs on the
 *  server for some minutes; the list of adventures shows how far it is, and the adventure opens when it is done. */
export function importAdventure() {
  openDialog(ImportAdventureDialog);
}

/** Starts the import of the chosen PDF; `detail` is how fine the AI splits the book into blocks and how much their notes hold. */
export async function startAdventureImport(file: File, detail: 'low' | 'medium' | 'high') {
  try {
    const job = await api.importAdventure(file, detail);
    startedHere.add(job.id);
    adventures.imports = [job, ...adventures.imports.filter((item) => item.id !== job.id)];
    watching.add(job.id);
    toast(t('The AI reads "{0}". This takes a few minutes; you can go on meanwhile.', file.name), 'info');
    openImportProgress();
    pollImports();
  } catch (e) {
    errorToast(e);
  }
}

// --- the imports: the server keeps them (and their logs) while they run, so they are found again after a reload

const startedHere = new Set<string>(); // imports started in this window: when one is done, its adventure opens
const watching = new Set<string>(); // imports that were running the last time we looked: their end is reported
let polling = false;
let progressOpen = false;

/** What an import does right now, in the language of the app. */
export const importStage = (job: AdventureImport) => (job.stageKey ? t(job.stageKey, ...job.stageArgs) : job.stage);

export const importsRunning = () => adventures.imports.some((job) => job.status === 'running');

/** Shows the progress popup with all imports (once; it stays until it is closed). */
export async function openImportProgress() {
  if (progressOpen) return;
  progressOpen = true;
  const { default: ImportProgressDialog } = await import('../../components/adventure/ImportProgressDialog.svelte');
  openDialog(ImportProgressDialog, { onclosed: () => (progressOpen = false) });
}

/** Loads the imports of the user; an import that ended since the last look is reported (and its adventure opens if it was started here). */
export async function refreshImports() {
  let jobs: AdventureImport[];
  try {
    jobs = (await api.adventureImports()).jobs;
  } catch {
    return; // the server is not reachable for the moment: the next look tries again
  }
  adventures.imports = jobs;
  for (const job of jobs) {
    if (job.status === 'running') {
      watching.add(job.id);
    } else if (watching.delete(job.id)) {
      if (job.status === 'error') {
        errorToast(new Error(t('The import of "{0}" failed: {1}', job.name, job.error ?? '')));
      } else if (job.status === 'cancelled') {
        toast(t('The import of "{0}" was cancelled.', job.name), 'info');
      } else {
        await loadAdventures();
        toast(t('"{0}" was imported. Check the blocks against the book.', job.name), 'success');
        if (job.adventure && startedHere.has(job.id)) await openAdventureTab(job.adventure);
      }
    }
  }
}

/** Looks at the imports every few seconds for as long as one is running. */
export function pollImports() {
  if (polling) return;
  polling = true;
  void (async () => {
    try {
      do {
        await new Promise((resolve) => setTimeout(resolve, IMPORT_POLL_MS));
        await refreshImports();
      } while (importsRunning());
    } finally {
      polling = false;
    }
  })();
}

/** After the start of the app (or a login): imports that are still running are shown in the progress popup. */
export async function restoreImports() {
  await refreshImports();
  if (importsRunning()) {
    openImportProgress();
    pollImports();
  }
}

/** Cancels a running import after a question. */
export async function cancelImport(job: AdventureImport) {
  if (!(await askConfirm(t('Cancel the import of "{0}"?', job.name)))) return;
  try {
    await api.cancelAdventureImport(job.id);
  } catch (e) {
    errorToast(e); // it may have ended in the meantime
  }
  await refreshImports();
}

export async function dismissImport(id: string) {
  try {
    await api.dismissAdventureImport(id);
    adventures.imports = adventures.imports.filter((job) => job.id !== id);
  } catch (e) {
    errorToast(e);
  }
}

export async function createAdventure() {
  const title = await askText(t('New adventure'), t('Title'), '');
  if (!title?.trim()) return;
  try {
    const adventure = await api.createAdventure(title.trim());
    await loadAdventures();
    await openAdventureTab(adventure.id, adventure.title);
  } catch (e) {
    errorToast(e);
  }
}

export async function renameAdventure(id: string) {
  const entry = adventures.list.find((item) => item.id === id);
  const current = adventures.current?.id === id ? adventures.current : null;
  const title = await askText(t('Rename'), t('Title'), current?.title ?? entry?.title ?? '');
  if (!title?.trim() || title.trim() === (current?.title ?? entry?.title)) return;
  try {
    if (current) {
      change((adventure) => (adventure.title = title.trim()));
      await flushSave();
    } else {
      const adventure = await api.adventure(id);
      await api.saveAdventure({ ...adventure, title: title.trim() });
    }
    await loadAdventures();
  } catch (e) {
    errorToast(e);
  }
}

export async function deleteAdventure(id: string, title: string) {
  if (!(await askConfirm(t('Delete the adventure "{0}"? This cannot be undone.', title)))) return;
  try {
    await api.deleteAdventure(id);
    if (unsaved?.id === id) unsaved = null; // nothing left to save
    if (adventures.current?.id === id) adventures.current = null;
    closeTab(tabKey(id));
    await loadAdventures();
  } catch (e) {
    errorToast(e);
  }
}

/** Switches an adventure between private and public; publishing one that refers to private playlists asks first. */
export async function toggleVisibility() {
  const adventure = adventures.current;
  if (!adventure?.editable) return;
  const target = adventure.visibility === 'public' ? 'private' : 'public';
  try {
    await flushSave();
    let result = await api.setAdventureVisibility(adventure.id, target);
    if (!result.changed) {
      const ok = await askConfirm(t('This adventure uses private playlists ({0}). Others will see them as unavailable. Publish anyway?', result.private_playlists.join(', ')));
      if (!ok) return;
      result = await api.setAdventureVisibility(adventure.id, target, true);
    }
    adventure.visibility = result.visibility;
    await loadAdventures();
  } catch (e) {
    errorToast(e);
  }
}

// --- editing ---------------------------------------------------------------

export const selectedBlock = (): AdventureBlock | null => adventures.current?.blocks.find((block) => block.id === adventures.selected) ?? null;

/** Applies a change to the open adventure (only its owner may) and saves it shortly after the last change. */
export function change(apply: (adventure: Adventure) => void) {
  const adventure = adventures.current;
  if (!adventure?.editable) return;
  apply(adventure);
  unsaved = adventure; // another adventure is opened only after flushSave (openAdventure), so its changes are saved by then
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => void flushSave(), SAVE_DELAY);
}

/** Assigns songs to an adventure (its own playlist) and, with `blockId`, to that block as well; returns how many were new to the
 *  adventure, or to the block. The open adventure is changed in place and autosaved, any other one is loaded, changed and saved. */
export async function addSongsToAdventure(adventureId: string, refs: MusicRef[], blockId?: string): Promise<number> {
  let added = 0;
  const addTo = (adventure: Adventure) => {
    const block = blockId ? adventure.blocks.find((item) => item.id === blockId) : null;
    if (blockId && !block) throw new Error(t('This block does not exist any more.'));
    for (const ref of refs) {
      const isNew = addAdventureMusic(adventure, ref);
      if (block ? addMusic(block, ref) : isNew) added++;
    }
  };
  if (adventures.current?.id === adventureId) {
    change(addTo);
  } else {
    const adventure = await api.adventure(adventureId);
    addTo(adventure);
    if (added) await api.saveAdventure(adventure);
  }
  void loadAdventures(); // the list is sorted by the last change
  return added;
}

/** Saves the changes now. It resolves once they are stored: a save that is running finishes first, changes made meanwhile are saved
 *  after it. What is saved is the adventure that was changed, also when another one is open by then. */
export async function flushSave() {
  clearTimeout(saveTimer);
  saveTimer = undefined;
  while (inflight) await inflight;
  const adventure = unsaved;
  if (!adventure) return;
  unsaved = null;
  inflight = save(adventure);
  try {
    await inflight;
  } finally {
    inflight = null;
  }
}

async function save(adventure: Adventure) {
  const { id, title, blocks, links, music } = $state.snapshot(adventure);
  adventures.saving = true;
  try {
    const saved = await api.saveAdventure({ id, title, blocks, links, music });
    adventure.updated = saved.updated;
    const entry = adventures.list.find((item) => item.id === id);
    if (entry) Object.assign(entry, { title: saved.title, blocks: saved.blocks.length, played: saved.blocks.filter((block) => block.played).length, updated: saved.updated });
  } catch (e) {
    unsaved ??= adventure; // tried again with the next save
    errorToast(e);
  } finally {
    adventures.saving = false;
  }
}

/** Adds a block at the end of the list, linked from the block that was last (the link can be changed afterwards). */
export function addBlock(title = t('New block')) {
  change((adventure) => {
    adventures.selected = appendBlock(adventure, title).id;
  });
}

export function deleteBlock(id: string) {
  change((adventure) => {
    const next = removeBlock(adventure, id);
    if (adventures.selected === id) adventures.selected = next;
    if (adventures.playing === id) adventures.playing = null;
  });
}

export function setPlayed(id: string, played: boolean) {
  change((adventure) => {
    const block = adventure.blocks.find((item) => item.id === id);
    if (block) block.played = played;
  });
}

// --- playing a block -------------------------------------------------------

async function resolveSong(ref: SongRef): Promise<Track | null> {
  try {
    return await api.track((await api.resolve('song', ref.ufid)).id);
  } catch { /* moved out of the library or unknown: try the last known path */ }
  if (ref.path) {
    try {
      return await api.track(pathToId(ref.path));
    } catch { /* gone */ }
  }
  return null;
}

async function resolvePlaylist(ref: PlaylistRef): Promise<Track[] | null> {
  if (ref.unavailable) return null;
  try {
    const found = await api.resolve('playlist', ref.id);
    return (await api.tracksOfPlaylist(found.path)).tracks;
  } catch {
    return null;
  }
}

/** Plays the song of a link in the notes (found by its stable id). */
export async function playSongLink(ufid: string) {
  const track = await resolveSong({ type: 'song', ufid, path: '', title: '' });
  if (track) await playQueue([track]);
  else toast(t('This song was not found in the library.'), 'error');
}

/** The songs of one reference of a block; null if it cannot be found (or may not be seen). */
export async function refTracks(ref: MusicRef): Promise<Track[] | null> {
  if (ref.type === 'playlist') return resolvePlaylist(ref);
  const track = await resolveSong(ref);
  return track ? [track] : null;
}

/** Plays the music of a block in the player (the options of the player decide about shuffle and repeat). */
export async function playBlockMusic(block: AdventureBlock) {
  const tracks: Track[] = [];
  let missing = 0;
  for (const ref of block.music) {
    const found = await refTracks(ref);
    if (found) tracks.push(...found);
    else missing++;
  }
  if (missing) toast(t('{0} song(s) or playlist(s) of this block are not available.', missing), 'error');
  // the first song of the block starts (it is marked in the editor); shuffle only decides what follows
  if (tracks.length) await playQueue(tracks, undefined, 0);
}

export async function startEffect(ref: EffectRef) {
  if (!effects.list.length) await loadEffects();
  const effect = effects.list.find((item) => item.path === ref.path);
  if (!effect) {
    toast(t('Effect "{0}" was not found.', ref.name || ref.path), 'error');
    return;
  }
  prefs.effectsLoop = ref.loop; // for this effect; the saved preference is not changed
  playEffect(effect);
}

/** The key of an effect of a block in `missingEntries` (songs and playlists use `refKey`). */
export const effectKey = (ref: EffectRef) => `effect:${ref.path}`;

async function songExists(ufid: string, path = ''): Promise<boolean> {
  try {
    await api.resolve('song', ufid);
    return true;
  } catch { /* not under its id: perhaps still at its last known path */ }
  if (!path) return false;
  try {
    await api.track(pathToId(path));
    return true;
  } catch {
    return false;
  }
}

/** The songs and playlists of `refs` that can no longer be found, added to `missing` as `refKey` keys (a few checks at a time:
 *  the music of an adventure can be long). */
export async function missingMusic(refs: MusicRef[], missing = new Set<string>()): Promise<Set<string>> {
  const queue = [...refs];
  const worker = async () => {
    for (let ref = queue.shift(); ref; ref = queue.shift()) {
      const found = ref.type === 'song' ? await songExists(ref.ufid, ref.path)
        : !ref.unavailable && await api.resolve('playlist', ref.id).then(() => true, () => false);
      if (!found) missing.add(refKey(ref));
    }
  };
  await Promise.all(Array.from({ length: 6 }, worker));
  return missing;
}

/** What a block holds that can no longer be found (deleted, moved out of the library, a playlist that may not be seen, an effect
 *  that is not in the effects folder), as `refKey`/`effectKey` keys; `songs` are the ids of song links in its notes. */
/** The songs, playlists and effects of `block` (and the songs `songs` its notes link to) that can no longer be found. Nothing it reads
 *  is tracked: an effect that calls it re-runs only for what it reads itself (loading the effects would otherwise start it again). */
export function missingEntries(block: AdventureBlock, songs: string[] = []): Promise<Set<string>> {
  return untrack(() => findMissing(block, songs));
}

async function findMissing(block: AdventureBlock, songs: string[]): Promise<Set<string>> {
  const missing = new Set<string>();
  const checks: Promise<unknown>[] = [missingMusic(block.music, missing)];
  for (const ufid of new Set(songs)) checks.push(songExists(ufid).then((found) => { if (!found) missing.add(`song:${ufid}`); }));
  if (block.effects.length) {
    checks.push((async () => {
      if (!effects.list.length) await loadEffects();
      for (const ref of block.effects) if (!effects.list.some((item) => item.path === ref.path)) missing.add(effectKey(ref));
    })());
  }
  await Promise.all(checks);
  return missing;
}

/** Shows a block in play mode and starts what it holds: music (unless the block does not autoplay), and effects that start by themselves. */
export async function enterBlock(id: string, remember = true) {
  const adventure = adventures.current;
  const block = adventure?.blocks.find((item) => item.id === id);
  if (!adventure || !block) return;
  if (remember && adventures.playing && adventures.playing !== id) adventures.history.push(adventures.playing);
  adventures.playing = id;
  adventures.selected = id; // "Edit" opens the block the game is at
  adventures.mode = 'play';
  for (const effect of block.effects) if (effect.autostart) void startEffect(effect);
  if (block.autoplay && block.music.length) await playBlockMusic(block);
}

/** "Play" of the header: play mode shows the block chosen in the editor, without starting its music or effects (the game master
 *  starts them when the scene begins). The block shown before goes into the history for "back". */
export function switchToPlay() {
  const id = adventures.selected;
  if (id && id !== adventures.playing && adventures.current?.blocks.some((block) => block.id === id)) {
    if (adventures.playing) adventures.history.push(adventures.playing);
    adventures.playing = id;
  }
  adventures.mode = 'play';
}

/** "Apply" of the cover dialog: the picture being painted (`painting`) becomes the cover of the block as soon as it is done, while
 *  the game master works on. The open adventure is changed in place, another one is loaded, changed and saved; a toast tells when
 *  it is done. `pendingCovers` marks the blocks that wait for their picture. */
export async function applyCoverWhenReady(adventureId: string, blockId: string, painting: Promise<{ name: string }>) {
  const key = `${adventureId}/${blockId}`;
  adventures.pendingCovers = [...adventures.pendingCovers, key];
  try {
    const { name } = await painting;
    const setCover = (adventure: Adventure) => {
      const block = adventure.blocks.find((item) => item.id === blockId);
      if (!block) throw new Error(t('This block does not exist any more.'));
      block.cover = name;
      return block.title;
    };
    let title = '';
    if (adventures.current?.id === adventureId) {
      change((adventure) => (title = setCover(adventure)));
    } else {
      const adventure = await api.adventure(adventureId);
      title = setCover(adventure);
      await api.saveAdventure(adventure);
    }
    toast(t('The cover image of "{0}" is ready.', title || t('Untitled')), 'success');
  } catch (e) {
    errorToast(e);
  } finally {
    adventures.pendingCovers = adventures.pendingCovers.filter((item) => item !== key);
  }
}

/** Deletes the images no block uses any more, in all blocks of the open adventure. */
export async function cleanUpImages() {
  const adventure = adventures.current;
  if (!adventure?.editable) return;
  try {
    await flushSave(); // the server looks at the saved notes
    const { removed } = await api.cleanupAdventureImages(adventure.id);
    toast(t('{0} unused image(s) removed.', removed));
  } catch (e) {
    errorToast(e);
  }
}

/** Deletes the selected block after a question. */
export async function askDeleteBlock() {
  const block = selectedBlock();
  if (block && (await askConfirm(t('Delete the block "{0}"?', block.title || t('Untitled'))))) deleteBlock(block.id);
}

/** Paints a cover for every block of the open adventure that has none: the assistant describes the block (title and notes) as a picture,
 *  the image generation paints it. One after the other (the generator is a single service that has to start first); the blocks wait
 *  with their cover pending, and every cover is set as soon as it is done. */
export async function generateCovers() {
  const adventure = adventures.current;
  if (!adventure?.editable) return;
  const todo = adventure.blocks.filter((block) => !block.cover && !coverPending(adventure.id, block.id) && blockPrompt(block));
  if (!todo.length) {
    toast(t('Every block has a cover image already.'));
    return;
  }
  if (!(await askConfirm(t('Paint a cover image for {0} block(s) with AI? This takes a while; it runs in the background.', todo.length)))) return;
  const described = !!(data.settings?.groqConfigured || data.settings?.assistantConfigured);
  const keys = todo.map((block) => `${adventure.id}/${block.id}`);
  adventures.pendingCovers = [...adventures.pendingCovers, ...keys];
  toast(t('The cover images are painted in the background.'), 'info');
  for (const block of todo) {
    const scene = `Adventure: ${adventure.title}\n\n${blockPrompt(block)}`;
    const painting = (async () => {
      let text = scene;
      if (described) {
        try {
          text = (await api.assistantChat([{ role: 'user', content: scene }], 'image')).caption?.trim() || scene;
        } catch {
          // the notes themselves are the description
        }
      }
      return api.generateAdventureImage(adventure.id, text, 'landscape');
    })();
    await applyCoverWhenReady(adventure.id, block.id, painting);
  }
}

export const coverPending = (adventureId: string, blockId: string) => adventures.pendingCovers.includes(`${adventureId}/${blockId}`);

/** Adds a sound of the sound generation to a block: music to its songs (and to the music of the adventure), an effect or an ambience
 *  (looped) to its effects. The open adventure is changed in place, another one is loaded, changed and saved. */
async function addSoundToBlock(adventureId: string, blockId: string, kind: SoundKind, track: Track, title: string) {
  const addTo = (adventure: Adventure) => {
    const block = adventure.blocks.find((item) => item.id === blockId);
    if (!block) throw new Error(t('This block does not exist any more.'));
    if (kind === 'music') {
      if (track.ufid) assignMusic(adventure, block, { type: 'song', ufid: track.ufid, path: track.path, title });
    } else if (!block.effects.some((item) => item.path === track.path)) {
      block.effects.push({ path: track.path, name: title, loop: kind === 'ambience', autostart: false });
    }
  };
  if (kind !== 'music') await loadEffects();
  if (adventures.current?.id === adventureId) {
    change(addTo);
  } else {
    const adventure = await api.adventure(adventureId);
    addTo(adventure);
    await api.saveAdventure(adventure);
  }
}

/** What the AI of a block generates: a piece of the music generation (ACE-Step) or a sound of the sound generation (Stable Audio),
 *  with the length and the folder of the options of the create mode (see components/CreateOptions.svelte). */
export type BlockCreation =
  | { kind: 'song'; piece: ComposePiece; dir: string; duration: number }
  | { kind: SoundKind; sound: SoundDescription; dir: string; duration: number };

/** Generates a piece or a sound into its folder and adds it to the block with a toast. It also finishes when the dialog that started
 *  it is closed ("Apply" of the AI dialog), so it works with ids only. */
export async function createForBlock(adventureId: string, blockId: string, job: BlockCreation): Promise<Track> {
  const { track } = job.kind === 'song'
    ? await api.compose({ ...job.piece, dir: job.dir, duration: job.duration })
    : await api.sound({ ...job.sound, kind: job.kind, duration: job.duration || job.sound.duration, dir: job.dir });
  const title = (job.kind === 'song' ? job.piece.title : job.sound.title).trim() || track.title || track.name;
  await addSoundToBlock(adventureId, blockId, job.kind === 'song' ? 'music' : job.kind, track, title);
  toast(t('"{0}" is ready and was added to the block.', title), 'success');
  return track;
}

/** Goes to a block found with the search of the header: the editor shows it, play mode enters it (with its music). The words of
 *  the search are marked in its notes (the view that shows them takes `adventures.highlight` and clears it). */
export function goToBlock(id: string, terms: string[] = []) {
  adventures.highlight = terms.length ? { blockId: id, terms } : null;
  if (adventures.mode === 'play') void enterBlock(id);
  else adventures.selected = id;
}

export function previousBlock() {
  const id = adventures.history.pop();
  if (id) void enterBlock(id, false);
}
