// Per-device view preferences, persisted in localStorage.

export type ThemeMode = 'light' | 'dark';
export type RepeatMode = 'none' | 'single' | 'all';
export type RowStyle = 'small' | 'medium' | 'large';
export type ViewMode = 'simple' | 'player' | 'complex';

export interface Prefs {
  theme: ThemeMode;
  fontScale: number;
  volume: number; // 0..150
  effectsVolume: number;
  muted: boolean;
  repeat: RepeatMode;
  shuffle: boolean;
  /** The valence/arousal map next to the mood sliders. */
  showMoodMap: boolean;
  moodCollapsed: boolean;
  crossfade: boolean;
  normalize: boolean;
  showEffects: boolean;
  showLights: boolean;
  leftWidth: number;
  rightWidth: number;
  filter: { presets: boolean; circumplex: boolean; sliders: boolean; bpm: boolean; tags: boolean; genres: boolean };
  columns: Record<string, boolean>;
  hiddenCategories: string[];
  dynamicColumns: boolean;
  dynamicScore: boolean;
  titleInsteadOfFile: boolean;
  summaryUnderTitle: boolean;
  rowStyle: RowStyle;
  effectsGrid: boolean;
  effectsTitle: boolean;
  treeRoot: string | null;
  expanded: string[];
  /** Library roots that were already expanded once by default. */
  seenRoots: string[];
  openTabs: { type: 'dir' | 'playlist'; path: string }[];
  activeTab: string | null;
  tourDone: boolean;
  /** Accent colour of the signed in user (a key of lib/accent.ts), cached from the server. */
  accent: string;
  /** The options of the last YouTube import, preselected the next time. */
  importOptions: { makePlaylist: boolean; makeFolder: boolean; split: boolean; analyze: boolean };
}

const defaults: Prefs = {
  theme: 'light',
  fontScale: 1,
  volume: 70,
  effectsVolume: 70,
  muted: false,
  repeat: 'none',
  shuffle: false,
  showMoodMap: true,
  moodCollapsed: false,
  crossfade: true,
  normalize: true,
  showEffects: true,
  showLights: true,
  leftWidth: 260,
  rightWidth: 300,
  filter: { presets: true, circumplex: true, sliders: true, bpm: true, tags: true, genres: true },
  columns: { index: true, favorite: true, cover: true, title: false, summary: false, artist: false, album: false, genre: true, bpm: true, score: true, tags: true, duration: true },
  hiddenCategories: [],
  dynamicColumns: false,
  dynamicScore: true,
  titleInsteadOfFile: true,
  summaryUnderTitle: true,
  rowStyle: 'medium',
  effectsGrid: true,
  effectsTitle: false,
  treeRoot: null,
  expanded: [],
  seenRoots: [],
  openTabs: [],
  activeTab: null,
  tourDone: false,
  accent: '',
  importOptions: { makePlaylist: false, makeFolder: false, split: false, analyze: false },
};

const KEY = 'dungeontuber.prefs';

function load(): Prefs {
  try {
    const stored = JSON.parse(localStorage.getItem(KEY) ?? '{}');
    if (stored.theme !== 'light' && stored.theme !== 'dark') delete stored.theme; // e.g. the former 'system' mode
    return { ...defaults, ...stored, filter: { ...defaults.filter, ...stored.filter }, columns: { ...defaults.columns, ...stored.columns },
      importOptions: { ...defaults.importOptions, ...stored.importOptions } };
  } catch {
    return structuredClone(defaults);
  }
}

export const prefs: Prefs = $state(load());

let saveTimer: ReturnType<typeof setTimeout> | null = null;

export function savePrefs() {
  if (saveTimer) clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify($state.snapshot(prefs)));
    } catch { /* storage unavailable */ }
  }, 200);
}

export function applyViewMode(mode: ViewMode) {
  const simple = mode === 'simple';
  prefs.showEffects = !simple;
  prefs.showLights = !simple;
  // the mood panel stays available in the player mode (only folded away), so its caret can unfold it
  prefs.filter = { presets: !simple, circumplex: !simple, sliders: !simple, bpm: !simple, tags: true, genres: true };
  prefs.moodCollapsed = mode !== 'complex';
  if (mode === 'player') prefs.dynamicColumns = true;
  savePrefs();
}
