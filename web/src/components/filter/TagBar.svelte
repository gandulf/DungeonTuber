<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { availableGenres, availableTags, filter, onFilterChanged } from '../../lib/stores/library.svelte';
  import Icon from '../Icon.svelte';

  const tags = $derived(availableTags());
  const genres = $derived(availableGenres());
  let expandTags = $state(false);
  let expandGenres = $state(false);

  // selected chips first so they stay visible when collapsed
  const sortedTags = $derived([...tags].sort((a, b) => Number(filter.tags.includes(b)) - Number(filter.tags.includes(a))));
  const sortedGenres = $derived([...genres].sort((a, b) => Number(filter.genres.includes(b)) - Number(filter.genres.includes(a))));

  function toggleTag(tag: string) {
    filter.tags = filter.tags.includes(tag) ? filter.tags.filter((x) => x !== tag) : [...filter.tags, tag];
    onFilterChanged();
  }

  function toggleGenre(genre: string) {
    filter.genres = filter.genres.includes(genre) ? filter.genres.filter((x) => x !== genre) : [...filter.genres, genre];
    onFilterChanged();
  }

  function onTagDragStart(event: DragEvent, tag: string) {
    event.dataTransfer?.setData('application/x-dungeontuber-tag', tag);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  }
</script>

{#if (prefs.filter.tags && tags.length) || (prefs.filter.genres && genres.length)}
  <div class="tagbar">
    {#if prefs.filter.tags && tags.length}
      <div class="line" data-tour="tags">
        <span class="label"><Icon name="tag" size={14} /></span>
        <div class="chips" class:open={expandTags}>
          {#each sortedTags as tag (tag)}
            <button class="chip" class:on={filter.tags.includes(tag)} draggable="true" ondragstart={(e) => onTagDragStart(e, tag)} onclick={() => toggleTag(tag)}>{tag}</button>
          {/each}
        </div>
        {#if tags.length > 6}
          <button class="more" onclick={() => (expandTags = !expandTags)}>{expandTags ? t('Less') : t('More')} <Icon name={expandTags ? 'chevron-up' : 'chevron-down'} size={13} /></button>
        {/if}
      </div>
    {/if}
    {#if prefs.filter.genres && genres.length}
      <div class="line">
        <span class="label"><Icon name="music" size={14} /></span>
        <div class="chips" class:open={expandGenres}>
          {#each sortedGenres as genre (genre)}
            <button class="chip genre" class:on={filter.genres.includes(genre)} onclick={() => toggleGenre(genre)}>{genre}</button>
          {/each}
        </div>
        {#if genres.length > 6}
          <button class="more" onclick={() => (expandGenres = !expandGenres)}>{expandGenres ? t('Less') : t('More')} <Icon name={expandGenres ? 'chevron-up' : 'chevron-down'} size={13} /></button>
        {/if}
      </div>
    {/if}
  </div>
{/if}

<style>
  .tagbar { display: flex; flex-direction: column; gap: 8px; flex: none; padding-right: 2px; }
  .line { display: flex; align-items: flex-start; gap: 8px; }
  .label { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; border-radius: 9px; color: var(--faint); background: var(--surface); border: 1px solid var(--border); flex: none; }
  .chips { flex: 1; display: flex; flex-wrap: wrap; gap: 6px; max-height: 30px; overflow: hidden; }
  .chips.open { max-height: 150px; overflow-y: auto; }
  .more { display: inline-flex; align-items: center; gap: 4px; height: 30px; padding: 0 12px; border-radius: 10px; border: 1px solid var(--border); background: var(--surface); color: var(--muted); font-size: var(--fs-sm); flex: none; }
  .more:hover { color: var(--text); border-color: var(--border-strong); }
</style>
