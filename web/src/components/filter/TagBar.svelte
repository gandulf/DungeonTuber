<script lang="ts">
  import { untrack } from 'svelte';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { availableGenres, availableTags, filter, onFilterChanged } from '../../lib/stores/library.svelte';
  import { hasTag, toggleTagIn } from '../../lib/tags';
  import Icon from '../Icon.svelte';

  const tags = $derived(availableTags());
  const genres = $derived(availableGenres());
  // a row is unfolded by the user (remembered in the profile) or, for now, because a selected chip would hide in it
  let autoTags = $state(false);
  let autoGenres = $state(false);
  const expandTags = $derived(prefs.tagsExpanded || autoTags);
  const expandGenres = $derived(prefs.genresExpanded || autoGenres);
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
    if (!untrack(() => expandTags) && hasHiddenSelection(tagChips)) autoTags = true;
  });

  $effect(() => {
    void filter.genres;
    void genres;
    if (!untrack(() => expandGenres) && hasHiddenSelection(genreChips)) autoGenres = true;
  });

  function toggleTag(tag: string) {
    filter.tags = toggleTagIn(filter.tags, tag);
    onFilterChanged();
  }

  function toggleGenre(genre: string) {
    filter.genres = toggleTagIn(filter.genres, genre);
    onFilterChanged();
  }

  function onDragStart(event: DragEvent, type: 'tag' | 'genre', value: string) {
    event.dataTransfer?.setData(`application/x-dungeontuber-${type}`, value);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  }
</script>

<!-- The icon of a row unfolds and folds it when it has more chips than fit; the bubble counts the chips that are hidden. -->
{#snippet toggle(icon: string, overflow: boolean, expanded: boolean, hidden: number, flip: () => void)}
  {#if overflow}
    <button class="label toggle" aria-expanded={expanded} title={expanded ? t('Less') : t('More')} aria-label={expanded ? t('Less') : t('More')} onclick={flip}>
      <Icon name={icon} size={14} />
      {#if !expanded && hidden}<span class="badge">+{hidden}</span>{/if}
    </button>
  {:else}
    <span class="label"><Icon name={icon} size={14} /></span>
  {/if}
{/snippet}

{#if (prefs.filter.tags && tags.length) || (prefs.filter.genres && genres.length)}
  <div class="tagbar">
    {#if prefs.filter.tags && tags.length}
      <div class="line" data-tour="tags">
        {@render toggle('tag', overflowTags, expandTags, hiddenTags, () => { prefs.tagsExpanded = !expandTags; autoTags = false; savePrefs(); })}
        <div class="chips" class:open={expandTags} bind:this={tagChips}>
          {#each tags as tag (tag)}
            <button class="chip" class:on={hasTag(filter.tags, tag)} draggable="true" ondragstart={(e) => onDragStart(e, 'tag', tag)} onclick={() => toggleTag(tag)}>{tag}</button>
          {/each}
        </div>
      </div>
    {/if}
    {#if prefs.filter.genres && genres.length}
      <div class="line">
        {@render toggle('music', overflowGenres, expandGenres, hiddenGenres, () => { prefs.genresExpanded = !expandGenres; autoGenres = false; savePrefs(); })}
        <div class="chips" class:open={expandGenres} bind:this={genreChips}>
          {#each genres as genre (genre)}
            <button class="chip genre" class:on={hasTag(filter.genres, genre)} draggable="true" ondragstart={(e) => onDragStart(e, 'genre', genre)} onclick={() => toggleGenre(genre)}>{genre}</button>
          {/each}
        </div>
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
  .toggle { position: relative; padding: 0; cursor: pointer; font: inherit; }
  .toggle:hover { color: var(--text); border-color: var(--border-strong); }
  .toggle[aria-expanded='true'] { color: var(--accent); border-color: var(--accent); background: var(--accent-soft); }
  .badge { position: absolute; top: -7px; right: -7px; min-width: 18px; height: 18px; padding: 0 5px; box-sizing: border-box; display: flex; align-items: center; justify-content: center; border-radius: 999px; background: var(--accent); color: var(--accent-text); font-size: 10px; font-weight: 700; line-height: 1; box-shadow: 0 0 0 2px var(--bg); pointer-events: none; }
</style>
