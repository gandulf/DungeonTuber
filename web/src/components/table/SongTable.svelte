<script lang="ts">
  import { api, coverUrl, pathToId } from '../../lib/api';
  import { toggleFavorite, trackMenu, uploadFiles } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { bpmLevel, categoryLevel, emptyFilter, genreLevel, scoreLevel } from '../../lib/scoring';
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

  const ROW_HEIGHT = { small: 30, medium: 44, large: 62 } as const;
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
    if (c.cover) list.push({ id: 'cover', label: '', width: `${Math.round(rowHeight * 1.33)}px`, title: t('Cover') });
    list.push({ id: 'name', label: prefs.titleInsteadOfFile ? t('Title') : t('Name'), width: 'minmax(260px, 1fr)', sort: 'name', edit: prefs.titleInsteadOfFile ? 'text' : undefined });
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
      list.push({ id: `cat:${key}`, label: category?.name ?? key, width: '88px', sort: `cat:${key}`, edit: 'category', title: category?.description });
    }
    return list;
  });

  const template = $derived(columns.map((col) => col.width).join(' '));
  // minimum row width so the header and rows scroll horizontally together
  const minWidth = $derived(columns.reduce((sum, col) => sum + (parseInt(col.width.replace('minmax(', ''), 10) || 0), 0));

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
    anchor = null;
  });

  // --- selection ---
  let anchor: number | null = null;
  const selected = $derived(new Set(library.selection));

  function select(index: number, event: MouseEvent | KeyboardEvent) {
    const id = rows[index]?.track.id;
    if (!id) return;
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
  }

  // when a filter is set the best match is selected (like the desktop app)
  $effect(() => {
    if (filterActive && library.sortKey === 'score' && rows.length) {
      const best = rows[0].track.id;
      if (library.selection[0] !== best) {
        library.selection = [best];
        anchor = 0;
        if (viewport) viewport.scrollTop = 0;
      }
    }
  });

  // --- keyboard (navigation, type-to-search) ---
  function onKeydown(event: KeyboardEvent) {
    if (editing) return;
    const current = anchor ?? -1;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const target = Math.max(0, Math.min(rows.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)));
      select(target, event);
      scrollIntoView(target);
    } else if (event.key === 'PageDown' || event.key === 'PageUp') {
      event.preventDefault();
      const step = Math.floor(viewportHeight / rowHeight);
      const target = Math.max(0, Math.min(rows.length - 1, current + (event.key === 'PageDown' ? step : -step)));
      select(target, event);
      scrollIntoView(target);
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
    if (column.id === 'cover') {
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
    if (types.includes('application/x-dungeontuber-tag') || (canReorder && types.includes('application/x-dungeontuber-tracks'))
        || (tab.type === 'playlist' && types.includes('application/x-dungeontuber-path'))) {
      event.preventDefault();
      dropIndex = index;
    }
  }

  async function onRowDrop(event: DragEvent, track: Track, index: number) {
    const tag = event.dataTransfer?.getData('application/x-dungeontuber-tag');
    const treePath = event.dataTransfer?.getData('application/x-dungeontuber-path');
    dropIndex = null;
    if (treePath && tab.type === 'playlist') {
      event.preventDefault();
      event.stopPropagation();
      await dropTreePath(treePath, index);
      return;
    }
    if (tag) {
      event.preventDefault();
      event.stopPropagation();
      if (track.tags.includes(tag)) return;
      try {
        const updated = await api.patchTrack(track.id, { tags: [...track.tags, tag] });
        updateTrack(updated);
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
    const files = [...(event.dataTransfer?.files ?? [])];
    if (!files.length) return;
    event.preventDefault();
    if (tab.type === 'dir') await uploadFiles(tab.path, files);
    else {
      const dir = tab.path.slice(0, tab.path.lastIndexOf('/'));
      try {
        const result = await api.upload(dir, files.filter((f) => f.name.toLowerCase().endsWith('.mp3')));
        await api.addToPlaylist(tab.path, result.tracks.map((tr) => tr.id));
      } catch (e) {
        errorToast(e);
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
      { label: t('Tags'), checked: c.tags, action: () => toggleColumn('tags') },
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

  function sortedTags(track: Track): { tag: string; match: boolean }[] {
    const tags = track.tags.map((tag) => ({ tag, match: filter.tags.includes(tag) }));
    return tags.sort((a, b) => Number(b.match) - Number(a.match));
  }
</script>

<div class="table panel" class:filedrop={fileDrop} role="grid" tabindex="0" onkeydown={onKeydown}
     ondragover={(e) => { const types = e.dataTransfer?.types ?? []; if (types.includes('Files') || (tab.type === 'playlist' && types.includes('application/x-dungeontuber-path'))) { e.preventDefault(); fileDrop = true; } }}
     ondragleave={(e) => { if (e.currentTarget === e.target) fileDrop = false; }} ondrop={onTableDrop}>
  <div class="viewport" bind:this={viewport} onscroll={() => (scrollTop = viewport!.scrollTop)}>
  <div class="header" style:grid-template-columns={template} style:min-width="{minWidth}px" oncontextmenu={headerMenu} role="row" tabindex="-1">
    {#each columns as column (column.id)}
      <button class="th" class:right={column.align === 'right'} class:center={column.align === 'center'} title={column.title ?? column.label}
              onclick={() => column.sort && setSort(column.sort)}>
        {#if column.id === 'favorite'}<Icon name="star" size={13} />{:else if column.id === 'cover'}<Icon name="image" size={13} />{:else}<span class="ellipsis">{column.label}</span>{/if}
        {#if library.sortKey === column.sort}<span class="sort">{library.sortAsc ? '▲' : '▼'}</span>{/if}
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
             onclick={(e) => select(index, e)} onkeydown={() => {}}
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
                <span class="muted">{(track.index ?? 0) + 1}</span>
              {:else if column.id === 'favorite'}
                <span class="fav" class:on={track.favorite}><Icon name="star" size={15} filled={track.favorite} /></span>
              {:else if column.id === 'cover'}
                {#if track.has_cover}<img class="cover" src={coverUrl(track.id, rowHeight > 40 ? 128 : 64)} alt="" loading="lazy" />{/if}
              {:else if column.id === 'name'}
                <div class="name-cell">
                  <div class="texts">
                    <span class="title-text ellipsis">
                      {#if player.track?.id === track.id}<span class="now"><Icon name={player.playing ? 'volume' : 'pause'} size={13} /></span>{/if}
                      {displayName(track)}
                    </span>
                    {#if prefs.summaryUnderTitle && track.summary && prefs.rowStyle !== 'small'}<span class="summary ellipsis">{track.summary}</span>{/if}
                  </div>
                  {#if prefs.columns.tags && track.tags.length}
                    <div class="tags">
                      {#each sortedTags(track).slice(0, 4) as { tag, match } (tag)}<span class="pill" class:match>{tag}</span>{/each}
                    </div>
                  {/if}
                  {#if track.light?.color}<span class="bulb" style:color={track.light.color} title={t('Lights')}><Icon name="bulb" size={15} filled /></span>{/if}
                  {#if track.chapters.length}<span class="muted" title={t('Chapters')}><Icon name="marker" size={14} /></span>{/if}
                </div>
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
                <strong>{row.score ?? ''}</strong>
              {:else}
                {@const value = track.categories[column.id.slice(4)]}
                {#if value !== undefined && value !== null}
                  <div class="bar"><div class="fill" style:width="{Math.min(100, Number(value) * 10)}%"></div><span>{Number.isInteger(value) ? value : Number(value).toFixed(1)}</span></div>
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
  .table { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; position: relative; overflow: hidden; border-top-left-radius: 0; border-top-right-radius: 0; border-top: none; }
  .table:focus { outline: none; }
  .table.filedrop { box-shadow: inset 0 0 0 2px var(--accent); }
  .header { display: grid; border-bottom: 1px solid var(--border); background: var(--surface); position: sticky; top: 0; z-index: 2; }
  .th { display: flex; align-items: center; gap: 4px; padding: 8px 8px; font-size: var(--fs-sm); font-weight: 600; color: var(--muted); text-align: left; min-width: 0; }
  .th:hover { color: var(--text); background: var(--hover); }
  .th.right { justify-content: flex-end; }
  .th.center { justify-content: center; }
  .sort { font-size: 9px; }
  .viewport { flex: 1; overflow: auto; position: relative; }
  .spacer { position: relative; min-width: 100%; }
  .tr { position: absolute; left: 0; right: 0; top: 0; display: grid; align-items: center; border-bottom: 1px solid color-mix(in srgb, var(--border) 50%, transparent); cursor: default; }
  .tr:hover { background: var(--hover); }
  .tr.selected { background: var(--accent-soft); }
  .tr.playing { box-shadow: inset 3px 0 0 var(--accent); }
  .tr.drop-above { box-shadow: inset 0 2px 0 var(--accent); }
  .td { padding: 0 8px; min-width: 0; height: 100%; display: flex; align-items: center; overflow: hidden; }
  .td.right { justify-content: flex-end; }
  .td.center { justify-content: center; }
  .td.lvl-0 { background: var(--green-soft); }
  .td.lvl-1 { background: var(--orange-soft); }
  .td.lvl-2 { background: var(--red-soft); }
  .td.score-0 { background: var(--score-0); }
  .td.score-1 { background: var(--score-1); }
  .td.score-2 { background: var(--score-2); }
  .td.score-3 { background: var(--score-3); }
  .cover { width: 100%; height: 100%; object-fit: cover; display: block; }
  .td:has(.cover) { padding: 0; }
  .fav { color: var(--border-strong); display: flex; }
  .fav.on { color: #f5b400; }
  .name-cell { display: flex; align-items: center; gap: 8px; width: 100%; min-width: 0; }
  .texts { display: flex; flex-direction: column; min-width: 0; flex: 1; }
  .title-text { font-weight: 600; display: flex; align-items: center; gap: 5px; }
  .now { color: var(--accent); display: inline-flex; }
  .summary { font-size: var(--fs-xs); color: var(--muted); }
  .tags { display: flex; gap: 4px; flex: none; max-width: 45%; overflow: hidden; }
  .bulb { display: flex; }
  .bar { position: relative; width: 100%; height: 18px; border-radius: 4px; background: var(--surface-3); overflow: hidden; display: flex; align-items: center; justify-content: center; font-size: var(--fs-xs); font-variant-numeric: tabular-nums; }
  .bar .fill { position: absolute; left: 0; top: 0; bottom: 0; background: color-mix(in srgb, var(--accent) 35%, transparent); }
  .bar span { position: relative; }
  .edit { width: 100%; padding: 3px 6px; }
  .empty { padding: 40px; text-align: center; position: absolute; left: 0; right: 0; top: 40px; }
  .error { color: var(--red); }
  .search-pill { position: absolute; top: 44px; right: 18px; padding: 4px 10px; border-radius: 14px; background: var(--surface); border: 1px solid var(--accent); box-shadow: var(--shadow); display: flex; align-items: center; gap: 5px; }
  .search-pill.none { border-color: var(--red); }
  .footer { padding: 4px 10px; font-size: var(--fs-xs); border-top: 1px solid var(--border); }
</style>
