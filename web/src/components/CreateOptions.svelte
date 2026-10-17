<script lang="ts">
  import { uploadTarget } from '../lib/actions';
  import { locale, t } from '../lib/i18n.svelte';
  import { COMPOSE_DURATIONS, composeOptions, CREATE_KIND_LABELS, effectOptions, saveComposeOptions, saveEffectOptions, SOUND_DURATIONS,
           type CreateKind } from '../lib/stores/assistant.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { effects } from '../lib/stores/effects.svelte';
  import FolderSelect from './dialogs/FolderSelect.svelte';

  /** The options of generated music and sounds, shared by the create mode of the assistant and the AI of a block: the kind (of
   *  `kinds`), the length, the vocals and the language of the lyrics of a piece, and the target folder. The options are the same
   *  everywhere (composeOptions, effectOptions) and remembered in the browser; only the kind is the caller's. */
  let { kinds, kind = $bindable(), onkind }: { kinds: CreateKind[]; kind: CreateKind; onkind?: () => void } = $props();

  const composing = $derived(kind === 'song');
  const formatDuration = (seconds: number) => (seconds < 60 ? `${seconds} s` : `${seconds / 60} min`);

  $effect(() => {
    if (kinds.length && !kinds.includes(kind)) kind = kinds[0];
  });
  $effect(() => {
    if (composing && !composeOptions.dir) composeOptions.dir = uploadTarget() ?? '';
  });
  // sounds go into the effects folder until another folder is chosen
  $effect(() => {
    if (!composing && !effectOptions.dir) effectOptions.dir = effects.directory || data.settings?.effectsDirectory || uploadTarget() || '';
  });
  // the lyrics can be written in the languages of the app; until one is chosen, in the language of the app
  const lyricLanguages = $derived(data.locales.length ? data.locales : [locale()]);
  $effect(() => {
    if (composing && !lyricLanguages.includes(composeOptions.language)) composeOptions.language = lyricLanguages.includes(locale()) ? locale() : lyricLanguages[0];
  });
</script>

{#if kinds.length > 1}
  <select bind:value={kind} onchange={() => onkind?.()} aria-label={t('Kind')} title={t('Kind')}>
    {#each kinds as item (item)}<option value={item}>{t(CREATE_KIND_LABELS[item])}</option>{/each}
  </select>
{/if}
{#if composing}
  <select bind:value={composeOptions.duration} onchange={saveComposeOptions} aria-label={t('Length')} title={t('Length')}>
    {#each COMPOSE_DURATIONS as seconds (seconds)}<option value={seconds}>{formatDuration(seconds)}</option>{/each}
  </select>
  <label class="check"><input type="checkbox" checked={!composeOptions.instrumental}
         onchange={(e) => { composeOptions.instrumental = !e.currentTarget.checked; saveComposeOptions(); }} /> {t('Vocals')}</label>
  {#if !composeOptions.instrumental}
    <select bind:value={composeOptions.language} onchange={saveComposeOptions} aria-label={t('Language of the lyrics')} title={t('Language of the lyrics')}>
      {#each lyricLanguages as code (code)}<option value={code}>{t(code)}</option>{/each}
    </select>
  {/if}
  <span class="folder" title={t('Target folder')}><FolderSelect bind:selected={composeOptions.dir} /></span>
{:else}
  <select bind:value={effectOptions.duration} onchange={saveEffectOptions} aria-label={t('Length')} title={t('Length')}>
    {#each SOUND_DURATIONS as seconds (seconds)}<option value={seconds}>{seconds ? formatDuration(seconds) : t('As suggested')}</option>{/each}
  </select>
  <span class="folder" title={t('Target folder')}><FolderSelect bind:selected={effectOptions.dir} /></span>
{/if}

<style>
  .check { display: flex; align-items: center; gap: 4px; white-space: nowrap; }
  .folder { flex: 1; min-width: 0; }
</style>
