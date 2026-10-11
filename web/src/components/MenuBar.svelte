<script lang="ts">
  import { appMenu } from '../lib/menus';
  import { t } from '../lib/i18n.svelte';
  import { assistant, toggleAssistant } from '../lib/stores/assistant.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { library, setGlobal } from '../lib/stores/library.svelte';
  import { openMenu, ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';
  import Tabs from './Tabs.svelte';

  // the assistant button shows its label while the open tabs leave enough room, otherwise only its icon
  const TAB_ROOM = 160; // width a tab should keep before the label gives way
  const ICON_ONLY = 36;
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

  function showMenu(event: MouseEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    event.stopPropagation();
    openMenu({ clientX: rect.right - 240, clientY: rect.bottom + 6 }, appMenu());
  }
</script>

<header class="topbar">
  {#if ui.narrow}
    <button class="icon-btn" title={t('Files')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'tree' ? null : 'tree'; }}><Icon name="library" size={18} /></button>
  {/if}
  <div class="tabs-area" data-tour="tabs" bind:clientWidth={areaWidth}>
    {#if library.tabs.length}<Tabs />{:else}<span class="hint muted">{t('Welcome to Dungeon Tuber')}</span>{/if}
  </div>
  <label class="search" class:active={library.search || library.global} data-tour="search">
    <Icon name="search" size={15} />
    <input type="search" placeholder={library.global ? t('Search the whole library…') : t('Search tracks…')} bind:value={library.search} />
  </label>
  <button class="icon-btn global" class:active={library.global} aria-pressed={library.global} data-tour="global-search"
          title={library.global ? t('Global search: the best {0} songs of the whole library. Click to search the open tab again.', 50)
                                : t('Search the whole library instead of the open tab')}
          onclick={() => void setGlobal(!library.global)}><Icon name="globe" size={17} /></button>
  {#if data.settings?.assistantConfigured || data.auth?.is_admin !== false}
    <button class="assistant" class:active={assistant.open} class:labelled={showLabel} title={t('AI Assistant')} aria-label={t('AI Assistant')} aria-pressed={assistant.open}
            data-tour="assistant" bind:clientWidth={buttonWidth} onclick={toggleAssistant}>
      <Icon name="sparkles" size={17} />{#if showLabel}<span>{t('AI Assistant')}</span>{/if}
    </button>
  {/if}
  <button class="icon-btn" title={t('Menu')} data-tour="menubar" onclick={showMenu}><Icon name="menu" size={18} /></button>
  {#if ui.narrow}
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
  .global { width: 36px; height: 36px; border-radius: 10px; border: 1px solid transparent; }
  .global.active { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
  .assistant { display: flex; align-items: center; justify-content: center; gap: 7px; flex: none; height: 36px; min-width: 36px; padding: 0 9px; box-sizing: border-box; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); color: var(--muted); font: inherit; font-size: var(--fs-sm); font-weight: 600; white-space: nowrap; cursor: pointer; transition: border-color 0.15s, color 0.15s, background 0.15s; }
  .assistant.labelled { padding: 0 12px 0 10px; }
  .assistant:hover { color: var(--text); border-color: var(--border-strong); }
  .assistant.active { color: var(--accent); background: var(--accent-soft); border-color: var(--accent); }
</style>
