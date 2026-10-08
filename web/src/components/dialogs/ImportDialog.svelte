<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { ImportPreview } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import FolderTree from './FolderTree.svelte';
  import Modal from './Modal.svelte';

  let { directory }: { directory: string } = $props();

  // svelte-ignore state_referenced_locally
  let target = $state(directory);
  let url = $state('');
  let preview = $state<ImportPreview | null>(null);
  let selected = $state<Set<string>>(new Set());
  let makePlaylist = $state(prefs.importOptions.makePlaylist);
  let playlistName = $state('');
  let makeFolder = $state(prefs.importOptions.makeFolder);
  let analyze = $state(prefs.importOptions.analyze);
  let split = $state(prefs.importOptions.split);
  let folderName = $state('');
  let busy = $state(false);
  let error = $state('');

  const tooLong = (duration?: number | null) => !!preview && !!duration && duration > preview.maxMinutes * 60;
  const canSplit = $derived(!!preview && (preview.playlist || preview.entries.some((entry) => (entry.chapters ?? 0) > 1)));
  const chosen = $derived(preview ? preview.entries.filter((entry) => selected.has(entry.url) && !tooLong(entry.duration)) : []);

  function duration(seconds?: number | null): string {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = String(seconds % 60).padStart(2, '0');
    return h ? `${h}:${String(m).padStart(2, '0')}:${s}` : `${m}:${s}`;
  }

  async function lookup(whole?: boolean) {
    if (!url.trim() || busy) return;
    busy = true;
    error = '';
    preview = null;
    try {
      const result = await api.resolveImport(url.trim(), whole);
      preview = result;
      selected = new Set(result.entries.filter((entry) => !tooLong(entry.duration)).map((entry) => entry.url));
      playlistName = result.title;
      folderName = result.title;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }

  function toggle(entryUrl: string) {
    const next = new Set(selected);
    if (!next.delete(entryUrl)) next.add(entryUrl);
    selected = next;
  }

  /** Keeps the options the user could see for the next import (the others keep their earlier value). */
  function remember() {
    const options = prefs.importOptions;
    if (preview?.playlist) {
      options.makePlaylist = makePlaylist;
      options.makeFolder = makeFolder;
    }
    if (canSplit) options.split = split;
    if (data.settings?.voxalyzerActive !== false) options.analyze = analyze;
    savePrefs();
  }

  async function start() {
    if (!preview || !chosen.length || !target) return;
    busy = true;
    remember();
    const body = {
      dir: target,
      entries: chosen.map((entry) => ({ url: entry.url, title: entry.title })),
      split: split && canSplit,
      analyze: analyze && data.settings?.voxalyzerActive !== false,
      folder: preview.playlist && makeFolder && folderName.trim() ? folderName.trim() : undefined,
      album: preview.playlist ? preview.title : undefined,
      playlist: preview.playlist && makePlaylist && playlistName.trim() ? playlistName.trim() : undefined,
    };
    try {
      const { queued } = await api.startImport(body);
      toast(t('{0} songs queued for import', queued), 'success');
      closeDialog();
    } catch (e) {
      busy = false;
      errorToast(e);
    }
  }
</script>

<Modal resizable title={t('Import from YouTube')} onclose={closeDialog} width="760px">
  <div class="section" data-tour="import-url">
    <span class="label-xs">{t('YouTube link')}</span>
    <form class="row" onsubmit={(e) => { e.preventDefault(); void lookup(); }}>
      <input type="text" bind:value={url} placeholder="https://www.youtube.com/watch?v=…" oninput={() => { preview = null; error = ''; }} />
      <button class="btn" type="submit" disabled={busy || !url.trim()}><Icon name="search" size={15} /> {t('Look up')}</button>
    </form>
    {#if busy && !preview}<span class="muted summary">{t('Looking up…')}</span>{/if}
    {#if error}<span class="error summary">{error}</span>{/if}
  </div>

  {#if preview}
    <div class="section">
      <span class="label-xs">{preview.playlist ? t('Playlist: {0}', preview.title) : t('Video')}</span>
      {#if preview.hasVideo}
        <div class="modes">
          <label class="check"><input type="radio" name="scope" checked={preview.playlist} disabled={busy} onchange={() => lookup(true)} /> {t('Whole playlist')}</label>
          <label class="check"><input type="radio" name="scope" checked={!preview.playlist} disabled={busy} onchange={() => lookup(false)} /> {t('Only this video')}</label>
        </div>
      {/if}
      <ul class="entries">
        {#each preview.entries as entry (entry.url)}
          <li class:long={tooLong(entry.duration)}>
            <label title={tooLong(entry.duration) ? t('Longer than {0} minutes', preview.maxMinutes) : ''}>
              <input type="checkbox" checked={selected.has(entry.url) && !tooLong(entry.duration)} disabled={tooLong(entry.duration)}
                     onchange={() => toggle(entry.url)} />
              <span class="ellipsis">{entry.title}</span>
              <span class="muted time">{duration(entry.duration)}</span>
            </label>
          </li>
        {/each}
      </ul>
      {#if preview.playlist}
        <div class="actions">
          <button class="btn" onclick={() => (selected = new Set(preview!.entries.filter((e) => !tooLong(e.duration)).map((e) => e.url)))}>{t('Select all')}</button>
          <button class="btn" onclick={() => (selected = new Set())}>{t('Select none')}</button>
        </div>
        <label class="check"><input type="checkbox" bind:checked={makePlaylist} /> {t('Create a playlist')}</label>
        {#if makePlaylist}<input type="text" bind:value={playlistName} aria-label={t('Name')} />{/if}
        <label class="check"><input type="checkbox" bind:checked={makeFolder} /> {t('Download into a new folder')}</label>
        {#if makeFolder}<input type="text" bind:value={folderName} aria-label={t('Folder name')} />{/if}
      {/if}
    </div>

    <div class="section fill">
      <span class="label-xs">{t('Target folder')}</span>
      <FolderTree bind:selected={target} height="180px" />
    </div>
    {#if canSplit}
      <label class="check" title={t('Videos without chapters are imported as one song.')}>
        <input type="checkbox" bind:checked={split} /> {t('Split chapters into separate songs')}
      </label>
    {/if}
    {#if data.settings?.voxalyzerActive !== false}
      <label class="check"><input type="checkbox" bind:checked={analyze} /> {t('Analyze after import')}</label>
    {/if}
  {/if}

  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={!chosen.length || !target || busy} onclick={start}>
      <Icon name="upload" size={15} /> {t('Import {0} songs', chosen.length)}
    </button>
  {/snippet}
</Modal>

<style>
  .section { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
  .section.fill { flex: 1 1 auto; min-height: 0; }
  .row { display: flex; gap: 8px; }
  .row input { flex: 1; }
  .entries { list-style: none; margin: 0; padding: 4px; max-height: 220px; overflow: auto; border: 1px solid var(--border-strong); border-radius: 12px; }
  .entries label { display: flex; align-items: center; gap: 8px; padding: 3px 4px; cursor: pointer; }
  .entries .ellipsis { flex: 1; min-width: 0; }
  .long { opacity: 0.5; }
  .time { font-variant-numeric: tabular-nums; font-size: var(--fs-sm); }
  .actions { display: flex; gap: 8px; }
  .modes { display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .check { display: flex; align-items: center; gap: 8px; }
  .summary { font-size: var(--fs-sm); }
  .error { color: var(--danger, #d33); }
</style>
