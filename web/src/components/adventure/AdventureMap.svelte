<script lang="ts">
  import { flushSync, untrack } from 'svelte';
  import { CARD, cardLayout } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import type { Adventure } from '../../lib/types';
  import BlockCard from './BlockCard.svelte';

  /** The blocks of an adventure as cards (cover, title, the start of the notes) with the links between them, on the welcome screen
   *  of play mode. `current` is marked: the block being played, or the one the session continues with. A click starts a block. */
  let { adventure, current, playing = false, onopen }: { adventure: Adventure; current: string | null; playing?: boolean; onopen: (id: string) => void } = $props();

  const PAD = 24;

  const layout = $derived(cardLayout(adventure));
  const at = (id: string) => layout.pos.get(id);

  /** A link as a curve from the right edge of a card to the left edge of the next (around the cards when it leads backwards). */
  const edges = $derived(adventure.links.flatMap((link, index) => {
    const [from, to] = [at(link.from), at(link.to)];
    if (!from || !to) return [];
    const [x1, y1] = [from[0] + CARD.w + PAD, from[1] + CARD.h / 2 + PAD];
    const [x2, y2] = [to[0] + PAD, to[1] + CARD.h / 2 + PAD];
    const bend = Math.max(48, Math.abs(x2 - x1) / 2);
    return [{
      key: `${index}:${link.from}>${link.to}`, // two links may have the same ends and label (labels are edited later)
      d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
      label: link.label, mx: (x1 + x2) / 2, my: (y1 + y2) / 2,
      on: link.from === current, choice: !!link.label,
    }];
  }));

  let frame = $state<HTMLDivElement | null>(null);
  const size = $derived({ w: layout.width + 2 * PAD, h: layout.height + 2 * PAD });

  // --- zoom (Ctrl + mouse wheel): the world is scaled, the sizer around it has the scaled size so the map scrolls over all of it
  const MIN_ZOOM = 0.35;
  const MAX_ZOOM = 1.6;
  let zoom = $state(1);

  /** How far the world sits from the left/top edge of the map: while it is smaller than the map it is centered. */
  const inset = (k: number) => (frame ? [Math.max(0, (frame.clientWidth - size.w * k) / 2), Math.max(0, (frame.clientHeight - size.h * k) / 2)] : [0, 0]);

  /** Zooms to `k`: the point of the world at (cx, cy) on the screen moves to (tx, ty), so by default it stays under the pointer. */
  function zoomAt(k: number, cx: number, cy: number, tx = cx, ty = cy) {
    if (!frame) return;
    const next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, k));
    const rect = frame.getBoundingClientRect();
    const [px, py] = [cx - rect.left, cy - rect.top];
    const [ix, iy] = inset(zoom);
    const [wx, wy] = [(frame.scrollLeft + px - ix) / zoom, (frame.scrollTop + py - iy) / zoom];
    flushSync(() => (zoom = next)); // the sizer has its new size before the map scrolls
    const [nx, ny] = inset(next);
    frame.scrollLeft = wx * next + nx - (tx - rect.left);
    frame.scrollTop = wy * next + ny - (ty - rect.top);
  }

  function wheel(event: WheelEvent) {
    if (!event.ctrlKey) return;
    event.preventDefault(); // instead of zooming the whole page
    // the step follows the distance: a wheel notch (~100 px) zooms by ~12 %, a trackpad pinch (small deltas) zooms smoothly
    const delta = Math.max(-100, Math.min(100, event.deltaY * (event.deltaMode === 1 ? 33 : 1)));
    zoomAt(zoom * Math.exp(-delta * (Math.abs(delta) < 50 ? 0.01 : 0.0012)), event.clientX, event.clientY);
  }

  // --- two fingers pinch on a touch screen: zoom around the middle between them, moving the view along (one finger scrolls natively)
  let pinch: { dist: number; mx: number; my: number } | null = null;

  function spread(event: TouchEvent) {
    const [a, b] = [event.touches[0], event.touches[1]];
    return { dist: Math.max(1, Math.hypot(b.clientX - a.clientX, b.clientY - a.clientY)), mx: (a.clientX + b.clientX) / 2, my: (a.clientY + b.clientY) / 2 };
  }

  function touchStart(event: TouchEvent) {
    pinch = event.touches.length === 2 ? spread(event) : null;
  }

  function touchMove(event: TouchEvent) {
    if (!pinch || event.touches.length !== 2) return;
    event.preventDefault(); // instead of scrolling
    const now = spread(event);
    zoomAt(zoom * (now.dist / pinch.dist), pinch.mx, pinch.my, now.mx, now.my);
    pinch = now;
  }

  function touchEnd(event: TouchEvent) {
    if (event.touches.length < 2) pinch = null;
  }

  /** An attachment of the frame: wheel and pinch are not passive, so they can stop the browser from zooming the page. */
  function zoomGestures(element: HTMLElement) {
    element.addEventListener('wheel', wheel, { passive: false });
    element.addEventListener('touchstart', touchStart, { passive: true });
    element.addEventListener('touchmove', touchMove, { passive: false });
    element.addEventListener('touchend', touchEnd);
    element.addEventListener('touchcancel', touchEnd);
    return () => {
      element.removeEventListener('wheel', wheel);
      element.removeEventListener('touchstart', touchStart);
      element.removeEventListener('touchmove', touchMove);
      element.removeEventListener('touchend', touchEnd);
      element.removeEventListener('touchcancel', touchEnd);
    };
  }

  // --- moving the view by dragging with the left mouse button (touch screens scroll on their own); a drag is no click on a card
  let pan = $state<{ x: number; y: number; left: number; top: number; moved: boolean } | null>(null);
  let swallowClick = false;

  function panDown(event: PointerEvent) {
    if (event.button !== 0 || event.pointerType !== 'mouse' || !frame) return;
    pan = { x: event.clientX, y: event.clientY, left: frame.scrollLeft, top: frame.scrollTop, moved: false };
  }

  function panMove(event: PointerEvent) {
    if (!pan || !frame) return;
    const [dx, dy] = [event.clientX - pan.x, event.clientY - pan.y];
    if (!pan.moved) {
      if (Math.hypot(dx, dy) < 4) return;
      pan.moved = true;
      try {
        frame.setPointerCapture(event.pointerId); // the drag goes on outside the map
      } catch { /* the pointer is gone already */ }
    }
    frame.scrollLeft = pan.left - dx;
    frame.scrollTop = pan.top - dy;
  }

  function panUp() {
    swallowClick = !!pan?.moved;
    pan = null;
  }

  function maybeSwallow(event: MouseEvent) {
    if (!swallowClick) return;
    swallowClick = false;
    event.preventDefault();
    event.stopPropagation();
  }

  // the current card is scrolled into the middle of the map
  $effect(() => {
    const spot = current ? at(current) : null;
    if (!frame || !spot) return;
    const k = untrack(() => zoom);
    frame.scrollLeft = (spot[0] + PAD + CARD.w / 2) * k - frame.clientWidth / 2;
    frame.scrollTop = (spot[1] + PAD + CARD.h / 2) * k - frame.clientHeight / 2;
  });
