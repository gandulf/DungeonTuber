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
  import type { AgentInfo, AgentState, AgentToken, AssistantStatus, CloudStatus, KeySource, MetadataStatus, MusicCategory, ServerSettings, StorageConfig } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import { onEvent } from '../../lib/ws';
  import { keyField, secretField } from '../../lib/autofill';
  import CloudConnectionDialog from './CloudConnectionDialog.svelte';
  import Modal from './Modal.svelte';
  import UsersPanel, { type PasswordRequest } from './UsersPanel.svelte';

  type Section = 'general' | 'library' | 'categories' | 'lights' | 'analyzer' | 'agents' | 'youtube' | 'assistant' | 'player' | 'security';
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

  let cloud = $state<CloudStatus>({ configured: false, host: null, source: null });
  if (admin) void api.cloudAnalysis().then((result) => (cloud = result)).catch(() => {});

  /** The popup that takes the URL, key and secret of a cloud function on Modal (they are never shown again once stored). */
  let connection = $state<{ title: string; save: (url: string, key: string, secret: string) => Promise<void> } | null>(null);
  const editConnection = (title: string, save: (url: string, key: string, secret: string) => Promise<void>) => (connection = { title, save });

  async function saveCloud(url: string, key: string, secret: string) {
    cloud = await api.putCloudAnalysis(url, key, secret);
    toast(t('Cloud analysis saved'), 'success');
  }

  let metadata = $state<MetadataStatus | null>(null);
  let acoustidKey = $state('');
  if (admin) void api.metadataConfig().then((result) => (metadata = result)).catch(() => {});

  async function saveAcoustid() {
    try {
      metadata = await api.putMetadataConfig(acoustidKey);
      acoustidKey = '';
      toast(t('AcoustID key saved'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeAcoustid() {
    if (!(await askConfirm(t('Remove the AcoustID key?')))) return;
    try {
      metadata = await api.deleteMetadataConfig();
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

  let musicGen = $state<CloudStatus>({ configured: false, host: null, source: null });

  /** " · from the environment variable DT_…" for a value the server got from its environment (it cannot be removed here). */
  const fromEnv = (source: KeySource | undefined, variable: string) => (source === 'environment' ? ` · ${t('from the environment variable {0}', variable)}` : '');
  if (admin) void api.musicGenConfig().then((result) => (musicGen = result)).catch(() => {});

  async function saveMusicGen(url: string, key: string, secret: string) {
    musicGen = await api.putMusicGenConfig(url, key, secret);
    if (data.settings) data.settings.musicGenConfigured = musicGen.configured;
    toast(t('Music generation saved'), 'success');
  }

  let soundGen = $state<CloudStatus>({ configured: false, host: null, source: null });
  if (admin) void api.soundGenConfig().then((result) => (soundGen = result)).catch(() => {});

  async function saveSoundGen(url: string, key: string, secret: string) {
    soundGen = await api.putSoundGenConfig(url, key, secret);
    if (data.settings) data.settings.soundGenConfigured = soundGen.configured;
    toast(t('Sound generation saved'), 'success');
  }

  async function removeSoundGen() {
    if (!(await askConfirm(t('Remove the sound generation settings?')))) return;
    try {
      soundGen = await api.deleteSoundGenConfig();
      if (data.settings) data.settings.soundGenConfigured = soundGen.configured;
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeMusicGen() {
    if (!(await askConfirm(t('Remove the music generation settings?')))) return;
    try {
      musicGen = await api.deleteMusicGenConfig();
      if (data.settings) data.settings.musicGenConfigured = musicGen.configured;
    } catch (e) {
      errorToast(e);
    }
  }

  let assistantStatus = $state<AssistantStatus | null>(null);
  let assistantKey = $state('');
  let assistantModel = $state('');
  type InstructionMode = 'music' | 'smart' | 'compose' | 'effects' | 'general';
  /** The additional instructions, one tab per mode of the assistant. */
  const INSTRUCTION_TABS: { mode: InstructionMode; label: string; icon: string; placeholder: string; hint: string; promptHint: string }[] = [
    { mode: 'music', label: 'New music', icon: 'music',
      placeholder: 'e.g. We play Pathfinder in a dark fantasy world. Prefer instrumental film and game soundtracks without vocals.',
      hint: 'Added to every request, so the assistant better understands your game, setting and taste in music.',
      promptHint: 'The built-in prompt sets the task and the answer format; your instructions above are added to it. The format of the song list is enforced anyway.' },
    { mode: 'smart', label: 'Smart search', icon: 'sliders',
      placeholder: 'e.g. Exploration should stay calm, fights need high energy. Prefer songs without vocals.',
      hint: 'Added to every smart search. When empty, the instructions for the song suggestions are used as background (game, setting, taste).',
      promptHint: 'The built-in prompt sets the task and the rules. Keep {categories}, {tags}, {genres}, {min} and {max}: they are replaced by the categories, tags and genres of your library.' },
    { mode: 'compose', label: 'Compose', icon: 'wand',
      placeholder: 'e.g. We play DSA in Aventuria. Thorwal sounds Nordic with tagelharpa and drums, the elves ethereal with harp and flute.',
      hint: 'Added to every new piece the assistant describes for the music generation: setting, regions, instruments, taste. The instructions for the song suggestions are not used there.',
      promptHint: 'The built-in prompt tells the AI how to write the description and the lyrics for ACE-Step. Depending on the vocals option one of the two rules is added, with vocals also the length of the lyrics.' },
    { mode: 'effects', label: 'Effects', icon: 'waves',
      placeholder: 'e.g. We play DSA in Aventuria. Dungeons are damp and echoing, magic sounds crystalline and bright rather than electronic.',
      hint: 'Added to every sound the assistant describes for the sound generation: setting, places, how magic and creatures sound.',
      promptHint: 'The built-in prompt tells the AI how to describe sound effects, ambiences and background music for Stable Audio. The kind of sound chosen in the assistant is added to it.' },
    { mode: 'general', label: 'General', icon: 'mask', placeholder: 'e.g. We play DSA 4.1 with the core rules and the Aventurian Compendium.',
      hint: 'Added to every question of the general chat: the rules edition, the setting, house rules or the heroes.',
      promptHint: 'The built-in prompt sets the role of the assistant; your instructions above are added to it.' },
  ];
  /** Names of the parts of a prompt that has more than one (the compose mode). */
  const PROMPT_PARTS: Record<string, string> = {
    'compose.system': 'Prompt', 'compose.instrumental': 'Rules for instrumental pieces', 'compose.vocals': 'Rules for pieces with vocals',
  };
  /** The built-in prompts as edited here, by name ("compose.vocals"). */
  let prompts = $state<Record<string, string>>({});
  const promptsOf = (mode: InstructionMode) => (assistantStatus?.prompts ?? []).filter((entry) => entry.name.startsWith(`${mode}.`));
  const isDefault = (entry: { name: string; default: string }) => (prompts[entry.name] ?? '').trim() === entry.default.trim();
  const promptsChanged = (status: AssistantStatus) => status.prompts.some((entry) => (prompts[entry.name] ?? '').trim() !== entry.value.trim());
  let instructionTab = $state<InstructionMode>('music');
  let instructions = $state<Record<InstructionMode, string>>({ music: '', smart: '', compose: '', effects: '', general: '' });
  const storedInstructions = (status: AssistantStatus): Record<InstructionMode, string> =>
    ({ music: status.instructions, smart: status.smartInstructions, compose: status.composeInstructions, effects: status.effectsInstructions,
       general: status.generalInstructions });
  let assistantModels = $state<{ id: string; name: string }[]>([]);
  let groqKey = $state('');
  let groqModel = $state('');
  if (admin) void api.assistantConfig().then(applyAssistant).catch(() => {});

  /** The models of Google (with a stored key) or a built-in list; a stored model that is not listed stays selectable. */
  const modelOptions = $derived.by(() => {
    const current = assistantModel.trim();
    return current && !assistantModels.some((m) => m.id === current) ? [...assistantModels, { id: current, name: current }] : assistantModels;
  });

  async function loadAssistantModels() {
    try {
      assistantModels = (await api.assistantModels()).models;
    } catch {
      // keeps the previous list
    }
  }

  function applyAssistant(result: AssistantStatus) {
    const keyAdded = result.configured && !assistantStatus?.configured;
    if (keyAdded || !assistantModels.length) void loadAssistantModels();
    assistantStatus = result;
    assistantModel = result.model;
    instructions = storedInstructions(result);
    prompts = Object.fromEntries(result.prompts.map((entry) => [entry.name, entry.value]));
    assistantKey = '';
    groqModel = result.groqModel;
    groqKey = '';
    if (data.settings) {
      data.settings.assistantConfigured = result.configured;
      data.settings.groqConfigured = result.groqConfigured;
    }
  }

  async function saveGroq() {
    try {
      applyAssistant(await api.putAssistantConfig({ ...(groqKey.trim() ? { groqKey: groqKey.trim() } : {}), groqModel: groqModel.trim() }));
      toast(t('Groq saved'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeGroq() {
    if (!(await askConfirm(t('Remove the Groq API key?')))) return;
    try {
      applyAssistant(await api.deleteAssistantConfig('groq'));
    } catch (e) {
      errorToast(e);
    }
  }

  const assistantPayload = () => ({ ...(assistantKey.trim() ? { key: assistantKey.trim() } : {}), model: assistantModel.trim(),
    instructions: instructions.music.trim(), smartInstructions: instructions.smart.trim(), composeInstructions: instructions.compose.trim(),
    effectsInstructions: instructions.effects.trim(), generalInstructions: instructions.general.trim(), prompts: { ...prompts } });

  async function saveAssistant() {
    try {
      applyAssistant(await api.putAssistantConfig(assistantPayload()));
      toast(t('AI assistant saved'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function removeAssistant() {
    if (!(await askConfirm(t('Remove the API key of the AI assistant?')))) return;
    try {
      applyAssistant(await api.deleteAssistantConfig());
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

  let saving = $state(false);

  async function save() {
    saving = true;
    try {
      const changed: Partial<Record<keyof ServerSettings, unknown>> = {};
      const keys: (keyof ServerSettings)[] = ['locale', 'skipAnalyzedMusic', 'skipNormalizedMusic', 'lightsEnabled', 'lightsBroadcastIP', 'lightsTimeout', 'shareOnNetwork', 'sharePort'];
      for (const key of keys) if (form[key] !== s[key]) changed[key] = form[key];
      const rootList = roots.split('\n').map((r) => r.trim()).filter(Boolean);
      if (desktop && rootList.join('\n') !== s.libraryRoots.join('\n')) changed.libraryRoots = rootList;
      if (admin && proxy.trim() !== proxySaved) await api.putYoutubeProxy(proxy);
      const stored = assistantStatus && storedInstructions(assistantStatus);
      if (admin && assistantStatus && stored && (assistantKey.trim() || assistantModel.trim() !== assistantStatus.model
          || INSTRUCTION_TABS.some(({ mode }) => instructions[mode].trim() !== stored[mode]) || promptsChanged(assistantStatus))) {
        applyAssistant(await api.putAssistantConfig(assistantPayload()));
      }
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

  // --- password dialog (own password, new users, passwords of other users) -----------------------------------------

  let passwordDialog = $state<PasswordRequest | null>(null);
  let pwName = $state('');
  let password = $state('');
  let password2 = $state('');
  let pwBusy = $state(false);
  const pwValid = $derived((!passwordDialog?.withName || pwName.trim().length >= 2) && password.length >= 4 && password === password2);

  function askPassword(request: PasswordRequest) {
    pwName = password = password2 = '';
    passwordDialog = request;
  }

  async function submitPassword(event: SubmitEvent) {
    event.preventDefault();
    if (!passwordDialog || !pwValid || pwBusy) return;
    pwBusy = true;
    try {
      await passwordDialog.onsubmit(password, pwName.trim());
      passwordDialog = null;
    } catch (e) {
      errorToast(e);
    } finally {
      pwBusy = false;
    }
  }

  function changeOwnPassword() {
    askPassword({
      title: admin && !data.auth?.password_set ? t('Set password') : t('Change password'),
      subtitle: admin ? t('The password of the SuperAdmin ({0}).', data.auth?.user ?? 'admin') : t('Signed in as {0}', data.auth?.user ?? ''),
      submitLabel: t('Save'),
      onsubmit: async (value) => {
        if (!admin) await api.setOwnPassword(value);
        else {
          const result = await api.setPassword(value);
          if (data.auth) data.auth.password_set = result.password_set;
        }
        toast(t('Password changed'), 'success');
      },
    });
  }

  async function removePassword() {
    if (!(await askConfirm(t('Remove the password? Then only this computer can connect.')))) return;
    try {
      const result = await api.setPassword(null);
      if (data.auth) data.auth.password_set = result.password_set;
      toast(t('Password removed'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  const sections: [Section, string, string][] = [
    ['general', 'General', 'settings'],
    ['library', 'Library', 'folder'],
    ['categories', 'Categories', 'sliders'],
    ['lights', 'Lights', 'bulb'],
    ['analyzer', 'Analyzer', 'waves'],
    ['youtube', 'YouTube', 'download'],
    ['agents', 'Agents', 'cloud'],
    ['assistant', 'AI Assistant', 'sparkles'],
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
            <input type="text" {...keyField} placeholder={row.has_credentials ? t('Access key (unchanged)') : t('Access key')} bind:value={row.access_key} />
            <input type="password" {...secretField} placeholder={row.has_credentials ? t('Secret key (unchanged)') : t('Secret key')} bind:value={row.secret_key} />
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
            <input type="text" {...keyField} placeholder={proxyFromEnv ? t('Default from the server configuration') : 'http://user:password@host:port'} bind:value={proxy} /></label>
          <p class="muted small">{t('All YouTube requests go through this proxy (http, https, socks4 or socks5). Leave empty to use the default of the server (DT_YT_PROXY) or none.')}</p>
        {/if}
      {:else if section === 'assistant'}
        <section class="group">
          <h4><Icon name="edit" size={16} /> {t('Instructions')}</h4>
          <span class="muted small">{t('Your game, the setting and your taste in music, separately for each mode of the assistant. They are added to every request of the mode.')}</span>
          <div class="tabs" role="tablist" aria-label={t('Instructions')}>
            {#each INSTRUCTION_TABS as tab (tab.mode)}
              <button role="tab" class:active={instructionTab === tab.mode} aria-selected={instructionTab === tab.mode} onclick={() => (instructionTab = tab.mode)}>
                <Icon name={tab.icon} size={14} /><span>{t(tab.label)}</span>
                {#if instructions[tab.mode].trim()}<span class="filled" title={t('Instructions')}></span>{/if}
              </button>
            {/each}
          </div>
          {#each INSTRUCTION_TABS.filter((tab) => tab.mode === instructionTab) as tab (tab.mode)}
            <textarea rows="9" maxlength="4000" aria-label={t(tab.label)} placeholder={t(tab.placeholder)} bind:value={instructions[tab.mode]}></textarea>
            <span class="muted small">{t(tab.hint)}</span>
            {@const parts = promptsOf(tab.mode)}
            {#if parts.length}
              <details class="prompt" open={parts.some((entry) => entry.value.trim() !== entry.default.trim())}>
                <summary>{t('Prompt of the assistant')}
                  {#if parts.some((entry) => !isDefault(entry))}<span class="changed">{t('Changed')}</span>{/if}</summary>
                <span class="muted small">{t(tab.promptHint)}</span>
                {#each parts as entry (entry.name)}
                  {#if PROMPT_PARTS[entry.name]}<span class="label-xs">{t(PROMPT_PARTS[entry.name])}</span>{/if}
                  <textarea class="code" rows={entry.name.endsWith('.system') ? 14 : 7} maxlength="12000" spellcheck="false"
                            aria-label={t(PROMPT_PARTS[entry.name] ?? 'Prompt of the assistant')} bind:value={prompts[entry.name]}></textarea>
                  <div class="row">
                    <span class="grow"></span>
                    <button class="btn sm" disabled={isDefault(entry)} onclick={() => (prompts[entry.name] = entry.default)}>
                      <Icon name="refresh" size={13} /> {t('Reset to default')}</button>
                  </div>
                {/each}
              </details>
            {/if}
          {/each}
          <div class="row">
            <span class="grow"></span>
            <button class="btn" disabled={!assistantStatus} onclick={saveAssistant}>{t('Save')}</button>
          </div>
        </section>

        <span class="label-xs services">{t('Services and API keys')}</span>
        <section class="group">
          <h4>Google Gemini</h4>
          <p class="muted small">{t('The AI assistant suggests songs for a scene. It uses Google Gemini: create a free API key in Google AI Studio (aistudio.google.com) and enter it here. The free tier of the Flash models is enough for occasional questions. The key stays on the server and is never sent back to the browser; all users can chat with the assistant.')}</p>
          <span class="small">{assistantStatus?.configured ? t('Configured (key …{0})', assistantStatus.keyHint) + fromEnv(assistantStatus.keySource, 'DT_GEMINI_API_KEY') : t('Not configured')}</span>
          <label class="field">{t('API key')}
            <input type="password" {...secretField} placeholder={assistantStatus?.configured ? t('API key (unchanged)') : 'AIza…'} bind:value={assistantKey} /></label>
          <label class="field">{t('Model')}
            <select bind:value={assistantModel}>
              {#each modelOptions as option (option.id)}
                <option value={option.id}>{option.name}{option.id === assistantStatus?.defaultModel ? ` (${t('Default')})` : ''} – {option.id}</option>
              {/each}
            </select>
            <span class="muted small">{t('Only models of the free tier are offered (Flash and Flash-Lite); Flash-Lite answers faster.')}</span></label>
          <div class="row">
            <a class="btn" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer"><Icon name="lock" size={14} /> {t('Get an API key')}</a>
            <span class="grow"></span>
            <button class="btn" onclick={saveAssistant}>{t('Save')}</button>
            {#if assistantStatus?.keySource === 'settings'}<button class="btn danger" onclick={removeAssistant}>{t('Remove')}</button>{/if}
          </div>
        </section>
        <section class="group">
          <h4>Groq</h4>
          <span class="muted small">{t('The smart search and the composing of the assistant run on Groq when a key is entered (free tier at console.groq.com); the song suggestions and the general chat stay with Gemini, which knows more songs. Without a Groq key Gemini answers everything.')}</span>
          <span class="small">{assistantStatus?.groqConfigured ? t('Configured (key …{0})', assistantStatus.groqKeyHint) + fromEnv(assistantStatus.groqKeySource, 'DT_GROQ_API_KEY') : t('Not configured')}</span>
          <label class="field">{t('API key')}
            <input type="password" {...secretField} placeholder={assistantStatus?.groqConfigured ? t('API key (unchanged)') : 'gsk_…'} bind:value={groqKey} /></label>
          <label class="field">{t('Model')}
            <select bind:value={groqModel}>
              {#each assistantStatus?.groqModels ?? [] as option (option.id)}
                <option value={option.id}>{option.name}{option.id === assistantStatus?.groqDefaultModel ? ` (${t('Default')})` : ''} – {option.id}</option>
              {/each}
            </select></label>
          <div class="row">
            <a class="btn" href="https://console.groq.com/keys" target="_blank" rel="noopener noreferrer"><Icon name="lock" size={14} /> {t('Get an API key')}</a>
            <span class="grow"></span>
            <button class="btn" disabled={!groqKey.trim() && !assistantStatus?.groqConfigured} onclick={saveGroq}>{t('Save')}</button>
            {#if assistantStatus?.groqKeySource === 'settings'}<button class="btn danger" onclick={removeGroq}>{t('Remove')}</button>{/if}
          </div>
        </section>
        <section class="group">
          <h4>{t('Music generation')}</h4>
          <span class="muted small">{t('Composes new pieces for a scene ("Compose" in the assistant) with ACE-Step 1.5 in a cloud function on Modal, see agents/musicgen/modal_app.py. Create a proxy auth token in the Modal dashboard for the key and the secret; they are never sent back to the browser. Without a Groq or Gemini key the description is used as it is.')}</span>
          <span class="small">{musicGen.configured ? t('Configured ({0})', musicGen.host ?? '') + fromEnv(musicGen.source, 'DT_MUSICGEN_URL') : t('Not configured')}</span>
          <div class="row">
            <span class="grow"></span>
            <button class="btn" onclick={() => editConnection(t('Music generation'), saveMusicGen)}>{musicGen.source === 'settings' ? t('Change…') : t('Set up…')}</button>
            {#if musicGen.source === 'settings'}<button class="btn danger" onclick={removeMusicGen}>{t('Remove')}</button>{/if}
          </div>
        </section>
        <section class="group">
          <h4>{t('Sound generation')}</h4>
          <span class="muted small">{t('Creates sound effects, ambiences and background music ("Generate" in the assistant) with Stable Audio 3 in a cloud function on Modal, see agents/soundgen/modal_app.py. Create a proxy auth token in the Modal dashboard for the key and the secret; they are never sent back to the browser. Without a Groq or Gemini key the description is used as it is.')}</span>
          <span class="small">{soundGen.configured ? t('Configured ({0})', soundGen.host ?? '') + fromEnv(soundGen.source, 'DT_SOUNDGEN_URL') : t('Not configured')}</span>
          <div class="row">
            <span class="grow"></span>
            <button class="btn" onclick={() => editConnection(t('Sound generation'), saveSoundGen)}>{soundGen.source === 'settings' ? t('Change…') : t('Set up…')}</button>
            {#if soundGen.source === 'settings'}<button class="btn danger" onclick={removeSoundGen}>{t('Remove')}</button>{/if}
          </div>
        </section>
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
      {:else if section === 'analyzer'}
        <label class="check"><input type="checkbox" bind:checked={form.skipAnalyzedMusic} /> {t('Skip Analyzed Music')}</label>
        <label class="check"><input type="checkbox" bind:checked={form.skipNormalizedMusic} /> {t('Skip Normalized Music')}</label>
        <h4>{t('Cloud analysis')}</h4>
        <span class="muted small">{t('Analyzes on demand in a cloud function (Modal, see agents/voxalyzer/modal_app.py) when no agent is connected. Create a proxy auth token in the Modal dashboard for the key and the secret; they are never sent back to the browser.')}</span>
        <span class="small">{cloud.configured ? t('Configured ({0})', cloud.host ?? '') + fromEnv(cloud.source, 'DT_VOXALYZER_CLOUD_URL') : t('Not configured')}</span>
        <div class="row">
          <button class="btn" onclick={() => editConnection(t('Cloud analysis'), saveCloud)}>{cloud.source === 'settings' ? t('Change…') : t('Set up…')}</button>
          {#if cloud.source === 'settings'}<button class="btn danger" onclick={removeCloud}>{t('Remove')}</button>{/if}
        </div>
        <h4>{t('Metadata lookup')}</h4>
        <span class="muted small">{t('"Normalize metadata…" in the song menu looks up title, artist and album in MusicBrainz. With an AcoustID application key (free for non-commercial use: acoustid.org/new-application) and the program fpcalc (Chromaprint) on the server, songs are also identified by their sound, which also works for badly named files.')}</span>
        <span class="small">{metadata?.configured ? t('Configured (key …{0})', metadata.keyHint) + fromEnv(metadata.keySource, 'DT_ACOUSTID_API_KEY') : t('Not configured')} ·
          {metadata?.fpcalc ? t('fpcalc found') : t('fpcalc not found: install Chromaprint or put fpcalc into the tools folder of Dungeon Tuber')}</span>
        <label class="field">{t('AcoustID application key')}
          <input type="password" {...secretField} placeholder={metadata?.configured ? t('API key (unchanged)') : ''} bind:value={acoustidKey} /></label>
        <div class="row">
          <a class="btn" href="https://acoustid.org/new-application" target="_blank" rel="noopener noreferrer"><Icon name="lock" size={14} /> {t('Get an API key')}</a>
          <span class="grow"></span>
          <button class="btn" disabled={!acoustidKey.trim()} onclick={saveAcoustid}>{t('Save')}</button>
          {#if metadata?.keySource === 'settings'}<button class="btn danger" onclick={removeAcoustid}>{t('Remove')}</button>{/if}
        </div>
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
        <section class="group">
          <h4>{t('Your account')}</h4>
          <div class="item">
            <span class="dot" class:on={!admin || !!data.auth?.password_set}></span>
            <div class="info">
              <strong>{data.auth?.user ?? 'admin'}{#if admin} <span class="pill violet">{t('SuperAdmin')}</span>{/if}</strong>
              <span class="meta">{!admin || data.auth?.password_set ? t('A password is set.') : t('No password is set – only this computer can connect.')}</span>
            </div>
            <button class="btn sm" onclick={changeOwnPassword}><Icon name="lock" size={14} /> {admin && !data.auth?.password_set ? t('Set password') : t('Change password')}</button>
            {#if admin && data.auth?.password_set}
              <button class="icon-btn" title={t('Remove password')} aria-label={t('Remove password')} onclick={removePassword}><Icon name="trash" size={14} /></button>
            {/if}
          </div>
          {#if admin && data.auth?.local}
            <span class="muted small">{t('The desktop app only accepts connections from this computer. A password is needed when running as a server for other devices.')}</span>
          {/if}
        </section>
        {#if admin}<UsersPanel {askPassword} />{/if}
        {#if admin && data.auth?.local}
          <section class="group">
            <h4>{t('Share on network')}</h4>
            <label class="check"><input type="checkbox" bind:checked={form.shareOnNetwork} disabled={!data.auth?.password_set} />
              {t('Let tablets and phones in this network connect (requires a password and a restart)')}</label>
            <label class="field">{t('Port')}<input type="number" min="1024" max="65535" bind:value={form.sharePort} disabled={!form.shareOnNetwork} /></label>
            {#if form.shareOnNetwork}<p class="muted small">{t('After restarting, open {0} on the other device.', form.networkUrl)}</p>{/if}
          </section>
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
  {#if connection}
    <CloudConnectionDialog title={connection.title} save={connection.save} onclose={() => (connection = null)}
      hint={t('The URL that "modal deploy" prints, and the key and secret of a proxy auth token (Modal dashboard: Settings, Proxy Auth Tokens). Stored values are never shown again, so enter all three.')} />
  {/if}
  {#if passwordDialog}
    <Modal title={passwordDialog.title} onclose={() => (passwordDialog = null)} width="420px">
      <form id="password-form" class="pw-form" onsubmit={submitPassword}>
        {#if passwordDialog.subtitle}<p class="muted small">{passwordDialog.subtitle}</p>{/if}
        {#if passwordDialog.withName}
          <label class="field">{t('User name')}<input type="text" bind:value={pwName} autocomplete="off" /></label>
        {/if}
        <label class="field">{t('New password')}<input type="password" bind:value={password} autocomplete="new-password" />
          <span class="muted small">{t('At least 4 characters.')}</span></label>
        <label class="field">{t('Repeat password')}<input type="password" bind:value={password2} autocomplete="new-password" />
          {#if password2 && password !== password2}<span class="warn small">{t('The passwords do not match.')}</span>{/if}</label>
      </form>
      {#snippet footer()}
        <button class="btn" type="button" onclick={() => (passwordDialog = null)}>{t('Cancel')}</button>
        <button class="btn primary" type="submit" form="password-form" disabled={!pwValid || pwBusy}>{passwordDialog?.submitLabel}</button>
      {/snippet}
    </Modal>
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
  .tabs { display: flex; padding: 2px; gap: 2px; border-radius: 9px; background: var(--hover); border: 1px solid var(--border); }
  .tabs button { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; height: 30px; padding: 0 8px; border-radius: 7px;
                 color: var(--muted); font-size: var(--fs-sm); font-weight: 600; white-space: nowrap; }
  .tabs button:hover { color: var(--text); }
  .tabs button.active { background: var(--surface); color: var(--accent); box-shadow: var(--shadow-sm); }
  .filled { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .group textarea { resize: vertical; min-height: 140px; }
  .prompt { padding: 8px 10px; border: 1px dashed var(--border-strong); border-radius: var(--radius-sm); }
  .prompt summary { cursor: pointer; font-size: var(--fs-sm); font-weight: 600; color: var(--muted); display: flex; align-items: center; gap: 8px; }
  .prompt[open] summary { margin-bottom: 6px; }
  .prompt > span, .prompt > textarea { display: block; width: 100%; box-sizing: border-box; }
  .prompt > * + * { margin-top: 6px; }
  .changed { padding: 1px 8px; border-radius: 9px; background: var(--accent-soft); color: var(--accent); font-size: var(--fs-xs); }
  textarea.code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; font-size: var(--fs-xs); line-height: 1.45; min-height: 110px; }
  .services { margin-top: 10px; padding-top: 14px; border-top: 1px solid var(--border); }
  .pw-form { display: flex; flex-direction: column; gap: 12px; }
  .pw-form p { margin: 0; }
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
