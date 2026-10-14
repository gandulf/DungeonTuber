// Open song tabs (folders / playlists), their tracks and the shared filter.
import { api } from '../api';
import { cached } from '../cache';
import { findDuplicates, type DuplicateKind } from '../duplicates';
import { t } from '../i18n.svelte';
import { prefs, savePrefs } from '../prefs.svelte';
import { data } from './data.svelte';
import { calculateScore, emptyFilter } from '../scoring';
import { matcher, ranker } from '../search';
import { displayTags, tagNames } from '../tags';
import type { FilterConfig, Track } from '../types';
import { errorToast, toast } from './ui.svelte';

export interface Tab {
  key: string;
  type: 'dir' | 'playlist';
  path: string;
  name: string;
  tracks: Track[];
  loaded: boolean;
  loading: boolean;
  error: string | null;
  /** Playlists only: private (visible to its creator alone) and who created it. */
  private?: boolean;
  owner?: string | null;
  /** The whole library of the global search (see globalTab), not a folder or playlist. */
  global?: boolean;
  /** The songs that exist more than once in the library (see duplicatesTab). */
  duplicates?: boolean;
}

export type SortKey = string; // 'index' | 'name' | 'score' | 'bpm' | 'genre' | 'artist' | 'album' | 'favorite' | 'cat:<key>'

export const library = $state({
  tabs: [] as Tab[],
  active: null as string | null,
  search: '',
  sortKey: 'name' as SortKey,
  sortAsc: true,
  selection: [] as string[], // track ids
  /** The search covers the whole library (the best GLOBAL_LIMIT songs) instead of the open tab. */
  global: false,
  /** The table shows the songs that exist more than once in the library. */
  duplicates: false,
});

/** How many songs the global search shows. */
export const GLOBAL_LIMIT = 50;

/** All songs of the library for the global search; loaded when it is switched on. */
export const globalTab: Tab = $state({
  key: 'global', type: 'dir', path: '', name: '', tracks: [], loaded: false, loading: false, error: null, global: true,
});

/** The duplicates among the songs of the whole library; computed from globalTab (which is loaded when the duplicates are shown). */
export const duplicatesTab: Tab = $state({
  key: 'duplicates', type: 'dir', path: '', name: '', tracks: [], loaded: false, loading: false, error: null, duplicates: true,
});

/** Track id -> its group of duplicates (sorting by 'duplicate' keeps a group together), and how many groups there are. */
export const duplicateInfo = $state({
  groups: {} as Record<string, string>,
  kinds: {} as Record<string, DuplicateKind>,
  groupCount: 0,
  /** Groups of songs with identical files, found by the server; the songs with the same artist and title are found in the browser. */
  exact: [] as string[][],
  /** The server is still comparing the contents of the files. */
  comparing: false,
});

$effect.root(() => {
  $effect(() => {
    const result = findDuplicates(globalTab.tracks, duplicateInfo.exact);
    duplicatesTab.tracks = result.tracks;
    duplicateInfo.groups = result.groups;
    duplicateInfo.kinds = result.kinds;
    duplicateInfo.groupCount = result.groupCount;
  });
  $effect(() => {
    duplicatesTab.loading = globalTab.loading;
    duplicatesTab.loaded = globalTab.loaded;
    duplicatesTab.error = globalTab.error;
  });
});

export const filter: FilterConfig = $state({ categories: {}, tags: [], genres: [], bpm: null });

const tabKey = (type: string, path: string) => `${type}:${path}`;

export function activeTab(): Tab | null {
  if (library.duplicates) return duplicatesTab;
  if (library.global) return globalTab;
  return library.tabs.find((tab) => tab.key === library.active) ?? null;
}

/** Loads the songs of the whole library (again with `force`, e.g. after a change of the library). */
export async function loadGlobal(force = false) {
  if (globalTab.loading || (globalTab.loaded && !force)) return;
  globalTab.loading = true;
  globalTab.error = null;
  try {
    await cached('tracks:library', () => api.libraryTracks(), (result) => {
      globalTab.tracks = result.tracks;
      globalTab.loaded = true;
    });
  } catch (e) {
    globalTab.error = e instanceof Error ? e.message : String(e);
  } finally {
    globalTab.loading = false;
  }
}

