<script lang="ts">
  import { onDestroy } from 'svelte';
  import { api, coverUrl } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { fileNameFor, normalizedFlag } from '../../lib/normalize';
  import { reloadPlaylistTabs, updateTrack } from '../../lib/stores/library.svelte';
  import { refreshCurrentTrack } from '../../lib/stores/player.svelte';
  import { updateEffectTrack } from '../../lib/stores/effects.svelte';
  import { closeDialog, ownDialog, errorToast } from '../../lib/stores/ui.svelte';
  import type { LightSetting, LookupCandidate, LookupResult, Normalized, Track } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import LightEditor from './LightEditor.svelte';
  import Modal from './Modal.svelte';

  /** `playlist`: the song was opened from this playlist, so its scene name there can be edited too.
   *  `normalize`: looks up the metadata at once (the "Normalize metadata…" menu entry). */
  let { track, playlist, normalize = false }: { track: Track; playlist?: string; normalize?: boolean } = $props();

  // svelte-ignore state_referenced_locally
  let form = $state({
    scene: track.scene ?? '',
    name: track.file.replace(/\.mp3$/i, ''),
    title: track.title ?? '',
    artist: track.artist ?? '',
    album: track.album ?? '',
    track: track.track ?? 0,
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

  // the dialog focuses its first field (the favorite checkbox) when it opens: the scene name wins afterwards
  const split = (value: string) => value.split(',').map((s) => s.trim()).filter(Boolean);

  // --- normalize: the metadata of AcoustID / MusicBrainz -----------------------------------------------------------

  let lookup = $state<LookupResult | null>(null);
  let lookingUp = $state(false);
  let picked = $state<LookupCandidate | null>(null);

  async function findMetadata() {
    lookingUp = true;
    picked = null;
    try {
      lookup = await api.lookupTrack(track.id);
    } catch (e) {
      errorToast(e);
    } finally {
      lookingUp = false;
    }
  }

  // svelte-ignore state_referenced_locally
  if (normalize) void findMetadata();

  /** Fills the fields with the candidate; nothing is written before Save. */
  function apply(candidate: LookupCandidate) {
    picked = candidate;
    form.title = candidate.title;
    form.artist = candidate.artist;
    if (candidate.album) form.album = candidate.album;
    if (candidate.track) form.track = candidate.track;
    form.name = fileNameFor(candidate);
  }

  /** The flag of the song, or the one it gets on Save after a match was picked. */
  const flag = $derived<Normalized | null>(picked ? normalizedFlag(picked) : (track.normalized ?? null));
  const sourceName = (source: string) => (source === 'acoustid' ? 'AcoustID' : 'MusicBrainz');

  const minutes = (seconds: number | null) => (seconds ? `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}` : '');

  function pickCover(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    cover = file;
    if (preview) URL.revokeObjectURL(preview);
    preview = URL.createObjectURL(file);
  }

  const close = ownDialog(); // after the save: this dialog, not one opened meanwhile
  onDestroy(() => {
    if (preview) URL.revokeObjectURL(preview); // the picked cover
  });

  async function save() {
    if (saving) return; // Enter in a field submits the form as well
    saving = true;
    try {
      // before a rename: the playlist still refers to the song by its current path
      if (playlist && form.scene.trim() !== (track.scene ?? '')) {
        await api.setScene(playlist, track.id, form.scene.trim());
        reloadPlaylistTabs(playlist);
      }
      let updated = await api.patchTrack(track.id, {
        title: form.title, artist: form.artist, album: form.album, track: form.track || null, genres: split(form.genres), bpm: form.bpm || null,
        tags: split(form.tags), summary: form.summary, favorite: form.favorite, light,
        ...(picked ? { normalized: normalizedFlag(picked) } : {}),
        ...(form.name.trim() && form.name.trim() !== track.file.replace(/\.mp3$/i, '') ? { name: form.name.trim() } : {}),
      });
      if (cover) updated = { ...(await api.putCover(updated.id, cover)), previous_id: track.id };
      updateTrack(updated);
      updateEffectTrack(updated);
      refreshCurrentTrack(updated);
      close();
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
      <button class="btn sm" type="button" disabled={lookingUp} title={t('Looks up title, artist and album in MusicBrainz and AcoustID')} onclick={findMetadata}>
        <Icon name={lookingUp ? 'refresh' : 'search'} size={14} class={lookingUp ? 'spin' : ''} /> {t('Normalize…')}
      </button>
      {#if flag}
        {@const tip = (picked ? t('Normalized on Save with {0}', sourceName(flag.source)) : t('Normalized with {0} on {1}', sourceName(flag.source), flag.at ?? '–'))
          + (flag.recording_id ? ` · ${t('Open in MusicBrainz')}` : '')}
        {#if flag.recording_id}
          <a class="normalized" class:pending={!!picked} href="https://musicbrainz.org/recording/{flag.recording_id}" target="_blank" rel="noopener noreferrer" title={tip}>
            <Icon name="check" size={12} /> {t('Normalized')}
          </a>
        {:else}
          <span class="normalized" class:pending={!!picked} title={tip}><Icon name="check" size={12} /> {t('Normalized')}</span>
        {/if}
      {/if}
    </div>
    <div class="fields">
      {#if lookup}
        <div class="wide lookup">
          <div class="lookup-head">
            <span class="label-xs">{t('Matches')}</span>
            <span class="muted small">{t('Pick one to fill the fields; nothing is saved before Save.')}</span>
            <span class="grow"></span>
            <button class="icon-btn" type="button" title={t('Close')} aria-label={t('Close')} onclick={() => (lookup = null)}><Icon name="close" size={14} /></button>
          </div>
          {#each lookup.candidates as candidate, i (i)}
            <button type="button" class="candidate" class:picked={picked === candidate} onclick={() => apply(candidate)}>
              <span class="ellipsis"><strong>{candidate.title}</strong> · {candidate.artist}</span>
              <span class="muted small ellipsis">
                {[candidate.album, candidate.year, candidate.track ? `#${candidate.track}` : '', minutes(candidate.length)].filter(Boolean).join(' · ')}
              </span>
              <span class="score" class:high={candidate.score >= 90} title={candidate.source === 'acoustid' ? t('Found by the audio fingerprint (AcoustID)') : t('Found by title and artist (MusicBrainz)')}>
                {candidate.score}% <span class="src">{candidate.source === 'acoustid' ? 'AcoustID' : 'MusicBrainz'}</span>
              </span>
            </button>
          {:else}
            <p class="muted small">{t('No matches found.')}</p>
          {/each}
          {#each lookup.errors as error (error)}<p class="warn small">{error}</p>{/each}
        </div>
      {/if}
      {#if playlist}
        <label class="wide scene">
          <span>{t('Scene name')} <span class="muted">· {t('Only used in this playlist')}</span></span>
          <input type="text" bind:value={form.scene} data-autofocus />
        </label>
      {/if}
      <label class="wide">{t('Name')}<input type="text" bind:value={form.name} /></label>
      <label class="wide">{t('Title')}<input type="text" bind:value={form.title} /></label>
      <label>{t('Artist')}<input type="text" bind:value={form.artist} /></label>
      <label>{t('Album')}<input type="text" bind:value={form.album} /></label>
      <div class="wide triple">
        <label>{t('Genre')}<input type="text" bind:value={form.genres} placeholder={t('Separate multiple tags with comma')} /></label>
        <label>{t('Track')}<input type="number" min="0" max="9999" bind:value={form.track} /></label>
        <label>{t('BPM')}<input type="number" min="0" max="300" bind:value={form.bpm} /></label>
      </div>
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
      {#if track.ufid}
        <span class="wide path muted" title={t('Stable song id, kept when the file is moved or renamed')}>{t('ID')} {track.ufid}</span>
      {/if}
    </div>
    <button type="submit" hidden disabled={saving} aria-label={t('Save')}></button>
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
  .fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px 12px; }
  .triple { display: grid; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr) minmax(0, 1fr); gap: 12px; }
  .fields label { display: flex; flex-direction: column; gap: 4px; font-size: var(--fs-sm); color: var(--muted); }
  .fields input, .fields textarea { color: var(--text); }
  .wide { grid-column: 1 / -1; }
  .scene > span:first-child { color: var(--gold); font-weight: 600; }
  .scene .muted { font-weight: 400; }
  .check { display: flex; align-items: center; gap: 6px; }
  .small { font-size: var(--fs-xs); }
  .path { font-size: var(--fs-xs); overflow-wrap: anywhere; }
  .lookup { display: flex; flex-direction: column; gap: 4px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface-2); max-height: 260px; overflow: auto; }
  .lookup-head { display: flex; align-items: center; gap: 8px; }
  .grow { flex: 1; }
  .candidate { display: grid; grid-template-columns: 1fr auto; grid-template-areas: 'name score' 'meta score'; gap: 0 10px; align-items: center; text-align: left; padding: 6px 8px; border-radius: var(--radius-sm); border: 1px solid transparent; }
  .candidate:hover { background: var(--hover); }
  .candidate.picked { border-color: var(--accent); background: var(--accent-soft); }
  .candidate > :nth-child(1) { grid-area: name; min-width: 0; }
  .candidate > :nth-child(2) { grid-area: meta; min-width: 0; }
  .score { grid-area: score; font-size: var(--fs-xs); font-weight: 600; color: var(--muted); text-align: right; }
  .score.high { color: var(--green); }
  .src { display: block; font-weight: 400; color: var(--faint); }
  .warn { color: var(--danger, #d9534f); margin: 0; }
  .lookup p { margin: 0; }
  .normalized { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 10px; font-size: var(--fs-xs); font-weight: 600;
    background: var(--green-soft); color: var(--green); text-decoration: none; }
  .normalized.pending { background: transparent; border: 1px dashed var(--green); }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } .fields { grid-template-columns: minmax(0, 1fr); } }
</style>