</script>

{#if adventure.blocks.length}
  <div class="map-wrap">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="map" class:panning={pan?.moved} bind:this={frame} {@attach zoomGestures} title={t('Drag to move the view, Ctrl + mouse wheel to zoom')}
       onpointerdown={panDown} onpointermove={panMove} onpointerup={panUp} onpointercancel={panUp} onclickcapture={maybeSwallow}>
    <div class="sizer" style:width="{size.w * zoom}px" style:height="{size.h * zoom}px">
    <div class="world" style:width="{size.w}px" style:height="{size.h}px" style:transform="scale({zoom})">
      <svg class="edges" width={size.w} height={size.h} aria-hidden="true">
        <defs>
          <marker id="map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" class="tip" />
          </marker>
          <marker id="map-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" class="tip on" />
          </marker>
        </defs>
        {#each edges as edge (edge.key)}
          <path class="line" class:on={edge.on} class:choice={edge.choice} d={edge.d} marker-end={edge.on ? 'url(#map-arrow-on)' : 'url(#map-arrow)'} />
          {#if edge.label}<text x={edge.mx} y={edge.my - 6} text-anchor="middle" class:on={edge.on}>{edge.label}</text>{/if}
        {/each}
      </svg>
      {#each adventure.blocks as block (block.id)}
        {@const spot = at(block.id)}
        {#if spot}
          <button type="button" class="card" class:current={block.id === current} class:played={block.played}
                  style:left="{spot[0] + PAD}px" style:top="{spot[1] + PAD}px" style:width="{CARD.w}px" style:height="{CARD.h}px"
                  title={block.title || t('Untitled')} onclick={() => onopen(block.id)}>
            <BlockCard {block} adventureId={adventure.id} badge={block.id === current ? (playing ? t('Now') : t('Next up')) : null} />
          </button>
        {/if}
      {/each}
    </div>
    </div>
  </div>
  {#if zoom !== 1}
    <button type="button" class="zoom" title={t('Back to 100 %')} onclick={() => (zoom = 1)}>{Math.round(zoom * 100)} %</button>
  {/if}
  </div>
{/if}

<style>
  /* the map takes the height its container leaves (the rest of the welcome screen), at least a few cards high */
  .map { position: absolute; inset: 0; display: flex; overflow: auto; border-radius: 14px; background: var(--surface); border: 1px solid var(--border);
         background-image: radial-gradient(var(--border) 1px, transparent 1px); background-size: 22px 22px; }
  .map { cursor: grab; user-select: none; touch-action: pan-x pan-y; } /* the page does not zoom: a pinch zooms the map */
  .map.panning, .map.panning .card { cursor: grabbing; }
  .sizer { position: relative; flex: none; margin: auto; } /* centered while smaller than the map (auto margins of a flex item stay safe) */
  .world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
  /* the map takes the room that is left, so the overview fits the screen (the map scrolls inside, the page does not) */
  .map-wrap { position: relative; width: 100%; flex: 1; min-height: 0; }
  .zoom { position: absolute; right: 10px; bottom: 10px; padding: 3px 9px; border-radius: 999px;
          font-size: var(--fs-xs); background: var(--bg-2); border: 1px solid var(--border); color: var(--muted); box-shadow: var(--shadow); }
  .zoom:hover { color: var(--accent); border-color: var(--accent); }
  .edges { position: absolute; left: 0; top: 0; pointer-events: none; overflow: visible; }
  .line { fill: none; stroke: var(--muted); stroke-width: 1.6; opacity: 0.7; }
  .line.choice { stroke-dasharray: 6 4; }
  .line.on { stroke: var(--accent); stroke-width: 2.4; opacity: 1; }
  .tip { fill: var(--muted); }
  .tip.on { fill: var(--accent); }
  text { fill: var(--muted); font-size: 11px; paint-order: stroke; stroke: var(--surface); stroke-width: 4px; }
  text.on { fill: var(--accent); }
  .card { position: absolute; box-sizing: border-box; display: flex; flex-direction: column; gap: 4px; padding: 0 0 10px; overflow: hidden; text-align: left;
          border-radius: 12px; background: var(--bg-2); border: 1px solid var(--border-strong, var(--border)); color: var(--text); cursor: pointer;
          transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s; }
  .card:hover { border-color: var(--accent); transform: translateY(-2px); box-shadow: var(--shadow); }
  .card.current { border: 2px solid var(--accent); box-shadow: 0 0 0 4px var(--accent-soft), var(--shadow); }
  .card.played:not(.current) { opacity: 0.6; }
</style>
