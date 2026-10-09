import { api, coverUrl, mediaUrl } from '../api';
import { AudioEngine } from '../audio/engine';
import { t } from '../i18n.svelte';
import { prefs, savePrefs } from '../prefs.svelte';
import type { Chapter, Effect, LightSetting, PlayerSettings, Track } from '../types';
import { visibleRows } from './library.svelte';

export const player = $state({
  track: null as Track | null,
  playing: false,
  position: 0, // seconds
  duration: 0,
  error: null as string | null,
  effect: null as Effect | null,
  effectIntensity: 0,
  effectPlaying: false,
});

const CHAPTER_WINDOW = 3; // seconds after a chapter start in which it still fires
let firedChapters = new Set<number>();
let lastPosition = 0;

const engine = new AudioEngine({
  onTime(position, duration) {
    player.position = position;
    player.duration = Number.isFinite(duration) ? duration : 0;
    checkChapters(position);
  },
  onEnded() {
    if (prefs.repeat === 'single' && player.track) {
      void playTrack(player.track, false);
    } else {
      next(true);
    }
  },
  onError(message) {
    player.error = message || t('Error loading file');
    player.playing = false;
  },
  onState(playing) {
    player.playing = playing;
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = playing ? 'playing' : 'paused';
  },
});

export function applyAudioPrefs() {
  engine.setVolume(prefs.volume, prefs.muted);
  engine.setEffectsVolume(prefs.effectsVolume, false);
  engine.setNormalize(prefs.normalize);
}

// --- the player options of the signed in user ---
// They are kept on the server with the user profile, so every device starts with the same shuffle, repeat, volume, normalization, crossfade and dynamic table columns.
const currentSettings = (): PlayerSettings => ({ shuffle: prefs.shuffle, repeat: prefs.repeat, volume: prefs.volume, muted: prefs.muted, effectsVolume: prefs.effectsVolume, normalize: prefs.normalize, crossfade: prefs.crossfade,
  dynamicScore: prefs.dynamicScore, dynamicColumns: prefs.dynamicColumns });
let known = ''; // what the server has (or is being sent)
let settingsLoaded = $state(false);

/** Applies the options saved in the profile; a profile without them keeps (and from then on saves) what this browser has. */
export function applyPlayerSettings(saved: PlayerSettings | null) {
  if (saved) {
    Object.assign(prefs, saved);
    known = JSON.stringify(currentSettings());
    savePrefs();
  }
  applyAudioPrefs();
  settingsLoaded = true;
}

$effect.root(() => {
  $effect(() => {
    const serialized = JSON.stringify(currentSettings());
    if (!settingsLoaded || serialized === known) return;
    const timer = setTimeout(() => {
      known = serialized;
      void api.putUserState({ player: JSON.parse(serialized) }).catch(() => undefined);
    }, 500);
    return () => clearTimeout(timer);
  });
});

export function cueLight(setting: LightSetting | null | undefined) {
  if (!setting) return;
  void api.cue(setting).catch(() => undefined);
}

function checkChapters(position: number) {
  const track = player.track;
  if (!track?.chapters.length) return;
  if (position < lastPosition - 0.5) firedChapters = new Set([...firedChapters].filter((time) => time / 1000 < position));
  lastPosition = position;
  for (const chapter of track.chapters) {
    const start = chapter.time / 1000;
    if (position >= start && position < start + CHAPTER_WINDOW && !firedChapters.has(chapter.time)) {
      firedChapters.add(chapter.time);
      if (chapter.time > 0 || position < CHAPTER_WINDOW) cueLight(chapter.light);
    }
  }
}

function updateMediaSession(track: Track) {
  if (!('mediaSession' in navigator)) return;
  navigator.mediaSession.metadata = new MediaMetadata({
    title: track.title || track.name,
    artist: track.artist ?? '',
    album: track.album ?? '',
    artwork: track.has_cover ? [{ src: coverUrl(track.id, 512), sizes: '512x512', type: 'image/jpeg' }] : [],
  });
}

export async function playTrack(track: Track, crossfade = prefs.crossfade) {
  player.track = track;
  player.error = null;
  player.position = 0;
  firedChapters = new Set();
  lastPosition = 0;
  cueLight(track.light);
  updateMediaSession(track);
  await engine.play(mediaUrl(track.id), crossfade);
}

