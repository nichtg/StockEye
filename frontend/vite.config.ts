/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv } from 'vite';
import { cspPlugin, spa404Plugin } from './build-tools/plugins';
import { resolveApiBaseUrl, resolveBasePath } from './src/lib/config';

// Locally the API is same-origin (the dev proxy below, or the docker-compose nginx). For GitHub
// Pages, VITE_API_BASE_URL points at the API host and VITE_BASE_PATH at the repository path.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  return {
    base: resolveBasePath(env.VITE_BASE_PATH),
    plugins: [react(), cspPlugin(resolveApiBaseUrl(env.VITE_API_BASE_URL)), spa404Plugin()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target: 'http://127.0.0.1:8000', changeOrigin: false },
      },
    },
    build: {
      sourcemap: false,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
      css: false,
      restoreMocks: true,
      unstubGlobals: true,
    },
  };
});
