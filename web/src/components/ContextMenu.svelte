<script lang="ts">
  import { closeMenu, ui, type MenuItem } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';

  let menuEl = $state<HTMLDivElement | null>(null);
  let position = $state({ x: 0, y: 0 });
  let openSub = $state<number | null>(null);

  $effect(() => {
    const menu = ui.menu;
    if (!menu || !menuEl) return;
    openSub = null;
    const rect = menuEl.getBoundingClientRect();
    position = {
      x: Math.min(menu.x, window.innerWidth - rect.width - 8),
      y: Math.min(menu.y, window.innerHeight - rect.height - 8),
    };
  });

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
          <div class="menu sub">{@render items(item.children, 1)}</div>
        {/if}
      </div>
    {/if}
  {/each}
{/snippet}

{#if ui.menu}
  <div class="menu" bind:this={menuEl} style:left="{position.x || ui.menu.x}px" style:top="{position.y || ui.menu.y}px"
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
    border-radius: var(--radius);
    box-shadow: var(--shadow);
    padding: 5px;
  }
  .sub { position: absolute; left: 100%; top: -5px; margin-left: 2px; }
  .item-wrap { position: relative; }
  .item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 10px 6px 6px; border-radius: var(--radius-sm); text-align: left; }
  .item:hover:not(:disabled) { background: var(--accent-soft); }
  .ic { width: 18px; display: flex; justify-content: center; color: var(--muted); }
  .label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .shortcut { color: var(--muted); font-size: var(--fs-xs); }
  .sep { height: 1px; background: var(--border); margin: 4px 6px; }
</style>
