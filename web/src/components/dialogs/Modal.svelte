<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from '../Icon.svelte';

  let { title, onclose, width = '520px', children, footer }: {
    title: string; onclose: () => void; width?: string; children: Snippet; footer?: Snippet;
  } = $props();

  let dialog = $state<HTMLDialogElement | null>(null);

  $effect(() => {
    if (!dialog) return;
    dialog.showModal();
    // focus the first form field instead of the close button
    dialog.querySelector<HTMLElement>('.content input:not([type=hidden]):not([hidden]), .content textarea, .content select')?.focus();
  });
</script>

<dialog bind:this={dialog} style:width oncancel={(e) => { e.preventDefault(); onclose(); }}
        onclick={(e) => e.target === dialog && onclose()}>
  <div class="box">
    <header>
      <h2>{title}</h2>
      <button class="icon-btn" aria-label="Close" onclick={onclose}><Icon name="close" size={16} /></button>
    </header>
    <div class="content">{@render children()}</div>
    {#if footer}<footer>{@render footer()}</footer>{/if}
  </div>
</dialog>

<style>
  dialog { padding: 0; border: 1px solid var(--border); border-radius: 12px; background: var(--surface); color: var(--text); box-shadow: var(--shadow); max-width: calc(100vw - 24px); max-height: calc(100vh - 40px); }
  dialog::backdrop { background: rgba(10, 12, 20, 0.45); backdrop-filter: blur(2px); }
  .box { display: flex; flex-direction: column; max-height: calc(100vh - 42px); }
  header { display: flex; align-items: center; padding: 14px 16px 6px 20px; }
  h2 { margin: 0; font-size: 17px; flex: 1; }
  .content { padding: 8px 20px 16px; overflow: auto; }
  footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border); }
</style>
