import { defineConfig } from 'vitest/config';
import { fileURLToPath, URL } from 'node:url';
import react from '@vitejs/plugin-react';
import viteCompression from 'vite-plugin-compression';

const BACKEND_TARGET = process.env.BACKEND_TARGET ?? process.env.BACKEND_URL;
const RUNTIME_ENV = (process.env.JUKE_RUNTIME_ENV ?? 'development').toLowerCase();
const PROD_LIKE_ENVIRONMENTS = new Set(['staging', 'production']);
const SHOULD_PRECOMPRESS_ASSETS = PROD_LIKE_ENVIRONMENTS.has(RUNTIME_ENV);
const createCompressionPlugin = viteCompression as unknown as typeof import('vite-plugin-compression')['default'];

if (!BACKEND_TARGET) {
  throw new Error('BACKEND_URL must be defined for the frontend dev server.');
}

export default defineConfig({
  plugins: [
    react(),
    ...(SHOULD_PRECOMPRESS_ASSETS
      ? [
          createCompressionPlugin({
            algorithm: 'brotliCompress',
            ext: '.br',
            deleteOriginFile: false,
          }),
          createCompressionPlugin({
            algorithm: 'gzip',
            ext: '.gz',
            deleteOriginFile: false,
          }),
        ]
      : []),
  ],
  define: {
    __JUKE_RUNTIME_ENV__: JSON.stringify(RUNTIME_ENV),
  },
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
