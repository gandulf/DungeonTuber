<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import type { Chapter, LightSetting } from '../../lib/types';
  import LightEditor from './LightEditor.svelte';
  import Modal from './Modal.svelte';

  let { chapter, onSave }: { chapter: Chapter | null; onSave: (title: string, light: LightSetting | null) => void } = $props();

  // svelte-ignore state_referenced_locally
  let title = $state(chapter?.title ?? '');
  // svelte-ignore state_referenced_locally
  let light = $state<LightSetting | null>(chapter?.light ? { ...chapter.light } : null);

  function save() {
    onSave(title.trim() || t('Chapter'), light);
    closeDialog();
  }
</script>

<Modal title={chapter ? t('Edit chapter') : t('Add chapter')} onclose={closeDialog} width="420px">
  <form class="form" onsubmit={(e) => { e.preventDefault(); save(); }}>
    <label>{t('Name')}<input type="text" bind:value={title} /></label>
    <span class="label-xs">{t('Lights')}</span>
    <LightEditor bind:value={light} />
  </form>
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" onclick={save}>{t('Save')}</button>
  {/snippet}
</Modal>

<style>
  .form { display: flex; flex-direction: column; gap: 10px; }
  label { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-sm); }
</style>
