import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'VITE_');
  if (mode === 'production') {
    // Production must talk to the real control plane and must never contain test seeding.
    if (env.VITE_API_MODE !== 'http') throw new Error('Production builds require VITE_API_MODE=http');
    if (env.VITE_ENABLE_TEST_SEED === 'true') throw new Error('VITE_ENABLE_TEST_SEED must not be set for production builds');
  }
  return {
    plugins: [react()],
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    server: { port: 5173, proxy: env.VITE_API_MODE === 'http' ? { '/api': 'http://127.0.0.1:8000' } : undefined },
  };
});
