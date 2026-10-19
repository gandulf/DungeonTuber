<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { startAdventureImport } from '../../lib/stores/adventure.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  type Detail = 'low' | 'medium' | 'high';
  /** The levels of detail of server/adventureimport.py: the AI decides how many blocks a book needs for the chosen one. */
  const DETAILS: { value: Detail; label: string; hint: string }[] = [
    { value: 'low', label: 'Low', hint: 'Few large blocks (a chapter or a major location each) with short notes: the read-aloud text and the essentials.' },
    { value: 'medium', label: 'Medium', hint: 'One block per place, encounter or situation, with the notes a game master needs during play.' },
    { value: 'high', label: 'High', hint: 'Fine blocks (every room, encounter and conversation) with complete notes: all details, checks and values of the book. Takes longer.' },
  ];

  let file = $state<File | null>(null);
  let detail = $state<Detail>('medium');
  let dragOver = $state(false);

  const isPdf = (candidate: File) => candidate.type === 'application/pdf' || candidate.name.toLowerCase().endsWith('.pdf');
  const megabytes = (bytes: number) => `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  function pick(candidate: File | undefined) {
    if (candidate && isPdf(candidate)) file = candidate;
  }

  function start() {
    if (!file) return;
    const chosen = file;
    closeDialog();
    void startAdventureImport(chosen, detail);
  }
</script>

<Modal title={t('Import an adventure book (PDF)')} onclose={closeDialog} width="520px">
  <div class="section">
    <span class="label-xs">{t('PDF file')}</span>
    <label class="drop" class:over={dragOver} ondragover={(e) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); dragOver = true; } }}
           ondragleave={() => (dragOver = false)} ondrop={(e) => { e.preventDefault(); dragOver = false; pick(e.dataTransfer?.files[0]); }}>
      <input type="file" accept="application/pdf,.pdf" hidden onchange={(e) => { pick(e.currentTarget.files?.[0]); e.currentTarget.value = ''; }} />
      {#if file}
        <span class="chosen"><Icon name="upload" size={15} /><span class="ellipsis" title={file.name}>{file.name}</span><span class="muted">{megabytes(file.size)}</span></span>
      {:else}
        <span class="muted">{t('Drop a PDF here or click to choose one')}</span>
      {/if}
    </label>
  </div>

  <div class="section">
    <span class="label-xs" id="import-detail">{t('Level of detail')}</span>
    <div class="seg" role="radiogroup" aria-labelledby="import-detail">
      {#each DETAILS as option (option.value)}
        <button type="button" role="radio" aria-checked={detail === option.value} class:on={detail === option.value} onclick={() => (detail = option.value)}>{t(option.label)}</button>
      {/each}
    </div>
    <span class="muted hint">{t(DETAILS.find((option) => option.value === detail)!.hint)}</span>
    <span class="muted hint">{t('The AI decides how many blocks that takes: a longer book gets more of them.')}</span>
  </div>

  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={!file} onclick={start}><Icon name="upload" size={15} /> {t('Import')}</button>
  {/snippet}
</Modal>

<style>
  .section { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .drop { display: flex; align-items: center; justify-content: center; min-height: 90px; padding: 10px; border: 2px dashed var(--border-strong); border-radius: 12px;
          font-size: var(--fs-sm); cursor: pointer; }
  .drop:hover, .drop.over { border-color: var(--accent); background: var(--accent-soft); }
  .chosen { display: flex; align-items: center; gap: 8px; min-width: 0; max-width: 100%; }
  .seg { align-self: flex-start; }
  .hint { font-size: var(--fs-sm); }
</style>
