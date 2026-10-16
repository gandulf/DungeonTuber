<script lang="ts">
  import { addLink, addMusic, linksFrom, linksTo, refKey, removeLink } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { applyBlockLink, applyFormat, applySongLink, blockLinkTarget, renderNotes, songLinkTarget, type Format } from '../../lib/notes';
  import { adventures, change, deleteBlock, enterBlock, playBlockMusic, playSongLink, selectedBlock, setPlayed, startEffect } from '../../lib/stores/adventure.svelte';
  import { effects, loadEffects } from '../../lib/stores/effects.svelte';
  import { cueLight } from '../../lib/stores/player.svelte';
  import { askConfirm, openDialog } from '../../lib/stores/ui.svelte';
  import type { LightSetting, MusicRef } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import LightEditor from '../dialogs/LightEditor.svelte';
  import PickMusicDialog from './PickMusicDialog.svelte';

  const block = $derived(selectedBlock());
  const adventure = $derived(adventures.current!);

  let preview = $state(false);
  let notes = $state<HTMLTextAreaElement | null>(null);
  let light = $state<LightSetting | null>(null);
  let linkTarget = $state('');

  // the light of the selected block is edited in a local copy (the editor binds to it) and written back when it differs
  let lightOf = '';
  $effect(() => {
    const saved = block?.light ? $state.snapshot(block.light) : null;
    // the server leaves out what is not set
    light = saved ? { scene: saved.scene ?? null, brightness: saved.brightness ?? null, temperature: saved.temperature ?? null, color: saved.color ?? null } : null;
    lightOf = JSON.stringify(light);
  });
  $effect(() => {
    const value = $state.snapshot(light);
    if (!block || JSON.stringify(value) === lightOf) return;
    lightOf = JSON.stringify(value);
    change(() => (block.light = value));
  });

  $effect(() => {
    if (!effects.list.length && !effects.loading) void loadEffects();
  });

  const others = $derived(adventure.blocks.filter((item) => item.id !== block?.id));
  const outgoing = $derived(block ? linksFrom(adventure, block.id) : []);
  const incoming = $derived(block ? linksTo(adventure, block.id) : []);
  const titleOf = (id: string) => adventure.blocks.find((item) => item.id === id)?.title || t('Untitled');

  function format(kind: Format) {
    if (!notes || !block) return;
    const edit = applyFormat(notes.value, notes.selectionStart, notes.selectionEnd, kind);
    change(() => (block.markdown = edit.text));
    notes.value = edit.text;
    notes.focus();
    notes.setSelectionRange(edit.start, edit.end);
  }

  function linkToBlock(id: string) {
    const target = adventure.blocks.find((item) => item.id === id);
    if (!notes || !block || !target) return;
    const edit = applyBlockLink(notes.value, notes.selectionStart, notes.selectionEnd, target);
    change(() => (block.markdown = edit.text));
    notes.value = edit.text;
    notes.focus();
    notes.setSelectionRange(edit.start, edit.end);
  }

  function linkToSong() {
    if (!notes || !block) return;
    const [start, end] = [notes.selectionStart, notes.selectionEnd];
    openDialog(PickMusicDialog, {
      single: true,
      has: () => false,
      onpick: (ref: MusicRef) => {
        if (ref.type !== 'song' || !notes || !block) return;
        const edit = applySongLink(notes.value, start, end, ref);
        change(() => (block.markdown = edit.text));
        notes.value = edit.text;
        notes.focus();
        notes.setSelectionRange(edit.start, edit.end);
      },
    });
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
    openDialog(PickMusicDialog, {
      onpick: (ref: MusicRef) => change(() => addMusic(block!, ref)),
      has: (ref: MusicRef) => !!block?.music.some((item) => refKey(item) === refKey(ref)),
    });
  }

  function addEffect(path: string) {
    const effect = effects.list.find((item) => item.path === path);
    if (!effect || !block) return;
    change(() => {
      if (!block.effects.some((item) => item.path === path)) block.effects.push({ path, name: effect.title || effect.name, loop: true, autostart: false });
    });
  }

  function newLink() {
    if (!block || !linkTarget) return;
    change((a) => addLink(a, block.id, linkTarget));
    linkTarget = '';
  }

  async function remove() {
    if (block && (await askConfirm(t('Delete the block "{0}"?', block.title || t('Untitled'))))) deleteBlock(block.id);
  }

  const toolbar: [Format, string, string][] = [
    ['bold', 'B', 'Bold'], ['italic', 'I', 'Italic'], ['heading', 'H', 'Heading'], ['list', '•', 'List'], ['quote', '❝', 'Quote'], ['link', '🔗', 'Link'], ['rule', '―', 'Divider'],
  ];
