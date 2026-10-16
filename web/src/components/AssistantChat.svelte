<script lang="ts">
  import { tick } from 'svelte';
  import { locale, t } from '../lib/i18n.svelte';
  import { markdown } from '../lib/markdown';
  import { applyFilter, ask, assistant, compose, COMPOSE_DURATIONS, composeOptions, CREATE_KINDS, createSound, currentChat, effectOptions, moreSongs, newChat,
           saveComposeOptions, saveEffectOptions, setMode, SONGS_PER_ANSWER, SOUND_DURATIONS, youtubeSearchUrl, type AssistantMode, type ChatTurn, type CreateKind,
           type Take } from '../lib/stores/assistant.svelte';
  import { effects } from '../lib/stores/effects.svelte';
  import { calculateScore, scorePercent } from '../lib/scoring';
  import { playTrack } from '../lib/stores/player.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { activeTab, findsInTab, library } from '../lib/stores/library.svelte';
  import { songQueries } from '../lib/search';
  import { openImportDialog, uploadTarget } from '../lib/actions';
  import { openDialog } from '../lib/stores/ui.svelte';
  import type { AssistantSong, SmartFilter, Track } from '../lib/types';
  import FolderSelect from './dialogs/FolderSelect.svelte';
  import SettingsDialog from './dialogs/SettingsDialog.svelte';
  import Icon from './Icon.svelte';

  const EXAMPLES: Record<AssistantMode, string[]> = {
    music: ['A brawl in a crowded tavern', 'Exploring a haunted crypt', 'The final fight against a dragon', 'A sad farewell at a funeral'],
    general: ['How does an attack work?', 'A name and a short description for a dwarven innkeeper', 'Three plot hooks for a village festival'],
    smart: ['A brawl in a crowded tavern', 'Exploring a haunted crypt', 'A sad farewell at a funeral'],
    create: ['A brawl in a crowded tavern', 'Rain on a tent at night', 'A heavy door slams shut in a dungeon', 'A festival in an elven forest'],
  };
  /** Music is composed by the music generation (ACE-Step), the other kinds are created by the sound generation (Stable Audio). */
  const KIND_LABELS: Record<CreateKind, string> = { song: 'Music', music: 'Background music', ambience: 'Ambience', sfx: 'Sound effect' };
  /** What the user asks for when the kind of a description is not the chosen one any more. */
  const KIND_REQUESTS: Record<CreateKind, string> = {
    song: 'Make it a piece of music instead.', music: 'Make it instrumental background music instead.', ambience: 'Make it an ambience instead.',
    sfx: 'Make it a sound effect instead.',
  };
  const MODES: [AssistantMode, string, string, string][] = [
    ['music', 'New music', 'music', 'New songs for a scene, to find on YouTube and import'],
    ['smart', 'Smart search', 'sliders', 'Finds the best fitting songs of your whole library for a scene: the AI sets the filter, nothing is invented'],
    ['create', 'Generate', 'wand', 'Generates music (ACE-Step), sound effects, ambiences and background music (Stable Audio) for a scene with AI and stores them in your library'],
    ['general', 'General', 'mask', 'Questions about rules, the world and the session'],
  ];
  const TOP_MATCHES = 5;

  let text = $state('');
  let input = $state<HTMLTextAreaElement | null>(null);
  let log = $state<HTMLElement | null>(null);
  const assistantConfigured = $derived(data.settings?.assistantConfigured === true);
  const musicGenConfigured = $derived(data.settings?.musicGenConfigured === true);
  const soundGenConfigured = $derived(data.settings?.soundGenConfigured === true);
  const groqConfigured = $derived(data.settings?.groqConfigured === true);
  const creating = $derived(assistant.mode === 'create');
  // the kinds whose generator is set up: music needs the music generation, the sounds the sound generation
  const kinds = $derived(CREATE_KINDS.filter((kind) => (kind === 'song' ? musicGenConfigured : soundGenConfigured)));
  const composing = $derived(creating && effectOptions.kind === 'song');
  const sounding = $derived(creating && effectOptions.kind !== 'song');
  // the smart search runs on Groq or Gemini; the create mode needs the music or the sound generation (without an AI service the text
  // of the user is the description); the song suggestions and the general chat need Gemini
  const configured = $derived(creating ? kinds.length > 0 : assistant.mode === 'smart' ? groqConfigured || assistantConfigured : assistantConfigured);
  const admin = $derived(data.auth?.is_admin !== false);
  const chat = $derived(currentChat());
  const music = $derived(assistant.mode === 'music');
  const smart = $derived(assistant.mode === 'smart');
  const tab = $derived(activeTab());

  /** The best songs of the open tab for the filter of an answer (its own filter, also when the sliders were moved since). */
  function topMatches(chosen: SmartFilter): { track: Track; percent: number }[] {
    const config = { categories: chosen.categories, tags: chosen.tags, genres: chosen.genres, bpm: chosen.bpm };
    return (tab?.tracks ?? [])
      .map((track) => ({ track, score: calculateScore(track, config) }))
      .filter((row): row is { track: Track; score: number } => row.score !== null)
      .sort((a, b) => a.score - b.score)
      .slice(0, TOP_MATCHES)
      .map(({ track, score }) => ({ track, percent: scorePercent(score) ?? 0 }));
  }

  const categoryName = (key: string) => data.categories.find((category) => category.key === key)?.name ?? key;
  const lastTurn = $derived(chat.turns.at(-1));

  // the mode tabs scroll when they do not fit (phones): keep the chosen one in view
  let modesEl = $state<HTMLElement | null>(null);
  $effect(() => {
    void assistant.mode;
    modesEl?.querySelector<HTMLElement>('button.active')?.scrollIntoView({ block: 'nearest', inline: 'center' });
  });

  $effect(() => {
    void chat.turns.length;
    void chat.busy;
    void tick().then(() => log?.scrollTo({ top: log.scrollHeight, behavior: 'smooth' }));
  });

  $effect(() => {
    void assistant.mode;
    if (configured) input?.focus();
  });

  $effect(() => {
    if (composing && !composeOptions.dir) composeOptions.dir = uploadTarget() ?? '';
  });
  $effect(() => {
    if (creating && kinds.length && !kinds.includes(effectOptions.kind)) effectOptions.kind = kinds[0];
  });
  // sounds go into the effects folder until another folder is chosen
  $effect(() => {
    if (sounding && !effectOptions.dir) effectOptions.dir = effects.directory || data.settings?.effectsDirectory || uploadTarget() || '';
  });

  // the lyrics can be written in the languages of the app; until one is chosen, in the language of the app
  const lyricLanguages = $derived(data.locales.length ? data.locales : [locale()]);
  $effect(() => {
    if (composing && !lyricLanguages.includes(composeOptions.language)) composeOptions.language = lyricLanguages.includes(locale()) ? locale() : lyricLanguages[0];
  });
  /** What a new description has to change so that the piece matches the options: the vocals or the language of the lyrics. */
  function outdated(piece: { instrumental: boolean; language: string }): 'vocals' | 'language' | null {
    if (piece.instrumental !== composeOptions.instrumental) return 'vocals';
    return !piece.instrumental && piece.language && piece.language !== composeOptions.language ? 'language' : null;
  }

  const formatDuration = (seconds: number) => (seconds < 60 ? `${seconds} s` : `${seconds / 60} min`);

  /** The kind of the description of an answer: music for a piece, the kind of the sound otherwise. */
  const describedKind = (turn: { piece?: unknown; sound?: { kind: CreateKind } }): CreateKind | null => (turn.piece ? 'song' : turn.sound?.kind ?? null);

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

