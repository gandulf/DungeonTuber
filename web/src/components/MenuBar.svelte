<script lang="ts">
  import { appMenu } from '../lib/menus';
  import { t } from '../lib/i18n.svelte';
  import { library } from '../lib/stores/library.svelte';
  import { openMenu, ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';
  import Tabs from './Tabs.svelte';

  function showMenu(event: MouseEvent) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    event.stopPropagation();
    openMenu({ clientX: rect.right - 240, clientY: rect.bottom + 6 }, appMenu());
  }
</script>

<header class="topbar" data-tour="menubar">
  {#if ui.narrow}
    <button class="icon-btn" title={t('Files')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'tree' ? null : 'tree'; }}><Icon name="library" size={18} /></button>
  {/if}
  <div class="tabs-area">
    {#if library.tabs.length}<Tabs />{:else}<span class="hint muted">{t('Welcome to Dungeon Tuber')}</span>{/if}
  </div>
  <label class="search" class:active={library.search}>
    <Icon name="search" size={15} />
    <input type="search" placeholder={t('Search tracks…')} bind:value={library.search} />
  </label>
  <button class="icon-btn" title={t('Menu')} onclick={showMenu}><Icon name="menu" size={18} /></button>
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
</style>