/** Shows every song that exists more than once in the library in the table, the duplicates of a song next to each other. */
export async function showDuplicates() {
  library.duplicates = true;
  library.global = false;
  library.selection = [];
  library.search = '';
  library.sortKey = 'duplicate';
  library.sortAsc = true;
  duplicatesTab.name = t('Duplicates');
  duplicateInfo.exact = [];
  await loadGlobal(true); // the library may have changed since it was loaded
  // the songs with the same title show up right away; the files with the same content follow once the server has compared them
  duplicateInfo.comparing = true;
  try {
    duplicateInfo.exact = (await api.libraryDuplicates()).groups;
  } catch (e) {
    errorToast(e);
  } finally {
    duplicateInfo.comparing = false;
  }
}

/** Leaves the duplicates for the tab that was open before. */
export function closeDuplicates() {
  library.duplicates = false;
  library.selection = [];
  const tab = activeTab();
  if (tab && library.sortKey === 'duplicate') library.sortKey = tab.type === 'playlist' ? 'index' : 'name';
  library.sortAsc = library.sortKey !== 'score';
}

/** Switches the search across the whole library on or off. */
export async function setGlobal(on: boolean) {
  library.global = on;
  library.duplicates = false;
  library.selection = [];
  globalTab.name = t('Whole library');
  if (on) {
    if (library.sortKey === 'duplicate') library.sortKey = 'name';
    if (!emptyFilter(filter)) {
      library.sortKey = 'score';
      library.sortAsc = false;
    }
    await loadGlobal();
  } else {
    const tab = activeTab();
    if (tab && library.sortKey !== 'score') library.sortKey = tab.type === 'playlist' ? 'index' : 'name';
  }
}

let globalTimer: ReturnType<typeof setTimeout> | undefined;

/** The library changed: the songs of the global search are loaded again (once for many changes, e.g. during an import). */
export function globalChanged() {
  if (!globalTab.loaded) return;
  clearTimeout(globalTimer);
  globalTimer = setTimeout(() => void loadGlobal(true), 500);
}

let persistTimer: ReturnType<typeof setTimeout> | undefined;

/** The open tabs belong to the signed in user and are kept on the server. */
function persistTabs() {
  const tabs = { open: library.tabs.map((tab) => ({ type: tab.type, path: tab.path })), active: library.active };
  data.user.tabs = tabs;
  clearTimeout(persistTimer);
  persistTimer = setTimeout(() => void api.putUserState({ tabs }).catch(() => undefined), 400);
}

export async function openTab(type: 'dir' | 'playlist', path: string, activate = true, lazy = false) {
  const key = tabKey(type, path);
  const existing = library.tabs.find((tab) => tab.key === key);
  if (existing) {
    if (activate) selectTab(key);
    return existing;
  }
  const name = path.split('/').filter(Boolean).pop()?.replace(/\.m3u$/i, '') ?? path;
  if (type === 'dir') {
    prefs.treeRoot = path; // the default target for new playlists and uploads
    savePrefs();
  }
  library.tabs.push({ key, type, path, name, tracks: [], loaded: false, loading: false, error: null });
  if (activate) selectTab(key);
  else if (!lazy) void loadTab(key);
  persistTabs();
  return library.tabs.find((tab) => tab.key === key)!;
}

export async function loadTab(key: string, force = false) {
  const tab = library.tabs.find((t) => t.key === key);
  if (!tab || tab.loading || (tab.loaded && !force)) return;
  tab.loading = true;
  tab.error = null;
  try {
    // the cached songs show at once, the current ones replace them when they differ
    await cached(`tracks:${tab.key}`, () => (tab.type === 'dir' ? api.tracksOfDir(tab.path) : api.tracksOfPlaylist(tab.path)), (result) => {
      tab.tracks = result.tracks;
      tab.name = result.name || tab.name;
      tab.private = result.private;
      tab.owner = result.uploaded_by;
      tab.loaded = true;
    });
  } catch (e) {
    tab.error = e instanceof Error ? e.message : String(e);
  } finally {
    tab.loading = false;
  }
}

export function selectTab(key: string) {
  library.global = false; // picking a folder or playlist leaves the global search and the duplicates
  library.duplicates = false;
  library.active = key;
  library.selection = [];
  library.search = '';
  const tab = activeTab();
  if (tab) {
    library.sortKey = tab.type === 'playlist' ? 'index' : emptyFilter(filter) ? 'name' : 'score';
    library.sortAsc = library.sortKey !== 'score';
  }
  void loadTab(key);
  persistTabs();
}