<div class="chat" role="dialog" data-tour="assistant-chat" aria-label={t('AI Assistant')} tabindex="-1"
         onkeydown={(e) => e.key === 'Escape' && (assistant.open = false)}>
  <header>
    <Icon name="sparkles" size={17} />
    <h2>{t('AI Assistant')}</h2>
    <span class="grow"></span>
    {#if chat.turns.length}
      <button class="icon-btn" title={t('New chat')} aria-label={t('New chat')} disabled={chat.busy} onclick={newChat}><Icon name="refresh" size={15} /></button>
    {/if}
    <button class="icon-btn" title={t('Close')} aria-label={t('Close')} onclick={() => (assistant.open = false)}><Icon name="close" size={16} /></button>
  </header>
  <div class="modes" role="tablist" aria-label={t('Mode')} bind:this={modesEl}>
    {#each MODES as [mode, label, icon, hint] (mode)}
      <button role="tab" class:active={assistant.mode === mode} aria-selected={assistant.mode === mode} onclick={() => setMode(mode)} title={t(hint)}>
        <Icon name={icon} size={14} /><span>{t(label)}</span>
        {#if assistant.chats[mode].busy && assistant.mode !== mode}<span class="pending" aria-hidden="true"></span>{/if}
      </button>
    {/each}
  </div>

  <div class="log" bind:this={log}>
    {#if !configured}
      <div class="empty">
        <p>{creating ? t('The music and the sound generation are not configured yet.') : t('The AI assistant is not configured yet.')}</p>
        {#if admin}
          <button class="btn primary" onclick={openSettings}><Icon name="settings" size={14} />
            {creating ? t('Set up the music or the sound generation') : t('Set up the AI assistant')}</button>
        {:else}
          <p class="muted">{creating ? t('Ask the SuperAdmin to set up the music or the sound generation in the settings.') : t('Ask the SuperAdmin to enter an API key in the settings.')}</p>
        {/if}
      </div>
    {:else if !chat.turns.length}
      <div class="empty">
        <p>{music ? t('Describe a scene of your session and get the {0} best fitting songs. They are new songs that are not in your library yet: open them on YouTube or download them with the download button to import them.', SONGS_PER_ANSWER)
                  : smart ? t('Describe a scene: the AI sets the mood filter and your library ranks its songs. Only songs you have are found.')
                  : composing ? t('Describe a scene and the AI composes a new piece for it (ACE-Step). The piece is stored in the chosen folder and analyzed like any other song.')
                  : sounding ? t('Describe a sound and the AI creates it (Stable Audio): a sound effect, an ambience or background music. It is stored in your effects folder, or in the folder you choose.')
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
      {:else if smart}
        <div class="bubble bot">
          {#if turn.message}<p>{turn.message}</p>{/if}
          {#if turn.filter}
            {@const chosen = turn.filter}
            <div class="values">
              {#each Object.entries(chosen.categories) as [key, value] (key)}<span class="value">{categoryName(key)} <b>{value}</b></span>{/each}
              {#each chosen.tags as tag (tag)}<span class="value tag">{tag}</span>{/each}
              {#each chosen.genres as genre (genre)}<span class="value genre">{genre}</span>{/each}
              {#if chosen.bpm}<span class="value">BPM <b>{chosen.bpm}</b></span>{/if}
            </div>
            {@const matches = topMatches(chosen)}
            {#if matches.length}
              <span class="label">{t('Best matches in {0}', tab?.name ?? '')}</span>
              <ol class="songs">
                {#each matches as { track, percent } (track.id)}
                  <li>
                    <button class="icon-btn" title={t('Play')} aria-label={t('Play')} onclick={() => playTrack(track)}><Icon name="play" size={13} /></button>
                    <span class="name"><strong>{track.title || track.name}</strong>{#if track.artist}<span class="muted">{track.artist}</span>{/if}</span>
                    <span class="percent">{percent}%</span>
                  </li>
                {/each}
              </ol>
            {:else}
              <p class="muted">{tab?.loading ? t('Loading…') : t('No song of the library has values for this filter yet; analyze the songs first.')}</p>
            {/if}
            <button class="btn sm apply" onclick={() => { applyFilter(chosen); assistant.open = false; }}><Icon name="filter" size={13} /> {t('Apply filter')}</button>
          {/if}
        </div>
      {:else if creating}
        <div class="bubble bot">
          {#if turn.message}<p>{turn.message}</p>{/if}
          {#if turn.piece}
            {@const piece = turn.piece}
            <div class="piece">
              <strong>{piece.title} <span class="kind">{t('Music')} · {piece.instrumental ? t('Instrumental') : piece.language ? `${t('Vocals')} · ${t(piece.language)}` : t('Vocals')}</span></strong>
              <span class="muted caption">{piece.caption}{piece.bpm ? ` · ${piece.bpm} BPM` : ''}</span>
              {#if piece.lyrics}<details><summary>{t('Lyrics')}</summary><pre>{piece.lyrics}</pre></details>{/if}
            </div>
            {@render takes(turn.takes ?? [], t('Composing… after a break the cloud needs a few minutes to start.'), true)}
            <div class="row">
              <button class="btn sm apply" disabled={!composeOptions.dir || !musicGenConfigured} onclick={() => compose(turn)}>
                <Icon name="wand" size={13} /> {turn.takes?.length ? t('Compose a variation') : t('Compose')}</button>
              <!-- the description holds the lyrics: switching the vocals needs a new one -->
              {#if turn === lastTurn && composing && outdated(piece) === 'vocals'}
                <button class="btn sm apply" disabled={chat.busy} onclick={() => send(composeOptions.instrumental ? t('Make it instrumental, without vocals.') : t('Make it with vocals and write lyrics.'))}>
                  <Icon name="refresh" size={13} /> {composeOptions.instrumental ? t('Describe again as instrumental') : t('Describe again with vocals')}</button>
              {:else if turn === lastTurn && composing && outdated(piece) === 'language'}
                <button class="btn sm apply" disabled={chat.busy} onclick={() => send(t('Write the lyrics in {0}.', t(composeOptions.language)))}>
                  <Icon name="refresh" size={13} /> {t('Describe again in {0}', t(composeOptions.language))}</button>
              {/if}
              {@render redescribe(turn)}
            </div>
          {:else if turn.sound}
            {@const sound = turn.sound}
            <div class="piece">
              <strong>{sound.title} <span class="kind">{t(KIND_LABELS[sound.kind])}{sound.duration ? ` · ${formatDuration(sound.duration)}` : ''}</span></strong>
              <span class="muted caption">{sound.caption}</span>
            </div>
            {@render takes(turn.takes ?? [], t('Creating… after a break the cloud needs a few minutes to start.'), false)}
            <div class="row">
              <button class="btn sm apply" disabled={!effectOptions.dir || !soundGenConfigured} onclick={() => createSound(turn)}>
                <Icon name="waves" size={13} /> {turn.takes?.length ? t('Create a variation') : t('Create')}</button>
              {@render redescribe(turn)}
            </div>
          {/if}
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
                {@const check = song.check}
                <li class:missing={check?.found === false}>
                  <span class="num">{turn.first + n}</span>
                  <span class="name">
                    <strong>{song.title}</strong>
                    {#if check?.found === false}
                      <span class="muted">{song.artist}{song.artist ? ' · ' : ''}{t('Not found on YouTube')}</span>
                    {:else if song.artist}<span class="muted">{song.artist}</span>{/if}
                  </span>
                  {#if !check}<span class="checking" title={t('Checking on YouTube…')}></span>{/if}
                  {#if query}
                    <button class="icon-btn found" title={t('Show in the open tab')} aria-label={t('Show in the open tab')} onclick={() => searchLibrary(query)}><Icon name="search" size={14} /></button>
                  {/if}
                  {#if check?.found && check.url}
                    <a class="yt verified" href={check.url} target="_blank" rel="noopener noreferrer"
                       title="{t('Open on YouTube')}: {check.title}{check.channel ? ` · ${check.channel}` : ''}"><Icon name="check" size={13} /> YouTube</a>
                    <button class="icon-btn import" title={t('Import from YouTube…')} aria-label={t('Import from YouTube…')} onclick={() => openImportDialog(undefined, check.url)}><Icon name="download" size={14} /></button>
                  {:else}
                    <a class="yt" href={youtubeSearchUrl(song)} target="_blank" rel="noopener noreferrer" title={t('Search on YouTube')}><Icon name="youtube" size={15} /> YouTube</a>
                  {/if}
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

  {#if configured && creating}
    <div class="options">
      <select bind:value={effectOptions.kind} onchange={saveEffectOptions} aria-label={t('Kind')} title={t('Kind')}>
        {#each kinds as kind (kind)}<option value={kind}>{t(KIND_LABELS[kind])}</option>{/each}
      </select>
      {#if composing}
        <select bind:value={composeOptions.duration} onchange={saveComposeOptions} aria-label={t('Length')} title={t('Length')}>
          {#each COMPOSE_DURATIONS as seconds (seconds)}<option value={seconds}>{formatDuration(seconds)}</option>{/each}
        </select>
        <label class="check"><input type="checkbox" checked={!composeOptions.instrumental}
               onchange={(e) => { composeOptions.instrumental = !e.currentTarget.checked; saveComposeOptions(); }} /> {t('Vocals')}</label>
        {#if !composeOptions.instrumental}
          <select bind:value={composeOptions.language} onchange={saveComposeOptions} aria-label={t('Language of the lyrics')} title={t('Language of the lyrics')}>
            {#each lyricLanguages as code (code)}<option value={code}>{t(code)}</option>{/each}
          </select>
        {/if}
        <span class="folder" title={t('Target folder')}><FolderSelect bind:selected={composeOptions.dir} /></span>
      {:else}
        <select bind:value={effectOptions.duration} onchange={saveEffectOptions} aria-label={t('Length')} title={t('Length')}>
          {#each SOUND_DURATIONS as seconds (seconds)}<option value={seconds}>{seconds ? formatDuration(seconds) : t('As suggested')}</option>{/each}
        </select>
        <span class="folder" title={t('Target folder')}><FolderSelect bind:selected={effectOptions.dir} /></span>
      {/if}
    </div>
  {/if}
  {#if configured}
    <form class="compose" onsubmit={(e) => { e.preventDefault(); send(); }}>
      <textarea bind:this={input} bind:value={text} rows="2" placeholder={music ? t('Which songs fit…? e.g. a chase through the sewers') : composing ? t('Describe the piece… e.g. a chase through the sewers') : sounding ? t('Describe the sound… e.g. rain on a tent at night') : smart ? t('Describe the scene… e.g. a chase through the sewers') : t('Your question…')} onkeydown={onKeydown}></textarea>
      <button class="btn primary send" type="submit" disabled={chat.busy || !text.trim()} title={t('Send')} aria-label={t('Send')}><Icon name="send" size={16} /></button>
    </form>
  {/if}
</div>

{#snippet takes(list: Take[], working: string, findable: boolean)}
  <ol class="songs">
    {#each list as take, n (n)}
      <li class:missing={take.status === 'error'}>
        {#if take.status === 'composing'}
          <span class="checking"></span>
          <span class="name"><span class="muted">{working}</span></span>
        {:else if take.status === 'error'}
          <Icon name="close" size={14} />
          <span class="name"><span class="err">{take.error}</span></span>
        {:else if take.track}
          {@const track = take.track}
          <button class="icon-btn" title={t('Play')} aria-label={t('Play')} onclick={() => playTrack(track)}><Icon name="play" size={13} /></button>
          <span class="name"><strong>{track.title || track.name}</strong><span class="muted" title={track.path}>{track.path.split('/').at(-2) ?? ''}</span></span>
          {#if findable}
            <button class="icon-btn found" title={t('Show in the open tab')} aria-label={t('Show in the open tab')} onclick={() => searchLibrary(track.title || track.name)}><Icon name="search" size={14} /></button>
          {/if}
        {/if}
      </li>
    {/each}
  </ol>
{/snippet}

<!-- a description is written for its kind (a piece of music or a sound): another kind needs a new one -->
{#snippet redescribe(turn: ChatTurn)}
  {#if turn === lastTurn && turn.role === 'assistant' && describedKind(turn) !== effectOptions.kind}
    <button class="btn sm apply" disabled={chat.busy} onclick={() => send(t(KIND_REQUESTS[effectOptions.kind]))}>
      <Icon name="refresh" size={13} /> {t('Describe again as {0}', t(KIND_LABELS[effectOptions.kind]))}</button>
  {/if}
{/snippet}

<style>
  .chat {
    position: fixed; top: 58px; right: 16px; z-index: 40; width: min(440px, calc(100vw - 32px)); height: min(640px, calc(100vh - 150px));
    display: flex; flex-direction: column; background: var(--surface); color: var(--text); border: 1px solid var(--border-strong);
    border-radius: var(--radius-lg); box-shadow: var(--shadow), 0 0 60px rgba(var(--ambient), 0.12); overflow: hidden;
  }
  header { display: flex; align-items: center; gap: 8px; padding: 10px 10px 10px 16px; border-bottom: 1px solid var(--border); color: var(--accent); }
  h2 { margin: 0; font-size: var(--fs-lg); font-family: var(--font-display); color: var(--text); white-space: nowrap; }
  .modes { display: flex; margin: 8px 12px 0; padding: 2px; gap: 2px; border-radius: 9px; background: var(--hover); border: 1px solid var(--border); }
  .modes { overflow-x: auto; scrollbar-width: none; }
  .modes::-webkit-scrollbar { display: none; }
  .modes button { flex: 1 0 auto; display: flex; align-items: center; justify-content: center; gap: 5px; height: 28px; padding: 0 8px; border-radius: 7px; color: var(--muted); font-size: var(--fs-xs); font-weight: 600; position: relative; white-space: nowrap; }
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
  /* the answers can be copied elsewhere: the desktop window (pywebview) turns text selection off for the whole page */
  .log :is(.bubble, .piece, .caption, .name, p, pre, li) { -webkit-user-select: text; user-select: text; cursor: text; }
  .log :is(button, a, .chip) { -webkit-user-select: none; user-select: none; cursor: pointer; }
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
  .songs li.missing strong { color: var(--muted); text-decoration: line-through; text-decoration-color: var(--faint); }
  .songs li.missing .yt { opacity: 0.6; }
  .checking { width: 10px; height: 10px; flex: none; border: 2px solid var(--faint); border-right-color: transparent; border-radius: 50%; animation: check-spin 0.8s linear infinite; }
  @keyframes check-spin { to { transform: rotate(360deg); } }
  .num { width: 22px; flex: none; text-align: right; color: var(--faint); font-variant-numeric: tabular-nums; font-size: var(--fs-xs); }
  .name { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .name .muted { font-size: var(--fs-xs); }
  .found { color: var(--green); }
  .yt { display: inline-flex; align-items: center; gap: 4px; flex: none; padding: 3px 8px; border-radius: 6px; font-size: var(--fs-xs); color: var(--red); text-decoration: none; border: 1px solid var(--red-soft); }
  .yt:hover { background: var(--red-soft); }
  .yt.verified { color: var(--green); border-color: var(--green-soft); }
  .yt.verified:hover { background: var(--green-soft); }
  .import { width: 26px; height: 26px; }
  .more { align-self: center; }
  .values { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
  .value { padding: 2px 8px; border-radius: 10px; background: var(--surface); border: 1px solid var(--border); font-size: var(--fs-xs); }
  .value b { color: var(--accent); }
  .value.tag { border-color: var(--accent-soft); color: var(--accent); }
  .value.genre { border-color: var(--gold-soft); color: var(--gold); }
  .label { display: block; margin: 2px 0 4px; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: 0.05em; color: var(--faint); }
  .percent { flex: none; font-size: var(--fs-xs); font-variant-numeric: tabular-nums; color: var(--green); font-weight: 600; }
  .apply { margin-top: 8px; }
  .piece { display: flex; flex-direction: column; gap: 2px; margin-bottom: 6px; }
  .piece .caption { font-size: var(--fs-xs); }
  .kind { margin-left: 4px; padding: 1px 7px; border-radius: 9px; background: var(--surface); border: 1px solid var(--border); font-size: var(--fs-xs); font-weight: 600; color: var(--muted); }
  .bot .row { display: flex; flex-wrap: wrap; gap: 6px; }
  .piece summary { cursor: pointer; font-size: var(--fs-xs); color: var(--muted); }
  .piece pre { margin: 4px 0 0; white-space: pre-wrap; font-family: inherit; font-size: var(--fs-xs); }
  .err { color: var(--red); font-size: var(--fs-xs); }
  .options { display: flex; align-items: center; gap: 10px; padding: 8px 10px 0; border-top: 1px solid var(--border); font-size: var(--fs-xs); }
  .options .check { display: flex; align-items: center; gap: 4px; white-space: nowrap; }
  .options .folder { flex: 1; min-width: 0; }
  .options + .compose { border-top: none; }
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
