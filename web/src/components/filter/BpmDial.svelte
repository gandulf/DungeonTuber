<script lang="ts">
  import { t } from '../../lib/i18n.svelte';

  let { value, onchange }: { value: number | null; onchange: (value: number | null) => void } = $props();

  const steps = Array.from({ length: 11 }, (_, i) => i * 20); // 0 = off
  const current = $derived(value ?? 0);

  function set(event: Event) {
    const v = Number((event.currentTarget as HTMLInputElement).value);
    onchange(v === 0 ? null : v);
  }
</script>

<div class="bpm" title={t('BPM (Beats per Minute)')}>
  <span class="value" class:off={!value}>{value ? `${value}` : '–'}</span>
  <input type="range" min="0" max="200" step="20" value={current} onchange={set} list="bpm-steps" aria-label={t('BPM')}
         ondblclick={() => onchange(null)} />
  <datalist id="bpm-steps">{#each steps as step (step)}<option value={step}></option>{/each}</datalist>
  <span class="name">{t('BPM')}</span>
</div>

<style>
  .bpm { display: flex; flex-direction: column; align-items: center; gap: 4px; width: 66px; flex: none; }
  .value { font-size: var(--fs-sm); font-weight: 600; }
  .value.off { color: var(--muted); font-weight: 400; }
  input { writing-mode: vertical-lr; direction: rtl; height: 104px; width: 22px; margin: 0; }
  .name { font-size: var(--fs-xs); color: var(--muted); }
</style>
