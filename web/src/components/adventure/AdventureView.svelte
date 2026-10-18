<script lang="ts">
  import { moveBlock, unreachable } from '../../lib/adventures';
  import { canDropOnAdventure, canDropOnBlock, dropOnAdventure, dropOnBlock } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { addBlock, adventures, change, switchToPlay, toggleVisibility } from '../../lib/stores/adventure.svelte';
  import { ui } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import AdventureMusic from './AdventureMusic.svelte';
  import BlockEditor from './BlockEditor.svelte';
  import GraphView from './GraphView.svelte';
  import PlayMode from './PlayMode.svelte';

  let layout = $state<'list' | 'graph'>('list');
  const MUSIC = '#music'; // the drop-down entry of the adventure music (phones)
  const adventure = $derived(adventures.current);
  const stranded = $derived(adventure ? new Set(unreachable(adventure).map((block) => block.id)) : new Set<string>());

  // below the blocks: the adventure's own music instead of the editor of a block
  let showMusic = $state(false);
  let musicOver = $state(false);
  let blockOver = $state<string | null>(null);

  // a block chosen elsewhere (the search of the header) is shown instead of the music
  $effect(() => {
    void adventures.selected;
    showMusic = false;
  });

  function selectBlock(id: string) {
    showMusic = false;
    adventures.selected = id;
  }
</script>

