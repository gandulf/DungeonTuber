// The open adventure: editing (autosaved), the path through its blocks in play mode and what a block starts (music, effects).
// Adventures are tabs next to folders and playlists (see stores/library.svelte.ts); the one of the active tab is `adventures.current`.
import { api, pathToId } from '../api';
import { addAdventureMusic, addMusic, appendBlock, assignMusic, removeBlock } from '../adventures';
import { t } from '../i18n.svelte';
import { prefs } from '../prefs.svelte';
import type { Adventure, AdventureBlock, AdventureSummary, EffectRef, MusicRef, PlaylistRef, SongRef, Track } from '../types';
import { effects, loadEffects } from './effects.svelte';
import { closeTab, library, openTab, setGlobal } from './library.svelte';
import { playEffect, playQueue } from './player.svelte';
import { askConfirm, askText, errorToast, toast } from './ui.svelte';

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

export async function flushSave() {
  clearTimeout(saveTimer);
  saveTimer = undefined;
  const adventure = adventures.current;
  if (!adventure?.editable) return;
  if (adventures.saving) {
    saveTimer = setTimeout(() => void flushSave(), SAVE_DELAY); // a save is running: this one follows
    return;
  }
  const { id, title, blocks, links, music } = $state.snapshot(adventure);
  adventures.saving = true;
  try {
    const saved = await api.saveAdventure({ id, title, blocks, links, music });
    adventure.updated = saved.updated;
    const entry = adventures.list.find((item) => item.id === id);
    if (entry) Object.assign(entry, { title: saved.title, blocks: saved.blocks.length, played: saved.blocks.filter((block) => block.played).length, updated: saved.updated });
  } catch (e) {
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

/** Shows a block in play mode and starts what it holds: music (unless the block does not autoplay), and effects that start by themselves. */
export async function enterBlock(id: string, remember = true) {
  const adventure = adventures.current;
  const block = adventure?.blocks.find((item) => item.id === id);
  if (!adventure || !block) return;
  if (remember && adventures.playing && adventures.playing !== id) adventures.history.push(adventures.playing);
  adventures.playing = id;
  adventures.mode = 'play';
  for (const effect of block.effects) if (effect.autostart) void startEffect(effect);
  if (block.autoplay && block.music.length) await playBlockMusic(block);
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

export const coverPending = (adventureId: string, blockId: string) => adventures.pendingCovers.includes(`${adventureId}/${blockId}`);

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
