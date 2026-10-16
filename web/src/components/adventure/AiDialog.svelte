<script lang="ts">
  import { api } from '../../lib/api';
  import { addMusic } from '../../lib/adventures';
  import { blockPrompt, plainText, rankTracks, tagsAndGenres, type Ranked } from '../../lib/adventureAi';
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { scorePercent } from '../../lib/scoring';
  import { adventures, change } from '../../lib/stores/adventure.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { effects, loadEffects } from '../../lib/stores/effects.svelte';
  import { globalTab, loadGlobal } from '../../lib/stores/library.svelte';
  import { lights } from '../../lib/stores/lights.svelte';
  import { cueLight, playQueue } from '../../lib/stores/player.svelte';
  import { closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { AssistantReply, LightSetting, SoundDescription, SoundKind, Track } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** The AI helpers of a block: `draft` writes its notes, `songs` ranks the songs of the library for it, `light` chooses a light, `sound` creates an
   *  ambience, an effect or background music with the sound generation. */
  let { task, blockId }: { task: 'draft' | 'songs' | 'light' | 'sound'; blockId: string } = $props();

  const adventure = $derived(adventures.current!);
  const block = $derived(adventure.blocks.find((item) => item.id === blockId) ?? null);

  // svelte-ignore state_referenced_locally
  let input = $state(task === 'draft' ? '' : block ? blockPrompt(block) : '');
  let refine = $state('');
  let busy = $state(false);
  let message = $state('');
  let history: { role: 'user' | 'assistant'; content: string }[] = [];

  let draft = $state('');
  let ranked = $state<Ranked[]>([]);
  let light = $state<LightSetting | null>(null);
  let kind = $state<SoundKind>('ambience');
  let sound = $state<SoundDescription | null>(null);
  let made = $state<Track | null>(null);

  const titles = {
    draft: 'Draft the notes', songs: 'Suggest songs', light: 'Suggest a light', sound: 'Create a sound',
  };

  /** Asks the assistant; a follow-up (refine) continues the conversation, so "darker" changes the last answer. */
  async function ask(text: string, mode: 'story' | 'smart' | 'effects', context: Parameters<typeof api.assistantChat>[2]): Promise<AssistantReply | null> {
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
    if (!text) return;
    if (!followUp) history = [];
    if (task === 'draft') {
      const context = followUp ? text : `Adventure: ${adventure.title}\nScene: ${block.title}\nNotes so far:\n${plainText(block.markdown) || '(none)'}\n\n${text}`;
      const reply = await ask(context, 'story', { task: 'draft' });
      if (reply?.text) draft = reply.text;
    } else if (task === 'light') {
      const reply = await ask(text, 'story', { task: 'light', scenes: lights.scenes.filter((scene) => !/^Custom Mode/i.test(scene)) });
      if (reply) {
        light = reply.light ?? null;
        if (!light) message = t('No usable light was suggested. Try describing the mood.');
      }
    } else if (task === 'songs') {
      await loadGlobal();
      const reply = await ask(text, 'smart', tagsAndGenres(globalTab.tracks));
      if (reply?.filter) {
        ranked = rankTracks(globalTab.tracks, reply.filter);
        if (!ranked.length) message = t('No songs of the library fit. Try another description.');
      }
    } else {
      const reply = await ask(text, 'effects', { kind });
      if (reply?.sound) sound = reply.sound;
    }
    if (followUp) refine = '';
  }

  // --- what a result does to the block ---

  function useDraft(append: boolean) {
    if (!block || !draft.trim()) return;
    change(() => (block.markdown = append && block.markdown.trim() ? `${block.markdown.trimEnd()}\n\n${draft.trim()}` : draft.trim()));
    closeDialog();
  }

  function useLight() {
    if (!block || !light) return;
    const chosen = { ...light };
    change(() => (block.light = chosen));
    closeDialog();
  }

  function addSong(track: Track) {
    if (!block || !track.ufid) return;
    const ufid = track.ufid;
    change(() => addMusic(block, { type: 'song', ufid, path: track.path, title: track.title || track.name }));
    toast(t('Added: {0}', track.title || track.name));
  }

  const has = (track: Track) => !!block?.music.some((ref) => ref.type === 'song' && ref.ufid === track.ufid);

  async function generate() {
    if (!block || !sound) return;
    const dir = kind === 'music' ? (prefs.treeRoot ?? data.settings?.libraryRoots[0]) : effects.directory;
    if (!dir) {
      errorToast(new Error(kind === 'music' ? t('Choose a library folder first.') : t('Choose a folder for the sounds first.')));
      return;
    }
    busy = true;
    made = null;
    try {
      const result = await api.sound({ ...sound, kind, dir });
      made = result.track;
      const track = result.track;
      if (kind === 'music') {
        if (track.ufid) {
          const ufid = track.ufid;
          change(() => addMusic(block, { type: 'song', ufid, path: track.path, title: sound!.title || track.name }));
        }
      } else {
        await loadEffects();
        change(() => block.effects.push({ path: track.path, name: sound!.title || track.name, loop: kind === 'ambience', autostart: false }));
      }
      toast(t('Created and added to the block.'), 'success');
    } catch (e) {
      errorToast(e);
    } finally {
      busy = false;
    }
  }

  const aiReady = $derived(!!(data.settings?.groqConfigured || data.settings?.assistantConfigured));
  const lightLabel = (value: LightSetting) => value.scene ? value.scene : value.color ? value.color : value.temperature ? `${value.temperature} K` : '';
</script>

<Modal title={t(titles[task])} onclose={closeDialog} width="640px">
  {#if !aiReady && task !== 'sound'}
    <p class="muted">{t('The AI assistant is not configured')}</p>
  {:else if !block}
    <p class="muted">{t('This block does not exist any more.')}</p>
  {:else}
    <div class="body">
      {#if task === 'sound'}
        <div class="seg">
          {#each [['ambience', t('Ambience')], ['sfx', t('Effect')], ['music', t('Music')]] as [key, label] (key)}
            <button type="button" class:on={kind === key} onclick={() => { kind = key as SoundKind; sound = null; }}>{label}</button>
          {/each}
        </div>
      {/if}

      <label class="field">
        <span class="label-xs">{task === 'draft' ? t('What should the notes say? (bullet points are fine)') : t('Describe the scene')}</span>
        <textarea rows={task === 'draft' ? 4 : 5} bind:value={input} placeholder={task === 'draft' ? t('A smoky tavern, the innkeeper hides a secret…') : ''}></textarea>
      </label>
      <div class="row">
        <button class="btn primary" disabled={busy || !input.trim()} onclick={() => void run()}><Icon name="sparkles" size={14} />{task === 'sound' ? t('Describe the sound') : t('Ask')}</button>
        {#if busy}<span class="muted small">{task === 'sound' && sound ? t('Generating… this can take a few minutes.') : t('Thinking…')}</span>{/if}
      </div>
      {#if message}<p class="message">{message}</p>{/if}

      {#if task === 'draft' && draft}
        <textarea class="result" rows="10" bind:value={draft}></textarea>
      {:else if task === 'light' && light}
        <div class="light">
          <span class="swatch" style:background={light.color ?? (light.temperature ? `hsl(35 90% ${Math.max(40, 100 - (light.temperature - 2200) / 60)}%)` : 'var(--accent)')}></span>
          <span>{lightLabel(light)} · {Math.round(((light.brightness ?? 255) / 255) * 100)}%</span>
          <span class="grow"></span>
          <button class="btn sm" onclick={() => cueLight(light)}>{t('Preview')}</button>
        </div>
      {:else if task === 'songs' && ranked.length}
        <div class="songs">
          {#each ranked as item (item.track.id)}
            <div class="song">
              <button class="icon-btn mini" title={t('Play')} aria-label={t('Play')} onclick={() => void playQueue([item.track])}><Icon name="play" size={13} /></button>
              <span class="ellipsis">{item.track.title || item.track.name}</span>
              <span class="muted ellipsis artist">{item.track.artist ?? ''}</span>
              <span class="muted small">{scorePercent(item.score)}%</span>
              {#if has(item.track)}<Icon name="check" size={14} />
              {:else}<button class="btn sm" disabled={!item.track.ufid} title={item.track.ufid ? '' : t('This song has no stable id yet. Refresh the library first.')} onclick={() => addSong(item.track)}>{t('Add')}</button>{/if}
            </div>
          {/each}
        </div>
      {:else if task === 'sound' && sound}
        <div class="sound">
          <input type="text" bind:value={sound.title} aria-label={t('Title')} />
          <textarea rows="3" bind:value={sound.caption} aria-label={t('Description')}></textarea>
          <div class="row">
            <button class="btn primary" disabled={busy || !sound.caption.trim()} onclick={() => void generate()}><Icon name="waves" size={14} />{t('Generate')}</button>
            {#if made}<button class="btn" onclick={() => void playQueue([made!])}><Icon name="play" size={14} />{t('Play')}</button>{/if}
          </div>
        </div>
      {/if}

      {#if (task === 'draft' && draft) || (task === 'light' && light) || (task === 'songs' && ranked.length)}
        <div class="row">
          <input type="text" bind:value={refine} placeholder={t('Change it: darker, shorter, more tense…')} onkeydown={(e) => e.key === 'Enter' && void run(true)} />
          <button class="btn" disabled={busy || !refine.trim()} onclick={() => void run(true)}>{t('Change')}</button>
        </div>
      {/if}
    </div>
  {/if}
  {#snippet footer()}
    {#if task === 'draft' && draft}
      <button class="btn" onclick={() => useDraft(true)}>{t('Append to notes')}</button>
      <button class="btn primary" onclick={() => useDraft(false)}>{t('Replace notes')}</button>
    {:else if task === 'light' && light}
      <button class="btn primary" onclick={useLight}>{t('Use for this block')}</button>
    {:else}
      <button class="btn" onclick={closeDialog}>{t('Close')}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .body { display: flex; flex-direction: column; gap: 12px; }
  .field { display: flex; flex-direction: column; gap: 6px; }
  textarea { width: 100%; box-sizing: border-box; resize: vertical; }
  .row { display: flex; align-items: center; gap: 8px; }
  .row input { flex: 1; min-width: 0; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .message { margin: 0; color: var(--muted); font-size: var(--fs-sm); }
  .small { font-size: var(--fs-xs); }
  .grow { flex: 1; }
  .result { min-height: 180px; line-height: 1.5; }
  .light { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); }
  .swatch { width: 28px; height: 28px; border-radius: 8px; border: 1px solid var(--border-strong, var(--border)); flex: none; }
  .songs { display: flex; flex-direction: column; gap: 2px; max-height: 320px; overflow-y: auto; }
  .song { display: flex; align-items: center; gap: 8px; padding: 4px 6px; border-radius: 8px; }
  .song:hover { background: var(--hover); }
  .song .ellipsis { min-width: 0; flex: 1; }
  .artist { flex: 0 1 30%; font-size: var(--fs-sm); }
  .mini { width: 24px; height: 24px; }
  .sound { display: flex; flex-direction: column; gap: 8px; }
  .seg button { padding: 5px 13px; }
</style>
