<script lang="ts">
  import { PDFViewer, type PluginRegistry } from '@embedpdf/svelte-pdf-viewer';
  // the PDF engine (PDFium as WebAssembly) is served with the app: no request to a CDN
  import wasmUrl from '@embedpdf/pdfium/pdfium.wasm?url';
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import Modal from './Modal.svelte';

  /** The PDF of an adventure book (the viewer of EmbedPDF), opened at `page`. With `onpick` it chooses a page for a link: the page
   *  field follows the viewer (and moves it), it only takes pages the book has, and `onpick` gets the chosen page, or null when the
   *  dialog is closed without one. */
  let { adventureId, title, page = 1, onpick }: { adventureId: string; title: string; page?: number; onpick?: (page: number | null) => void } = $props();

  interface ScrollApi {
    scrollToPage(options: { pageNumber: number; behavior?: ScrollBehavior }): void;
    getTotalPages(): number;
    onLayoutReady(handler: (event: { isInitial: boolean; totalPages: number }) => void): unknown;
    onPageChange(handler: (event: { pageNumber: number; totalPages: number }) => void): unknown;
  }

  // svelte-ignore state_referenced_locally
  const start = page;
  let scroll: ScrollApi | null = null;
  let total = $state(0); // the pages of the book, known once the document is open
  // svelte-ignore state_referenced_locally
  let current = $state(start);
  let finished = false;

  /** A valid page of the book: a whole number from 1 to the last page. */
  const valid = (value: number) => Math.min(Math.max(1, Math.round(value) || 1), total || Math.max(1, Math.round(value) || 1));

  function goTo(value: number) {
    current = valid(value);
    scroll?.scrollToPage({ pageNumber: current, behavior: 'instant' });
  }

  function ready(registry: PluginRegistry) {
    scroll = (registry.getPlugin('scroll') as { provides(): ScrollApi } | null)?.provides() ?? null;
    if (!scroll) return;
    scroll.onPageChange((event) => {
      current = event.pageNumber;
      total = event.totalPages;
    });
    // the first page asked for is scrolled to as soon as the pages are laid out (the document may already be there)
    scroll.onLayoutReady((event) => {
      total = event.totalPages;
      if (event.isInitial && start > 1) goTo(start);
    });
    try {
      total = scroll.getTotalPages();
      if (total && start > 1) goTo(start);
    } catch {
      // no document yet: the layout event does it
    }
  }

  function finish(picked: number | null) {
    if (finished) return;
    finished = true;
    const pick = onpick; // read before the dialog is closed: its props are gone afterwards
    closeDialog();
    pick?.(picked);
  }

  // svelte-ignore state_referenced_locally
  const config = {
    src: `/api/adventures/${encodeURIComponent(adventureId)}/pdf`,
    wasmUrl: new URL(wasmUrl, window.location.href).href, // absolute: the engine runs in a worker made from a blob, which cannot resolve a path
    fontFallback: null, // no fonts from a CDN
    tabBar: 'never' as const,
    theme: { preference: prefs.theme === 'dark' ? 'dark' as const : 'light' as const },
    permissions: { enforceDocumentPermissions: false }, // the book is the user's own: a protected PDF is only read here
    disabledCategories: ['annotation', 'redaction', 'document-print'],
  };
</script>

<Modal resizable title={title || t('Adventure book')} onclose={() => finish(null)} width="min(1100px, calc(100vw - 24px))">
  <div class="viewer"><PDFViewer {config} onready={ready} style="height: 100%; width: 100%" /></div>

  {#snippet footer()}
    {#if onpick}
      <label class="page">{t('Page')}
        <input type="number" min="1" max={total || undefined} step="1" value={current} disabled={!total}
               onchange={(e) => { goTo(Number(e.currentTarget.value)); e.currentTarget.value = String(current); }} />
        {#if total}<span class="muted">{t('of {0}', total)}</span>{/if}
      </label>
      <span class="grow"></span>
      <button class="btn" onclick={() => finish(null)}>{t('Cancel')}</button>
      <button class="btn primary" disabled={!total} onclick={() => finish(valid(current))}><Icon name="link" size={15} /> {t('Link this page')}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .viewer { height: min(78vh, 1000px); min-height: 320px; }
  .page { display: inline-flex; align-items: center; gap: 8px; }
  .page input { width: 80px; }
  .grow { flex: 1; }
</style>
