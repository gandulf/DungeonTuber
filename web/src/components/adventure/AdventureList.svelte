<script lang="ts">
  import { longpress } from '../../lib/longpress';
  import { canDropOnAdventure, dropOnAdventure } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { library } from '../../lib/stores/library.svelte';
  import { adventures, createAdventure, deleteAdventure, importAdventure, loadAdventures, openAdventureTab, renameAdventure } from '../../lib/stores/adventure.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { openMenu, ui } from '../../lib/stores/ui.svelte';
  import { onEvent } from '../../lib/ws';
  import Icon from '../Icon.svelte';
  import SectionToggle from '../SectionToggle.svelte';
  import { prefs } from '../../lib/prefs.svelte';

  const activeId = $derived(library.global || library.duplicates ? null : library.tabs.find((tab) => tab.key === library.active && tab.type === 'adventure')?.path);

  $effect(() => {
    void loadAdventures();
    return onEvent('adventures.changed', () => void loadAdventures());
  });

  let over = $state<string | null>(null); // the adventure songs are dragged over

  function open(id: string) {
    if (ui.mobilePanel === 'tree') ui.mobilePanel = null;
    void openAdventureTab(id);
  }
</script>

<div class="nav-section">
  <div class="row">
    <SectionToggle name="adventures" label={t('Adventures')} />
    <span class="grow"></span>
    {#if data.settings?.assistantConfigured}
      <button class="icon-btn mini" title={t('Import an adventure book (PDF) with the AI')} disabled={!!adventures.importing}
              onclick={importAdventure}><Icon name="upload" size={14} /></button>
    {/if}
    <button class="icon-btn mini" title={t('New adventure')} onclick={() => void createAdventure()}><Icon name="plus" size={14} /></button>
  </div>
  {#if adventures.importing}
    {@const job = adventures.importing}
    <div class="importing" title={job.name}>
      <span class="spinner"></span>
      <span class="ellipsis">{job.step ? t('Writing the notes ({0} of {1})', job.step, job.total - 1) : t('Reading "{0}"…', job.name)}</span>
    </div>
  {/if}
  {#if !prefs.collapsedSections.includes('adventures')}
  {#each adventures.list as item (item.id)}
    <button class="nav-item" class:active={activeId === item.id} class:over={over === item.id} title={item.title} use:longpress
            onclick={() => open(item.id)}
            ondragover={(e) => { if (item.editable && canDropOnAdventure(e.dataTransfer)) { e.preventDefault(); over = item.id; } }}
            ondragleave={() => (over = null)}
            ondrop={(e) => { e.preventDefault(); over = null; void dropOnAdventure(item.id, item.title, e.dataTransfer); }}
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
  {/if}
</div>

<style>
  .nav-section { display: flex; flex-direction: column; gap: 1px; }
  .row { display: flex; align-items: center; justify-content: space-between; }
  .mini { width: 24px; height: 24px; }
  .nav-item { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 9px; color: var(--muted); text-align: left; transition: background 0.15s, color 0.15s; }
  @media (hover: hover) { .nav-item:hover { background: var(--hover); color: var(--text); } }
  .nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .nav-item.over { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .meta { display: flex; flex: none; margin-left: auto; color: var(--faint); }
  .empty { font-size: var(--fs-xs); padding: 2px 10px 4px; line-height: 1.4; }
  .grow { flex: 1; }
  .importing { display: flex; align-items: center; gap: 8px; padding: 6px 10px; color: var(--muted); font-size: var(--fs-xs); }
  .spinner { width: 10px; height: 10px; flex: none; border: 2px solid var(--faint); border-right-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (pointer: coarse) {
    .nav-item { min-height: 44px; padding-top: 0; padding-bottom: 0; -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
    .nav-item:active { background: var(--hover); }
    .mini { width: 40px; height: 40px; }
  }
</style>
