<script lang="ts">
  import { onMount } from 'svelte';
  import { addLink, autoLayout, CARD, fromCard, removeLink, toCard } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { imageUrl } from '../../lib/notes';
  import { addBlock, adventures, change } from '../../lib/stores/adventure.svelte';
  import type { AdventureBlock, AdventureLink } from '../../lib/types';
  import { openDialog } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import ImagePopup from '../dialogs/ImagePopup.svelte';
  import BlockCard from './BlockCard.svelte';

  const adventure = $derived(adventures.current!);
  const editable = $derived(adventure.editable);

  const MIN_ZOOM = 0.3;
  const MAX_ZOOM = 2;

  // the view onto the graph (pan and zoom are not saved), the block being dragged and the link being drawn
  let view = $state({ x: 24, y: 24, k: 1 });
  let frame = $state<HTMLDivElement | null>(null);
  let drag = $state<{ id: string; moved: boolean; startX: number; startY: number; origin: [number, number] } | null>(null);
  let pan = $state<{ startX: number; startY: number; x: number; y: number } | null>(null);
  let drawing = $state<{ from: string; x: number; y: number } | null>(null);
  let selectedLink = $state<AdventureLink | null>(null);

  // the blocks are drawn as cards at their stored positions stretched to the card size (see CARD_SCALE); the world is in card pixels
  const center = (id: string): [number, number] | null => {
    const block = adventure.blocks.find((item) => item.id === id);
    if (!block) return null;
    const [x, y] = toCard(block.pos);
    return [x + CARD.w / 2, y + CARD.h / 2];
  };

  /** A link leaves a block on its right side and enters the next one on its left side. */
  function edge(link: AdventureLink) {
    const from = adventure.blocks.find((item) => item.id === link.from);
    const to = adventure.blocks.find((item) => item.id === link.to);
    if (!from || !to) return null;
    const [[fx, fy], [tx, ty]] = [toCard(from.pos), toCard(to.pos)];
    const [x1, y1] = [fx + CARD.w, fy + CARD.h / 2];
    const [x2, y2] = [tx, ty + CARD.h / 2];
    const bend = Math.max(48, Math.abs(x2 - x1) / 2);
    return { d: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`, mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
  }

  const world = (event: PointerEvent): [number, number] => {
    const rect = frame!.getBoundingClientRect();
    return [(event.clientX - rect.left - view.x) / view.k, (event.clientY - rect.top - view.y) / view.k];
  };

  const clampZoom = (k: number) => Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, k));

  /** Zooms to `k`: the point of the world at (px, py) of the frame moves to (tx, ty), so by default it stays put. */
  function zoomAt(k: number, px: number, py: number, tx = px, ty = py) {
    view = { x: tx - ((px - view.x) / view.k) * k, y: ty - ((py - view.y) / view.k) * k, k };
  }

  function wheel(event: WheelEvent) {
    event.preventDefault();
    const rect = frame!.getBoundingClientRect();
    // the step follows the distance: a wheel notch (~100 px) zooms by ~10 %, a trackpad pinch (small deltas) zooms smoothly
    const delta = Math.max(-100, Math.min(100, event.deltaY * (event.deltaMode === 1 ? 33 : 1)));
    zoomAt(clampZoom(view.k * Math.exp(-delta * (Math.abs(delta) < 50 ? 0.01 : 0.001))), event.clientX - rect.left, event.clientY - rect.top);
  }

  $effect(() => {
    const element = frame;
    element?.addEventListener('wheel', wheel, { passive: false });
    return () => element?.removeEventListener('wheel', wheel);
  });

  function zoomBy(factor: number) {
    const rect = frame!.getBoundingClientRect();
    zoomAt(clampZoom(view.k * factor), rect.width / 2, rect.height / 2);
  }

  // the fingers on the frame: two of them pinch, which zooms around the middle between them and moves the view along with it
  const fingers = new Map<number, [number, number]>();
  let pinch: { dist: number; mx: number; my: number } | null = null;

  function spread() {
    const [[x1, y1], [x2, y2]] = [...fingers.values()];
    return { dist: Math.max(1, Math.hypot(x2 - x1, y2 - y1)), mx: (x1 + x2) / 2, my: (y1 + y2) / 2 };
  }

  /** Runs before the handlers of the blocks (capture phase), so a second finger can end what the first one started. */
  function fingerDown(event: PointerEvent) {
    if (event.pointerType !== 'touch') return;
    fingers.set(event.pointerId, [event.clientX, event.clientY]);
    if (fingers.size !== 2) return;
    // a block moved by the first finger goes back, a link being drawn is dropped
    if (drag?.moved) {
      const block = adventure.blocks.find((item) => item.id === drag!.id);
      if (block) block.pos = [drag.origin[0], drag.origin[1]];
    }
    drag = null;
    drawing = null;
    pan = null;
    pinch = spread();
  }

  function pinchMove(event: PointerEvent): boolean {
    if (!fingers.has(event.pointerId)) return false;
    fingers.set(event.pointerId, [event.clientX, event.clientY]);
    if (!pinch || fingers.size < 2) return false;
    const now = spread();
    const rect = frame!.getBoundingClientRect();
    zoomAt(clampZoom(view.k * (now.dist / pinch.dist)), pinch.mx - rect.left, pinch.my - rect.top, now.mx - rect.left, now.my - rect.top);
    pinch = now;
    return true;
  }

  function fingerUp(event: PointerEvent) {
    fingers.delete(event.pointerId);
    if (fingers.size < 2) pinch = null;
  }

  /** Shows all blocks. */
  function fit() {
    if (!frame || !adventure.blocks.length) return;
    const spots = adventure.blocks.map((block) => toCard(block.pos));
    const xs = spots.map(([x]) => x);
    const ys = spots.map(([, y]) => y);
    const [left, top] = [Math.min(...xs), Math.min(...ys)];
    const [width, height] = [Math.max(...xs) + CARD.w - left, Math.max(...ys) + CARD.h - top];
    const rect = frame.getBoundingClientRect();
    const k = Math.min(1, Math.max(MIN_ZOOM, Math.min((rect.width - 48) / width, (rect.height - 48) / height)));
    view = { x: 24 - left * k, y: 24 - top * k, k };
  }

  function arrange() {
    change((a) => autoLayout(a));
    fit();
  }

  function backgroundDown(event: PointerEvent) {
    if (pinch) return;
    if (event.target !== frame && !(event.target as Element).classList.contains('world')) return;
    selectedLink = null;
    pan = { startX: event.clientX, startY: event.clientY, x: view.x, y: view.y };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function nodeDown(event: PointerEvent, id: string) {
    event.stopPropagation();
    if (pinch) return;
    adventures.selected = id;
    selectedLink = null;
    if (!editable) return;
    const block = adventure.blocks.find((item) => item.id === id)!;
    drag = { id, moved: false, startX: event.clientX, startY: event.clientY, origin: [block.pos[0], block.pos[1]] };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  /** A double click on the picture of a block shows its cover large. The node captures the pointer while it is dragged, so the
   *  event arrives at the node: the position tells whether it was on the picture. */
  function showCover(event: MouseEvent, block: AdventureBlock) {
    if (!block.cover || !document.elementsFromPoint(event.clientX, event.clientY).some((element) => element.classList.contains('art'))) return;
    openDialog(ImagePopup, { src: imageUrl(adventure.id, block.cover), title: block.title || t('Cover image') });
  }

  function handleDown(event: PointerEvent, id: string) {
    event.stopPropagation();
    if (!editable || pinch) return;
    const [x, y] = world(event);
    drawing = { from: id, x, y };
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent) {
    if (pinchMove(event)) return;
    if (drawing) {
      [drawing.x, drawing.y] = world(event);
    } else if (drag) {
      const dx = (event.clientX - drag.startX) / view.k;
      const dy = (event.clientY - drag.startY) / view.k;
      if (!drag.moved && Math.hypot(dx, dy) * view.k < 3) return;
      drag.moved = true;
      const block = adventure.blocks.find((item) => item.id === drag!.id);
      if (block) {
        const [x, y] = toCard(drag.origin);
        block.pos = fromCard(x + dx, y + dy);
      }
    } else if (pan) {
      view = { ...view, x: pan.x + event.clientX - pan.startX, y: pan.y + event.clientY - pan.startY };
    }
  }

  function up(event: PointerEvent) {
    fingerUp(event);
    if (drawing) {
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest<HTMLElement>('[data-node]')?.dataset.node;
      const from = drawing.from;
      drawing = null;
      if (target && target !== from) change((a) => addLink(a, from, target));
    } else if (drag) {
      if (drag.moved) change(() => undefined); // the new position is already in the block: this saves it
      drag = null;
    }
    pan = null;
  }

  function removeSelectedLink() {
    if (!selectedLink) return;
    const link = selectedLink;
    selectedLink = null;
    change((a) => removeLink(a, link));
  }

  const start = $derived(drawing ? center(drawing.from) : null);

  onMount(() => {
    // blocks that were never placed (all at the same spot) are arranged once
    const [first, ...rest] = adventure.blocks;
    if (editable && rest.length && rest.every((block) => block.pos[0] === first.pos[0] && block.pos[1] === first.pos[1])) change((a) => autoLayout(a));
    fit();
  });
</script>

<div class="graph">
  <div class="tools">
    {#if editable}<button class="btn sm" onclick={() => addBlock()}><Icon name="plus" size={13} />{t('Add block')}</button>{/if}
    {#if editable}<button class="btn sm ghost" title={t('Arrange the blocks by their path')} onclick={arrange}><Icon name="tree" size={13} />{t('Arrange')}</button>{/if}
    <span class="grow"></span>
    <button class="icon-btn mini" title={t('Zoom out')} aria-label={t('Zoom out')} onclick={() => zoomBy(1 / 1.25)}>−</button>
    <button class="icon-btn mini" title={t('Zoom in')} aria-label={t('Zoom in')} onclick={() => zoomBy(1.25)}>+</button>
    <button class="btn sm ghost" title={t('Show all blocks')} onclick={fit}>{t('Fit')}</button>
  </div>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="frame" bind:this={frame} onpointerdowncapture={fingerDown} onpointerdown={backgroundDown} onpointermove={move} onpointerup={up} onpointercancel={up}>
    <div class="world" style:transform="translate({view.x}px, {view.y}px) scale({view.k})">
      <svg class="edges" width="1" height="1" overflow="visible" aria-hidden="true">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" /></marker>
        </defs>
        {#each adventure.links as link (link)}
          {@const shape = edge(link)}
          {#if shape}
            <g class="edge" class:on={selectedLink === link} class:choice={!!link.label}>
              <path class="hit" d={shape.d} onpointerdown={(e) => { e.stopPropagation(); selectedLink = link; }} role="presentation" />
              <path class="line" d={shape.d} marker-end="url(#arrow)" />
              {#if link.label}<text x={shape.mx} y={shape.my - 6} text-anchor="middle">{link.label}</text>{/if}
            </g>
          {/if}
        {/each}
        {#if drawing && start}
          <path class="line draft" d={`M ${start[0] + CARD.w / 2} ${start[1]} L ${drawing.x} ${drawing.y}`} />
        {/if}
      </svg>
      {#each adventure.blocks as block, index (block.id)}
        {@const [x, y] = toCard(block.pos)}
        <!-- svelte-ignore a11y_no_static_element_interactions -->
        <div class="node" class:selected={adventures.selected === block.id} class:played={block.played} class:first={index === 0} data-node={block.id}
             style:left="{x}px" style:top="{y}px" style:width="{CARD.w}px" style:height="{CARD.h}px"
             title={block.cover ? t('Double-click the picture to enlarge it') : undefined}
             onpointerdown={(e) => nodeDown(e, block.id)} ondblclick={(e) => showCover(e, block)}>
          <BlockCard {block} adventureId={adventure.id} badge={index === 0 ? t('Start') : null} />
          {#if editable}
            <!-- svelte-ignore a11y_no_static_element_interactions -->
            <span class="handle" title={t('Drag to another block to link it')} onpointerdown={(e) => handleDown(e, block.id)}></span>
          {/if}
        </div>
      {/each}
      {#if selectedLink && editable}
        {@const shape = edge(selectedLink)}
        {#if shape}
          <div class="link-edit" style:left="{shape.mx}px" style:top="{shape.my}px" onpointerdown={(e) => e.stopPropagation()} role="presentation">
            <input type="text" placeholder={t('Label (a choice)')} value={selectedLink.label ?? ''}
                   oninput={(e) => { const link = selectedLink!; change(() => (link.label = e.currentTarget.value.trim() || null)); }} />
            <button class="icon-btn mini" title={t('Remove link')} aria-label={t('Remove link')} onclick={removeSelectedLink}><Icon name="trash" size={13} /></button>
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>

<style>
  .graph { display: flex; flex-direction: column; gap: 6px; }
  .tools { display: flex; align-items: center; gap: 6px; }
  .grow { flex: 1; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .mini { width: 26px; height: 26px; font-size: 1.1rem; line-height: 1; }
  .frame { position: relative; height: clamp(300px, 52vh, 600px); overflow: hidden; resize: vertical; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); cursor: grab; touch-action: none;
           background-image: radial-gradient(var(--border) 1px, transparent 1px); background-size: 22px 22px; }
  .frame:active { cursor: grabbing; }
  .world { position: absolute; left: 0; top: 0; transform-origin: 0 0; }
  .edges { position: absolute; left: 0; top: 0; color: var(--muted); pointer-events: none; }
  .edge .line { fill: none; stroke: currentColor; stroke-width: 1.8; }
  .edge .hit { fill: none; stroke: transparent; stroke-width: 14; pointer-events: stroke; cursor: pointer; }
  .edge.choice { color: var(--accent); }
  .edge.on { color: var(--accent); }
  .edge.on .line { stroke-width: 2.8; }
  .edge text { fill: var(--text); font-size: 12px; paint-order: stroke; stroke: var(--surface); stroke-width: 4px; pointer-events: none; }
  .line.draft { fill: none; stroke: var(--accent); stroke-width: 2; stroke-dasharray: 5 4; }
  .node { position: absolute; box-sizing: border-box; display: flex; flex-direction: column; gap: 4px; padding: 0 0 10px; border-radius: 12px; background: var(--bg-2);
          border: 1px solid var(--border-strong, var(--border)); color: var(--text); cursor: pointer; user-select: none; transition: border-color 0.15s, box-shadow 0.15s; }
  .node :global(.art) { border-radius: 11px 11px 0 0; overflow: hidden; }
  .node:hover { border-color: var(--accent); box-shadow: var(--shadow); }
  .node.selected { border: 2px solid var(--accent); box-shadow: 0 0 0 4px var(--accent-soft), var(--shadow); }
  .node.played:not(.selected) { opacity: 0.65; }
  .handle { position: absolute; right: -7px; top: calc(50% - 7px); width: 14px; height: 14px; border-radius: 50%; background: var(--accent); border: 2px solid var(--bg-2); cursor: crosshair; }
  .link-edit { position: absolute; transform: translate(-50%, 8px); display: flex; align-items: center; gap: 4px; padding: 4px; border-radius: 9px; background: var(--bg-2); border: 1px solid var(--accent); box-shadow: var(--shadow); }
  .link-edit input { width: 150px; }
</style>