export function closeTab(key: string) {
  const index = library.tabs.findIndex((tab) => tab.key === key);
  if (index < 0) return;
  library.tabs.splice(index, 1);
  if (library.active === key) {
    const next = library.tabs[Math.min(index, library.tabs.length - 1)];
    library.active = next?.key ?? null;
    if (next) void loadTab(next.key);
  }
  persistTabs();
}

export function closeOtherTabs(key: string) {
  library.tabs = library.tabs.filter((tab) => tab.key === key);
  library.active = key;
  persistTabs();
}

export function closeAllTabs() {
  library.tabs = [];
  library.active = null;
  persistTabs();
}

export function moveTab(from: number, to: number) {
  const [tab] = library.tabs.splice(from, 1);
  library.tabs.splice(to, 0, tab);
  persistTabs();
}

export function restoreTabs() {
  // tabs saved in this browser before they were kept per user are used once
  const saved = data.user.tabs ?? { open: prefs.openTabs, active: prefs.activeTab };
  for (const tab of saved.open) void openTab(tab.type, tab.path, false, true);
  const active = saved.active && library.tabs.some((tab) => tab.key === saved.active) ? saved.active : library.tabs[0]?.key;
  if (active) selectTab(active);
}

/** Replaces a track in every open tab (after edits / analysis). */
export function updateTrack(track: Track) {
  const previous = track.previous_id ?? track.id;
  for (const tab of [...library.tabs, globalTab]) {
    const index = tab.tracks.findIndex((t) => t.id === previous || t.id === track.id);
    // events carry no favorite: it is personal and stays as it is
    if (index >= 0) tab.tracks[index] = { ...track, favorite: track.favorite ?? tab.tracks[index].favorite, index: tab.tracks[index].index, scene: tab.tracks[index].scene };
  }
  if (previous !== track.id) library.selection = library.selection.map((id) => (id === previous ? track.id : id));
}

export function reloadPlaylistTabs(path: string) {
  for (const tab of library.tabs) if (tab.type === 'playlist' && tab.path === path) void loadTab(tab.key, true);
}

export function reloadDirTabs(path: string) {
  for (const tab of library.tabs) if (tab.type === 'dir' && (path === tab.path || path.startsWith(tab.path + '/'))) void loadTab(tab.key, true);
}

export function reloadAllDirTabs() {
  for (const tab of library.tabs) if (tab.type === 'dir') void loadTab(tab.key, true);
}

// --- derived list -----------------------------------------------------------

export interface Row {
  track: Track;
  score: number | null;
}

function sortValue(row: Row, key: SortKey, playlist: boolean): string | number | boolean | null {
  const track = row.track;
  switch (key) {
    case 'index': return playlist ? (track.index ?? 0) : (track.track ?? null); // folders show the track number in the # column
    case 'name': return (track.scene || (prefs.titleInsteadOfFile && track.title ? track.title : track.name)).toLowerCase();
    case 'title': return (track.title ?? '').toLowerCase();
    case 'score': return row.score === null ? null : -row.score; // the column shows a match in percent: ascending = worst first
    case 'bpm': return track.bpm;
    case 'track': return track.track ?? null;
    case 'genre': return track.genres.join(', ').toLowerCase();
    case 'artist': return (track.artist ?? '').toLowerCase();
    case 'album': return (track.album ?? '').toLowerCase();
    case 'summary': return (track.summary ?? '').toLowerCase();
    case 'favorite': return track.favorite ? 0 : 1;
    case 'duplicate': return duplicateInfo.groups[track.id] ?? null;
    case 'length': return track.length;
    default:
      if (key.startsWith('cat:')) return track.categories[key.slice(4)] ?? null;
      return null;
  }
}

/** The text of a song that the search looks at. */
const searchText = (track: Track) =>
  `${track.scene ?? ''} ${track.name} ${track.title ?? ''} ${track.artist ?? ''} ${track.album ?? ''} ${track.summary ?? ''} ${track.tags.join(' ')}`;

/** Whether the search would find anything in the open tab. */
export function findsInTab(query: string): boolean {
  if (library.global && !globalTab.loaded) return false;
  const matches = matcher(query);
  return !!activeTab()?.tracks.some((track) => matches(searchText(track)));
}

/** The best GLOBAL_LIMIT songs of the whole library: by the search (the whole query in the title first), then by the filter.
 *  Without a search and a filter nothing is shown, the library is too large to list. */
