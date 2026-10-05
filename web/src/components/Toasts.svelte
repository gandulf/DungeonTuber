<script lang="ts">
  import { dismissToast, ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';
</script>

<div class="toasts" aria-live="polite">
  {#each ui.toasts as toast (toast.id)}
    <div class="toast {toast.kind}">
      <span class="msg">{toast.message}</span>
      <button class="icon-btn" aria-label="Close" onclick={() => dismissToast(toast.id)}><Icon name="close" size={14} /></button>
    </div>
  {/each}
</div>

<style>
  .toasts { position: fixed; right: 16px; bottom: 96px; z-index: 1100; display: flex; flex-direction: column; gap: 8px; max-width: min(420px, calc(100vw - 32px)); }
  .toast { display: flex; align-items: center; gap: 8px; padding: 8px 8px 8px 14px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--border); box-shadow: var(--shadow); border-left: 4px solid var(--accent); animation: in 0.18s ease-out; }
  .toast.error { border-left-color: var(--red); }
  .toast.success { border-left-color: var(--green); }
  .msg { flex: 1; overflow-wrap: anywhere; }
  @keyframes in { from { opacity: 0; transform: translateY(6px); } }
</style>
