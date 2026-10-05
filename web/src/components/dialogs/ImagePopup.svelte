<script lang="ts">
  import { closeDialog } from '../../lib/stores/ui.svelte';

  let { src, title }: { src: string; title: string } = $props();
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && closeDialog()} />

<div class="overlay" role="dialog" aria-label={title} tabindex="-1" onclick={closeDialog} onkeydown={() => {}}>
  <img {src} alt={title} />
  <span class="caption">{title}</span>
</div>

<style>
  .overlay { position: fixed; inset: 0; z-index: 900; background: rgba(0, 0, 0, 0.8); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; cursor: zoom-out; }
  img { max-width: 90vw; max-height: 82vh; border-radius: 10px; box-shadow: 0 10px 40px rgba(0,0,0,.6); }
  .caption { color: white; font-weight: 600; }
</style>
