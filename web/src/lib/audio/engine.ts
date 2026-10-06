// Web Audio playback: two music decks for crossfading, a compressor for volume normalization and
// a separate looping effects bus. The current track is also downloaded completely in the background so
// playback can continue from memory if the connection drops.

export interface DeckCallbacks {
  onTime(position: number, duration: number): void;
  onEnded(): void;
  onError(message: string): void;
  onState(playing: boolean): void;
}

const CROSSFADE_SECONDS = 1;

/** Perceptual volume curve used by the desktop app: 0..150 -> gain (v/100)^2 */
export function volumeToGain(volume: number, muted = false): number {
  if (muted) return 0;
  const v = Math.max(0, Math.min(150, volume)) / 100;
  return v * v;
}

class Deck {
  readonly audio = new Audio();
  gain: GainNode | null = null;
  blobUrl: string | null = null;
  streamUrl: string | null = null;
  private abort: AbortController | null = null;

  constructor() {
    this.audio.preload = 'auto';
    this.audio.crossOrigin = 'use-credentials';
  }

  connect(ctx: AudioContext, destination: AudioNode) {
    if (this.gain) return;
    const source = ctx.createMediaElementSource(this.audio);
    this.gain = ctx.createGain();
    source.connect(this.gain).connect(destination);
  }

  load(url: string) {
    this.release();
    this.streamUrl = url;
    this.audio.src = url;
    this.precache(url);
  }

  private async precache(url: string) {
    this.abort = new AbortController();
    try {
      const response = await fetch(url, { credentials: 'same-origin', signal: this.abort.signal });
      if (!response.ok) return;
      const blob = await response.blob();
      if (this.streamUrl === url) this.blobUrl = URL.createObjectURL(blob);
    } catch { /* aborted or offline - streaming continues */ }
  }

  /** Continue from the in-memory copy (after a network error). */
  fallbackToBlob(): boolean {
    if (!this.blobUrl || this.audio.src === this.blobUrl) return false;
    const time = this.audio.currentTime;
    const playing = !this.audio.paused;
    this.audio.src = this.blobUrl;
    this.audio.currentTime = time;
    if (playing) void this.audio.play();
    return true;
  }

  release() {
    this.abort?.abort();
    this.abort = null;
    if (this.blobUrl) URL.revokeObjectURL(this.blobUrl);
    this.blobUrl = null;
    this.streamUrl = null;
  }

  stop() {
    this.audio.pause();
    this.audio.removeAttribute('src');
    this.audio.load();
    this.release();
  }
}

export class AudioEngine {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private compressor: DynamicsCompressorNode | null = null;
  private musicBus: GainNode | null = null;
  private effectsBus: GainNode | null = null;
  private decks = [new Deck(), new Deck()];
  private active = 0;
  private effect = new Audio();
  private effectConnected = false;
  private callbacks: DeckCallbacks;
  private normalize = true;
  private fadeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(callbacks: DeckCallbacks) {
    this.callbacks = callbacks;
    this.effect.loop = true;
    this.effect.crossOrigin = 'use-credentials';
    this.decks.forEach((deck, index) => {
      const audio = deck.audio;
      audio.addEventListener('timeupdate', () => index === this.active && this.callbacks.onTime(audio.currentTime, audio.duration || 0));
      audio.addEventListener('durationchange', () => index === this.active && this.callbacks.onTime(audio.currentTime, audio.duration || 0));
      audio.addEventListener('ended', () => index === this.active && this.callbacks.onEnded());
      audio.addEventListener('play', () => index === this.active && this.callbacks.onState(true));
      audio.addEventListener('pause', () => index === this.active && this.callbacks.onState(false));
      audio.addEventListener('error', () => {
        if (index !== this.active || !audio.getAttribute('src')) return;
        if (!deck.fallbackToBlob()) this.callbacks.onError(audio.error?.message || 'Error loading file');
      });
      audio.addEventListener('stalled', () => index === this.active && !navigator.onLine && deck.fallbackToBlob());
    });
  }

