<script lang="ts">
  import { t } from '../lib/i18n.svelte';
  import { closeAllTabs, closeOtherTabs, closeTab, library, loadTab, moveTab, selectTab } from '../lib/stores/library.svelte';
  import { openMenu } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';

  let dragIndex: number | null = null;

  function menu(event: MouseEvent, key: string) {
    openMenu(event, [
      { label: t('Refresh'), icon: 'refresh', action: () => loadTab(key, true) },
      { separator: true },
      { label: t('Close'), icon: 'close', action: () => closeTab(key) },
      { label: t('Close Other'), action: () => closeOtherTabs(key) },
      { label: t('Close All'), action: closeAllTabs },
    ]);
  }
</script>

<div class="tabs" role="tablist">
  {#each library.tabs as tab, index (tab.key)}
    <div class="tab" class:active={tab.key === library.active} role="tab" tabindex="0" aria-selected={tab.key === library.active}
         title={tab.path} draggable="true"
         onclick={() => selectTab(tab.key)} onkeydown={(e) => e.key === 'Enter' && selectTab(tab.key)}
         onauxclick={(e) => e.button === 1 && closeTab(tab.key)} oncontextmenu={(e) => menu(e, tab.key)}
         ondragstart={() => (dragIndex = index)} ondragover={(e) => dragIndex !== null && e.preventDefault()}
         ondrop={() => { if (dragIndex !== null && dragIndex !== index) moveTab(dragIndex, index); dragIndex = null; }}>
      <Icon name={tab.type === 'playlist' ? 'playlist' : 'folder'} size={15} />
      <span class="name">{tab.name}</span>
      {#if tab.loading}<span class="dot"></span>{/if}
      <button class="close" aria-label={t('Close')} onclick={(e) => { e.stopPropagation(); closeTab(tab.key); }}>
        <Icon name="close" size={12} />
      </button>
    </div>
  {/each}
</div>

<style>
  .tabs { display: flex; gap: 2px; overflow-x: auto; scrollbar-width: thin; margin-top: 6px; border-bottom: 1px solid var(--border); }
  .tab { display: flex; align-items: center; gap: 6px; padding: 7px 8px 7px 12px; border-bottom: 2px solid transparent; color: var(--muted); cursor: pointer; flex: 0 1 auto; min-width: 90px; max-width: 280px; border-radius: 6px 6px 0 0; user-select: none; }
  .tab:hover { color: var(--text); background: var(--hover); }
  .tab.active { color: var(--text); border-bottom-color: var(--accent); font-weight: 600; }
  .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
  .close { display: flex; padding: 3px; border-radius: 4px; color: var(--muted); opacity: 0.6; }
  .tab:hover .close, .tab.active .close { opacity: 1; }
  .close:hover { background: var(--hover); color: var(--text); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: pulse 1s infinite alternate; }
  @keyframes pulse { to { opacity: 0.3; } }
</style>
