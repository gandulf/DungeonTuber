<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { activeTab } from '../../lib/stores/library.svelte';
  import Icon from '../Icon.svelte';

  let { valence, arousal, onchange }: { valence: number | null; arousal: number | null; onchange: (valence: number | null, arousal: number | null) => void } = $props();

  const SIZE = 150;
  let svg = $state<SVGSVGElement | null>(null);
  let drag = $state<{ v: number; a: number } | null>(null);

  const point = $derived(drag ?? (valence !== null && arousal !== null ? { v: valence, a: arousal } : null));
  const scatter = $derived(
    (activeTab()?.tracks ?? [])
      .map((track) => ({ v: track.categories.Valence, a: track.categories.Arousal }))
      .filter((p) => typeof p.v === 'number' && typeof p.a === 'number')
      .slice(0, 2000),
  );

  const toX = (v: number) => (v / 10) * SIZE;
  const toY = (a: number) => SIZE - (a / 10) * SIZE;

  function valueAt(event: PointerEvent) {
    const rect = svg!.getBoundingClientRect();
    const clamp = (n: number) => Math.round(Math.max(0, Math.min(10, n)) * 2) / 2;
    return { v: clamp(((event.clientX - rect.left) / rect.width) * 10), a: clamp((1 - (event.clientY - rect.top) / rect.height) * 10) };
  }

  function down(event: PointerEvent) {
    drag = valueAt(event);
    (event.currentTarget as Element).setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent) {
    if (drag) drag = valueAt(event);
  }

  function up() {
    if (!drag) return;
    const { v, a } = drag;
    drag = null;
    onchange(v, a);
  }
</script>

<div class="circumplex" title={t('Circumplex model of emotion')}>
  <svg bind:this={svg} width={SIZE} height={SIZE} viewBox="0 0 {SIZE} {SIZE}" role="slider" tabindex="0" aria-label={t('Circumplex model of emotion')}
       aria-valuenow={valence ?? undefined} onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    <rect width={SIZE} height={SIZE} rx="10" class="bg" />
    <circle cx={SIZE / 2} cy={SIZE / 2} r={SIZE / 2 - 6} class="ring" />
    <line x1={SIZE / 2} y1="6" x2={SIZE / 2} y2={SIZE - 6} class="axis" />
    <line x1="6" y1={SIZE / 2} x2={SIZE - 6} y2={SIZE / 2} class="axis" />
    {#each scatter as p, i (i)}<circle cx={toX(p.v!)} cy={toY(p.a!)} r="2" class="dot" />{/each}
    <text x={SIZE / 2} y="15" class="label" text-anchor="middle">{t('excited')}</text>
    <text x={SIZE / 2} y={SIZE - 7} class="label" text-anchor="middle">{t('calm')}</text>
    <text x="7" y={SIZE / 2 - 5} class="label">{t('unpleasant')}</text>
    <text x={SIZE - 7} y={SIZE / 2 - 5} class="label" text-anchor="end">{t('pleasant')}</text>
    {#if point}
      <circle cx={toX(point.v)} cy={toY(point.a)} r="8" class="handle" />
    {/if}
  </svg>
  {#if point}
    <button class="icon-btn clear" title={t('Clear Values')} onclick={() => onchange(null, null)}><Icon name="close" size={13} /></button>
    <span class="values">{point.v} / {point.a}</span>
  {/if}
</div>

<style>
  .circumplex { position: relative; flex: none; }
  svg { display: block; cursor: crosshair; touch-action: none; border-radius: 10px; }
  .bg { fill: var(--surface-2); stroke: var(--border); }
  .ring { fill: none; stroke: var(--border); stroke-dasharray: 3 4; }
  .axis { stroke: var(--border-strong); stroke-width: 1; }
  .dot { fill: var(--muted); opacity: 0.45; }
  .label { font-size: 9px; fill: var(--muted); pointer-events: none; }
  .handle { fill: var(--accent); stroke: var(--surface); stroke-width: 3; filter: drop-shadow(0 1px 2px rgba(0,0,0,.3)); }
  .clear { position: absolute; left: 2px; bottom: 2px; width: 22px; height: 22px; }
  .values { position: absolute; right: 6px; bottom: 4px; font-size: var(--fs-xs); color: var(--muted); }
</style>
