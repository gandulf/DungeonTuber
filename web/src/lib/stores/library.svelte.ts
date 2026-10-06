// Open song tabs (folders / playlists), their tracks and the shared filter.
import { api } from '../api';
import { t } from '../i18n.svelte';
import { prefs, savePrefs } from '../prefs.svelte';
import { data } from './data.svelte';
import { calculateScore, emptyFilter } from '../scoring';
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
}

export type SortKey = string; // 'index' | 'name' | 'score' | 'bpm' | 'genre' | 'artist' | 'album' | 'favorite' | 'cat:<key>'

export const library = $state({
  tabs: [] as Tab[],
  active: null as string | null,
  search: '',
  sortKey: 'name' as SortKey,
  sortAsc: true,
  selection: [] as string[], // track ids
});

export const filter: FilterConfig = $state({ categories: {}, tags: [], genres: [], bpm: null });

const tabKey = (type: string, path: string) => `${type}:${path}`;

export function activeTab(): Tab | null {
  return library.tabs.find((tab) => tab.key === library.active) ?? null;
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
    const result = tab.type === 'dir' ? await api.tracksOfDir(tab.path) : await api.tracksOfPlaylist(tab.path);
    tab.tracks = result.tracks;
    tab.name = result.name || tab.name;
    tab.loaded = true;
  } catch (e) {
    tab.error = e instanceof Error ? e.message : String(e);
  } finally {
    tab.loading = false;
  }
}

export function selectTab(key: string) {
  library.active = key;
  library.selection = [];
  library.search = '';
  const tab = activeTab();
  if (tab) {
    library.sortKey = tab.type === 'playlist' ? 'index' : emptyFilter(filter) ? 'name' : 'score';
    library.sortAsc = true;
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
  for (const tab of library.tabs) {
    const index = tab.tracks.findIndex((t) => t.id === previous || t.id === track.id);
    // events carry no favorite: it is personal and stays as it is
    if (index >= 0) tab.tracks[index] = { ...track, favorite: track.favorite ?? tab.tracks[index].favorite, index: tab.tracks[index].index };
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

function sortValue(row: Row, key: SortKey): string | number | boolean | null {
  const track = row.track;
  switch (key) {
    case 'index': return track.index ?? 0;
    case 'name': return (prefs.titleInsteadOfFile && track.title ? track.title : track.name).toLowerCase();
    case 'title': return (track.title ?? '').toLowerCase();
    case 'score': return row.score;
    case 'bpm': return track.bpm;
    case 'genre': return track.genres.join(', ').toLowerCase();
    case 'artist': return (track.artist ?? '').toLowerCase();
    case 'album': return (track.album ?? '').toLowerCase();
    case 'summary': return (track.summary ?? '').toLowerCase();
    case 'favorite': return track.favorite ? 0 : 1;
    case 'length': return track.length;
    default:
      if (key.startsWith('cat:')) return track.categories[key.slice(4)] ?? null;
      return null;
  }
}

export function visibleRows(): Row[] {
  const tab = activeTab();
  if (!tab) return [];
  const search = library.search.trim().toLowerCase();
  let rows: Row[] = tab.tracks.map((track) => ({ track, score: calculateScore(track, filter) }));
  if (search) {
    rows = rows.filter(({ track }) => `${track.name} ${track.title ?? ''} ${track.summary ?? ''} ${track.tags.join(' ')}`.toLowerCase().includes(search));
  }
  const key = library.sortKey;
  const direction = library.sortAsc ? 1 : -1;
  return rows.sort((a, b) => {
    const va = sortValue(a, key);
    const vb = sortValue(b, key);
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
    library.sortAsc = key !== 'favorite' ? true : true;
  }
}

/** Called when the filter changes: like the desktop app, sort by score. */
export function onFilterChanged() {
  if (!emptyFilter(filter)) {
    library.sortKey = 'score';
    library.sortAsc = true;
  } else if (library.sortKey === 'score') {
    library.sortKey = activeTab()?.type === 'playlist' ? 'index' : 'name';
  }
}

export function availableTags(): string[] {
  const tags = new Set<string>();
  activeTab()?.tracks.forEach((track) => track.tags.forEach((tag) => tags.add(tag)));
  return [...tags].sort((a, b) => a.localeCompare(b));
}

export function availableGenres(): string[] {
  const genres = new Set<string>();
  activeTab()?.tracks.forEach((track) => track.genres.forEach((genre) => genres.add(genre)));
  return [...genres].sort((a, b) => a.localeCompare(b));
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
