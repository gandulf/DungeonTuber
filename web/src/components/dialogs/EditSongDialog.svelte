<script lang="ts">
  import { api, coverUrl } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { updateTrack } from '../../lib/stores/library.svelte';
  import { refreshCurrentTrack } from '../../lib/stores/player.svelte';
  import { updateEffectTrack } from '../../lib/stores/effects.svelte';
  import { closeDialog, errorToast } from '../../lib/stores/ui.svelte';
  import type { LightSetting, Track } from '../../lib/types';
  import LightEditor from './LightEditor.svelte';
  import Modal from './Modal.svelte';

  let { track }: { track: Track } = $props();

  // svelte-ignore state_referenced_locally
  let form = $state({
    name: track.file.replace(/\.mp3$/i, ''),
    title: track.title ?? '',
    artist: track.artist ?? '',
    album: track.album ?? '',
    genres: track.genres.join(', '),
    bpm: track.bpm ?? 0,
    tags: track.tags.join(', '),
    summary: track.summary ?? '',
    favorite: track.favorite,
  });
  // svelte-ignore state_referenced_locally
  let light = $state<LightSetting | null>(track.light ? { ...track.light } : null);
  let cover = $state<File | null>(null);
  let preview = $state<string | null>(null);
  let saving = $state(false);

  const split = (value: string) => value.split(',').map((s) => s.trim()).filter(Boolean);

  function pickCover(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    cover = file;
    if (preview) URL.revokeObjectURL(preview);
    preview = URL.createObjectURL(file);
  }

  async function save() {
    saving = true;
    try {
      let updated = await api.patchTrack(track.id, {
        title: form.title, artist: form.artist, album: form.album, genres: split(form.genres), bpm: form.bpm || null,
        tags: split(form.tags), summary: form.summary, favorite: form.favorite, light,
        ...(form.name.trim() && form.name.trim() !== track.file.replace(/\.mp3$/i, '') ? { name: form.name.trim() } : {}),
      });
      if (cover) updated = { ...(await api.putCover(updated.id, cover)), previous_id: track.id };
      updateTrack(updated);
      updateEffectTrack(updated);
      refreshCurrentTrack(updated);
      closeDialog();
    } catch (e) {
      errorToast(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal title={t('Edit Song')} onclose={closeDialog} width="680px">
  <form class="grid" data-tour="edit-form" onsubmit={(e) => { e.preventDefault(); void save(); }}>
    <div class="cover-col">
      <label class="cover">
        {#if preview}<img src={preview} alt="" />{:else if track.has_cover}<img src={coverUrl(track.id, 256)} alt="" />{:else}<span class="muted">{t('Cover')}</span>{/if}
        <input type="file" accept="image/*" hidden onchange={pickCover} />
      </label>
      <span class="muted hint">{t('Select Image')}</span>
      <label class="check"><input type="checkbox" bind:checked={form.favorite} /> {t('Favorite')}</label>
    </div>
    <div class="fields">
      <label class="wide">{t('Name')}<input type="text" bind:value={form.name} /></label>
      <label class="wide">{t('Title')}<input type="text" bind:value={form.title} /></label>
      <label>{t('Artist')}<input type="text" bind:value={form.artist} /></label>
      <label>{t('Album')}<input type="text" bind:value={form.album} /></label>
      <label>{t('Genre')}<input type="text" bind:value={form.genres} placeholder={t('Separate multiple tags with comma')} /></label>
      <label>{t('BPM')}<input type="number" min="0" max="300" bind:value={form.bpm} /></label>
      <label class="wide">{t('Tags')}<input type="text" bind:value={form.tags} placeholder={t('Separate multiple tags with comma')} /></label>
      <label class="wide">{t('Summary')}<textarea rows="3" bind:value={form.summary}></textarea></label>
      <div class="wide">
        <span class="label-xs">{t('Lights')}</span>
        <LightEditor bind:value={light} />
      </div>
      {#if track.uploaded_by}
        <span class="wide muted small">
          {t('Uploaded by {0}', track.uploaded_by)}{track.uploaded_at ? ` · ${new Date(track.uploaded_at * 1000).toLocaleString()}` : ''}
        </span>
      {/if}
      <span class="wide path muted" title={track.path}>{track.path}</span>
    </div>
    <button type="submit" hidden aria-label={t('Save')}></button>
  </form>
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={saving} onclick={save}>{t('Save')}</button>
  {/snippet}
</Modal>

<style>
  .grid { display: grid; grid-template-columns: 160px 1fr; gap: 18px; }
  .cover-col { display: flex; flex-direction: column; gap: 8px; align-items: center; }
  .cover { width: 160px; height: 160px; border-radius: 10px; border: 1px dashed var(--border-strong); display: grid; place-items: center; overflow: hidden; cursor: pointer; background: var(--surface-2); }
  .cover img { width: 100%; height: 100%; object-fit: cover; }
  .hint { font-size: var(--fs-xs); }
  .fields { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 12px; }
  .fields label { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-sm); color: var(--muted); }
  .fields input, .fields textarea { color: var(--text); }
  .wide { grid-column: 1 / -1; }
  .check { display: flex; align-items: center; gap: 6px; }
  .small { font-size: var(--fs-xs); }
  .path { font-size: var(--fs-xs); overflow-wrap: anywhere; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
</style>
