<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import Icon from '../Icon.svelte';

  let { value, onchange }: { value: number | null; onchange: (value: number | null) => void } = $props();
  let dragging = $state<number | null>(null);
  const shown = $derived(dragging ?? value ?? 0);
</script>

<div class="row" class:off={!shown} title={t('BPM (Beats per Minute)')}>
  <span class="icon"><Icon name="activity" size={17} /></span>
  <span class="name">{t('BPM')}</span>
  <input class="range" type="range" min="0" max="200" step="20" value={shown} aria-label={t('BPM')} style:--pct="{(shown / 200) * 100}%"
         oninput={(e) => (dragging = Number((e.currentTarget as HTMLInputElement).value))}
         onchange={(e) => { const v = Number((e.currentTarget as HTMLInputElement).value); dragging = null; onchange(v === 0 ? null : v); }}
         ondblclick={() => onchange(null)} />
  <span class="value">{shown || '–'}</span>
  {#if value}<button class="clear" aria-label="clear" onclick={() => onchange(null)}>×</button>{:else}<span></span>{/if}
</div>

<style>
  .row { display: grid; grid-template-columns: 22px minmax(70px, 110px) 1fr 26px 18px; align-items: center; gap: 10px; min-height: 31px; }
  .icon { color: var(--gold); display: flex; }
  .value { font-variant-numeric: tabular-nums; text-align: right; font-weight: 600; font-size: var(--fs-sm); }
  .off .icon, .off .value { color: var(--faint); }
  .off .name { color: var(--muted); }
  .off input { opacity: 0.55; }
  .clear { color: var(--faint); font-size: 16px; line-height: 1; border-radius: 4px; }
  .clear:hover { color: var(--text); background: var(--hover); }
</style>
