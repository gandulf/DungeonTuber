<script lang="ts">
  import { untrack } from 'svelte';
  import { api, coverUrl, pathToId } from '../../lib/api';
  import { toggleFavorite, trackMenu, uploadFiles } from '../../lib/actions';
  import { itemsFromDrop } from '../../lib/upload';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { bpmLevel, categoryLevel, emptyFilter, genreLevel, scoreLevel, scorePercent } from '../../lib/scoring';
  import { data } from '../../lib/stores/data.svelte';
  import { extraCategoryKeys, filter, library, loadTab, removeFromPlaylist, reorderPlaylist, setSort, updateTrack, visibleRows, type Tab } from '../../lib/stores/library.svelte';
  import { player, playTrack, refreshCurrentTrack } from '../../lib/stores/player.svelte';
  import { errorToast, openDialog, openMenu, type MenuItem } from '../../lib/stores/ui.svelte';
  import type { Track } from '../../lib/types';
  import ImagePopup from '../dialogs/ImagePopup.svelte';
  import Icon from '../Icon.svelte';

  let { tab }: { tab: Tab } = $props();

  interface Column {
    id: string;
    label: string;
    width: string;
    sort?: string;
    edit?: 'text' | 'number' | 'list' | 'category';
    align?: 'right' | 'center';
    title?: string;
  }

  const ROW_HEIGHT = { small: 38, medium: 52, large: 68 } as const;
  const rowHeight = $derived(ROW_HEIGHT[prefs.rowStyle]);

  const rows = $derived(visibleRows());
  const filterActive = $derived(!emptyFilter(filter));

  const categoryKeys = $derived.by(() => {
    const known = data.categories.map((c) => c.key);
    return [...known, ...extraCategoryKeys(known)];
  });

  const columns = $derived.by((): Column[] => {
    const c = prefs.columns;
    const list: Column[] = [];
    if (tab.type === 'playlist' && c.index) list.push({ id: 'index', label: '#', width: '42px', sort: 'index', align: 'right' });
    if (c.favorite) list.push({ id: 'favorite', label: '', width: '30px', sort: 'favorite', align: 'center', title: t('Favorite') });
    list.push({ id: 'name', label: prefs.titleInsteadOfFile ? t('Title') : t('Name'), width: 'minmax(240px, 1.5fr)', sort: 'name', edit: prefs.titleInsteadOfFile ? 'text' : undefined });
    if (c.tags) list.push({ id: 'mood', label: t('Mood'), width: 'minmax(130px, 0.7fr)' });
    if (c.title && !prefs.titleInsteadOfFile) list.push({ id: 'title', label: t('Title'), width: 'minmax(120px, 0.6fr)', sort: 'title', edit: 'text' });
    if (c.summary && !prefs.summaryUnderTitle) list.push({ id: 'summary', label: t('Summary'), width: 'minmax(160px, 0.8fr)', sort: 'summary', edit: 'text' });
    if (c.artist) list.push({ id: 'artist', label: t('Artist'), width: '130px', sort: 'artist', edit: 'text' });
    if (c.album) list.push({ id: 'album', label: t('Album'), width: '130px', sort: 'album', edit: 'text' });
    if (c.genre) list.push({ id: 'genre', label: t('Genre'), width: '110px', sort: 'genre', edit: 'list' });
    if (c.bpm && (!prefs.dynamicColumns || filter.bpm !== null)) list.push({ id: 'bpm', label: t('BPM'), width: '58px', sort: 'bpm', edit: 'number', align: 'right' });
    if (c.score && (!prefs.dynamicScore || filterActive)) list.push({ id: 'score', label: t('Score'), width: '62px', sort: 'score', align: 'right' });
    for (const key of categoryKeys) {
      if (prefs.hiddenCategories.includes(key)) continue;
      const value = filter.categories[key];
      if (prefs.dynamicColumns && (value === null || value === undefined || value < 0)) continue;
      const category = data.categories.find((cat) => cat.key === key);
      list.push({ id: `cat:${key}`, label: category?.name ?? key, width: '108px', sort: `cat:${key}`, edit: 'category', title: category?.description });
    }
    if (c.duration) list.push({ id: 'duration', label: t('Duration'), width: '70px', sort: 'length', align: 'right' });
    return list;
  });

  const MIN_COLUMN = 40;
  // a column the user resized keeps its pixel width, the others keep their flexible default
  const widthOf = (col: Column) => (prefs.columnWidths[col.id] ? `${prefs.columnWidths[col.id]}px` : col.width);
  const template = $derived(columns.map(widthOf).join(' '));
  // minimum row width so the header and rows scroll horizontally together
  const minWidth = $derived(columns.reduce((sum, col) => sum + (parseInt(widthOf(col).replace('minmax(', ''), 10) || 0), 0));

  // --- virtual scrolling ---
  let viewport = $state<HTMLDivElement | null>(null);
  let scrollTop = $state(0);
  let viewportHeight = $state(600);
  const overscan = 8;
  const first = $derived(Math.max(0, Math.floor(scrollTop / rowHeight) - overscan));
  const last = $derived(Math.min(rows.length, Math.ceil((scrollTop + viewportHeight) / rowHeight) + overscan));
  const visible = $derived(rows.slice(first, last));

  $effect(() => {
    if (!viewport) return;
    const observer = new ResizeObserver(() => (viewportHeight = viewport!.clientHeight));
    observer.observe(viewport);
    return () => observer.disconnect();
  });

  // reset scroll when switching tabs
  $effect(() => {
    void tab.key;
    if (viewport) viewport.scrollTop = 0;
    anchor = cursor = null;
  });

  // --- selection ---
  // anchor: where a shift-selection starts, cursor: the row the keyboard moves from
  let anchor: number | null = null;
  let cursor: number | null = null;
  let table = $state<HTMLDivElement | null>(null);
  const selected = $derived(new Set(library.selection));

  function select(index: number, event: MouseEvent | KeyboardEvent) {
    const id = rows[index]?.track.id;
    if (!id) return;
    cursor = index;
    if (event.shiftKey && anchor !== null) {
      const [a, b] = [Math.min(anchor, index), Math.max(anchor, index)];
      library.selection = rows.slice(a, b + 1).map((row) => row.track.id);
    } else if (event.ctrlKey || event.metaKey) {
      library.selection = selected.has(id) ? library.selection.filter((s) => s !== id) : [...library.selection, id];
      anchor = index;
    } else {
      library.selection = [id];
      anchor = index;
    }
  }

  function selectedTracks(): Track[] {
    return rows.filter((row) => selected.has(row.track.id)).map((row) => row.track);
  }

  function scrollIntoView(index: number) {
    if (!viewport) return;
    const header = (viewport.querySelector('.header') as HTMLElement | null)?.offsetHeight ?? 0;
    const top = index * rowHeight;
    const visibleHeight = viewport.clientHeight - header;
    if (top < viewport.scrollTop) viewport.scrollTop = top;
    else if (top + rowHeight > viewport.scrollTop + visibleHeight) viewport.scrollTop = top + rowHeight - visibleHeight;
    scrollTop = viewport.scrollTop; // render the new window right away instead of waiting for the scroll event
  }

  // when the filter (or the sorting) changes the best match is selected (like the desktop app); moving the selection afterwards must not trigger this again
  let bestFor = '';
  $effect(() => {
    const key = `${tab.key}|${library.sortKey}|${library.sortAsc}|${JSON.stringify(filter)}`;
    if (!filterActive || library.sortKey !== 'score' || !rows.length) {
      bestFor = '';
      return;
    }
    if (key === bestFor) return;
    bestFor = key;
    untrack(() => {
      library.selection = [rows[0].track.id];
      anchor = cursor = 0;
      if (viewport) viewport.scrollTop = 0;
    });
  });

  // --- keyboard (navigation, type-to-search) ---
  function onKeydown(event: KeyboardEvent) {
    if (editing) return;
    const current = Math.min(cursor ?? anchor ?? -1, rows.length - 1);
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const target = Math.max(0, Math.min(rows.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
      select(target, event);
      scrollIntoView(target);
      table?.focus({ preventScroll: true }); // a focused row can be recycled by the virtual list, which would end the keyboard navigation
    } else if ((event.key === 'ArrowLeft' || event.key === 'ArrowRight') && viewport && viewport.scrollWidth > viewport.clientWidth) {
      event.preventDefault(); // many columns: scroll the whole table sideways
      viewport.scrollBy({ left: (event.key === 'ArrowRight' ? 1 : -1) * (event.ctrlKey ? viewport.clientWidth * 0.8 : 120) });
    } else if (event.key === 'PageDown' || event.key === 'PageUp') {
      event.preventDefault();
      const step = Math.floor(viewportHeight / rowHeight);
      const target = Math.max(0, Math.min(rows.length - 1, current + (event.key === 'PageDown' ? step : -step)));
      select(target, event);
      scrollIntoView(target);
      table?.focus({ preventScroll: true });
    } else if (event.key === 'Enter' && current >= 0) {
      void playTrack(rows[current].track);
    } else if (event.key === 'Delete' && tab.type === 'playlist' && library.selection.length) {
      void removeFromPlaylist(tab.path, library.selection);
    } else if (event.key === 'F2' && current >= 0) {
      const editable = columns.find((col) => col.edit === 'text');
      if (editable) startEdit(rows[current].track, editable);
    } else if (event.key === 'Escape') {
      library.search = '';
    } else if (event.key === 'Backspace') {
      library.search = library.search.slice(0, -1);
    } else if (event.key.length === 1 && /[\p{L}\p{N} _\-]/u.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      library.search += event.key;
    } else if ((event.ctrlKey || event.metaKey) && event.key === 'a') {
      event.preventDefault();
      library.selection = rows.map((row) => row.track.id);
    }
  }

  // --- inline editing ---
  let editing = $state<{ id: string; column: string; value: string } | null>(null);

  function cellText(track: Track, column: Column): string {
    switch (column.id) {
      case 'name': return track.title ?? '';
      case 'title': return track.title ?? '';
      case 'summary': return track.summary ?? '';
      case 'artist': return track.artist ?? '';
      case 'album': return track.album ?? '';
      case 'genre': return track.genres.join(', ');
      case 'bpm': return track.bpm?.toString() ?? '';
      default: {
        const value = track.categories[column.id.slice(4)];
        return value === undefined || value === null ? '' : String(value);
      }
    }
  }

  function startEdit(track: Track, column: Column) {
    editing = { id: track.id, column: column.id, value: cellText(track, column) };
  }

  async function commitEdit() {
    if (!editing) return;
    const { id, column, value } = editing;
    editing = null;
    const track = tab.tracks.find((tr) => tr.id === id);
    if (!track) return;
    const col = columns.find((c) => c.id === column);
    if (!col || value === cellText(track, col)) return;
    const patch: Record<string, unknown> = {};
    if (column === 'name' || column === 'title') patch.title = value;
    else if (column === 'genre') patch.genres = value.split(',').map((s) => s.trim()).filter(Boolean);
    else if (column === 'bpm') {
      const bpm = value.trim() === '' ? null : Number(value);
      if (bpm !== null && (!Number.isFinite(bpm) || bpm < 0)) return errorToast(t('Invalid number'));
      patch.bpm = bpm === null ? null : Math.round(bpm);
    } else if (column.startsWith('cat:')) {
      const number = value.trim() === '' ? null : Number(value.replace(',', '.'));
      if (number !== null && !Number.isFinite(number)) return errorToast(t('Invalid number'));
      patch.categories = { [column.slice(4)]: number === null ? null : Math.min(10, Math.max(0, number)) };
    } else patch[column] = value;
    try {
      const updated = await api.patchTrack(id, patch);
      updateTrack(updated);
      refreshCurrentTrack(updated);
    } catch (e) {
      errorToast(e);
    }
  }

  function onCellDblClick(event: MouseEvent, track: Track, column: Column) {
    event.stopPropagation();
    if (column.id === 'favorite') return void toggleFavorite(track);
    if (column.id === 'name' && (event.target as HTMLElement).closest('.thumb')) {
      if (track.has_cover) openDialog(ImagePopup, { src: coverUrl(track.id, 0), title: track.title || track.name });
      return;
    }
    // double-click plays (like the desktop app); the title is edited with F2
    if (column.id !== 'name' && column.edit) startEdit(track, column);
    else void playTrack(track);
  }

  function focusInput(node: HTMLInputElement) {
    node.focus();
    node.select();
  }

  // --- drag & drop ---
  let dragIds: string[] = [];
  let dropIndex = $state<number | null>(null);
  let fileDrop = $state(false);
  const canReorder = $derived(tab.type === 'playlist' && library.sortKey === 'index' && library.sortAsc && !library.search);

  function onDragStart(event: DragEvent, track: Track) {
    if (!selected.has(track.id)) library.selection = [track.id];
    dragIds = [...library.selection];
    event.dataTransfer?.setData('application/x-dungeontuber-tracks', JSON.stringify(dragIds));
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copyMove';
  }

  function onRowDragOver(event: DragEvent, index: number) {
    const types = event.dataTransfer?.types ?? [];
    if (types.includes('application/x-dungeontuber-tag') || types.includes('application/x-dungeontuber-genre') || (canReorder && types.includes('application/x-dungeontuber-tracks'))
        || (tab.type === 'playlist' && types.includes('application/x-dungeontuber-path'))) {
      event.preventDefault();
      dropIndex = index;
    }
  }

  async function onRowDrop(event: DragEvent, track: Track, index: number) {
    const tag = event.dataTransfer?.getData('application/x-dungeontuber-tag');
    const genre = event.dataTransfer?.getData('application/x-dungeontuber-genre');
    const treePath = event.dataTransfer?.getData('application/x-dungeontuber-path');
    dropIndex = null;
    if (treePath && tab.type === 'playlist') {
      event.preventDefault();
      event.stopPropagation();
      await dropTreePath(treePath, index);
      return;
    }
    if (tag || genre) {
      event.preventDefault();
      event.stopPropagation();
      try {
        if (tag && !track.tags.includes(tag)) updateTrack(await api.patchTrack(track.id, { tags: [...track.tags, tag] }));
        if (genre && !track.genres.includes(genre)) updateTrack(await api.patchTrack(track.id, { genres: [...track.genres, genre] }));
      } catch (e) {
        errorToast(e);
      }
      return;
    }
    if (canReorder && dragIds.length) {
      event.preventDefault();
      event.stopPropagation();
      const order = rows.map((row) => row.track.id).filter((id) => !dragIds.includes(id));
      const target = rows.slice(0, index).filter((row) => !dragIds.includes(row.track.id)).length;
      order.splice(target, 0, ...dragIds);
      await reorderPlaylist(tab, order);
    }
    dragIds = [];
  }

  /** A song dragged from the file tree onto a playlist is inserted at the drop position. */
  async function dropTreePath(path: string, index: number) {
    if (!path.toLowerCase().endsWith('.mp3')) return;
    try {
      await api.addToPlaylist(tab.path, [pathToId(path)], index);
      await loadTab(tab.key, true);
    } catch (e) {
      errorToast(e);
    }
  }

  async function onTableDrop(event: DragEvent) {
    const treePath = event.dataTransfer?.getData('application/x-dungeontuber-path');
    if (treePath && tab.type === 'playlist') {
      event.preventDefault();
      dropIndex = null;
      return dropTreePath(treePath, -1);
    }
    fileDrop = false;
    dropIndex = null;
    if (!event.dataTransfer?.types.includes('Files')) return;
    event.preventDefault();
    const items = await itemsFromDrop(event.dataTransfer);
    if (!items.length) return;
    if (tab.type === 'dir') await uploadFiles(tab.path, items);
    else {
      const dir = tab.path.slice(0, tab.path.lastIndexOf('/'));
      const tracks = await uploadFiles(dir, items);
      if (tracks.length) {
        try {
          await api.addToPlaylist(tab.path, tracks.map((tr) => tr.id));
        } catch (e) {
          errorToast(e);
        }
      }
    }
  }

  // --- header menu (column visibility) ---
  function toggleColumn(key: string) {
    prefs.columns[key] = !prefs.columns[key];
    savePrefs();
  }

  function toggleCategory(key: string) {
    prefs.hiddenCategories = prefs.hiddenCategories.includes(key) ? prefs.hiddenCategories.filter((k) => k !== key) : [...prefs.hiddenCategories, key];
    savePrefs();
  }

  function setPref<K extends 'dynamicColumns' | 'dynamicScore' | 'titleInsteadOfFile' | 'summaryUnderTitle'>(key: K) {
    prefs[key] = !prefs[key];
    savePrefs();
  }

  function startResize(event: PointerEvent, column: Column) {
    event.preventDefault();
    event.stopPropagation();
    const handle = event.currentTarget as HTMLElement;
    const startX = event.clientX;
    const startWidth = (handle.parentElement as HTMLElement).offsetWidth;
    handle.setPointerCapture(event.pointerId);
    const move = (e: PointerEvent) => (prefs.columnWidths[column.id] = Math.max(MIN_COLUMN, Math.round(startWidth + e.clientX - startX)));
    const stop = () => {
      handle.removeEventListener('pointermove', move);
      handle.removeEventListener('pointerup', stop);
      handle.removeEventListener('pointercancel', stop);
      savePrefs();
    };
    handle.addEventListener('pointermove', move);
    handle.addEventListener('pointerup', stop);
    handle.addEventListener('pointercancel', stop);
  }

  /** Keyboard alternative to dragging: the arrow keys change the width of the focused column in 10px steps. */
  function resizeByKey(event: KeyboardEvent, column: Column) {
    const step = event.key === 'ArrowRight' ? 10 : event.key === 'ArrowLeft' ? -10 : 0;
    if (!step) return;
    event.preventDefault();
    event.stopPropagation();
    const width = prefs.columnWidths[column.id] ?? (event.currentTarget as HTMLElement).parentElement!.offsetWidth;
    prefs.columnWidths[column.id] = Math.max(MIN_COLUMN, width + step);
    savePrefs();
  }

  function resetWidth(column: Column) {
    delete prefs.columnWidths[column.id];
    savePrefs();
  }

  function headerMenu(event: MouseEvent) {
    const c = prefs.columns;
    const items: MenuItem[] = [
      { label: t('Index'), checked: c.index, action: () => toggleColumn('index') },
      { label: t('Favorite'), checked: c.favorite, action: () => toggleColumn('favorite') },
      { label: t('Cover'), checked: c.cover, action: () => toggleColumn('cover') },
      { label: t('Title'), checked: c.title, disabled: prefs.titleInsteadOfFile, action: () => toggleColumn('title') },
      { label: t('Summary'), checked: c.summary, disabled: prefs.summaryUnderTitle, action: () => toggleColumn('summary') },
      { label: t('Artist'), checked: c.artist, action: () => toggleColumn('artist') },
      { label: t('Album'), checked: c.album, action: () => toggleColumn('album') },
      { label: t('Genre'), checked: c.genre, action: () => toggleColumn('genre') },
      { label: t('BPM'), checked: c.bpm, action: () => toggleColumn('bpm') },
      { label: t('Score'), checked: c.score, action: () => toggleColumn('score') },
      { label: t('Mood'), checked: c.tags, action: () => toggleColumn('tags') },
      { label: t('Duration'), checked: c.duration, action: () => toggleColumn('duration') },
      { label: t('Categories'), children: categoryKeys.map((key) => ({
        label: data.categories.find((cat) => cat.key === key)?.name ?? key, checked: !prefs.hiddenCategories.includes(key), action: () => toggleCategory(key),
      })) },
      { separator: true },
      { label: t('Dynamic Columns'), checked: prefs.dynamicColumns, action: () => setPref('dynamicColumns') },
      { label: t('Dynamic Score Column'), checked: prefs.dynamicScore, action: () => setPref('dynamicScore') },
      { label: t('Use mp3 title instead of file name'), checked: prefs.titleInsteadOfFile, action: () => setPref('titleInsteadOfFile') },
      { label: t('Display summary next to title'), checked: prefs.summaryUnderTitle, action: () => setPref('summaryUnderTitle') },
      { label: t('Row Style'), children: (['small', 'medium', 'large'] as const).map((style) => ({
        label: t(style.toUpperCase()), checked: prefs.rowStyle === style, action: () => { prefs.rowStyle = style; savePrefs(); },
      })) },
    ];
    openMenu(event, items);
  }

  // --- rendering helpers ---
  const levelClass = ['lvl-0', 'lvl-1', 'lvl-2'];

  function cellClass(track: Track, column: Column, score: number | null): string {
    if (column.id === 'score') {
      const level = scoreLevel(score);
      return level === null ? '' : `score-${level}`;
    }
    if (column.id === 'bpm') return levelClass[bpmLevel(filter.bpm, track.bpm) ?? -1] ?? '';
    if (column.id === 'genre') return levelClass[genreLevel(filter.genres, track.genres) ?? -1] ?? '';
    if (column.id.startsWith('cat:')) {
      const key = column.id.slice(4);
      return levelClass[categoryLevel(filter.categories[key], track.categories[key]) ?? -1] ?? '';
    }
    return '';
  }

  function displayName(track: Track) {
    return prefs.titleInsteadOfFile && track.title ? track.title : track.name;
  }

  /** Shows as many tag chips as fit into the column and sums up the rest as "+N" (re-fitted whenever the column is resized). */
  function fitChips(node: HTMLElement, _deps: string) {
    const fit = () => {
      const pills = [...node.querySelectorAll<HTMLElement>('.pill')];
      const more = node.querySelector<HTMLElement>('.more-tags');
      if (!more) return;
      pills.forEach((pill) => (pill.style.display = ''));
      more.style.display = 'none';
      const gap = parseFloat(getComputedStyle(node).columnGap) || 0;
      const available = node.clientWidth;
      const widths = pills.map((pill) => pill.offsetWidth);
      const sum = (count: number) => widths.slice(0, count).reduce((total, width) => total + width, 0) + gap * Math.max(0, count - 1);
      // a single chip is always shown (clipped when the column is too narrow)
      if (pills.length <= 1 || sum(pills.length) <= available) return;
      more.style.display = '';
      let shown = pills.length - 1;
      for (; shown > 1; shown--) {
        more.textContent = `+${pills.length - shown}`;
        if (sum(shown) + gap + more.offsetWidth <= available) break;
      }
      more.textContent = `+${pills.length - shown}`;
      pills.forEach((pill, index) => (pill.style.display = index < shown ? '' : 'none'));
    };
    const observer = new ResizeObserver(fit);
    observer.observe(node);
    fit();
    return { update: fit, destroy: () => observer.disconnect() };
  }

  function sortedTags(track: Track): { tag: string; match: boolean }[] {
    const tags = track.tags.map((tag) => ({ tag, match: filter.tags.includes(tag) }));
    return tags.sort((a, b) => Number(b.match) - Number(a.match));
  }

  const PILL_TONES = ['', 'gold', 'violet'];
  function tone(tag: string): string {
    let hash = 0;
    for (const ch of tag) hash = (hash * 31 + ch.charCodeAt(0)) | 0;
    return PILL_TONES[Math.abs(hash) % PILL_TONES.length];
  }

  function duration(seconds: number) {
    if (!seconds || seconds < 0) return '';
    return `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;
  }
</script>

<div class="table card" style:--row-h="{rowHeight}px" class:filedrop={fileDrop} role="grid" tabindex="0" bind:this={table} onkeydown={onKeydown}
     ondragover={(e) => { const types = e.dataTransfer?.types ?? []; if (types.includes('Files') || (tab.type === 'playlist' && types.includes('application/x-dungeontuber-path'))) { e.preventDefault(); fileDrop = true; } }}
     ondragleave={(e) => { if (e.currentTarget === e.target) fileDrop = false; }} ondrop={onTableDrop}>
  <div class="viewport" bind:this={viewport} onscroll={() => (scrollTop = viewport!.scrollTop)}>
  <div class="header" style:grid-template-columns={template} style:min-width="{minWidth}px" oncontextmenu={headerMenu} role="row" tabindex="-1">
    {#each columns as column (column.id)}
      <button class="th" class:right={column.align === 'right'} class:center={column.align === 'center'} title={column.title ?? column.label}
              onclick={() => column.sort && setSort(column.sort)}>
        {#if column.id === 'favorite'}<Icon name="heart" size={13} />{:else}<span class="ellipsis">{column.label}</span>{/if}
        {#if library.sortKey === column.sort}<span class="sort">{library.sortAsc ? '▲' : '▼'}</span>{/if}
        <span class="resize" role="slider" tabindex="0" aria-label={t('Column width')} aria-valuemin={MIN_COLUMN} aria-valuenow={prefs.columnWidths[column.id] ?? 0} title={t('Drag to resize, double-click to reset')}
              onpointerdown={(e) => startResize(e, column)} onclick={(e) => e.stopPropagation()} onkeydown={(e) => resizeByKey(e, column)} ondblclick={(e) => { e.stopPropagation(); resetWidth(column); }}></span>
      </button>
    {/each}
  </div>

    {#if tab.loading && !tab.tracks.length}
      <div class="empty muted">{t('Loading…')}</div>
    {:else if tab.error}
      <div class="empty error">{tab.error}</div>
    {:else if !rows.length}
      <div class="empty muted">{library.search ? t('No matches for "{0}"', library.search) : t('No MP3 files found.')}</div>
    {/if}
    <div class="spacer" style:height="{rows.length * rowHeight}px" style:min-width="{minWidth}px">
      {#each visible as row, i (row.track.id)}
        {@const track = row.track}
        {@const index = first + i}
        <div class="tr" class:selected={selected.has(track.id)} class:playing={player.track?.id === track.id} class:drop-above={dropIndex === index}
             style:transform="translateY({index * rowHeight}px)" style:height="{rowHeight}px" style:grid-template-columns={template}
             role="row" tabindex="-1" aria-selected={selected.has(track.id)} draggable="true"
             onclick={(e) => { select(index, e); table?.focus({ preventScroll: true }); }} onkeydown={() => {}}
             oncontextmenu={(e) => { if (!selected.has(track.id)) select(index, e); openMenu(e, trackMenu(selectedTracks())); }}
             ondragstart={(e) => onDragStart(e, track)} ondragover={(e) => onRowDragOver(e, index)} ondragleave={() => (dropIndex = null)}
             ondrop={(e) => onRowDrop(e, track, index)}>
          {#each columns as column (column.id)}
            <div class="td {cellClass(track, column, row.score)}" class:right={column.align === 'right'} class:center={column.align === 'center'}
                 role="gridcell" tabindex="-1" ondblclick={(e) => onCellDblClick(e, track, column)}>
              {#if editing && editing.id === track.id && editing.column === column.id}
                <input class="edit" type="text" bind:value={editing.value} use:focusInput onblur={commitEdit}
                       onkeydown={(e) => { e.stopPropagation(); if (e.key === 'Enter') commitEdit(); if (e.key === 'Escape') editing = null; }} />
              {:else if column.id === 'index'}
                {#if player.track?.id === track.id}<span class="now"><Icon name={player.playing ? 'volume' : 'pause'} size={14} /></span>{:else}<span class="muted">{(track.index ?? 0) + 1}</span>{/if}
              {:else if column.id === 'favorite'}
                <span class="fav" class:on={track.favorite}><Icon name="heart" size={16} filled={track.favorite} /></span>
              {:else if column.id === 'name'}
                <div class="name-cell">
                  {#if prefs.columns.cover}
                    <span class="thumb" class:playing={player.track?.id === track.id}>
                      {#if track.has_cover}<img src={coverUrl(track.id, rowHeight > 44 ? 128 : 64)} alt="" loading="lazy" />{:else}<Icon name="music" size={16} />{/if}
                      {#if player.track?.id === track.id}<span class="thumb-play"><Icon name={player.playing ? 'volume' : 'play'} size={14} /></span>{/if}
                    </span>
                  {/if}
                  <div class="texts">
                    <span class="title-text ellipsis">{displayName(track)}</span>
                    {#if prefs.rowStyle !== 'small'}
                      <span class="sub ellipsis">{prefs.summaryUnderTitle && track.summary ? track.summary : track.artist || track.album || ''}</span>
                    {/if}
                  </div>
                  {#if track.light?.color}<span class="bulb" style:color={track.light.color} title={t('Lights')}><Icon name="bulb" size={15} filled /></span>{/if}
                  {#if track.chapters.length}<span class="muted" title={t('Chapters')}><Icon name="marker" size={14} /></span>{/if}
                </div>
              {:else if column.id === 'mood'}
                <div class="tags" use:fitChips={track.tags.join('|') + '#' + filter.tags.join('|')}>
                  {#each sortedTags(track) as { tag, match } (tag)}<span class="pill {match ? 'match' : tone(tag)}">{tag}</span>{/each}
                  <span class="more-tags" title={track.tags.join(', ')}></span>
                </div>
              {:else if column.id === 'duration'}
                <span class="muted num">{duration(track.length)}</span>
              {:else if column.id === 'title'}
                <span class="ellipsis">{track.title ?? ''}</span>
              {:else if column.id === 'summary'}
                <span class="ellipsis muted">{track.summary}</span>
              {:else if column.id === 'artist'}
                <span class="ellipsis">{track.artist ?? ''}</span>
              {:else if column.id === 'album'}
                <span class="ellipsis">{track.album ?? ''}</span>
              {:else if column.id === 'genre'}
                <span class="ellipsis">{track.genres.join(', ')}</span>
              {:else if column.id === 'bpm'}
                {track.bpm ?? ''}
              {:else if column.id === 'score'}
                {#if row.score !== null}<span class="score" title={t('Distance: {0}', row.score)}>{scorePercent(row.score)}%</span>{/if}
              {:else}
                {@const value = track.categories[column.id.slice(4)]}
                {#if value !== undefined && value !== null}
                  <div class="bar-cell"><div class="bar"><div class="fill" style:width="{Math.min(100, Number(value) * 10)}%"></div></div><span class="num">{Number.isInteger(value) ? value : Number(value).toFixed(1)}</span></div>
                {/if}
              {/if}
            </div>
          {/each}
        </div>
      {/each}
    </div>
  </div>

  {#if library.search}
    <div class="search-pill" class:none={!rows.length}><Icon name="search" size={13} /> {library.search}</div>
  {/if}
  <div class="footer muted">{rows.length} / {tab.tracks.length} · {t('{0} selected', library.selection.length)}</div>
</div>

<style>
  .table { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; position: relative; overflow: hidden; margin-right: 2px; }
  .table:focus { outline: none; }
  .table.filedrop { box-shadow: inset 0 0 0 2px var(--accent); }
  .header { display: grid; background: var(--surface); position: sticky; top: 0; z-index: 2; border-bottom: 1px solid var(--border); }
  .th { display: flex; align-items: center; gap: 4px; padding: 12px 10px 10px; font-size: var(--fs-xs); font-weight: 650; letter-spacing: 0.05em; text-transform: uppercase; color: var(--faint); text-align: left; min-width: 0; }
  .th { position: relative; }
  .th:hover { color: var(--text); }
  .resize { position: absolute; top: 0; bottom: 0; right: -5px; width: 10px; cursor: col-resize; z-index: 3; touch-action: none; }
  .resize::after { content: ''; position: absolute; top: 25%; bottom: 25%; left: 4px; width: 2px; border-radius: 1px; background: var(--border-strong); opacity: 0; transition: opacity 0.12s; }
  .th:hover .resize::after, .resize:hover::after { opacity: 1; }
  .th.right { justify-content: flex-end; }
  .th.center { justify-content: center; }
  .sort { font-size: 8px; color: var(--accent); }
  .viewport { flex: 1; overflow: auto; position: relative; padding: 0 6px; }
  .spacer { position: relative; min-width: 100%; }
  .tr { position: absolute; left: 0; right: 0; top: 0; display: grid; align-items: center; cursor: default; border-radius: 10px; transition: background 0.12s; }
  .tr:hover { background: var(--hover); }
  .tr.selected { background: var(--accent-soft); }
  .tr.playing { background: linear-gradient(90deg, rgba(var(--ambient), 0.22), transparent 75%); }
  .tr.playing.selected { background: linear-gradient(90deg, rgba(var(--ambient), 0.26), var(--accent-soft) 75%); }
  .tr.drop-above { box-shadow: inset 0 2px 0 var(--accent); }
  .td { padding: 0 10px; min-width: 0; height: 100%; display: flex; align-items: center; overflow: hidden; }
  .td.right { justify-content: flex-end; }
  .td.center { justify-content: center; }
  .td.lvl-0 .num, .td.lvl-0 > span { color: var(--green); font-weight: 600; }
  .td.lvl-1 .num, .td.lvl-1 > span { color: var(--gold); font-weight: 600; }
  .td.lvl-2 .num, .td.lvl-2 > span { color: var(--red); font-weight: 600; }
  .td.lvl-0 .fill { background: var(--green); }
  .td.lvl-1 .fill { background: var(--gold); }
  .td.lvl-2 .fill { background: var(--red); }
  .score { font-weight: 700; font-variant-numeric: tabular-nums; padding: 2px 9px; border-radius: 7px; }
  .td.score-0 .score { color: var(--score-0); background: color-mix(in srgb, var(--score-0) 16%, transparent); }
  .td.score-1 .score { color: var(--score-1); background: color-mix(in srgb, var(--score-1) 16%, transparent); }
  .td.score-2 .score { color: var(--score-2); background: color-mix(in srgb, var(--score-2) 16%, transparent); }
  .td.score-3 .score { color: var(--score-3); background: color-mix(in srgb, var(--score-3) 16%, transparent); }
  .num { font-variant-numeric: tabular-nums; font-size: var(--fs-sm); }
  .now { color: var(--accent); display: flex; }
  .fav { color: var(--faint); display: flex; opacity: 0.5; }
  .tr:hover .fav { opacity: 1; }
  .fav.on { color: var(--rose); opacity: 1; filter: drop-shadow(0 0 6px var(--rose-soft)); }
  .name-cell { display: flex; align-items: center; gap: 12px; width: 100%; min-width: 0; }
  .thumb { position: relative; width: calc(var(--row-h) - 14px); height: calc(var(--row-h) - 14px); border-radius: 8px; overflow: hidden; flex: none; background: var(--surface-3); display: grid; place-items: center; color: var(--faint); }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .thumb.playing { box-shadow: 0 0 0 2px var(--accent), 0 0 14px var(--accent-glow); }
  .thumb-play { position: absolute; inset: 0; display: grid; place-items: center; background: rgba(10, 8, 20, 0.5); color: #fff; }
  .texts { display: flex; flex-direction: column; min-width: 0; flex: 1; gap: 1px; }
  .title-text { font-weight: 600; }
  .sub { font-size: var(--fs-xs); color: var(--muted); }
  .tags { display: flex; flex: 1; gap: 5px; min-width: 0; overflow: hidden; align-items: center; }
  .more-tags { font-size: var(--fs-xs); color: var(--faint); flex: none; white-space: nowrap; }
  .bulb { display: flex; filter: drop-shadow(0 0 4px currentColor); }
  .bar-cell { display: flex; align-items: center; gap: 8px; width: 100%; }
  .bar { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .bar .fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
  .bar-cell .num { width: 22px; text-align: right; color: var(--muted); }
  .edit { width: 100%; padding: 4px 7px; }
  .empty { padding: 40px; text-align: center; position: absolute; left: 0; right: 0; top: 44px; }
  .error { color: var(--red); }
  .search-pill { position: absolute; top: 50px; right: 18px; padding: 5px 12px; border-radius: 10px; background: var(--surface); border: 1px solid var(--accent); box-shadow: var(--shadow); display: flex; align-items: center; gap: 6px; }
  .search-pill.none { border-color: var(--red); }
  .footer { padding: 7px 16px; font-size: var(--fs-xs); border-top: 1px solid var(--border); }
</style>
