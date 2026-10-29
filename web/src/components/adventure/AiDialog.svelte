<script lang="ts">
  import { api } from '../../lib/api';
  import { onMount } from 'svelte';
  import { blockPrompt, plainText, tagsAndGenres, tldrPrompt } from '../../lib/adventureAi';
  import { t } from '../../lib/i18n.svelte';
  import { imageUrl, inertLinkClick, renderNotes } from '../../lib/notes';
  import { adventures, applyCoverWhenReady, change, createForBlock, searchSongsWithFilter, type BlockCreation } from '../../lib/stores/adventure.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { composeOptions, describeSoundYourself, describeYourself, effectOptions, type CreateKind } from '../../lib/stores/assistant.svelte';
  import { globalTab, loadGlobal } from '../../lib/stores/library.svelte';
  import { playQueue } from '../../lib/stores/player.svelte';
  import { closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { AssistantReply, ComposePiece, SoundDescription, Track } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import CreateOptions from '../CreateOptions.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** The AI helpers of a block: `draft` writes its notes, `songs` chooses filters for it and opens the library to add songs (like
   *  "Search…" of its music), `sound` creates what
   *  `kinds` allows (a piece of the music generation, background music, an ambience or an effect) with the options of the create mode
   *  of the assistant (CreateOptions.svelte), `cover` paints its cover with the image generation, `tldr` sums the whole notes up in
   *  keywords (the short summary of the block; it is written as soon as the dialog opens). */
  let { task, blockId, kinds = ['ambience', 'sfx'] }: { task: 'draft' | 'songs' | 'sound' | 'cover' | 'tldr'; blockId: string; kinds?: CreateKind[] } = $props();

  const adventure = $derived(adventures.current!);
  const block = $derived(adventure.blocks.find((item) => item.id === blockId) ?? null);

  // svelte-ignore state_referenced_locally
  let input = $state(task === 'draft' || task === 'tldr' ? '' : block ? blockPrompt(block) : '');
  let refine = $state('');
  let busy = $state(false);
  let message = $state('');
  let history: { role: 'user' | 'assistant'; content: string }[] = [];

  let draft = $state('');
  /** The notes go to the AI as they are (Markdown, not shortened) instead of a shortened plain text. */
  let wholeText = $state(false);
  const MAX_WHOLE_TEXT = 6000;
  // svelte-ignore state_referenced_locally
  let kind = $state<CreateKind>(kinds.includes(effectOptions.kind) ? effectOptions.kind : kinds[0]);
  // the description of a piece (kind song) or of a sound, as the assistant wrote it; it can be changed before generating
  let piece = $state<ComposePiece | null>(null);
  let sound = $state<SoundDescription | null>(null);
  /** Another kind: a description is made for its kind, the one of the former kind goes. */
  function setKind(value: CreateKind) {
    if (value !== kind) piece = sound = null;
    kind = value;
  }
  let made = $state<Track | null>(null);
  // cover: the English description Stable Diffusion paints from, the format and the painted image (its name in the adventure)
  let caption = $state('');
  let size = $state<'landscape' | 'square' | 'portrait'>('landscape');
  let painted = $state<string | null>(null);
  let painting = $state(false);
  const sizes = [['landscape', 'Landscape'], ['square', 'Square'], ['portrait', 'Portrait']] as const;

  const titles = $derived({
    draft: 'Draft the notes', tldr: 'Summarize the notes', songs: 'AI search', sound: kinds.includes('song') || kinds.includes('music') ? 'Create music' : 'Create a sound', cover: 'Create a cover image',
  });

  /** Asks the assistant; a follow-up (refine) continues the conversation, so "darker" changes the last answer. */
  async function ask(text: string, mode: 'story' | 'tldr' | 'smart' | 'compose' | 'effects' | 'image', context: Parameters<typeof api.assistantChat>[2]): Promise<AssistantReply | null> {
    history.push({ role: 'user', content: text });
    busy = true;
    try {
      const reply = await api.assistantChat(history, mode, context);
      history.push({ role: 'assistant', content: reply.content });
      message = reply.message;
      return reply;
    } catch (e) {
      history.pop();
      errorToast(e);
      return null;
    } finally {
      busy = false;
    }
  }

  const request = (text: string) => text.trim();

  async function run(followUp = false) {
    if (!block) return;
    const text = request(followUp ? refine : input);
    if (!text && task !== 'tldr') return;
    if (followUp && !text) return;
    if (!followUp) history = [];
    if (task === 'tldr') {
      // the wishes are optional: the summary is written from the notes alone
      const reply = await ask(followUp ? text : tldrPrompt(adventure.title, block, text), 'tldr', undefined);
      if (reply?.text) draft = reply.text;
    } else if (task === 'draft') {
      const notes = wholeText ? block.markdown.trim().slice(0, MAX_WHOLE_TEXT) : plainText(block.markdown);
      const context = followUp ? text : `Adventure: ${adventure.title}\nScene: ${block.title}\nNotes so far${wholeText ? ' (Markdown)' : ''}:\n${notes || '(none)'}\n\n${text}`;
      const reply = await ask(context, 'story', undefined);
      if (reply?.text) draft = reply.text;
    } else if (task === 'songs') {
      await loadGlobal();
      const reply = await ask(text, 'smart', tagsAndGenres(globalTab.tracks));
      if (reply?.filter) {
        void searchSongsWithFilter(block.id, reply.filter);
        closeDialog();
        return;
      }
    } else if (task === 'cover') {
      const reply = await ask(followUp ? text : `Adventure: ${adventure.title}\n\n${text}`, 'image', undefined);
      if (reply?.caption) caption = reply.caption;
    } else if (kind === 'song') {
      const context = { instrumental: composeOptions.instrumental, duration: composeOptions.duration,
                        ...(composeOptions.instrumental || !composeOptions.language ? {} : { language: composeOptions.language }) };
      const reply = aiReady ? await ask(text, 'compose', context) : describeYourself(text);
      if (reply?.piece) piece = reply.piece;
    } else {
      const reply = aiReady ? await ask(text, 'effects', { kind }) : describeSoundYourself(text, kind);
      if (reply?.sound) sound = reply.sound;
    }
    if (followUp) refine = '';
  }

  // --- what a result does to the block ---

  function useSummary() {
    if (!block || !draft.trim()) return;
    change(() => (block.tldr = draft.trim()));
    closeDialog();
  }

  // the summary needs nothing but the notes: it is written right away
  onMount(() => {
    if (task === 'tldr' && aiReady && block?.markdown.trim()) void run();
  });

  function useDraft(append: boolean) {
    if (!block || !draft.trim()) return;
    change(() => (block.markdown = append && block.markdown.trim() ? `${block.markdown.trimEnd()}\n\n${draft.trim()}` : draft.trim()));
    closeDialog();
  }

  /** The piece or sound being generated; it is added to the block when it is done, also after "Apply" closed the dialog. */
  let generating: Promise<Track> | null = $state(null);

  async function generate() {
    if (!block || !(kind === 'song' ? piece : sound)) return;
    const dir = kind === 'song' ? composeOptions.dir : effectOptions.dir;
    if (!dir) {
      errorToast(new Error(kind === 'song' ? t('Choose a folder for the composed pieces first.') : t('Choose a folder for the sounds first.')));
      return;
    }
    busy = true;
    made = null;
    const creation: BlockCreation = kind === 'song'
      ? { kind, piece: $state.snapshot(piece)!, dir, duration: composeOptions.duration }
      : { kind, sound: $state.snapshot(sound)!, dir, duration: effectOptions.duration };
    const job = (generating = createForBlock(adventure.id, block.id, creation));
    try {
      made = await job;
    } catch (e) {
      errorToast(e);
    } finally {
      if (generating === job) generating = null;
      busy = false;
    }
  }

  /** "Apply" while a sound is generated: the dialog closes, the generation goes on and adds the sound to the block when it is done. */
  function applySound() {
    if (!generating) return;
    toast(t('The sound is generated in the background and added to the block when it is done.'), 'info');
    closeDialog();
  }

  /** Paints the picture to look at; it is stored in the adventure right away and becomes the cover with "Apply". */
  let running: Promise<{ name: string }> | null = null;

  async function paint() {
    const prompt = (aiReady ? caption : input).trim();
    if (!block || !prompt) return;
    busy = painting = true;
    const job = (running = api.generateAdventureImage(adventure.id, prompt, size));
    try {
      painted = (await job).name;
    } catch (e) {
      errorToast(e);
    } finally {
      if (running === job) running = null;
      busy = painting = false;
    }
  }

  /** "Apply": a finished picture becomes the cover at once; otherwise the dialog closes and the picture (the one being painted, or a
   *  new one, after the assistant described it if that is still to do) becomes the cover in the background once it is done. */
  function apply() {
    if (!block) return;
    if (painted && !painting) {
      const name = painted;
      change(() => (block.cover = name));
      closeDialog();
      return;
    }
    const [adventureId, scene, chosenSize] = [adventure.id, input.trim(), size];
    const describe = async () => {
      const reply = await api.assistantChat([{ role: 'user', content: `Adventure: ${adventure.title}\n\n${scene}` }], 'image');
      return reply.caption?.trim() || scene;
    };
    const prompt = (aiReady ? caption : input).trim();
    const job = running ?? (prompt ? api.generateAdventureImage(adventureId, prompt, chosenSize)
      : aiReady && scene ? describe().then((text) => api.generateAdventureImage(adventureId, text, chosenSize)) : null);
    if (!job) return;
    void applyCoverWhenReady(adventureId, block.id, job);
    toast(t('The cover image is painted in the background.'), 'info');
    closeDialog();
  }


  const aiReady = $derived(!!(data.settings?.groqConfigured || data.settings?.assistantConfigured));
  const canApply = $derived(!!painted || painting || !!(aiReady ? caption.trim() || input.trim() : input.trim()));
