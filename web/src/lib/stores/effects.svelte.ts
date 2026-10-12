import { api } from '../api';
import { cached } from '../cache';
import { affectsDirectory } from '../paths';
import type { Effect, Track } from '../types';
import { errorToast } from './ui.svelte';

export const effects = $state({
  directory: null as string | null,
  list: [] as Effect[],
  loading: false,
  search: '',
});

export async function loadEffects() {
  effects.loading = true;
  try {
    // the effects of the last start show at once, the current ones replace them when they differ
    await cached('effects', () => api.effects(), (result) => {
      effects.directory = result.directory;
      effects.list = result.effects;
    });
  } catch (e) {
    errorToast(e);
  } finally {
    effects.loading = false;
  }
}

let reloadTimer: ReturnType<typeof setTimeout> | undefined;

/** Reloads the effects after a change of the library; an import that changes many files reloads once. */
export function effectsChanged(path: string) {
  if (!affectsDirectory(path, effects.directory)) return;
  clearTimeout(reloadTimer);
  reloadTimer = setTimeout(() => void loadEffects(), 300);
}

export function updateEffectTrack(track: Track) {
  for (const effect of effects.list) {
    const index = effect.intensities.findIndex((t) => t.id === track.id || t.id === track.previous_id);
    if (index >= 0) effect.intensities[index] = { ...track, favorite: track.favorite ?? effect.intensities[index].favorite };
  }
}