{#snippet modes()}
  <div class="seg">
    {#if adventure?.editable}<button class:on={adventures.mode === 'edit'} title={t('Edit')} aria-label={t('Edit')} onclick={() => (adventures.mode = 'edit')}><Icon name="edit" size={13} /><span class="label">{t('Edit')}</span></button>{/if}
    <button class:on={adventures.mode === 'play'} title={t('Play')} aria-label={t('Play')} onclick={switchToPlay}><Icon name="play" size={13} /><span class="label">{t('Play')}</span></button>
  </div>
{/snippet}

{#if adventure}
  <!-- on phones play mode has no header line: the mode buttons go to the end of its play bar -->
  {@const compact = ui.narrow && adventures.mode === 'play'}
  <section class="adventure">
    {#if !compact}
    <header>
      <h2 class="name ellipsis" title={adventure.title}>{adventure.title}</h2>
      <button class="btn sm visibility" class:in-play={adventures.mode === 'play'} disabled={!adventure.editable} onclick={() => void toggleVisibility()}
              title={adventure.visibility === 'public' ? t('Everyone can see this adventure. Click to make it private.') : t('Only you can see this adventure. Click to publish it.')}>
        <Icon name={adventure.visibility === 'public' ? 'users' : 'lock'} size={14} />{adventure.visibility === 'public' ? t('Public') : t('Private')}
      </button>
      {#if adventures.mode === 'edit'}
        <div class="seg">
          <button class:on={layout === 'list'} onclick={() => (layout = 'list')}><Icon name="list" size={13} /> {t('List')}</button>
          <button class:on={layout === 'graph'} onclick={() => (layout = 'graph')}><Icon name="tree" size={13} /> {t('Graph')}</button>
        </div>
      {/if}
      {@render modes()}
    </header>
    {/if}

    {#if adventures.mode === 'play'}
      <div class="scroll play"><PlayMode tools={compact ? modes : undefined} /></div>
    {:else}
      <div class="edit" class:graph={layout === 'graph'}>
        {#if layout === 'graph'}
          <GraphView />
        {:else if ui.narrow}
          <!-- phones: the blocks as a drop-down with the actions of the chosen one beside it, instead of the list -->
          {@const index = adventure.blocks.findIndex((block) => block.id === adventures.selected)}
          <div class="block-bar">
            <select aria-label={t('Blocks')} value={showMusic ? MUSIC : (adventures.selected ?? '')}
                    onchange={(e) => { const value = e.currentTarget.value; if (value === MUSIC) showMusic = true; else selectBlock(value); }}>
              {#each adventure.blocks as block, i (block.id)}
                <option value={block.id}>{block.played ? '✓ ' : ''}{block.title || t('Untitled')}{stranded.has(block.id) && i > 0 ? ' ·' : ''}</option>
              {/each}
              <option value={MUSIC}>♫ {t('Adventure music')} ({adventure.music.length})</option>
            </select>
            {#if adventure.editable}
              {#if !showMusic && index >= 0}
                <button class="icon-btn" title={t('Move up')} aria-label={t('Move up')} disabled={index === 0} onclick={() => change((a) => moveBlock(a, adventure.blocks[index].id, -1))}><Icon name="chevron-up" size={15} /></button>
                <button class="icon-btn" title={t('Move down')} aria-label={t('Move down')} disabled={index === adventure.blocks.length - 1} onclick={() => change((a) => moveBlock(a, adventure.blocks[index].id, 1))}><Icon name="chevron-down" size={15} /></button>
              {/if}
              <button class="icon-btn" title={t('Add block')} aria-label={t('Add block')} onclick={() => { showMusic = false; addBlock(); }}><Icon name="plus" size={16} /></button>
            {/if}
          </div>
        {:else}
        <nav class="blocks" aria-label={t('Blocks')}>
          {#each adventure.blocks as block, index (block.id)}
            <!-- songs of the adventure music or the library dropped here are added to the block -->
            <div class="block" class:active={!showMusic && adventures.selected === block.id} class:over={blockOver === block.id} role="listitem"
                 ondragover={(e) => { if (adventure.editable && canDropOnBlock(e.dataTransfer)) { e.preventDefault(); blockOver = block.id; } }}
                 ondragleave={(e) => { if (!(e.currentTarget as HTMLElement).contains(e.relatedTarget as Node)) blockOver = null; }}
                 ondrop={(e) => { if (!canDropOnBlock(e.dataTransfer)) return; e.preventDefault(); blockOver = null; void dropOnBlock(block.id, e.dataTransfer); }}>
              <button class="pick" onclick={() => selectBlock(block.id)}>
                {#if block.played}<Icon name="check" size={13} />{/if}
                <span class="ellipsis">{block.title || t('Untitled')}</span>
                {#if stranded.has(block.id) && index > 0}<span class="loose" title={t('No link leads to this block')}>·</span>{/if}
              </button>
              {#if adventure.editable && !showMusic && adventures.selected === block.id}
                <button class="icon-btn mini" title={t('Move up')} disabled={index === 0} onclick={() => change((a) => moveBlock(a, block.id, -1))}><Icon name="chevron-up" size={13} /></button>
                <button class="icon-btn mini" title={t('Move down')} disabled={index === adventure.blocks.length - 1} onclick={() => change((a) => moveBlock(a, block.id, 1))}><Icon name="chevron-down" size={13} /></button>
              {/if}
            </div>
          {/each}
          {#if adventure.editable}<button class="btn sm add" onclick={() => { showMusic = false; addBlock(); }}><Icon name="plus" size={13} />{t('Add block')}</button>{/if}
          <div class="block music-entry" class:active={showMusic} class:over={musicOver}
               ondragover={(e) => { if (adventure.editable && canDropOnAdventure(e.dataTransfer)) { e.preventDefault(); musicOver = true; } }}
               ondragleave={() => (musicOver = false)}
               ondrop={(e) => { e.preventDefault(); musicOver = false; void dropOnAdventure(adventure.id, adventure.title, e.dataTransfer); }}
               role="presentation">
            <button class="pick" onclick={() => (showMusic = true)}>
              <Icon name="playlist" size={14} /><span class="ellipsis">{t('Adventure music')}</span><span class="count muted">{adventure.music.length}</span>
            </button>
          </div>
        </nav>
        {/if}
        <div class="scroll">
          {#if showMusic && layout === 'list'}<AdventureMusic onselect={selectBlock} />{:else}<BlockEditor />{/if}
        </div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .adventure { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; padding: 0 16px; }
  header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .name { flex: 1; min-width: 120px; margin: 0; font-family: var(--font-display); font-size: 1.2rem; font-weight: 700; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .seg button { display: inline-flex; align-items: center; gap: 5px; }
  .edit { flex: 1; min-height: 0; display: grid; grid-template-columns: 220px 1fr; gap: 16px; }
  .edit.graph { grid-template-columns: 1fr; grid-template-rows: auto minmax(0, 1fr); gap: 12px; }
  .scroll { min-height: 0; overflow-y: auto; padding-bottom: 24px; }
  /* play mode fills the height: the overview of the welcome screen uses all of it */
  .scroll.play { flex: 1; display: flex; flex-direction: column; }
  .blocks { display: flex; flex-direction: column; gap: 2px; min-height: 0; overflow-y: auto; }
  .block { display: flex; align-items: center; border-radius: 9px; }
  .block:hover { background: var(--hover); }
  .block.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .pick { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; padding: 7px 10px; text-align: left; color: inherit; }
  .loose { color: var(--faint); font-size: 1.4em; line-height: 0.5; }
  .mini { width: 22px; height: 22px; }
  .add { align-self: flex-start; margin-top: 6px; }
  .music-entry { margin-top: 10px; padding-top: 6px; border-top: 1px solid var(--border); border-radius: 0 0 9px 9px; }
  .block.over, .music-entry.over { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .count { margin-left: auto; font-size: var(--fs-xs); font-weight: 400; }
  /* phones: a compact header (one line in play mode): no title (the tab shows it), no visibility button while playing, the modes as icons */
  @media (max-width: 900px) {
    header { gap: 8px; justify-content: flex-end; }
    .name { display: none; }
    .visibility.in-play { display: none; }
    .seg .label { display: none; }
  }
  .block-bar { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .block-bar select { flex: 1; min-width: 0; }
  @media (max-width: 900px) {
    .edit { grid-template-columns: minmax(0, 1fr); grid-template-rows: auto minmax(0, 1fr); gap: 10px; }
  }
</style>
