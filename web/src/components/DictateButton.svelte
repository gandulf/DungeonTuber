<script lang="ts">
  import { onDestroy } from 'svelte';
  import { createDictation, dictationSupported } from '../lib/dictation.svelte';
  import { t } from '../lib/i18n.svelte';
  import { data } from '../lib/stores/data.svelte';
  import Icon from './Icon.svelte';

  /** The microphone button of a text box: the first click starts listening, each phrase is transcribed after a pause and given to `ontext`; a second click, or
   *  a few seconds without speech, ends it.
   *  It is hidden while no AI service (Groq or Gemini) is set up for the transcription or when the browser cannot record. */
  let { ontext, disabled = false }: { ontext: (text: string) => void; disabled?: boolean } = $props();

  const { dictation, toggle, cancel } = createDictation((text) => ontext(text));
  onDestroy(cancel);

  const label = $derived(dictation.state === 'recording' ? t('Stop dictating') : dictation.pending ? t('Transcribing…') : t('Dictate'));
</script>

{#if data.settings?.dictationConfigured && dictationSupported()}
  <button type="button" class="dictate" class:recording={dictation.state === 'recording'} class:working={dictation.pending > 0}
          disabled={disabled} title={label} aria-label={label} aria-pressed={dictation.state === 'recording'}
          onmousedown={(e) => e.preventDefault()} onclick={toggle}>
    <Icon name={dictation.state === 'recording' ? 'stop' : 'mic'} size={16} />
  </button>
{/if}

<style>
  .dictate { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; padding: 0; border-radius: 8px; color: var(--muted); }
  .dictate:hover:not(:disabled) { background: var(--hover); color: var(--text); }
  .dictate.recording { background: var(--red-soft); color: var(--red); animation: dictate-pulse 1.2s ease-in-out infinite; }
  .dictate.working:not(.recording) { opacity: 0.5; }
  .dictate:disabled { cursor: default; }
  @keyframes dictate-pulse { 50% { opacity: 0.55; } }
</style>
