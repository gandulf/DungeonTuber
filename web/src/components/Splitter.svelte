<script lang="ts">
  let { size = $bindable(), min = 150, max = 600, invert = false, onchange }: {
    size: number; min?: number; max?: number; invert?: boolean; onchange?: () => void;
  } = $props();

  function start(event: PointerEvent) {
    const startX = event.clientX;
    const startSize = size;
    const target = event.currentTarget as HTMLElement;
    target.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => {
      const delta = (e.clientX - startX) * (invert ? -1 : 1);
      size = Math.round(Math.max(min, Math.min(max, startSize + delta)));
    };
    const up = () => {
      target.removeEventListener('pointermove', move);
      target.removeEventListener('pointerup', up);
      onchange?.();
    };
    target.addEventListener('pointermove', move);
    target.addEventListener('pointerup', up);
  }
</script>

<div class="splitter" role="separator" aria-orientation="vertical" onpointerdown={start}></div>

<style>
  .splitter { width: 10px; flex: none; cursor: col-resize; position: relative; }
  .splitter::after { content: ''; position: absolute; left: 4px; top: 30%; bottom: 30%; width: 2px; border-radius: 1px; background: transparent; transition: background 0.15s; }
  .splitter:hover::after { background: var(--border-strong); }
</style>
