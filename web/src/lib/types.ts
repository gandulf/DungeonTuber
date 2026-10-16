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
  /** Track number on the album (ID3 TRCK). */
  track?: number | null;
  summary: string;
  genres: string[];
  tags: string[];
  length: number; // seconds
  favorite: boolean;
  categories: Record<string, number>;
  bpm: number | null;
  light: LightSetting | null;
  /** Set when the metadata was normalized with AcoustID / MusicBrainz. */
  normalized?: Normalized | null;
  chapters: Chapter[];
  /** Stable id of the song (UFID frame), unchanged by moves, renames and tag edits. */
  ufid?: string | null;
  has_cover: boolean;
  index: number | null;
  previous_id?: string;
  /** Playlists only: the scene name of the entry (stored in the playlist, not in the mp3). */
  scene?: string | null;
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
  /** Set for private playlists, which only their creator sees. */
  private?: boolean;
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
  /** Playlists only: private (visible to its creator alone) and who created it. */
  private?: boolean;
  uploaded_by?: string | null;
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
  /** What the server configured on the agent (light agents only): broadcast address and seconds to wait for bulbs. */
  settings?: { broadcast?: string; wait?: number };
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
  /** Batch normalize skips songs that were normalized already. */
  skipNormalizedMusic: boolean;
  lightsEnabled: boolean;
  lightsBroadcastIP: string;
  lightsTimeout: number;
  effectsDirectory: string;
  libraryRoots: string[];
  shareOnNetwork: boolean;
  sharePort: number;
  networkUrl: string;
  voxalyzerActive: boolean;
  assistantConfigured: boolean;
  /** Groq has a key: it answers the smart search and the compose mode of the assistant. */
  groqConfigured: boolean;
  /** The music generation (ACE-Step on Modal) is set up. */
  musicGenConfigured: boolean;
  /** The sound generation (Stable Audio 3 on Modal) is set up. */
  soundGenConfigured: boolean;
}

/** A song the AI assistant suggests. */
export interface AssistantSong {
  title: string;
  artist: string;
  /** The check on YouTube: undefined while it runs, found null when YouTube could not be searched. */
  check?: SongCheck;
}

/** A suggested song looked up on YouTube; url, title, channel and duration are those of the matching video. */
export interface SongCheck {
  found: boolean | null;
  url?: string;
  title?: string;
  channel?: string;
  duration?: number | null;
}

export interface AssistantReply {
  message: string;
  songs: AssistantSong[];
  /** The raw answer of the model; it goes back into the conversation. */
  content: string;
  /** The filter chosen by the smart search. */
  filter?: SmartFilter;
  /** The piece described in the compose mode. */
  piece?: ComposePiece;
  /** The sound described in the effects mode. */
  sound?: SoundDescription;
  /** The notes drafted in the story mode. */
  text?: string;
}

/** What the sound generation creates: a sound effect, an ambience (a steady background of a place) or instrumental music. */
export type SoundKind = 'sfx' | 'ambience' | 'music';

/** A sound for the sound generation (see server/soundgen.py); the caption is the description Stable Audio creates it from. */
export interface SoundDescription {
  title: string;
  caption: string;
  kind: SoundKind;
  /** Seconds the assistant suggests; null: the default of the kind. */
  duration: number | null;
}

/** A piece for the music generation (see server/musicgen.py); the caption is the description ACE-Step composes from. */
export interface ComposePiece {
  title: string;
  caption: string;
  lyrics: string;
  /** ISO 639-1 code of the lyrics; empty: ACE-Step finds it. */
  language: string;
  instrumental: boolean;
  bpm: number | null;
}

/** A composed piece stored in the library. */
export interface ComposeResult {
  track: Track;
  seed: number | null;
}

/** The filter of the smart search: values the app knows (see server/smartsearch.py). */
export interface SmartFilter {
  categories: Record<string, number>;
  tags: string[];
  genres: string[];
  bpm: number | null;
}

