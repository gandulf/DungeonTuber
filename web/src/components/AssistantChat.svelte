<script lang="ts">
  import { tick } from 'svelte';
  import { t } from '../lib/i18n.svelte';
  import { markdown } from '../lib/markdown';
  import { ask, assistant, currentChat, moreSongs, newChat, setMode, SONGS_PER_ANSWER, youtubeSearchUrl, type AssistantMode } from '../lib/stores/assistant.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { activeTab, findsInTab, library } from '../lib/stores/library.svelte';
  import { songQueries } from '../lib/search';
  import { openDialog } from '../lib/stores/ui.svelte';
  import type { AssistantSong } from '../lib/types';
  import SettingsDialog from './dialogs/SettingsDialog.svelte';
  import Icon from './Icon.svelte';

  const EXAMPLES: Record<AssistantMode, string[]> = {
    music: ['A brawl in a crowded tavern', 'Exploring a haunted crypt', 'The final fight against a dragon', 'A sad farewell at a funeral'],
    general: ['How does an attack work?', 'A name and a short description for a dwarven innkeeper', 'Three plot hooks for a village festival'],
  };
  const MODES: [AssistantMode, string, string][] = [['music', 'Music', 'music'], ['general', 'General', 'mask']];

  let text = $state('');
  let input = $state<HTMLTextAreaElement | null>(null);
  let log = $state<HTMLElement | null>(null);
  const configured = $derived(data.settings?.assistantConfigured === true);
  const admin = $derived(data.auth?.is_admin !== false);
  const chat = $derived(currentChat());
  const music = $derived(assistant.mode === 'music');
  const lastTurn = $derived(chat.turns.at(-1));

  $effect(() => {
    void chat.turns.length;
    void chat.busy;
    void tick().then(() => log?.scrollTo({ top: log.scrollHeight, behavior: 'smooth' }));
  });

  $effect(() => {
    void assistant.mode;
    if (configured) input?.focus();
  });

  function send(question = text) {
    if (!question.trim() || chat.busy) return;
    text = '';
    void ask(question);
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }

  /** The query that finds the song in the open tab (filler words left out), or null when the tab does not have it. */
  const localQueries = $derived.by(() => {
    void activeTab()?.tracks;
    const found = new Map<string, string | null>();
    for (const turn of chat.turns) {
      if (turn.role !== 'assistant') continue;
      for (const song of turn.songs) {
        if (!found.has(song.title)) found.set(song.title, songQueries(song.title).find((query) => findsInTab(query)) ?? null);
      }
    }
    return found;
  });

  function searchLibrary(query: string) {
    library.search = query;
  }

  function openSettings() {
    assistant.open = false;
    openDialog(SettingsDialog, { initialSection: 'assistant' });
  }
</script>

