<script lang="ts">
  import { t } from '../lib/i18n.svelte';

  /** An IPv4 address in four boxes (xxx.xxx.xxx.xxx): a dot or the third digit moves on, backspace on an empty box goes back, a pasted address fills all boxes.
   *  `value` is "a.b.c.d" (boxes that are still empty stay empty), or '' while all of them are empty.
   *  With `broadcast` the last box starts with 255 once the first three are filled in, and an address that does not end in 255 gets a hint. */
  let { value = $bindable(''), placeholder = '255.255.255.255', label = '', broadcast = false }: { value?: string; placeholder?: string; label?: string; broadcast?: boolean } = $props();

  const split = (text: string) => {
    const parts = text.split('.').slice(0, 4);
    while (parts.length < 4) parts.push('');
    return parts;
  };
  const join = (list: string[]) => (list.every((part) => part === '') ? '' : list.join('.'));

  // svelte-ignore state_referenced_locally
  let parts = $state(split(value));
  let boxes: HTMLInputElement[] = [];
  const hints = $derived(split(placeholder));

  // a value that was set from outside (another agent, a saved setting) is shown
  $effect(() => {
    if (value !== join(parts)) parts = split(value);
  });

  function update(index: number, text: string) {
    parts[index] = text;
    value = join(parts);
  }

  function focus(index: number, atEnd = false) {
    const box = boxes[index];
    if (!box) return;
    box.focus();
    if (atEnd) box.setSelectionRange(box.value.length, box.value.length);
    else box.select();
  }

  /** A broadcast address of a home network ends in 255: the box is filled in when it is reached with the first three numbers in place. */
  function suggest(index: number) {
    if (broadcast && index === 3 && parts[3] === '' && parts.slice(0, 3).every((part) => part !== '')) update(3, '255');
  }

  const hint = $derived.by(() => {
    if (!broadcast || parts.some((part) => part === '') || parts[3] === '255') return '';
    return parts[3] === '0'
      ? t('An address that ends in 0 is the address of the network, not a broadcast address. A broadcast address ends in 255.')
      : t('A broadcast address of a home network ends in 255 (e.g. 192.168.1.255). Other numbers only fit networks with a different subnet mask.');
  });

  function onInput(event: Event, index: number) {
    const box = event.currentTarget as HTMLInputElement;
    let digits = box.value.replace(/\D/g, '').slice(0, 3);
    if (digits !== '' && Number(digits) > 255) digits = '255';
    box.value = digits;
    update(index, digits);
    // three digits, or a number that cannot get longer (26 and up), complete the box
    if (index < 3 && box === document.activeElement && (digits.length === 3 || (digits.length === 2 && Number(digits) > 25))) focus(index + 1);
  }

  function onKeydown(event: KeyboardEvent, index: number) {
    const box = event.currentTarget as HTMLInputElement;
    if (['.', ',', ' '].includes(event.key)) {
      event.preventDefault();
      if (box.value !== '') focus(index + 1);
    } else if (event.key === 'Backspace' && box.value === '' && index > 0) {
      event.preventDefault();
      focus(index - 1, true);
    } else if (event.key === 'ArrowLeft' && box.selectionStart === 0 && box.selectionEnd === 0 && index > 0) {
      event.preventDefault();
      focus(index - 1, true);
    } else if (event.key === 'ArrowRight' && box.selectionStart === box.value.length && index < 3) {
      event.preventDefault();
      focus(index + 1);
    }
  }

  function onPaste(event: ClipboardEvent) {
    const numbers = (event.clipboardData?.getData('text') ?? '').match(/\d{1,3}/g);
    if (!numbers?.length) return;
    event.preventDefault();
    const next = ['', '', '', ''];
    numbers.slice(0, 4).forEach((number, i) => (next[i] = String(Math.min(255, Number(number)))));
    parts = next;
    value = join(next);
    focus(Math.min(numbers.length, 3));
  }
</script>

<div class="wrap">
<div class="ip" role="group" aria-label={label}>
  {#each parts as part, index (index)}
    {#if index > 0}<span class="dot">.</span>{/if}
    <input class="octet" type="text" inputmode="numeric" autocomplete="off" maxlength="3" aria-label={`${label} ${index + 1}`.trim()}
           placeholder={hints[index]} value={part} bind:this={boxes[index]}
           oninput={(e) => onInput(e, index)} onkeydown={(e) => onKeydown(e, index)} onpaste={onPaste} onfocus={(e) => { suggest(index); (e.currentTarget as HTMLInputElement).select(); }} />
  {/each}
</div>
{#if hint}<span class="hint">{hint}</span>{/if}
</div>

<style>
  .wrap { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; }
  .ip { display: inline-flex; align-items: center; align-self: flex-start; gap: 4px; padding: 0 12px; border-radius: var(--radius-sm); background: var(--surface-2); border: 1px solid var(--border); }
  .ip:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .ip .octet { width: 4.6ch; padding: 8px 4px; text-align: center; border: none; border-radius: 0; background: none; box-shadow: none; font-variant-numeric: tabular-nums; }
  .ip .octet:focus { border: none; box-shadow: none; }
  .dot { color: var(--faint); user-select: none; }
  .hint { font-size: var(--fs-xs); color: var(--gold); max-width: 360px; line-height: 1.35; }
</style>
