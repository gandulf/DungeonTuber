// Commands shared by the tree, the song table, menus and shortcuts.
import { api, pathToId } from './api';
import { t } from './i18n.svelte';
import { prefs, savePrefs } from './prefs.svelte';
import { data, forgetFavorites, isPlaylistPath } from './stores/data.svelte';
import { loadEffects } from './stores/effects.svelte';
import { activeTab, addToPlaylist, closeTab, library, loadTab, openTab, reloadAllDirTabs, reloadDirTabs, reloadPlaylistTabs, removeFromPlaylist, updateTrack } from './stores/library.svelte';
import { playTrack, refreshCurrentTrack } from './stores/player.svelte';
import { askConfirm, askText, errorToast, openDialog, toast, ui, type MenuItem } from './stores/ui.svelte';
import type { JobKind } from './stores/downloads.svelte';
import type { BrowseItem, Track } from './types';
import { isMp3, itemsFromDrop, type UploadItem } from './upload';
import EditSongDialog from '../components/dialogs/EditSongDialog.svelte';
import DownloadsDialog from '../components/dialogs/DownloadsDialog.svelte';
import ImportDialog from '../components/dialogs/ImportDialog.svelte';
import PlaylistDialog from '../components/dialogs/PlaylistDialog.svelte';
import UploadDialog from '../components/dialogs/UploadDialog.svelte';

export function dirname(path: string): string {
  const index = path.lastIndexOf('/');
  return index > 0 ? path.slice(0, index) : path;
}

export async function openItem(item: BrowseItem) {
  if (item.type === 'dir') await openTab('dir', item.path);
  else if (item.type === 'm3u') await openTab('playlist', item.path);
  else {
    try {
      await playTrack(await api.track(item.id));
    } catch (e) {
      errorToast(e);
    }
  }
}

export async function analyze(paths: string[]) {
  try {
    const result = await api.analyze(paths);
    toast(t('Analyzing {0}...', result.queued === 1 ? paths[0].split('/').pop()! : `${result.queued} files`));
  } catch (e) {
    errorToast(e);
  }
}

export async function rescanLibrary(path?: string) {
  try {
    toast(t('Rescanning library...'));
    const result = await api.rescan(path);
    reloadAllDirTabs();
    toast(t('Rescan finished: {0} new, {1} changed, {2} removed', result.added, result.changed, result.removed));
  } catch (e) {
    errorToast(e);
  }
}

/** The library folders were changed (desktop app): drops what lies outside of the new folders, then syncs the database and the open tabs. */
export async function libraryRootsChanged() {
  try {
    const roots = (await api.roots()).map((root) => root.path.replace(/\/+$/, ''));
    const inside = (path: string) => roots.some((root) => path === root || path.startsWith(root + '/'));
    for (const tab of [...library.tabs]) if (!inside(tab.path)) closeTab(tab.key);
    if (prefs.treeRoot && !inside(prefs.treeRoot)) {
      prefs.treeRoot = null;
      savePrefs();
    }
  } catch (e) {
    errorToast(e);
  }
  void loadEffects();
  await rescanLibrary();
}

/** Edits the tags of a song; opened from a playlist, its scene name there comes first. */
export function editSong(track: Track, playlist?: string) {
  openDialog(EditSongDialog, { track, playlist });
}

/** Edits a song picked in the file tree (which only knows its id). */
export async function editSongById(id: string) {
  try {
    editSong(await api.track(id));
  } catch (e) {
    errorToast(e);
  }
}

export async function toggleFavorite(track: Track) {
  try {
    const updated = await api.patchTrack(track.id, { favorite: !track.favorite });
    updateTrack(updated);
    refreshCurrentTrack(updated);
  } catch (e) {
    errorToast(e);
  }
}