export function togglePlay() {
  if (!player.track) {
    const first = visibleRows()[0];
    if (first) void playTrack(first.track);
    return;
  }
  if (player.playing) engine.pause();
  else engine.resume();
}

export function stop() {
  engine.stop();
}

function neighbour(offset: number): Track | null {
  const rows = visibleRows();
  if (!rows.length) return null;
  if (prefs.shuffle && offset > 0 && rows.length > 1) {
    const candidates = rows.filter((row) => row.track.id !== player.track?.id);
    return candidates[Math.floor(Math.random() * candidates.length)].track;
  }
  const index = player.track ? rows.findIndex((row) => row.track.id === player.track!.id) : -1;
  let target = index + offset;
  if (target >= rows.length) {
    if (prefs.repeat !== 'all') return null;
    target = 0;
  }
  if (target < 0) target = prefs.repeat === 'all' ? rows.length - 1 : 0;
  return rows[target]?.track ?? null;
}

export function next(auto = false) {
  const track = neighbour(1);
  if (track) void playTrack(track);
  else if (auto) engine.stop();
}

export function previous() {
  if (player.position > 3) {
    engine.seek(0);
    return;
  }
  const track = neighbour(-1);
  if (track) void playTrack(track);
}

export function seek(seconds: number) {
  engine.seek(seconds);
}

export function seekToChapter(chapter: Chapter) {
  firedChapters.delete(chapter.time);
  engine.seek(chapter.time / 1000);
}

export function setVolume(volume: number) {
  prefs.volume = Math.round(Math.max(0, Math.min(150, volume)));
  prefs.muted = false;
  engine.setVolume(prefs.volume, prefs.muted);
  savePrefs();
}

export function toggleMute() {
  prefs.muted = !prefs.muted;
  engine.setVolume(prefs.volume, prefs.muted);
  savePrefs();
}

export function cycleRepeat() {
  prefs.repeat = prefs.repeat === 'none' ? 'all' : prefs.repeat === 'all' ? 'single' : 'none';
  savePrefs();
}

export function toggleShuffle() {
  prefs.shuffle = !prefs.shuffle;
  savePrefs();
}

export function refreshCurrentTrack(track: Track) {
  if (player.track && (player.track.id === track.id || player.track.id === track.previous_id)) {
    player.track = { ...track, favorite: track.favorite ?? player.track.favorite };
  }
}

// --- effects ---------------------------------------------------------------

export function playEffect(effect: Effect, intensity = 0) {
  const variant = effect.intensities[Math.min(intensity, effect.intensities.length - 1)];
  if (!variant) return;
  if (player.effect?.id === effect.id && player.effectIntensity === intensity && player.effectPlaying) {
    engine.pauseEffect();
    player.effectPlaying = false;
    return;
  }
  player.effect = effect;
  player.effectIntensity = intensity;
  engine.playEffect(mediaUrl(variant.id));
  player.effectPlaying = true;
  cueLight(variant.light);
}

export function setEffectIntensity(intensity: number) {
  const effect = player.effect;
  if (!effect) return;
  player.effectIntensity = intensity;
  const variant = effect.intensities[intensity];
  if (variant) {
    engine.switchEffect(mediaUrl(variant.id));
    cueLight(variant.light);
  }
}

export function toggleEffect() {
  if (!player.effect) return;
  if (engine.effectPlaying) {
    engine.pauseEffect();
    player.effectPlaying = false;
  } else {
    engine.playEffect(mediaUrl(player.effect.intensities[player.effectIntensity].id));
    player.effectPlaying = true;
  }
}

export function setEffectsVolume(volume: number) {
  prefs.effectsVolume = Math.round(Math.max(0, Math.min(150, volume)));
  engine.setEffectsVolume(prefs.effectsVolume, false);
  savePrefs();
}

export function setNormalize(enabled: boolean) {
  prefs.normalize = enabled;
  engine.setNormalize(enabled);
  savePrefs();
}

if ('mediaSession' in navigator) {
  navigator.mediaSession.setActionHandler('play', () => togglePlay());
  navigator.mediaSession.setActionHandler('pause', () => togglePlay());
  navigator.mediaSession.setActionHandler('nexttrack', () => next());
  navigator.mediaSession.setActionHandler('previoustrack', () => previous());
}
