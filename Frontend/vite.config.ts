import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { defineConfig } from 'vite';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
  server: {
    port: 3000,
    // Everything under /api goes to the FastAPI backend. The browser only ever
    // talks to :3000, so there is no CORS to configure and no absolute URLs in
    // the React code -- fetch('/api/jobs') works unchanged in production, where
    // FastAPI serves the built frontend itself.
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    // FastAPI serves this directory in production (see DIST in app.py).
    outDir: 'dist',
  },
});