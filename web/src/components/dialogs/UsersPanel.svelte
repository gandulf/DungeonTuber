<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { askConfirm, askText, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { UserInfo } from '../../lib/types';
  import Icon from '../Icon.svelte';

  let users = $state<UserInfo[]>([]);
  let name = $state('');
  let password = $state('');

  async function load() {
    try {
      users = await api.users();
    } catch (e) {
      errorToast(e);
    }
  }

  $effect(() => {
    void load();
  });

  async function add(event: SubmitEvent) {
    event.preventDefault();
    try {
      await api.createUser(name.trim(), password);
      name = password = '';
      await load();
      toast(t('User created'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function reset(user: UserInfo) {
    const value = await askText(t('Set password'), `${t('New password')} (${user.name})`);
    if (!value) return;
    try {
      await api.resetUserPassword(user.name, value);
      toast(t('Password changed'), 'success');
    } catch (e) {
      errorToast(e);
    }
  }

  async function remove(user: UserInfo) {
    if (!(await askConfirm(t('Delete user {0}?', user.name)))) return;
    try {
      await api.deleteUser(user.name);
      await load();
    } catch (e) {
      errorToast(e);
    }
  }
</script>

<h4>{t('Users')}</h4>
<ul class="users">
  {#each users as user (user.name)}
    <li>
      <Icon name={user.admin ? 'power' : 'smile'} size={15} />
      <span class="grow ellipsis">{user.name}{#if user.admin} <span class="muted small">({t('SuperAdmin')})</span>{/if}</span>
      {#if !user.admin}
        <button class="btn sm" onclick={() => reset(user)}>{t('Set password')}</button>
        <button class="icon-btn" title={t('Remove')} onclick={() => remove(user)}><Icon name="trash" size={15} /></button>
      {/if}
    </li>
  {/each}
</ul>
{#if data.auth?.password_set}
  <form class="add" onsubmit={add}>
    <input type="text" placeholder={t('User name')} bind:value={name} autocomplete="off" />
    <input type="password" placeholder={t('Password')} bind:value={password} autocomplete="new-password" />
    <button class="btn primary" type="submit" disabled={name.trim().length < 2 || password.length < 4}><Icon name="plus" size={14} /> {t('Add user')}</button>
  </form>
{:else}
  <p class="muted small">{t('Set the SuperAdmin password first to add users.')}</p>
{/if}

<style>
  .users { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 4px; }
  li { display: flex; align-items: center; gap: 8px; padding: 4px 8px; border: 1px solid var(--border); border-radius: 10px; }
  .grow { flex: 1; min-width: 0; }
  .add { display: flex; gap: 8px; flex-wrap: wrap; }
  .add input { flex: 1; min-width: 120px; }
</style>
