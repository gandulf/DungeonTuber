// Videos announced once after the start (Shell.svelte): each user sees a video once, remembered on the server (videos_seen).
import type { UserState } from './types';

/** The 3 minute intro (login page and About dialog); a language without its own video falls back to the English one. */
export const INTRO_VIDEOS: Record<string, string> = { en: '85AZrB7YnOY', de: 'mWnSz5cADNA' };

export interface AnnouncedVideo {
  /** Remembered in videos_seen once shown. */
  key: string;
  /** Message id of the dialog title and text (translated with t()). */
  title: string;
  text: string;
  /** YouTube id per language; a language without its own video does not announce it. */
  youtube: Record<string, string>;
  /** Teasers (login page, About dialog): local thumbnail per language (the player loads from YouTube only after a click) and the teaser line. */
  thumb: Record<string, string>;
  teaser: string;
}

export const VIDEOS: AnnouncedVideo[] = [
  {
    key: 'adventures',
    title: 'New: Adventures',
    text: 'Prepare your sessions as adventures: scenes with notes, music and effects, the AI assistant at your side and the adventure mode for the game night.',
    youtube: { de: 'qnc-YPvEd8g' },
    thumb: { de: '/adventures-teaser.de.jpg' },
    teaser: 'Prepare and play adventures with music, effects and AI',
  },
];

/** The first video the user has not seen yet that exists in their language. */
export function nextVideo(user: UserState, lang: string): (AnnouncedVideo & { id: string }) | null {
  const video = VIDEOS.find((v) => v.youtube[lang] && !user.videos_seen.includes(v.key));
  return video ? { ...video, id: video.youtube[lang] } : null;
}
