<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { library } from '../../lib/stores/library.svelte';
  import { adventures, createAdventure, deleteAdventure, loadAdventures, openAdventureTab, renameAdventure } from '../../lib/stores/adventure.svelte';
  import { openMenu, ui } from '../../lib/stores/ui.svelte';
  import { onEvent } from '../../lib/ws';
  import Icon from '../Icon.svelte';

  const activeId = $derived(library.global || library.duplicates ? null : library.tabs.find((tab) => tab.key === library.active && tab.type === 'adventure')?.path);

  $effect(() => {
    void loadAdventures();
    return onEvent('adventures.changed', () => void loadAdventures());
  });

  function open(id: string) {
    if (ui.mobilePanel === 'tree') ui.mobilePanel = null;
    void openAdventureTab(id);
  }
</script>

<div class="nav-section">
  <div class="row">
    <span class="label-xs">{t('Adventures')}</span>
    <button class="icon-btn mini" title={t('New adventure')} onclick={() => void createAdventure()}><Icon name="plus" size={14} /></button>
  </div>
  {#each adventures.list as item (item.id)}
    <button class="nav-item" class:active={activeId === item.id} title={item.title}
            onclick={() => open(item.id)}
            oncontextmenu={(e) => openMenu(e, [
              { label: t('Open'), icon: 'mask', action: () => open(item.id) },
              ...(item.editable ? [
                { label: t('Rename'), icon: 'edit', action: () => void renameAdventure(item.id) },
                { label: t('Delete'), icon: 'trash', action: () => void deleteAdventure(item.id, item.title) },
              ] : []),
            ])}>
      <Icon name="mask" size={16} /><span class="ellipsis">{item.title}</span>
      <span class="meta" title={item.visibility === 'public' ? t('Public') : t('Private')}>
        <Icon name={item.visibility === 'public' ? 'users' : 'lock'} size={12} />
      </span>
    </button>
  {:else}
    <span class="empty muted">{t('Plan a story with notes and music for every scene.')}</span>
  {/each}
</div>

<style>
  .nav-section { display: flex; flex-direction: column; gap: 1px; }
  .nav-section .label-xs { padding: 4px 8px 6px; }
  .row { display: flex; align-items: center; justify-content: space-between; }
  .mini { width: 24px; height: 24px; }
  .nav-item { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 9px; color: var(--muted); text-align: left; transition: background 0.15s, color 0.15s; }
  .nav-item:hover { background: var(--hover); color: var(--text); }
  .nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .meta { display: flex; flex: none; margin-left: auto; color: var(--faint); }
  .empty { font-size: var(--fs-xs); padding: 2px 10px 4px; line-height: 1.4; }
</style>
