import type {
  AgentInfo, AuthState, BrowseItem, BrowseResult, Chapter, DownloadItem, Effect, ImportPreview, Light, LightSetting, MusicCategory, Preset, ServerSettings, Track, TrackList,
  StorageConfig, UserInfo, UserState, VersionInfo,
} from './types';

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

async function request<T>(method: string, url: string, body?: unknown, raw = false): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin', headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    (init.headers as Record<string, string>)['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail);
    } catch { /* not json */ }
    if (response.status === 401 && onUnauthorized && !url.startsWith('/api/auth/')) onUnauthorized();
    throw new ApiError(response.status, message);
  }
  if (raw) return response as unknown as T;
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

const get = <T>(url: string) => request<T>('GET', url);
const qs = (params: Record<string, string | boolean | undefined>) =>
  new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  // auth
  me: () => get<AuthState>('/api/auth/me'),
  login: (username: string, password: string) => request<AuthState>('POST', '/api/auth/login', { username, password }),
  logout: () => request('POST', '/api/auth/logout'),
  setOwnPassword: (password: string) => request('PUT', '/api/auth/me/password', { password }),
  users: () => get<UserInfo[]>('/api/users'),
  createUser: (name: string, password: string) => request<UserInfo>('POST', '/api/users', { name, password }),
  resetUserPassword: (name: string, password: string) => request('PUT', `/api/users/${encodeURIComponent(name)}/password`, { password }),
  deleteUser: (name: string) => request('DELETE', `/api/users/${encodeURIComponent(name)}`),
  setPassword: (password: string | null) => request<{ password_set: boolean }>('PUT', '/api/auth/password', { password }),

  // library
  roots: () => get<BrowseItem[]>('/api/roots'),
  browse: (path: string) => get<BrowseResult>(`/api/browse?${qs({ path })}`),
  tracksOfDir: (dir: string) => get<TrackList>(`/api/tracks?${qs({ dir })}`),
  tracksOfPlaylist: (playlist: string) => get<TrackList>(`/api/tracks?${qs({ playlist })}`),
  track: (id: string) => get<Track>(`/api/tracks/${id}`),
  patchTrack: (id: string, patch: Partial<Omit<Track, 'categories'>> & { categories?: Record<string, number | null>; name?: string }) =>
    request<Track>('PATCH', `/api/tracks/${id}`, patch),
  putChapters: (id: string, chapters: Chapter[]) => request<Track>('PUT', `/api/tracks/${id}/chapters`, chapters),
  putCover: (id: string, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<Track>('PUT', `/api/tracks/${id}/cover`, form);
  },

  // playlists & files
  createPlaylist: (path: string, ids: string[] = []) => request<{ path: string; id: string; name: string }>('POST', '/api/playlists', { path, ids }),
  addToPlaylist: (playlist: string, ids: string[], index = -1) => request<{ added: number }>('POST', '/api/playlists/entries', { playlist, ids, index }),
  removeFromPlaylist: (playlist: string, ids: string[]) => request('POST', '/api/playlists/remove', { playlist, ids }),
  reorderPlaylist: (playlist: string, ids: string[]) => request('PUT', '/api/playlists/order', { playlist, ids }),
  move: (source: string, target_dir: string) => request<{ path: string; id: string }>('POST', '/api/files/move', { source, target_dir }),
  deleteFile: (path: string) => request<{ deleted: boolean }>('DELETE', `/api/files?${qs({ path })}`),
  createFolder: (parent: string, name: string) => {
    const form = new FormData();
    form.append('parent', parent);
    form.append('name', name);
    return request<{ path: string }>('POST', '/api/files/folder', form);
  },
  upload: (dir: string, files: File[], paths?: string[]) => {
    const form = new FormData();
    form.append('dir', dir);
    files.forEach((file) => form.append('files', file));
    paths?.forEach((path) => form.append('paths', path));
    return request<{ tracks: Track[] }>('POST', '/api/upload', form);
  },

  // import of YouTube links
  resolveImport: (url: string, whole?: boolean) => request<ImportPreview>('POST', '/api/import/resolve', { url, whole }),
  startImport: (body: { dir: string; entries: { url: string; title: string }[]; album?: string; playlist?: string; folder?: string; analyze?: boolean; split?: boolean }) =>
    request<{ queued: number; pending: number }>('POST', '/api/import', body),
  cloudAnalysis: () => get<{ configured: boolean; host: string | null }>('/api/analysis/cloud'),
  putCloudAnalysis: (url: string, key: string, secret: string) => request<{ configured: boolean; host: string | null }>('PUT', '/api/analysis/cloud', { url, key, secret }),
  deleteCloudAnalysis: () => request<{ configured: boolean; host: string | null }>('DELETE', '/api/analysis/cloud'),
  youtubeCookies: () => get<{ set: boolean; updated: number | null }>('/api/import/cookies'),
  putYoutubeCookies: (content: string) => request<{ set: boolean; updated: number | null }>('PUT', '/api/import/cookies', { content }),
  deleteYoutubeCookies: () => request<{ set: boolean; updated: number | null }>('DELETE', '/api/import/cookies'),
  importStatus: () => get<{ pending: number; done: number; failed: number; items: DownloadItem[] }>('/api/import'),

  // settings
  userState: () => get<UserState>('/api/user/state'),
  putUserState: (state: Partial<UserState>) => request<UserState>('PUT', '/api/user/state', state),
  settings: () => get<ServerSettings>('/api/settings'),
  putSettings: (values: Partial<Record<keyof ServerSettings, unknown>>) => request<ServerSettings>('PUT', '/api/settings', values),
  categories: () => get<MusicCategory[]>('/api/categories'),
  putCategories: (categories: MusicCategory[]) => request<MusicCategory[]>('PUT', '/api/categories', categories),
  resetCategories: () => request<MusicCategory[]>('POST', '/api/categories/reset'),
  presets: () => get<Preset[]>('/api/presets'),
  putPresets: (presets: Preset[]) => request<Preset[]>('PUT', '/api/presets', presets),
  version: () => get<VersionInfo>('/api/version'),
  locales: () => get<string[]>('/api/locales'),

  // remote storages (S3)
  storages: () => get<{ available: boolean; storages: StorageConfig[] }>('/api/storages'),
  putStorages: (storages: StorageConfig[]) => request<{ available: boolean; storages: StorageConfig[] }>('PUT', '/api/storages', storages),
  testStorage: (storage: StorageConfig) => request<{ ok: boolean; entries: number }>('POST', '/api/storages/test', storage),

  // effects & analysis
  effects: () => get<{ directory: string | null; effects: Effect[] }>('/api/effects'),
  analyze: (paths: string[]) => request<{ queued: number; pending: number }>('POST', '/api/analysis', { paths }),
  rescan: (path?: string) => request<{ added: number; changed: number; removed: number; total: number }>('POST', '/api/library/rescan', { path: path ?? null }),
  analysisStatus: () => get<{ backend: string; pending: number; done: number; failed: number }>('/api/analysis'),

  // lights
  lights: () => get<{ enabled: boolean; lights: Light[]; scenes: string[]; agent: boolean }>('/api/lights'),
  discoverLights: () => request<{ enabled: boolean; lights: Light[]; scenes: string[] }>('POST', '/api/lights/discover'),
  patchLight: (mac: string, patch: Partial<Light> & { clear_color?: boolean }) => request<Light>('PATCH', `/api/lights/${encodeURIComponent(mac)}`, patch),
  cue: (setting: LightSetting) => request<{ applied: number }>('POST', '/api/lights/cue', setting),

  // agents (WiZ light agent, ...)
  agents: () => get<{ tokenSet: boolean; connected: AgentInfo[] }>('/api/agents'),
  removeAgent: (kind: string) => request<{ connected: AgentInfo[] }>('DELETE', `/api/agents/${encodeURIComponent(kind)}`),
  createAgentToken: () => request<{ token: string }>('POST', '/api/agents/token'),
};

/** Same opaque id the server derives from a path (urlsafe base64 without padding). */
export function pathToId(path: string): string {
  const bytes = new TextEncoder().encode(path);
  let binary = '';
  bytes.forEach((b) => (binary += String.fromCharCode(b)));
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export const mediaUrl = (trackId: string) => `/media/tracks/${trackId}`;
export const coverUrl = (trackId: string, size = 128) => `/media/covers/${trackId}?size=${size}`;
