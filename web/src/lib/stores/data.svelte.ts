// Server-side (per GM) data: auth, settings, categories, presets.
import { api } from '../api';
import { cachedFirst, remember } from '../cache';
import { setLocale } from '../i18n.svelte';
import { prefs, savePrefs } from '../prefs.svelte';
import type { AuthState, MusicCategory, Preset, ServerSettings, UserState, VersionInfo } from '../types';
import { errorToast } from './ui.svelte';

export const data = $state({
  auth: null as AuthState | null,
  settings: null as ServerSettings | null,
  user: { favorites: [], tabs: null, accent: '', tour_done: false, tour_seen: [], news_off: false, videos_seen: [], player: null, view: null, locale: '' } as UserState,
  categories: [] as MusicCategory[],
  presets: [] as Preset[],
  version: null as VersionInfo | null,
  locales: [] as string[],
});

/** Picks the accent colour of the signed in user ('' for the default); applied at once and kept on the server. */
export async function setAccent(accent: string) {
  prefs.accent = accent;
  savePrefs();
  data.user.accent = accent;
  try {
    data.user = await api.putUserState({ accent });
  } catch (e) {
    errorToast(e);
  }
}

/** Picks the language of the signed in user ('' for the default of the server); applied at once and kept on the server. */
export async function setUserLocale(locale: string) {
  data.user.locale = locale;
  setLocale(locale || data.settings?.locale);
  try {
    data.user = await api.putUserState({ locale });
  } catch (e) {
    errorToast(e);
  }
}

export async function loadAuth() {
  data.auth = await api.me();
  return data.auth;
}

/** Applies a loaded value, except when the app changed it since the last one was applied (e.g. a favorite added right
 *  after the start): then the late answer of the server would undo that change. */
function unlessChanged<T>(current: () => unknown, apply: (value: T) => void): (value: T) => void {
  let applied: string | undefined;
  return (value) => {
    if (applied !== undefined && JSON.stringify($state.snapshot(current())) !== applied) return;
    apply(value);
    applied = JSON.stringify(value);
  };
}

function applyLocale() {
  if (data.settings) setLocale(data.user.locale || data.settings.locale);
}

/** Loads what the app needs to start. The values of the last start (see cache.ts) are used at once, so the app shows
 *  without waiting for the server; the current ones replace them as they arrive. */
export async function loadData() {
  await Promise.all([
    cachedFirst('settings', api.settings, unlessChanged(() => data.settings, (settings) => {
      data.settings = settings;
      applyLocale();
    })),
    cachedFirst('user', api.userState, unlessChanged(() => data.user, (user) => {
      data.user = user;
      prefs.accent = user.accent; // the browser remembers it, so the next start has the colour before the server answers
      savePrefs();
      applyLocale();
    })),
    cachedFirst('categories', api.categories, unlessChanged(() => data.categories, (categories) => (data.categories = categories))),
    cachedFirst('presets', api.presets, unlessChanged(() => data.presets, (presets) => (data.presets = presets))),
    cachedFirst('locales', api.locales, (locales) => (data.locales = locales)),
  ]);
  rememberChanges();
  api.version().then((version) => (data.version = version)).catch(() => undefined);
}

let remembering = false;

/** Changes made while the app runs (saved settings, favorites, ...) are kept for the next start. Started only after
 *  loadData, so the empty defaults never overwrite the cache. */
function rememberChanges() {
  if (remembering) return;
  remembering = true;
  $effect.root(() => {
    $effect(() => {
      if (data.settings) remember('settings', $state.snapshot(data.settings));
    });
    $effect(() => remember('user', $state.snapshot(data.user)));
    $effect(() => remember('categories', $state.snapshot(data.categories)));
    $effect(() => remember('presets', $state.snapshot(data.presets)));
  });
}

export async function saveSettings(values: Partial<Record<keyof ServerSettings, unknown>>) {
  try {
    data.settings = await api.putSettings(values);
    if ('locale' in values) {
      setLocale(data.user.locale || data.settings.locale);
      data.categories = await api.categories();
    }
  } catch (e) {
    errorToast(e);
    throw e;
  }
}

export async function saveCategories(categories: MusicCategory[] | null) {
  data.categories = categories ? await api.putCategories(categories) : await api.resetCategories();
}

export async function savePresets(presets: Preset[]) {
  try {
    data.presets = await api.putPresets(presets);
  } catch (e) {
    errorToast(e);
  }
}

/** Brings back the default presets. */
export async function resetPresets() {
  try {
    data.presets = await api.resetPresets();
  } catch (e) {
    errorToast(e);
  }
}

export function categoryName(key: string): string {
  return data.categories.find((c) => c.key === key)?.name ?? key;
}

async function saveFavorites(favorites: string[]) {
  try {
    data.user = await api.putUserState({ favorites });
  } catch (e) {
    errorToast(e);
  }
}

/** Favorites are folders (shown under "Library") and playlists (shown under "Playlists"). */
export const isPlaylistPath = (path: string) => path.toLowerCase().endsWith('.m3u');

export function addFavorite(path: string) {
  if (!data.user.favorites.includes(path)) void saveFavorites([...data.user.favorites, path]);
}

export function removeFavorite(path: string) {
  void saveFavorites(data.user.favorites.filter((p) => p !== path));
}

const inside = (path: string, base: string) => path === base || path.startsWith(base + '/');

/** Favorites follow a renamed or moved folder or playlist. */
export async function moveFavorites(oldPath: string, newPath: string) {
  if (data.user.favorites.some((p) => inside(p, oldPath))) {
    await saveFavorites(data.user.favorites.map((p) => (inside(p, oldPath) ? newPath + p.slice(oldPath.length) : p)));
  }
}

/** Deleted folders and playlists leave the favorites. */
export async function forgetFavorites(paths: string[]) {
  const kept = data.user.favorites.filter((p) => !paths.some((base) => inside(p, base)));
  if (kept.length !== data.user.favorites.length) await saveFavorites(kept);
}
