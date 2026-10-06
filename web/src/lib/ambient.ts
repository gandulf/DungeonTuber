// Tints the UI with the average colour of the current cover (CSS variable --ambient).
const cache = new Map<string, string>();
const FALLBACK = '124, 92, 255';

export async function applyAmbient(url: string | null) {
  const root = document.documentElement;
  if (!url) {
    root.style.setProperty('--ambient', FALLBACK);
    return;
  }
  const cached = cache.get(url);
  if (cached) {
    root.style.setProperty('--ambient', cached);
    return;
  }
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 16;
    const ctx = canvas.getContext('2d', { willReadFrequently: true })!;
    ctx.drawImage(image, 0, 0, 16, 16);
    const data = ctx.getImageData(0, 0, 16, 16).data;
    let r = 0, g = 0, b = 0, weight = 0;
    for (let i = 0; i < data.length; i += 4) {
      const max = Math.max(data[i], data[i + 1], data[i + 2]);
      const min = Math.min(data[i], data[i + 1], data[i + 2]);
      const w = 1 + (max - min) / 32; // prefer saturated pixels
      r += data[i] * w; g += data[i + 1] * w; b += data[i + 2] * w; weight += w;
    }
    const value = `${Math.round(r / weight)}, ${Math.round(g / weight)}, ${Math.round(b / weight)}`;
    cache.set(url, value);
    root.style.setProperty('--ambient', value);
  } catch {
    root.style.setProperty('--ambient', FALLBACK);
  }
}
