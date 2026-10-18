<script lang="ts">
  import { locale, t } from '../lib/i18n.svelte';
  import { INTRO_VIDEOS, VIDEOS } from '../lib/videos';

  // the player is only loaded after a click, so the page makes no request to YouTube before that
  let playing = $state<string | null>(null); // the teaser whose player is shown

  const intro = $derived(INTRO_VIDEOS[locale()] ? locale() : 'en');
  // the announced videos that exist in the user's language, after the intro
  const more = $derived(VIDEOS.filter((v) => v.youtube[locale()] && v.thumb[locale()]));
</script>

<div class="teasers">
  {@render teaser('intro', INTRO_VIDEOS[intro], intro === 'en' ? '/intro-teaser.jpg' : `/intro-teaser.${intro}.jpg`, t('Play intro video'), t('New here?'), t('Watch the 3 minute intro to DungeonTuber'))}
  {#each more as video (video.key)}
    {@render teaser(video.key, video.youtube[locale()], video.thumb[locale()], t('Play video'), t(video.title), t(video.teaser))}
  {/each}
</div>

{#snippet teaser(key: string, youtube: string, thumb: string, label: string, title: string, text: string)}
  <section class="teaser">
    {#if playing === key}
      <iframe
        title="DungeonTuber"
        src="https://www.youtube-nocookie.com/embed/{youtube}?autoplay=1&rel=0"
        allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
        allowfullscreen
        referrerpolicy="strict-origin-when-cross-origin"
      ></iframe>
    {:else}
      <button class="thumb" type="button" aria-label={label} onclick={() => (playing = key)}>
        <img src={thumb} alt="" loading="lazy" />
        <span class="play" aria-hidden="true"><svg viewBox="0 0 24 24" width="28" height="28"><path d="M8 5v14l11-7z" fill="currentColor" /></svg></span>
      </button>
    {/if}
    <p><strong>{title}</strong> <span class="muted">{text}</span></p>
  </section>
{/snippet}

<style>
  .teasers { display: flex; flex-wrap: wrap; justify-content: center; gap: 20px; width: 100%; }
  .teaser { width: min(360px, 100%); display: flex; flex-direction: column; gap: 8px; text-align: center; }
  .teaser p { margin: 0; font-size: var(--fs-sm); }
  .thumb, iframe { position: relative; display: block; width: 100%; aspect-ratio: 16 / 9; border: 0; padding: 0; border-radius: var(--radius-lg); overflow: hidden; box-shadow: var(--shadow); background: #000; }
  .thumb { cursor: pointer; }
  .thumb img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform 0.3s ease; }
  .thumb:hover img, .thumb:focus-visible img { transform: scale(1.04); }
  .play { position: absolute; inset: 0; margin: auto; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; color: #fff; background: rgba(var(--ambient), 0.9); box-shadow: 0 4px 18px rgba(0, 0, 0, 0.4); }
</style>