export interface AssistantStatus {
  configured: boolean;
  model: string;
  defaultModel: string;
  /** The last characters of the stored key. */
  keyHint: string;
  keySource: KeySource;
  groqKeySource: KeySource;
  /** Additional instructions of the SuperAdmin for the song suggestions. */
  instructions: string;
  /** The instructions the modes have until they are changed (the other modes have none). */
  defaultInstructions: Partial<Record<'music' | 'smart' | 'compose', string>>;
  /** Additional instructions of the SuperAdmin for the general chat. */
  generalInstructions: string;
  /** Additional instructions of the SuperAdmin for the compose mode. */
  composeInstructions: string;
  /** Additional instructions of the SuperAdmin for the smart search; without them those of the song suggestions are used. */
  smartInstructions: string;
  /** Additional instructions of the SuperAdmin for the effects mode. */
  effectsInstructions: string;
  groqConfigured: boolean;
  groqModel: string;
  groqDefaultModel: string;
  groqKeyHint: string;
  groqModels: { id: string; name: string }[];
  /** The built-in prompts (e.g. "compose.vocals") with their default and the text in use. */
  prompts: { name: string; default: string; value: string }[];
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
  tabs: { open: { type: 'dir' | 'playlist' | 'adventure'; path: string }[]; active: string | null } | null;
  accent: string;
  tour_done: boolean;
  /** Ids of the tour steps the user has seen (Tour.svelte), so steps added later can be shown as news. */
  tour_seen: string[];
  /** No "What's new" popup for tour steps the user has not seen. */
  news_off: boolean;
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
  tagsExpanded: boolean;
  genresExpanded: boolean;
  columns: Record<string, boolean>;
  columnWidths: Record<string, number>;
  hiddenCategories: string[];
  titleInsteadOfFile: boolean;
  summaryUnderTitle: boolean;
  rowStyle: 'small' | 'medium' | 'large';
  effectsGrid: boolean;
  effectsLoop: boolean;
  effectsTitle: boolean;
  importOptions: { makePlaylist: boolean; makeFolder: boolean; split: boolean; analyze: boolean; limitMinutes: number };
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
  /** Unix time of the last sign in (null: never) and how often the user signed in. */
  last_login: number | null;
  logins: number;
  /** Unix time of the last page load, and the visits of the site (page loads after a pause of 30 minutes count anew), also with an existing session. */
  last_seen: number | null;
  visits: number;
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

/** A match of the metadata lookup (AcoustID by fingerprint, MusicBrainz by text, see core/musiclookup.py). */
export interface LookupCandidate {
  title: string;
  artist: string;
  album: string | null;
  track: number | null;
  year: string | null;
  length: number | null;
  score: number;
  source: 'acoustid' | 'musicbrainz';
  recording_id: string;
}

/** Set on songs whose metadata was taken from a match (written into the file as TXXX:dt_normalized). */
export interface Normalized {
  source: 'acoustid' | 'musicbrainz';
  recording_id: string;
  /** Date of the normalization (YYYY-MM-DD). */
  at?: string;
}

export interface LookupResult {
  candidates: LookupCandidate[];
  errors: string[];
}

/** Where a key comes from: stored in the settings, an environment variable of the server (DT_…), or nowhere. */
export type KeySource = 'settings' | 'environment' | null;

export interface MetadataStatus {
  configured: boolean;
  keyHint: string;
  keySource: KeySource;
  fpcalc: boolean;
}

/** The connection to a cloud function on Modal (cloud analysis, music generation). */
export interface CloudStatus {
  configured: boolean;
  host: string | null;
  source: KeySource;
}

// --- adventures --------------------------------------------------------------

export interface SongRef { type: 'song'; ufid: string; path: string; title: string }
export interface PlaylistRef { type: 'playlist'; id: string; path: string; title: string; unavailable?: boolean }
export type MusicRef = SongRef | PlaylistRef;

export interface EffectRef { path: string; name: string; loop: boolean; autostart: boolean }

export interface AdventureBlock {
  id: string;
  title: string;
  markdown: string;
  played: boolean;
  pos: [number, number];
  autoplay: boolean;
  music: MusicRef[];
  effects: EffectRef[];
  images: string[];
}

export interface AdventureLink { from: string; to: string; label: string | null }

export interface AdventureSummary {
  id: string;
  title: string;
  owner: string;
  visibility: 'private' | 'public';
  blocks: number;
  played: number;
  updated: number;
  editable: boolean;
}

export interface Adventure {
  id: string;
  title: string;
  owner: string;
  visibility: 'private' | 'public';
  created: number;
  updated: number;
  blocks: AdventureBlock[];
  links: AdventureLink[];
  editable: boolean;
}

export interface PlaylistInfo { id: string; path: string; name: string; playlist_id: string }
