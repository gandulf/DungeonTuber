<script lang="ts">
  import { uploadFiles } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import { isMp3, itemsFromDrop, itemsFromFiles, type UploadItem } from '../../lib/upload';
  import Icon from '../Icon.svelte';
  import FolderSelect from './FolderSelect.svelte';
  import Modal from './Modal.svelte';

  let { directory, initial = [] }: { directory: string; initial?: UploadItem[] } = $props();

  // svelte-ignore state_referenced_locally
  let target = $state(directory);
  // svelte-ignore state_referenced_locally
  let items = $state<UploadItem[]>(initial.filter((item) => isMp3(item.file.name)));
  let skipped = $state(0);
  let dragOver = $state(false);
  let busy = $state(false);

  const subfolderCount = $derived(new Set(items.map((item) => item.path.split('/').slice(0, -1).join('/')).filter(Boolean)).size);

  function add(added: UploadItem[]) {
    const known = new Set(items.map((item) => item.path));
    const mp3s = added.filter((item) => isMp3(item.file.name));
    skipped += added.length - mp3s.length;
    items = [...items, ...mp3s.filter((item) => !known.has(item.path) && known.add(item.path))];
  }

  function picked(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    add(itemsFromFiles(input.files ?? []));
    input.value = '';
  }

  async function dropped(event: DragEvent) {
    event.preventDefault();
    dragOver = false;
    add(await itemsFromDrop(event.dataTransfer));
  }

  function clear() {
    items = [];
    skipped = 0;
  }

  async function start() {
    busy = true;
    const files = items;
    closeDialog();
    await uploadFiles(target, files);
  }
</script>

<Modal resizable title={t('Upload songs')} onclose={closeDialog} width="760px">
  <div class="section">
    <span class="label-xs">{t('Target folder')}</span>
    <FolderSelect bind:selected={target} />
  </div>

  <div class="section fill" data-tour="upload-drop">
    <span class="label-xs">{t('Files')}</span>
    <div class="drop" class:over={dragOver} role="presentation"
         ondragover={(e) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); dragOver = true; } }}
         ondragleave={() => (dragOver = false)} ondrop={dropped}>
      {#if items.length}
        <ul>
          {#each items as item (item.path)}
            <li class="ellipsis" title={item.path}><Icon name="music" size={13} /> {item.path}</li>
          {/each}
        </ul>
      {:else}
        <span class="muted">{t('Drop mp3 files or folders here')}</span>
      {/if}
    </div>
    <div class="actions">
      <label class="btn">
        <Icon name="music" size={15} /> {t('Add files…')}
        <input type="file" accept=".mp3,audio/mpeg" multiple hidden onchange={picked} />
      </label>
      <label class="btn">
        <Icon name="folder" size={15} /> {t('Add folder…')}
        <input type="file" multiple hidden {...{ webkitdirectory: true }} onchange={picked} />
      </label>
      {#if items.length}<button class="btn" onclick={clear}>{t('Clear')}</button>{/if}
    </div>
    {#if items.length}
      <span class="muted summary">
        {t('{0} files selected', items.length)}{subfolderCount ? ` · ${t('{0} subfolders will be created', subfolderCount)}` : ''}
      </span>
    {/if}
    {#if skipped}<span class="muted summary">{t('{0} files that are not mp3 were skipped.', skipped)}</span>{/if}
  </div>

  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={!items.length || busy} onclick={start}>
      <Icon name="upload" size={15} /> {t('Upload')}
    </button>
  {/snippet}
</Modal>

<style>
  .section { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .section.fill { flex: 1 1 auto; min-height: 0; }
  .drop { min-height: 90px; max-height: 170px; overflow: auto; display: flex; align-items: center; justify-content: center; padding: 8px; border: 2px dashed var(--border-strong); border-radius: 12px; font-size: var(--fs-sm); }
  .section.fill .drop { flex: 1 1 auto; max-height: none; }
  .drop.over { border-color: var(--accent); background: var(--accent-soft); }
  ul { list-style: none; margin: 0; padding: 0; width: 100%; align-self: flex-start; }
  li { padding: 2px 4px; color: var(--muted); }
  .actions { display: flex; flex-wrap: wrap; gap: 8px; }
  .actions .btn { cursor: pointer; }
  .summary { font-size: var(--fs-sm); }
</style>
