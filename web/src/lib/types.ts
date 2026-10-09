export interface LightSetting {
  scene: string | null;
  brightness: number | null;
  temperature: number | null;
  color: string | null;
}

export interface Chapter {
  title: string;
  time: number; // ms
  light: LightSetting | null;
}

export interface Track {
  /** Who uploaded the file (only for files uploaded through Dungeon Tuber). */
  uploaded_by?: string | null;
  uploaded_at?: number | null;
  id: string;
  path: string;
  file: string;
  name: string;
  title: string | null;
  artist: string | null;
  album: string | null;
  summary: string;
  genres: string[];
  tags: string[];
  length: number; // seconds
  favorite: boolean;
  categories: Record<string, number>;
  bpm: number | null;
  light: LightSetting | null;
  chapters: Chapter[];
  has_cover: boolean;
  index: number | null;
  previous_id?: string;
}

export interface BrowseItem {
  name: string;
  file?: string;
  path: string;
  id: string;
  type: 'dir' | 'mp3' | 'm3u';
  /** Only set for library roots: 'local', 's3', ... */
  storage?: string;
  /** Who uploaded or created it (unset for files that were not added through Dungeon Tuber). */
  uploaded_by?: string | null;
}

export interface BrowseResult {
  path: string;
  name: string;
  id: string;
  parent: string | null;
  items: BrowseItem[];
}

export interface TrackList {
  type: 'dir' | 'playlist';
  path: string;
  name: string;
  tracks: Track[];
}

export interface MusicCategory {
  key: string;
  name: string;
  description: string;
  levels: Record<string, string>;
  group: string | null;
}

export interface Preset {
  name: string;
  categories: Record<string, number>;
  tags: string[];
  genres: string[];
  bpm: number | null;
}

export interface Effect {
  id: string;
  path: string;
  name: string;
  title: string | null;
  cover_url: string | null;
  intensities: Track[];
}

export interface Light extends LightSetting {
  name: string;
  mac: string;
  scenable: boolean;
  state: boolean;
  online: boolean;
  temperature_min: number;
  temperature_max: number;
  scenes: string[];
}

export interface AgentInfo {
  id: number;
  kind: string;
  name: string;
  user: string | null;
}

export interface AgentToken {
  id: string;
  name: string;
  user: string;
  created: number;
  used: number | null;
}

export interface AgentState {
  tokens: AgentToken[];
  connected: AgentInfo[];
}

export interface ServerSettings {
  locale: string;
  skipAnalyzedMusic: boolean;
  lightsEnabled: boolean;
  lightsBroadcastIP: string;
  lightsTimeout: number;
  effectsDirectory: string;
  libraryRoots: string[];
  shareOnNetwork: boolean;
  sharePort: number;
  networkUrl: string;
  voxalyzerActive: boolean;
}

export interface StorageConfig {
  id?: string;
  name: string;
  bucket: string;
  prefix: string;
  endpoint_url: string;
  public_endpoint_url: string;
  region: string;
  direct: boolean;
  has_credentials?: boolean;
  /** write-only; omitted to keep the stored value */
  access_key?: string;
  secret_key?: string;
}

export interface AuthState {
  authenticated: boolean;
  local: boolean;
  password_set: boolean;
  user: string | null;
  is_admin: boolean;
}

/** What every user keeps for themselves: favorite folders and the open tabs. */
export interface UserState {
  favorites: string[];
  tabs: { open: { type: 'dir' | 'playlist'; path: string }[]; active: string | null } | null;
  accent: string;
  tour_done: boolean;
  player: PlayerSettings | null;
  /** The view preferences (see stores/profile.svelte.ts). */
  view: Partial<ViewSettings> | null;
  /** The language of the user, '' for the default of the server. */
  locale: string;
}

/** The view preferences that follow a user from device to device (a subset of Prefs). */
export interface ViewSettings {
  showEffects: boolean;
  showLights: boolean;
  filter: { presets: boolean; circumplex: boolean; sliders: boolean; bpm: boolean; tags: boolean; genres: boolean };
  moodCollapsed: boolean;
  showMoodMap: boolean;
  columns: Record<string, boolean>;
  columnWidths: Record<string, number>;
  hiddenCategories: string[];
  titleInsteadOfFile: boolean;
  summaryUnderTitle: boolean;
  rowStyle: 'small' | 'medium' | 'large';
  effectsGrid: boolean;
  effectsTitle: boolean;
  importOptions: { makePlaylist: boolean; makeFolder: boolean; split: boolean; analyze: boolean };
}

/** The player options that follow a user from device to device. */
export interface PlayerSettings {
  shuffle: boolean;
  repeat: 'none' | 'all' | 'single';
  volume: number;
  muted: boolean;
  effectsVolume: number;
  normalize: boolean;
  crossfade: boolean;
  dynamicScore: boolean;
  dynamicColumns: boolean;
}

export interface UserInfo {
  name: string;
  admin: boolean;
  created: number | null;
}

export interface ImportEntry {
  url: string;
  title: string;
  duration?: number | null;
  uploader?: string | null;
  chapters?: number | null;
}

export interface DownloadItem {
  id: number;
  url: string;
  title: string;
  state: 'queued' | 'downloading' | 'running' | 'done' | 'skipped' | 'failed';
  percent: number;
  message: string;
}

export interface ImportPreview {
  title: string;
  playlist: boolean;
  hasVideo: boolean;
  maxMinutes: number;
  entries: ImportEntry[];
}

export interface VersionInfo {
  current: string;
  latest: string | null;
  newer: boolean;
  download: string;
}

export interface FilterConfig {
  categories: Record<string, number | null>;
  tags: string[];
  genres: string[];
  bpm: number | null;
}
