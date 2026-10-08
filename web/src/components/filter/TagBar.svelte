<script lang="ts">
  import { untrack } from 'svelte';
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { availableGenres, availableTags, filter, onFilterChanged } from '../../lib/stores/library.svelte';
  import Icon from '../Icon.svelte';

  const tags = $derived(availableTags());
  const genres = $derived(availableGenres());
  let expandTags = $state(false);
  let expandGenres = $state(false);
  let tagChips = $state<HTMLElement | null>(null);
  let genreChips = $state<HTMLElement | null>(null);

  let hiddenTags = $state(0);
  let hiddenGenres = $state(0);
  // more content than the single row (one chip is 30px high), whether the row is unfolded or not
  let overflowTags = $state(false);
  let overflowGenres = $state(false);
  const overflows = (container: HTMLElement) => container.scrollHeight > 36;

  /** Number of chips that do not fit into the collapsed row. */
  function countHidden(container: HTMLElement): number {
    const bottom = container.getBoundingClientRect().bottom;
    return [...container.children].filter((chip) => chip.getBoundingClientRect().top >= bottom - 1).length;
  }

  $effect(() => {
    void tags;
    const container = tagChips;
    if (!container) return;
    const update = () => {
      overflowTags = overflows(container);
      hiddenTags = expandTags ? 0 : countHidden(container);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  });

  $effect(() => {
    void genres;
    const container = genreChips;
    if (!container) return;
    const update = () => {
      overflowGenres = overflows(container);
      hiddenGenres = expandGenres ? 0 : countHidden(container);
    };
    update();
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  });

  /** A selected chip in a collapsed row would be invisible; the row unfolds when a selection hides in it. */
  function hasHiddenSelection(container: HTMLElement | null): boolean {
    if (!container) return false;
    const bottom = container.getBoundingClientRect().bottom;
    return [...container.querySelectorAll('.chip.on')].some((chip) => chip.getBoundingClientRect().top >= bottom - 1);
  }

  $effect(() => {
    void filter.tags;
    void tags;
    if (!untrack(() => expandTags) && hasHiddenSelection(tagChips)) expandTags = true;
  });

  $effect(() => {
    void filter.genres;
    void genres;
    if (!untrack(() => expandGenres) && hasHiddenSelection(genreChips)) expandGenres = true;
  });

  function toggleTag(tag: string) {
    filter.tags = filter.tags.includes(tag) ? filter.tags.filter((x) => x !== tag) : [...filter.tags, tag];
    onFilterChanged();
  }

  function toggleGenre(genre: string) {
    filter.genres = filter.genres.includes(genre) ? filter.genres.filter((x) => x !== genre) : [...filter.genres, genre];
    onFilterChanged();
  }

  function onDragStart(event: DragEvent, type: 'tag' | 'genre', value: string) {
    event.dataTransfer?.setData(`application/x-dungeontuber-${type}`, value);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  }
</script>

{#if (prefs.filter.tags && tags.length) || (prefs.filter.genres && genres.length)}
  <div class="tagbar">
    {#if prefs.filter.tags && tags.length}
      <div class="line" data-tour="tags">
        <span class="label"><Icon name="tag" size={14} /></span>
        <div class="chips" class:open={expandTags} bind:this={tagChips}>
          {#each tags as tag (tag)}
            <button class="chip" class:on={filter.tags.includes(tag)} draggable="true" ondragstart={(e) => onDragStart(e, 'tag', tag)} onclick={() => toggleTag(tag)}>{tag}</button>
          {/each}
        </div>
        {#if overflowTags}
          <button class="more" onclick={() => (expandTags = !expandTags)}>{expandTags ? t('Less') : hiddenTags ? `${t('More')} (+${hiddenTags})` : t('More')} <Icon name={expandTags ? 'chevron-up' : 'chevron-down'} size={13} /></button>
        {/if}
      </div>
    {/if}
    {#if prefs.filter.genres && genres.length}
      <div class="line">
        <span class="label"><Icon name="music" size={14} /></span>
        <div class="chips" class:open={expandGenres} bind:this={genreChips}>
          {#each genres as genre (genre)}
            <button class="chip genre" class:on={filter.genres.includes(genre)} draggable="true" ondragstart={(e) => onDragStart(e, 'genre', genre)} onclick={() => toggleGenre(genre)}>{genre}</button>
          {/each}
        </div>
        {#if overflowGenres}
          <button class="more" onclick={() => (expandGenres = !expandGenres)}>{expandGenres ? t('Less') : hiddenGenres ? `${t('More')} (+${hiddenGenres})` : t('More')} <Icon name={expandGenres ? 'chevron-up' : 'chevron-down'} size={13} /></button>
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
