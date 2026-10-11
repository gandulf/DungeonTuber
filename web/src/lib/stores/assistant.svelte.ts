import { api } from '../api';
import { t } from '../i18n.svelte';
import type { AssistantSong, SmartFilter } from '../types';
import { availableGenres, availableTags, filter, onFilterChanged, setGlobal } from './library.svelte';

export type ChatTurn =
  | { role: 'user'; content: string }
  /** `first` is the number of the first song in the running count of all suggestions. */
  | { role: 'assistant'; content: string; message: string; songs: AssistantSong[]; first: number; filter?: SmartFilter }
  | { role: 'error'; message: string; question: string };

/** "music" suggests songs for a scene, "general" answers questions about rules, the setting or the session, "smart" sets the filter
 *  so that the songs of the open tab are ranked for a scene (only songs of the library, nothing invented). */
export type AssistantMode = 'music' | 'general' | 'smart';
const MODES: AssistantMode[] = ['music', 'general', 'smart'];

interface Chat {
  turns: ChatTurn[];
  busy: boolean;
}

const MODE_KEY = 'dt-assistant-mode';

function storedMode(): AssistantMode {
  try {
    const mode = localStorage.getItem(MODE_KEY) as AssistantMode;
    return MODES.includes(mode) ? mode : 'music';
  } catch {
    return 'music';
  }
}

/** The chats with the AI assistant, one per mode; they live as long as the page, so closing the popup keeps them. */
export const assistant = $state({
  open: false,
  mode: storedMode(),
  chats: { music: { turns: [], busy: false }, general: { turns: [], busy: false }, smart: { turns: [], busy: false } } as Record<AssistantMode, Chat>,
});

export const SONGS_PER_ANSWER = 10;

/** The chat of the selected mode. */
export const currentChat = () => assistant.chats[assistant.mode];

export function toggleAssistant() {
  assistant.open = !assistant.open;
}

export function setMode(mode: AssistantMode) {
  assistant.mode = mode;
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    // the mode is only remembered when the browser allows it
  }
}

export function newChat() {
  const chat = currentChat();
  if (!chat.busy) chat.turns = [];
}

export const youtubeSearchUrl = (song: AssistantSong) =>
  `https://www.youtube.com/results?search_query=${encodeURIComponent([song.title, song.artist].filter(Boolean).join(' '))}`;

export async function ask(text: string) {
  text = text.trim();
  const mode = assistant.mode;
  const chat = assistant.chats[mode];
  if (!text || chat.busy) return;
  chat.turns = chat.turns.filter((turn) => turn.role !== 'error');
  chat.turns.push({ role: 'user', content: text });
  chat.busy = true;
  try {
    const history = chat.turns.flatMap((turn) => (turn.role === 'error' ? [] : [{ role: turn.role, content: turn.content }]));
    // the smart search ranks the whole library (global search) and may only pick tags and genres its songs have
    if (mode === 'smart') await setGlobal(true);
    const context = mode === 'smart' ? { tags: availableTags(), genres: availableGenres() } : undefined;
    const reply = await api.assistantChat(history, mode, context);
    const first = chat.turns.reduce((count, turn) => count + (turn.role === 'assistant' ? turn.songs.length : 0), 1);
    chat.turns.push({ role: 'assistant', content: reply.content, message: reply.message, songs: reply.songs, first, filter: reply.filter });
    if (mode === 'smart' && reply.filter) applyFilter(reply.filter);
    if (mode === 'music' && reply.songs.length) void checkSongs(chat.turns[chat.turns.length - 1]);
  } catch (e) {
    // the question leaves the conversation again, so asking once more does not send it twice
    chat.turns.pop();
    chat.turns.push({ role: 'error', message: e instanceof Error ? e.message : String(e), question: text });
  } finally {
    chat.busy = false;
  }
}

/** Sets the filter of the app (sliders, tags, genres, BPM) to the choice of the smart search; the table then ranks by it. */
export function applyFilter(chosen: SmartFilter) {
  void setGlobal(true);
  filter.categories = { ...chosen.categories };
  filter.tags = [...chosen.tags];
  filter.genres = [...chosen.genres];
  filter.bpm = chosen.bpm;
  onFilterChanged();
}

/** Looks the songs of an answer up on YouTube in the background (see server/songcheck.py); the list is shown meanwhile. */
async function checkSongs(turn: ChatTurn) {
  if (turn.role !== 'assistant') return;
  try {
    const { results } = await api.assistantVerify(turn.songs.map(({ title, artist }) => ({ title, artist })));
    turn.songs.forEach((song, index) => (song.check = results[index] ?? { found: null }));
  } catch {
    turn.songs.forEach((song) => (song.check = { found: null })); // unchecked, shown as before
  }
}

export function moreSongs() {
  return ask(t('Suggest {0} more songs for this scene, different from all songs before.', SONGS_PER_ANSWER));
}