/** Asks for a name and the folder of a new playlist; the folder of the open tab (or the given one) is preselected. */
export function newPlaylist(ids: string[] = [], directory?: string) {
  const tab = activeTab();
  const current = tab?.type === 'dir' ? tab.path : tab ? dirname(tab.path) : null;
  const dir = directory ?? current ?? prefs.treeRoot ?? data.settings?.libraryRoots[0];
  if (dir) openDialog(PlaylistDialog, { directory: dir, ids });
}

/** Names the scene a song is used for in one playlist (kept in the playlist, the mp3 stays as it is). */
export async function editScene(playlist: string, track: Track) {
  const scene = await askText(t('Scene name'), t('Only used in this playlist'), track.scene ?? '');
  if (scene !== null && scene !== track.scene) await setScene(playlist, track, scene);
}

async function setScene(playlist: string, track: Track, scene: string) {
  try {
    await api.setScene(playlist, track.id, scene);
    reloadPlaylistTabs(playlist);
  } catch (e) {
    errorToast(e);
  }
}

/** Edits the name and the visibility (public or private) of a playlist. */
export function editPlaylist(playlist: { path: string; name: string; private?: boolean }) {
  openDialog(PlaylistDialog, { playlist: { path: playlist.path, name: playlist.name, private: !!playlist.private } });
}

/** Uploads mp3 files one request at a time (folders below `directory` are created from the item paths); returns the stored tracks. */
export async function uploadFiles(directory: string, files: (File | UploadItem)[]): Promise<Track[]> {
  const items = files.map((f) => (f instanceof File ? { file: f, path: f.name } : f)).filter((item) => isMp3(item.file.name));
  if (!items.length) {
    toast(t('Only mp3 files can be uploaded.'), 'error');
    return [];
  }
  const tracks: Track[] = [];
  const failed: string[] = [];
  try {
    for (const [index, item] of items.entries()) {
      ui.progress = t('Uploading {0} of {1}: {2}', index + 1, items.length, item.file.name);
      try {
        tracks.push(...(await api.upload(directory, [item.file], [item.path])).tracks);
      } catch (e) {
        failed.push(`${item.path}: ${e instanceof Error ? e.message : e}`);
      }
    }
  } finally {
    ui.progress = null;
  }
  reloadDirTabs(directory);
  if (!failed.length) toast(t('Upload complete'), 'success');
  else toast(t('{0} of {1} files could not be uploaded: {2}', failed.length, items.length, failed[0]), 'error');
  return tracks;
}

const TRACKS_TYPE = 'application/x-dungeontuber-tracks';
const PATH_TYPE = 'application/x-dungeontuber-path';

/** Songs from the table, songs from the file tree and files from the computer can be dropped on a playlist. */
export function canDropOnPlaylist(transfer: DataTransfer | null): boolean {
  const types = transfer?.types ?? [];
  return types.includes(TRACKS_TYPE) || types.includes(PATH_TYPE) || types.includes('Files');
}

/** Adds what was dropped to the end of a playlist; files from the computer are uploaded next to the playlist first. */
export async function dropOnPlaylist(playlist: string, transfer: DataTransfer | null) {
  if (!transfer) return;
  const ids: string[] = [];
  try {
    ids.push(...(JSON.parse(transfer.getData(TRACKS_TYPE) || '[]') as string[]));
  } catch { /* not ours */ }
  const path = transfer.getData(PATH_TYPE);
  if (path.toLowerCase().endsWith('.mp3')) ids.push(pathToId(path));
  const files = transfer.types.includes('Files') ? await itemsFromDrop(transfer) : []; // read before anything else is awaited
  if (files.length) ids.push(...(await uploadFiles(dirname(playlist), files)).map((track) => track.id));
  if (ids.length) await addToPlaylist(playlist, [...new Set(ids)]);
}

/** The SuperAdmin may delete everything, other users what they uploaded or created themselves. */
export function canDelete(owner?: string | null): boolean {
  return !!data.auth?.is_admin || (!!owner && owner === data.auth?.user);
}

