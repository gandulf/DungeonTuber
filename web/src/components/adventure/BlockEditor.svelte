<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../../lib/api';
  import { blockSongsFromTransfer, canDropOnBlock } from '../../lib/actions';
  import { addAdventureMusic, addLink, addMusic, assignMusic, linksFrom, linksTo, moveEntry, refKey, removeLink } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { blockLinkTarget, imageUrl, markMissingSongLinks, renderNotes, songLinkIds, songLinkTarget } from '../../lib/notes';
  import { adventures, change, deleteBlock, effectKey, coverPending, flushSave, missingEntries, playSongLink, refTracks, searchSongsForBlock, selectedBlock, setPlayed, startEffect } from '../../lib/stores/adventure.svelte';
  import { player, playQueue, togglePlay } from '../../lib/stores/player.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { askConfirm, errorToast, openDialog, toast } from '../../lib/stores/ui.svelte';
  import type { Effect, MusicRef } from '../../lib/types';
  import type { CreateKind } from '../../lib/stores/assistant.svelte';
  import Icon from '../Icon.svelte';
  import ImagePopup from '../dialogs/ImagePopup.svelte';
  import AiDialog from './AiDialog.svelte';
  import PickMusicDialog from './PickMusicDialog.svelte';

  // the notes editor (Tiptap) is a chunk of its own, loaded once notes are edited
  let notesEditor: Promise<typeof import('./NotesEditor.svelte').default> | null = null;
  const loadNotesEditor = () => (notesEditor ??= import('./NotesEditor.svelte').then((module) => module.default));

  const block = $derived(selectedBlock());
  const adventure = $derived(adventures.current!);

  let linkTarget = $state('');

  const others = $derived(adventure.blocks.filter((item) => item.id !== block?.id));
  const outgoing = $derived(block ? linksFrom(adventure, block.id) : []);
  const incoming = $derived(block ? linksTo(adventure, block.id) : []);
  const titleOf = (id: string) => adventure.blocks.find((item) => item.id === id)?.title || t('Untitled');

  async function cleanUpImages() {
    try {
      await flushSave(); // the server looks at the saved notes
      const { removed } = await api.cleanupAdventureImages(adventure.id);
      toast(t('{0} unused image(s) removed.', removed));
    } catch (e) {
      errorToast(e);
    }
  }

  function previewClick(event: MouseEvent) {
    const song = songLinkTarget(event.target);
    if (song) {
      event.preventDefault();
      void playSongLink(song);
      return;
    }
    const target = blockLinkTarget(event.target);
    if (!target) return;
    event.preventDefault();
    adventures.selected = target;
  }

  function addMusicDialog() {
    // the block chooses from the adventure's music; what comes from the library is assigned to the adventure as well
    openDialog(PickMusicDialog, {
      pool: adventure.music,
      // a song of the adventure (also one of its playlists) is there already; one from the library is assigned to the adventure too
      onpick: (ref: MusicRef, fromPool: boolean) => change((a) => (fromPool ? addMusic(block!, ref) : assignMusic(a, block!, ref))),
      has: (ref: MusicRef) => !!block?.music.some((item) => refKey(item) === refKey(ref)),
    });
  }

  /** The effects of the effects folder in the dialog of the music (with a play button each); a pick adds a looped effect. */
  function addEffectDialog() {
    openDialog(PickMusicDialog, {
      effect: {
        onpick: (effect: Effect) => change(() => {
          if (block && !block.effects.some((item) => item.path === effect.path)) block.effects.push({ path: effect.path, name: effect.title || effect.name, loop: true, autostart: false });
        }),
        has: (path: string) => !!block?.effects.some((item) => item.path === path),
      },
    });
  }

  function newLink() {
    if (!block || !linkTarget) return;
    change((a) => addLink(a, block.id, linkTarget));
    linkTarget = '';
  }

  /** The AI helpers sit next to what they change (see AiDialog.svelte): the notes, the music and the effects (the cover has its own
   *  button); each needs the service it talks to. */
  const aiText = $derived(!!(data.settings?.groqConfigured || data.settings?.assistantConfigured));
  const aiSounds = $derived(!!data.settings?.soundGenConfigured);
  // music: a piece of the music generation (ACE-Step) and background music of the sound generation, as far as they are set up
  const musicKinds = $derived<CreateKind[]>([...(data.settings?.musicGenConfigured ? ['song' as const] : []), ...(aiSounds ? ['music' as const] : [])]);
  function openAi(task: 'draft' | 'songs' | 'sound', kinds?: CreateKind[]) {
    if (block) openDialog(AiDialog, { task, blockId: block.id, kinds });
  }

  // --- drag & drop: songs and effects are put in order by dragging them; songs of the song table or the folder tree can be dropped
  // into the music (they are assigned to the adventure as well). `dropAt.index` is where the entry lands (0 = first, length = last).
  type EntryList = 'music' | 'effects';
  const ENTRY_TYPE = 'application/x-dungeontuber-block-entry';
  let dragging = $state<{ list: EntryList; from: number } | null>(null);
  let dropAt = $state<{ list: EntryList; index: number } | null>(null);

  function entryDragStart(event: DragEvent, list: EntryList, index: number) {
    dragging = { list, from: index };
    event.dataTransfer?.setData(ENTRY_TYPE, list);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  }

  function accepts(event: DragEvent, list: EntryList): boolean {
    return dragging ? dragging.list === list : list === 'music' && canDropOnBlock(event.dataTransfer);
  }

  /** Over an entry: the drop goes before it or, in its lower half, after it. */
  function entryDragOver(event: DragEvent, list: EntryList, index: number) {
    if (!canEdit() || !accepts(event, list)) return;
    event.preventDefault();
    event.stopPropagation();
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    dropAt = { list, index: event.clientY > rect.top + rect.height / 2 ? index + 1 : index };
  }

  /** Over the rest of the section (below the entries, or an empty list): the drop goes to the end. */
  function listDragOver(event: DragEvent, list: EntryList) {
    if (!canEdit() || !accepts(event, list) || !block) return;
    event.preventDefault();
    dropAt = { list, index: (list === 'music' ? block.music : block.effects).length };
  }

  async function entryDrop(event: DragEvent, list: EntryList) {
    if (!block || !accepts(event, list)) return;
    event.preventDefault();
    event.stopPropagation();
    const at = dropAt?.list === list ? dropAt.index : null;
    const moved = dragging;
    dropAt = null;
    dragging = null;
    if (at === null) return;
    if (moved) {
      const target = block;
      change(() => (list === 'music' ? moveEntry(target.music, moved.from, at) : moveEntry(target.effects, moved.from, at)));
      return;
    }
    const target = block;
    try {
      const refs = await blockSongsFromTransfer(event.dataTransfer);
      if (!refs.length) return;
      change((a) => {
        let index = at;
        for (const ref of refs) {
          addAdventureMusic(a, ref);
          if (!target.music.some((item) => refKey(item) === refKey(ref))) target.music.splice(index++, 0, ref);
        }
      });
    } catch (e) {
      errorToast(e);
    }
  }

  function dragEnd() {
    dragging = null;
    dropAt = null;
  }

  const canEdit = () => !!adventure.editable;
  const dropBefore = (list: EntryList, index: number) => dropAt?.list === list && dropAt.index === index;

  /** A click on a song or playlist of the block plays it; on the song that is playing it pauses (like the effects). */
  async function playRef(ref: MusicRef) {
    if (songPlaying(ref)) return togglePlay();
    const tracks = await refTracks(ref);
    if (tracks?.length) await playQueue(tracks);
  }

  // songs, playlists and effects of the block that can no longer be found are marked (checked again when the lists change)
  // (the song links of the notes too: checked again when the linked songs change, not on every key stroke)
  let missing = $state(new Set<string>());
  const linkedSongs = $derived([...new Set(songLinkIds(block?.markdown ?? ''))].sort().join('\n'));
  $effect(() => {
    if (!block) return;
    void [block.music.map(refKey), block.effects.map((item) => item.path)];
    const songs = linkedSongs ? linkedSongs.split('\n') : [];
    let stale = false;
    void missingEntries(untrack(() => block), songs).then((found) => { if (!stale) missing = found; });
    return () => (stale = true);
  });
  const missingSongs = $derived([...missing].filter((key) => key.startsWith('song:')).map((key) => key.slice(5)));
  let previewElement = $state<HTMLDivElement | null>(null);
  $effect(() => {
    void block?.markdown;
    if (previewElement) markMissingSongLinks(previewElement, missing, t('This song was not found in the library.'));
  });
  const missingTitle = $derived(t('No longer found: removed, moved or not visible to you.'));

  const songPlaying = (ref: MusicRef) => ref.type === 'song' && player.playing && player.track?.ufid === ref.ufid;

  let coverInput = $state<HTMLInputElement | null>(null);
  // on touch screens a tap on the cover shows its buttons (a mouse shows them on hover); another block closes them again
  let coverOpen = $state(false);
  let coverTouch = false;
  $effect(() => {
    void block?.id;
    coverOpen = false;
  });

  async function uploadCover(file: File) {
    if (!block) return;
    const target = block;
    try {
      const { name } = await api.uploadAdventureImage(adventure.id, file);
      change(() => (target.cover = name));
    } catch (e) {
      errorToast(e);
    }
  }

  async function remove() {
    if (block && (await askConfirm(t('Delete the block "{0}"?', block.title || t('Untitled'))))) deleteBlock(block.id);
  }

