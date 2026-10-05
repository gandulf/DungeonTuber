<script lang="ts">
  import type { MusicCategory } from '../../lib/types';

  let { category, value, onchange }: { category: MusicCategory; value: number | null; onchange: (value: number | null) => void } = $props();

  let track = $state<HTMLDivElement | null>(null);
  let dragging = $state(false);
  let preview = $state<number | null>(null);
  const shown = $derived(dragging ? preview : value);
  const levels = $derived(Object.entries(category.levels).map(([k, v]) => [Number(k), v] as const).sort((a, b) => a[0] - b[0]));

  function levelText(v: number | null): string {
    if (v === null) return '';
    let best = levels[0];
    for (const level of levels) if (Math.abs(level[0] - v) < Math.abs(best[0] - v)) best = level;
    return best ? best[1] : '';
  }

  function valueAt(clientY: number): number | null {
    const rect = track!.getBoundingClientRect();
    const ratio = 1 - (clientY - rect.top) / rect.height;
    const v = Math.round(ratio * 11) - 1; // -1 (off) .. 10
    return v < 0 ? null : Math.min(10, v);
  }

  function down(event: PointerEvent) {
    dragging = true;
    preview = valueAt(event.clientY);
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent) {
    if (dragging) preview = valueAt(event.clientY);
  }

  function up() {
    if (!dragging) return;
    dragging = false;
    if (preview !== value) onchange(preview);
  }

  function key(event: KeyboardEvent) {
    if (event.key === 'ArrowUp') onchange(Math.min(10, (value ?? -1) + 1));
    else if (event.key === 'ArrowDown') onchange(value === null || value <= 0 ? null : value - 1);
    else if (event.key === 'Delete' || event.key === 'Backspace') onchange(null);
    else return;
    event.preventDefault();
  }
</script>

<div class="slider" title={category.description + '\n' + levels.map(([k, v]) => `${k}: ${v}`).join('\n')}>
  <span class="value" class:off={shown === null}>{shown ?? '–'}</span>
  <div class="track" bind:this={track} role="slider" tabindex="0" aria-label={category.name} aria-valuemin={0} aria-valuemax={10}
       aria-valuenow={value ?? undefined} onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}
       onkeydown={key} ondblclick={() => onchange(null)}>
    <div class="fill" class:active={shown !== null} style:height="{shown === null ? 0 : ((shown + 1) / 11) * 100}%"></div>
    {#if shown !== null}<div class="thumb" style:bottom="calc({((shown + 1) / 11) * 100}% - 7px)"></div>{/if}
  </div>
  <span class="name ellipsis">{category.name}</span>
  {#if dragging && preview !== null}<span class="tip">{levelText(preview)}</span>{/if}
</div>

<style>
  .slider { position: relative; display: flex; flex-direction: column; align-items: center; gap: 4px; width: 66px; flex: none; }
  .value { font-size: var(--fs-sm); font-weight: 600; font-variant-numeric: tabular-nums; }
  .value.off { color: var(--muted); font-weight: 400; }
  .track { position: relative; width: 10px; height: 104px; border-radius: 5px; background: var(--surface-3); cursor: ns-resize; touch-action: none; }
  .track:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
  .fill { position: absolute; left: 0; right: 0; bottom: 0; border-radius: 5px; background: var(--border-strong); }
  .fill.active { background: var(--accent); }
  .thumb { position: absolute; left: 50%; width: 16px; height: 16px; margin-left: -8px; border-radius: 50%; background: var(--surface); border: 3px solid var(--accent); box-shadow: 0 1px 3px rgba(0,0,0,.25); }
  .name { font-size: var(--fs-xs); color: var(--muted); max-width: 66px; text-align: center; }
  .tip { position: absolute; top: 100%; left: 50%; transform: translateX(-50%); margin-top: 4px; z-index: 10; background: var(--text); color: var(--bg); padding: 3px 8px; border-radius: 6px; font-size: var(--fs-xs); white-space: nowrap; pointer-events: none; }
</style>
