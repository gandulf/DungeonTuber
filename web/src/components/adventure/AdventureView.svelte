<script lang="ts">
  import { moveBlock, unreachable } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { addBlock, adventures, change, toggleVisibility } from '../../lib/stores/adventure.svelte';
  import Icon from '../Icon.svelte';
  import BlockEditor from './BlockEditor.svelte';
  import PlayMode from './PlayMode.svelte';

  const adventure = $derived(adventures.current);
  const stranded = $derived(adventure ? new Set(unreachable(adventure).map((block) => block.id)) : new Set<string>());
</script>

{#if adventure}
  <section class="adventure">
    <header>
      <h2 class="name ellipsis" title={adventure.title}>{adventure.title}</h2>
      <span class="state muted">{adventures.saving ? t('Saving…') : ''}</span>
      <button class="btn sm" disabled={!adventure.editable} onclick={() => void toggleVisibility()}
              title={adventure.visibility === 'public' ? t('Everyone can see this adventure. Click to make it private.') : t('Only you can see this adventure. Click to publish it.')}>
        <Icon name={adventure.visibility === 'public' ? 'users' : 'lock'} size={14} />{adventure.visibility === 'public' ? t('Public') : t('Private')}
      </button>
      <div class="seg">
        {#if adventure.editable}<button class:on={adventures.mode === 'edit'} onclick={() => (adventures.mode = 'edit')}><Icon name="edit" size={13} /> {t('Edit')}</button>{/if}
        <button class:on={adventures.mode === 'play'} onclick={() => (adventures.mode = 'play')}><Icon name="play" size={13} /> {t('Play')}</button>
      </div>
    </header>

    {#if adventures.mode === 'play'}
      <div class="scroll"><PlayMode /></div>
    {:else}
      <div class="edit">
        <nav class="blocks" aria-label={t('Blocks')}>
          {#each adventure.blocks as block, index (block.id)}
            <div class="block" class:active={adventures.selected === block.id}>
              <button class="pick" onclick={() => (adventures.selected = block.id)}>
                {#if block.played}<Icon name="check" size={13} />{/if}
                <span class="ellipsis">{block.title || t('Untitled')}</span>
                {#if stranded.has(block.id) && index > 0}<span class="loose" title={t('No link leads to this block')}>·</span>{/if}
              </button>
              {#if adventure.editable && adventures.selected === block.id}
                <button class="icon-btn mini" title={t('Move up')} disabled={index === 0} onclick={() => change((a) => moveBlock(a, block.id, -1))}><Icon name="chevron-up" size={13} /></button>
                <button class="icon-btn mini" title={t('Move down')} disabled={index === adventure.blocks.length - 1} onclick={() => change((a) => moveBlock(a, block.id, 1))}><Icon name="chevron-down" size={13} /></button>
              {/if}
            </div>
          {/each}
          {#if adventure.editable}<button class="btn sm add" onclick={() => addBlock()}><Icon name="plus" size={13} />{t('Add block')}</button>{/if}
        </nav>
        <div class="scroll"><BlockEditor /></div>
      </div>
    {/if}
  </section>
{/if}

<style>
  .adventure { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 12px; padding: 0 16px; }
  header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
  .name { flex: 1; min-width: 120px; margin: 0; font-family: var(--font-display); font-size: 1.2rem; font-weight: 700; }
  .state { font-size: var(--fs-xs); min-width: 56px; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .seg button { display: inline-flex; align-items: center; gap: 5px; }
  .edit { flex: 1; min-height: 0; display: grid; grid-template-columns: 220px 1fr; gap: 16px; }
  .scroll { min-height: 0; overflow-y: auto; padding-bottom: 24px; }
  .blocks { display: flex; flex-direction: column; gap: 2px; min-height: 0; overflow-y: auto; }
  .block { display: flex; align-items: center; border-radius: 9px; }
  .block:hover { background: var(--hover); }
  .block.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .pick { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; padding: 7px 10px; text-align: left; color: inherit; }
  .loose { color: var(--faint); font-size: 1.4em; line-height: 0.5; }
  .mini { width: 22px; height: 22px; }
  .add { align-self: flex-start; margin-top: 6px; }
  @media (max-width: 760px) {
    .edit { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
    .blocks { flex-direction: row; flex-wrap: wrap; max-height: 120px; }
  }
</style>
