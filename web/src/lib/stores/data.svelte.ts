// Server-side (per GM) data: auth, settings, categories, presets.
import { api } from '../api';
import { setLocale } from '../i18n.svelte';
import type { AuthState, MusicCategory, Preset, ServerSettings, UserState, VersionInfo } from '../types';
import { errorToast } from './ui.svelte';

export const data = $state({
  auth: null as AuthState | null,
  settings: null as ServerSettings | null,
  user: { favorites: [], tabs: null } as UserState,
  categories: [] as MusicCategory[],
  presets: [] as Preset[],
  version: null as VersionInfo | null,
  locales: [] as string[],
});

export async function loadAuth() {
  data.auth = await api.me();
  return data.auth;
}

export async function loadData() {
  const [settings, categories, presets, locales, user] = await Promise.all([api.settings(), api.categories(), api.presets(), api.locales(), api.userState()]);
  data.settings = settings;
  data.user = user;
  data.categories = categories;
  data.presets = presets;
  data.locales = locales;
  setLocale(settings.locale);
  api.version().then((version) => (data.version = version)).catch(() => undefined);
}

export async function saveSettings(values: Partial<Record<keyof ServerSettings, unknown>>) {
  try {
    data.settings = await api.putSettings(values);
    if ('locale' in values) {
      setLocale(data.settings.locale);
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

export function categoryName(key: string): string {
  return data.categories.find((c) => c.key === key)?.name ?? key;
}

async function saveFavoriteFolders(favorites: string[]) {
  try {
    data.user = await api.putUserState({ favorites });
  } catch (e) {
    errorToast(e);
  }
}

export function addFavoriteFolder(path: string) {
  if (!data.user.favorites.includes(path)) void saveFavoriteFolders([...data.user.favorites, path]);
}

export function removeFavoriteFolder(path: string) {
  void saveFavoriteFolders(data.user.favorites.filter((p) => p !== path));
}
