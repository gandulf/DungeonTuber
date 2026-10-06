<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { updateTrack } from '../../lib/stores/library.svelte';
  import { player, refreshCurrentTrack, seek, seekToChapter } from '../../lib/stores/player.svelte';
  import { errorToast, openDialog, openMenu } from '../../lib/stores/ui.svelte';
  import type { Chapter } from '../../lib/types';
  import ChapterDialog from '../dialogs/ChapterDialog.svelte';

  let bar = $state<HTMLDivElement | null>(null);
  let dragging = $state<number | null>(null);
  let hover = $state<number | null>(null);

  const duration = $derived(player.duration || player.track?.length || 0);
  const position = $derived(dragging ?? player.position);
  const chapters = $derived(player.track?.chapters ?? []);

  function format(seconds: number) {
    if (!Number.isFinite(seconds) || seconds < 0) return '00:00';
    const s = Math.round(seconds);
    return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }

  function timeAt(clientX: number) {
    const rect = bar!.getBoundingClientRect();
    return Math.max(0, Math.min(1, (clientX - rect.left) / rect.width)) * duration;
  }

  function nearChapter(seconds: number): Chapter | null {
    const tolerance = duration * 0.012;
    return chapters.find((c) => Math.abs(c.time / 1000 - seconds) <= tolerance) ?? null;
  }

  function down(event: PointerEvent) {
    if (!duration || event.button !== 0) return;
    const time = timeAt(event.clientX);
    const chapter = nearChapter(time);
    if (chapter) {
      seekToChapter(chapter);
      return;
    }
    dragging = time;
    (event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
  }

  function move(event: PointerEvent) {
    if (!duration) return;
    hover = timeAt(event.clientX);
    if (dragging !== null) {
      dragging = hover;
      seek(dragging);
    }
  }

  function up() {
    if (dragging !== null) seek(dragging);
    dragging = null;
  }

  async function saveChapters(list: Chapter[]) {
    const track = player.track;
    if (!track) return;
    try {
      const updated = await api.putChapters(track.id, list);
      updateTrack(updated);
      refreshCurrentTrack(updated);
    } catch (e) {
      errorToast(e);
    }
  }

  function editChapter(existing: Chapter | null, time: number) {
    openDialog(ChapterDialog, {
      chapter: existing,
      onSave: (title: string, light: Chapter['light']) => {
        const others = chapters.filter((c) => c !== existing);
        void saveChapters([...others, { title, time: existing ? existing.time : Math.round(time * 1000), light }]);
      },
    });
  }

  function menu(event: MouseEvent) {
    if (!player.track || !duration) return;
    const time = timeAt(event.clientX);
    const chapter = nearChapter(time);
    openMenu(event, [
      { label: chapter ? t('Edit chapter') : t('Add chapter'), icon: 'marker', action: () => editChapter(chapter, time) },
      ...(chapter ? [{ label: t('Remove chapter'), icon: 'trash', action: () => saveChapters(chapters.filter((c) => c !== chapter)) }] : []),
    ]);
  }
</script>

<div class="seek">
  <span class="time">{format(position)}</span>
  <div class="bar" bind:this={bar} role="slider" tabindex="0" aria-label={t('Position')} aria-valuemin={0} aria-valuemax={duration}
       aria-valuenow={position} onpointerdown={down} onpointermove={move} onpointerup={up} onpointerleave={() => (hover = null)}
       oncontextmenu={menu} onkeydown={(e) => { if (e.key === 'ArrowRight') seek(position + 5); if (e.key === 'ArrowLeft') seek(position - 5); }}>
    <div class="rail"><div class="progress" style:width="{duration ? (position / duration) * 100 : 0}%"></div></div>
    {#each chapters as chapter (chapter.time)}
      <div class="chapter" style:left="{duration ? (chapter.time / 1000 / duration) * 100 : 0}%" title="{format(chapter.time / 1000)} {chapter.title}">
        <span class="tick"></span>
        <span class="dot" style:background={chapter.light?.color ?? 'var(--accent)'}></span>
        <span class="clabel">{chapter.title}</span>
      </div>
    {/each}
    {#if duration}<div class="knob" style:left="{(position / duration) * 100}%"></div>{/if}
    {#if hover !== null}<div class="hover-time" style:left="{(hover / duration) * 100}%">{format(hover)}</div>{/if}
  </div>
  <span class="time">{format(duration)}</span>
</div>

<style>
  .seek { display: flex; align-items: center; gap: 10px; }
  .time { font-size: var(--fs-xs); color: var(--muted); font-variant-numeric: tabular-nums; width: 38px; text-align: center; }
  .bar { position: relative; flex: 1; height: 26px; cursor: pointer; touch-action: none; }
  .rail { position: absolute; left: 0; right: 0; top: 50%; height: 6px; margin-top: -3px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .progress { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent), var(--accent-2)); box-shadow: 0 0 10px var(--accent-glow); }
  .knob { position: absolute; top: 50%; width: 15px; height: 15px; margin: -7.5px 0 0 -7.5px; border-radius: 50%; background: #fff; border: 3px solid var(--accent); box-shadow: 0 0 0 4px var(--accent-soft); opacity: 0; transition: opacity 0.15s; }
  .bar:hover .knob { opacity: 1; }
  .chapter { position: absolute; top: 0; bottom: 0; width: 0; }
  .tick { position: absolute; top: 7px; height: 12px; width: 2px; margin-left: -1px; background: var(--text); opacity: 0.5; }
  .dot { position: absolute; top: 1px; width: 7px; height: 7px; margin-left: -3.5px; border-radius: 50%; }
  .clabel { position: absolute; bottom: -4px; transform: translateX(-50%); font-size: 9px; text-transform: uppercase; color: var(--muted); white-space: nowrap; pointer-events: none; }
  .hover-time { position: absolute; bottom: 100%; transform: translateX(-50%); font-size: var(--fs-xs); background: var(--text); color: var(--bg); padding: 1px 5px; border-radius: 4px; pointer-events: none; }
</style>