</script>

{#if block}
  {@const editable = adventure.editable}
  <div class="editor">
    <div class="head">
      <input class="title" type="text" placeholder={t('Block title')} value={block.title} readonly={!editable}
             oninput={(e) => change(() => (block.title = e.currentTarget.value))} />
      <button class="btn sm" title={t('Play this block')} onclick={() => void enterBlock(block.id)}><Icon name="play" size={14} />{t('Play')}</button>
      {#if editable}<button class="icon-btn" title={t('Delete block')} onclick={() => void remove()}><Icon name="trash" size={16} /></button>{/if}
    </div>

    <div class="flags">
      <label class="check"><input type="checkbox" checked={block.played} onchange={(e) => setPlayed(block.id, e.currentTarget.checked)} disabled={!editable} />{t('Played')}</label>
      <label class="check"><input type="checkbox" checked={block.autoplay} disabled={!editable}
                                  onchange={(e) => change(() => (block.autoplay = e.currentTarget.checked))} />{t('Start the music when the block is entered')}</label>
    </div>

    <section>
      <div class="bar">
        <span class="label-xs">{t('Notes')}</span>
        <span class="grow"></span>
        {#if editable && !preview}
          {#each toolbar as [kind, label, name] (kind)}
            <button class="fmt" title={t(name)} aria-label={t(name)} onclick={() => format(kind)}>{label}</button>
          {/each}
          <button class="fmt" title={t('Link the selected text to a song')} aria-label={t('Song link')} onclick={linkToSong}>♪</button>
          {#if others.length}
            <select class="block-pick" aria-label={t('Link to a block')} title={t('Link the selected text to a block')} value=""
                    onchange={(e) => { linkToBlock(e.currentTarget.value); e.currentTarget.value = ''; }}>
              <option value="">{t('Block link…')}</option>
              {#each others as other (other.id)}<option value={other.id}>{other.title || t('Untitled')}</option>{/each}
            </select>
          {/if}
        {/if}
        <button class="btn sm ghost" onclick={() => (preview = !preview)}>{preview ? t('Edit') : t('Preview')}</button>
      </div>
      {#if preview || !editable}
        <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
        <div class="notes" onclick={previewClick}>{@html renderNotes(block.markdown, adventure.blocks) || `<p class="muted">${t('No notes yet.')}</p>`}</div>
      {:else}
        <textarea bind:this={notes} rows="12" placeholder={t('Describe the scene in Markdown…')} value={block.markdown}
                  oninput={(e) => change(() => (block.markdown = e.currentTarget.value))}></textarea>
      {/if}
    </section>

    <section>
      <div class="bar">
        <span class="label-xs">{t('Music')}</span>
        <span class="grow"></span>
        {#if block.music.length}<button class="btn sm ghost" onclick={() => void playBlockMusic(block)}><Icon name="play" size={13} />{t('Play')}</button>{/if}
        {#if editable}<button class="btn sm" onclick={addMusicDialog}><Icon name="plus" size={13} />{t('Add')}</button>{/if}
      </div>
      {#each block.music as ref, index (refKey(ref))}
        <div class="item">
          <Icon name={ref.type === 'song' ? 'music' : 'playlist'} size={15} />
          <span class="ellipsis">{ref.title || ref.path || t('Untitled')}</span>
          {#if ref.type === 'playlist' && ref.unavailable}<span class="warn">{t('unavailable')}</span>{/if}
          {#if editable}<button class="icon-btn mini" title={t('Remove')} onclick={() => change(() => block.music.splice(index, 1))}><Icon name="close" size={13} /></button>{/if}
        </div>
      {:else}
        <span class="muted small">{t('No music: the current music keeps playing.')}</span>
      {/each}
    </section>

    <section>
      <div class="bar">
        <span class="label-xs">{t('Effects')}</span>
        <span class="grow"></span>
        {#if editable}
          <select aria-label={t('Add effect')} value="" onchange={(e) => { addEffect(e.currentTarget.value); e.currentTarget.value = ''; }}>
            <option value="">{t('Add effect…')}</option>
            {#each effects.list as effect (effect.id)}<option value={effect.path}>{effect.title || effect.name}</option>{/each}
          </select>
        {/if}
      </div>
      {#each block.effects as effect, index (effect.path)}
        <div class="item">
          <Icon name="waves" size={15} />
          <span class="ellipsis">{effect.name || effect.path}</span>
          <label class="check small"><input type="checkbox" checked={effect.loop} disabled={!editable} onchange={(e) => change(() => (effect.loop = e.currentTarget.checked))} />{t('Loop')}</label>
          <label class="check small"><input type="checkbox" checked={effect.autostart} disabled={!editable} onchange={(e) => change(() => (effect.autostart = e.currentTarget.checked))} />{t('Auto')}</label>
          <button class="icon-btn mini" title={t('Play')} onclick={() => void startEffect(effect)}><Icon name="play" size={13} /></button>
          {#if editable}<button class="icon-btn mini" title={t('Remove')} onclick={() => change(() => block.effects.splice(index, 1))}><Icon name="close" size={13} /></button>{/if}
        </div>
      {:else}
        <span class="muted small">{t('Ambient loops or one-shot effects of the effects folder.')}</span>
      {/each}
    </section>

    <section>
      <div class="bar">
        <span class="label-xs">{t('Light')}</span>
        <span class="grow"></span>
        {#if block.light}<button class="btn sm ghost" onclick={() => cueLight(block.light as LightSetting)}>{t('Preview')}</button>{/if}
      </div>
      {#if editable}<LightEditor bind:value={light} />{:else if !block.light}<span class="muted small">{t('None')}</span>{/if}
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
          <button class="btn sm" disabled={!linkTarget} onclick={newLink}>{t('Add link')}</button>
        </div>
      {/if}
      {#if incoming.length}
        <span class="muted small">{t('Reached from')}: {incoming.map((link) => titleOf(link.from)).join(', ')}</span>
      {/if}
    </section>
  </div>
{/if}

<style>
  .editor { display: flex; flex-direction: column; gap: 16px; min-width: 0; }
  .head { display: flex; align-items: center; gap: 8px; }
  .title { flex: 1; min-width: 0; font-size: var(--fs-lg, 1.15em); font-weight: 650; }
  .flags { display: flex; flex-wrap: wrap; gap: 6px 18px; }
  .check { display: inline-flex; align-items: center; gap: 7px; font-size: var(--fs-sm); color: var(--muted); }
  .check.small { font-size: var(--fs-xs); }
  section { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); }
  .bar { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
  .grow { flex: 1; }
  .block-pick { max-width: 150px; font-size: var(--fs-sm); }
  .fmt { min-width: 28px; height: 28px; padding: 0 6px; border-radius: 7px; color: var(--muted); font-weight: 600; }
  .fmt:hover { background: var(--hover); color: var(--text); }
  textarea { width: 100%; min-height: 200px; resize: vertical; font-family: var(--font-mono, ui-monospace, monospace); line-height: 1.5; box-sizing: border-box; }
  .notes { line-height: 1.6; overflow-wrap: anywhere; }
  .notes :global(img) { max-width: 100%; border-radius: 8px; }
  .notes :global(h1), .notes :global(h2), .notes :global(h3) { margin: 0.6em 0 0.3em; }
  .notes :global(blockquote) { margin: 0.6em 0; padding-left: 12px; border-left: 3px solid var(--accent); color: var(--muted); }
  .item { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .item .target { flex: none; max-width: 40%; font-weight: 550; }
  .item .label { flex: 1; min-width: 0; }
  .item > .ellipsis { flex: 1; min-width: 0; }
  .mini { width: 24px; height: 24px; }
  .small { font-size: var(--fs-sm); }
  .warn { font-size: var(--fs-xs); color: var(--red); border: 1px solid var(--red); border-radius: 6px; padding: 0 6px; }
</style>
