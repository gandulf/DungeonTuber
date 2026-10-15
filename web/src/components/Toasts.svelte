<script lang="ts">
  import { dismissToast, ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';

  // A modal dialog (the settings) lies in the top layer of the browser, above everything with a z-index, so the toasts are a popover:
  // it is shown again with every new toast, which puts it above the dialog that is open at that moment.
  let element = $state<HTMLElement | null>(null);
  $effect(() => {
    if (!element) return;
    const count = ui.toasts.length;
    void ui.toasts.at(-1)?.id;
    if (element.matches(':popover-open')) element.hidePopover();
    if (count) element.showPopover();
  });
</script>

<div class="toasts" popover="manual" aria-live="polite" bind:this={element}>
  {#each ui.toasts as toast (toast.id)}
    <div class="toast {toast.kind}">
      <span class="msg">{toast.message}</span>
      <button class="icon-btn" aria-label="Close" onclick={() => dismissToast(toast.id)}><Icon name="close" size={14} /></button>
    </div>
  {/each}
</div>

<style>
  /* a popover has the look of a box by default */
  .toasts { position: fixed; inset: auto 16px 96px auto; margin: 0; padding: 0; border: none; background: none; color: inherit; overflow: visible; z-index: 1100; flex-direction: column; gap: 8px; max-width: min(420px, calc(100vw - 32px)); }
  .toasts:popover-open { display: flex; }
  .toast { display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 14px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow); border-left: 4px solid var(--accent); animation: in 0.18s ease-out; }
  .toast.error { border-left-color: var(--red); }
  .toast.success { border-left-color: var(--green); }
  .msg { flex: 1; overflow-wrap: anywhere; }
  @keyframes in { from { opacity: 0; transform: translateY(6px); } }
</style>