function bestOfLibrary(rows: Row[]): Row[] {
  const query = library.search.trim();
  const filtering = !emptyFilter(filter);
  if (!query && !filtering) return [];
  const rank = ranker(query);
  const titleRank = ranker(query);
  const ranked = rows
    .map((row) => {
      const text = rank(searchText(row.track));
      if (text === null) return null;
      const inTitle = query ? titleRank(`${row.track.title ?? ''} ${row.track.name}`) === 0 : true;
      return { row, text: query ? text * 2 + (inTitle ? 0 : 1) : 0 };
    })
    .filter((entry): entry is { row: Row; text: number } => entry !== null);
  ranked.sort((a, b) => a.text - b.text || (filtering ? (a.row.score ?? Infinity) - (b.row.score ?? Infinity) : 0));
  return ranked.slice(0, GLOBAL_LIMIT).map((entry) => entry.row);
}

export function visibleRows(): Row[] {
  const tab = activeTab();
  if (!tab) return [];
  let rows: Row[] = tab.tracks.map((track) => ({ track, score: calculateScore(track, filter) }));
  if (tab.global) {
    rows = bestOfLibrary(rows);
  } else if (library.search.trim()) {
    const matches = matcher(library.search);
    rows = rows.filter(({ track }) => matches(searchText(track)));
  }
  const key = library.sortKey;
  const direction = library.sortAsc ? 1 : -1;
  const playlist = tab.type === 'playlist';
  return rows.sort((a, b) => {
    const va = sortValue(a, key, playlist);
    const vb = sortValue(b, key, playlist);
    if (va === vb) return 0;
    if (va === null || va === undefined) return 1; // missing values last
    if (vb === null || vb === undefined) return -1;
    return (va < vb ? -1 : 1) * direction;
  });
}

export function setSort(key: SortKey) {
  if (library.sortKey === key) library.sortAsc = !library.sortAsc;
  else {
    library.sortKey = key;
    library.sortAsc = key !== 'score'; // best match first
  }
}

/** Called when the filter changes: like the desktop app, sort by score. */
export function onFilterChanged() {
  if (!emptyFilter(filter)) {
    library.sortKey = 'score';
    library.sortAsc = false;
  } else if (library.sortKey === 'score') {
    library.sortKey = activeTab()?.type === 'playlist' ? 'index' : 'name';
  }
}

/** The tags of the songs in the open tab, "Pop" and "pop" listed once, in the same spelling as in the table. */
export function availableTags(): string[] {
  return displayTags((activeTab()?.tracks ?? []).flatMap((track) => track.tags), tabTagNames()).sort((a, b) => a.localeCompare(b));
}

export function availableGenres(): string[] {
  return displayTags((activeTab()?.tracks ?? []).flatMap((track) => track.genres), tabTagNames()).sort((a, b) => a.localeCompare(b));
}

/** The spelling to show for every tag and genre of the open tab (see tags.ts). */
export function tabTagNames(): Map<string, string> {
  return tagNames((activeTab()?.tracks ?? []).flatMap((track) => [track.tags, track.genres]));
}

export function extraCategoryKeys(known: string[]): string[] {
  const keys = new Set<string>();
  activeTab()?.tracks.forEach((track) => Object.keys(track.categories).forEach((key) => !known.includes(key) && keys.add(key)));
  return [...keys].sort();
}

// --- playlist helpers ---------------------------------------------------------

export async function addToPlaylist(playlist: string, ids: string[], index = -1) {
  try {
    const { added } = await api.addToPlaylist(playlist, ids, index);
    if (added) {
      reloadPlaylistTabs(playlist);
      toast(t('Add to playlist') + ' ✓', 'success');
    } else toast(t('Already in the playlist'));
  } catch (e) {
    errorToast(e);
  }
}

export async function removeFromPlaylist(playlist: string, ids: string[]) {
  try {
    await api.removeFromPlaylist(playlist, ids);
    reloadPlaylistTabs(playlist);
  } catch (e) {
    errorToast(e);
  }
}

export async function reorderPlaylist(tab: Tab, ids: string[]) {
  const byId = new Map(tab.tracks.map((track) => [track.id, track]));
  tab.tracks = ids.map((id, index) => ({ ...byId.get(id)!, index }));
  try {
    await api.reorderPlaylist(tab.path, ids);
  } catch (e) {
    errorToast(e);
    void loadTab(tab.key, true);
  }
}
