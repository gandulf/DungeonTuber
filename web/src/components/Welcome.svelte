<script lang="ts">
  import { t } from '../lib/i18n.svelte';
  import { prefs } from '../lib/prefs.svelte';
  import { openTab } from '../lib/stores/library.svelte';
  import { ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';
</script>

<div class="welcome">
  <img src="/icon.png" alt="" width="72" height="72" />
  <h1>{t('Welcome to Dungeon Tuber')}</h1>
  <p class="muted">{t('Double-click a folder or playlist in the file tree to open it as a tab, then use the filters to find the perfect music for your scene.')}</p>
  <div class="actions">
    {#if prefs.treeRoot}
      <button class="btn primary" onclick={() => openTab('dir', prefs.treeRoot!)}><Icon name="folder" size={16} /> {t('Open current folder')}</button>
    {/if}
    <button class="btn" onclick={() => (ui.tour = true)}><Icon name="info" size={16} /> {t('Show Tour')}</button>
  </div>
  <ul class="tips muted">
    <li><kbd>Ctrl</kbd>+<kbd>P</kbd> {t('Play')} · <kbd>Ctrl</kbd>+<kbd>N</kbd> {t('Next')} · <kbd>Ctrl</kbd>+<kbd>B</kbd> {t('Previous')}</li>
    <li>{t('Drop mp3 files on the file tree to upload them.')}</li>
    <li>{t('Drag a tag chip onto a song to tag it.')}</li>
  </ul>
</div>

<style>
  .welcome { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 10px; padding: 32px; }
  h1 { margin: 6px 0 0; font-size: 24px; }
  p { max-width: 520px; line-height: 1.5; }
  .actions { display: flex; gap: 10px; flex-wrap: wrap; justify-content: center; }
  .tips { list-style: none; padding: 0; margin-top: 18px; display: flex; flex-direction: column; gap: 6px; font-size: var(--fs-sm); }
  kbd { border: 1px solid var(--border-strong); border-bottom-width: 2px; border-radius: 4px; padding: 0 5px; font-size: var(--fs-xs); background: var(--surface); }
</style>
