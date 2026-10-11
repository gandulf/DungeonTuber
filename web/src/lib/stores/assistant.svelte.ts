import { api } from '../api';
import { t } from '../i18n.svelte';
import type { AssistantSong } from '../types';

export type ChatTurn =
  | { role: 'user'; content: string }
  /** `first` is the number of the first song in the running count of all suggestions. */
  | { role: 'assistant'; content: string; message: string; songs: AssistantSong[]; first: number }
  | { role: 'error'; message: string; question: string };

/** "music" suggests songs for a scene, "general" answers questions about rules, the setting or the session. */
export type AssistantMode = 'music' | 'general';

interface Chat {
  turns: ChatTurn[];
  busy: boolean;
}

const MODE_KEY = 'dt-assistant-mode';

function storedMode(): AssistantMode {
  try {
    return localStorage.getItem(MODE_KEY) === 'general' ? 'general' : 'music';
  } catch {
    return 'music';
  }
}

/** The chats with the AI assistant, one per mode; they live as long as the page, so closing the popup keeps them. */
export const assistant = $state({
  open: false,
  mode: storedMode(),
  chats: { music: { turns: [], busy: false }, general: { turns: [], busy: false } } as Record<AssistantMode, Chat>,
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
    const reply = await api.assistantChat(history, mode);
    const first = chat.turns.reduce((count, turn) => count + (turn.role === 'assistant' ? turn.songs.length : 0), 1);
    chat.turns.push({ role: 'assistant', content: reply.content, message: reply.message, songs: reply.songs, first });
  } catch (e) {
    // the question leaves the conversation again, so asking once more does not send it twice
    chat.turns.pop();
    chat.turns.push({ role: 'error', message: e instanceof Error ? e.message : String(e), question: text });
  } finally {
    chat.busy = false;
  }
}

export function moreSongs() {
  return ask(t('Suggest {0} more songs for this scene, different from all songs before.', SONGS_PER_ANSWER));
}
