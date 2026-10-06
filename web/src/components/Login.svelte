<script lang="ts">
  import { api } from '../lib/api';
  import { data } from '../lib/stores/data.svelte';
  import { t } from '../lib/i18n.svelte';

  let { onLogin }: { onLogin: () => void } = $props();
  let username = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);

  async function submit(event: SubmitEvent) {
    event.preventDefault();
    busy = true;
    error = null;
    try {
      await api.login(username.trim(), password);
      onLogin();
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      busy = false;
    }
  }
</script>

<div class="wrap">
  <form class="panel card" onsubmit={submit}>
    <img src="/icon.png" alt="" width="56" height="56" />
    <h1>Dungeon Tuber</h1>
    {#if data.auth && !data.auth.password_set}
      <p class="muted">{t('No password is set on the server. Only the server machine can connect – run "python -m server --set-password".')}</p>
    {:else}
      <label>
        <span class="label-xs">{t('User name')}</span>
        <!-- svelte-ignore a11y_autofocus -->
        <input type="text" bind:value={username} placeholder="admin" autocomplete="username" autofocus />
      </label>
      <label>
        <span class="label-xs">{t('Password')}</span>
        <input type="password" bind:value={password} autocomplete="current-password" />
      </label>
      {#if error}<p class="error">{error}</p>{/if}
      <button class="btn primary" type="submit" disabled={busy || !password}>{t('Login')}</button>
    {/if}
  </form>
</div>

<style>
  .wrap { height: 100%; display: grid; place-items: center; padding: 16px; }
  .card { width: min(360px, 100%); padding: 28px; display: flex; flex-direction: column; gap: 14px; align-items: stretch; text-align: center; }
  .card img { align-self: center; }
  h1 { margin: 0; font-size: 22px; }
  label { display: flex; flex-direction: column; gap: 6px; text-align: left; }
  .error { color: var(--red); margin: 0; }
</style>
