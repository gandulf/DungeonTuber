<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { activeTab } from '../../lib/stores/library.svelte';
  import { player } from '../../lib/stores/player.svelte';

  let { valence, arousal, onchange }: { valence: number | null; arousal: number | null; onchange: (valence: number | null, arousal: number | null) => void } = $props();

  let pad = $state<HTMLDivElement | null>(null);
  let drag = $state<{ v: number; a: number } | null>(null);

  const point = $derived(drag ?? (valence !== null && arousal !== null ? { v: valence, a: arousal } : null));
  const scatter = $derived(
    (activeTab()?.tracks ?? [])
      .map((track) => ({ id: track.id, v: track.categories.Valence, a: track.categories.Arousal }))
      .filter((p) => typeof p.v === 'number' && typeof p.a === 'number')
      .slice(0, 1500),
  );
  const playing = $derived(player.track ? { v: player.track.categories.Valence, a: player.track.categories.Arousal } : null);

  function valueAt(event: PointerEvent) {
    const rect = pad!.getBoundingClientRect();
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

<div class="wrap">
  <span class="axis top">{t('excited')}</span>
  <span class="axis bottom">{t('calm')}</span>
  <span class="axis left">{t('unpleasant')}</span>
  <span class="axis right">{t('pleasant')}</span>

  <div class="quadrants" aria-hidden="true">
    <span class="q q1">{t('Epic')} · {t('Aggressive')}</span>
    <span class="q q2">{t('Happy')} · {t('Exuberant')}</span>
    <span class="q q3">{t('Sad')} · {t('Mysterious')}</span>
    <span class="q q4">{t('Peaceful')} · {t('Warm')}</span>
  </div>

  <div class="pad" bind:this={pad} role="slider" tabindex="0" aria-label={t('Circumplex model of emotion')} aria-valuenow={valence ?? undefined}
       onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}
       onkeydown={(e) => { if (e.key === 'Delete' || e.key === 'Backspace') onchange(null, null); }}
       ondblclick={() => onchange(null, null)}>
    <div class="cross-h"></div>
    <div class="cross-v"></div>
    {#each scatter as p (p.id)}
      <span class="dot" style:left="{p.v! * 10}%" style:bottom="{p.a! * 10}%"></span>
    {/each}
    {#if playing && typeof playing.v === 'number' && typeof playing.a === 'number'}
      <span class="now" style:left="{playing.v * 10}%" style:bottom="{playing.a * 10}%"></span>
    {/if}
    {#if point}
      <span class="handle" style:left="{point.v * 10}%" style:bottom="{point.a * 10}%"></span>
    {/if}
  </div>
</div>

<style>
  .wrap { position: relative; flex: 1; min-height: 150px; display: grid; grid-template-columns: 74px 1fr 74px; grid-template-rows: 22px 1fr 22px; }
  .axis { font-size: var(--fs-xs); color: var(--muted); display: flex; align-items: center; justify-content: center; }
  .top { grid-column: 2; grid-row: 1; }
  .bottom { grid-column: 2; grid-row: 3; }
  .left { grid-column: 1; grid-row: 2; }
  .right { grid-column: 3; grid-row: 2; }
  .quadrants { position: absolute; inset: 22px 0; pointer-events: none; }
  .q { position: absolute; font-size: 10px; font-weight: 600; padding: 3px 7px; border-radius: 6px; max-width: 70px; text-align: center; line-height: 1.25; }
  .q1 { left: 0; top: 6px; background: var(--rose-soft); color: var(--rose); }
  .q2 { right: 0; top: 6px; background: var(--gold-soft); color: var(--gold); }
  .q3 { left: 0; bottom: 6px; background: var(--accent-soft); color: var(--accent); }
  .q4 { right: 0; bottom: 6px; background: var(--green-soft); color: var(--green); }
  .pad {
    grid-column: 2; grid-row: 2; position: relative; border-radius: 14px; cursor: crosshair; touch-action: none; overflow: hidden;
    background:
      radial-gradient(circle at 25% 25%, var(--rose-soft), transparent 55%),
      radial-gradient(circle at 75% 25%, var(--gold-soft), transparent 55%),
      radial-gradient(circle at 25% 75%, var(--accent-soft), transparent 55%),
      radial-gradient(circle at 75% 75%, var(--green-soft), transparent 55%),
      var(--surface-2);
    border: 1px solid var(--border);
  }
  .cross-h, .cross-v { position: absolute; background: none; border-color: var(--border-strong); border-style: dashed; }
  .cross-h { left: 0; right: 0; top: 50%; border-width: 1px 0 0; }
  .cross-v { top: 0; bottom: 0; left: 50%; border-width: 0 0 0 1px; }
  .dot { position: absolute; width: 6px; height: 6px; margin: 0 0 -3px -3px; border-radius: 50%; background: var(--accent); opacity: 0.55; }
  .now { position: absolute; width: 12px; height: 12px; margin: 0 0 -6px -6px; border-radius: 50%; background: rgb(var(--ambient)); box-shadow: 0 0 0 3px var(--surface), 0 0 14px rgba(var(--ambient), 0.9); }
  .handle { position: absolute; width: 20px; height: 20px; margin: 0 0 -10px -10px; border-radius: 50%; border: 3px solid #fff; background: var(--accent); box-shadow: 0 0 0 6px var(--accent-soft), 0 0 22px var(--accent-glow); }
</style>
