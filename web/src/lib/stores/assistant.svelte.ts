import { api } from '../api';
import { t } from '../i18n.svelte';
import type { AssistantReply, AssistantSong, ComposePiece, SmartFilter, Track } from '../types';
import { data } from './data.svelte';
import { availableGenres, availableTags, filter, onFilterChanged, setGlobal } from './library.svelte';

export type ChatTurn =
  | { role: 'user'; content: string }
  /** `first` is the number of the first song in the running count of all suggestions. */
  | { role: 'assistant'; content: string; message: string; songs: AssistantSong[]; first: number; filter?: SmartFilter; piece?: ComposePiece; takes?: Take[] }
  | { role: 'error'; message: string; question: string };

/** One generation of a composed piece; a variation is another take with a new seed. */
export interface Take {
  status: 'composing' | 'done' | 'error';
  track?: Track;
  seed?: number | null;
  error?: string;
}

/** "music" suggests songs for a scene, "general" answers questions about rules, the setting or the session, "smart" sets the filter
 *  so that the songs of the open tab are ranked for a scene (only songs of the library, nothing invented), "compose" lets the
 *  music generation (ACE-Step) compose a new piece for a scene. */
export type AssistantMode = 'music' | 'general' | 'smart' | 'compose';
const MODES: AssistantMode[] = ['music', 'general', 'smart', 'compose'];

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
  chats: { music: { turns: [], busy: false }, general: { turns: [], busy: false }, smart: { turns: [], busy: false },
           compose: { turns: [], busy: false } } as Record<AssistantMode, Chat>,
});

const COMPOSE_KEY = 'dt-compose-options';
export const COMPOSE_DURATIONS = [30, 60, 120, 180, 300];

function storedComposeOptions(): { duration: number; instrumental: boolean; language: string } {
  try {
    const stored = JSON.parse(localStorage.getItem(COMPOSE_KEY) ?? '{}');
    return { duration: COMPOSE_DURATIONS.includes(stored.duration) ? stored.duration : 120, instrumental: stored.instrumental !== false,
             language: typeof stored.language === 'string' ? stored.language : '' };
  } catch {
    return { duration: 120, instrumental: true, language: '' };
  }
}

/** The options of the compose mode: length, with or without vocals, the language of the lyrics ('' until chosen: the language of the
 *  app) and the folder the pieces are stored in. */
export const composeOptions = $state({ ...storedComposeOptions(), dir: '' });

export function saveComposeOptions() {
  try {
    localStorage.setItem(COMPOSE_KEY, JSON.stringify({ duration: composeOptions.duration, instrumental: composeOptions.instrumental,
                                                       language: composeOptions.language }));
  } catch {
    // the options are only remembered when the browser allows it
  }
}

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
    const context = mode === 'smart' ? { tags: availableTags(), genres: availableGenres() }
      : mode === 'compose' ? { instrumental: composeOptions.instrumental, duration: composeOptions.duration,
                               ...(composeOptions.instrumental || !composeOptions.language ? {} : { language: composeOptions.language }) } : undefined;
    const described = data.settings?.groqConfigured || data.settings?.assistantConfigured;
    const reply = mode === 'compose' && !described ? describeYourself(text) : await api.assistantChat(history, mode, context);
    const first = chat.turns.reduce((count, turn) => count + (turn.role === 'assistant' ? turn.songs.length : 0), 1);
    chat.turns.push({ role: 'assistant', content: reply.content, message: reply.message, songs: reply.songs, first, filter: reply.filter,
                      piece: reply.piece, takes: reply.piece ? [] : undefined });
    if (mode === 'smart' && reply.filter) applyFilter(reply.filter);
    if (mode === 'compose' && reply.piece) void compose(chat.turns[chat.turns.length - 1]);
    if (mode === 'music' && reply.songs.length) void checkSongs(chat.turns[chat.turns.length - 1]);
  } catch (e) {
    // the question leaves the conversation again, so asking once more does not send it twice
    chat.turns.pop();
    chat.turns.push({ role: 'error', message: e instanceof Error ? e.message : String(e), question: text });
  } finally {
    chat.busy = false;
  }
}

/** Without an AI service (Groq or Gemini) the text of the user is the description of the piece. */
function describeYourself(text: string): AssistantReply {
  const piece: ComposePiece = { title: text.split(/[,.;\n]/)[0].trim().slice(0, 60), caption: text.slice(0, 512), lyrics: '', language: composeOptions.instrumental ? '' : composeOptions.language,
                                instrumental: composeOptions.instrumental, bpm: null };
  return { content: text, message: '', songs: [], piece };
}

/** Lets the music generation compose the piece of an answer (once more for a variation) and stores it in the chosen folder. */
export async function compose(turn: ChatTurn) {
  if (turn.role !== 'assistant' || !turn.piece || !turn.takes) return;
  turn.takes.push({ status: 'composing' });
  const take = turn.takes[turn.takes.length - 1];
  try {
    if (!composeOptions.dir) throw new Error(t('Choose a folder for the composed pieces first.'));
    const result = await api.compose({ ...turn.piece, dir: composeOptions.dir, duration: composeOptions.duration });
    Object.assign(take, { status: 'done', track: result.track, seed: result.seed });
  } catch (e) {
    Object.assign(take, { status: 'error', error: e instanceof Error ? e.message : String(e) });
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
