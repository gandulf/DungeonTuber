import { data } from './stores/data.svelte';

/** What the guided tour (components/Tour.svelte) shows for a step. `text` and `title` are message ids of the locale files.
 *  Steps the user has not seen are announced by a "What's new" tour of just those steps, except the ones marked `news: false`
 *  (they only explain a dialog or a menu entry that belongs to another step). Never rename or reuse an id: the ids a user has seen are stored on the server. */
export interface TourInfo {
  id: string;
  text: string;
  title: string;
  news?: false;
  /** The step is announced only when the feature is available to the user. */
  available?: () => boolean;
}

export const TOUR_INFO: TourInfo[] = [
  { id: 'tree', title: 'Music library', text: 'Tour Directory Tree' },
  { id: 'upload', title: 'Upload and import', text: 'Tour Upload' },
  { id: 'menu-upload', title: 'Upload songs', text: 'Tour Menu Upload', news: false },
  { id: 'upload-dialog', title: 'Upload songs', text: 'Tour Upload Dialog', news: false },
  { id: 'menu-import', title: 'Import from YouTube', text: 'Tour Menu Import', news: false },
  { id: 'import-dialog', title: 'Import from YouTube', text: 'Tour Import Dialog', news: false },
  { id: 'table', title: 'Song table', text: 'Tour Song Table' },
  { id: 'menu-edit', title: 'Edit songs', text: 'Tour Menu Edit', news: false },
  { id: 'edit-song', title: 'Edit songs', text: 'Tour Edit Song', news: false },
  { id: 'analyze', title: 'Analyze songs', text: 'Tour Analyze', available: () => data.settings?.voxalyzerActive !== false },
  { id: 'russel', title: 'Mood map', text: 'Tour Russel Widget' },
  { id: 'slider', title: 'Category sliders', text: 'Tour Category Slider' },
  { id: 'bpm', title: 'BPM dial', text: 'Tour BPM Widget' },
  { id: 'tags', title: 'Tags', text: 'Tour Tags Widget' },
  { id: 'presets', title: 'Presets', text: 'Tour Presets Widget' },
  { id: 'player', title: 'Player', text: 'Tour Player' },
  { id: 'effects', title: 'Effects', text: 'Tour Effectslist' },
  { id: 'lights', title: 'Lights', text: 'Tour Lights' },
  { id: 'tabs', title: 'Tabs', text: 'Tour Tabs' },
  { id: 'search', title: 'Search', text: 'Tour Search' },
  { id: 'global-search', title: 'Browse and Explore', text: 'Tour Global Search' },
  {
    id: 'assistant', title: 'AI Assistant', text: 'Tour AI Assistant',
    available: () => !!(data.settings?.assistantConfigured || data.settings?.groqConfigured || data.settings?.musicGenConfigured || data.settings?.soundGenConfigured)
      || data.auth?.is_admin !== false,
  },
  { id: 'menubar', title: 'Main menu', text: 'Tour Menubar' },
  { id: 'view-modes', title: 'View modes', text: 'Tour View Modes' },
];

/** The steps of the tour before the seen steps were stored: users who finished the tour back then have seen these. */
const LEGACY_STEPS = TOUR_INFO.map((info) => info.id).filter((id) => id !== 'global-search' && id !== 'assistant');

export const tourInfo = (id: string) => TOUR_INFO.find((info) => info.id === id);

/** The announceable steps this user has not seen in the tour; none while the user has not finished the tour (it shows everything then). */
export function unseenTourSteps(): TourInfo[] {
  const user = data.user;
  if (!user.tour_done) return [];
  const seen = new Set(user.tour_seen.length ? user.tour_seen : LEGACY_STEPS);
  return TOUR_INFO.filter((info) => info.news !== false && !seen.has(info.id) && (info.available?.() ?? true));
}
