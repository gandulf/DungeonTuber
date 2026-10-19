<script lang="ts">
  import { listening, ORB_BARS } from '../../lib/dictation.svelte';

  /** The spectrum ball: a glowing core that swells with the voice, ringed by bars that follow the frequencies the microphone hears. */
  let { size = 48 }: { size?: number } = $props();

  const CENTER = 24;
  const INNER = 14; // where the bars start
  const bar = (index: number, value: number) => {
    const angle = (index / ORB_BARS) * Math.PI * 2 - Math.PI / 2;
    const reach = INNER + 1.5 + value * 8;
    return { x1: CENTER + Math.cos(angle) * INNER, y1: CENTER + Math.sin(angle) * INNER, x2: CENTER + Math.cos(angle) * reach, y2: CENTER + Math.sin(angle) * reach };
  };
</script>

<svg class="orb" viewBox="0 0 48 48" width={size} height={size} aria-hidden="true">
  <defs>
    <radialGradient id="orb-core" cx="50%" cy="40%" r="60%">
      <stop offset="0" stop-color="#fff" stop-opacity="0.95" />
      <stop offset="1" stop-color="#fff" stop-opacity="0.35" />
    </radialGradient>
  </defs>
  <circle class="core" cx={CENTER} cy={CENTER} r={7 + listening.level * 6} fill="url(#orb-core)" />
  {#each listening.bars as value, index (index)}
    {@const b = bar(index, value)}
    <line x1={b.x1} y1={b.y1} x2={b.x2} y2={b.y2} stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-opacity={0.45 + value * 0.55} />
  {/each}
</svg>

<style>
  .orb { display: block; overflow: visible; filter: drop-shadow(0 0 4px rgba(255, 255, 255, 0.6)); }
  .core { animation: orb-breathe 2.4s ease-in-out infinite; transform-origin: center; transform-box: fill-box; }
  @keyframes orb-breathe { 50% { opacity: 0.8; } }
  @media (prefers-reduced-motion: reduce) { .core { animation: none; } }
</style>