export async function deleteItems(items: { path: string; name: string; dir?: boolean }[]) {
  if (!items.length) return;
  const message = items.length > 1 ? t('Delete {0} items?', items.length)
    : items[0].dir ? t('Delete folder {0} and everything in it?', items[0].name) : t('Delete {0}?', items[0].name);
  if (!(await askConfirm(message))) return;
  try {
    for (const item of items) await api.deleteFile(item.path);
  } catch (e) {
    errorToast(e);
  }
  const gone = (path: string) => items.some((item) => path === item.path || path.startsWith(item.path + '/'));
  for (const tab of [...library.tabs]) if (gone(tab.path)) closeTab(tab.key);
  await forgetFavorites(items.map((item) => item.path));
  for (const tab of library.tabs) void loadTab(tab.key, true);
}

export function openUploadDialog(directory?: string, initial: UploadItem[] = []) {
  const target = directory ?? uploadTarget();
  if (target) openDialog(UploadDialog, { directory: target, initial });
}

export function openDownloadsDialog(kind: JobKind = 'downloads') {
  openDialog(DownloadsDialog, { kind });
}

export function openImportDialog(directory?: string) {
  const target = directory ?? uploadTarget();
  if (target) openDialog(ImportDialog, { directory: target });
}

export function uploadTarget(): string | null {
  const tab = activeTab();
  return tab?.type === 'dir' ? tab.path : (prefs.treeRoot ?? data.settings?.libraryRoots[0] ?? null);
}

/** "Add to playlist": the favorite playlists and the open ones. */
export function playlistMenu(ids: string[]): MenuItem[] {
  const paths = [...new Set([...data.user.favorites.filter(isPlaylistPath), ...library.tabs.filter((tab) => tab.type === 'playlist').map((tab) => tab.path)])];
  const name = (path: string) => path.split('/').pop()!.replace(/\.m3u$/i, '');
  return [
    { label: t('New Playlist…'), icon: 'plus', action: () => newPlaylist(ids) },
    ...(paths.length ? [{ separator: true }] : []),
    ...paths.map((path) => ({ label: name(path), icon: 'playlist', action: () => addToPlaylist(path, ids) })),
  ];
}

export function trackMenu(tracks: Track[]): MenuItem[] {
  const tab = activeTab();
  const ids = tracks.map((track) => track.id);
  const single = tracks.length === 1 ? tracks[0] : null;
  const items: MenuItem[] = [];
  if (single) {
    items.push({ label: t('Play'), icon: 'play', action: () => playTrack(single) });
    items.push({ label: t('Edit Song…'), icon: 'edit', tour: 'menu-edit', action: () => editSong(single, tab?.type === 'playlist' ? tab.path : undefined) });
    items.push({ label: t('Favorite'), icon: 'star', checked: single.favorite, action: () => toggleFavorite(single) });
  }
  if (data.settings?.voxalyzerActive !== false) {
    items.push({ label: t('Analyze'), icon: 'sparkles', tour: 'menu-analyze', action: () => analyze(tracks.map((track) => track.path)) });
  }
  items.push({ separator: true }, { label: t('Add to playlist'), icon: 'playlist', children: playlistMenu(ids) });
  if (tab?.type === 'playlist') {
    if (single) items.push({ label: t('Scene name…'), icon: 'marker', action: () => editScene(tab.path, single) });
    if (single?.scene) items.push({ label: t('Remove scene name'), icon: 'close', action: () => setScene(tab.path, single, '') });
    items.push({ label: t('Remove from playlist'), icon: 'trash', action: () => removeFromPlaylist(tab.path, ids) });
  }
  if (tracks.length && tracks.every((track) => canDelete(track.uploaded_by))) {
    items.push({ separator: true }, { label: t('Delete file'), icon: 'trash',
      action: () => deleteItems(tracks.map((track) => ({ path: track.path, name: track.name }))) });
  }
  return items;
}
