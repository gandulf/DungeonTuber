<script lang="ts">
  import { longpress } from '../../lib/longpress';
  import { canDropOnAdventure, dropOnAdventure } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { library } from '../../lib/stores/library.svelte';
  import { adventures, createAdventure, deleteAdventure, exportAdventure, importAdventure, importAdventureFile, importsRunning, importStage, loadAdventures, openAdventureTab, openImportProgress, renameAdventure } from '../../lib/stores/adventure.svelte';
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

  /** The ways to get an adventure: from a file of this app (ZIP), or from a book (PDF) read by the AI. */
  function importMenu(event: MouseEvent) {
    openMenu(event, [
      { label: t('Import an adventure file (ZIP)…'), icon: 'upload', action: importAdventureFile },
      ...(data.settings?.assistantConfigured
        ? [{ label: t('Import an adventure book (PDF) with the AI'), icon: 'sparkles', disabled: importsRunning(), action: importAdventure }] : []),
    ]);
  }

  function open(id: string) {
    if (ui.mobilePanel === 'tree') ui.mobilePanel = null;
    void openAdventureTab(id);
  }
</script>

<div class="nav-section">
  <div class="row">
    <SectionToggle name="adventures" label={t('Adventures')} />
    <span class="grow"></span>
    <button class="icon-btn mini" title={t('Import an adventure')} aria-label={t('Import an adventure')} aria-haspopup="menu" onclick={importMenu}><Icon name="upload" size={14} /></button>
    <button class="icon-btn mini" title={t('New adventure')} onclick={() => void createAdventure()}><Icon name="plus" size={14} /></button>
  </div>
  {#if adventures.imports.length}
    <!-- the imports (running ones first): a click shows the progress popup with their logs -->
    {@const job = adventures.imports.find((item) => item.status === 'running') ?? adventures.imports[0]}
    <button class="importing" class:failed={job.status === 'error'} title={t('Show the progress and the log of the imports')} onclick={() => void openImportProgress()}>
      {#if job.status === 'running'}<span class="spinner"></span>{:else if job.status === 'done'}<Icon name="check" size={13} />{:else if job.status === 'cancelled'}<Icon name="close" size={13} />{:else}<Icon name="info" size={13} />{/if}
      <span class="ellipsis">{job.status === 'running' ? `${importStage(job)} · ${job.name}` : job.status === 'error' ? t('Import failed: {0}', job.name) : job.status === 'cancelled' ? t('Import cancelled: {0}', job.name) : t('Imported: {0}', job.name)}</span>
    </button>
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
              { label: t('Export (ZIP)'), icon: 'download', action: () => exportAdventure(item.id) },
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
  .importing { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 10px; border-radius: 8px; text-align: left; color: var(--muted); font-size: var(--fs-xs); }
  .importing:hover { background: var(--hover); color: var(--text); }
  .importing.failed { color: var(--red); }
  .spinner { width: 10px; height: 10px; flex: none; border: 2px solid var(--faint); border-right-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (pointer: coarse) {
    .nav-item { min-height: 44px; padding-top: 0; padding-bottom: 0; -webkit-touch-callout: none; -webkit-user-select: none; user-select: none; -webkit-tap-highlight-color: transparent; }
    .nav-item:active { background: var(--hover); }
    .mini { width: 40px; height: 40px; }
  }
</style>
