<script lang="ts" module>
  /** What the password dialog of the settings asks for (see SettingsDialog). */
  export interface PasswordRequest {
    title: string;
    subtitle?: string;
    withName?: boolean;
    submitLabel: string;
    onsubmit: (password: string, name: string) => Promise<void>;
  }
</script>

<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { data } from '../../lib/stores/data.svelte';
  import { askConfirm, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { UserInfo } from '../../lib/types';
  import Icon from '../Icon.svelte';

  let { askPassword }: { askPassword: (request: PasswordRequest) => void } = $props();

  let users = $state<UserInfo[]>([]);

  async function load() {
    try {
      users = await api.users();
    } catch (e) {
      errorToast(e);
    }
  }

  onMount(() => void load());

  function add() {
    askPassword({
      title: t('Create user'),
      withName: true,
      submitLabel: t('Create user'),
      onsubmit: async (password, name) => {
        await api.createUser(name, password);
        await load();
        toast(t('User created'), 'success');
      },
    });
  }

  function reset(user: UserInfo) {
    askPassword({
      title: t('Change password'),
      subtitle: t('New password for {0}.', user.name),
      submitLabel: t('Save'),
      onsubmit: async (password) => {
        await api.resetUserPassword(user.name, password);
        toast(t('Password changed'), 'success');
      },
    });
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

  const others = $derived(users.filter((user) => !user.admin));
</script>

<section class="group">
  <div class="head">
    <h4>{t('Users')} <span class="count">{others.length}</span></h4>
    <span class="grow"></span>
    {#if data.auth?.password_set}
      <button class="btn sm primary" onclick={add}><Icon name="plus" size={14} /> {t('Create user')}</button>
    {/if}
  </div>
  {#each others as user (user.name)}
    <div class="item">
      <Icon name="smile" size={15} />
      <div class="grow who">
        <strong class="ellipsis">{user.name}</strong>
        <span class="muted small" title={user.last_seen ? t('Last seen {0}', new Date(user.last_seen * 1000).toLocaleString()) : ''}>
          {user.last_login ? t('Last login {0}', new Date(user.last_login * 1000).toLocaleString()) : t('Never logged in')} · {t('{0} logins', user.logins)} · {t('{0} visits', user.visits)}</span>
      </div>
      <button class="icon-btn" title={t('Change password')} aria-label={t('Change password')} onclick={() => reset(user)}><Icon name="edit" size={14} /></button>
      <button class="icon-btn" title={t('Remove')} aria-label={t('Remove')} onclick={() => remove(user)}><Icon name="trash" size={14} /></button>
    </div>
  {:else}
    <p class="empty">{data.auth?.password_set ? t('No other users yet.') : t('Set the SuperAdmin password first to add users.')}</p>
  {/each}
</section>

<style>
  .group { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border: 1px solid var(--border); border-radius: var(--radius); background: var(--surface-2); }
  .head { display: flex; align-items: center; gap: 8px; }
  h4 { margin: 0 0 2px; display: flex; align-items: center; gap: 8px; font-size: var(--fs-lg); }
  .count { font-size: var(--fs-xs); font-weight: 600; padding: 1px 8px; border-radius: 10px; background: var(--accent-soft); color: var(--accent); }
  .item { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border: 1px solid var(--border); border-radius: var(--radius-sm); background: var(--surface); }
  .grow { flex: 1; min-width: 0; }
  .who { display: flex; flex-direction: column; gap: 1px; }
  .empty { margin: 0; color: var(--muted); font-size: var(--fs-sm); }
</style>
