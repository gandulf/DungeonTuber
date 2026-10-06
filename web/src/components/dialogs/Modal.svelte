<script lang="ts">
  import type { Snippet } from 'svelte';
  import Icon from '../Icon.svelte';

  let { title, onclose, width = '520px', resizable = false, children, footer }: {
    title: string; onclose: () => void; width?: string; resizable?: boolean; children: Snippet; footer?: Snippet;
  } = $props();

  let dialog = $state<HTMLDialogElement | null>(null);
  // only a click that starts and ends on the backdrop closes the dialog (not a drag on the resize handle)
  let pressedBackdrop = false;

  function outside(event: MouseEvent): boolean {
    const rect = dialog!.getBoundingClientRect();
    return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom;
  }

  $effect(() => {
    if (!dialog) return;
    dialog.showModal();
    // focus the first form field instead of the close button
    dialog.querySelector<HTMLElement>('.content input:not([type=hidden]):not([hidden]), .content textarea, .content select')?.focus();
  });
</script>

<dialog bind:this={dialog} class:resizable style:width oncancel={(e) => { e.preventDefault(); onclose(); }}
        onpointerdown={(e) => (pressedBackdrop = e.target === dialog && outside(e))}
        onclick={(e) => pressedBackdrop && e.target === dialog && outside(e) && onclose()}>
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
  dialog.resizable { resize: both; overflow: hidden; min-width: min(360px, calc(100vw - 24px)); min-height: 180px; }
  dialog { padding: 0; border: 1px solid var(--border-strong); border-radius: 18px; background: var(--surface); color: var(--text); box-shadow: var(--shadow), 0 0 60px rgba(var(--ambient), 0.12); max-width: calc(100vw - 24px); max-height: calc(100vh - 40px); }
  dialog::backdrop { background: rgba(8, 6, 18, 0.55); backdrop-filter: blur(4px); }
  dialog[open] { display: flex; }
  .box { display: flex; flex-direction: column; flex: 1; min-width: 0; min-height: 0; max-height: calc(100vh - 42px); }
  header { display: flex; align-items: center; padding: 14px 16px 6px 20px; }
  h2 { margin: 0; font-size: 18px; flex: 1; font-family: var(--font-display); letter-spacing: -0.01em; }
  .content { padding: 8px 20px 16px; overflow: auto; flex: 1; min-height: 0; display: flex; flex-direction: column; }
  .content > :global(*:not(.fill)) { flex-shrink: 0; }
  footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px; border-top: 1px solid var(--border); }
</style>
