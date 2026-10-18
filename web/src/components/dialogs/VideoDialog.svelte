<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import Modal from './Modal.svelte';

  let { youtube, title, text }: { youtube: string; title: string; text: string } = $props();
</script>

<Modal title={t(title)} onclose={closeDialog} width="min(880px, calc(100vw - 24px))">
  <p class="muted">{t(text)}</p>
  <iframe
    title={t(title)}
    src="https://www.youtube-nocookie.com/embed/{youtube}?rel=0"
    allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
    allowfullscreen
    referrerpolicy="strict-origin-when-cross-origin"
  ></iframe>
  {#snippet footer()}
    <button class="btn primary" onclick={closeDialog}>{t('Close')}</button>
  {/snippet}
</Modal>

<style>
  p { margin: 0 0 12px; }
  iframe { display: block; width: 100%; aspect-ratio: 16 / 9; border: 0; border-radius: var(--radius-lg); background: #000; }
</style>
