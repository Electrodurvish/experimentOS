/// <reference types="vitest/config" />
import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  // Override with VITE_API_PROXY=http://host:port in .env.local if the API runs elsewhere.
  const backend = loadEnv(mode, '.', '').VITE_API_PROXY || 'http://localhost:8000';
  const proxy = { target: backend, changeOrigin: true };
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { '/api': proxy, '/healthz': proxy, '/readyz': proxy, '/metrics': proxy },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            react: ['react', 'react-dom', 'react-router-dom'],
            charts: ['recharts'],
          },
        },
      },
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts'],
      css: false,
    },
  };
});
