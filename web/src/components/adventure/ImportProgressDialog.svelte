<script lang="ts">
  import { onDestroy, tick } from 'svelte';
  import { t } from '../../lib/i18n.svelte';
  import { adventures, cancelImport, dismissImport, importStage, openAdventureTab } from '../../lib/stores/adventure.svelte';
  import { closeDialog, toast } from '../../lib/stores/ui.svelte';
  import type { AdventureImport } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** The imports of adventure books (PDF): a progress bar, what the import does right now and its log for each one. They are shown as
   *  long as the server has them, so an import that was started before a reload, or in another window, is found here too. */
  let { onclosed = () => {} }: { onclosed?: () => void } = $props();
  // svelte-ignore state_referenced_locally
  const closed = onclosed; // read now: the props are gone when the dialog is destroyed
  onDestroy(closed);

  // the time that has passed goes on while an import runs
  let now = $state(Date.now() / 1000);
  $effect(() => {
    const timer = setInterval(() => (now = Date.now() / 1000), 1000);
    return () => clearInterval(timer);
  });

  const percent = (job: AdventureImport) => (job.status === 'done' ? 100 : job.total > 0 ? Math.min(99, Math.round((job.step / job.total) * 100)) : 0);
  const clock = (seconds: number) => `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  const elapsed = (job: AdventureImport) => clock(Math.max(0, (job.finished || now) - job.started));
  const timeOf = (seconds: number) => new Date(seconds * 1000).toLocaleTimeString();

  async function copyLog(job: AdventureImport) {
    const text = job.log.map((line) => `${timeOf(line.time)} ${line.level.toUpperCase()} ${line.message}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      toast(t('The log was copied.'), 'success');
    } catch {
      toast(t('The log could not be copied.'), 'error');
    }
  }

  async function open(job: AdventureImport) {
    if (!job.adventure) return;
    closeDialog();
    await openAdventureTab(job.adventure);
  }

  // the log of a running import scrolls with it
  const logs = new Map<string, HTMLElement>();
  const logBox = (node: HTMLElement, id: string) => {
    logs.set(id, node);
    return { destroy: () => logs.delete(id) };
  };
  $effect(() => {
    void adventures.imports.map((job) => job.log.length).join(',');
    void tick().then(() => logs.forEach((box) => (box.scrollTop = box.scrollHeight)));
  });
</script>

<Modal title={t('Adventure imports')} onclose={closeDialog} width="640px">
  {#if !adventures.imports.length}
    <p class="muted">{t('There are no imports.')}</p>
  {/if}
  {#each adventures.imports as job (job.id)}
    <section class="job" class:error={job.status === 'error'} class:done={job.status === 'done'} class:cancelled={job.status === 'cancelled'}>
      <header>
        {#if job.status === 'running'}<span class="spinner"></span>{:else if job.status === 'done'}<Icon name="check" size={16} />{:else if job.status === 'cancelled'}<Icon name="close" size={16} />{:else}<Icon name="info" size={16} />{/if}
        <strong class="name ellipsis" title={job.name}>{job.name}</strong>
        <span class="muted time">{elapsed(job)}</span>
      </header>
      <div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={percent(job)} class:indeterminate={job.status === 'running' && job.step === 0}>
        <span style:width="{percent(job)}%"></span>
      </div>
      <div class="stage">
        <span>{job.status === 'error' ? job.error : importStage(job)}</span>
        {#if job.status === 'running'}<span class="muted">{percent(job)} %</span>{/if}
      </div>
      <details open={job.status !== 'done'}>
        <summary>{t('Log')} <span class="muted">({job.log.length})</span></summary>
        <div class="log" use:logBox={job.id}>
          {#each job.log as line, index (index)}
            <div class="line {line.level}"><span class="when">{timeOf(line.time)}</span><span class="msg">{line.message}</span></div>
          {/each}
        </div>
      </details>
      <div class="actions">
        <button class="btn sm" onclick={() => void copyLog(job)}><Icon name="copy" size={13} />{t('Copy log')}</button>
        <span class="grow"></span>
        {#if job.status === 'running'}
          <button class="btn sm danger" onclick={() => void cancelImport(job)}><Icon name="close" size={13} />{t('Cancel the import')}</button>
        {/if}
        {#if job.status === 'done' && job.adventure}
          <button class="btn sm primary" onclick={() => void open(job)}><Icon name="mask" size={13} />{t('Open the adventure')}</button>
        {/if}
        {#if job.status !== 'running'}
          <button class="btn sm" onclick={() => void dismissImport(job.id)}>{t('Dismiss')}</button>
        {/if}
      </div>
    </section>
  {/each}

  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Close')}</button>
  {/snippet}
</Modal>

<style>
  .job { display: flex; flex-direction: column; gap: 8px; padding: 12px; margin-bottom: 12px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); }
  .job.error { border-color: var(--red); }
  .job.cancelled { opacity: 0.8; }
  header { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .name { flex: 1; min-width: 0; }
  .time { font-variant-numeric: tabular-nums; font-size: var(--fs-sm); }
  .bar { position: relative; height: 8px; border-radius: 4px; overflow: hidden; background: var(--track); }
  .bar span { display: block; height: 100%; border-radius: 4px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); transition: width 0.4s ease; }
  .job.error .bar span { background: var(--red); }
  .job.done .bar span { background: var(--green, var(--accent)); }
  .job.cancelled .bar span { background: var(--faint); }
  .btn.danger { color: var(--red); }
  .bar.indeterminate span { width: 35% !important; animation: slide 1.4s ease-in-out infinite; }
  @keyframes slide { 0% { transform: translateX(-100%); } 100% { transform: translateX(290%); } }
  @media (prefers-reduced-motion: reduce) { .bar.indeterminate span { animation: none; } }
  .stage { display: flex; justify-content: space-between; gap: 8px; font-size: var(--fs-sm); }
  .job.error .stage span:first-child { color: var(--red); }
  summary { cursor: pointer; font-size: var(--fs-sm); color: var(--muted); }
  .log { margin-top: 6px; max-height: 180px; overflow-y: auto; padding: 8px; border-radius: 8px; background: var(--bg); border: 1px solid var(--border);
         font-family: var(--font-mono, ui-monospace, monospace); font-size: var(--fs-xs); line-height: 1.5; }
  .line { display: flex; gap: 8px; }
  .when { flex: none; color: var(--faint); }
  .msg { min-width: 0; overflow-wrap: anywhere; }
  .line.warning .msg { color: var(--gold); }
  .line.error .msg { color: var(--red); }
  .actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .grow { flex: 1; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
</style>
