<script lang="ts" module>
  const ICONS: Record<string, string> = {
    Valence: 'smile', Arousal: 'bolt', Engagement: 'activity', Darkness: 'moon', Aggressive: 'flame', Happy: 'sun',
    Party: 'sparkles', Relaxed: 'leaf', Sad: 'drop', Tonal: 'waves',
  };
</script>

<script lang="ts">
  import type { MusicCategory } from '../../lib/types';
  import Icon from '../Icon.svelte';

  let { category, value, onchange }: { category: MusicCategory; value: number | null; onchange: (value: number | null) => void } = $props();

  let dragging = $state<number | null>(null);
  const shown = $derived(dragging ?? value);
  const levels = $derived(Object.entries(category.levels).map(([k, v]) => [Number(k), v] as const).sort((a, b) => a[0] - b[0]));
  const icon = $derived(ICONS[category.key] ?? 'sliders');

  function levelText(v: number | null): string {
    if (v === null || !levels.length) return '';
    let best = levels[0];
    for (const level of levels) if (Math.abs(level[0] - v) < Math.abs(best[0] - v)) best = level;
    return best[1];
  }
</script>

<div class="row" class:off={shown === null} title={category.description + '\n' + levels.map(([k, v]) => `${k}: ${v}`).join('\n')}>
  <span class="icon"><Icon name={icon} size={17} /></span>
  <span class="name ellipsis">{category.name}</span>
  <input class="range" type="range" min="0" max="10" step="1" value={shown ?? 0} aria-label={category.name}
         style:--pct="{shown === null ? 0 : shown * 10}%"
         oninput={(e) => (dragging = Number((e.currentTarget as HTMLInputElement).value))}
         onchange={(e) => { const v = Number((e.currentTarget as HTMLInputElement).value); dragging = null; onchange(v); }}
         ondblclick={() => onchange(null)} />
  <span class="value">{shown ?? '–'}</span>
  {#if shown !== null}
    <button class="clear" aria-label="clear" title={levelText(shown)} onclick={() => onchange(null)}>×</button>
  {:else}
    <span class="clear-space"></span>
  {/if}
  {#if dragging !== null}<span class="tip">{levelText(dragging)}</span>{/if}
</div>

<style>
  .row { position: relative; display: grid; grid-template-columns: 22px minmax(70px, 110px) 1fr 26px 18px; align-items: center; gap: 10px; min-height: 31px; }
  .icon { color: var(--accent); display: flex; }
  .name { font-size: var(--fs); }
  .value { font-variant-numeric: tabular-nums; text-align: right; font-weight: 600; font-size: var(--fs-sm); }
  .off .icon, .off .value { color: var(--faint); }
  .off .name { color: var(--muted); }
  .off input { opacity: 0.55; }
  .clear { color: var(--faint); font-size: 16px; line-height: 1; border-radius: 4px; }
  .clear:hover { color: var(--text); background: var(--hover); }
  .tip { position: absolute; right: 48px; top: -18px; background: var(--text); color: var(--bg); padding: 2px 8px; border-radius: 6px; font-size: var(--fs-xs); white-space: nowrap; pointer-events: none; z-index: 5; }
</style>