  private ensureContext() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') void this.ctx.resume();
      return;
    }
    this.ctx = new AudioContext();
    this.master = this.ctx.createGain();
    this.master.connect(this.ctx.destination);
    this.compressor = this.ctx.createDynamicsCompressor();
    this.compressor.threshold.value = -24;
    this.compressor.ratio.value = 4;
    this.musicBus = this.ctx.createGain();
    this.effectsBus = this.ctx.createGain();
    this.effectsBus.connect(this.master);
    this.routeMusic();
    this.decks.forEach((deck) => deck.connect(this.ctx!, this.musicBus!));
  }

  private routeMusic() {
    if (!this.musicBus || !this.compressor || !this.master) return;
    this.musicBus.disconnect();
    this.compressor.disconnect();
    if (this.normalize) {
      this.musicBus.connect(this.compressor).connect(this.master);
    } else {
      this.musicBus.connect(this.master);
    }
  }

  setNormalize(enabled: boolean) {
    this.normalize = enabled;
    this.routeMusic();
  }

  // Volumes are remembered until the AudioContext exists (it may only be created after a user gesture).
  private pendingVolume = 0.49;
  private pendingEffectsVolume = 0.49;

  setVolume(volume: number, muted: boolean) {
    this.pendingVolume = volumeToGain(volume, muted);
    this.applyPendingVolumes();
  }

  setEffectsVolume(volume: number, muted: boolean) {
    this.pendingEffectsVolume = volumeToGain(volume, muted);
    this.applyPendingVolumes();
  }

  private applyPendingVolumes() {
    if (this.musicBus) this.musicBus.gain.value = this.pendingVolume;
    if (this.effectsBus) this.effectsBus.gain.value = this.pendingEffectsVolume;
  }

  get current(): HTMLAudioElement {
    return this.decks[this.active].audio;
  }

  async play(url: string, crossfade: boolean) {
    this.ensureContext();
    this.applyPendingVolumes();
    const previous = this.decks[this.active];
    const fade = crossfade && !previous.audio.paused && !!previous.audio.getAttribute('src') && !!this.ctx;

    if (this.fadeTimer) {
      clearTimeout(this.fadeTimer);
      this.fadeTimer = null;
    }

    if (fade) {
      this.active = 1 - this.active;
    } else {
      previous.stop();
    }

    const deck = this.decks[this.active];
    deck.load(url);
    const now = this.ctx!.currentTime;
    if (fade) {
      deck.gain!.gain.cancelScheduledValues(now);
      deck.gain!.gain.setValueAtTime(0, now);
      deck.gain!.gain.linearRampToValueAtTime(1, now + CROSSFADE_SECONDS);
      previous.gain!.gain.cancelScheduledValues(now);
      previous.gain!.gain.setValueAtTime(previous.gain!.gain.value, now);
      previous.gain!.gain.linearRampToValueAtTime(0, now + CROSSFADE_SECONDS);
      this.fadeTimer = setTimeout(() => previous.stop(), CROSSFADE_SECONDS * 1000 + 50);
    } else {
      deck.gain!.gain.cancelScheduledValues(now);
      deck.gain!.gain.setValueAtTime(1, now);
    }
    try {
      await deck.audio.play();
    } catch (e) {
      if ((e as DOMException).name !== 'AbortError') this.callbacks.onError(String((e as Error).message ?? e));
    }
  }

  resume() {
    this.ensureContext();
    this.applyPendingVolumes();
    void this.current.play().catch(() => undefined);
  }

  pause() {
    this.current.pause();
  }

  stop() {
    this.decks.forEach((deck) => deck.stop());
    this.callbacks.onState(false);
  }

  seek(seconds: number) {
    const audio = this.current;
    if (Number.isFinite(seconds)) audio.currentTime = Math.max(0, Math.min(seconds, audio.duration || seconds));
  }

  // --- effects bus ---
  playEffect(url: string) {
    this.ensureContext();
    this.applyPendingVolumes();
    if (!this.effectConnected && this.ctx && this.effectsBus) {
      this.ctx.createMediaElementSource(this.effect).connect(this.effectsBus);
      this.effectConnected = true;
    }
    if (this.effect.getAttribute('src') !== url) this.effect.src = url;
    void this.effect.play().catch(() => undefined);
  }

  switchEffect(url: string) {
    const playing = !this.effect.paused;
    this.effect.src = url;
    if (playing) void this.effect.play().catch(() => undefined);
  }

  pauseEffect() {
    this.effect.pause();
  }

  get effectPlaying(): boolean {
    return !this.effect.paused;
  }
}
