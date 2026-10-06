<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import Modal from './Modal.svelte';
</script>

<Modal title={t('About')} onclose={closeDialog} width="420px">
  <div class="about">
    <img src="/icon.png" alt="" width="72" height="72" />
    <h3>Dungeon Tuber</h3>
    <p class="muted">{t('Version')}: {data.version?.current ?? '–'}</p>
    {#if data.version?.newer}
      <p><a href={data.version.download} target="_blank" rel="noreferrer">{t('Newer version available {0}', data.version.latest ?? '')}</a></p>
    {/if}
    <p>{t('Author')}: Gandulf Kohlweiss</p>
    <p><a href="https://github.com/gandulf/DungeonTuber" target="_blank" rel="noreferrer">github.com/gandulf/DungeonTuber</a></p>
  </div>
</Modal>

<style>
  .about { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 2px; }
  h3 { margin: 8px 0 2px; }
  p { margin: 4px 0; }
  a { color: var(--accent); }
</style>