</script>

<Modal title={t(titles[task])} onclose={closeDialog} width="640px">
  {#if !aiReady && task !== 'sound' && task !== 'cover'}
    <p class="muted">{t('The AI assistant is not configured')}</p>
  {:else if !block}
    <p class="muted">{t('This block does not exist any more.')}</p>
  {:else}
    <div class="body">
      {#if task === 'sound'}
        <div class="options"><CreateOptions {kinds} bind:kind={() => kind, setKind} /></div>
      {/if}
      {#if task === 'cover'}
        <div class="seg">
          {#each sizes as [key, label] (key)}
            <button type="button" class:on={size === key} onclick={() => (size = key)}>{t(label)}</button>
          {/each}
        </div>
      {/if}

      {#if task === 'tldr'}
        {#if !block.markdown.trim()}<p class="muted">{t('This block has no notes to summarize yet.')}</p>{/if}
        <label class="field">
          <span class="label-xs">{t('Wishes (optional)')}</span>
          <textarea rows="2" bind:value={input} placeholder={t('e.g. only the checks and the dangers')}></textarea>
        </label>
      {:else}
      <label class="field">
        <span class="label-xs">{task === 'draft' ? t('What should the notes say? (bullet points are fine)') : task === 'cover' && !aiReady ? t('Describe the picture (in English)') : t('Describe the scene')}</span>
        <textarea rows={task === 'draft' ? 4 : 5} bind:value={input} placeholder={task === 'draft' ? t('A smoky tavern, the innkeeper hides a secret…') : ''}></textarea>
      </label>
      {/if}
      {#if task === 'draft'}
        <label class="check" title={t('Without it the AI gets a shortened plain text of the notes (about 1500 characters).')}>
          <input type="checkbox" bind:checked={wholeText} disabled={!block.markdown.trim()} />{t('Include the whole text of this block')}
        </label>
      {/if}
      <div class="row">
        {#if task === 'cover' && !aiReady}
          <button class="btn primary" disabled={busy || !input.trim()} onclick={() => void paint()}><Icon name="sparkles" size={14} />{t('Generate')}</button>
        {:else if task === 'tldr'}
          <button class="btn primary" disabled={busy || !block.markdown.trim()} onclick={() => void run()}><Icon name="sparkles" size={14} />{draft ? t('Summarize again') : t('Summarize')}</button>
        {:else}
          <button class="btn primary" disabled={busy || !input.trim()} onclick={() => void run()}><Icon name="sparkles" size={14} />{task === 'sound' ? (kind === 'song' ? t('Describe the piece') : t('Describe the sound')) : task === 'cover' ? t('Describe the picture') : task === 'songs' ? t('Find songs in the library') : t('Ask')}</button>
        {/if}
        {#if busy}<span class="muted small">{(task === 'sound' && (sound || piece)) || painting ? t('Generating… this can take a few minutes.') : t('Thinking…')}</span>{/if}
      </div>
      {#if message}<p class="message">{message}</p>{/if}

      {#if task === 'tldr' && draft}
        <!-- as it will look in the block; it can be changed there afterwards -->
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
        <div class="tldr-preview" onclick={inertLinkClick}>{@html renderNotes(draft, adventure.blocks, adventure.id)}</div>
      {:else if task === 'draft' && draft}
        <textarea class="result" rows="10" bind:value={draft}></textarea>
      {:else if task === 'sound' && (piece || sound)}
        {@const description = (piece ?? sound)!}
        <div class="sound">
          <input type="text" bind:value={description.title} aria-label={t('Title')} />
          <textarea rows="3" bind:value={description.caption} aria-label={t('Description')}></textarea>
          {#if piece && !piece.instrumental}<textarea rows="6" bind:value={piece.lyrics} aria-label={t('Lyrics')}></textarea>{/if}
          <div class="row">
            <button class="btn primary" disabled={busy || !description.caption.trim()} onclick={() => void generate()}><Icon name="waves" size={14} />{t('Generate')}</button>
            {#if made}<button class="btn" onclick={() => void playQueue([made!])}><Icon name="play" size={14} />{t('Play')}</button>{/if}
          </div>
        </div>
      {/if}
      {#if task === 'cover' && aiReady && caption}
        <div class="sound">
          <textarea rows="4" bind:value={caption} aria-label={t('Description')}></textarea>
          <div class="row">
            <button class="btn primary" disabled={busy || !caption.trim()} onclick={() => void paint()}><Icon name="sparkles" size={14} />{painted ? t('Generate again') : t('Generate')}</button>
          </div>
        </div>
      {/if}
      {#if task === 'cover' && painted}
        <img class="painted" src={imageUrl(adventure.id, painted)} alt={t('Cover image')} />
      {/if}

      {#if ((task === 'draft' || task === 'tldr') && draft) || (task === 'cover' && caption)}
        <div class="row">
          <input type="text" bind:value={refine} placeholder={t('Change it: darker, shorter, more tense…')} onkeydown={(e) => e.key === 'Enter' && !busy && void run(true)} />
          <button class="btn" disabled={busy || !refine.trim()} onclick={() => void run(true)}>{t('Change')}</button>
        </div>
      {/if}
    </div>
  {/if}
  {#snippet footer()}
    {#if task === 'tldr'}
      <button class="btn" onclick={closeDialog}>{t('Close')}</button>
      <button class="btn primary" disabled={!draft.trim() || busy} onclick={useSummary}>{t('Replace the summary')}</button>
    {:else if task === 'draft' && draft}
      <button class="btn" onclick={() => useDraft(true)}>{t('Append to notes')}</button>
      <button class="btn primary" onclick={() => useDraft(false)}>{t('Replace notes')}</button>
    {:else if task === 'cover'}
      <button class="btn" onclick={closeDialog}>{t('Close')}</button>
      <button class="btn primary" disabled={!canApply || (busy && !painting)}
              title={painted && !painting ? t('Use this picture as the cover') : t('Closes the dialog: the picture becomes the cover as soon as it is painted')}
              onclick={apply}>{t('Apply')}</button>
    {:else if task === 'sound'}
      <button class="btn" onclick={closeDialog}>{t('Close')}</button>
      <button class="btn primary" disabled={!generating} title={t('Closes the dialog: the sound is added to the block as soon as it is generated')}
              onclick={applySound}>{t('Apply')}</button>
    {:else}
      <button class="btn" onclick={closeDialog}>{t('Close')}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .body { display: flex; flex-direction: column; gap: 12px; }
  .field { display: flex; flex-direction: column; gap: 6px; }
  .check { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); }
  .options { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; font-size: var(--fs-xs); }
  textarea { width: 100%; box-sizing: border-box; resize: vertical; }
  .row { display: flex; align-items: center; gap: 8px; }
  .row input { flex: 1; min-width: 0; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .message { margin: 0; color: var(--muted); font-size: var(--fs-sm); }
  .small { font-size: var(--fs-xs); }
  .result { min-height: 180px; line-height: 1.5; }
  .tldr-preview { padding: 10px 14px; border-radius: 10px; background: var(--accent-soft); border: 1px solid var(--border); line-height: 1.5; overflow-wrap: anywhere; }
  .tldr-preview :global(ul) { margin: 0; padding-left: 1.2em; }
  .tldr-preview :global(p) { margin: 0 0 0.4em; }
  .sound { display: flex; flex-direction: column; gap: 8px; }
  .seg button { padding: 5px 13px; }
  .painted { display: block; max-width: 100%; max-height: 340px; margin: 0 auto; border-radius: 10px; object-fit: contain; }
</style>
