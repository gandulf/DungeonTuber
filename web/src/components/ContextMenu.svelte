<script lang="ts">
  import { closeMenu, ui, type MenuItem } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';

  let menuEl = $state<HTMLDivElement | null>(null);
  let position = $state<{ x: number; y: number } | null>(null);
  let openSub = $state<number | null>(null);
  const MARGIN = 8;

  // keeps the menu completely inside the window (it is shown once it has been measured)
  $effect(() => {
    const menu = ui.menu;
    if (!menu) {
      position = null;
      return;
    }
    if (!menuEl) return;
    openSub = null;
    const rect = menuEl.getBoundingClientRect();
    position = {
      x: Math.max(MARGIN, Math.min(menu.x, window.innerWidth - rect.width - MARGIN)),
      y: Math.max(MARGIN, Math.min(menu.y, window.innerHeight - rect.height - MARGIN)),
    };
  });

  /** A submenu opens to the left when there is no room on the right, and moves up when it would leave the window at the bottom. */
  function fit(node: HTMLElement) {
    const rect = node.getBoundingClientRect();
    if (rect.right > window.innerWidth - MARGIN) {
      node.style.left = 'auto';
      node.style.right = '100%';
      node.style.marginLeft = '0';
      node.style.marginRight = '2px';
    }
    const placed = node.getBoundingClientRect();
    if (placed.left < MARGIN) node.style.transform = `translateX(${MARGIN - placed.left}px)`; // neither side has room: overlap the parent menu
    if (rect.bottom > window.innerHeight - MARGIN) {
      const parentTop = node.parentElement?.getBoundingClientRect().top ?? rect.top;
      const top = Math.max(MARGIN, window.innerHeight - MARGIN - rect.height);
      node.style.top = `${top - parentTop}px`;
    }
  }

  function run(item: MenuItem) {
    if (item.disabled || item.children) return;
    closeMenu();
    item.action?.();
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Escape' && ui.menu) closeMenu();
  }
</script>

<svelte:window onkeydown={onKey} />

{#snippet items(list: MenuItem[], level: number)}
  {#each list as item, i (i)}
    {#if item.separator}
      <div class="sep"></div>
    {:else}
      <div class="item-wrap" role="none" onmouseenter={() => level === 0 && (openSub = item.children ? i : null)}>
        <button class="item" disabled={item.disabled} onclick={(e) => { e.stopPropagation(); run(item); }}>
          <span class="ic">
            {#if item.checked}<Icon name="check" size={15} />{:else if item.icon}<Icon name={item.icon} size={15} />{/if}
          </span>
          <span class="label">{item.label}</span>
          {#if item.shortcut}<span class="shortcut">{item.shortcut}</span>{/if}
          {#if item.children}<Icon name="chevron-right" size={14} />{/if}
        </button>
        {#if item.children && openSub === i && level === 0}
          <div class="menu sub" use:fit>{@render items(item.children, 1)}</div>
        {/if}
      </div>
    {/if}
  {/each}
{/snippet}

{#if ui.menu}
  <div class="menu" bind:this={menuEl} style:left="{position?.x ?? ui.menu.x}px" style:top="{position?.y ?? ui.menu.y}px" style:visibility={position ? 'visible' : 'hidden'}
       role="menu" tabindex="-1" onclick={(e) => e.stopPropagation()} oncontextmenu={(e) => e.preventDefault()}
       onkeydown={() => {}}>
    {@render items(ui.menu.items, 0)}
  </div>
{/if}

<style>
  .menu {
    position: fixed;
    z-index: 1000;
    min-width: 200px;
    max-width: 320px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    box-shadow: var(--shadow);
    padding: 6px;
    backdrop-filter: blur(12px);
  }
  .sub { position: absolute; left: 100%; top: -5px; margin-left: 2px; }
  .item-wrap { position: relative; }
  .item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 7px 10px 7px 7px; border-radius: 8px; text-align: left; }
  .item:hover:not(:disabled) { background: var(--accent-soft); }
  .ic { width: 18px; display: flex; justify-content: center; color: var(--muted); }
  .label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .shortcut { color: var(--muted); font-size: var(--fs-xs); }
  .sep { height: 1px; background: var(--border); margin: 4px 6px; }
</style>
