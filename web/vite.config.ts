import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';

const BACKEND_TARGET = process.env.BACKEND_TARGET ?? 'http://web:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': fileURLToPath(new URL('./src/shared', import.meta.url)),
      '@uikit': fileURLToPath(new URL('./src/uikit', import.meta.url)),
    },
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/auth': {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
      '/api': {
        target: BACKEND_TARGET,
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/setupTests.ts',
    css: true,
  },
});
