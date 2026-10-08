<script lang="ts">
  import { api } from '../lib/api';
  import { data } from '../lib/stores/data.svelte';
  import { locale, t } from '../lib/i18n.svelte';

  let { onLogin }: { onLogin: () => void } = $props();
  let username = $state('');
  let password = $state('');
  let error = $state<string | null>(null);
  let busy = $state(false);
  let playing = $state(false);

  // YouTube id per language; a language without its own video falls back to the English one
  const INTRO_VIDEOS: Record<string, string> = { en: '85AZrB7YnOY', de: '6qrLKajl07k' };
  const intro = $derived(INTRO_VIDEOS[locale()] ? locale() : 'en');
  const introVideo = $derived(INTRO_VIDEOS[intro]);

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

  <!-- the player is only loaded after a click, so the login page makes no request to YouTube before that -->
  <section class="teaser">
    {#if playing}
      <iframe
        title="DungeonTuber"
        src="https://www.youtube-nocookie.com/embed/{introVideo}?autoplay=1&rel=0"
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        allowfullscreen
        referrerpolicy="strict-origin-when-cross-origin"
      ></iframe>
    {:else}
      <button class="thumb" type="button" aria-label={t('Play intro video')} onclick={() => (playing = true)}>
        <img src={intro === 'en' ? '/intro-teaser.jpg' : `/intro-teaser.${intro}.jpg`} alt="" loading="lazy" />
        <span class="play" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28"><path d="M8 5v14l11-7z" fill="currentColor" /></svg></span>
      </button>
    {/if}
    <p><strong>{t('New here?')}</strong> <span class="muted">{t('Watch the 3 minute intro to DungeonTuber')}</span></p>
  </section>
</div>

<style>
  .wrap { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 20px; padding: 16px; overflow-y: auto; }
  .teaser { width: min(360px, 100%); display: flex; flex-direction: column; gap: 8px; text-align: center; }
  .teaser p { margin: 0; font-size: var(--fs-sm); }
  .thumb, iframe { position: relative; display: block; width: 100%; aspect-ratio: 16 / 9; border: 0; padding: 0; border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow); background: #000; }
  .thumb { cursor: pointer; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s ease; }
  .thumb:hover img, .thumb:focus-visible img { transform: scale(1.04); }
  .play { position: absolute; inset: 0; margin: auto; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; color: #fff; background: rgba(var(--ambient), 0.9); box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4); }
  .card { width: min(360px, 100%); padding: 28px; display: flex; flex-direction: column; gap: 14px; align-items: stretch; text-align: center; }
  .card img { align-self: center; }
  h1 { margin: 0; font-size: 22px; }
  label { display: flex; flex-direction: column; gap: 6px; text-align: left; }
  .error { color: var(--red); margin: 0; }
</style>
