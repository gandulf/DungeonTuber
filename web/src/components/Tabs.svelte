<script lang="ts">
  import { longpress } from '../lib/longpress';
  import { t } from '../lib/i18n.svelte';
  import { closeAllTabs, closeDuplicates, closeOtherTabs, closeTab, library, loadTab, moveTab, selectTab } from '../lib/stores/library.svelte';
  import { adventures, deleteAdventure, openAdventure, renameAdventure } from '../lib/stores/adventure.svelte';
  import { openMenu, ui } from '../lib/stores/ui.svelte';
  import type { Tab } from '../lib/stores/library.svelte';
  import Icon from './Icon.svelte';

  const MIN_TAB = 120; // narrowest a tab may get before it moves into the dropdown
  const GAP = 6;
  const DROPDOWN = 40;

  let dragIndex: number | null = null;
  let width = $state(0);

  // as many tabs as fit in one line, the active one always among them; the rest is reachable through the dropdown
  const capacity = $derived(Math.max(1, Math.floor((width - DROPDOWN) / (MIN_TAB + GAP))));
  const overflowing = $derived(library.tabs.length > capacity);
  const shown = $derived.by(() => {
    if (!overflowing) return library.tabs.map((tab, index) => ({ tab, index }));
    const all = library.tabs.map((tab, index) => ({ tab, index }));
    const first = all.slice(0, capacity);
    const active = all.find((entry) => entry.tab.key === library.active);
    if (active && !first.includes(active)) first[capacity - 1] = active;
    return first;
  });
  const hidden = $derived(library.tabs.filter((tab) => !shown.some((entry) => entry.tab.key === tab.key)));

  const icon = (tab: Tab) => (tab.type === 'playlist' ? 'playlist' : tab.type === 'adventure' ? 'mask' : 'folder');

  function showHidden(event: MouseEvent) {
    event.stopPropagation();
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    openMenu({ clientX: rect.right - 240, clientY: rect.bottom + 6 }, [
      ...hidden.map((tab) => ({ label: tab.name, icon: icon(tab), action: () => selectTab(tab.key) })),
      { separator: true },
      { label: t('Close All'), action: closeAllTabs },
    ]);
  }

  function menu(event: MouseEvent, key: string) {
    const index = library.tabs.findIndex((item) => item.key === key);
    const tab = library.tabs[index];
    const adventure = tab?.type === 'adventure' ? adventures.list.find((item) => item.id === tab.path) : null;
    openMenu(event, [
      tab?.type === 'adventure'
        ? { label: t('Refresh'), icon: 'refresh', action: () => void openAdventure(tab.path) }
        : { label: t('Refresh'), icon: 'refresh', action: () => loadTab(key, true) },
      ...(adventure?.editable ? [
        { label: t('Rename'), icon: 'edit', action: () => void renameAdventure(adventure.id) },
        { label: t('Delete'), icon: 'trash', action: () => void deleteAdventure(adventure.id, adventure.title) },
      ] : []),
      { separator: true },
      // the order of the tabs without dragging (touch)
      { label: t('Move left'), icon: 'chevron-left', disabled: index <= 0, action: () => moveTab(index, index - 1) },
      { label: t('Move right'), icon: 'chevron-right', disabled: index < 0 || index >= library.tabs.length - 1, action: () => moveTab(index, index + 1) },
      { separator: true },
      { label: t('Close'), icon: 'close', action: () => closeTab(key) },
      { label: t('Close Other'), action: () => closeOtherTabs(key) },
      { label: t('Close All'), action: closeAllTabs },
    ]);
  }
</script>

<div class="wrap" bind:clientWidth={width}>
<div class="tabs" role="tablist">
  {#each shown as { tab, index } (tab.key)}
    <div class="tab" class:active={tab.key === library.active && !library.global && !library.duplicates} role="tab" tabindex="0" aria-selected={tab.key === library.active}
         title={tab.path} draggable={!ui.coarse} use:longpress
         onclick={() => selectTab(tab.key)} onkeydown={(e) => e.key === 'Enter' && selectTab(tab.key)}
         onauxclick={(e) => e.button === 1 && closeTab(tab.key)} oncontextmenu={(e) => menu(e, tab.key)}
         ondragstart={() => (dragIndex = index)} ondragover={(e) => dragIndex !== null && e.preventDefault()}
         ondrop={() => { if (dragIndex !== null && dragIndex !== index) moveTab(dragIndex, index); dragIndex = null; }}>
      <Icon name={icon(tab)} size={15} />
      <span class="name">{tab.name}</span>
      {#if tab.loading}<span class="dot"></span>{/if}
      <button class="close" aria-label={t('Close')} onclick={(e) => { e.stopPropagation(); closeTab(tab.key); }}>
        <Icon name="close" size={12} />
      </button>
    </div>
  {/each}
  {#if library.duplicates}
    <div class="tab active" role="tab" tabindex="0" aria-selected="true" title={t('Duplicates')}>
      <Icon name="copy" size={15} />
      <span class="name">{t('Duplicates')}</span>
      <button class="close" aria-label={t('Close')} onclick={(e) => { e.stopPropagation(); closeDuplicates(); }}>
        <Icon name="close" size={12} />
      </button>
    </div>
  {/if}
</div>
{#if hidden.length}
  <button class="more" title={t('More tabs')} aria-label={t('More tabs')} onclick={showHidden}>
    <Icon name="chevron-down" size={15} /><span class="count">{hidden.length}</span>
  </button>
{/if}
</div>

<style>
  .wrap { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .more { display: flex; align-items: center; gap: 3px; flex: none; height: 34px; padding: 0 8px; border-radius: 10px; color: var(--muted); border: 1px solid var(--border); background: var(--surface); }
  @media (hover: hover) { .more:hover { color: var(--text); background: var(--hover); } }
  .count { font-size: var(--fs-xs); font-weight: 600; }
  .tabs { display: flex; flex: 1; min-width: 0; gap: 6px; overflow: hidden; padding: 2px; }
  .tab { display: flex; align-items: center; gap: 7px; height: 34px; padding: 0 6px 0 13px; border-radius: 10px; color: var(--muted); cursor: pointer; flex: 0 1 auto; min-width: 120px; max-width: 260px; user-select: none; border: 1px solid transparent; transition: background 0.15s, color 0.15s; }
  @media (hover: hover) { .tab:hover { color: var(--text); background: var(--hover); } }
  .tab.active { color: var(--accent); background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 35%, transparent); font-weight: 600; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .close { display: flex; padding: 4px; border-radius: 6px; color: inherit; opacity: 0; }
  .tab.active .close { opacity: 0.8; }
  @media (hover: hover) {
    .tab:hover .close { opacity: 0.8; }
    .close:hover { background: var(--hover); opacity: 1; }
  }
  /* fingers: a tap on a background tab switches to it (its close button is not there to be hit by accident); the active one has a bigger target */
  @media (hover: none) {
    .tab:not(.active) .close { display: none; }
    .tab:not(.active) { padding-right: 13px; }
    .close { padding: 8px; margin-right: -4px; }
  }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1s infinite alternate; }
  @keyframes pulse { to { opacity: 0.3; } }
</style>
