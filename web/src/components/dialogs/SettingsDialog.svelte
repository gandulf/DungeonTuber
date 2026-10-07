<script lang="ts">
  import { onDestroy } from 'svelte';
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { data, saveCategories, saveSettings } from '../../lib/stores/data.svelte';
  import { loadEffects } from '../../lib/stores/effects.svelte';
  import { loadLights } from '../../lib/stores/lights.svelte';
  import { setNormalize } from '../../lib/stores/player.svelte';
  import { askConfirm, closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { AgentInfo, MusicCategory, ServerSettings, StorageConfig } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import { onEvent } from '../../lib/ws';
  import Modal from './Modal.svelte';
  import UsersPanel from './UsersPanel.svelte';

  type Section = 'general' | 'library' | 'categories' | 'lights' | 'agents' | 'player' | 'security';
  const admin = data.auth?.is_admin !== false;
  let section = $state<Section>(admin ? 'general' : 'player');

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

  interface CategoryRow { key: string; name: string; group: string; description: string; levels: string }
  const toRow = (c: MusicCategory): CategoryRow => ({
    key: c.key, name: c.name, group: c.group ?? '', description: c.description,
    levels: Object.entries(c.levels).map(([k, v]) => `${k}: ${v}`).join('\n'),
  });
  let categories = $state<CategoryRow[]>(data.categories.map(toRow));
  let categoriesDirty = $state(false);
  let agents = $state<{ tokenSet: boolean; connected: AgentInfo[] } | null>(null);
  let agentToken = $state('');
  void api.agents().then((result) => (agents = result)).catch(() => {});
  const stopAgentEvents = onEvent('agents.state', (connected) => agents && (agents = { ...agents, connected }));
  onDestroy(stopAgentEvents);
  const agentLabels: Record<string, string> = { lights: 'WiZ light agent', voxalyzer: 'Voxalyzer analysis agent' };

  async function removeAgent(agent: AgentInfo) {
    const label = t(agentLabels[agent.kind] ?? agent.kind);
    if (!(await askConfirm(t('Remove {0}? It disconnects and does not reconnect.', `${label} (${agent.name})`)))) return;
    try {
      const result = await api.removeAgent(agent.kind);
      if (agents) agents = { ...agents, connected: result.connected };
    } catch (e) {
      errorToast(e);
    }
  }

  async function createAgentToken() {
    if (agents?.tokenSet && !(await askConfirm(t('A new token locks out agents that use the current one. Continue?')))) return;
    try {
      agentToken = (await api.createAgentToken()).token;
      agents = await api.agents();
    } catch (e) {
      errorToast(e);
    }
  }

  let password = $state('');
  let password2 = $state('');
  let saving = $state(false);

  function parseLevels(text: string): Record<string, string> {
    const levels: Record<string, string> = {};
    for (const line of text.split('\n')) {
      const match = line.match(/^\s*(\d+)\s*[:=]\s*(.+)$/);
      if (match) levels[match[1]] = match[2].trim();
    }
    return levels;
  }

  async function save() {
    saving = true;
    try {
      const changed: Partial<Record<keyof ServerSettings, unknown>> = {};
      const keys: (keyof ServerSettings)[] = ['locale', 'skipAnalyzedMusic', 'lightsEnabled', 'lightsBroadcastIP', 'lightsTimeout', 'effectsDirectory', 'shareOnNetwork', 'sharePort'];
      for (const key of keys) if (form[key] !== s[key]) changed[key] = form[key];
      const rootList = roots.split('\n').map((r) => r.trim()).filter(Boolean);
      if (rootList.join('\n') !== s.libraryRoots.join('\n')) changed.libraryRoots = rootList;
      if (Object.keys(changed).length) await saveSettings(changed);
      if ('effectsDirectory' in changed || 'libraryRoots' in changed) void loadEffects();
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
          list.push({ key, name: row.name.trim() || key, group: row.group.trim(), description: row.description, levels: parseLevels(row.levels) });
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
    categories.push({ key: '', name: t('New Category'), group: '', description: '', levels: '1: \n5: \n10: ' });
    categoriesDirty = true;
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
    ['agents', 'Agents', 'cloud'],
    ['player', 'Player', 'play'],
    ['security', 'Security', 'power'],
  ];
</script>

<Modal title={t('Settings')} onclose={closeDialog} width="820px">
  <div class="layout">
    <nav>
      {#each sections.filter(([key]) => admin || ['categories', 'player', 'security'].includes(key)) as [key, label, icon] (key)}
        <button class:active={section === key} onclick={() => (section = key)}><Icon name={icon} size={16} /> {t(label)}</button>
      {/each}
    </nav>
    <div class="body">
      {#if section === 'general'}
        <label class="field">{t('Language')}
          <select bind:value={form.locale}>
            <option value="">{t('System Default')}</option>
            {#each data.locales as locale (locale)}<option value={locale}>{t(locale)}</option>{/each}
          </select>
        </label>
        <h4>{t('Analyzer')}</h4>
        <label class="check"><input type="checkbox" bind:checked={form.skipAnalyzedMusic} /> {t('Skip Analyzed Music')}</label>
      {:else if section === 'library'}
        <label class="field">{t('Library folders (one per line, paths on the server)')}
          <textarea rows="5" bind:value={roots}></textarea></label>
        <label class="field">{t('Select Effects Directory')}
          <input type="text" bind:value={form.effectsDirectory} placeholder="C:/Music/Effects" /></label>
        <p class="muted small">{t('Only files inside these folders are accessible through the web interface.')}</p>
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
      {:else if section === 'categories'}
        <div class="cat-head">
          <span class="muted small">{t('Levels: one "value: description" per line')}</span>
          <span class="grow"></span>
          <button class="btn" onclick={addCategory}><Icon name="plus" size={14} /> {t('Add')}</button>
          <button class="btn danger" onclick={resetCategories}>{t('Reset All')}</button>
        </div>
        <div class="cats">
          {#each categories as row, i (i)}
            <div class="cat" oninput={() => (categoriesDirty = true)} role="group">
              <input type="text" placeholder={t('Key')} bind:value={row.key} />
              <input type="text" placeholder={t('Name')} bind:value={row.name} />
              <input type="text" placeholder={t('Group')} bind:value={row.group} />
              <button class="icon-btn" title={t('Remove')} onclick={() => { categories.splice(i, 1); categoriesDirty = true; }}><Icon name="trash" size={15} /></button>
              <textarea rows="2" placeholder={t('Description')} bind:value={row.description}></textarea>
              <textarea rows="3" placeholder="1: low&#10;5: medium&#10;10: high" bind:value={row.levels}></textarea>
            </div>
          {/each}
        </div>
      {:else if section === 'lights'}
        <label class="check"><input type="checkbox" bind:checked={form.lightsEnabled} /> {t('Enabled')} ({t('Wiz Lights')})</label>
        <label class="field">{t('Broadcast Space')}<input type="text" bind:value={form.lightsBroadcastIP} />
          <span class="muted small">{t('Take the ip address of you local wlan network and replace the last number with 255.')}</span></label>
        <label class="field">{t('Timeout')} (s)<input type="number" min="1" max="60" step="0.5" bind:value={form.lightsTimeout} />
          <span class="muted small">{t('Time to search for bulbs in seconds')}</span></label>
      {:else if section === 'agents'}
        <span class="muted small">{t('Programs on other machines that connect to this server: WiZ light agents (see agents/wiz) and Voxalyzer analysis agents (see agents/voxalyzer).')}</span>
        <div class="field">
          <span>{t('Connected agents')}</span>
          {#each agents?.connected ?? [] as agent (agent.kind)}
            <div class="row agent">
              <span class="grow">{t(agentLabels[agent.kind] ?? agent.kind)} <span class="muted small">{agent.name}</span></span>
              <button class="icon-btn" title={t('Remove')} onclick={() => removeAgent(agent)}><Icon name="trash" size={14} /></button>
            </div>
          {:else}
            <span class="muted small">{t('No agent connected')}</span>
          {/each}
        </div>
        <div class="field">
          <span>{t('Agent token')}</span>
          {#if agentToken}
            <input type="text" readonly value={agentToken} onfocus={(e) => e.currentTarget.select()} />
            <span class="muted small">{t('Copy this token now, it is only shown once. Start the agent with --token.')}</span>
          {/if}
          <div class="row"><button class="btn" onclick={createAgentToken}>{agents?.tokenSet ? t('New agent token') : t('Create agent token')}</button></div>
        </div>
      {:else if section === 'player'}
        <p class="muted small">{t('These settings are stored in this browser.')}</p>
        <label class="check"><input type="checkbox" checked={prefs.crossfade} onchange={(e) => { prefs.crossfade = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Crossfade')}</label>
        <label class="check"><input type="checkbox" checked={prefs.normalize} onchange={(e) => setNormalize((e.currentTarget as HTMLInputElement).checked)} /> {t('Normalize Volume')}</label>
        <span class="muted small">{t('All songs will be played at a normalized volume.')}</span>
        <label class="check"><input type="checkbox" checked={prefs.dynamicScore} onchange={(e) => { prefs.dynamicScore = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Dynamic Score Column')}</label>
        <label class="check"><input type="checkbox" checked={prefs.dynamicColumns} onchange={(e) => { prefs.dynamicColumns = (e.currentTarget as HTMLInputElement).checked; savePrefs(); }} /> {t('Dynamic Category Columns')}</label>
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
  .row.agent { align-items: center; }
  .grow { flex: 1; }
  .grow { flex: 1; }
  .storage { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); align-items: center; }
  .storage .id { align-self: center; }
  .storage .actions { justify-content: flex-end; }
  .warn { color: var(--danger, #d9534f); }
  .cat-head { display: flex; align-items: center; gap: 8px; }
  .cats { display: flex; flex-direction: column; gap: 10px; max-height: 420px; overflow: auto; padding-right: 4px; }
  .cat { display: grid; grid-template-columns: 1fr 1.3fr 1fr auto; gap: 6px; padding: 10px; border: 1px solid var(--border); border-radius: var(--radius); }
  .cat textarea:first-of-type { grid-column: 1 / 3; }
  .cat textarea:last-of-type { grid-column: 3 / 5; }
  @media (max-width: 640px) { .layout { grid-template-columns: 1fr; } nav { flex-direction: row; flex-wrap: wrap; } }
</style>
