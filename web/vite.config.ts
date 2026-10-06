import { defineConfig } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

const backend = process.env.DT_BACKEND ?? 'http://127.0.0.1:8765';

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    fs: { allow: ['..'] }, // translations live in ../core/locales
    proxy: {
      '/api': backend,
      '/media': backend,
      '/ws': { target: backend.replace(/^http/, 'ws'), ws: true },
    },
  },
  build: {
    outDir: '../server/static', // shipped inside the server package
    emptyOutDir: true,
    chunkSizeWarningLimit: 800,
  },
  test: {
    include: ['src/**/*.test.ts'],
  },
});
