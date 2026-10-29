<script lang="ts">
  import { appMenu } from '../lib/menus';
  import { t } from '../lib/i18n.svelte';
  import { assistant, toggleAssistant } from '../lib/stores/assistant.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { prefs } from '../lib/prefs.svelte';
  import { searchBlocks } from '../lib/adventures';
  import { searchTerms } from '../lib/highlight';
  import { adventures, goToBlock } from '../lib/stores/adventure.svelte';
  import { activeTab, library, setGlobal } from '../lib/stores/library.svelte';
  import { openMenu, ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';
  import Tabs from './Tabs.svelte';

  // the assistant button shows its label while the open tabs leave enough room, otherwise only its icon
  const TAB_ROOM = 160; // width a tab should keep before the label gives way
  const ICON_ONLY = 36;
  // the side panel holds the lights and the effects; without either there is nothing to open
  const hasSidePanel = $derived(prefs.showEffects || (prefs.showLights && data.settings?.lightsEnabled !== false));
  let areaWidth = $state(0);
  let buttonWidth = $state(0);
  let labelRoom = $state(110); // width the label adds to the button, measured while it is shown
  const showLabel = $derived.by(() => {
    if (ui.narrow) return false;
    // the room the tabs would have with the icon only button, so showing the label does not change the decision
    const room = areaWidth + Math.max(0, buttonWidth - ICON_ONLY);
    return room - labelRoom >= Math.max(1, library.tabs.length) * TAB_ROOM;
  });
  $effect(() => {
    if (showLabel && buttonWidth > ICON_ONLY) labelRoom = buttonWidth - ICON_ONLY;
  });

  // --- the search of an open adventure: its blocks instead of songs
  const openAdventure = $derived(!library.global && !library.duplicates && activeTab()?.type === 'adventure' ? adventures.current : null);
  let blockQuery = $state('');
  let hitsOpen = $state(false);
  let hitIndex = $state(0);
  const hits = $derived(openAdventure ? searchBlocks(openAdventure.blocks, blockQuery, 12) : []);
  const showHits = $derived(hitsOpen && !!blockQuery.trim());

  // another adventure starts with an empty search
  $effect(() => {
    void openAdventure?.id;
    blockQuery = '';
  });

  function go(id: string) {
    goToBlock(id, searchTerms(blockQuery));
    blockQuery = '';
    hitsOpen = false;
    (document.activeElement as HTMLElement | null)?.blur();
  }

  function hitKey(event: KeyboardEvent) {
    if (event.key === 'Escape') {
      blockQuery = '';
      hitsOpen = false;
    } else if (!showHits || !hits.length) {
      return;
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      hitIndex = (hitIndex + (event.key === 'ArrowDown' ? 1 : hits.length - 1)) % hits.length;
    } else if (event.key === 'Enter') {
      event.preventDefault();
      go(hits[Math.min(hitIndex, hits.length - 1)].block.id);
    }
  }

  function showMenu(event: MouseEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    event.stopPropagation();
    openMenu({ clientX: rect.right - 240, clientY: rect.bottom + 6 }, appMenu());
  }
</script>

<header class="topbar">
  {#if ui.narrow}
    <button class="icon-btn" title={t('Library')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'tree' ? null : 'tree'; }}><Icon name="library" size={18} /></button>
  {/if}
  <div class="tabs-area" data-tour="tabs" bind:clientWidth={areaWidth}>
    {#if library.tabs.length}<Tabs />{:else}<span class="hint muted">{t('Welcome to Dungeon Tuber')}</span>{/if}
  </div>
  {#if openAdventure}
    <!-- while an adventure is open the box searches its blocks: the hits open in a list below it -->
    <div class="search-wrap">
      <label class="search" class:active={!!blockQuery}>
        <Icon name="search" size={15} />
        <input type="search" placeholder={t('Search the blocks…')} bind:value={blockQuery} aria-label={t('Search the blocks…')}
               role="combobox" aria-expanded={showHits} aria-controls="block-hits" aria-autocomplete="list"
               onfocus={() => (hitsOpen = true)} onblur={() => setTimeout(() => (hitsOpen = false), 150)}
               oninput={() => { hitsOpen = true; hitIndex = 0; }} onkeydown={hitKey} />
      </label>
      {#if showHits}
        <ul class="hits" id="block-hits" role="listbox" aria-label={t('Blocks')}>
          {#each hits as hit, index (hit.block.id)}
            <li role="option" aria-selected={index === hitIndex} class:on={index === hitIndex}>
              <button type="button" onpointerdown={(e) => { e.preventDefault(); go(hit.block.id); }} onpointerenter={() => (hitIndex = index)}>
                <span class="hit-title ellipsis">{hit.block.title || t('Untitled')}</span>
                <span class="hit-text">{hit.before}{#if hit.match}<mark>{hit.match}</mark>{/if}{hit.after}</span>
              </button>
            </li>
          {:else}
            <li class="none muted">{t('No block fits "{0}".', blockQuery.trim())}</li>
          {/each}
        </ul>
      {/if}
    </div>
  {:else}
    <label class="search" class:active={!!library.search} data-tour="search">
      <Icon name="search" size={15} />
      <input type="search" placeholder={library.global ? t('Search the whole library…') : t('Search tracks…')} bind:value={library.search} />
    </label>
  {/if}
  <button class="mode" class:explore={library.global} role="switch" aria-checked={library.global} aria-label={t('Browse or explore')} data-tour="global-search"
          title={library.global ? t('Explore: the best {0} songs of the whole library. Click to browse the open tab again.', 50)
                                : t('Browse: search the open tab. Click to explore the whole library instead.')}
          onclick={() => void setGlobal(!library.global)}>
    <span class="thumb"></span>
    <span class="opt" class:on={!library.global}>{t('Browse')}</span>
    <span class="opt" class:on={library.global}>{t('Explore')}</span>
  </button>
  {#if data.settings?.assistantConfigured || data.settings?.groqConfigured || data.settings?.musicGenConfigured || data.settings?.soundGenConfigured || data.auth?.is_admin !== false}
    <button class="assistant" class:active={assistant.open} class:labelled={showLabel} title={t('AI Assistant')} aria-label={t('AI Assistant')} aria-pressed={assistant.open}
            data-tour="assistant" bind:clientWidth={buttonWidth} onclick={toggleAssistant}>
      <Icon name="sparkles" size={17} />{#if showLabel}<span>{t('AI Assistant')}</span>{/if}
    </button>
  {/if}
  <button class="icon-btn" title={t('Menu')} data-tour="menubar" onclick={showMenu}><Icon name="menu" size={18} /></button>
  <!-- tablets: the panel opens over the page (the library beside it stays); phones: the same with the bulb -->
  {#if ui.rightOverlay && !ui.narrow && hasSidePanel}
    <button class="icon-btn" class:active={ui.mobilePanel === 'side'} title={ui.mobilePanel === 'side' ? t('Hide effects and lights') : t('Show effects and lights')} aria-label={t('Effects and lights')}
            aria-pressed={ui.mobilePanel === 'side'} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'side' ? null : 'side'; }}><Icon name="panel-right" size={18} /></button>
  {/if}
  {#if ui.narrow && hasSidePanel}
    <button class="icon-btn" title={t('Lights')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'side' ? null : 'side'; }}><Icon name="bulb" size={18} /></button>
  {/if}
</header>

<style>
  .topbar { display: flex; align-items: center; gap: 10px; min-height: 40px; padding-right: 2px; }
  .tabs-area { flex: 1; min-width: 0; }
  .hint { font-size: var(--fs-sm); padding-left: 4px; }
  /* icon only until it is clicked (or while it holds a query), then it grows */
  .search { display: flex; align-items: center; height: 36px; width: 36px; padding: 0 10px; box-sizing: border-box; flex: none; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); color: var(--faint); cursor: text; overflow: hidden; transition: width 0.2s ease, border-color 0.15s, box-shadow 0.15s; }
  .search:hover { color: var(--text); }
  .search:focus-within, .search.active { width: min(280px, 34vw); }
  .search:focus-within, .search.active { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); color: var(--accent); }
  .search input { border: none; background: none; padding: 0; width: 0; flex: 1; min-width: 0; margin-left: 0; opacity: 0; color: var(--text); transition: opacity 0.15s, margin-left 0.2s; }
  .search:focus-within input, .search.active input { margin-left: 8px; opacity: 1; }
  .search input:focus { box-shadow: none; }
  .search-wrap { position: relative; flex: none; }
  .hits { position: absolute; right: 0; top: calc(100% + 6px); z-index: 60; width: min(380px, 90vw); max-height: min(60vh, 460px); overflow-y: auto; margin: 0; padding: 4px; list-style: none;
          border-radius: 12px; background: var(--bg-2); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow); }
  .hits button { display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 7px 10px; border-radius: 8px; text-align: left; color: var(--text); }
  .hits li.on button { background: var(--accent-soft); }
  .hit-title { font-weight: 600; }
  .hit-text { font-size: var(--fs-xs); line-height: 1.4; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .hit-text mark { background: var(--accent-soft); color: var(--accent); border-radius: 3px; padding: 0 1px; }
  .hits .none { padding: 8px 10px; font-size: var(--fs-sm); }
  /* iOS style switch: the thumb slides under the label of the active mode */
  .mode { position: relative; display: grid; grid-template-columns: 1fr 1fr; align-items: center; flex: none; height: 36px; padding: 3px; box-sizing: border-box; border-radius: 999px; background: var(--surface); border: 1px solid var(--border); font: inherit; font-size: var(--fs-sm); font-weight: 600; cursor: pointer; transition: border-color 0.15s; }
  .mode:hover { border-color: var(--border-strong); }
  .mode:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
  .thumb { position: absolute; top: 3px; bottom: 3px; left: 3px; width: calc(50% - 3px); border-radius: 999px; background: var(--accent); box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3); transition: transform 0.22s cubic-bezier(0.3, 0.7, 0.4, 1); }
  .mode.explore .thumb { transform: translateX(100%); }
  .opt { position: relative; padding: 0 10px; text-align: center; white-space: nowrap; color: var(--muted); transition: color 0.2s; }
  .opt.on { color: var(--accent-text); }
  .assistant { display: flex; align-items: center; justify-content: center; gap: 7px; flex: none; height: 36px; min-width: 36px; padding: 0 9px; box-sizing: border-box; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); color: var(--muted); font: inherit; font-size: var(--fs-sm); font-weight: 600; white-space: nowrap; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
  .assistant.labelled { padding: 0 12px 0 10px; }
  .assistant:hover { color: var(--text); border-color: var(--border-strong); }
  .assistant.active { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
  /* phones: the fixed size controls no longer fit next to the tabs, so the tabs get their own row */
  @media (max-width: 480px) {
    .topbar { flex-wrap: wrap; gap: 4px; }
    .icon-btn { min-width: 34px; min-height: 36px; padding-inline: 0; } /* the touch size of 40px would push the last button onto a line of its own */
    .search { width: 34px; padding: 0 9px; }
    .assistant { min-width: 34px; padding: 0 8px; }
    .tabs-area { order: 10; flex: 1 0 100%; }
    .tabs-area:has(.hint) { display: none; } /* only the welcome hint, no tabs */
    .mode { font-size: var(--fs-xs); }
    .opt { padding: 0 6px; }
    .search, .search-wrap { margin-left: auto; }
    .search-wrap .search { margin-left: 0; }
    /* an open search takes the free space of the row: the mode switch and the assistant step aside
       (the block search of an adventure sits in a wrapper, which grows instead) */
    .search:focus-within, .search.active { flex: 1; width: auto; min-width: 0; margin-left: 0; }
    .search-wrap:has(.search:focus-within), .search-wrap:has(.search.active) { flex: 1; display: flex; min-width: 0; margin-left: 0; }
    .topbar:has(.search:focus-within) :is(.mode, .assistant), .topbar:has(.search.active) :is(.mode, .assistant) { display: none; }
  }
  /* the narrowest phones: the controls (library, search, mode switch, assistant, menu, lights) still have to share one line */
  @media (max-width: 360px) {
    .topbar { gap: 3px; }
    .icon-btn, .search, .assistant { min-width: 32px; }
    .search { width: 32px; padding: 0 8px; }
    .opt { padding: 0 4px; }
  }
</style>