</script>

{#if block}
  {@const editable = adventure.editable}
  <div class="editor">
    <div class="head">
      <input class="title" type="text" placeholder={t('Block title')} value={block.title} readonly={!editable}
             oninput={(e) => change(() => (block.title = e.currentTarget.value))} />
      {#if editable}<button class="icon-btn" title={t('Delete block')} onclick={() => void remove()}><Icon name="trash" size={16} /></button>{/if}
    </div>

    <!-- the cover (its buttons lie over it: on hover with a mouse, after a tap on touch screens) and the options of the block next to it -->
    <div class="summary">
      {#if block.cover || editable}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
        <div class="cover" class:empty={!block.cover} class:open={coverOpen}
             onpointerdown={(e) => (coverTouch = e.pointerType !== 'mouse')}
             onclick={() => { if (coverTouch) coverOpen = !coverOpen; }}>
          {#if coverPending(adventure.id, block.id)}
            <span class="pending" title={t('The cover image is being painted…')}><Icon name="sparkles" size={16} /></span>
          {/if}
          {#if block.cover}
            {@const src = imageUrl(adventure.id, block.cover)}
            <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
            <img {src} alt={t('Cover image')} title={t('Double-click to enlarge')}
                 ondblclick={() => openDialog(ImagePopup, { src, title: block.title || t('Cover image') })} />
          {:else}
            <span class="placeholder" aria-hidden="true"><Icon name="mask" size={20} /></span>
          {/if}
          {#if editable}
            <div class="cover-actions">
              <button class="icon-btn mini" title={block.cover ? t('Change cover') : t('Add a cover image')} aria-label={block.cover ? t('Change cover') : t('Add a cover image')}
                      onclick={(e) => { e.stopPropagation(); coverOpen = false; coverInput?.click(); }}><Icon name="upload" size={14} /></button>
              {#if data.settings?.imageGenConfigured}
                <button class="icon-btn mini" title={t('Create with AI')} aria-label={t('Create with AI')}
                        onclick={(e) => { e.stopPropagation(); coverOpen = false; openDialog(AiDialog, { task: 'cover', blockId: block.id }); }}><Icon name="sparkles" size={14} /></button>
              {/if}
              {#if block.cover}
                <button class="icon-btn mini" title={t('Remove the cover')} aria-label={t('Remove the cover')}
                        onclick={(e) => { e.stopPropagation(); coverOpen = false; change(() => (block.cover = null)); }}><Icon name="close" size={14} /></button>
              {/if}
            </div>
            <input bind:this={coverInput} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden
                   onchange={(e) => { const file = e.currentTarget.files?.[0]; e.currentTarget.value = ''; if (file) void uploadCover(file); }} />
          {/if}
        </div>
      {/if}
      <div class="flags">
        <label class="check"><input type="checkbox" checked={block.played} onchange={(e) => setPlayed(block.id, e.currentTarget.checked)} disabled={!editable} />{t('Played')}</label>
        <label class="check"><input type="checkbox" checked={block.autoplay} disabled={!editable}
                                    onchange={(e) => change(() => (block.autoplay = e.currentTarget.checked))} />{t('Start the music when the block is entered')}</label>
      </div>
    </div>

    <section>
      <div class="bar">
        <span class="label-xs">{t('Notes')}</span>
        <span class="grow"></span>
        {#if editable}<button class="btn sm ghost" disabled={!aiText} title={aiText ? t('Draft the notes') : t('The AI assistant is not configured')}
                              onclick={() => openAi('draft')}><Icon name="sparkles" size={13} />{t('AI')}</button>{/if}
        {#if editable}<button class="btn sm ghost" title={t('Deletes the images no block uses any more')} onclick={() => void cleanUpImages()}>{t('Clean up images')}</button>{/if}
      </div>
      {#if editable}
        <!-- the editor (Tiptap) is loaded the first time notes are edited, not with the app -->
        {#await loadNotesEditor()}
          <div class="notes muted">{t('Loading…')}</div>
        {:then NotesEditor}
          {#key block.id}
            <NotesEditor value={block.markdown} adventureId={adventure.id} blocks={others} pool={adventure.music}
                         highlight={adventures.highlight?.blockId === block.id ? adventures.highlight.terms : null}
                         onhighlighted={() => (adventures.highlight = null)}
                         onchange={(markdown: string) => change(() => (block.markdown = markdown))}
                         onopenblock={(id: string) => (adventures.selected = id)} onplaysong={(ufid: string) => void playSongLink(ufid)} {missingSongs} />
          {/key}
        {/await}
      {:else}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
        <div class="notes selectable" bind:this={previewElement} onclick={previewClick}>{@html renderNotes(block.markdown, adventure.blocks, adventure.id) || `<p class="muted">${t('No notes yet.')}</p>`}</div>
      {/if}
    </section>

    <!-- music, effects and the path side by side as far as the width allows (see .panels) -->
    <div class="panels">
    <section role="list" aria-label={t('Music')} class:drop-end={dropBefore('music', block.music.length) && block.music.length > 0} class:drop-empty={dropBefore('music', 0) && !block.music.length}
             ondragover={(e) => listDragOver(e, 'music')} ondragleave={(e) => { if (e.currentTarget === e.target) dropAt = null; }}
             ondrop={(e) => void entryDrop(e, 'music')}>
      <div class="bar">
        <span class="label-xs">{t('Music')}</span>
        <span class="grow"></span>
        {#if editable}
          <button class="btn sm ghost" disabled={!musicKinds.length} title={musicKinds.length ? t('Create music') : t('The music and the sound generation are not configured yet.')}
                  aria-label={t('Create music')} onclick={() => openAi('sound', musicKinds)}><Icon name="wand" size={13} /></button>
          <button class="btn sm ghost" disabled={!aiText} title={aiText ? t('The AI chooses filters for this block and opens the library to add songs') : t('The AI assistant is not configured')}
                  onclick={() => openAi('songs')}><Icon name="sparkles" size={13} />{t('AI search')}</button>
          <button class="btn sm ghost" title={t('Search the whole library for songs for this block')} onclick={() => void searchSongsForBlock(block.id)}><Icon name="search" size={13} />{t('Search…')}</button>
          <button class="btn sm" title={t('Add songs of the adventure music')} onclick={addMusicDialog}><Icon name="plus" size={13} />{t('Add')}</button>
        {/if}
      </div>
      {#each block.music as ref, index (refKey(ref))}
        {@const on = songPlaying(ref)}
        {@const gone = missing.has(refKey(ref))}
        <div class="item" class:missing={gone} class:drop-before={dropBefore('music', index)} class:dragged={dragging?.list === 'music' && dragging.from === index}
             draggable={editable} role="listitem"
             ondragstart={(e) => entryDragStart(e, 'music', index)} ondragover={(e) => entryDragOver(e, 'music', index)}
             ondrop={(e) => void entryDrop(e, 'music')} ondragend={dragEnd}>
          {#if editable}<span class="grip" title={t('Drag to change the order')}><Icon name="menu" size={13} /></span>{/if}
          <button type="button" class="play-item" class:on disabled={gone} title={gone ? missingTitle : t(on ? 'Pause' : 'Play')} onclick={() => void playRef(ref)}>
            <Icon name={on ? 'volume' : ref.type === 'song' ? 'music' : 'playlist'} size={15} />
            <span class="ellipsis">{ref.title || ref.path || t('Untitled')}</span>
          </button>
          {#if index === 0 && block.autoplay}<span class="start" title={t('Starts when the block is entered')}><Icon name="play" size={10} />{t('Start')}</span>{/if}
          {#if gone}<span class="warn" title={missingTitle}>{ref.type === 'playlist' && ref.unavailable ? t('unavailable') : t('not found')}</span>{/if}
          {#if editable}<button class="icon-btn mini" title={t('Remove')} onclick={() => change(() => block.music.splice(index, 1))}><Icon name="close" size={13} /></button>{/if}
        </div>
      {:else}
        <span class="muted small">{t('No music: the current music keeps playing.')}</span>
      {/each}
    </section>

    <section role="list" aria-label={t('Effects')} class:drop-end={dropBefore('effects', block.effects.length) && block.effects.length > 0}
             ondragover={(e) => listDragOver(e, 'effects')} ondragleave={(e) => { if (e.currentTarget === e.target) dropAt = null; }}
             ondrop={(e) => void entryDrop(e, 'effects')}>
      <div class="bar">
        <span class="label-xs">{t('Effects')}</span>
        <span class="grow"></span>
        {#if editable}
          <button class="btn sm ghost" disabled={!aiSounds} title={aiSounds ? t('Create an ambience or a sound effect') : t('The sound generation is not configured')}
                  onclick={() => openAi('sound', ['ambience', 'sfx'])}><Icon name="sparkles" size={13} />{t('AI')}</button>
          <button class="btn sm" onclick={addEffectDialog}><Icon name="plus" size={13} />{t('Add')}</button>
        {/if}
      </div>
      {#each block.effects as effect, index (effect.path)}
        {@const on = player.effectPlaying && player.effect?.path === effect.path}
        {@const gone = missing.has(effectKey(effect))}
        <div class="item" class:missing={gone} class:drop-before={dropBefore('effects', index)} class:dragged={dragging?.list === 'effects' && dragging.from === index}
             draggable={editable} role="listitem"
             ondragstart={(e) => entryDragStart(e, 'effects', index)} ondragover={(e) => entryDragOver(e, 'effects', index)}
             ondrop={(e) => void entryDrop(e, 'effects')} ondragend={dragEnd}>
          {#if editable}<span class="grip" title={t('Drag to change the order')}><Icon name="menu" size={13} /></span>{/if}
          <button type="button" class="play-item" class:on disabled={gone} title={gone ? missingTitle : t(on ? 'Pause' : 'Play')} onclick={() => void startEffect(effect)}>
            <Icon name={on ? 'volume' : 'waves'} size={15} />
            <span class="ellipsis">{effect.name || effect.path}</span>
          </button>
          {#if gone}<span class="warn" title={missingTitle}>{t('not found')}</span>{/if}
          <label class="check small" title={t('Loop')}><input type="checkbox" checked={effect.loop} disabled={!editable} onchange={(e) => change(() => (effect.loop = e.currentTarget.checked))} /><span class="text">{t('Loop')}</span><span class="ic"><Icon name="repeat" size={14} /></span></label>
          <label class="check small" title={t('Auto')}><input type="checkbox" checked={effect.autostart} disabled={!editable} onchange={(e) => change(() => (effect.autostart = e.currentTarget.checked))} /><span class="text">{t('Auto')}</span><span class="ic"><Icon name="play" size={14} /></span></label>
          {#if editable}<button class="icon-btn mini" title={t('Remove')} onclick={() => change(() => block.effects.splice(index, 1))}><Icon name="close" size={13} /></button>{/if}
        </div>
      {:else}
        <span class="muted small">{t('Ambient loops or one-shot effects of the effects folder.')}</span>
      {/each}
    </section>

    <section>
      <div class="bar"><span class="label-xs">{t('Path')}</span></div>
      {#each outgoing as link (link)}
        <div class="item">
          <Icon name="forward" size={15} />
          <span class="ellipsis target">{titleOf(link.to)}</span>
          <input type="text" class="label" placeholder={t('Label (a choice, e.g. "enter the crypt")')} value={link.label ?? ''} readonly={!editable}
                 oninput={(e) => change(() => (link.label = e.currentTarget.value.trim() || null))} />
          {#if editable}<button class="icon-btn mini" title={t('Remove')} onclick={() => change((a) => removeLink(a, link))}><Icon name="close" size={13} /></button>{/if}
        </div>
      {:else}
        <span class="muted small">{t('Leads nowhere yet. Without a label a link is the default next block, with a label it is a choice.')}</span>
      {/each}
      {#if editable && others.length}
        <div class="item">
          <select bind:value={linkTarget} aria-label={t('Next block')}>
            <option value="">{t('Link to…')}</option>
            {#each others as other (other.id)}<option value={other.id}>{other.title || t('Untitled')}</option>{/each}
          </select>
          <button class="btn sm add-link" disabled={!linkTarget} title={t('Add link')} aria-label={t('Add link')} onclick={newLink}><span class="ic"><Icon name="plus" size={14} /></span><span class="text">{t('Add link')}</span></button>
        </div>
      {/if}
      {#if incoming.length}
        <span class="muted small">{t('Reached from')}: {incoming.map((link) => titleOf(link.from)).join(', ')}</span>
      {/if}
    </section>
    </div>
  </div>
{/if}

<style>
  .editor { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .head { display: flex; align-items: center; gap: 8px; }
  .title { flex: 1; min-width: 0; font-size: var(--fs-lg, 1.15em); font-weight: 650; }
  .summary { display: flex; align-items: center; gap: 16px; min-width: 0; }
  /* a small thumbnail in the image's own aspect ratio (landscape, portrait or square); its buttons lie over it */
  .cover { position: relative; flex: none; display: grid; place-items: center; min-width: 96px; min-height: 60px; }
  .cover img { display: block; width: auto; height: auto; max-width: 160px; max-height: 110px; border-radius: 8px; border: 1px solid var(--border); cursor: zoom-in; }
  .placeholder { display: grid; place-items: center; width: 96px; height: 60px; border-radius: 8px; border: 1px dashed var(--border-strong, var(--border)); color: var(--faint); }
  .cover-actions { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; flex-wrap: wrap; align-content: center; gap: 4px;
                   border-radius: 8px; background: rgba(0, 0, 0, 0.45); opacity: 0; pointer-events: none; transition: opacity 0.15s; }
  .cover-actions .mini { width: 26px; height: 26px; color: white; background: rgba(0, 0, 0, 0.35); }
  .cover-actions .mini:hover { background: var(--accent); }
  .cover.open .cover-actions, .cover:focus-within .cover-actions { opacity: 1; pointer-events: auto; }
  @media (hover: hover) { .cover:hover .cover-actions { opacity: 1; pointer-events: auto; } }
  /* without a picture there is nothing to cover: the buttons stay visible on the placeholder */
  .cover.empty .cover-actions { opacity: 1; pointer-events: auto; background: none; }
  .cover.empty .cover-actions .mini { color: var(--muted); background: var(--surface); }
  .cover.empty .cover-actions .mini:hover { color: white; background: var(--accent); }
  .cover.empty .placeholder :global(svg) { visibility: hidden; }
  .pending { position: absolute; top: 4px; right: 4px; z-index: 1; display: grid; place-items: center; width: 24px; height: 24px; border-radius: 50%;
             background: var(--accent); color: white; box-shadow: var(--shadow); pointer-events: none; animation: pending-pulse 1.4s ease-in-out infinite; }
  @keyframes pending-pulse { 50% { transform: scale(1.15); opacity: 0.7; } }
  .flags { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
  .check { display: inline-flex; align-items: center; gap: 7px; font-size: var(--fs-sm); color: var(--muted); }
  .check.small { font-size: var(--fs-xs); }
  /* the options of an effect: words, on phones icons (the words are their tooltips) */
  .check .ic { display: none; }
  .add-link .ic { display: none; }
  @media (max-width: 900px) {
    .check.small { gap: 3px; }
    .check.small .text { display: none; }
    .check.small .ic { display: flex; }
    .add-link .text { display: none; }
    .add-link .ic { display: flex; }
  }
  section { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); }
  /* three in a row when they fit, else two with the third across the whole width, else one below the other */
  .panels { display: flex; flex-wrap: wrap; gap: 16px; }
  .panels > section { flex: 1 1 320px; min-width: 0; box-sizing: border-box; }
  .bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .grow { flex: 1; }
  .notes { line-height: 1.6; overflow-wrap: anywhere; }
  .notes :global(img) { max-width: 100%; border-radius: 8px; }
  .notes :global(h1), .notes :global(h2), .notes :global(h3) { margin: 0.6em 0 0.3em; }
  .notes :global(blockquote) { margin: 0.6em 0; padding-left: 12px; border-left: 3px solid var(--accent); color: var(--muted); }
  .item { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .item .target { flex: none; max-width: 40%; font-weight: 550; }
  .item .label { flex: 1; min-width: 0; }
  .item > .ellipsis { flex: 1; min-width: 0; }
  .grip { flex: none; display: flex; color: var(--faint); cursor: grab; margin-right: -4px; }
  .item:hover .grip { color: var(--muted); }
  .item.dragged { opacity: 0.4; }
  .item.drop-before { box-shadow: 0 -2px 0 var(--accent); }
  section.drop-end > .item:last-of-type { box-shadow: 0 2px 0 var(--accent); }
  section.drop-empty { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .start { flex: none; display: inline-flex; align-items: center; gap: 3px; padding: 1px 7px; border-radius: 999px; font-size: var(--fs-xs); font-weight: 600;
           background: var(--accent-soft); color: var(--accent); }
  .play-item { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; margin: -3px 0; padding: 3px 6px; border-radius: 7px; text-align: left; color: var(--text); cursor: pointer; }
  .play-item:hover:not(:disabled) { background: var(--hover); }
  .play-item.on { color: var(--accent); }
  .play-item:disabled { cursor: default; opacity: 0.6; }
  .mini { width: 24px; height: 24px; }
  .small { font-size: var(--fs-sm); }
  .item.missing .play-item { color: var(--red); text-decoration: line-through; cursor: not-allowed; }
  .warn { flex: none; font-size: var(--fs-xs); color: var(--red); border: 1px solid var(--red); border-radius: 6px; padding: 0 6px; }
</style>
