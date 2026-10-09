<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { ACCENTS, DEFAULT_ACCENT } from '../../lib/accent';
  import { data, saveCategories, saveSettings, setAccent, setUserLocale } from '../../lib/stores/data.svelte';
  import { loadLights } from '../../lib/stores/lights.svelte';
  import { setNormalize } from '../../lib/stores/player.svelte';
  import { askConfirm, closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import AgentTokenDialog from './AgentTokenDialog.svelte';
  import CategoryEditDialog, { type CategoryRow } from './CategoryEditDialog.svelte';
  import type { AgentInfo, AgentState, AgentToken, MusicCategory, ServerSettings, StorageConfig } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import { onEvent } from '../../lib/ws';
  import Modal from './Modal.svelte';
  import UsersPanel from './UsersPanel.svelte';

  type Section = 'general' | 'library' | 'categories' | 'lights' | 'agents' | 'youtube' | 'player' | 'security';
  const AGENT_URL = 'https://github.com/gandulf/DungeonTuber/releases/latest/download/dt-youtube.exe';
  let { initialSection = 'general' }: { initialSection?: Section } = $props();
  const admin = data.auth?.is_admin !== false;
  // library folders can only be edited in the desktop app; a server gets them at startup
  const desktop = data.auth?.local === true;
  // svelte-ignore state_referenced_locally
  let section = $state<Section>(initialSection);

  const s = data.settings!;
  let form = $state<ServerSettings>(structuredClone($state.snapshot(s)) as ServerSettings);
  let roots = $state(form.libraryRoots.join('\n'));

  interface StorageRow extends StorageConfig { access_key: string; secret_key: string; testing: boolean }
  let storages = $state<StorageRow[]>([]);
  let storagesAvailable = $state(true);
  let storagesDirty = $state(false);
  void api.storages().then((result) => {
    storagesAvailable = result.available;
    storages = result.storages.map((c) => ({ ...c, access_key: '', secret_key: '', testing: false }));
  }).catch(errorToast);

  const storagePayload = (row: StorageRow): StorageConfig => ({
    id: row.id, name: row.name, bucket: row.bucket, prefix: row.prefix, endpoint_url: row.endpoint_url, public_endpoint_url: row.public_endpoint_url, region: row.region, direct: row.direct,
    ...(row.access_key ? { access_key: row.access_key } : {}), ...(row.secret_key ? { secret_key: row.secret_key } : {}),
  });

  function addStorage() {
    storages.push({ name: '', bucket: '', prefix: '', endpoint_url: '', public_endpoint_url: '', region: '', direct: false, access_key: '', secret_key: '', testing: false });
    storagesDirty = true;
  }

  async function testStorage(row: StorageRow) {
    row.testing = true;
    try {
      const result = await api.testStorage(storagePayload(row));
      toast(t('Connection successful ({0} entries in the root)', result.entries), 'success');
    } catch (e) {
      errorToast(e);
    } finally {
      row.testing = false;
    }
  }

  const LEVELS = ['1', '5', '10'];
  const toRow = (c: MusicCategory): CategoryRow => ({
    key: c.key, name: c.name, group: c.group ?? '', description: c.description,
    low: c.levels[1] ?? '', medium: c.levels[5] ?? '', high: c.levels[10] ?? '',
    other: Object.fromEntries(Object.entries(c.levels).filter(([level]) => !LEVELS.includes(level))), isNew: false,
  });
  const levelsOf = (row: CategoryRow): Record<string, string> => {
    const levels: Record<string, string> = { ...row.other };
    for (const [level, text] of [['1', row.low], ['5', row.medium], ['10', row.high]]) if (text.trim()) levels[level] = text.trim();
    return levels;
  };
  let categories = $state<CategoryRow[]>(data.categories.map(toRow));
  let categoriesDirty = $state(false);
  /** The category of the edit popup (`index` null for a new one). */
  let editing = $state<{ index: number | null; row: CategoryRow } | null>(null);
  let catList = $state<HTMLElement | null>(null);

  async function saveCategory(row: CategoryRow) {
    if (!editing) return;
    const { index } = editing;
    editing = null;
    categoriesDirty = true;
    if (index === null) {
      categories.push({ ...row, isNew: true });
      await tick();
      catList?.scrollTo({ top: catList.scrollHeight, behavior: 'smooth' }); // the new entry is at the end of a long list
    } else {
      categories[index] = { ...row, isNew: categories[index].isNew };
    }
  }
  let cookies = $state<{ set: boolean; updated: number | null }>({ set: false, updated: null });
  if (admin) void api.youtubeCookies().then((result) => (cookies = result)).catch(() => {});

  let proxy = $state('');
  let proxyFromEnv = $state(false);
  let proxySaved = '';
  if (admin) void api.youtubeProxy().then((result) => { proxy = proxySaved = result.value; proxyFromEnv = result.fromEnv; }).catch(() => {});

  async function uploadCookies(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    try {
      cookies = await api.putYoutubeCookies(await file.text());
      toast(t('YouTube cookies saved'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeCookies() {
    if (!(await askConfirm(t('Remove the stored YouTube cookies?')))) return;
    try {
      cookies = await api.deleteYoutubeCookies();
    } catch (e) {
      errorToast(e);
    }
  }

  let cloud = $state<{ configured: boolean; host: string | null }>({ configured: false, host: null });
  let cloudUrl = $state('');
  let cloudKey = $state('');
  let cloudSecret = $state('');
  if (admin) void api.cloudAnalysis().then((result) => (cloud = result)).catch(() => {});

  async function saveCloud() {
    try {
      cloud = await api.putCloudAnalysis(cloudUrl, cloudKey, cloudSecret);
      cloudUrl = cloudKey = cloudSecret = '';
      toast(t('Cloud analysis saved'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeCloud() {
    if (!(await askConfirm(t('Remove the cloud analysis settings?')))) return;
    try {
      cloud = await api.deleteCloudAnalysis();
    } catch (e) {
      errorToast(e);
    }
  }

  let agents = $state<AgentState | null>(null);
  let newToken = $state<{ token: string; name: string } | null>(null); // a new token is only shown once, in a popup
  let tokenName = $state('');
  void api.agents().then((result) => (agents = result)).catch(() => {});
  const youtubeAgents = $derived(agents?.connected.filter((a) => a.kind === 'youtube').length ?? 0);
  const stopAgentEvents = onEvent('agents.state', (connected) => agents && (agents = { ...agents, connected }));
  onDestroy(stopAgentEvents);
  const agentLabels: Record<string, string> = { lights: 'WiZ light agent', voxalyzer: 'Voxalyzer analysis agent', youtube: 'YouTube download agent' };

  async function removeAgent(agent: AgentInfo) {
    const label = t(agentLabels[agent.kind] ?? agent.kind);
    if (!(await askConfirm(t('Remove {0}? It disconnects and does not reconnect.', `${label} (${agent.name})`)))) return;
    try {
      const result = await api.removeAgent(agent.id);
      if (agents) agents = { ...agents, connected: result.connected };
    } catch (e) {
      errorToast(e);
    }
  }

  async function createAgentToken() {
    try {
      newToken = { token: (await api.createAgentToken(tokenName.trim())).token, name: tokenName.trim() };
      tokenName = '';
      agents = await api.agents();
    } catch (e) {
      errorToast(e);
    }
  }

  async function deleteAgentToken(token: AgentToken) {
    if (!(await askConfirm(t('Delete the token {0}? Agents that use it disconnect and are locked out.', token.name || t('Unnamed'))))) return;
    try {
      agents = await api.deleteAgentToken(token.id);
    } catch (e) {
      errorToast(e);
    }
  }

  let password = $state('');
  let password2 = $state('');
  let saving = $state(false);

  async function save() {
    saving = true;
    try {
      const changed: Partial<Record<keyof ServerSettings, unknown>> = {};
      const keys: (keyof ServerSettings)[] = ['locale', 'skipAnalyzedMusic', 'lightsEnabled', 'lightsBroadcastIP', 'lightsTimeout', 'shareOnNetwork', 'sharePort'];
      for (const key of keys) if (form[key] !== s[key]) changed[key] = form[key];
      const rootList = roots.split('\n').map((r) => r.trim()).filter(Boolean);
      if (desktop && rootList.join('\n') !== s.libraryRoots.join('\n')) changed.libraryRoots = rootList;
      if (admin && proxy.trim() !== proxySaved) await api.putYoutubeProxy(proxy);
      if (Object.keys(changed).length) await saveSettings(changed);
      if ('lightsEnabled' in changed && form.lightsEnabled) void loadLights();
      if (storagesDirty) {
        if (storages.some((row) => !row.bucket.trim())) throw new Error(t('Every storage needs a bucket name.'));
        await api.putStorages(storages.map(storagePayload));
      }
      if (categoriesDirty) {
        const keysSeen = new Set<string>();
        const list: MusicCategory[] = [];
        for (const row of categories) {
          const key = row.key.trim() || row.name.trim();
          if (!key) continue;
          if (keysSeen.has(key)) throw new Error(t('Category keys must be unique: {0}', key));
          keysSeen.add(key);
          list.push({ key, name: row.name.trim() || key, group: row.group.trim(), description: row.description, levels: levelsOf(row) });
        }
        await saveCategories(list);
      }
      closeDialog();
    } catch (e) {
      errorToast(e);
    } finally {
      saving = false;
    }
  }

  async function resetCategories() {
    if (!(await askConfirm(t('Reset All') + '?'))) return;
    await saveCategories(null);
    categories = data.categories.map(toRow);
    categoriesDirty = false;
  }

  function addCategory() {
    editing = { index: null, row: { key: '', name: '', group: '', description: '', low: '', medium: '', high: '', other: {}, isNew: true } };
  }

  async function changePassword(remove = false) {
    if (!remove && (password.length < 4 || password !== password2)) {
      toast(t('Passwords must match and have at least 4 characters.'), 'error');
      return;
    }
    try {
      if (!admin) await api.setOwnPassword(password);
      else {
        const result = await api.setPassword(remove ? null : password);
        if (data.auth) data.auth.password_set = result.password_set;
      }
      password = password2 = '';
      toast(remove ? t('Password removed') : t('Password changed'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  const sections: [Section, string, string][] = [
    ['general', 'General', 'settings'],
    ['library', 'Library', 'folder'],
    ['categories', 'Categories', 'sliders'],
    ['lights', 'Lights', 'bulb'],
    ['youtube', 'YouTube', 'download'],
    ['agents', 'Agents', 'cloud'],
    ['player', 'Player', 'play'],
    ['security', 'Security', 'power'],
  ];
</script>

<Modal resizable title={t('Settings')} onclose={closeDialog} width="820px">
  <div class="layout">
    <nav>
      {#each sections.filter(([key]) => admin || ['general', 'youtube', 'agents', 'player', 'security'].includes(key)) as [key, label, icon] (key)}
        <button class:active={section === key} onclick={() => (section = key)}><Icon name={icon} size={16} /> {t(label)}</button>
      {/each}
    </nav>
    <div class="body">
      {#if section === 'general'}
        <h4>{t('Accent color')}</h4>
        <div class="swatches" role="radiogroup" aria-label={t('Accent color')}>
          {#each ACCENTS as accent (accent.key)}
            {@const current = (data.user.accent || DEFAULT_ACCENT) === accent.key}
            <button class="swatch" class:selected={current} role="radio" aria-checked={current} title={t(accent.name)} aria-label={t(accent.name)}
                    style:background="linear-gradient(135deg, {accent.light[0]}, {accent.light[1]})"
                    onclick={() => setAccent(accent.key === DEFAULT_ACCENT ? '' : accent.key)}>
              {#if current}<Icon name="check" size={16} />{/if}
            </button>
          {/each}
        </div>
        <label class="field">{t('Language')}
          <select value={data.user.locale} onchange={(e) => setUserLocale(e.currentTarget.value)}>
            <option value="">{data.settings?.locale ? t('Server default') : t('System Default')}</option>
            {#each data.locales as locale (locale)}<option value={locale}>{t(locale)}</option>{/each}
          </select>
        </label>
        {#if admin}
          <label class="field">{t('Server language')}
            <select bind:value={form.locale}>
              <option value="">{t('System Default')}</option>
              {#each data.locales as locale (locale)}<option value={locale}>{t(locale)}</option>{/each}
            </select>
            <span class="muted small">{t('Language of server messages and category names, and the default of users who did not choose their own.')}</span>
          </label>
          <h4>{t('Analyzer')}</h4>
          <label class="check"><input type="checkbox" bind:checked={form.skipAnalyzedMusic} /> {t('Skip Analyzed Music')}</label>
        {/if}
      {:else if section === 'library'}
        {#if desktop}
          <label class="field">{t('Library folders (one per line, paths on the server)')}
            <textarea rows="5" bind:value={roots}></textarea></label>
          <p class="muted small">{t('Only files inside these folders are accessible through the web interface.')}</p>
        {/if}
        <h4>{t('Cloud storage (S3 compatible)')}</h4>
        <p class="muted small">{t('Buckets of AWS S3, Cloudflare R2, Backblaze B2, MinIO and others. Song data is kept in the library database; the files in the bucket are never modified. Use s3://<id>/folder as effects directory.')}</p>
        {#if !storagesAvailable}<p class="warn small">{t('The S3 client is not installed on the server (pip install DungeonTuber[s3]).')}</p>{/if}
        {#each storages as row, i (i)}
          <div class="storage" oninput={() => (storagesDirty = true)} onchange={() => (storagesDirty = true)} role="group">
            <input type="text" placeholder={t('Name')} bind:value={row.name} />
            <input type="text" placeholder={t('Bucket')} bind:value={row.bucket} />
            <input type="text" placeholder={t('Folder in bucket (optional)')} bind:value={row.prefix} />
            <input type="url" placeholder={t('Endpoint URL (empty for AWS)')} bind:value={row.endpoint_url} />
            <input type="text" placeholder={t('Region (optional)')} bind:value={row.region} />
            <input type="url" placeholder={t('Public endpoint URL for browsers (optional)')} title={t('Used for direct streaming when browsers reach the storage under another address than the server does.')} bind:value={row.public_endpoint_url} />
            <span class="muted small id">{row.id ? `s3://${row.id}` : ''}</span>
            <input type="text" autocomplete="off" placeholder={row.has_credentials ? t('Access key (unchanged)') : t('Access key')} bind:value={row.access_key} />
            <input type="password" autocomplete="new-password" placeholder={row.has_credentials ? t('Secret key (unchanged)') : t('Secret key')} bind:value={row.secret_key} />
            <label class="check small" title={t('The browser streams directly from the bucket. Needs a CORS rule on the bucket.')}>
              <input type="checkbox" bind:checked={row.direct} /> {t('Direct streaming')}</label>
            <div class="row actions">
              <button class="btn" disabled={row.testing || !row.bucket.trim()} onclick={() => testStorage(row)}>{t('Test connection')}</button>
              <button class="icon-btn" title={t('Remove')} onclick={() => { storages.splice(i, 1); storagesDirty = true; }}><Icon name="trash" size={15} /></button>
            </div>
          </div>
        {/each}
        <div class="row"><button class="btn" onclick={addStorage}><Icon name="plus" size={14} /> {t('Add storage')}</button></div>
      {:else if section === 'youtube'}
        <section class="group">
          <h4>{t('YouTube download agent')}</h4>
          <p class="muted small">{t('YouTube often blocks downloads from servers. The Windows agent dt-youtube.exe downloads on your own computer instead, where YouTube works reliably. Download the agent, create an agent token under Agents, download the agents.json offered with the token and save it in the same folder as the agent. The agent has to keep running as long as you want to download YouTube songs.')}</p>
          <div class="row">
            <span class="small">{youtubeAgents > 0 ? t('{0} YouTube download agent(s) connected', youtubeAgents) : t('No agent connected')}</span>
            <span class="grow"></span>
            <a class="btn primary" href={AGENT_URL} target="_blank" rel="noopener"><Icon name="download" size={14} /> {t('Download dt-youtube.exe')}</a>
          </div>
          <span class="muted small">{t('Always the latest release from GitHub.')}</span>
        </section>
        {#if admin}
          <h4>{t('Cookies')}</h4>
          <p class="muted small">{t('Without an agent: export the cookies of a signed-in YouTube session as cookies.txt (Netscape format, e.g. with a browser extension) and upload them here. Only the YouTube cookies are kept, and they are never sent back to the browser.')}</p>
          <div class="row">
            <span class="small">{cookies.set ? t('Cookies stored ({0})', new Date((cookies.updated ?? 0) * 1000).toLocaleString()) : t('No cookies stored')}</span>
            <span class="grow"></span>
            <label class="btn"><Icon name="upload" size={14} /> {t('Upload cookies.txt…')}<input type="file" accept=".txt,text/plain" hidden onchange={uploadCookies} /></label>
            {#if cookies.set}<button class="btn danger" onclick={removeCookies}>{t('Remove')}</button>{/if}
          </div>
          <label class="field">{t('Proxy for YouTube downloads')}
            <input type="text" autocomplete="off" placeholder={proxyFromEnv ? t('Default from the server configuration') : 'http://user:password@host:port'} bind:value={proxy} /></label>
          <p class="muted small">{t('All YouTube requests go through this proxy (http, https, socks4 or socks5). Leave empty to use the default of the server (DT_YT_PROXY) or none.')}</p>
        {/if}
      {:else if section === 'categories'}
        <div class="cat-head">
          <span class="muted small">{t('The mood categories songs are rated in.')}</span>
          <span class="grow"></span>
          <button class="btn" onclick={addCategory}><Icon name="plus" size={14} /> {t('Add')}</button>
          <button class="btn danger" onclick={resetCategories}>{t('Reset All')}</button>
        </div>
        <div class="cats" bind:this={catList}>
          <table class="cat-table">
            <thead><tr><th>{t('Name')}</th><th>{t('Group')}</th><th>{t('Description')}</th><th></th></tr></thead>
            <tbody>
              {#each categories as row, i (i)}
                <tr>
                  <td class="strong">{row.name || row.key}</td>
                  <td>{row.group || '–'}</td>
                  <td class="desc"><span class="ellipsis">{row.description}</span></td>
                  <td class="acts">
                    <button class="icon-btn" title={t('Edit')} aria-label={t('Edit')} onclick={() => (editing = { index: i, row: { ...$state.snapshot(row) } })}><Icon name="edit" size={15} /></button>
                    <button class="icon-btn" title={t('Remove')} aria-label={t('Remove')} onclick={() => { categories.splice(i, 1); categoriesDirty = true; }}><Icon name="trash" size={15} /></button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {:else if section === 'lights'}
        <label class="check"><input type="checkbox" bind:checked={form.lightsEnabled} /> {t('Enabled')} ({t('Wiz Lights')})</label>
        <label class="field">{t('Broadcast Space')}<input type="text" bind:value={form.lightsBroadcastIP} />
          <span class="muted small">{t('Take the ip address of you local wlan network and replace the last number with 255.')}</span></label>
        <label class="field">{t('Timeout')} (s)<input type="number" min="1" max="60" step="0.5" bind:value={form.lightsTimeout} />
          <span class="muted small">{t('Time to search for bulbs in seconds')}</span></label>
      {:else if section === 'agents'}
        <span class="muted small">{t('Programs on other machines that connect to this server: WiZ light agents (see agents/wiz), Voxalyzer analysis agents (see agents/voxalyzer) and YouTube download agents (see agents/youtube).')}</span>
        <section class="group">
          <h4>{t('Connected agents')} <span class="count">{agents?.connected.length ?? 0}</span></h4>
          {#each agents?.connected ?? [] as agent (agent.id)}
            <div class="item">
              <span class="dot on" title={t('Connected agents')}></span>
              <div class="info">
                <strong>{t(agentLabels[agent.kind] ?? agent.kind)}</strong>
                <span class="meta"><span>{agent.name}</span>{#if agent.user}<span class="pill violet">{agent.user}</span>{/if}</span>
              </div>
              {#if admin || agent.user === data.auth?.user}<button class="icon-btn" title={t('Remove')} onclick={() => removeAgent(agent)}><Icon name="trash" size={14} /></button>{/if}
            </div>
          {:else}
            <p class="empty">{t('No agent connected')}</p>
          {/each}
        </section>
        <section class="group">
          <h4>{t('Agent tokens')} <span class="count">{agents?.tokens.length ?? 0}</span></h4>
          {#each agents?.tokens ?? [] as token (token.id)}
            <div class="item">
              <span class="dot" class:on={!!token.used}></span>
              <div class="info">
                <strong>{token.name || t('Unnamed')}</strong>
                <span class="meta">
                  {#if admin}<span class="pill violet">{token.user}</span>{/if}
                  <span>{t('Created {0}', new Date(token.created * 1000).toLocaleDateString())}</span>
                  <span>{token.used ? t('Last used {0}', new Date(token.used * 1000).toLocaleString()) : t('Never used')}</span>
                </span>
              </div>
              <button class="icon-btn" title={t('Remove')} onclick={() => deleteAgentToken(token)}><Icon name="trash" size={14} /></button>
            </div>
          {:else}
            <p class="empty">{t('No agent token yet')}</p>
          {/each}
          <div class="row create">
            <input type="text" class="grow" placeholder={t('Name of the token (e.g. the computer)')} bind:value={tokenName} />
            <button class="btn" onclick={createAgentToken}><Icon name="plus" size={14} /> {t('Create agent token')}</button>
          </div>
        </section>
        {#if admin}
        <h4>{t('Cloud analysis')}</h4>
        <span class="muted small">{t('Analyzes on demand in a cloud function (Modal, see agents/voxalyzer/modal_app.py) when no agent is connected. Create a proxy auth token in the Modal dashboard for the key and the secret; they are never sent back to the browser.')}</span>
        <span class="small">{cloud.configured ? t('Configured ({0})', cloud.host ?? '') : t('Not configured')}</span>
        <label class="field">{t('Endpoint URL')}<input type="url" placeholder="https://…modal.run" bind:value={cloudUrl} /></label>
        <label class="field">{t('Key')}<input type="text" autocomplete="off" placeholder="wk-…" bind:value={cloudKey} /></label>
        <label class="field">{t('Secret')}<input type="password" autocomplete="off" placeholder="ws-…" bind:value={cloudSecret} /></label>
        <div class="row">
          <button class="btn" disabled={!cloudUrl.trim() || !cloudKey.trim() || !cloudSecret.trim()} onclick={saveCloud}>{t('Save')}</button>
          {#if cloud.configured}<button class="btn danger" onclick={removeCloud}>{t('Remove')}</button>{/if}
        </div>
        {/if}
      {:else if section === 'player'}
        <label class="check"><input type="checkbox" checked={prefs.crossfade} onchange={(e) => { prefs.crossfade = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Crossfade')}</label>
        <span class="muted small">{t('The next song fades in while the current one fades out.')}</span>
        <label class="check"><input type="checkbox" checked={prefs.normalize} onchange={(e) => setNormalize((e.currentTarget as HTMLInputElement).checked)} /> {t('Normalize Volume')}</label>
        <span class="muted small">{t('All songs will be played at a normalized volume.')}</span>
        <label class="check"><input type="checkbox" checked={prefs.dynamicScore} onchange={(e) => { prefs.dynamicScore = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Dynamic Score Column')}</label>
        <span class="muted small">{t('Shows the match score column only while a filter is active.')}</span>
        <label class="check"><input type="checkbox" checked={prefs.dynamicColumns} onchange={(e) => { prefs.dynamicColumns = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Dynamic Category Columns')}</label>
        <span class="muted small">{t('Shows the BPM and mood columns only when the filter uses them.')}</span>
      {:else if section === 'security'}
        {#if !admin}
          <p>{t('Signed in as {0}', data.auth?.user ?? '')}</p>
        {:else}
          {#if data.auth?.local}
            <p class="muted">{t('The desktop app only accepts connections from this computer. A password is needed when running as a server for other devices.')}</p>
          {/if}
          <p>{data.auth?.password_set ? t('A password is set.') : t('No password is set – only this computer can connect.')}</p>
        {/if}
        <label class="field">{t('New password')}<input type="password" bind:value={password} autocomplete="new-password" /></label>
        <label class="field">{t('Repeat password')}<input type="password" bind:value={password2} autocomplete="new-password" /></label>
        <div class="row">
          <button class="btn primary" onclick={() => changePassword()}>{t('Set password')}</button>
          {#if admin && data.auth?.password_set}<button class="btn danger" onclick={() => changePassword(true)}>{t('Remove password')}</button>{/if}
        </div>
        {#if admin}<UsersPanel />{/if}
        {#if admin && data.auth?.local}
          <h4>{t('Share on network')}</h4>
          <label class="check"><input type="checkbox" bind:checked={form.shareOnNetwork} disabled={!data.auth?.password_set} />
            {t('Let tablets and phones in this network connect (requires a password and a restart)')}</label>
          <label class="field">{t('Port')}<input type="number" min="1024" max="65535" bind:value={form.sharePort} disabled={!form.shareOnNetwork} /></label>
          {#if form.shareOnNetwork}<p class="muted small">{t('After restarting, open {0} on the other device.', form.networkUrl)}</p>{/if}
        {/if}
      {/if}
    </div>
  </div>
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={saving} onclick={save}>{t('Save')}</button>
  {/snippet}

  {#if newToken}
    <AgentTokenDialog token={newToken.token} name={newToken.name} onclose={() => (newToken = null)} />
  {/if}
  {#if editing}
    <CategoryEditDialog row={editing.row} onsave={saveCategory} onclose={() => (editing = null)} />
  {/if}
</Modal>

<style>
  .layout { display: grid; grid-template-columns: 170px 1fr; gap: 18px; min-height: 380px; }
  nav { display: flex; flex-direction: column; gap: 2px; }
  nav button { display: flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: var(--radius-sm); text-align: left; color: var(--muted); }
  nav button:hover { background: var(--hover); color: var(--text); }
  nav button.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .body { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
  .field { display: flex; flex-direction: column; gap: 5px; }
  .check { display: flex; align-items: center; gap: 8px; }
  h4 { margin: 8px 0 0; }
  .small { font-size: var(--fs-xs); }
  .row { display: flex; gap: 8px; }
  .swatches { display: flex; flex-wrap: wrap; gap: 10px; }
  .swatch { width: 34px; height: 34px; border-radius: 50%; border: 2px solid transparent; display: grid; place-items: center; color: #fff; cursor: pointer; box-shadow: var(--shadow-sm); }
  .swatch:hover { transform: scale(1.08); }
  .swatch.selected { border-color: var(--text); }
  .group { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
  .group h4 { margin: 0 0 2px; display: flex; align-items: center; gap: 8px; font-size: var(--fs-lg); }
  .count { font-size: var(--fs-xs); font-weight: 600; padding: 1px 8px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
  .item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); }
  .item .info { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .meta { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 12px; font-size: var(--fs-xs); color: var(--muted); }
  .dot { width: 9px; height: 9px; flex: none; border-radius: 50%; background: var(--border-strong); }
  .dot.on { background: var(--green); box-shadow: 0 0 0 3px var(--green-soft); }
  .empty { margin: 0; color: var(--muted); font-size: var(--fs-sm); }
  .create { padding-top: 6px; border-top: 1px dashed var(--border-strong); }
  .grow { flex: 1; }
  .grow { flex: 1; }
  .storage { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); align-items: center; }
  .storage .id { align-self: center; }
  .storage .actions { justify-content: flex-end; }
  .warn { color: var(--danger, #d9534f); }
  .cat-head { display: flex; align-items: center; gap: 8px; }
  .cats { display: flex; flex-direction: column; gap: 10px; max-height: 420px; overflow: auto; padding-right: 4px; }
  .cat-table { width: 100%; border-collapse: collapse; font-size: var(--fs-sm); }
  .cat-table th { text-align: left; font-size: var(--fs-xs); font-weight: 650; text-transform: uppercase; letter-spacing: 0.06em; color: var(--faint); padding: 4px 8px; }
  .cat-table td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: middle; }
  .cat-table .strong { font-weight: 600; }
  .cat-table .desc { max-width: 220px; color: var(--muted); }
  .cat-table .desc .ellipsis { display: block; }
  .cat-table .acts { white-space: nowrap; text-align: right; width: 72px; }
  @media (max-width: 640px) { .layout { grid-template-columns: 1fr; } nav { flex-direction: row; flex-wrap: wrap; } }
</style>