<div class="chat" role="dialog" aria-label={t('AI Assistant')} tabindex="-1"
         onkeydown={(e) => e.key === 'Escape' && (assistant.open = false)}>
  <header>
    <Icon name="sparkles" size={17} />
    <h2>{t('AI Assistant')}</h2>
    <span class="grow"></span>
    <div class="modes" role="tablist" aria-label={t('Mode')}>
      {#each MODES as [mode, label, icon] (mode)}
        <button role="tab" class:active={assistant.mode === mode} aria-selected={assistant.mode === mode} onclick={() => setMode(mode)}
                title={mode === 'music' ? t('Songs for a scene') : t('Questions about rules, the world and the session')}>
          <Icon name={icon} size={14} /><span>{t(label)}</span>
          {#if assistant.chats[mode].busy && assistant.mode !== mode}<span class="pending" aria-hidden="true"></span>{/if}
        </button>
      {/each}
    </div>
    {#if chat.turns.length}
      <button class="icon-btn" title={t('New chat')} aria-label={t('New chat')} disabled={chat.busy} onclick={newChat}><Icon name="refresh" size={15} /></button>
    {/if}
    <button class="icon-btn" title={t('Close')} aria-label={t('Close')} onclick={() => (assistant.open = false)}><Icon name="close" size={16} /></button>
  </header>

  <div class="log" bind:this={log}>
    {#if !configured}
      <div class="empty">
        <p>{t('The AI assistant is not configured yet.')}</p>
        {#if admin}
          <button class="btn primary" onclick={openSettings}><Icon name="settings" size={14} /> {t('Set up the AI assistant')}</button>
        {:else}
          <p class="muted">{t('Ask the SuperAdmin to enter an API key in the settings.')}</p>
        {/if}
      </div>
    {:else if !chat.turns.length}
      <div class="empty">
        <p>{music ? t('Describe a scene of your session and get the {0} best fitting songs.', SONGS_PER_ANSWER)
                  : t('Ask about the rules (e.g. DSA), the world or anything else around your session.')}</p>
        <div class="examples">
          {#each EXAMPLES[assistant.mode] as example (example)}
            <button class="chip" onclick={() => send(t(example))}>{t(example)}</button>
          {/each}
        </div>
      </div>
    {/if}

    {#each chat.turns as turn, i (i)}
      {#if turn.role === 'user'}
        <div class="bubble user">{turn.content}</div>
      {:else if turn.role === 'error'}
        <div class="bubble error">
          <span>{turn.message}</span>
          <button class="btn" onclick={() => send(turn.question)}><Icon name="refresh" size={14} /> {t('Try again')}</button>
        </div>
      {:else if !music}
        <!-- escaped by markdown(), so the answer cannot inject HTML -->
        <div class="bubble bot text">{@html markdown(turn.message)}</div>
      {:else}
        <div class="bubble bot">
          {#if turn.message}<p>{turn.message}</p>{/if}
          {#if turn.songs.length}
            <ol class="songs">
              {#each turn.songs as song, n (n)}
                {@const query = localQueries.get(song.title)}
                <li>
                  <span class="num">{turn.first + n}</span>
                  <span class="name">
                    <strong>{song.title}</strong>
                    {#if song.artist}<span class="muted">{song.artist}</span>{/if}
                  </span>
                  {#if query}
                    <button class="icon-btn found" title={t('Show in the open tab')} aria-label={t('Show in the open tab')} onclick={() => searchLibrary(query)}><Icon name="search" size={14} /></button>
                  {/if}
                  <a class="yt" href={youtubeSearchUrl(song)} target="_blank" rel="noopener noreferrer" title={t('Search on YouTube')}><Icon name="youtube" size={15} /> YouTube</a>
                </li>
              {/each}
            </ol>
          {:else}
            <p class="muted">{t('No songs found, try to describe the scene differently.')}</p>
          {/if}
        </div>
        {#if turn === lastTurn && turn.songs.length}
          <button class="btn more" disabled={chat.busy} onclick={moreSongs}><Icon name="plus" size={14} /> {t('Show {0} more songs', SONGS_PER_ANSWER)}</button>
        {/if}
      {/if}
    {/each}

    {#if chat.busy}<div class="bubble bot typing" aria-live="polite"><span></span><span></span><span></span></div>{/if}
  </div>

  {#if configured}
    <form class="compose" onsubmit={(e) => { e.preventDefault(); send(); }}>
      <textarea bind:this={input} bind:value={text} rows="2" placeholder={music ? t('Which songs fit…? e.g. a chase through the sewers') : t('Your question…')} onkeydown={onKeydown}></textarea>
      <button class="btn primary send" type="submit" disabled={chat.busy || !text.trim()} title={t('Send')} aria-label={t('Send')}><Icon name="send" size={16} /></button>
    </form>
  {/if}
</div>

<style>
  .chat {
    position: fixed; top: 58px; right: 16px; z-index: 40; width: min(440px, calc(100vw - 32px)); height: min(640px, calc(100vh - 150px));
    display: flex; flex-direction: column; background: var(--surface); color: var(--text); border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg); box-shadow: var(--shadow), 0 0 60px rgba(var(--ambient), 0.12); overflow: hidden;
  }
  header { display: flex; align-items: center; gap: 8px; padding: 10px 10px 10px 16px; border-bottom: 1px solid var(--border); color: var(--accent); }
  h2 { margin: 0; font-size: var(--fs-lg); font-family: var(--font-display); color: var(--text); white-space: nowrap; }
  .modes { display: flex; padding: 2px; gap: 2px; border-radius: 9px; background: var(--hover); border: 1px solid var(--border); }
  .modes button { display: flex; align-items: center; gap: 5px; height: 26px; padding: 0 9px; border-radius: 7px; color: var(--muted); font-size: var(--fs-xs); font-weight: 600; position: relative; }
  .modes button:hover { color: var(--text); }
  .modes button.active { background: var(--surface); color: var(--accent); box-shadow: var(--shadow-sm); }
  .pending { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); animation: blink 1.2s infinite ease-in-out; }
  .text { line-height: 1.5; }
  .text :global(p) { margin: 0 0 8px; }
  .text :global(p:last-child), .text :global(ul:last-child), .text :global(ol:last-child) { margin-bottom: 0; }
  .text :global(ul), .text :global(ol) { margin: 0 0 8px; padding-left: 20px; }
  .text :global(li) { margin: 2px 0; }
  .text :global(h3), .text :global(h4), .text :global(h5), .text :global(h6) { margin: 10px 0 4px; font-size: var(--fs); }
  .text :global(h3:first-child), .text :global(h4:first-child) { margin-top: 0; }
  .text :global(code) { padding: 1px 4px; border-radius: 4px; background: var(--hover); font-size: 0.92em; }
  .text :global(hr) { border: none; border-top: 1px solid var(--border); margin: 8px 0; }
  .grow { flex: 1; }
  .log { flex: 1; min-height: 0; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; padding: 14px; }
  .empty { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; color: var(--muted); font-size: var(--fs-sm); }
  .empty p { margin: 0; }
  .examples { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { padding: 5px 10px; border-radius: 14px; border: 1px solid var(--border-strong); background: var(--surface-2, var(--surface)); color: var(--text); font-size: var(--fs-xs); cursor: pointer; }
  .chip:hover { border-color: var(--accent); color: var(--accent); }
  .bubble { max-width: 92%; padding: 9px 12px; border-radius: var(--radius); font-size: var(--fs-sm); line-height: 1.4; overflow-wrap: anywhere; }
  .bubble p { margin: 0 0 6px; }
  .user { align-self: flex-end; background: var(--accent); color: var(--accent-text); border-bottom-right-radius: 4px; white-space: pre-wrap; }
  .bot { align-self: stretch; max-width: none; background: var(--hover); border-bottom-left-radius: 4px; }
  .error { align-self: stretch; max-width: none; display: flex; align-items: center; gap: 10px; background: var(--red-soft); color: var(--red); }
  .error span { flex: 1; }
  .songs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
  .songs li { display: flex; align-items: center; gap: 8px; padding: 4px 4px 4px 0; border-radius: var(--radius-sm); }
  .songs li:hover { background: var(--hover); }
  .num { width: 22px; flex: none; text-align: right; color: var(--faint); font-variant-numeric: tabular-nums; font-size: var(--fs-xs); }
  .name { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .name .muted { font-size: var(--fs-xs); }
  .found { color: var(--green); }
  .yt { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 3px 8px; border-radius: 6px; font-size: var(--fs-xs); color: var(--red); text-decoration: none; border: 1px solid var(--red-soft); }
  .yt:hover { background: var(--red-soft); }
  .more { align-self: center; }
  .typing { align-self: flex-start; display: flex; gap: 4px; padding: 12px 14px; }
  .typing span { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); animation: blink 1.2s infinite ease-in-out; }
  .typing span:nth-child(2) { animation-delay: 0.2s; }
  .typing span:nth-child(3) { animation-delay: 0.4s; }
  @keyframes blink { 0%, 80%, 100% { opacity: 0.25; } 40% { opacity: 1; } }
  .compose { display: flex; gap: 8px; align-items: flex-end; padding: 10px; border-top: 1px solid var(--border); }
  .compose textarea { flex: 1; resize: none; min-height: 40px; max-height: 120px; }
  .send { height: 40px; width: 44px; justify-content: center; padding: 0; }
  @media (max-width: 900px) { .chat { top: 52px; right: 8px; width: calc(100vw - 16px); height: calc(100vh - 140px); } }
</style>
