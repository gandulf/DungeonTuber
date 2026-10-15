<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { AgentInfo } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import IpInput from '../IpInput.svelte';

  /** What the server configures on a light agent: the broadcast address of the bulb network and the time to wait for bulbs. */
  let { agent, onsaved }: { agent: AgentInfo; onsaved: (connected: AgentInfo[]) => void } = $props();

  // svelte-ignore state_referenced_locally
  let broadcast = $state(agent.settings?.broadcast ?? '');
  // a number input binds a number (or null when it is empty), not a string
  // svelte-ignore state_referenced_locally
  let wait = $state<number | null>(agent.settings?.wait ?? null);
  let busy = $state(false);

  async function save() {
    busy = true;
    try {
      const result = await api.putAgentSettings(agent.id, { broadcast: broadcast.trim() || null, wait: wait ? Number(wait) : null });
      onsaved(result.connected);
      toast(t('Agent settings saved'), 'success');
    } catch (e) {
      errorToast(e);
    } finally {
      busy = false;
    }
  }
</script>

<form class="settings" onsubmit={(e) => { e.preventDefault(); void save(); }}>
  <div class="broadcast">
    <span>{t('Broadcast Space')}</span>
    <IpInput bind:value={broadcast} label={t('Broadcast Space')} broadcast />
  </div>
  <label class="short">{t('Timeout')} (s)
    <input type="number" min="1" max="60" step="0.5" bind:value={wait} />
  </label>
  <button class="btn sm" type="submit" disabled={busy}><Icon name="check" size={14} /> {t('Save')}</button>
  <span class="muted small hint">{t('Sent to the agent at once and whenever it connects. An empty field uses the value of the agent itself.')}</span>
</form>

<style>
  .settings { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 8px 12px; padding: 0 0 10px 22px; }
  label, .broadcast { display: flex; flex-direction: column; gap: 3px; font-size: var(--fs-sm); }
  .short input { width: 90px; }
  .hint { flex-basis: 100%; }
</style>
