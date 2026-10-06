<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { setVolume, toggleMute } from '../../lib/stores/player.svelte';
  import Icon from '../Icon.svelte';

  let { volume = undefined, onchange = undefined, onmute = undefined, muted = undefined, compact = false }: {
    volume?: number; onchange?: (v: number) => void; onmute?: () => void; muted?: boolean; compact?: boolean;
  } = $props();

  const value = $derived(volume ?? prefs.volume);
  const isMuted = $derived(muted ?? prefs.muted);
  const shown = $derived(isMuted ? 0 : value);
</script>

<div class="volume" class:compact>
  <button class="icon-btn" title="{t('Mute')} (Ctrl+M)" onclick={() => (onmute ?? toggleMute)()}>
    <Icon name={isMuted || value === 0 ? 'volume-x' : 'volume'} size={18} />
  </button>
  <input class="range" class:boost={value > 100} type="range" min="0" max="150" step="1" value={shown} aria-label={t('Volume')}
         style:--pct="{(shown / 150) * 100}%"
         oninput={(e) => (onchange ?? setVolume)(Number((e.currentTarget as HTMLInputElement).value))} />
  <span class="pct">{shown}%</span>
</div>

<style>
  .volume { display: flex; align-items: center; gap: 8px; }
  input { width: 130px; }
  .compact input { width: auto; flex: 1; }
  .compact { flex: 1; }
  input.boost { background: linear-gradient(to right, var(--accent) 0, var(--accent-2) 66.6%, var(--gold) 66.6%, var(--gold) var(--pct), var(--surface-3) var(--pct)); }
  .pct { font-size: var(--fs-xs); color: var(--muted); width: 36px; font-variant-numeric: tabular-nums; text-align: right; }
</style>
