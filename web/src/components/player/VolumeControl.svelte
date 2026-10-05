<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { setVolume, toggleMute } from '../../lib/stores/player.svelte';
  import Icon from '../Icon.svelte';

  let { volume = undefined, onchange = undefined, onmute = undefined, muted = undefined }: {
    volume?: number; onchange?: (v: number) => void; onmute?: () => void; muted?: boolean;
  } = $props();

  const value = $derived(volume ?? prefs.volume);
  const isMuted = $derived(muted ?? prefs.muted);
</script>

<div class="volume">
  <button class="icon-btn" title="{t('Mute')} (Ctrl+M)" onclick={() => (onmute ?? toggleMute)()}>
    <Icon name={isMuted || value === 0 ? 'volume-x' : 'volume'} size={17} />
  </button>
  <input type="range" min="0" max="150" step="1" value={isMuted ? 0 : value} aria-label={t('Volume')}
         style:--pct="{((isMuted ? 0 : value) / 150) * 100}%" class:boost={value > 100}
         oninput={(e) => (onchange ?? setVolume)(Number((e.currentTarget as HTMLInputElement).value))} />
  <span class="pct">{isMuted ? 0 : value}%</span>
</div>

<style>
  .volume { display: flex; align-items: center; gap: 6px; }
  input { width: 110px; appearance: none; height: 5px; border-radius: 3px; background: linear-gradient(to right, var(--accent) var(--pct), var(--surface-3) var(--pct)); cursor: pointer; }
  input.boost { background: linear-gradient(to right, var(--accent) 66.6%, #f59e0b 66.6%, #f59e0b var(--pct), var(--surface-3) var(--pct)); }
  input::-webkit-slider-thumb { appearance: none; width: 13px; height: 13px; border-radius: 50%; background: var(--surface); border: 3px solid var(--accent); }
  input::-moz-range-thumb { width: 9px; height: 9px; border-radius: 50%; background: var(--surface); border: 3px solid var(--accent); }
  .pct { font-size: var(--fs-xs); color: var(--muted); width: 34px; font-variant-numeric: tabular-nums; }
</style>
