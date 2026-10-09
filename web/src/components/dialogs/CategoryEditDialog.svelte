<script lang="ts" module>
  /** The levels 1, 5 and 10 (low, medium, high) have their own fields; any other level of a category is kept in `other`. */
  export interface CategoryRow { key: string; name: string; group: string; description: string; low: string; medium: string; high: string; other: Record<string, string>; isNew: boolean }
</script>

<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import Modal from './Modal.svelte';

  let { row, onsave, onclose }: { row: CategoryRow; onsave: (row: CategoryRow) => void; onclose: () => void } = $props();

  // svelte-ignore state_referenced_locally
  let form = $state<CategoryRow>({ ...row }); // a copy: the list only changes when the popup is confirmed
  const valid = $derived(!!(form.name.trim() || form.key.trim()));
</script>

<Modal resizable title={row.isNew ? t('New Category') : t('Edit Category')} {onclose} width="680px">
  <form class="cat-form" onsubmit={(e) => { e.preventDefault(); if (valid) onsave(form); }}>
    <label class="field">{t('Name')}<input type="text" bind:value={form.name} /></label>
    <label class="field">{t('Group')}<input type="text" bind:value={form.group} /></label>
    <label class="field wide">{t('Key')}
      {#if row.isNew}<input type="text" placeholder={t('Same as the name')} bind:value={form.key} />{:else}<span class="muted key">{row.key}</span>{/if}</label>
    <label class="field wide">{t('Description')}<textarea rows="2" bind:value={form.description}></textarea></label>
    <div class="levels wide">
      <label class="field"><span><b>1</b> · {t('Low')}</span><input type="text" bind:value={form.low} /></label>
      <label class="field"><span><b>5</b> · {t('Medium')}</span><input type="text" bind:value={form.medium} /></label>
      <label class="field"><span><b>10</b> · {t('High')}</span><input type="text" bind:value={form.high} /></label>
    </div>
  </form>
  {#snippet footer()}
    <button class="btn" onclick={onclose}>{t('Cancel')}</button>
    <button class="btn primary" disabled={!valid} onclick={() => onsave(form)}>{t('Ok')}</button>
  {/snippet}
</Modal>

<style>
  .cat-form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
  .wide { grid-column: 1 / -1; }
  .field { display: flex; flex-direction: column; gap: 5px; }
  .key { font-family: monospace; }
  .levels { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
</style>
